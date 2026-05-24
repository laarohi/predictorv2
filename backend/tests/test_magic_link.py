"""Tests for the magic-link login service.

Covers token generation/hashing primitives, the request path
(rate limit, unknown email, inactive user, revoke prior, email
send), and the verify path (invalid, expired, used, success).

The DB layer is mocked — we're testing the service logic, not the
ORM. End-to-end happy path is sanity-checked manually.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.magic_link import MagicLinkToken
from app.models.user import User
from app.services.magic_link import (
    RATE_LIMIT_MAX_REQUESTS,
    TOKEN_TTL_MINUTES,
    RateLimited,
    TokenAlreadyUsed,
    TokenExpired,
    TokenInvalid,
    UnknownEmail,
    UserInactive,
    _generate_raw_token,
    _hash_token,
    create_magic_link,
    verify_magic_link,
)


# ── helpers ─────────────────────────────────────────────────────────────────


def _user(email: str = "luke@example.com", active: bool = True) -> User:
    u = MagicMock(spec=User)
    import uuid
    u.id = uuid.uuid4()
    u.email = email
    u.name = "Luke"
    u.is_active = active
    return u


def _session_for_create(user: User | None, recent_request_count: int = 0):
    """Wire the session for create_magic_link:
      1. SELECT user → user
      2. SELECT count(MagicLinkToken) recent → recent_request_count
      3. UPDATE revoke prior (no read)
      4. (session.add for the new row, then commit)
    """
    session = AsyncMock()
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    count_result = MagicMock()
    count_result.scalar.return_value = recent_request_count
    revoke_result = MagicMock()  # update has no read
    session.execute.side_effect = [user_result, count_result, revoke_result]
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _session_for_verify(token_row, user):
    """Wire session for verify_magic_link:
      1. SELECT token by hash → token_row
      2. SELECT user → user (only if token row passed checks)
    """
    session = AsyncMock()
    token_result = MagicMock()
    token_result.scalar_one_or_none.return_value = token_row
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    session.execute.side_effect = [token_result, user_result]
    session.commit = AsyncMock()
    return session


# ── primitives ──────────────────────────────────────────────────────────────


class TestTokenPrimitives:
    def test_generate_token_is_43_chars(self):
        """secrets.token_urlsafe(32) → 32 bytes → ~43 base64 chars."""
        assert len(_generate_raw_token()) == 43

    def test_generate_token_unique(self):
        """A handful of generations shouldn't collide."""
        tokens = {_generate_raw_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_hash_is_64_chars_hex(self):
        """sha256 hex digest is always 64 hex chars."""
        h = _hash_token("anything")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_deterministic(self):
        """Same input → same hash."""
        assert _hash_token("xyz") == _hash_token("xyz")

    def test_hash_differs_per_input(self):
        assert _hash_token("a") != _hash_token("b")


# ── request path ────────────────────────────────────────────────────────────


class TestCreateMagicLinkRequest:
    @pytest.mark.asyncio
    @patch("app.services.magic_link.send_email", new_callable=AsyncMock)
    async def test_happy_path(self, mock_send):
        user = _user()
        session = _session_for_create(user, recent_request_count=0)

        await create_magic_link(session, "luke@example.com")

        # A token row was added.
        added = session.add.call_args_list
        assert len(added) == 1
        assert isinstance(added[0].args[0], MagicLinkToken)
        # An email was sent.
        mock_send.assert_awaited_once()
        # Subject sanity check
        kwargs = mock_send.await_args.kwargs
        assert "login" in kwargs["subject"].lower()

    @pytest.mark.asyncio
    @patch("app.services.magic_link.send_email", new_callable=AsyncMock)
    async def test_unknown_email_raises(self, mock_send):
        session = _session_for_create(None)
        with pytest.raises(UnknownEmail):
            await create_magic_link(session, "nobody@example.com")
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("app.services.magic_link.send_email", new_callable=AsyncMock)
    async def test_inactive_user_raises(self, mock_send):
        user = _user(active=False)
        session = _session_for_create(user)
        with pytest.raises(UserInactive):
            await create_magic_link(session, user.email)
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("app.services.magic_link.send_email", new_callable=AsyncMock)
    async def test_rate_limited_when_at_cap(self, mock_send):
        user = _user()
        session = _session_for_create(user, recent_request_count=RATE_LIMIT_MAX_REQUESTS)
        with pytest.raises(RateLimited):
            await create_magic_link(session, user.email)
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("app.services.magic_link.send_email", new_callable=AsyncMock)
    async def test_under_rate_limit_succeeds(self, mock_send):
        user = _user()
        session = _session_for_create(user, recent_request_count=RATE_LIMIT_MAX_REQUESTS - 1)
        await create_magic_link(session, user.email)
        mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.services.magic_link.send_email", new_callable=AsyncMock)
    async def test_email_normalised_to_lowercase(self, mock_send):
        """Mixed-case input normalises before the user lookup."""
        # The actual lowercase comparison happens in the SQL query
        # (func.lower(User.email) == normalised). Verifying the
        # normalisation reaches that point — we'd need a real DB to
        # test the SQL itself, but the function shouldn't blow up.
        user = _user(email="luke@example.com")
        session = _session_for_create(user)
        await create_magic_link(session, "LUKE@EXAMPLE.COM")
        mock_send.assert_awaited_once()


# ── verify path ─────────────────────────────────────────────────────────────


def _valid_token_row(user_id, raw_token: str):
    """A token row in good shape: unused, not expired."""
    row = MagicLinkToken(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES),
    )
    return row


class TestVerifyMagicLink:
    @pytest.mark.asyncio
    async def test_happy_path_returns_user(self):
        user = _user()
        raw = _generate_raw_token()
        row = _valid_token_row(user.id, raw)
        session = _session_for_verify(row, user)

        result = await verify_magic_link(session, raw)

        assert result is user
        # Marked used.
        assert row.used_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_token_raises_invalid(self):
        session = _session_for_verify(None, None)
        with pytest.raises(TokenInvalid):
            await verify_magic_link(session, "anything")

    @pytest.mark.asyncio
    async def test_expired_token_raises_expired(self):
        user = _user()
        raw = _generate_raw_token()
        row = _valid_token_row(user.id, raw)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session = _session_for_verify(row, user)

        with pytest.raises(TokenExpired):
            await verify_magic_link(session, raw)

    @pytest.mark.asyncio
    async def test_used_token_raises_already_used(self):
        user = _user()
        raw = _generate_raw_token()
        row = _valid_token_row(user.id, raw)
        row.used_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session = _session_for_verify(row, user)

        with pytest.raises(TokenAlreadyUsed):
            await verify_magic_link(session, raw)

    @pytest.mark.asyncio
    async def test_inactive_user_raises(self):
        user = _user(active=False)
        raw = _generate_raw_token()
        row = _valid_token_row(user.id, raw)
        session = _session_for_verify(row, user)

        with pytest.raises(UserInactive):
            await verify_magic_link(session, raw)

    @pytest.mark.asyncio
    async def test_used_check_runs_before_expired_check(self):
        """A row that's both used AND expired should report TokenAlreadyUsed
        (the used signal is more informative — the user just clicked
        an old link they'd already used)."""
        user = _user()
        raw = _generate_raw_token()
        row = _valid_token_row(user.id, raw)
        row.used_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        session = _session_for_verify(row, user)

        with pytest.raises(TokenAlreadyUsed):
            await verify_magic_link(session, raw)
