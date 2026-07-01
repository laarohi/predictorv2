"""Regression test for the leaderboard's per-phase outcome/exact counts.

Two bugs, fixed together: `LeaderboardEntry.correct_outcomes`/`exact_scores`
(1) ignored the requested phase filter entirely — Phase I and Phase II tabs
both showed the user's combined cross-phase counts — and (2) graded knockout
matches on the ET/penalty result instead of the 90-minute regulation result
that the rest of the scoring engine uses (see test_scoring_regulation_and_fallback.py).
Both are exercised here via `calculate_leaderboard`, the actual code path the
standings page hits.
"""

from decimal import Decimal
from datetime import datetime, timezone

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
from app.services.leaderboard import calculate_leaderboard

KICKOFF = datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest.mark.asyncio
async def test_leaderboard_correct_outcomes_and_exact_scores_are_phase_scoped(session):
    """One correct Phase 1 group pick + one correct Phase 2 knockout pick
    (that only reads correct against the REGULATION result, not the ET
    winner). Overall must sum both; each phase tab must show only its own."""
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC", is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    user = User(email="dual@example.com", name="dual")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Phase 1: group match, exact 2-1 pick.
    group_fx = Fixture(
        competition_id=comp.id, home_team="France", away_team="Germany",
        kickoff=KICKOFF, stage="group", group="A", status=MatchStatus.FINISHED,
    )
    session.add(group_fx)
    session.add(Score(fixture=group_fx, home_score=2, away_score=1, source=ScoreSource.API))
    await session.commit()
    await session.refresh(group_fx)
    session.add(MatchPrediction(
        user_id=user.id, fixture_id=group_fx.id, home_score=2, away_score=1,
        phase=PredictionPhase.PHASE_1,
    ))

    # Phase 2: knockout match, 1-1 after 90 min but 2-1 after extra time. The
    # user predicts the regulation draw (1-1) — correct + exact under the
    # 90-minute grading rule, but WRONG under the old ET-based bug (which
    # would compare against the "1" home-win ET outcome).
    ko_fx = Fixture(
        competition_id=comp.id, home_team="Brazil", away_team="Croatia",
        kickoff=KICKOFF, stage="quarter_final", status=MatchStatus.FINISHED,
    )
    session.add(ko_fx)
    session.add(Score(
        fixture=ko_fx, home_score=1, away_score=1,
        home_score_et=2, away_score_et=1, source=ScoreSource.API,
    ))
    await session.commit()
    await session.refresh(ko_fx)
    session.add(MatchPrediction(
        user_id=user.id, fixture_id=ko_fx.id, home_score=1, away_score=1,
        phase=PredictionPhase.PHASE_2,
    ))
    await session.commit()

    overall = await calculate_leaderboard(session, force_refresh=True, phase=None)
    phase1 = await calculate_leaderboard(session, force_refresh=True, phase="phase_1")
    phase2 = await calculate_leaderboard(session, force_refresh=True, phase="phase_2")

    overall_entry = next(e for e in overall.entries if e.user_id == user.id)
    phase1_entry = next(e for e in phase1.entries if e.user_id == user.id)
    phase2_entry = next(e for e in phase2.entries if e.user_id == user.id)

    assert (overall_entry.correct_outcomes, overall_entry.exact_scores) == (2, 2)
    assert (phase1_entry.correct_outcomes, phase1_entry.exact_scores) == (1, 1)
    # This is the regression check: under the old bug this read (0, 0) because
    # it compared the regulation draw pick against the ET "1" winner.
    assert (phase2_entry.correct_outcomes, phase2_entry.exact_scores) == (1, 1)
