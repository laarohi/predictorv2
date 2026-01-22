"""Score schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.score import ScoreSource


class ScoreRead(BaseModel):
    """Schema for reading score data."""

    id: uuid.UUID
    fixture_id: uuid.UUID
    home_score: int
    away_score: int
    home_score_et: int | None
    away_score_et: int | None
    home_penalties: int | None
    away_penalties: int | None
    source: ScoreSource
    verified: bool
    outcome: str

    class Config:
        """Pydantic config."""

        from_attributes = True


class ScoreUpdate(BaseModel):
    """Schema for updating/creating a score (admin)."""

    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    home_score_et: int | None = Field(default=None, ge=0)
    away_score_et: int | None = Field(default=None, ge=0)
    home_penalties: int | None = Field(default=None, ge=0)
    away_penalties: int | None = Field(default=None, ge=0)
    verified: bool = False


class LiveMatchScore(BaseModel):
    """Live score for a single match."""

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: str
    minute: int | None
    kickoff: datetime


class LiveScoreResponse(BaseModel):
    """Response for live scores polling endpoint."""

    matches: list[LiveMatchScore]
    last_updated: datetime
