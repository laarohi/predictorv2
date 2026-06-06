"""Web Push sender (VAPID) — the push counterpart of services/email.py.

`pywebpush` is synchronous (requests-based), so each send runs in a worker
thread via ``anyio.to_thread`` to avoid blocking the FastAPI event loop.

Behavioural parity with email.py:
- Blank VAPID keys make every send a no-op (returns ``SKIPPED``), exactly
  like a blank ``RESEND_API_KEY`` — dev/test boot and run without push.

The push service signals subscription death via HTTP status:
- 404 / 410  -> the endpoint is gone; the caller DELETEs the row.
- 403        -> usually a bad VAPID subject/key or server clock skew
                (iOS returns ``BadJwtToken``); logged, treated as a
                transient failure so we don't lose the subscription.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

import anyio
import requests
from pywebpush import WebPushException, webpush
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import get_settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)

# Drop the push if the device is offline for longer than this (seconds).
_PUSH_TTL = 60 * 60 * 12  # 12h


class PushOutcome(str, Enum):
    SENT = "sent"
    SKIPPED = "skipped"  # VAPID not configured
    DEAD = "dead"        # 404/410 — caller should delete the subscription
    FAILED = "failed"    # transient/other — safe to retry next tick


@dataclass(frozen=True, slots=True)
class PushResult:
    outcome: PushOutcome
    status_code: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == PushOutcome.SENT


def _send_sync(sub_info: dict, data: str, vapid_private_key: str, vapid_claims: dict) -> int:
    """Blocking pywebpush call — runs in a worker thread.

    `webpush` mutates the claims dict (fills in ``aud`` from the endpoint
    and ``exp``), so it gets a fresh copy each call.
    """
    response = webpush(
        subscription_info=sub_info,
        data=data,
        vapid_private_key=vapid_private_key,
        vapid_claims=dict(vapid_claims),
        ttl=_PUSH_TTL,
        timeout=10,  # a slow/hostile endpoint must not pin a thread-pool worker
    )
    return response.status_code


async def send_push(subscription: PushSubscription, payload: dict) -> PushResult:
    """Send one notification to one device subscription."""
    settings = get_settings()
    if not (settings.vapid_private_key and settings.vapid_public_key):
        logger.warning("send_push called but VAPID keys are blank — skipping")
        return PushResult(PushOutcome.SKIPPED)

    sub_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    claims = {"sub": settings.vapid_subject}  # aud is auto-derived from endpoint

    try:
        status = await anyio.to_thread.run_sync(
            _send_sync, sub_info, json.dumps(payload), settings.vapid_private_key, claims
        )
        return PushResult(PushOutcome.SENT, status_code=status)
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            # Log only the host, never the token-bearing endpoint path.
            logger.info(
                "push subscription dead (%s): host=%s",
                status,
                urlparse(subscription.endpoint).netloc,
            )
            return PushResult(PushOutcome.DEAD, status_code=status, error=str(exc))
        logger.warning("push send failed (%s): %s", status, exc)
        return PushResult(PushOutcome.FAILED, status_code=status, error=str(exc))
    except requests.exceptions.RequestException as exc:
        # Transport blip (push service briefly unreachable / timeout) — expected
        # and retryable; warn rather than emit a full stack trace.
        logger.warning("push transport error: %s", exc)
        return PushResult(PushOutcome.FAILED, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("push send unexpected error")
        return PushResult(PushOutcome.FAILED, error=str(exc))


async def send_to_user(session: AsyncSession, user_id: uuid.UUID, payload: dict) -> int:
    """Send a payload to all of a user's active subscriptions.

    Purges any subscription the push service reports as dead (404/410).
    Returns the count of successful sends. Commits once at the end.
    """
    result = await session.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.active.is_(True),
        )
    )
    subscriptions = list(result.scalars().all())

    sent = 0
    dirty = False
    for sub in subscriptions:
        res = await send_push(sub, payload)
        if res.ok:
            sent += 1
        elif res.outcome == PushOutcome.DEAD:
            await session.delete(sub)
            dirty = True

    if dirty:
        try:
            await session.commit()
        except Exception:  # noqa: BLE001
            # The dead-row purge is best-effort cleanup; never let it mask a
            # successful delivery count or abort the caller (e.g. a future tick).
            logger.exception("push: failed to commit dead-subscription purge")
            await session.rollback()
    return sent
