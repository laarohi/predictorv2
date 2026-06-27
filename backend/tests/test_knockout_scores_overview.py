"""Tests for the knockout-scores overview endpoint.

The endpoint mirrors /overview/groups but for Phase 2 knockout MATCH-SCORE
picks, with the crucial difference that knockout fixtures lock *per match*
(T-{lock} before each kickoff), not en-masse at a single deadline. So the
aggregate must:

  - INCLUDE a fixture's 1/X/2 split only once that fixture is individually
    locked (past its T-{lock} window) or finished,
  - OMIT a fixture entirely while it is still unlocked (future kickoff) so
    unlocked picks never leak — not even into total_predictors,
  - EXCLUDE ghost users from every count,
  - order rows by round (round_of_32 → final) then kickoff.

Real in-memory SQLite (the endpoint leans on the per-fixture lock view and a
GROUP BY-style aggregation, so mocks would test nothing).
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.api.predictions import get_knockout_scores_overview
from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score
from app.models.user import User


def _viewer():
    class _U:
        id = None

    return _U()


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def seeded(session: AsyncSession):
    """Competition, two knockout fixtures (one locked, one not), three users
    (two real + one ghost) all with score picks on both fixtures.

    - LOCKED R32 fixture: kickoff 1 day in the PAST → locked & visible.
    - UNLOCKED R32 fixture: kickoff far in the FUTURE → not locked → omitted.
    """
    now = utc_now()
    comp = Competition(name="WC2026", is_active=True, is_phase2_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    locked_fx = Fixture(
        competition_id=comp.id,
        home_team="Argentina",
        away_team="Brazil",
        kickoff=now - timedelta(days=1),  # well past its lock window
        stage="round_of_32",
        status=MatchStatus.FINISHED,
    )
    unlocked_fx = Fixture(
        competition_id=comp.id,
        home_team="France",
        away_team="Spain",
        kickoff=now + timedelta(days=2),  # nowhere near its lock window
        stage="round_of_32",
        status=MatchStatus.SCHEDULED,
    )
    # A group fixture must never appear in this knockout-only aggregate.
    group_fx = Fixture(
        competition_id=comp.id,
        home_team="Mexico",
        away_team="Canada",
        kickoff=now - timedelta(days=3),
        stage="group",
        group="A",
        status=MatchStatus.FINISHED,
    )

    alice = User(email="alice@example.com", name="Alice")
    bob = User(email="bob@example.com", name="Bob")
    ghost = User(email="ghost@example.com", name="Ghost", is_ghost=True)
    session.add_all([locked_fx, unlocked_fx, group_fx, alice, bob, ghost])
    await session.commit()
    for obj in (locked_fx, unlocked_fx, group_fx, alice, bob, ghost):
        await session.refresh(obj)

    # Score picks for the LOCKED fixture: Alice 2-1 (home), Bob 0-3 (away),
    # Ghost 1-1 (draw — must be excluded).
    session.add_all(
        [
            MatchPrediction(
                user_id=alice.id, fixture_id=locked_fx.id, home_score=2, away_score=1,
                phase=PredictionPhase.PHASE_2,
            ),
            MatchPrediction(
                user_id=bob.id, fixture_id=locked_fx.id, home_score=0, away_score=3,
                phase=PredictionPhase.PHASE_2,
            ),
            MatchPrediction(
                user_id=ghost.id, fixture_id=locked_fx.id, home_score=1, away_score=1,
                phase=PredictionPhase.PHASE_2,
            ),
            # Picks on the UNLOCKED fixture — these must never surface.
            MatchPrediction(
                user_id=alice.id, fixture_id=unlocked_fx.id, home_score=4, away_score=0,
                phase=PredictionPhase.PHASE_2,
            ),
            MatchPrediction(
                user_id=bob.id, fixture_id=unlocked_fx.id, home_score=0, away_score=2,
                phase=PredictionPhase.PHASE_2,
            ),
        ]
    )
    # Actual result for the finished/locked fixture.
    session.add(Score(fixture_id=locked_fx.id, home_score=2, away_score=1))
    await session.commit()

    return {
        "locked": locked_fx,
        "unlocked": unlocked_fx,
        "group": group_fx,
        "alice": alice,
        "bob": bob,
        "ghost": ghost,
    }


@pytest.mark.asyncio
async def test_includes_only_locked_knockout_fixtures_and_excludes_ghosts(
    session, seeded
):
    resp = await get_knockout_scores_overview(session, _viewer())

    # Exactly one fixture is visible — the past-kickoff (locked) one. The
    # future-kickoff fixture is omitted entirely, and the group fixture is
    # out of scope.
    assert len(resp.fixtures) == 1
    row = resp.fixtures[0]
    assert (row.home_team, row.away_team) == ("Argentina", "Brazil")
    assert str(row.fixture_id) == str(seeded["locked"].id)
    assert row.stage == "round_of_32"

    # 1/X/2 split counts only the two real players (Alice home, Bob away);
    # the ghost's draw pick is excluded.
    assert (row.home_count, row.draw_count, row.away_count) == (1, 0, 1)

    # The unlocked fixture's France/Spain teams must not appear anywhere.
    teams_present = {(f.home_team, f.away_team) for f in resp.fixtures}
    assert ("France", "Spain") not in teams_present

    # total_predictors counts only non-ghost players whose picks are on a
    # VISIBLE fixture — Alice + Bob = 2 (ghost excluded, and the unlocked
    # fixture's picks never feed this count).
    assert resp.total_predictors == 2

    # The finished fixture carries its actual result through.
    assert (row.actual_home, row.actual_away) == (2, 1)
    assert row.status == MatchStatus.FINISHED


@pytest.mark.asyncio
async def test_unlocked_only_returns_empty(session, seeded):
    """If the one locked fixture is pushed into the future, nothing is
    visible — confirming the per-match gate is what reveals rows, and that
    no unlocked pick data (or predictor count) leaks."""
    locked = seeded["locked"]
    locked.kickoff = utc_now() + timedelta(days=5)
    locked.status = MatchStatus.SCHEDULED
    session.add(locked)
    await session.commit()
    session.expire_all()

    resp = await get_knockout_scores_overview(session, _viewer())
    assert resp.fixtures == []
    assert resp.total_predictors == 0


@pytest.mark.asyncio
async def test_rounds_ordered_r32_to_final(session, seeded):
    """A locked semi-final + a locked R32 come back in round order, not
    kickoff order — earlier round first regardless of which kicked off
    first."""
    comp_id = seeded["locked"].competition_id
    now = utc_now()
    # A semi-final that kicked off BEFORE the R32 (chronologically earlier)
    # but belongs to a later round.
    sf = Fixture(
        competition_id=comp_id,
        home_team="Germany",
        away_team="Japan",
        kickoff=now - timedelta(days=2),
        stage="semi_final",
        status=MatchStatus.FINISHED,
    )
    session.add(sf)
    await session.commit()

    resp = await get_knockout_scores_overview(session, _viewer())
    stages = [f.stage for f in resp.fixtures]
    # R32 (the seeded locked fixture) comes before the semi_final even though
    # the SF kicked off earlier.
    assert stages == ["round_of_32", "semi_final"]
