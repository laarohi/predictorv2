"""Daily leaderboard snapshot — one row per user per day.

Powers the rank trajectory sparkline on the Panini dashboard and the
per-row 7-day trend column on the leaderboard. We take one snapshot per
day per user; the live current position is fetched separately and
prepended client-side so the most recent dot is always up to date.

Snapshots are taken by a background task in score_scheduler.py — idempotent
per (user_id, captured_date), so running the snapshot loop on every tick is
cheap and self-healing if the server was down for a day.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.user import User


class LeaderboardSnapshot(SQLModel, table=True):
    """One user's position + points captured on a given calendar day (UTC)."""

    __tablename__ = "leaderboard_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "captured_date", name="uq_snapshot_user_date"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)

    # Rank as of the snapshot.
    position: int
    # Total points across all phases at the moment of capture.
    total_points: int

    # The wall-clock UTC date this snapshot represents. Used for uniqueness
    # so we never end up with two snapshots for the same user on the same
    # day (the service uses INSERT ... ON CONFLICT semantics).
    captured_date: date = Field(index=True)
    # Exact moment the snapshot row was inserted (for audit/debug).
    captured_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationship
    user: Optional["User"] = Relationship()
