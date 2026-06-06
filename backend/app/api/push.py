"""Web Push subscription endpoints.

The frontend flow:
  1. GET  /push/vapid-public-key  -> the applicationServerKey for subscribe()
  2. POST /push/subscribe         -> store the browser's PushSubscription
  3. POST /push/status            -> is THIS device active server-side?
  4. POST /push/unsubscribe       -> deactivate (on logout / disable toggle)
  5. POST /push/test              -> send the current user a test buzz

Subscriptions are upserted by `endpoint` (globally unique) via an atomic
INSERT ... ON CONFLICT, so a double-tap / re-fired subscribe is idempotent
rather than a 500. The endpoint is treated as UNTRUSTED client input: it is
length-bounded and its host is allowlisted to real push services (the value
is later fetched server-side by pywebpush, so an unvalidated URL would be an
SSRF sink). Re-subscribing re-points the device's channel at the current
user (a device's push channel follows whoever is logged in on it).
"""

import asyncio
import logging
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import select

from app.config import get_settings
from app.database import async_session_maker
from app.dependencies import AdminUser, CurrentUser, DbSession
from app.models._datetime import utc_now
from app.models.push_subscription import PushSubscription
from app.services.push import send_to_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Real push-service hosts. The stored endpoint is fetched server-side, so we
# only accept https URLs whose host belongs to a known push service — this
# closes the SSRF vector (no localhost / 169.254.x / internal addresses).
_ALLOWED_PUSH_HOST_SUFFIXES = (
    ".push.apple.com",            # Safari / iOS  (web.push.apple.com)
    ".notify.windows.com",        # Edge / WNS
    ".push.services.mozilla.com", # Firefox
)
_ALLOWED_PUSH_HOSTS_EXACT = frozenset({"fcm.googleapis.com"})  # Chrome / Edge / FCM


def _validate_endpoint(endpoint: str) -> None:
    """Reject anything that isn't an https URL to a known push service."""
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    ok = parsed.scheme == "https" and (
        host in _ALLOWED_PUSH_HOSTS_EXACT
        or any(host.endswith(suffix) for suffix in _ALLOWED_PUSH_HOST_SUFFIXES)
    )
    if not ok:
        raise HTTPException(status_code=422, detail="Unsupported push endpoint")


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=255)
    auth: str = Field(max_length=255)


class SubscribeRequest(BaseModel):
    # Shape of the browser's PushSubscription.toJSON(); expirationTime ignored.
    endpoint: str = Field(max_length=2048)
    keys: PushKeys


class EndpointRequest(BaseModel):
    endpoint: str = Field(max_length=2048)


@router.get("/vapid-public-key")
async def vapid_public_key() -> dict:
    """Public VAPID key for the browser's pushManager.subscribe().

    Not secret. Empty string if push isn't configured — the frontend treats
    that as "push unavailable" and hides the opt-in.
    """
    return {"key": get_settings().vapid_public_key}


@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    current_user: CurrentUser,
    session: DbSession,
    request: Request,
) -> dict:
    """Store (or refresh) a device subscription for the current user."""
    _validate_endpoint(body.endpoint)
    user_agent = (request.headers.get("user-agent") or "")[:512]
    now = utc_now()

    # Atomic upsert by endpoint — idempotent under a double-fired subscribe.
    # (A Core insert bypasses the model's default_factory, so id/timestamps
    # are supplied explicitly.)
    stmt = (
        pg_insert(PushSubscription)
        .values(
            id=uuid.uuid4(),
            user_id=current_user.id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            active=True,
            user_agent=user_agent,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["endpoint"],
            set_={
                "user_id": current_user.id,
                "p256dh": body.keys.p256dh,
                "auth": body.keys.auth,
                "active": True,
                "user_agent": user_agent,
                "updated_at": now,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()
    return {"status": "subscribed"}


@router.post("/status")
async def status(
    body: EndpointRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """Whether THIS device's subscription is active for the current user.

    The browser-side subscription can outlive a server-side deactivation
    (logout / disable keep the browser subscription per the iOS rules), so
    the toggle reconciles its 'enabled' state against this instead of trusting
    pushManager.getSubscription() alone.
    """
    row = (
        await session.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == body.endpoint,
                PushSubscription.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    return {"active": bool(row and row.active)}


@router.post("/unsubscribe")
async def unsubscribe(
    body: EndpointRequest,
    current_user: CurrentUser,
    session: DbSession,
) -> dict:
    """Deactivate a device subscription (we keep the row — see model docstring)."""
    existing = (
        await session.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == body.endpoint,
                PushSubscription.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.active = False
        existing.updated_at = utc_now()
        await session.commit()

    return {"status": "unsubscribed"}


@router.post("/test")
async def test_push(current_user: CurrentUser, session: DbSession) -> dict:
    """Send the current user a test notification across their devices."""
    payload = {
        "title": "CxF Predictaa",
        "body": "🔔 Notifications are on — you're all set.",
        "url": "/",
    }
    sent = await send_to_user(session, current_user.id, payload)
    return {"sent": sent}


# One of every alert shape, mirroring the copy in services/push_triggers.py —
# an admin QA tool to preview rendering/delivery on-device without waiting for
# the real events. Keep in sync with the trigger payloads.
_SAMPLE_INTERVAL_SECONDS = 10
SAMPLE_ALERTS: list[dict] = [
    {
        "title": "⏰ Predictions close in ~24 hours",
        "body": "You've still got 5 picks to fill before kickoff.",
        "url": "/predictions",
    },
    {
        "title": "⏰ Predictions lock soon",
        "body": "Brazil v Croatia kicks off shortly — get your score in.",
        "url": "/predictions",
    },
    {"title": "England 2–1 France", "body": "You predicted 2–1 — +15 pts 🎯", "url": "/results"},
    {"title": "Spain 3–0 Japan", "body": "You predicted 2–0 — +5 pts ✅", "url": "/results"},
    {"title": "Brazil 1–2 Argentina", "body": "You predicted 1–1 — +0 pts ❌", "url": "/results"},
    {
        "title": "Knockouts are live 🏆",
        "body": "Phase 2 is open — make your knockout picks.",
        "url": "/predictions",
    },
]

# Hold references to in-flight sample tasks so they aren't garbage-collected
# mid-run (asyncio only keeps weak refs to bare create_task results).
_sample_tasks: set[asyncio.Task] = set()


async def _send_sample_alerts(user_id: uuid.UUID) -> None:
    """Send each sample alert to the user's devices, ~10s apart, in its own session."""
    async with async_session_maker() as session:
        for i, payload in enumerate(SAMPLE_ALERTS):
            if i:
                await asyncio.sleep(_SAMPLE_INTERVAL_SECONDS)
            try:
                await send_to_user(session, user_id, payload)
            except Exception:  # noqa: BLE001
                logger.exception("push: sample alert send failed")


@router.post("/test-samples")
async def test_samples(current_user: AdminUser) -> dict:
    """Admin QA: fire one of every alert shape to the caller's own devices,
    spaced ~10s apart, in the background (so they land on a locked screen)."""
    task = asyncio.create_task(_send_sample_alerts(current_user.id))
    _sample_tasks.add(task)
    task.add_done_callback(_sample_tasks.discard)
    return {"scheduled": len(SAMPLE_ALERTS), "interval_seconds": _SAMPLE_INTERVAL_SECONDS}
