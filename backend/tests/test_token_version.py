"""JWT token_version revocation (sec-auth:AUTH-8).

A token carries the user's token_version as the `tv` claim; get_current_user
rejects a token whose `tv` doesn't match the user's current token_version, so
bumping it (sign-out-everywhere) invalidates outstanding tokens.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.dependencies import create_access_token, get_current_user


def _session_for(user) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session.execute = AsyncMock(return_value=result)
    return session


def _user(uid, token_version=0):
    u = MagicMock()
    u.id = uid
    u.token_version = token_version
    u.is_active = True
    return u


@pytest.mark.asyncio
async def test_matching_token_version_is_accepted():
    uid = uuid.uuid4()
    token = create_access_token(user_id=str(uid), token_version=0)
    user = _user(uid, token_version=0)
    returned = await get_current_user(_session_for(user), token)
    assert returned is user


@pytest.mark.asyncio
async def test_stale_token_version_is_rejected():
    uid = uuid.uuid4()
    token = create_access_token(user_id=str(uid), token_version=0)
    # User bumped their token_version after this token was issued.
    user = _user(uid, token_version=1)
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_session_for(user), token)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_legacy_token_without_tv_claim_defaults_to_zero():
    # A pre-AUTH-8 token (no tv claim) is treated as tv=0 and still works for a
    # user at the default token_version 0.
    uid = uuid.uuid4()
    token = create_access_token(user_id=str(uid))  # defaults token_version=0
    user = _user(uid, token_version=0)
    returned = await get_current_user(_session_for(user), token)
    assert returned is user
