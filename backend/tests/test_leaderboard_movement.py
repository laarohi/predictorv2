"""Leaderboard movement chip (▲/▼ N) is day-over-day, not since-last-rebuild.

Regression lock for the bug where the rank-movement chip read ±0 even after a
real climb: the old implementation diffed each user's position against the
PREVIOUS CACHE REBUILD, which resets its own baseline every 30s, so between
two rebuilds nobody ever "moved". Movement is now diffed against the user's
latest snapshot from a PRIOR calendar day — the same reference the trajectory
chart's final segment uses — so chip and chart agree.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models._datetime import utc_now
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.leaderboard import calculate_leaderboard, invalidate_cache

KICKOFF = utc_now().replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed(session: AsyncSession) -> tuple[User, User]:
    """One finished 2-0 fixture; Alice hits the exact score (15 pts, rank 1),
    Bob gets the outcome only (5 pts, rank 2)."""
    comp = Competition(
        name="WC2026", entry_fee=Decimal("0"), external_id="WC", is_active=True
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    fx = Fixture(
        competition_id=comp.id,
        home_team="Mexico",
        away_team="South Africa",
        kickoff=KICKOFF,
        stage="group",
        group="A",
        status=MatchStatus.FINISHED,
    )
    session.add(fx)
    session.add(Score(fixture=fx, home_score=2, away_score=0, source=ScoreSource.API))

    alice = User(email="alice@example.com", name="Alice")
    bob = User(email="bob@example.com", name="Bob")
    session.add_all([alice, bob])
    await session.commit()
    for obj in (fx, alice, bob):
        await session.refresh(obj)

    session.add(MatchPrediction(
        user_id=alice.id, fixture_id=fx.id, home_score=2, away_score=0,
        phase=PredictionPhase.PHASE_1,
    ))
    session.add(MatchPrediction(
        user_id=bob.id, fixture_id=fx.id, home_score=1, away_score=0,
        phase=PredictionPhase.PHASE_1,
    ))
    await session.commit()
    return alice, bob


def _movement(board, user_id) -> int:
    return next(e.movement for e in board.entries if e.user_id == user_id)


@pytest.mark.asyncio
async def test_movement_is_diff_vs_prior_day_snapshot(session):
    alice, bob = await _seed(session)
    today = utc_now().date()
    # Yesterday Alice was 2nd and Bob 1st; today (live) Alice is 1st, Bob 2nd.
    session.add(LeaderboardSnapshot(
        user_id=alice.id, position=2, total_points=0,
        captured_date=today - timedelta(days=1),
    ))
    session.add(LeaderboardSnapshot(
        user_id=bob.id, position=1, total_points=0,
        captured_date=today - timedelta(days=1),
    ))
    await session.commit()

    invalidate_cache()
    board = await calculate_leaderboard(session, force_refresh=True)

    # Sanity: Alice leads on points.
    alice_e = next(e for e in board.entries if e.user_id == alice.id)
    bob_e = next(e for e in board.entries if e.user_id == bob.id)
    assert (alice_e.position, bob_e.position) == (1, 2)

    # Movement = prior_day_position - current_position (positive = climbed).
    assert _movement(board, alice.id) == 1   # 2 → 1
    assert _movement(board, bob.id) == -1     # 1 → 2


@pytest.mark.asyncio
async def test_no_prior_snapshot_means_zero_movement(session):
    alice, bob = await _seed(session)

    invalidate_cache()
    board = await calculate_leaderboard(session, force_refresh=True)

    # No snapshot history at all → no baseline → chip stays ±0.
    assert _movement(board, alice.id) == 0
    assert _movement(board, bob.id) == 0


@pytest.mark.asyncio
async def test_todays_snapshot_is_not_a_movement_baseline(session):
    """A snapshot captured TODAY must not seed movement — only a prior day
    counts, otherwise the chip would diff the live rank against itself."""
    alice, bob = await _seed(session)
    today = utc_now().date()
    session.add(LeaderboardSnapshot(
        user_id=alice.id, position=2, total_points=0, captured_date=today,
    ))
    await session.commit()

    invalidate_cache()
    board = await calculate_leaderboard(session, force_refresh=True)

    assert _movement(board, alice.id) == 0
