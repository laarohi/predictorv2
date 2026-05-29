"""Admin bootstrap (ADMIN_EMAILS) and registration toggle (AUTH-2 / AUTH-3)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.auth import register
from app.schemas.auth import UserCreate


def _settings(*, registration_enabled=True, admin_emails=None):
    s = MagicMock()
    s.registration_enabled = registration_enabled
    s.admin_emails = admin_emails or []
    s.jwt_access_token_expire_minutes = 60
    return s


def _session_no_existing_user():
    """Session whose email-lookup returns no user, capturing the added User."""
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_registration_disabled_returns_403():
    with patch("app.api.auth.get_settings", return_value=_settings(registration_enabled=False)):
        with pytest.raises(HTTPException) as exc:
            await register(
                UserCreate(email="x@example.com", name="X", password="password123"),
                session=_session_no_existing_user(),
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_allowlisted_email_registers_as_admin():
    session = _session_no_existing_user()
    settings = _settings(admin_emails=["boss@example.com"])
    with patch("app.api.auth.get_settings", return_value=settings):
        await register(
            UserCreate(email="Boss@example.com", name="Boss", password="password123"),
            session=session,
        )
    created = session.add.call_args.args[0]
    assert created.is_admin is True  # case-insensitive match


@pytest.mark.asyncio
async def test_non_allowlisted_email_registers_as_non_admin():
    session = _session_no_existing_user()
    settings = _settings(admin_emails=["boss@example.com"])
    with patch("app.api.auth.get_settings", return_value=settings):
        await register(
            UserCreate(email="rando@example.com", name="Rando", password="password123"),
            session=session,
        )
    created = session.add.call_args.args[0]
    assert created.is_admin is False
