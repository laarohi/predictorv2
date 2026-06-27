"""Tests for two scoring-engine changes (each required by the repo rule that
no scoring change ships without a pytest case):

CHANGE 1 — Knockout match SCORES are graded on the 90-minute (regulation)
result. A KO score prediction earns correct-outcome (1/X/2, draws allowed)
+ exact-score bonus + rarity exactly like a group match. "Who advanced" is
scored separately by the advancement layer, so there is no double-count here.
`Score.regulation_outcome` is the new regulation-only outcome; `Score.outcome`
(ET → penalties) is left untouched for advancement / resolver / tiebreakers.

CHANGE 2 — Phase 1 → Phase 2 bracket read-time fallback. If a user has ZERO
Phase 2 TeamPrediction rows at scoring time, their Phase 1 bracket carries
forward: those Phase 1 rows are ALSO scored under the Phase 2 advancement
table and added to the phase_2 bucket. A user with any Phase 2 row gets no
fallback.
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
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.models.user import User
from app.services.scoring import calculate_user_points

KICKOFF = datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _comp(session: AsyncSession) -> Competition:
    comp = Competition(
        name="WC2026", entry_fee=Decimal("0"), external_id="WC", is_active=True
    )
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


async def _user(session: AsyncSession, email: str) -> User:
    u = User(email=email, name=email.split("@")[0])
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


# =============================================================================
# CHANGE 1 — Score.regulation_outcome property (pure)
# =============================================================================


class TestRegulationOutcomeProperty:
    """`regulation_outcome` is the 90-minute result only; `outcome` is the
    true ET/penalty winner. The two diverge exactly when a knockout match goes
    beyond 90 minutes."""

    def test_group_match_no_et_regulation_equals_outcome(self):
        """A 90-min-only score: regulation_outcome == outcome (no-op for groups)."""
        s = Score(fixture_id=None, home_score=2, away_score=1)  # type: ignore[arg-type]
        assert s.regulation_outcome == "1"
        assert s.outcome == "1"

    def test_regulation_draw_allowed(self):
        """Equal 90-min scores → 'X' even though knockouts can't end drawn."""
        s = Score(fixture_id=None, home_score=1, away_score=1)  # type: ignore[arg-type]
        assert s.regulation_outcome == "X"

    def test_extra_time_winner_does_not_change_regulation(self):
        """Reg 1-1, ET 2-1: regulation_outcome is the DRAW; outcome is the
        ET (home) win. The match-score grader must see 'X'."""
        s = Score(  # type: ignore[arg-type]
            fixture_id=None,
            home_score=1, away_score=1,
            home_score_et=2, away_score_et=1,
        )
        assert s.regulation_outcome == "X"   # 90-min result
        assert s.outcome == "1"               # full result (ET winner)

    def test_penalties_winner_does_not_change_regulation(self):
        """Reg 0-0, pens 4-3 to away: regulation_outcome 'X', outcome '2'."""
        s = Score(  # type: ignore[arg-type]
            fixture_id=None,
            home_score=0, away_score=0,
            home_score_et=0, away_score_et=0,
            home_penalties=3, away_penalties=4,
        )
        assert s.regulation_outcome == "X"
        assert s.outcome == "2"


# =============================================================================
# CHANGE 1 — knockout match scores graded on regulation (via calculate_user_points)
# =============================================================================


async def _seed_ko_extra_time_fixture(session: AsyncSession, comp: Competition) -> Fixture:
    """A knockout fixture that finished 1-1 after 90 min, 2-1 in extra time."""
    fx = Fixture(
        competition_id=comp.id, home_team="Brazil", away_team="Croatia",
        kickoff=KICKOFF, stage="quarter_final", status=MatchStatus.FINISHED,
    )
    session.add(fx)
    session.add(
        Score(
            fixture=fx,
            home_score=1, away_score=1,         # regulation (90 min)
            home_score_et=2, away_score_et=1,   # extra time
            source=ScoreSource.API,
        )
    )
    await session.commit()
    await session.refresh(fx)
    return fx


@pytest.mark.asyncio
async def test_ko_score_graded_on_regulation_correct_draw_pick(session):
    """Predicting the regulation result (1-1) of an ET knockout earns the
    draw outcome + exact bonus — NOT zero, even though the team that 'won'
    in ET was the home side."""
    comp = await _comp(session)
    fx = await _seed_ko_extra_time_fixture(session, comp)
    user = await _user(session, "draw@example.com")
    # KO predictions live in Phase 2 (knockout 90-min scores).
    session.add(
        MatchPrediction(
            user_id=user.id, fixture_id=fx.id,
            home_score=1, away_score=1, phase=PredictionPhase.PHASE_2,
        )
    )
    await session.commit()

    bd = await calculate_user_points(session, user.id)
    # Sole predictor → f=1/1 ≥ 0.5 → no rarity bonus. Base 5 + exact 10 = 15.
    assert bd.phase2.match_outcome_points == 5
    assert bd.phase2.exact_score_points == 10
    assert bd.phase2.hybrid_bonus_points == 0
    assert bd.correct_outcomes == 1
    assert bd.exact_scores == 1
    assert bd.total == 15


