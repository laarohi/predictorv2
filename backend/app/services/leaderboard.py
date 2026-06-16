"""Leaderboard service with caching.

Provides cached leaderboard calculations with position tracking.
Supports filtering by phase (overall, phase_1, phase_2).
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.models._datetime import utc_now
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.fixture import Fixture, MatchStatus
from app.models.leaderboard_snapshot import LeaderboardSnapshot
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


async def _previous_day_positions(
    session: AsyncSession, today: date
) -> dict[uuid.UUID, int]:
    """Each user's most recent leaderboard position from a PRIOR day.

    Backs the day-over-day movement chip (▲/▼ N). We deliberately diff
    against the latest snapshot with ``captured_date < today`` rather than
    against the previous cache rebuild: rebuilds happen every 30s and reset
    their own baseline, so nobody's rank ever "moves" between two of them and
    the chip read ±0 even after a real climb. Yesterday's snapshot is a
    stable reference, and it's the SAME point the trajectory chart's final
    segment compares the live rank against — so chip and chart agree.

    Loaded with a portable ordered scan (last-write-wins per user) instead of
    Postgres ``DISTINCT ON`` so the query also runs under sqlite in tests.
    The snapshot set is ~users × days — small enough that the full scan beats
    the round-trips of a per-user query.
    """
    result = await session.execute(
        select(LeaderboardSnapshot.user_id, LeaderboardSnapshot.position)
        .where(LeaderboardSnapshot.captured_date < today)
        .order_by(LeaderboardSnapshot.captured_date.asc())
    )
    positions: dict[uuid.UUID, int] = {}
    for user_id, position in result.all():
        positions[user_id] = position  # ascending order → latest prior day wins
    return positions


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


async def get_user_streaks(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[int, int]:
    """Current hot/cold form for a user — the TRAILING run of finished matches.

    Walks the user's finished match predictions ordered by kickoff and measures
    the unbroken run ending at the *most recent* result:

    - **hot**: consecutive correct outcomes (1/X/2) ending at the latest match
    - **cold**: consecutive misses ending at the latest match

    Exactly one is non-zero (the last result was either a hit or a miss); both
    are 0 when the user has no finished predictions. Correctness is outcome-level
    to match ``get_user_match_stats`` — exact-score streaks would read 0–1 and
    never trigger the leaderboard's 🔥/🧊 chip.

    Kept as a separate query (not folded into ``get_user_match_stats``) because
    streaks need kickoff ordering that the count-only stats don't; at ~30 users
    the extra pass is free, and the isolation makes it unit-testable.
    """
    result = await session.execute(
        select(MatchPrediction, Score)
        .join(Fixture, MatchPrediction.fixture_id == Fixture.id)
        .join(Score, Score.fixture_id == Fixture.id)
        .where(
            MatchPrediction.user_id == user_id,
            Fixture.status == MatchStatus.FINISHED,
        )
        # Fixture.id tiebreaker → deterministic order when matches share a kickoff
        # (the group-stage final round is simultaneous); without it the trailing
        # row — and thus hot-vs-cold — could flip between rebuilds.
        .order_by(Fixture.kickoff.asc(), Fixture.id.asc())
    )
    rows = result.all()
    if not rows:
        return 0, 0

    # Walk backwards from the latest result, counting how many consecutive
    # matches share the latest match's hit/miss value.
    latest_pred, latest_score = rows[-1]
    latest_hit = latest_pred.predicted_outcome == latest_score.outcome
    run = 0
    for pred, score in reversed(rows):
        if (pred.predicted_outcome == score.outcome) != latest_hit:
            break
        run += 1
    return (run, 0) if latest_hit else (0, run)


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

        # Day-over-day movement baseline: each user's latest position from a
        # prior calendar day (UTC, matching the snapshot write path). See
        # _previous_day_positions for why this replaced the old "diff vs last
        # cache rebuild" logic, which was ~always a no-op.
        prev_day_positions = await _previous_day_positions(session, now.date())

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
            get_group_completion,
            get_qualifying_third_place_teams,
        )

        outcome_counts_by_fixture = await get_all_outcome_counts(session)
        actual_advancement = await get_actual_advancement(session)
        actual_standings = await get_actual_group_standings(session)
        qualifying_thirds = await get_qualifying_third_place_teams(session)
        group_completion = await get_group_completion(session)

        entries: list[LeaderboardEntry] = []

        for user in users:
            breakdown = await calculate_user_points(
                session,
                user.id,
                outcome_counts_by_fixture=outcome_counts_by_fixture,
                actual_advancement_cache=actual_advancement,
                actual_standings_cache=actual_standings,
                qualifying_thirds_cache=qualifying_thirds,
                group_completion_cache=group_completion,
            )
            correct_outcomes, exact_scores = await get_user_match_stats(session, user.id)
            hot_streak, cold_streak = await get_user_streaks(session, user.id)

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
                    hot_streak=hot_streak,
                    cold_streak=cold_streak,
                    movement=0,  # Will be calculated after positioning
                    is_ghost=user.is_ghost,
                )
            )

        # Sort by phase points (descending), then by exact scores as tiebreaker
        entries.sort(key=lambda e: (e.total_points, e.exact_scores), reverse=True)

        # Assign positions (handle ties). Ghost entries stay interleaved by
        # points for display but never consume a rank: positions are assigned
        # over real users only, so a ghost can't shift anyone down a place.
        ranked = [e for e in entries if not e.is_ghost]
        current_position = 1
        for i, entry in enumerate(ranked):
            if i > 0 and (
                entry.total_points < ranked[i - 1].total_points
                or (
                    entry.total_points == ranked[i - 1].total_points
                    and entry.exact_scores < ranked[i - 1].exact_scores
                )
            ):
                current_position = i + 1
            entry.position = current_position

            # Day-over-day movement vs the latest prior-day snapshot.
            prev_pos = prev_day_positions.get(entry.user_id)
            if prev_pos is not None:
                entry.movement = prev_pos - entry.position  # Positive = moved up

        # Update cache
        _cache[cache_key] = CachedLeaderboard(
            entries=entries,
            last_calculated=now,
            total_participants=len(ranked),
            phase=phase,
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
