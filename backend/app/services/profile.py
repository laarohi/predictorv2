"""Profile service — shared stats calculation for user profiles."""

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.prediction import MatchPrediction, TeamPrediction
from app.schemas.auth import UserStats
from app.services.leaderboard import calculate_leaderboard
from app.services.scoring import calculate_user_points


async def calculate_user_stats(session: AsyncSession, user_id: uuid.UUID) -> UserStats:
    """Calculate profile statistics for a user.

    This is reused by both /auth/me/stats and /users/{id}/profile.
    """
    breakdown = await calculate_user_points(session, user_id)

    # Get leaderboard position
    leaderboard = await calculate_leaderboard(session)
    position = None
    for entry in leaderboard.entries:
        if entry.user_id == user_id:
            position = entry.position
            break

    # Count raw predictions
    match_count_result = await session.execute(
        select(func.count(MatchPrediction.id)).where(
            MatchPrediction.user_id == user_id
        )
    )
    total_match_predictions = match_count_result.scalar_one()

    team_count_result = await session.execute(
        select(func.count(TeamPrediction.id)).where(
            TeamPrediction.user_id == user_id
        )
    )
    total_team_predictions = team_count_result.scalar_one()

    total_predictions = total_match_predictions + total_team_predictions

    # Accuracy: correct outcomes / scored match predictions
    accuracy_pct = 0.0
    if breakdown.total_predictions > 0:
        accuracy_pct = round(
            (breakdown.correct_outcomes / breakdown.total_predictions) * 100, 1
        )

    return UserStats(
        total_match_predictions=total_match_predictions,
        total_team_predictions=total_team_predictions,
        total_predictions=total_predictions,
        correct_outcomes=breakdown.correct_outcomes,
        exact_scores=breakdown.exact_scores,
        accuracy_pct=accuracy_pct,
        total_points=breakdown.total,
        leaderboard_position=position,
        total_participants=leaderboard.total_participants,
        breakdown=breakdown,
    )
