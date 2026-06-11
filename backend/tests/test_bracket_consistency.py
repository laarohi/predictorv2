"""Tests for Phase 1 bracket ↔ group-prediction consistency validation.

Why this exists: saving group scores never touches `team_predictions`, so a
user who edits groups after saving a bracket strands stale knockout rows in
the DB (found in the 2026-06-11 pre-lock audit). The frontend now re-saves
the reconciled bracket on every such save; `validate_phase1_bracket` is the
backend guard that refuses payloads a stale or buggy client could still
send. These tests lock both checks:

  1. stage-chain: every pick must descend from the previous stage
  2. R32 roster: every round_of_32 team must qualify under the standings
     implied by the user's SAVED Phase 1 group predictions — skipped
     entirely while those predictions are incomplete

plus the endpoint wiring (422 for Phase 1 violations, Phase 2 exempt).

Group seeding model: groups A–L × teams "<G>1".."<G>4". <G>1 wins all
(9 pts), <G>2 wins twice (6 pts), <G>3 beats <G>4 by (12 - group_index)
goals — third-place goal difference therefore decreases A→L, so the
thirds of groups A–H qualify and I–L miss out. All deterministic, no ties.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from unittest.mock import AsyncMock, patch

from app.api.predictions import update_bracket_predictions
from app.dependencies import RequestContext
from app.models.competition import Competition
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase
from app.models.user import AuthProvider, User
from app.schemas.prediction import BracketPredictionUpdate, TeamAdvancementPrediction
from app.services.bracket_consistency import (
    check_stage_chain,
    get_predicted_qualifiers,
    validate_phase1_bracket,
)

KICKOFF = datetime(2026, 6, 11, 19, 0, tzinfo=timezone.utc)
GROUPS = list("ABCDEFGHIJKL")


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


def _ctx() -> RequestContext:
    return RequestContext(
        request_id=uuid.uuid4(),
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


def _group_results(gi: int) -> list[tuple[str, str, int, int]]:
    """The six matches of group index `gi` as (home, away, hs, as)."""
    g = GROUPS[gi]
    t = [f"{g}{n}" for n in (1, 2, 3, 4)]
    return [
        (t[0], t[1], 3, 0),
        (t[0], t[2], 3, 0),
        (t[0], t[3], 3, 0),
        (t[1], t[2], 2, 0),
        (t[1], t[3], 2, 0),
        (t[2], t[3], 12 - gi, 0),  # third-place GD falls A→L: A–H thirds qualify
    ]


async def _seed_groups(
    session: AsyncSession,
    competition: Competition,
    user: User,
    *,
    predict_all: bool = True,
) -> None:
    """Create all 72 group fixtures, plus the user's score predictions for
    each (omits the last fixture when ``predict_all=False``)."""
    rows: list[tuple[Fixture, int, int]] = []
    for gi in range(len(GROUPS)):
        for home, away, hs, aws in _group_results(gi):
            fixture = Fixture(
                competition_id=competition.id,
                home_team=home,
                away_team=away,
                kickoff=KICKOFF,
                stage="group",
                group=GROUPS[gi],
                status=MatchStatus.SCHEDULED,
            )
            session.add(fixture)
            rows.append((fixture, hs, aws))
    await session.flush()

    to_predict = rows if predict_all else rows[:-1]
    for fixture, hs, aws in to_predict:
        session.add(
            MatchPrediction(
                user_id=user.id,
                fixture_id=fixture.id,
                home_score=hs,
                away_score=aws,
                phase=PredictionPhase.PHASE_1,
            )
        )
    await session.commit()


def _expected_qualifiers() -> set[str]:
    """Top 2 of every group + thirds of groups A–H (see module docstring)."""
    qualifiers = {f"{g}1" for g in GROUPS} | {f"{g}2" for g in GROUPS}
    qualifiers |= {f"{g}3" for g in GROUPS[:8]}
    return qualifiers


def _consistent_payload() -> list[TeamAdvancementPrediction]:
    """A full bracket whose picks chain correctly off the expected roster."""
    r32 = sorted(_expected_qualifiers())
    assert len(r32) == 32
    picks = [TeamAdvancementPrediction(team=t, stage="round_of_32") for t in r32]
    picks += [TeamAdvancementPrediction(team=t, stage="round_of_16") for t in r32[:16]]
    picks += [TeamAdvancementPrediction(team=t, stage="quarter_final") for t in r32[:8]]
    picks += [TeamAdvancementPrediction(team=t, stage="semi_final") for t in r32[:4]]
    picks += [TeamAdvancementPrediction(team=t, stage="final") for t in r32[:2]]
    picks.append(TeamAdvancementPrediction(team=r32[0], stage="winner"))
    return picks


# ---------------------------------------------------------------------------
# check_stage_chain (pure)
# ---------------------------------------------------------------------------


def test_chain_accepts_consistent_payload() -> None:
    assert check_stage_chain(_consistent_payload()) == []


def test_chain_flags_r16_pick_missing_from_r32() -> None:
    payload = [
        TeamAdvancementPrediction(team="France", stage="round_of_32"),
        TeamAdvancementPrediction(team="Germany", stage="round_of_16"),
    ]
    problems = check_stage_chain(payload)
    assert len(problems) == 1
    assert "Germany" in problems[0]
    assert "round_of_16" in problems[0]


def test_chain_flags_winner_not_in_final() -> None:
    payload = _consistent_payload()
    payload[-1] = TeamAdvancementPrediction(team="L4", stage="winner")
    problems = check_stage_chain(payload)
    assert len(problems) == 1
    assert "winner" in problems[0] and "L4" in problems[0]


def test_chain_flags_phase2_shaped_payload() -> None:
    """An R16-first payload violates the chain — which is exactly why the
    endpoint must NOT run this validation for Phase 2 brackets."""
    payload = [TeamAdvancementPrediction(team="France", stage="round_of_16")]
    assert len(check_stage_chain(payload)) == 1


def test_chain_ignores_group_rows() -> None:
    payload = [
        TeamAdvancementPrediction(team="France", stage="group", group_position=1)
    ]
    assert check_stage_chain(payload) == []


def test_chain_accepts_empty_payload() -> None:
    assert check_stage_chain([]) == []


# ---------------------------------------------------------------------------
# get_predicted_qualifiers
# ---------------------------------------------------------------------------


async def test_qualifiers_none_when_no_predictions(session, competition, user) -> None:
    await _seed_groups(session, competition, user, predict_all=True)
    other = User(
        email="other@example.com",
        name="Other",
        password_hash="x",
        auth_provider=AuthProvider.EMAIL,
        competition_id=competition.id,
    )
    session.add(other)
    await session.commit()
    assert await get_predicted_qualifiers(session, other.id) is None


async def test_qualifiers_none_when_predictions_incomplete(
    session, competition, user
) -> None:
    await _seed_groups(session, competition, user, predict_all=False)
    assert await get_predicted_qualifiers(session, user.id) is None


async def test_qualifiers_none_when_no_fixtures(session, competition, user) -> None:
    assert await get_predicted_qualifiers(session, user.id) is None


async def test_qualifiers_derived_from_complete_predictions(
    session, competition, user
) -> None:
    await _seed_groups(session, competition, user)
    qualifiers = await get_predicted_qualifiers(session, user.id)
    assert qualifiers == _expected_qualifiers()
    assert len(qualifiers) == 32


# ---------------------------------------------------------------------------
# validate_phase1_bracket
# ---------------------------------------------------------------------------


async def test_validate_accepts_consistent_bracket(session, competition, user) -> None:
    await _seed_groups(session, competition, user)
    assert await validate_phase1_bracket(session, user.id, _consistent_payload()) == []


async def test_validate_rejects_stale_r32_team(session, competition, user) -> None:
    """The audit scenario: a saved roster team that no longer qualifies."""
    await _seed_groups(session, competition, user)
    payload = _consistent_payload()
    # "I3" is Group I's third — GD too low to make the best-8, never a
    # qualifier here. Replace a roster entry with it (chain stays intact
    # because I3 carries no later-round picks).
    stale = TeamAdvancementPrediction(team="I3", stage="round_of_32")
    payload = [p for p in payload if not (p.stage == "round_of_32" and p.team == "L2")]
    payload.append(stale)
    # L2 had no later-round picks in _consistent_payload (only r32[:16] do
    # and sorted order puts L2 last) — verify that assumption holds.
    assert all(p.team != "L2" or p.stage == "round_of_32" for p in _consistent_payload())

    problems = await validate_phase1_bracket(session, user.id, payload)
    assert len(problems) == 1
    assert "I3" in problems[0]
    assert "round_of_32" in problems[0]


async def test_validate_skips_roster_check_when_groups_incomplete(
    session, competition, user
) -> None:
    await _seed_groups(session, competition, user, predict_all=False)
    payload = _consistent_payload()  # roster can't be checked → accepted
    assert await validate_phase1_bracket(session, user.id, payload) == []


async def test_validate_reports_chain_and_roster_together(
    session, competition, user
) -> None:
    await _seed_groups(session, competition, user)
    payload = [
        TeamAdvancementPrediction(team="I3", stage="round_of_32"),  # not a qualifier
        TeamAdvancementPrediction(team="Z9", stage="round_of_16"),  # not in r32
    ]
    problems = await validate_phase1_bracket(session, user.id, payload)
    assert len(problems) == 2


# ---------------------------------------------------------------------------
# Endpoint wiring (PUT /bracket)
# ---------------------------------------------------------------------------


@patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
@patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
async def test_endpoint_rejects_inconsistent_phase1_bracket(
    mock_phase, mock_locked, session, competition, user
) -> None:
    mock_phase.return_value = PredictionPhase.PHASE_1
    mock_locked.return_value = False
    await _seed_groups(session, competition, user)

    payload = [TeamAdvancementPrediction(team="I3", stage="round_of_32")]
    with pytest.raises(HTTPException) as exc:
        await update_bracket_predictions(
            bracket_data=BracketPredictionUpdate(predictions=payload),
            session=session,
            current_user=user,
            ctx=_ctx(),
        )
    assert exc.value.status_code == 422
    assert "I3" in exc.value.detail


@patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
@patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
async def test_endpoint_accepts_consistent_phase1_bracket(
    mock_phase, mock_locked, session, competition, user
) -> None:
    mock_phase.return_value = PredictionPhase.PHASE_1
    mock_locked.return_value = False
    await _seed_groups(session, competition, user)

    result = await update_bracket_predictions(
        bracket_data=BracketPredictionUpdate(predictions=_consistent_payload()),
        session=session,
        current_user=user,
        ctx=_ctx(),
    )
    assert result == {"status": "ok"}


@patch("app.api.predictions.is_phase2_bracket_locked", new_callable=AsyncMock)
@patch("app.api.predictions.is_phase1_locked", new_callable=AsyncMock)
@patch("app.api.predictions.get_current_phase", new_callable=AsyncMock)
async def test_endpoint_exempts_phase2_brackets(
    mock_phase, mock_p1_locked, mock_p2_locked, session, competition, user
) -> None:
    """Phase 2 payloads legitimately start at R16 — the Phase 1 chain/roster
    validation must not run for them."""
    mock_phase.return_value = PredictionPhase.PHASE_2
    mock_p1_locked.return_value = False
    mock_p2_locked.return_value = False
    await _seed_groups(session, competition, user)

    payload = [TeamAdvancementPrediction(team="A1", stage="round_of_16")]
    result = await update_bracket_predictions(
        bracket_data=BracketPredictionUpdate(predictions=payload),
        session=session,
        current_user=user,
        ctx=_ctx(),
    )
    assert result == {"status": "ok"}
