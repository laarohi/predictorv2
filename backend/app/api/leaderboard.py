"""Leaderboard API routes."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from app.dependencies import DbSession, OptionalUser
from app.models.user import User
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse, PointBreakdown
from app.services.scoring import calculate_user_points, get_scoring_config, SCORING_STRATEGIES

router = APIRouter()


class ScoringConfigResponse(BaseModel):
    """Response model for scoring configuration."""

    mode: str
    available_modes: list[str]
    match: dict[str, Any]
    advancement: dict[str, Any]
    phase_multipliers: dict[str, float]


@router.get("/scoring-rules", response_model=ScoringConfigResponse)
async def get_scoring_rules() -> ScoringConfigResponse:
    """Get the current scoring configuration.

    Returns the scoring rules in effect, including:
    - Current scoring mode (fixed/hybrid)
    - Available scoring modes
    - Match prediction point values
    - Advancement prediction point values
    - Phase multipliers
    """
    config = get_scoring_config()
    return ScoringConfigResponse(
        mode=config.get("mode", "hybrid"),
        available_modes=list(SCORING_STRATEGIES.keys()),
        match=config.get("match", {}),
        advancement=config.get("advancement", {}),
        phase_multipliers=config.get("phase_multipliers", {}),
    )


@router.get("/", response_model=LeaderboardResponse)
async def get_leaderboard(session: DbSession, _user: OptionalUser) -> LeaderboardResponse:
    """Get full leaderboard with standings."""
    # Get all active users
    result = await session.execute(select(User).where(User.is_active == True))
    users = result.scalars().all()

    entries: list[LeaderboardEntry] = []

    for user in users:
        points = await calculate_user_points(session, user.id)
        entries.append(
            LeaderboardEntry(
                user_id=user.id,
                user_name=user.name,
                position=0,  # Will be set after sorting
                total_points=points.total,
                breakdown=points,
                correct_outcomes=0,  # Would need additional calculation
                exact_scores=0,
                movement=0,
            )
        )

    # Sort by total points (descending)
    entries.sort(key=lambda e: e.total_points, reverse=True)

    # Assign positions (handle ties)
    current_position = 1
    for i, entry in enumerate(entries):
        if i > 0 and entry.total_points < entries[i - 1].total_points:
            current_position = i + 1
        entry.position = current_position

    return LeaderboardResponse(
        entries=entries,
        last_calculated=datetime.utcnow(),
        total_participants=len(users),
    )


@router.get("/breakdown/{user_id}")
async def get_user_breakdown(
    user_id: uuid.UUID, session: DbSession, _user: OptionalUser
) -> PointBreakdown:
    """Get detailed point breakdown for a user."""
    return await calculate_user_points(session, user_id)
