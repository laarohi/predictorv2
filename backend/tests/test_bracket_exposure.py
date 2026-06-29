"""Tests for the bracket-exposure service.

Covers the v4 per-stage `earned / available` classification that drives the
DwScoringJourney widget — the rule from CLAUDE.md is that any scoring-engine
change ships with a pytest case, and `_classify_picks_per_stage` is a
scoring-adjacent function (it credits the points the user can still earn).

The cases below stand alone — they do NOT depend on the legacy
`alive_per_stage` count (which is still tested implicitly via the
returned-shape assertions). They focus on:

  1. No picks → both buckets empty
  2. All picks earned (every feeder match finished, every pick won)
  3. All picks available (no feeder match has resolved yet)
  4. Mixed: some earned, some available, some eliminated
  5. TBD-match dedup: picking both teams in one unfinished match
     counts as 1 in `available.n`
  6. Progressive denominators across stages (known + tbd add up)
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import PredictionPhase, TeamPrediction
from app.models.score import Score, ScoreSource
from app.models.user import AuthProvider, User
from app.services.bracket_exposure import (
    STAGE_FED_BY,
    compute_bracket_exposure,
)


KICKOFF = datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)

# A scoring config compatible with backend/config/worldcup2026.yml shape.
# All-fixed values to keep the arithmetic easy to read in tests.
_SCORING_CONFIG = {
    "advancement": {
        "round_of_32": 10,
        "round_of_16": 20,
        "quarter_final": 30,
        "semi_final": 50,
        "final": 75,
        "winner": 100,
        "group_position": 5,
        "phase_2": {
            "round_of_32": 0,
            "round_of_16": 14,
            "quarter_final": 21,
            "semi_final": 35,
            "final": 52,
            "winner": 70,
        },
    },
}


@pytest.fixture(autouse=True)
def patch_scoring_config():
    """Force the service to read our test config instead of YAML."""
    with patch(
        "app.services.bracket_exposure.get_scoring_config",
        return_value=_SCORING_CONFIG,
    ):
        yield


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    """Per-test in-memory SQLite session. Mirrors test_standings.py."""
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


def _add_ko(
    session: AsyncSession,
    competition_id: UUID,
    *,
    stage: str,
    home: str,
    away: str,
    home_score: int | None = None,
    away_score: int | None = None,
    status: MatchStatus = MatchStatus.SCHEDULED,
) -> Fixture:
    """Add one KO fixture. Score row only if a score is supplied."""
    fx = Fixture(
        competition_id=competition_id,
        home_team=home,
        away_team=away,
        kickoff=KICKOFF,
        stage=stage,
        group=None,
        status=status,
    )
    session.add(fx)
    if home_score is not None and away_score is not None:
        session.add(
            Score(
                fixture=fx,
                home_score=home_score,
                away_score=away_score,
                source=ScoreSource.API,
            )
        )
    return fx


def _add_pick(
    session: AsyncSession,
    user_id: UUID,
    *,
    team: str,
    stage: str,
    phase: PredictionPhase = PredictionPhase.PHASE_1,
) -> TeamPrediction:
    """Add one knockout pick — predicts `team` makes `stage`."""
    tp = TeamPrediction(user_id=user_id, team=team, stage=stage, phase=phase)
    session.add(tp)
    return tp


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


async def test_inverse_map_round_trips() -> None:
    """STAGE_FED_BY is the inverse of STAGE_ADVANCES_TO. Documents the
    invariant the new computation relies on."""
    from app.services.bracket_exposure import STAGE_ADVANCES_TO

    for src, dst in STAGE_ADVANCES_TO.items():
        assert STAGE_FED_BY[dst] == src


async def test_empty_exposure_has_all_stages_blank(session, user) -> None:
    """No picks, no fixtures → per_stage has every dest stage but each cell
    is zero. The widget can render the shell without scaffolding."""
    result = await compute_bracket_exposure(session, user.id)

    assert set(result.per_stage.keys()) == {
        "round_of_16", "quarter_final", "semi_final", "final", "winner"
    }
    for row in result.per_stage.values():
        assert row.earned.n == 0
        assert row.earned.of == 0
        assert row.earned.pts == 0
        assert row.earned.teams == []
        assert row.available.n == 0
        assert row.available.of == 0
        assert row.available.pts == 0
        assert row.available.teams == []


# ---------------------------------------------------------------------------
# Single-stage cases — R16 picks against R32 feeder fixtures
# ---------------------------------------------------------------------------


async def test_all_picks_earned_when_feeders_resolved(session, user, competition) -> None:
    """Every R32 feeder is FINISHED, and every team the user picked won.
    All three picks land in the earned bucket; available is empty."""
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX", home_score=2, away_score=0,
            status=MatchStatus.FINISHED)
    _add_ko(session, competition.id, stage="round_of_32",
            home="BRA", away="GER", home_score=3, away_score=1,
            status=MatchStatus.FINISHED)
    _add_ko(session, competition.id, stage="round_of_32",
            home="ESP", away="ITA", home_score=1, away_score=0,
            status=MatchStatus.FINISHED)
    _add_pick(session, user.id, team="ARG", stage="round_of_16")
    _add_pick(session, user.id, team="BRA", stage="round_of_16")
    _add_pick(session, user.id, team="ESP", stage="round_of_16")
    await session.commit()

    result = await compute_bracket_exposure(session, user.id)
    r16 = result.per_stage["round_of_16"]

    assert r16.earned.n == 3
    assert r16.earned.of == 3   # 3 feeder R32 matches resolved
    assert r16.earned.pts == 60  # 3 * 20 (R16 phase-1 stage points)
    assert sorted(r16.earned.teams) == ["ARG", "BRA", "ESP"]
    assert r16.available.n == 0
    assert r16.available.of == 0
    assert r16.available.pts == 0


async def test_all_picks_available_when_feeders_pending(session, user, competition) -> None:
    """No R32 match has finished yet. The user's R16 picks all land in
    `available` with their team listed in the teams array."""
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX")
    _add_ko(session, competition.id, stage="round_of_32",
            home="BRA", away="GER")
    _add_pick(session, user.id, team="ARG", stage="round_of_16")
    _add_pick(session, user.id, team="BRA", stage="round_of_16")
    await session.commit()

    result = await compute_bracket_exposure(session, user.id)
    r16 = result.per_stage["round_of_16"]

    assert r16.earned.n == 0
    assert r16.earned.of == 0
    assert r16.available.n == 2
    assert r16.available.of == 2  # 2 feeder R32 matches still tbd
    assert r16.available.pts == 40
    assert sorted(r16.available.teams) == ["ARG", "BRA"]


# ---------------------------------------------------------------------------
# TBD-match dedup — the headline rule
# ---------------------------------------------------------------------------


async def test_tbd_match_dedup_caps_available_at_one_per_match(
    session, user, competition
) -> None:
    """User picks BOTH teams from the SAME unfinished R32 match to make R16.
    At most one of them can advance, so `available.n` is 1 (not 2). The
    teams list still surfaces both names so the tooltip can show the pair.
    """
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX")
    _add_pick(session, user.id, team="ARG", stage="round_of_16")
    _add_pick(session, user.id, team="MEX", stage="round_of_16")
    await session.commit()

    result = await compute_bracket_exposure(session, user.id)
    r16 = result.per_stage["round_of_16"]

    assert r16.available.n == 1                  # capped, not 2
    assert r16.available.of == 1
    assert r16.available.pts == 20               # 1 * 20
    assert sorted(r16.available.teams) == ["ARG", "MEX"]
    assert r16.earned.n == 0


async def test_eliminated_picks_surface_in_missed(session, user, competition) -> None:
    """Pick lost their feeder match → not earned, not available, but now
    surfaced in the `missed` bucket (carries 0 pts) so the grouped-bars
    widget can render the muted-red tail with the busted team. Previously
    these picks were silently dropped."""
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX", home_score=2, away_score=0,
            status=MatchStatus.FINISHED)
    _add_pick(session, user.id, team="MEX", stage="round_of_16")  # MEX lost
    await session.commit()

    result = await compute_bracket_exposure(session, user.id)
    r16 = result.per_stage["round_of_16"]

    assert r16.earned.n == 0
    assert r16.earned.teams == []
    assert r16.available.n == 0
    assert r16.available.teams == []
    # The eliminated pick now lands in `missed`, with 0 pts.
    assert r16.missed.n == 1
    assert r16.missed.teams == ["MEX"]
    assert r16.missed.pts == 0
    # The feeder match still bumped known_count even though the user's
    # pick lost — denominators describe the world, not the user.
    assert r16.earned.of == 1
    assert r16.missed.of == 1


# ---------------------------------------------------------------------------
# Multi-stage cases — progressive denominators across the bracket
# ---------------------------------------------------------------------------


async def test_mixed_earned_available_eliminated_in_one_stage(
    session, user, competition
) -> None:
    """Three R32 matches: one resolved (pick was winner → earned), one
    resolved (pick lost → eliminated), one still tbd (pick → available).
    Verifies all three buckets coexist on one stage row.
    """
    # Resolved + winner
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX", home_score=2, away_score=0,
            status=MatchStatus.FINISHED)
    # Resolved + loser
    _add_ko(session, competition.id, stage="round_of_32",
            home="BRA", away="GER", home_score=0, away_score=1,
            status=MatchStatus.FINISHED)
    # Unresolved
    _add_ko(session, competition.id, stage="round_of_32",
            home="ESP", away="ITA")
    _add_pick(session, user.id, team="ARG", stage="round_of_16")
    _add_pick(session, user.id, team="BRA", stage="round_of_16")
    _add_pick(session, user.id, team="ESP", stage="round_of_16")
    await session.commit()

    result = await compute_bracket_exposure(session, user.id)
    r16 = result.per_stage["round_of_16"]

    assert r16.earned.n == 1                 # ARG advanced
    assert r16.earned.teams == ["ARG"]
    assert r16.available.n == 1              # ESP is alive
    assert r16.available.teams == ["ESP"]
    # BRA lost → the `missed` bucket (0 pts), no longer dropped
    assert r16.missed.n == 1
    assert r16.missed.teams == ["BRA"]
    assert r16.missed.pts == 0
    assert "BRA" not in r16.earned.teams
    assert "BRA" not in r16.available.teams
    assert r16.earned.of == 2                # 2 R32 matches resolved
    assert r16.available.of == 1             # 1 R32 match tbd
    # Reconciliation: with no same-match double picks, the three buckets
    # account for every pick the user made at the stage.
    assert r16.earned.n + r16.available.n + r16.missed.n == 3


async def test_progressive_denominators_per_stage(session, user, competition) -> None:
    """Different stages have different known/tbd splits. Verifies the
    `of` field correctly tracks resolution per feeder stage."""
    # R32: 2 matches, both resolved
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX", home_score=2, away_score=0,
            status=MatchStatus.FINISHED)
    _add_ko(session, competition.id, stage="round_of_32",
            home="BRA", away="GER", home_score=3, away_score=1,
            status=MatchStatus.FINISHED)
    # R16: 1 match resolved, 1 tbd
    _add_ko(session, competition.id, stage="round_of_16",
            home="ARG", away="BRA", home_score=1, away_score=0,
            status=MatchStatus.FINISHED)
    _add_ko(session, competition.id, stage="round_of_16",
            home="ESP", away="POR")
    await session.commit()

    result = await compute_bracket_exposure(session, user.id)

    # R16 row reflects R32 feeders: 2 resolved, 0 tbd
    assert result.per_stage["round_of_16"].earned.of == 2
    assert result.per_stage["round_of_16"].available.of == 0
    # QF row reflects R16 feeders: 1 resolved, 1 tbd
    assert result.per_stage["quarter_final"].earned.of == 1
    assert result.per_stage["quarter_final"].available.of == 1


# ---------------------------------------------------------------------------
# Phase 2 — different stage points table
# ---------------------------------------------------------------------------


async def test_phase_2_uses_lower_stage_points(session, user, competition) -> None:
    """Phase 2 scoring lives under advancement.phase_2 with reduced values.
    A correct R16 pick earns 14 pts in Phase 2 vs 20 pts in Phase 1."""
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX", home_score=2, away_score=0,
            status=MatchStatus.FINISHED)
    _add_pick(session, user.id, team="ARG", stage="round_of_16",
              phase=PredictionPhase.PHASE_2)
    await session.commit()

    result = await compute_bracket_exposure(
        session, user.id, phase=PredictionPhase.PHASE_2
    )
    r16 = result.per_stage["round_of_16"]
    assert r16.earned.n == 1
    assert r16.earned.pts == 14   # 1 * 14 (phase_2 R16 points), not 20


# ---------------------------------------------------------------------------
# Defensive — backwards compat with alive_per_stage
# ---------------------------------------------------------------------------


async def test_alive_per_stage_still_matches_earned_count(session, user, competition) -> None:
    """The v1 `alive_per_stage[stage]` field should equal the new
    `per_stage[stage].earned.n` so the v3 dashboard keeps working
    side-by-side with the v4 widgets during rollout."""
    _add_ko(session, competition.id, stage="round_of_32",
            home="ARG", away="MEX", home_score=2, away_score=0,
            status=MatchStatus.FINISHED)
    _add_ko(session, competition.id, stage="round_of_32",
            home="BRA", away="GER", home_score=3, away_score=1,
            status=MatchStatus.FINISHED)
    _add_pick(session, user.id, team="ARG", stage="round_of_16")
    _add_pick(session, user.id, team="BRA", stage="round_of_16")
    await session.commit()

    result = await compute_bracket_exposure(session, user.id)

    for stage in ("round_of_16", "quarter_final", "semi_final", "final", "winner"):
        assert result.alive_per_stage[stage] == result.per_stage[stage].earned.n
