"""Leaderboard API routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.dependencies import DbSession, OptionalUser
from app.schemas.leaderboard import LeaderboardResponse, PointBreakdown
from app.services.leaderboard import calculate_leaderboard, invalidate_cache
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
async def get_leaderboard(
    session: DbSession,
    _user: OptionalUser,
    refresh: bool = Query(False, description="Force cache refresh"),
    phase: str | None = Query(None, description="Filter by phase: 'phase_1', 'phase_2', or null for overall"),
) -> LeaderboardResponse:
    """Get full leaderboard with standings.

    Uses 30-second caching for performance. Pass refresh=true to force recalculation.
    Includes correct outcomes, exact scores, and position movement tracking.

    The `phase` parameter allows filtering:
    - `null` or omitted: Overall leaderboard (sum of all phases)
    - `phase_1`: Phase 1 points only
    - `phase_2`: Phase 2 points only

    Position rankings are recalculated based on the selected phase's points.
    """
    # Validate phase parameter
    if phase is not None and phase not in ("phase_1", "phase_2"):
        phase = None  # Default to overall for invalid values

    return await calculate_leaderboard(session, force_refresh=refresh, phase=phase)


@router.post("/invalidate")
async def invalidate_leaderboard_cache() -> dict[str, str]:
    """Invalidate the leaderboard cache.

    Call this after scores are updated to force recalculation on next request.
    """
    invalidate_cache()
    return {"status": "cache invalidated"}


@router.get("/breakdown/{user_id}")
async def get_user_breakdown(
    user_id: uuid.UUID, session: DbSession, _user: OptionalUser
) -> PointBreakdown:
    """Get detailed point breakdown for a user."""
    return await calculate_user_points(session, user_id)
