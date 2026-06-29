"""Tests for the knockout match-points ledger.

`get_knockout_match_points_ledger` powers the 'KO matches so far' strip — the
match-score sibling of the bracket-advancement Scoring Journey. It reuses
`calculate_match_points` (already covered by test_scoring.py), so these cases
focus on what the ledger itself adds:

  1. Empty when the user has no KO match prediction
  2. Per-round grouping in tournament order, with group fixtures excluded
  3. Banked points for finished fixtures (exact vs outcome) reconcile with the
     scoring engine
  4. Best-case `available` ceiling (15) for unplayed predicted fixtures

A fixed-mode scoring config keeps the arithmetic deterministic (no rarity).
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services.scoring import get_knockout_match_points_ledger


KICKOFF = datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)

# Fixed mode → exact = correct_outcome(5) + exact_score(10) = 15, outcome = 5,
# miss = 0, no rarity bonus. Best-case available is the module constant (15).
_FIXED_CONFIG = {
    "mode": "fixed",
    "match": {"correct_outcome": 5, "exact_score": 10, "rarity_cap": 10, "hybrid_cap": 10},
    "advancement": {},
}


@pytest.fixture(autouse=True)
def patch_scoring_config():
    with patch("app.services.scoring.get_scoring_config", return_value=_FIXED_CONFIG):
        yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def competition(session: AsyncSession) -> Competition:
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), external_id="WC")
    session.add(comp)
    await session.commit()
    await session.refresh(comp)
    return comp


@pytest_asyncio.fixture
async def user(session: AsyncSession, competition: Competition) -> User:
    u = User(
        email="t@example.com",
        name="Tester",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        competition_id=competition.id,
    )
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def _fixture(
    session: AsyncSession,
    comp_id: UUID,
    *,
    stage: str,
    home: str,
    away: str,
    status: MatchStatus = MatchStatus.SCHEDULED,
    home_score: int | None = None,
    away_score: int | None = None,
    kickoff: datetime = KICKOFF,
) -> Fixture:
    fx = Fixture(
        competition_id=comp_id,
        home_team=home,
        away_team=away,
        kickoff=kickoff,
        stage=stage,
        group=None,
        status=status,
    )
    session.add(fx)
    if home_score is not None and away_score is not None:
        session.add(
            Score(fixture=fx, home_score=home_score, away_score=away_score, source=ScoreSource.API)
        )
    return fx


def _pred(
    session: AsyncSession,
    user_id: UUID,
    fixture: Fixture,
    *,
    home: int,
    away: int,
    phase: PredictionPhase = PredictionPhase.PHASE_2,
) -> MatchPrediction:
    p = MatchPrediction(
        user_id=user_id, fixture_id=fixture.id, home_score=home, away_score=away, phase=phase
    )
    session.add(p)
    return p


async def test_empty_when_no_ko_predictions(session, user) -> None:
    assert await get_knockout_match_points_ledger(session, user.id) == []


async def test_banked_split_and_available_grouped_in_order(session, user, competition) -> None:
    # R32 finished, EXACT prediction → 15 banked
    f1 = _fixture(session, competition.id, stage="round_of_32", home="BRA", away="KOR",
                  status=MatchStatus.FINISHED, home_score=2, away_score=0)
    _pred(session, user.id, f1, home=2, away=0)
    # R32 finished, correct OUTCOME only → 5 banked
    f2 = _fixture(session, competition.id, stage="round_of_32", home="FRA", away="SEN",
                  status=MatchStatus.FINISHED, home_score=1, away_score=0)
    _pred(session, user.id, f2, home=2, away=0)
    # QF scheduled (unplayed) → best-case available 15
    f3 = _fixture(session, competition.id, stage="quarter_final", home="ESP", away="GER")
    _pred(session, user.id, f3, home=1, away=1)
    # Group fixture → must be excluded from the KO ledger
    fg = _fixture(session, competition.id, stage="group", home="USA", away="WAL",
                  status=MatchStatus.FINISHED, home_score=1, away_score=1)
    _pred(session, user.id, fg, home=1, away=1)
    await session.commit()

    ledger = await get_knockout_match_points_ledger(session, user.id)

    # Rounds in tournament order; group excluded.
    assert [r["stage"] for r in ledger] == ["round_of_32", "quarter_final"]

    r32 = ledger[0]
    assert r32["earned_pts"] == 20          # 15 (exact) + 5 (outcome)
    assert r32["available_pts"] == 0
    assert len(r32["fixtures"]) == 2
    assert {f["result"] for f in r32["fixtures"]} == {"exact", "outcome"}
    assert all(f["status"] == "finished" for f in r32["fixtures"])

    qf = ledger[1]
    assert qf["earned_pts"] == 0
    assert qf["available_pts"] == 15        # best-case ceiling, unplayed
    assert qf["fixtures"][0]["points"] is None
    assert qf["fixtures"][0]["actual"] is None
    assert qf["fixtures"][0]["status"] != "finished"


async def test_only_callers_own_predictions_count(session, user, competition) -> None:
    """A second user's prediction on the same fixture must not leak into the
    caller's banked points."""
    other = User(email="o@example.com", name="Other", password_hash="x",
                 auth_provider=AuthProvider.EMAIL, competition_id=competition.id)
    session.add(other)
    await session.commit()
    await session.refresh(other)

    f1 = _fixture(session, competition.id, stage="round_of_32", home="BRA", away="KOR",
                  status=MatchStatus.FINISHED, home_score=2, away_score=0)
    _pred(session, user.id, f1, home=2, away=0)     # caller: exact → 15
    _pred(session, other.id, f1, home=0, away=3)    # other: miss
    await session.commit()

    ledger = await get_knockout_match_points_ledger(session, user.id)
    assert len(ledger) == 1
    assert ledger[0]["earned_pts"] == 15
    assert len(ledger[0]["fixtures"]) == 1
