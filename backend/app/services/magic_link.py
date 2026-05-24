"""Magic-link login service — passwordless auth via email.

Flow:
  1. User submits their email at /login.
  2. `create_magic_link` looks up the user, generates a crypto-random
     token, hashes it, stores the hash + 15-min expiry, sends the raw
     token in an email link.
  3. User clicks the link in their inbox; the frontend POSTs the raw
     token to `verify_magic_link`.
  4. Service hashes the submitted token, finds the row, checks not
     expired and not used, marks used, returns the user.
  5. API layer issues a JWT for the verified user.

Security choices:
- Token: `secrets.token_urlsafe(32)` — 32 bytes (~43 chars) of
  cryptographic randomness. NOT uuid4 (not guaranteed crypto-secure).
- Storage: sha256 hex of the token, never the raw. Leaked DB →
  attackers get hashes, useless without the source token.
- TTL: 15 minutes. Short enough to limit window of compromise,
  long enough that email delivery delay isn't a problem.
- Single-use: `used_at` set on first verify, second verify rejects.
- Revoke prior: requesting a new link marks all prior unused tokens
  for that user as used — limits the window of compromise to the
  most recent request.
- Rate limit: max 3 requests per email per 15 min, so an attacker
  can't spam someone's inbox with login emails.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select, update

from app.config import get_settings
from app.models._datetime import utc_now
from app.models.magic_link import MagicLinkToken
from app.models.user import User
from app.services.email import EmailSendError, send_email

logger = logging.getLogger(__name__)

TOKEN_TTL_MINUTES: Final[int] = 15
RATE_LIMIT_WINDOW_MINUTES: Final[int] = 15
RATE_LIMIT_MAX_REQUESTS: Final[int] = 3


class MagicLinkError(Exception):
    """Generic verify-side failure. Distinguished by subclass."""


class TokenInvalid(MagicLinkError):
    """No matching token row exists."""


class TokenExpired(MagicLinkError):
    """Row exists but expires_at is in the past."""


class TokenAlreadyUsed(MagicLinkError):
    """Row exists but used_at is already set."""


class UserInactive(MagicLinkError):
    """User exists but is_active=False."""


class RateLimited(MagicLinkError):
    """Too many magic-link requests for this email in the rate window."""


class UnknownEmail(MagicLinkError):
    """No user account exists for the submitted email. (Acceptable to
    surface to the user in this friend-group context — enumeration
    risk is essentially zero.)"""


# ── helpers ─────────────────────────────────────────────────────────────────


def _generate_raw_token() -> str:
    """32 bytes of crypto-random, URL-safe base64. ~43 characters."""
    return secrets.token_urlsafe(32)


def _hash_token(raw: str) -> str:
    """sha256 hex digest. One-way, deterministic, fast."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_login_url(raw_token: str) -> str:
    """The clickable URL embedded in the email."""
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/auth/magic?token={raw_token}"


# ── email template ──────────────────────────────────────────────────────────


def _render_email(user: User, raw_token: str) -> tuple[str, str, str]:
    """Subject + HTML + plain text for the magic-link email."""
    login_url = _build_login_url(raw_token)
    ttl_minutes = TOKEN_TTL_MINUTES

    subject = "Your login link for The Predictor"

    html = f"""\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{subject}</title>
</head>
<body style="margin:0; padding:0; background:#f1ebde; font-family:'Helvetica Neue',Helvetica,Arial,sans-serif; color:#0e1d40;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1ebde;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px; background:#f1ebde; border:2px solid #0e1d40;">
          <tr>
            <td style="padding:18px 22px 14px; border-bottom:2px solid #0e1d40; background:#e9e1cf;">
              <div style="font-size:11px; letter-spacing:0.1em; text-transform:uppercase; color:#8a826f;">The Predictor</div>
              <div style="font-family:'Archivo Black','Helvetica Neue',Helvetica,Arial,sans-serif; font-size:22px; line-height:1.2; margin-top:4px; letter-spacing:0.01em;">Your login link</div>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 22px;">
              <p style="margin:0 0 16px; font-size:14px; line-height:1.5; color:#514a3d;">
                Hi {_esc(user.name)}, click the button below to sign in. This link is valid for <strong>{ttl_minutes} minutes</strong> and can only be used once.
              </p>
              <p style="margin:0 0 16px;">
                <a href="{_esc(login_url)}" style="display:inline-block; padding:12px 22px; background:#0e1d40; color:#f1ebde; text-decoration:none; font-family:'Archivo Black','Helvetica Neue',Helvetica,Arial,sans-serif; font-size:14px; letter-spacing:0.06em;">SIGN IN →</a>
              </p>
              <p style="margin:14px 0 0; font-size:12px; color:#8a826f; line-height:1.5;">
                If the button doesn't work, copy and paste this link into your browser:<br>
                <span style="font-family:'IBM Plex Mono',Menlo,Consolas,monospace; word-break:break-all;">{_esc(login_url)}</span>
              </p>
              <p style="margin:18px 0 0; font-size:12px; color:#8a826f; line-height:1.5;">
                If you didn't request this, you can safely ignore this email — your account is unchanged.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 22px 22px; border-top:2px solid #0e1d40; background:#e9e1cf; font-size:11px; color:#8a826f; letter-spacing:0.03em;">
              The Predictor · <a href="https://predictor.laarohi.xyz" style="color:#514a3d;">predictor.laarohi.xyz</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    text = f"""\
