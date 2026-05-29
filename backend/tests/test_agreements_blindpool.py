"""Blind-pool enforcement for GET /predictions/agreements.

Regression guard for sec-input:BLI-1: the endpoint returned agreement counts
(relative to the caller's own pick) for ALL predicted fixtures with no lock
check. A caller could sweep their own score and watch agrees_exact move to
reconstruct everyone's picks before a match locked; boundary cases such as
agrees_exact == total leaked outright. Unlocked fixtures must be excluded.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.predictions import get_agreements
from app.models.fixture import MatchStatus
from app.models.prediction import MatchPrediction


def _mp(fixture_id, user_id, home, away) -> MatchPrediction:
    return MatchPrediction(
        user_id=user_id, fixture_id=fixture_id, home_score=home, away_score=away
    )


def _fixture(fid, status=MatchStatus.SCHEDULED) -> MagicMock:
    f = MagicMock()
    f.id = fid
    f.status = status
    return f


def _session(my_preds, fixtures, all_preds) -> AsyncMock:
    session = AsyncMock()
    r1 = MagicMock()
    r1.scalars.return_value.all.return_value = my_preds
    r2 = MagicMock()
    r2.scalars.return_value.all.return_value = fixtures
    r3 = MagicMock()
    r3.scalars.return_value.all.return_value = all_preds
    session.execute.side_effect = [r1, r2, r3]
    return session


@pytest.mark.asyncio
async def test_agreements_excludes_unlocked_fixtures():
    uid, fid = uuid.uuid4(), uuid.uuid4()
    mine = _mp(fid, uid, 2, 1)
    everyone = [mine, _mp(fid, uuid.uuid4(), 2, 1), _mp(fid, uuid.uuid4(), 0, 0)]
    session = _session([mine], [_fixture(fid)], everyone)
    current = MagicMock()
    current.id = uid
    with (
        patch("app.api.predictions.is_phase1_locked", new=AsyncMock(return_value=False)),
        patch(
            "app.api.predictions.get_fixture_lock_view",
            new=AsyncMock(return_value=(False, None)),
        ),
    ):
        result = await get_agreements(session, current, None)
    assert result == []


@pytest.mark.asyncio
async def test_agreements_returned_for_locked_fixture():
    uid, fid = uuid.uuid4(), uuid.uuid4()
    mine = _mp(fid, uid, 2, 1)
    everyone = [mine, _mp(fid, uuid.uuid4(), 2, 1), _mp(fid, uuid.uuid4(), 1, 0)]
    session = _session([mine], [_fixture(fid)], everyone)
    current = MagicMock()
    current.id = uid
    with (
        patch("app.api.predictions.is_phase1_locked", new=AsyncMock(return_value=False)),
        patch(
            "app.api.predictions.get_fixture_lock_view",
            new=AsyncMock(return_value=(True, None)),
        ),
    ):
        result = await get_agreements(session, current, None)
    assert len(result) == 1
    ag = result[0]
    assert ag.total == 3
    assert ag.agrees_exact == 2  # two players also picked 2-1
    assert ag.agrees_outcome == 3  # 2-1, 2-1, 1-0 are all home wins
