"""Tests for the prediction-overview endpoints (groups + bracket).

Real in-memory SQLite sessions (the endpoints lean on GROUP BY counts and
the predicted-standings derivation, so mocks would test nothing). The
phase-lock gates are patched per test — their own logic is covered in
test_locking.py.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.api.predictions import get_bracket_overview, get_groups_overview
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.user import User

KICKOFF = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)

# Group A teams + round-robin fixtures (6 games, 4 teams).
TEAMS = ["Mexico", "Canada", "Germany", "Japan"]
PAIRS = [
    ("Mexico", "Canada"),
    ("Germany", "Japan"),
    ("Mexico", "Germany"),
    ("Canada", "Japan"),
    ("Mexico", "Japan"),
    ("Canada", "Germany"),
]


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
    """Competition + group A fixtures + two predictors with full score picks."""
    comp = Competition(name="WC2026", entry_fee=Decimal("0"), is_active=True)
    session.add(comp)
    await session.commit()
    await session.refresh(comp)

    fixtures = [
        Fixture(
            competition_id=comp.id,
            home_team=home,
            away_team=away,
            kickoff=KICKOFF,
            stage="group",
            group="A",
            status=MatchStatus.SCHEDULED,
        )
        for home, away in PAIRS
    ]
    alice = User(email="alice@example.com", name="Alice")
    bob = User(email="bob@example.com", name="Bob")
    session.add_all(fixtures + [alice, bob])
    await session.commit()
    for f in fixtures:
        await session.refresh(f)
    await session.refresh(alice)
    await session.refresh(bob)

    # Alice: Mexico wins everything (Mexico 1st), home sides win otherwise.
    # Bob: Canada wins everything (Canada 1st), draws otherwise.
    for f in fixtures:
        if "Mexico" in (f.home_team, f.away_team):
            a_home, a_away = (2, 0) if f.home_team == "Mexico" else (0, 2)
        else:
            a_home, a_away = (1, 0)
        if "Canada" in (f.home_team, f.away_team):
            b_home, b_away = (3, 1) if f.home_team == "Canada" else (1, 3)
        else:
            b_home, b_away = (1, 1)
        session.add_all(
            [
                MatchPrediction(
                    user_id=alice.id, fixture_id=f.id, home_score=a_home, away_score=a_away
                ),
                MatchPrediction(
                    user_id=bob.id, fixture_id=f.id, home_score=b_home, away_score=b_away
                ),
            ]
        )

    # Brackets: both carry Mexico into the R32; only Alice carries Canada.
    session.add_all(
        [
            TeamPrediction(user_id=alice.id, team="Mexico", stage="round_of_32"),
            TeamPrediction(user_id=alice.id, team="Canada", stage="round_of_32"),
            TeamPrediction(user_id=bob.id, team="Mexico", stage="round_of_32"),
            TeamPrediction(user_id=alice.id, team="Mexico", stage="winner"),
            TeamPrediction(user_id=bob.id, team="Germany", stage="winner"),
            # Phase 2 row — must not leak into the Phase 1 overview.
            TeamPrediction(
                user_id=bob.id,
                team="Japan",
                stage="winner",
                phase=PredictionPhase.PHASE_2,
            ),
        ]
    )
    await session.commit()
    return {"fixtures": fixtures, "alice": alice, "bob": bob}


def _viewer() -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    return u


# ---- /overview/groups ------------------------------------------------------


@pytest.mark.asyncio
async def test_groups_overview_403_before_phase1_deadline(session, seeded):
    with patch("app.api.predictions.is_phase1_locked", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as exc:
            await get_groups_overview(session, _viewer())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_groups_overview_counts(session, seeded):
    with patch("app.api.predictions.is_phase1_locked", new=AsyncMock(return_value=True)):
        resp = await get_groups_overview(session, _viewer())

    assert resp.total_predictors == 2
    assert [g.group for g in resp.groups] == ["A"]
    group = resp.groups[0]

    teams = {t.team: t for t in group.teams}
    assert set(teams) == set(TEAMS)
    # Predicted 1st: Alice → Mexico, Bob → Canada.
    assert teams["Mexico"].first_count == 1
    assert teams["Canada"].first_count == 1
    assert teams["Germany"].first_count == 0
    # R32 advance counts (Phase 1 rows only).
    assert teams["Mexico"].advance_count == 2
    assert teams["Canada"].advance_count == 1
    assert teams["Japan"].advance_count == 0
    # Sorted by advance desc, then first desc.
    assert group.teams[0].team == "Mexico"
    assert group.teams[1].team == "Canada"

    # Outcome split for Mexico v Canada: Alice 2-0 (home), Bob 1-3 (away).
    mex_can = next(
        f for f in group.fixtures if (f.home_team, f.away_team) == ("Mexico", "Canada")
    )
    assert (mex_can.home_count, mex_can.draw_count, mex_can.away_count) == (1, 0, 1)
    assert mex_can.actual_home is None and mex_can.actual_away is None

    # Germany v Japan: Alice 1-0 (home), Bob 1-1 (draw).
    ger_jpn = next(
        f for f in group.fixtures if (f.home_team, f.away_team) == ("Germany", "Japan")
    )
    assert (ger_jpn.home_count, ger_jpn.draw_count, ger_jpn.away_count) == (1, 1, 0)


# ---- /overview/bracket -----------------------------------------------------


@pytest.mark.asyncio
async def test_bracket_overview_403s(session, seeded):
    with patch("app.api.predictions.is_phase1_locked", new=AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as exc:
            await get_bracket_overview(session, _viewer(), phase=1)
    assert exc.value.status_code == 403

    with patch(
        "app.api.predictions.is_phase2_bracket_locked", new=AsyncMock(return_value=False)
    ):
        with pytest.raises(HTTPException) as exc:
            await get_bracket_overview(session, _viewer(), phase=2)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_bracket_overview_counts_and_phase_separation(session, seeded):
    with patch("app.api.predictions.is_phase1_locked", new=AsyncMock(return_value=True)):
        resp = await get_bracket_overview(session, _viewer(), phase=1)

    assert resp.phase == 1
    teams = {t.team: t for t in resp.teams}
    # All group-stage teams present even with zero picks.
    assert set(TEAMS) <= set(teams)
    assert teams["Mexico"].round_of_32 == 2
    assert teams["Mexico"].winner == 1
    assert teams["Germany"].winner == 1
    assert teams["Canada"].round_of_32 == 1
    # Bob's PHASE_2 Japan-winner row must not appear in Phase 1.
    assert teams["Japan"].winner == 0
    assert teams["Mexico"].group == "A"
    # Sorted champion-first; Mexico ahead of Germany on the R32 tiebreak
    # (equal winner counts, more Round-of-32 picks).
    assert [t.team for t in resp.teams[:2]] == ["Mexico", "Germany"]


@pytest.mark.asyncio
async def test_bracket_overview_phase2_counts(session, seeded):
    with patch(
        "app.api.predictions.is_phase2_bracket_locked", new=AsyncMock(return_value=True)
    ):
        resp = await get_bracket_overview(session, _viewer(), phase=2)

    assert resp.phase == 2
    teams = {t.team: t for t in resp.teams}
    assert teams["Japan"].winner == 1
    assert teams["Mexico"].winner == 0
    # Only Bob has Phase 2 rows.
    assert resp.total_predictors == 1
