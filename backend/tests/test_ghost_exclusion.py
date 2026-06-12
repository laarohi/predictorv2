"""Ghost entrants (users.is_ghost) must never affect the real competition.

Ghosts are synthetic users (wisdom-of-the-crowd consensus, Polymarket bot)
whose predictions live in the ordinary tables and are scored normally, but
who are excluded from every cross-user aggregate. These tests lock the
data-integrity-critical exclusions:

1. Rarity outcome counts ignore ghost predictions entirely — a ghost can
   never change a real user's hybrid/logarithmic bonus.
2. Adding a ghost (user + predictions) leaves every real user's leaderboard
   total byte-identical, ghosts are interleaved by points but unranked
   (position 0), and total_participants counts humans only.
3. The community predictions endpoint (heatmap / match leaderboard source)
   never returns a ghost pick.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.leaderboard import calculate_leaderboard, invalidate_cache
from app.services.scoring import get_all_outcome_counts, get_outcome_counts

KICKOFF = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed(session: AsyncSession, *, with_ghost_predictions: bool):
    """One finished group fixture (2-1), two humans, one ghost.

    Alice hits the exact score, Bob gets the outcome only. The ghost also
    picks 2-1 — the exact configuration where a counted ghost would halve
    Alice's rarity bonus.
    """
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
    session.add(Score(fixture=fx, home_score=2, away_score=1, source=ScoreSource.API))

    alice = User(email="alice@example.com", name="Alice")
    bob = User(email="bob@example.com", name="Bob")
    ghost = User(
        email="crowd@ghost.invalid",
        name="The Crowd",
        is_ghost=True,
        password_hash=None,
    )
    session.add_all([alice, bob, ghost])
    await session.commit()
    for obj in (fx, alice, bob, ghost):
        await session.refresh(obj)

    session.add(
        MatchPrediction(
            user_id=alice.id, fixture_id=fx.id, home_score=2, away_score=1,
            phase=PredictionPhase.PHASE_1,
        )
    )
    session.add(
        MatchPrediction(
            user_id=bob.id, fixture_id=fx.id, home_score=1, away_score=0,
            phase=PredictionPhase.PHASE_1,
        )
    )
    if with_ghost_predictions:
        session.add(
            MatchPrediction(
                user_id=ghost.id, fixture_id=fx.id, home_score=2, away_score=1,
                phase=PredictionPhase.PHASE_1,
            )
        )
    await session.commit()
    return fx, alice, bob, ghost


@pytest.mark.asyncio
async def test_outcome_counts_exclude_ghost_predictions(session):
    fx, _alice, _bob, _ghost = await _seed(session, with_ghost_predictions=True)

    counts = await get_outcome_counts(session, fx.id)
    # Alice + Bob both picked a home win; the ghost's identical pick is invisible.
    assert counts == {"1": 2, "X": 0, "2": 0}

    all_counts = await get_all_outcome_counts(session)
    assert all_counts[fx.id] == {"1": 2, "X": 0, "2": 0}


@pytest.mark.asyncio
async def test_ghost_never_changes_real_user_points(session):
    """The no-interference invariant: real totals are identical with and
    without the ghost's predictions in the database."""
    fx, alice, bob, ghost = await _seed(session, with_ghost_predictions=False)

    invalidate_cache()
    before = await calculate_leaderboard(session, force_refresh=True)
    points_before = {
        e.user_id: e.total_points for e in before.entries if not e.is_ghost
    }

    session.add(
        MatchPrediction(
            user_id=ghost.id, fixture_id=fx.id, home_score=2, away_score=1,
            phase=PredictionPhase.PHASE_1,
        )
    )
    await session.commit()

    invalidate_cache()
    after = await calculate_leaderboard(session, force_refresh=True)
    points_after = {
        e.user_id: e.total_points for e in after.entries if not e.is_ghost
    }

    assert points_before == points_after


@pytest.mark.asyncio
async def test_ghost_interleaved_but_unranked(session):
    await _seed(session, with_ghost_predictions=True)

    invalidate_cache()
    board = await calculate_leaderboard(session, force_refresh=True)

    ghosts = [e for e in board.entries if e.is_ghost]
    humans = [e for e in board.entries if not e.is_ghost]

    assert len(ghosts) == 1
    ghost_entry = ghosts[0]
    # Unranked: position stays 0, and no human rank is displaced.
    assert ghost_entry.position == 0
    assert [e.position for e in humans] == [1, 2]
    # The ghost picked the exact score, so it interleaves above Bob (outcome
    # only) in the points-sorted entry list.
    order = [e.user_name for e in board.entries]
    assert order.index("The Crowd") < order.index("Bob")
    # Humans only in the participant count.
    assert board.total_participants == 2


@pytest.mark.asyncio
async def test_community_predictions_hide_ghosts(session):
    from app.api.predictions import get_community_predictions

    fx, _alice, _bob, _ghost = await _seed(session, with_ghost_predictions=True)

    with patch(
        "app.api.predictions.get_fixture_lock_view", return_value=(True, None)
    ):
        resp = await get_community_predictions(fx.id, session, None)

    names = {p.user_name for p in resp.predictions}
    assert names == {"Alice", "Bob"}
