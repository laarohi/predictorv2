"""Tests for the admin Phase 2 prediction-status roster endpoint.

Returns per-player COMPLETION (bracket fill / 31 + KO score fill) — counts
only, never the picks — categorised none/partial/complete and sorted
not-started first so the admin can chase stragglers. Ghosts excluded;
unresolved 'slot:' placeholders excluded from the scores denominator.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.api.admin import _PHASE2_BRACKET_TOTAL, get_phase2_prediction_status
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import User


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


def _admin():
    class _A:
        id = None

    return _A()


async def _user(session, name, ghost=False) -> User:
    u = User(email=f"{name}@x.com", name=name, is_ghost=ghost, is_active=True)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_roster_categorises_sorts_and_excludes(session):
    now = utc_now()
    comp = Competition(
        name="WC", is_active=True, is_phase2_active=True,
        phase2_bracket_deadline=now + timedelta(hours=2),
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    # Two resolved KO fixtures (scores denominator = 2) + one placeholder
    # (excluded — its teams aren't known yet).
    ko1 = Fixture(competition_id=comp.id, home_team="Brazil", away_team="Japan",
                  kickoff=now + timedelta(days=1), stage="round_of_32",
                  status=MatchStatus.SCHEDULED)
    ko2 = Fixture(competition_id=comp.id, home_team="Spain", away_team="Italy",
                  kickoff=now + timedelta(days=1), stage="round_of_32",
                  status=MatchStatus.SCHEDULED)
    placeholder = Fixture(competition_id=comp.id, home_team="slot:x:1:home",
                          away_team="slot:x:1:away", kickoff=now + timedelta(days=1),
                          stage="round_of_16", status=MatchStatus.SCHEDULED)
    session.add_all([ko1, ko2, placeholder])
    await session.commit()
    for f in (ko1, ko2, placeholder):
        await session.refresh(f)

    nobody = await _user(session, "Zoe")  # nothing → none
    partial = await _user(session, "Amy")  # 3 bracket rows + 1 score → partial
    full = await _user(session, "Bob")  # 31 bracket rows → complete
    ghost = await _user(session, "Ghost", ghost=True)  # full bracket, but excluded

    for i in range(3):
        session.add(TeamPrediction(user_id=partial.id, team=f"T{i}",
                    stage="round_of_16", phase=PredictionPhase.PHASE_2))
    session.add(MatchPrediction(user_id=partial.id, fixture_id=ko1.id,
                home_score=1, away_score=0, phase=PredictionPhase.PHASE_2))
    for i in range(_PHASE2_BRACKET_TOTAL):
        session.add(TeamPrediction(user_id=full.id, team=f"F{i}",
                    stage="round_of_16", phase=PredictionPhase.PHASE_2))
    for i in range(_PHASE2_BRACKET_TOTAL):
        session.add(TeamPrediction(user_id=ghost.id, team=f"G{i}",
                    stage="round_of_16", phase=PredictionPhase.PHASE_2))
    await session.commit()

    resp = await get_phase2_prediction_status(session, _admin())

    assert resp.is_phase2_active is True
    assert resp.knockout_fixture_count == 2  # placeholder excluded
    assert resp.bracket_total == _PHASE2_BRACKET_TOTAL
    assert resp.bracket_not_started == 1
    assert resp.bracket_complete == 1

    names = [u.name for u in resp.users]
    assert "Ghost" not in names  # ghost fully excluded
    # not-started sorts first (the chase list)
    assert resp.users[0].name == "Zoe"
    assert resp.users[0].bracket_status == "none"

    by = {u.name: u for u in resp.users}
    assert by["Amy"].bracket_status == "partial"
    assert by["Amy"].bracket_filled == 3
    assert by["Amy"].scores_filled == 1 and by["Amy"].scores_total == 2
    assert by["Bob"].bracket_status == "complete"
    assert by["Bob"].bracket_filled == _PHASE2_BRACKET_TOTAL
    assert by["Zoe"].scores_filled == 0


@pytest.mark.asyncio
async def test_inactive_competition_still_lists_users(session):
    """Endpoint works even before/without Phase 2 activation (is_phase2_active
    flag reflects state; everyone reads as not-started)."""
    comp = Competition(name="WC", is_active=True, is_phase2_active=False)
    session.add(comp)
    await session.commit()
    await _user(session, "Solo")

    resp = await get_phase2_prediction_status(session, _admin())
    assert resp.is_phase2_active is False
    assert resp.bracket_not_started == 1
    assert resp.users[0].bracket_status == "none"
