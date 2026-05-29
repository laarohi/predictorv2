"""Users API routes — public profiles and prediction viewing."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.dependencies import CurrentUser, DbSession, OptionalUser
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import User
from app.schemas.auth import UserStats
from app.services.locking import get_fixture_lock_view, is_phase1_locked
from app.services.profile import calculate_user_stats
from sqlmodel import func

router = APIRouter()


# Response schemas


class PublicProfile(BaseModel):
    """Public-facing user profile."""

    id: uuid.UUID
    name: str
    created_at: datetime
    stats: UserStats


class UserMatchPredictionView(BaseModel):
    """A user's prediction for a single match, with fixture context and result data."""

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    kickoff: datetime
    stage: str
    group: str | None
    status: MatchStatus
    # The user's prediction
    predicted_home: int
    predicted_away: int
    # Actual result (only for finished fixtures with scores)
    actual_home: int | None = None
    actual_away: int | None = None
    actual_outcome: str | None = None
    # Result flags
    is_exact: bool = False
    is_correct_outcome: bool = False


class BracketSummary(BaseModel):
    """Summary of bracket predictions grouped by stage, with phase separation."""

    stages: dict[str, list[str]]  # stage -> [team names] (merged, backward compat)
    phase1_stages: dict[str, list[str]] = {}  # Phase 1 bracket
    phase2_stages: dict[str, list[str]] = {}  # Phase 2 bracket


class UserPredictionsResponse(BaseModel):
    """All visible predictions for a user."""

    user_id: uuid.UUID
    user_name: str
    match_predictions: list[UserMatchPredictionView]
    bracket_summary: BracketSummary


# Endpoints


class RosterEntry(BaseModel):
    """One row of the pre-tournament registered-users roster.

    Paid status is intentionally surfaced — small private competition
    where the admin's paid-toggle decisions are visible to all
    participants. The dashboard roster renders an UNPAID pill next
    to every unpaid player. Email, auth_provider, and other private
    fields are still excluded.
    """

    user_id: uuid.UUID
    name: str
    match_predictions_filled: int
    bracket_picks_filled: int
    is_current_user: bool
    paid: bool


class RosterResponse(BaseModel):
    entries: list[RosterEntry]
    total_active_users: int


@router.get("/roster", response_model=RosterResponse)
async def get_roster(
    session: DbSession,
    current_user: CurrentUser,
) -> RosterResponse:
    """List of active registered users with their prediction progress.

    Drives the DwRoster widget on the Phase 1 dashboard. Returns only
    public-safe fields. Sorted alphabetically by name so the order is
    stable across requests (signup order would leak join time).

    The two count fields are deliberately granular: a player who's
    finished group-stage picks but hasn't touched the bracket shows as
    "48 + 0" rather than a single 48/92 ratio that conflates two
    different completeness signals.
    """
    # Active users only — drops `is_active=False` rows (admin-disabled
    # or otherwise sidelined). Sorted by name for stability.
    users_result = await session.execute(
        select(User).where(User.is_active == True).order_by(User.name)  # noqa: E712
    )
    users = list(users_result.scalars().all())

    # Aggregate prediction counts in single queries — avoids O(N) round-trips
    match_counts_result = await session.execute(
        select(MatchPrediction.user_id, func.count(MatchPrediction.id))
        .group_by(MatchPrediction.user_id)
    )
    match_counts: dict[uuid.UUID, int] = dict(match_counts_result.all())

    # Bracket picks live in TeamPrediction — count only the knockout stages
    # (group_position picks land here too but they're picked alongside
    # group-stage scores, not as bracket bracket picks).
    KO_STAGES = ("round_of_32", "round_of_16", "quarter_final", "semi_final", "final", "winner")
    bracket_counts_result = await session.execute(
        select(TeamPrediction.user_id, func.count(TeamPrediction.id))
        .where(TeamPrediction.stage.in_(KO_STAGES))
        .where(TeamPrediction.phase == PredictionPhase.PHASE_1)
        .group_by(TeamPrediction.user_id)
    )
    bracket_counts: dict[uuid.UUID, int] = dict(bracket_counts_result.all())

    entries = [
        RosterEntry(
            user_id=u.id,
            name=u.name,
            match_predictions_filled=match_counts.get(u.id, 0),
            bracket_picks_filled=bracket_counts.get(u.id, 0),
            is_current_user=(u.id == current_user.id),
            paid=u.paid,
        )
        for u in users
    ]
    return RosterResponse(entries=entries, total_active_users=len(users))


