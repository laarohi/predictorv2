"""Blind-pool enforcement for bracket picks in GET /users/{id}/predictions.

Regression guard for sec-authz:AUTH-1 / sec-logic:BLI-2: the match-score
path was gated by the blind pool but the bracket_summary returned ALL of the
target user's TeamPredictions unconditionally, leaking every opponent's
group winners / knockout advancement / champion pick before Phase 1 locked.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.users import get_user_predictions
from app.models.prediction import PredictionPhase, TeamPrediction


def _user_obj(uid: uuid.UUID, name: str = "Player") -> MagicMock:
    u = MagicMock()
    u.id = uid
    u.name = name
    return u


def _session(user, team_preds) -> AsyncMock:
    """session.execute returns: user lookup, (empty) match rows, team preds."""
    session = AsyncMock()
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    match_result = MagicMock()
    match_result.all.return_value = []
    team_result = MagicMock()
    team_result.scalars.return_value.all.return_value = team_preds
    session.execute.side_effect = [user_result, match_result, team_result]
    return session


def _preds(owner_id):
    return [
        TeamPrediction(
            user_id=owner_id, team="Brazil", stage="winner", phase=PredictionPhase.PHASE_1
        ),
        TeamPrediction(
            user_id=owner_id, team="France", stage="final", phase=PredictionPhase.PHASE_2
        ),
    ]


@pytest.mark.asyncio
async def test_bracket_hidden_from_other_users_before_lock():
    owner_id = uuid.uuid4()
    owner = _user_obj(owner_id, "Owner")
    session = _session(owner, _preds(owner_id))
    viewer = _user_obj(uuid.uuid4(), "Nosy")  # different user
    with (
        patch("app.api.users.is_phase1_locked", new=AsyncMock(return_value=False)),
        patch("app.api.users.is_phase2_bracket_locked", new=AsyncMock(return_value=False)),
    ):
        resp = await get_user_predictions(owner_id, session, viewer)
    assert resp.bracket_summary.stages == {}
    assert resp.bracket_summary.phase1_stages == {}
    assert resp.bracket_summary.phase2_stages == {}


@pytest.mark.asyncio
async def test_owner_sees_own_bracket_even_before_lock():
    owner_id = uuid.uuid4()
    owner = _user_obj(owner_id, "Owner")
    session = _session(owner, _preds(owner_id))
    with (
        patch("app.api.users.is_phase1_locked", new=AsyncMock(return_value=False)),
        patch("app.api.users.is_phase2_bracket_locked", new=AsyncMock(return_value=False)),
    ):
        resp = await get_user_predictions(owner_id, session, owner)  # viewer == owner
    assert resp.bracket_summary.phase1_stages == {"winner": ["Brazil"]}
    assert resp.bracket_summary.phase2_stages == {"final": ["France"]}


@pytest.mark.asyncio
async def test_phase1_bracket_revealed_only_after_phase1_lock():
    owner_id = uuid.uuid4()
    owner = _user_obj(owner_id, "Owner")
    session = _session(owner, _preds(owner_id))
    viewer = _user_obj(uuid.uuid4(), "Nosy")
    with (
        patch("app.api.users.is_phase1_locked", new=AsyncMock(return_value=True)),
        patch("app.api.users.is_phase2_bracket_locked", new=AsyncMock(return_value=False)),
    ):
        resp = await get_user_predictions(owner_id, session, viewer)
    assert resp.bracket_summary.phase1_stages == {"winner": ["Brazil"]}
    # Phase 2 bracket still hidden — its deadline hasn't passed.
    assert resp.bracket_summary.phase2_stages == {}
