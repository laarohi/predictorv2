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
from unittest.mock import MagicMock, patch

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


@pytest.mark.asyncio
async def test_groups_overview_aggregates_exclude_ghosts(session):
    from app.api.predictions import _build_groups_aggregates

    fx, _alice, _bob, _ghost = await _seed(session, with_ghost_predictions=True)

    agg = await _build_groups_aggregates(session)
    assert agg["total_predictors"] == 2
    # Alice + Bob picked home; the ghost's identical pick must not register.
    assert agg["outcome_counts"][fx.id] == {"1": 2, "X": 0, "2": 0}


@pytest.mark.asyncio
async def test_bonus_overview_hides_ghosts(session):
    from unittest.mock import AsyncMock

    from app.api import predictions as preds_api
    from app.models.bonus import BonusPrediction
    from app.models.prediction import PredictionPhase

    _fx, alice, _bob, ghost = await _seed(session, with_ghost_predictions=True)
    session.add(BonusPrediction(user_id=alice.id, question_id="dark_horse",
                                answer="Morocco", phase=PredictionPhase.PHASE_1))
    session.add(BonusPrediction(user_id=ghost.id, question_id="dark_horse",
                                answer="Japan", phase=PredictionPhase.PHASE_1))
    await session.commit()

    question = MagicMock(id="dark_horse", category="top_flop",
                         label="Dark Horse", input_type="team", points=20)
    preds_api._overview_cache.clear()
    with (
        patch.object(preds_api, "is_phase1_locked", new=AsyncMock(return_value=True)),
        patch.object(preds_api, "get_bonus_questions", return_value=[question]),
    ):
        resp = await preds_api.get_bonus_overview(session, MagicMock())

    answers = {a.answer: a.users for a in resp.questions[0].answers}
    assert answers == {"Morocco": ["Alice"]}  # ghost's Japan pick invisible


@pytest.mark.asyncio
async def test_agreements_exclude_ghosts(session):
    from app.api.predictions import get_agreements

    fx, alice, _bob, _ghost = await _seed(session, with_ghost_predictions=True)

    rows = await get_agreements(session, alice, fixture_ids=[fx.id])
    assert len(rows) == 1
    # The ghost shares Alice's exact 2-1 — it must count neither in
    # agreement nor in the denominator.
    assert rows[0].agrees_exact == 1
    assert rows[0].total == 2


@pytest.mark.asyncio
async def test_competition_info_counts_humans_only(session):
    """/api/competition/info feeds the public rules page ("N players
    signed up" + the rarity-band table's pool size) — ghosts must not
    inflate either count."""
    from app.api.competition import get_competition_info

    await _seed(session, with_ghost_predictions=True)

    info = await get_competition_info(session)
    assert info.total_players == 2
    assert info.paid_players == 0


@pytest.mark.asyncio
async def test_daily_snapshots_skip_ghost_rows(session):
    """take_daily_snapshots writes rows for humans only (ghosts have no
    rank, so a snapshot row would be meaningless and would leak into the
    progression chart). pg_insert is Postgres-only, so capture the rows
    it would insert instead of executing against sqlite."""
    import uuid
    from types import SimpleNamespace
    from unittest.mock import MagicMock as MM

    from app.services import snapshots as snaps

    def entry(name, ghost, pos):
        # take_daily_snapshots only reads attributes — a namespace stands in
        # for LeaderboardEntry without dragging in a full PointBreakdown.
        return SimpleNamespace(
            user_id=uuid.uuid4(), user_name=name, position=pos,
            total_points=10, correct_outcomes=0, exact_scores=0,
            is_ghost=ghost,
        )

    board = MM()
    board.entries = [entry("Luke", False, 1), entry("The Crowd", True, 0),
                     entry("Bob", False, 2)]

    captured = {}

    def fake_pg_insert(model):
        stmt = MM()

        def values(rows):
            captured["rows"] = rows
            return stmt

        stmt.values = values
        stmt.on_conflict_do_nothing = lambda **kw: stmt
        return stmt

    fake_session = MM()

    async def execute(stmt):
        result = MM()
        result.rowcount = len(captured["rows"])
        return result

    async def commit():
        return None

    fake_session.execute = execute
    fake_session.commit = commit

    with (
        patch.object(snaps, "calculate_leaderboard", return_value=board) as calc,
        patch.object(snaps, "pg_insert", new=fake_pg_insert),
    ):
        calc.return_value = board

        async def fake_calc(*a, **kw):
            return board

        calc.side_effect = fake_calc
        inserted = await snaps.take_daily_snapshots(fake_session)

    names = {r["user_id"] for r in captured["rows"]}
    assert inserted == 2
    assert names == {board.entries[0].user_id, board.entries[2].user_id}
