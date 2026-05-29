"""Leaderboard service with caching.

Provides cached leaderboard calculations with position tracking.
Supports filtering by phase (overall, phase_1, phase_2).
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models._datetime import utc_now
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.prediction import MatchPrediction
from app.models.score import Score
from app.models.user import User
from app.schemas.leaderboard import LeaderboardEntry, LeaderboardResponse, PointBreakdown
from app.services.scoring import calculate_user_points


PhaseFilter = Literal["overall", "phase_1", "phase_2"] | None


@dataclass
class CachedLeaderboard:
    """Cached leaderboard data with TTL."""

    entries: list[LeaderboardEntry]
    last_calculated: datetime
    total_participants: int
    phase: str | None
    # Previous positions for movement tracking
    previous_positions: dict[uuid.UUID, int] = field(default_factory=dict)


# In-memory cache - keyed by phase.
# NOTE: this cache is per-process. Correct for the current single-worker
# deployment; if uvicorn is ever run with --workers>1 each worker keeps its
# own cache and invalidation signal, so move this to a shared store (Redis /
# a DB last-invalidated timestamp) before scaling out.
_cache: dict[str, CachedLeaderboard] = {}
_cache_ttl = timedelta(seconds=30)  # 30-second cache

# Per-key locks for single-flight rebuilds (see calculate_leaderboard).
_cache_locks: dict[str, asyncio.Lock] = {}


def _lock_for(cache_key: str) -> asyncio.Lock:
    lock = _cache_locks.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _cache_locks[cache_key] = lock
    return lock


def _response_from_cache(cached: CachedLeaderboard) -> LeaderboardResponse:
    return LeaderboardResponse(
        entries=cached.entries,
        last_calculated=cached.last_calculated,
        total_participants=cached.total_participants,
        phase=cached.phase,
    )


def _get_phase_points(breakdown: PointBreakdown, phase: PhaseFilter) -> int:
    """Get points for a specific phase from a breakdown."""
    if phase == "phase_1":
        return breakdown.phase1.total
    elif phase == "phase_2":
        return breakdown.phase2.total
    else:
        return breakdown.total


async def get_user_match_stats(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[int, int]:
    """Get correct outcomes and exact scores count for a user.

    Returns:
        Tuple of (correct_outcomes, exact_scores)
    """
    # Get all match predictions with scores for finished matches
    result = await session.execute(
        select(MatchPrediction, Score)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .outerjoin(Score, Fixture.id == Score.fixture_id)
        .where(
            MatchPrediction.user_id == user_id,
            Fixture.status == MatchStatus.FINISHED,
        )
    )
    rows = result.all()

    correct_outcomes = 0
    exact_scores = 0

    for prediction, score in rows:
        if not score:
            continue

        # Check correct outcome
        if prediction.predicted_outcome == score.outcome:
            correct_outcomes += 1

            # Check exact score
            if (
                prediction.home_score == score.final_home_score
                and prediction.away_score == score.final_away_score
            ):
                exact_scores += 1

    return correct_outcomes, exact_scores


async def calculate_leaderboard(
    session: AsyncSession,
    force_refresh: bool = False,
    phase: PhaseFilter = None,
) -> LeaderboardResponse:
    """Calculate leaderboard with caching.

    Args:
        session: Database session
        force_refresh: If True, bypass cache
        phase: Filter by phase ("phase_1", "phase_2", or None for overall)

    Returns:
        LeaderboardResponse with all entries sorted by the specified phase's points
    """
    global _cache

    cache_key = phase or "overall"

    # Fast path: a fresh cache hit needs no lock.
    if not force_refresh:
        cached = _cache.get(cache_key)
        if cached and (utc_now() - cached.last_calculated) < _cache_ttl:
            return _response_from_cache(cached)

    # Single-flight: serialize rebuilds of a given key so concurrent cache
    # misses (e.g. many users polling right after TTL expiry or a score
    # update) coalesce behind one rebuild instead of each running the full
    # O(users) recompute in parallel.
    async with _lock_for(cache_key):
        # Re-check inside the lock: another coroutine may have just rebuilt.
        if not force_refresh:
            cached = _cache.get(cache_key)
            if cached and (utc_now() - cached.last_calculated) < _cache_ttl:
                return _response_from_cache(cached)

        now = utc_now()

        # Store previous positions for movement tracking
        previous_positions: dict[uuid.UUID, int] = {}
        if cache_key in _cache:
            previous_positions = {e.user_id: e.position for e in _cache[cache_key].entries}

        # Get all active users
        result = await session.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()

        # Precompute tournament-global inputs ONCE and feed them to every
        # calculate_user_points call (see its *_cache args). This collapses a
        # cold rebuild from O(users × fixtures) queries to a small constant.
        # Imported here to mirror scoring.py's lazy standings import.
        from app.services.scoring import get_actual_advancement, get_all_outcome_counts
        from app.services.standings import (
            get_actual_group_standings,
            get_qualifying_third_place_teams,
        )

        outcome_counts_by_fixture = await get_all_outcome_counts(session)
        actual_advancement = await get_actual_advancement(session)
        actual_standings = await get_actual_group_standings(session)
        qualifying_thirds = await get_qualifying_third_place_teams(session)

        entries: list[LeaderboardEntry] = []

        for user in users:
            breakdown = await calculate_user_points(
                session,
                user.id,
                outcome_counts_by_fixture=outcome_counts_by_fixture,
                actual_advancement_cache=actual_advancement,
                actual_standings_cache=actual_standings,
                qualifying_thirds_cache=qualifying_thirds,
            )
            correct_outcomes, exact_scores = await get_user_match_stats(session, user.id)

            # Get points based on phase filter
            phase_points = _get_phase_points(breakdown, phase)

            entries.append(
                LeaderboardEntry(
                    user_id=user.id,
                    user_name=user.name,
                    position=0,  # Will be set after sorting
                    total_points=phase_points,  # Points for the filtered phase
                    breakdown=breakdown,  # Full breakdown (always includes all phases)
                    correct_outcomes=correct_outcomes,
                    exact_scores=exact_scores,
                    movement=0,  # Will be calculated after positioning
                )
            )

        # Sort by phase points (descending), then by exact scores as tiebreaker
        entries.sort(key=lambda e: (e.total_points, e.exact_scores), reverse=True)

        # Assign positions (handle ties)
        current_position = 1
        for i, entry in enumerate(entries):
            if i > 0 and (
                entry.total_points < entries[i - 1].total_points
                or (
                    entry.total_points == entries[i - 1].total_points
                    and entry.exact_scores < entries[i - 1].exact_scores
                )
            ):
                current_position = i + 1
            entry.position = current_position

            # Calculate movement from previous position
            prev_pos = previous_positions.get(entry.user_id)
            if prev_pos is not None:
                entry.movement = prev_pos - entry.position  # Positive = moved up

        # Update cache
        _cache[cache_key] = CachedLeaderboard(
            entries=entries,
            last_calculated=now,
            total_participants=len(users),
            phase=phase,
            previous_positions={e.user_id: e.position for e in entries},
        )

        return _response_from_cache(_cache[cache_key])


def invalidate_cache() -> None:
    """Invalidate the leaderboard cache.

    Call this when scores are updated to force recalculation.
    """
    global _cache
    _cache = {}


def set_cache_ttl(seconds: int) -> None:
    """Set the cache TTL in seconds."""
    global _cache_ttl
    _cache_ttl = timedelta(seconds=seconds)
