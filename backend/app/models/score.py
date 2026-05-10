"""Score model for actual match results."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.fixture import Fixture


class ScoreSource(str, Enum):
    """Source of the score data."""

    API = "api"  # From external API
    MANUAL = "manual"  # Entered by admin


class Score(SQLModel, table=True):
    """Actual match result."""

    __tablename__ = "scores"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixtures.id", unique=True, index=True)

    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)

    # For knockout matches with extra time/penalties
    home_score_et: int | None = None  # After extra time
    away_score_et: int | None = None
    home_penalties: int | None = None
    away_penalties: int | None = None

    source: ScoreSource = Field(default=ScoreSource.API)
    verified: bool = Field(default=False)  # Admin verified

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    fixture: "Fixture" = Relationship(back_populates="score")

    @property
    def outcome(self) -> str:
        """Get match outcome: '1' (home), 'X' (draw), '2' (away)."""
        # For knockout, consider penalties
        if self.home_penalties is not None and self.away_penalties is not None:
            if self.home_penalties > self.away_penalties:
                return "1"
            return "2"

        # For extra time
        if self.home_score_et is not None and self.away_score_et is not None:
            if self.home_score_et > self.away_score_et:
                return "1"
            elif self.home_score_et < self.away_score_et:
                return "2"
            return "X"

        # Regular time
        if self.home_score > self.away_score:
            return "1"
        elif self.home_score < self.away_score:
            return "2"
        return "X"

    @property
    def final_home_score(self) -> int:
        """Get final home score (including ET if applicable)."""
        return self.home_score_et if self.home_score_et is not None else self.home_score

    @property
    def final_away_score(self) -> int:
        """Get final away score (including ET if applicable)."""
        return self.away_score_et if self.away_score_et is not None else self.away_score
