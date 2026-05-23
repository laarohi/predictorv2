"""Transactional email via Resend.

Thin async wrapper around Resend's HTTP API (single POST per email,
JSON body, bearer-token auth). Kept dependency-free beyond `httpx`,
which is already a project dependency.

Behavioural notes:

- If `RESEND_API_KEY` is blank the service logs a warning and returns
  the sentinel `EMAIL_SKIPPED` instead of raising. This lets dev/test
  environments run end-to-end without leaking real emails — anything
  that "would have" sent still completes without a 500.
- 5xx responses retry with exponential backoff (capped at 3 attempts:
  0s, 1s, 4s). 4xx responses fail fast — they're permanent errors
  (bad From address, invalid recipient, malformed payload).
- The Resend API returns `{"id": "..."}` on success; that id is the
  message identifier you'd reference for a delivery-status lookup.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


RESEND_API_URL = "https://api.resend.com/emails"
EMAIL_SKIPPED = "skipped:no-api-key"
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


class EmailSendError(RuntimeError):
    """Raised when Resend returns a non-retryable error (4xx) or all
    retry attempts on 5xx are exhausted."""


@dataclass(frozen=True, slots=True)
class EmailResult:
    """What happened when we tried to send.

    `message_id` is Resend's id on success, or the EMAIL_SKIPPED
    sentinel if the API key was blank, or None if the send failed.
    """

    message_id: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.message_id is not None and self.message_id != EMAIL_SKIPPED


async def send_email(
    *,
    to: str | Iterable[str],
    subject: str,
    html: str,
    text: str | None = None,
    from_address: str | None = None,
) -> EmailResult:
    """Send one email via Resend.

    Args:
        to: Single address or iterable of addresses. Resend accepts up
            to 50 recipients per send.
        subject: Email subject line.
        html: HTML body. Required (Resend rejects emails with neither
            HTML nor text).
        text: Optional plain-text alternative. Strongly recommended —
            improves deliverability and renders cleanly in clients that
            block HTML by default.
        from_address: Override the configured EMAIL_FROM. Use sparingly;
            the configured value should be correct for production.
    """
    settings = get_settings()

    if not settings.resend_api_key:
        logger.warning(
            "send_email called but RESEND_API_KEY is blank — returning skipped sentinel"
        )
        return EmailResult(message_id=EMAIL_SKIPPED)

    recipients = [to] if isinstance(to, str) else list(to)
    payload: dict[str, object] = {
        "from": from_address or settings.email_from,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }

    last_error: str | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        for attempt in range(_MAX_RETRIES):
            try:
                response = await client.post(RESEND_API_URL, json=payload, headers=headers)
            except httpx.TimeoutException as e:
                last_error = f"timeout: {e}"
                await _backoff(attempt)
                continue
            except httpx.RequestError as e:
                last_error = f"connection error: {e}"
                await _backoff(attempt)
                continue

            if response.status_code == 200:
                body = response.json()
                message_id = body.get("id")
                if not message_id:
                    last_error = f"resend returned no id: {body!r}"
                    raise EmailSendError(last_error)
                logger.info("send_email ok: id=%s to=%s", message_id, recipients)
                return EmailResult(message_id=message_id)

            # 4xx: permanent. Don't retry.
            if 400 <= response.status_code < 500:
                detail = _extract_error_detail(response)
                last_error = f"resend {response.status_code}: {detail}"
                logger.error("send_email failed (no retry): %s", last_error)
                raise EmailSendError(last_error)

            # 5xx: retryable.
            detail = _extract_error_detail(response)
            last_error = f"resend {response.status_code}: {detail}"
            logger.warning(
                "send_email transient failure attempt %d/%d: %s",
                attempt + 1, _MAX_RETRIES, last_error,
            )
            await _backoff(attempt)

    # All retries exhausted.
    raise EmailSendError(f"send_email retries exhausted: {last_error}")


async def _backoff(attempt: int) -> None:
    """Exponential backoff: 0s, 1s, 4s for attempts 0, 1, 2."""
    if attempt == 0:
        return
    delay = _BACKOFF_BASE_SECONDS * (4 ** (attempt - 1))
    await asyncio.sleep(delay)


def _extract_error_detail(response: httpx.Response) -> str:
    """Best-effort parse of Resend's error body. Falls back to status text."""
    try:
        body = response.json()
        if isinstance(body, dict):
            # Resend's error shape: {"statusCode": N, "message": "...", "name": "..."}
            msg = body.get("message") or body.get("error") or str(body)
            return str(msg)
    except (ValueError, KeyError):
        pass
    return response.text[:200] or response.reason_phrase