@pytest.mark.asyncio
async def test_ko_score_et_winner_pick_scores_zero(session):
    """Predicting the EXTRA-TIME line (2-1 home win) of a match that was 1-1
    at 90 min scores 0 for the match: the regulation outcome was a draw, so a
    home-win pick misses. (Their advancement call is scored by the bracket.)"""
    comp = await _comp(session)
    fx = await _seed_ko_extra_time_fixture(session, comp)
    user = await _user(session, "etpick@example.com")
    session.add(
        MatchPrediction(
            user_id=user.id, fixture_id=fx.id,
            home_score=2, away_score=1, phase=PredictionPhase.PHASE_2,
        )
    )
    await session.commit()

    bd = await calculate_user_points(session, user.id)
    assert bd.phase2.match_outcome_points == 0
    assert bd.phase2.exact_score_points == 0
    assert bd.correct_outcomes == 0
    assert bd.exact_scores == 0
    assert bd.total == 0


@pytest.mark.asyncio
async def test_ko_rarity_denominator_counts_regulation_outcome(session):
    """Rarity counts predictors who picked the REGULATION outcome, not the ET
    winner. Reg 1-1 (draw). Pool: 4 picked a draw (incl. caller), so f=4/8 →
    at the 0.5 gate → no bonus. Pin the count flows through regulation by
    checking the caller (a draw-picker) gets base only, while the 8th outcome
    bucket (home wins) does NOT count toward the draw caller's correctness."""
    comp = await _comp(session)
    fx = await _seed_ko_extra_time_fixture(session, comp)

    # Pool of 8 (no ghosts): 3 draws + caller's draw = 4 draws, 4 home wins.
    caller = await _user(session, "caller@example.com")
    session.add(
        MatchPrediction(
            user_id=caller.id, fixture_id=fx.id,
            home_score=0, away_score=0, phase=PredictionPhase.PHASE_2,  # a draw
        )
    )
    for i in range(3):
        u = await _user(session, f"draw{i}@example.com")
        session.add(MatchPrediction(
            user_id=u.id, fixture_id=fx.id,
            home_score=2, away_score=2, phase=PredictionPhase.PHASE_2,  # draws
        ))
    for i in range(4):
        u = await _user(session, f"homewin{i}@example.com")
        session.add(MatchPrediction(
            user_id=u.id, fixture_id=fx.id,
            home_score=3, away_score=0, phase=PredictionPhase.PHASE_2,  # home wins
        ))
    await session.commit()

    bd = await calculate_user_points(session, caller.id)
    # Caller picked a 0-0 draw → correct regulation outcome (X), wrong exact.
    # f = 4 draw-predictors / 8 total = 0.5 → gated → no rarity bonus.
    assert bd.phase2.match_outcome_points == 5
    assert bd.phase2.exact_score_points == 0
    assert bd.phase2.hybrid_bonus_points == 0
    assert bd.total == 5


@pytest.mark.asyncio
async def test_group_match_scoring_unchanged_regression(session):
    """Regression: a plain group match (no ET) scores exactly as before —
    home_score == final and regulation_outcome == outcome, so switching the
    grader to regulation is a no-op for groups."""
    comp = await _comp(session)
    fx = Fixture(
        competition_id=comp.id, home_team="France", away_team="Germany",
        kickoff=KICKOFF, stage="group", group="A", status=MatchStatus.FINISHED,
    )
    session.add(fx)
    session.add(Score(fixture=fx, home_score=2, away_score=1, source=ScoreSource.API))
    await session.commit()
    await session.refresh(fx)

    user = await _user(session, "group@example.com")
    session.add(MatchPrediction(
        user_id=user.id, fixture_id=fx.id, home_score=2, away_score=1,
        phase=PredictionPhase.PHASE_1,
    ))
    await session.commit()

    bd = await calculate_user_points(session, user.id)
    # Exact 2-1, sole predictor (f=1 ≥ 0.5 → no rarity). Base 5 + exact 10.
    # Assert the MATCH-score components (what this regression pins); the user
    # also picks up an incidental group-position bonus once the (single-match)
    # group completes — orthogonal to the regulation-grading change.
    assert bd.phase1.match_outcome_points == 5
    assert bd.phase1.exact_score_points == 10
    assert bd.phase1.hybrid_bonus_points == 0
    assert bd.phase1.match_total == 15
    assert bd.correct_outcomes == 1
    assert bd.exact_scores == 1