@router.get("/{user_id}/profile", response_model=PublicProfile)
async def get_user_profile(
    user_id: uuid.UUID,
    session: DbSession,
    _user: OptionalUser,
) -> PublicProfile:
    """Get public profile for a user."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    stats = await calculate_user_stats(session, user.id)

    return PublicProfile(
        id=user.id,
        name=user.name,
        created_at=user.created_at,
        stats=stats,
    )


@router.get("/{user_id}/predictions", response_model=UserPredictionsResponse)
async def get_user_predictions(
    user_id: uuid.UUID,
    session: DbSession,
    _user: OptionalUser,
) -> UserPredictionsResponse:
    """Get all visible predictions for a user.

    Blind pool enforced: only includes predictions for fixtures that are
    locked (5 min before kickoff) or finished.
    """
    # Verify user exists
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Get match predictions with fixture and score data
    result = await session.execute(
        select(MatchPrediction, Fixture)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .options(selectinload(Fixture.score))
        .where(MatchPrediction.user_id == user_id)
        .order_by(Fixture.kickoff)
    )
    rows = result.all()
    phase1_locked = await is_phase1_locked(session)

    match_predictions: list[UserMatchPredictionView] = []
    for pred, fixture in rows:
        # Blind pool: skip unless the fixture is locked or finished. For
        # Phase 1 group fixtures, lock means phase1_deadline has passed.
        locked, _ = await get_fixture_lock_view(
            session, fixture, phase1_locked=phase1_locked
        )
        if not locked and fixture.status != MatchStatus.FINISHED:
            continue

        view = UserMatchPredictionView(
            fixture_id=fixture.id,
            home_team=fixture.home_team,
            away_team=fixture.away_team,
            kickoff=fixture.kickoff,
            stage=fixture.stage,
            group=fixture.group,
            status=fixture.status,
            predicted_home=pred.home_score,
            predicted_away=pred.away_score,
        )

        # Add actual result data for finished fixtures
        if fixture.status == MatchStatus.FINISHED and fixture.score:
            score = fixture.score
            view.actual_home = score.home_score
            view.actual_away = score.away_score
            view.actual_outcome = score.outcome

            # Check exact score
            view.is_exact = (
                pred.home_score == score.final_home_score
                and pred.away_score == score.final_away_score
            )

            # Check correct outcome
            pred_outcome = pred.predicted_outcome
            view.is_correct_outcome = pred_outcome == score.outcome

        match_predictions.append(view)

    # Bracket summary: group team predictions by stage and phase
    result = await session.execute(
        select(TeamPrediction).where(TeamPrediction.user_id == user_id)
    )
    team_preds = result.scalars().all()

    stages: dict[str, list[str]] = {}
    phase1_stages: dict[str, list[str]] = {}
    phase2_stages: dict[str, list[str]] = {}
    for tp in team_preds:
        stages.setdefault(tp.stage, []).append(tp.team)
        if tp.phase == PredictionPhase.PHASE_1:
            phase1_stages.setdefault(tp.stage, []).append(tp.team)
        else:
            phase2_stages.setdefault(tp.stage, []).append(tp.team)

    return UserPredictionsResponse(
        user_id=user.id,
        user_name=user.name,
        match_predictions=match_predictions,
        bracket_summary=BracketSummary(
            stages=stages,
            phase1_stages=phase1_stages,
            phase2_stages=phase2_stages,
        ),
    )
