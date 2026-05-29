"""Per-account login throttle (sec-infra:SEC-3)."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.auth import login
from app.schemas.auth import UserLogin
from app.services import login_throttle as lt


def test_lockout_after_max_failures():
    lt.reset_throttle()
    email = "a@example.com"
    assert lt.seconds_locked(email) is None
    for _ in range(lt.MAX_FAILURES):
        lt.record_failure(email)
    assert lt.seconds_locked(email) is not None


def test_success_clears_counter():
    lt.reset_throttle()
    email = "b@example.com"
    for _ in range(lt.MAX_FAILURES - 1):
        lt.record_failure(email)
    lt.record_success(email)
    assert lt.seconds_locked(email) is None
    # One failure after a clear is well below the threshold.
    lt.record_failure(email)
    assert lt.seconds_locked(email) is None


def test_throttle_is_case_insensitive():
    lt.reset_throttle()
    for _ in range(lt.MAX_FAILURES):
        lt.record_failure("Mixed@Example.com")
    assert lt.seconds_locked("mixed@example.com") is not None


@pytest.mark.asyncio
async def test_login_returns_429_when_locked():
    lt.reset_throttle()
    email = "c@example.com"
    for _ in range(lt.MAX_FAILURES):
        lt.record_failure(email)
    with pytest.raises(HTTPException) as exc:
        await login(UserLogin(email=email, password="whatever123"), session=AsyncMock())
    assert exc.value.status_code == 429
    lt.reset_throttle()