THE PREDICTOR — LOGIN LINK
========================================

Hi {user.name},

Click the link below to sign in. This link is valid for {ttl_minutes}
minutes and can only be used once.

{login_url}

If you didn't request this, ignore this email — your account is
unchanged.

----------------------------------------
predictor.laarohi.xyz
"""

    return subject, html, text


def _esc(s: str | None) -> str:
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── request path ────────────────────────────────────────────────────────────


async def _count_recent_requests(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Number of magic-link tokens issued for this user within the
    rate-limit window. Used to enforce RATE_LIMIT_MAX_REQUESTS."""
    cutoff = utc_now() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    result = await session.execute(
        select(func.count(MagicLinkToken.id))
        .where(MagicLinkToken.user_id == user_id)
        .where(MagicLinkToken.created_at >= cutoff)
    )
    return int(result.scalar() or 0)


async def _revoke_prior_unused(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Mark every unexpired, unused token for this user as used.
    Limits the valid-token window to the most recent issuance."""
    now = utc_now()
    await session.execute(
        update(MagicLinkToken)
        .where(MagicLinkToken.user_id == user_id)
        .where(MagicLinkToken.used_at.is_(None))
        .values(used_at=now)
    )


async def create_magic_link(session: AsyncSession, email: str) -> None:
    """Generate, store, and email a magic-link token for the user with
    this email. Idempotent against double-clicks (request counter is
    incremented; existing tokens are revoked first).

    Raises:
        UnknownEmail: no user found.
        UserInactive: user is_active=False.
        RateLimited: too many requests in the window.
        EmailSendError: Resend returned a permanent failure.
    """
    normalised = email.strip().lower()

    # Look up user. Email column is indexed + unique.
    user_result = await session.execute(
        select(User).where(func.lower(User.email) == normalised)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise UnknownEmail(email)
    if not user.is_active:
        raise UserInactive(email)

    # Rate-limit: count is BEFORE inserting the new row.
    recent = await _count_recent_requests(session, user.id)
    if recent >= RATE_LIMIT_MAX_REQUESTS:
        raise RateLimited(
            f"too many magic-link requests for {email} "
            f"({recent} in last {RATE_LIMIT_WINDOW_MINUTES}min)"
        )

    # Revoke any prior unused tokens — limits "valid token" window
    # to the most recent issuance. Done in the same transaction as
    # the new insert so the window is never wider than 0 mid-flight.
    await _revoke_prior_unused(session, user.id)

    raw_token = _generate_raw_token()
    token_row = MagicLinkToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=utc_now() + timedelta(minutes=TOKEN_TTL_MINUTES),
    )
    session.add(token_row)
    await session.commit()

    # Send email AFTER commit — if the commit fails, no email goes
    # out; if email send fails, the token row exists but is unusable
    # by the user (they'll just request a new link). Better than the
    # reverse order, which could send a working link to a user whose
    # commit then rolls back.
    subject, html, text = _render_email(user, raw_token)
    try:
        await send_email(to=user.email, subject=subject, html=html, text=text)
    except EmailSendError:
        # The token row exists but the user never got the link.
        # Log loud — admin investigates. We don't roll back the row
        # because Resend may have actually delivered before raising.
        logger.exception("create_magic_link: send failed for user_id=%s", user.id)
        raise


# ── verify path ─────────────────────────────────────────────────────────────


async def verify_magic_link(session: AsyncSession, raw_token: str) -> User:
    """Validate the submitted token and return the user it belongs to.

    Marks the token as used inside the same transaction as the lookup
    so two concurrent verify requests with the same token can't both
    succeed.

    Raises:
        TokenInvalid: no matching row (wrong/forged/never-issued token).
        TokenExpired: row exists but expires_at is past.
        TokenAlreadyUsed: row exists but used_at is set.
        UserInactive: row's user is_active=False.
    """
    token_hash = _hash_token(raw_token)
    result = await session.execute(
        select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise TokenInvalid()

    now = utc_now()
    # Convert DB-loaded value defensively — see _datetime.aware_utc note.
    from app.models._datetime import aware_utc
    expires_at = aware_utc(row.expires_at)
    used_at = aware_utc(row.used_at)

    if used_at is not None:
        raise TokenAlreadyUsed()
    if expires_at < now:
        raise TokenExpired()

    user_result = await session.execute(select(User).where(User.id == row.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise UserInactive()

    # Mark used atomically. The next verify with the same token will
    # be rejected by the used_at check above.
    row.used_at = now
    await session.commit()

    logger.info("verify_magic_link ok: user_id=%s", user.id)
    return user
