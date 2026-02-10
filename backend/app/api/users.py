"""Users API routes — public profiles and prediction viewing."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.dependencies import DbSession, OptionalUser
from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction, PredictionPhase, TeamPrediction
from app.models.score import Score
from app.models.user import User
from app.schemas.auth import UserStats
from app.services.profile import calculate_user_stats

router = APIRouter()

LOCK_MINUTES = 5


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
    """Summary of bracket predictions grouped by stage."""

    stages: dict[str, list[str]]  # stage -> [team names]


class UserPredictionsResponse(BaseModel):
    """All visible predictions for a user."""

    user_id: uuid.UUID
    user_name: str
    match_predictions: list[UserMatchPredictionView]
    bracket_summary: BracketSummary


# Endpoints


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

    match_predictions: list[UserMatchPredictionView] = []
    for pred, fixture in rows:
        # Blind pool: skip if not locked and not finished
        if not fixture.is_locked(LOCK_MINUTES) and fixture.status != MatchStatus.FINISHED:
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

    # Bracket summary: group team predictions by stage
    result = await session.execute(
        select(TeamPrediction).where(TeamPrediction.user_id == user_id)
    )
    team_preds = result.scalars().all()

    stages: dict[str, list[str]] = {}
    for tp in team_preds:
        if tp.stage not in stages:
            stages[tp.stage] = []
        stages[tp.stage].append(tp.team)

    return UserPredictionsResponse(
        user_id=user.id,
        user_name=user.name,
        match_predictions=match_predictions,
        bracket_summary=BracketSummary(stages=stages),
    )