# =============================================================================
# CHANGE 2 — Phase 1 → Phase 2 bracket read-time fallback
# =============================================================================


async def _make_brazil_winner(session: AsyncSession, comp: Competition) -> None:
    """Drive get_actual_advancement to put Brazil at 'winner' via a finished
    final between Brazil and Argentina (Brazil wins). No group rows, so group
    qualification doesn't muddy the advancement map."""
    fx = Fixture(
        competition_id=comp.id, home_team="Brazil", away_team="Argentina",
        kickoff=KICKOFF, stage="final", status=MatchStatus.FINISHED,
    )
    session.add(fx)
    session.add(Score(fixture=fx, home_score=1, away_score=0, source=ScoreSource.API))
    await session.commit()


@pytest.mark.asyncio
async def test_phase1_bracket_falls_back_to_phase2_when_no_phase2_rows(session):
    """User has a Phase 1 winner pick (Brazil) and NO Phase 2 rows → the
    Phase 1 pick ALSO scores under the Phase 2 table and lands in phase_2.
    Phase 1 still scores normally too (additive, not a move)."""
    comp = await _comp(session)
    await _make_brazil_winner(session, comp)
    user = await _user(session, "fallback@example.com")
    session.add(TeamPrediction(
        user_id=user.id, team="Brazil", stage="winner",
        phase=PredictionPhase.PHASE_1,
    ))
    await session.commit()

    bd = await calculate_user_points(session, user.id)
    # Phase 1 winner = 150 (normal). Fallback adds Phase 2 winner = 100.
    assert bd.phase1.winner_points == 150
    assert bd.phase2.winner_points == 100
    assert bd.total == 250


@pytest.mark.asyncio
async def test_no_fallback_when_user_has_any_phase2_rows(session):
    """User has a Phase 1 bracket AND a (single) Phase 2 row → no fallback.
    Only the actual Phase 2 rows score Phase 2."""
    comp = await _comp(session)
    await _make_brazil_winner(session, comp)
    user = await _user(session, "hasphase2@example.com")
    # Phase 1 says Brazil winner; Phase 2 bracket says Argentina winner (wrong).
    session.add(TeamPrediction(
        user_id=user.id, team="Brazil", stage="winner",
        phase=PredictionPhase.PHASE_1,
    ))
    session.add(TeamPrediction(
        user_id=user.id, team="Argentina", stage="winner",
        phase=PredictionPhase.PHASE_2,
    ))
    await session.commit()

    bd = await calculate_user_points(session, user.id)
    # Phase 1 Brazil-winner scores 150. Phase 2 Argentina-winner is wrong → 0.
    # Crucially the Phase 1 Brazil pick must NOT fall back into Phase 2.
    assert bd.phase1.winner_points == 150
    assert bd.phase2.winner_points == 0
    assert bd.total == 150


@pytest.mark.asyncio
async def test_partial_phase2_bracket_suppresses_fallback(session):
    """Even a single, UNRELATED Phase 2 row counts as 'submitted a Phase 2
    bracket' — the Phase 1 winner pick does not fall back."""
    comp = await _comp(session)
    await _make_brazil_winner(session, comp)
    user = await _user(session, "partial@example.com")
    session.add(TeamPrediction(
        user_id=user.id, team="Brazil", stage="winner",
        phase=PredictionPhase.PHASE_1,
    ))
    # A token Phase 2 row for a DIFFERENT (losing) team/stage — scores 0 itself.
    session.add(TeamPrediction(
        user_id=user.id, team="Croatia", stage="round_of_16",
        phase=PredictionPhase.PHASE_2,
    ))
    await session.commit()

    bd = await calculate_user_points(session, user.id)
    assert bd.phase1.winner_points == 150
    # No fallback: Phase 2 has only the Croatia row, which earns nothing.
    assert bd.phase2.winner_points == 0
    assert bd.phase2.round_of_16_points == 0
    assert bd.total == 150


@pytest.mark.asyncio
async def test_no_bracket_at_all_scores_zero_phase2(session):
    """User with NEITHER Phase 1 nor Phase 2 bracket rows → 0 Phase 2
    advancement (the fallback loop simply has nothing to score)."""
    comp = await _comp(session)
    await _make_brazil_winner(session, comp)
    user = await _user(session, "empty@example.com")
    await session.commit()

    bd = await calculate_user_points(session, user.id)
    assert bd.phase2.winner_points == 0
    assert bd.phase1.winner_points == 0
    assert bd.total == 0
