"""Parity test for the PERF-1 leaderboard precompute.

calculate_user_points gained optional *_cache args so the leaderboard build can
precompute the per-fixture outcome counts and tournament-global
advancement/standings once instead of per user. This must NOT change results.
These tests seed a full group + two users and assert the cached path produces
exactly the same PointBreakdown as the uncached path.
"""

from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.scoring import (
    calculate_user_points,
    get_actual_advancement,
    get_all_outcome_counts,
)
from app.services.standings import (
    get_actual_group_standings,
    get_qualifying_third_place_teams,
)

KICKOFF = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)

# France 9, Germany 6, Spain 3, Italy 0 — a full round-robin of 4.
RESULTS = [
    ("France", "Germany", 2, 1),
    ("France", "Spain", 3, 0),
    ("France", "Italy", 1, 0),
    ("Germany", "Spain", 2, 1),
    ("Germany", "Italy", 2, 1),
    ("Spain", "Italy", 1, 0),
]


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed(session: AsyncSession):
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    fixtures: list[Fixture] = []
    for home, away, hs, as_ in RESULTS:
        fx = Fixture(
            competition_id=comp.id, home_team=home, away_team=away,
            kickoff=KICKOFF, stage="group", group="A", status=MatchStatus.FINISHED,
        )
        session.add(fx)
        session.add(Score(fixture=fx, home_score=hs, away_score=as_, source=ScoreSource.API))
        fixtures.append(fx)
    await session.commit()
    for fx in fixtures:
        await session.refresh(fx)

    # User A predicts the exact actual scores; user B predicts every match 0-0.
    user_a, user_b = User(email="a@example.com", name="A"), User(email="b@example.com", name="B")
    session.add(user_a)
    session.add(user_b)
    await session.commit()
    await session.refresh(user_a)
    await session.refresh(user_b)

    for fx, (_, _, hs, as_) in zip(fixtures, RESULTS):
        session.add(MatchPrediction(user_id=user_a.id, fixture_id=fx.id, home_score=hs, away_score=as_))
        session.add(MatchPrediction(user_id=user_b.id, fixture_id=fx.id, home_score=0, away_score=0))
    # A couple of bracket picks to exercise the advancement path too.
    session.add(TeamPrediction(user_id=user_a.id, team="France", stage="winner", phase=PredictionPhase.PHASE_1))
    session.add(TeamPrediction(user_id=user_b.id, team="Spain", stage="final", phase=PredictionPhase.PHASE_1))
    await session.commit()
    return user_a, user_b


@pytest.mark.asyncio
async def test_cached_path_matches_uncached(session):
    user_a, user_b = await _seed(session)

    # Precompute the globals exactly as calculate_leaderboard does.
    occ = await get_all_outcome_counts(session)
    adv = await get_actual_advancement(session)
    standings = await get_actual_group_standings(session)
    thirds = await get_qualifying_third_place_teams(session)

    totals = []
    for uid in (user_a.id, user_b.id):
        uncached = await calculate_user_points(session, uid)
        cached = await calculate_user_points(
            session, uid,
            outcome_counts_by_fixture=occ,
            actual_advancement_cache=adv,
            actual_standings_cache=standings,
            qualifying_thirds_cache=thirds,
        )
        assert cached == uncached, f"cached/uncached breakdown diverged for {uid}"
        totals.append(uncached.total)

    # Sanity: the exact-predictor (A) actually scored, so we're comparing real
    # non-trivial breakdowns, not two empty ones.
    assert totals[0] > 0
