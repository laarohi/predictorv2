"""Daily leaderboard snapshot service.

Two write paths and two read paths:

WRITE
- take_daily_snapshots(session) — for every user with at least one prediction,
  insert today's snapshot row. Idempotent: a per-user-per-day unique constraint
  means a second call on the same day is a no-op for users who already have
  a row. Called from the score_scheduler tick.

READ
- get_user_trajectory(session, user_id, days) — return the last `days` of
  snapshot points for one user (oldest first). The current live position is
  NOT included; the API endpoint prepends/appends it as needed.
- get_steepest_climbers(session, days, limit) — rank users by their position
  improvement over the trailing N days. Used for the dashboard footer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models._datetime import utc_now
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.services.leaderboard import calculate_leaderboard


logger = logging.getLogger(__name__)


async def take_daily_snapshots(session: AsyncSession) -> int:
    """Snapshot every user's current position + total points for today (UTC).

    Returns the number of rows actually inserted (zero if today's snapshot
    already exists for everyone — i.e. on every tick after the first).

    Uses an idempotent INSERT ... ON CONFLICT DO NOTHING so concurrent
    scheduler invocations can't double-insert. Safe to call every minute.
    """
    leaderboard = await calculate_leaderboard(session, phase=None)
    if not leaderboard.entries:
        return 0

    today = utc_now().date()
    rows = [
        {
            "id": uuid.uuid4(),
            "user_id": entry.user_id,
            "position": entry.position,
            "total_points": entry.total_points,
            "captured_date": today,
            "captured_at": utc_now(),
        }
        for entry in leaderboard.entries
    ]

    stmt = (
        pg_insert(LeaderboardSnapshot)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_snapshot_user_date")
    )
    result = await session.execute(stmt)
    await session.commit()
    inserted = result.rowcount or 0
    if inserted:
        logger.info("leaderboard_snapshots: inserted %d rows for %s", inserted, today)
    return inserted


async def get_user_trajectory(
    session: AsyncSession,
    user_id: uuid.UUID,
    days: int = 7,
) -> list[LeaderboardSnapshot]:
    """Return one user's snapshot history for the last `days` days, oldest first.

    Includes today's snapshot if one exists; doesn't fabricate missing days.
    The API endpoint appends a live "now" point on top of this so the chart's
    final dot is always the current rank.
    """
    floor_date = utc_now().date() - timedelta(days=days - 1)
    result = await session.execute(
        select(LeaderboardSnapshot)
        .where(LeaderboardSnapshot.user_id == user_id)
        .where(LeaderboardSnapshot.captured_date >= floor_date)
        .order_by(LeaderboardSnapshot.captured_date.asc())
    )
    return list(result.scalars().all())


async def get_steepest_climbers(
    session: AsyncSession,
    days: int = 7,
    limit: int = 5,
) -> list[dict]:
    """Return the users whose position improved the most over the last `days`.

    Compared between each user's earliest snapshot in the window and their
    most recent. `places` is positive when the user climbed (a lower number
    = better rank), so a move from 14 → 8 returns places=6.

    Returns a list of dicts: { user_id, user_name, places, current_position,
    previous_position }.
    """
    floor_date = utc_now().date() - timedelta(days=days - 1)
    result = await session.execute(
        select(LeaderboardSnapshot)
        .where(LeaderboardSnapshot.captured_date >= floor_date)
        .order_by(LeaderboardSnapshot.user_id, LeaderboardSnapshot.captured_date.asc())
    )
    snaps = list(result.scalars().all())

    # Group by user → (earliest, latest)
    per_user: dict[uuid.UUID, tuple[LeaderboardSnapshot, LeaderboardSnapshot]] = {}
    for snap in snaps:
        if snap.user_id not in per_user:
            per_user[snap.user_id] = (snap, snap)
        else:
            first, _last = per_user[snap.user_id]
            per_user[snap.user_id] = (first, snap)

    climbers = []
    for user_id, (first, last) in per_user.items():
        places = first.position - last.position  # positive = climbed
        climbers.append(
            {
                "user_id": user_id,
                "places": places,
                "current_position": last.position,
                "previous_position": first.position,
            }
        )

    climbers.sort(key=lambda c: c["places"], reverse=True)
    return climbers[:limit]
