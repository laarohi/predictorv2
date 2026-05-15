"""Leaderboard API routes."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession, OptionalUser
from app.schemas.leaderboard import LeaderboardResponse, PointBreakdown
from app.services.leaderboard import calculate_leaderboard, invalidate_cache
from app.services.scoring import calculate_user_points, get_scoring_config, SCORING_STRATEGIES
from app.services.snapshots import get_steepest_climbers, get_user_trajectory

router = APIRouter()


class RankSnapshotPoint(BaseModel):
    """One day's rank + points for a user."""

    position: int
    total_points: int
    captured_date: date


class RankTrajectoryResponse(BaseModel):
    """A user's rank trajectory over the last N days.

    `points` is oldest → newest. The final entry is the user's CURRENT live
    rank (not the last DB snapshot) — the endpoint appends it so the chart's
    most recent dot is always current, even if today's daily snapshot is
    still pending.
    """

    user_id: uuid.UUID
    points: list[RankSnapshotPoint]
    total_participants: int


class SteepestClimberEntry(BaseModel):
    """One row in the steepest-climbers list."""

    user_id: uuid.UUID
    user_name: str
    places: int
    current_position: int
    previous_position: int


class SteepestClimbersResponse(BaseModel):
    """Top-N users by 7-day rank improvement."""

    days: int
    entries: list[SteepestClimberEntry]


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


async def _build_trajectory(
    session: DbSession,
    user_id: uuid.UUID,
    days: int,
) -> RankTrajectoryResponse:
    """Shared implementation for the two trajectory endpoints. Pulls the
    user's snapshot history then appends the current live rank as the
    last point so the chart's tip is always up to date."""
    snaps = await get_user_trajectory(session, user_id, days=days)
    live = await calculate_leaderboard(session, phase=None)
    live_entry = next((e for e in live.entries if e.user_id == user_id), None)

    points = [
        RankSnapshotPoint(
            position=s.position,
            total_points=s.total_points,
            captured_date=s.captured_date,
        )
        for s in snaps
    ]
    if live_entry is not None:
        live_point = RankSnapshotPoint(
            position=live_entry.position,
            total_points=live_entry.total_points,
            captured_date=date.today(),
        )
        # If the last snapshot is from today, overwrite it with the live
        # value so the chart doesn't show stale data for the current day.
        if points and points[-1].captured_date == live_point.captured_date:
            points[-1] = live_point
        else:
            points.append(live_point)

    return RankTrajectoryResponse(
        user_id=user_id,
        points=points,
        total_participants=live.total_participants,
    )


@router.get("/snapshots/me", response_model=RankTrajectoryResponse)
async def get_my_trajectory(
    session: DbSession,
    user: CurrentUser,
    days: int = Query(7, ge=2, le=90),
) -> RankTrajectoryResponse:
    """Rank trajectory for the current user, last `days` days (default 7).

    Used by the dashboard's rank-trajectory card. Returned points are
    oldest → newest; the final point is always the user's live current
    rank, not the most recent stored snapshot.
    """
    return await _build_trajectory(session, user.id, days)


@router.get("/snapshots/{user_id}", response_model=RankTrajectoryResponse)
async def get_user_trajectory_route(
    user_id: uuid.UUID,
    session: DbSession,
    _user: CurrentUser,
    days: int = Query(7, ge=2, le=90),
) -> RankTrajectoryResponse:
    """Rank trajectory for any user — powers the leaderboard's per-row
    sparkline column and the public profile."""
    return await _build_trajectory(session, user_id, days)


@router.get("/climbers", response_model=SteepestClimbersResponse)
async def get_climbers(
    session: DbSession,
    _user: CurrentUser,
    days: int = Query(7, ge=2, le=90),
    # Cap raised from 20 → 100 so the Dashboard can request the full field
    # (it asks for 32 to cover any plausible competition size). 422'd
    # previously when the dashboard called /climbers?days=7&limit=32.
    limit: int = Query(5, ge=1, le=100),
) -> SteepestClimbersResponse:
    """Top-N users by rank improvement over the last `days`.

    Used by the dashboard's "Steepest climb · group of 32" footer. Returns
    `places` positive when the user climbed (e.g. 14 → 8 yields places=6).
    """
    raw = await get_steepest_climbers(session, days=days, limit=limit)

    # Fetch user names in one shot
    from sqlmodel import select  # local import to avoid widening top-level deps
    from app.models.user import User

    user_ids = [c["user_id"] for c in raw]
    name_lookup: dict[uuid.UUID, str] = {}
    if user_ids:
        result = await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        for uid, name in result.all():
            name_lookup[uid] = name

    entries = [
        SteepestClimberEntry(
            user_id=c["user_id"],
            user_name=name_lookup.get(c["user_id"], "Unknown"),
            places=c["places"],
            current_position=c["current_position"],
            previous_position=c["previous_position"],
        )
        for c in raw
    ]
    return SteepestClimbersResponse(days=days, entries=entries)
