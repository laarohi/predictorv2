"""Fixture schemas."""

import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel

from app.models.fixture import MatchStatus


class FixtureRead(BaseModel):
    """Schema for reading fixture data."""

    id: uuid.UUID
    home_team: str
    away_team: str
    kickoff: datetime
    stage: str
    group: str | None
    match_number: int | None
    status: MatchStatus
    minute: int | None
    is_locked: bool
    time_until_lock: int | None  # Seconds until lock, None if already locked

    class Config:
        """Pydantic config."""

        from_attributes = True


class FixturesByGroup(BaseModel):
    """Fixtures organized by group."""

    group: str
    fixtures: list[FixtureRead]


class LockStatus(BaseModel):
    """Lock status for a fixture."""

    fixture_id: uuid.UUID
    is_locked: bool
    locks_at: datetime
    time_remaining: timedelta | None
