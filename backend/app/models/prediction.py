"""Prediction models for match scores and team advancement."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models._datetime import utc_datetime_column, utc_now

if TYPE_CHECKING:
    from app.models.fixture import Fixture
    from app.models.user import User


class PredictionPhase(str, Enum):
    """Which prediction phase this was submitted in."""

    PHASE_1 = "phase_1"  # Pre-tournament
    PHASE_2 = "phase_2"  # After group stage


class MatchPrediction(SQLModel, table=True):
    """User's predicted score for a match."""

    __tablename__ = "match_predictions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixtures.id", index=True)

    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    phase: PredictionPhase = Field(default=PredictionPhase.PHASE_1)

    locked_at: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    user: "User" = Relationship(back_populates="match_predictions")
    fixture: "Fixture" = Relationship(back_populates="predictions")

    # One score prediction per (user, fixture). Enforced at the DB level —
    # the previous `Config.unique_together` was a SQLModel no-op, so concurrent
    # double-tap saves could insert duplicate rows and double-count points.
    __table_args__ = (
        UniqueConstraint("user_id", "fixture_id", name="uq_match_predictions_user_fixture"),
    )

    @property
    def predicted_outcome(self) -> str:
        """Get predicted outcome: '1' (home), 'X' (draw), '2' (away)."""
        if self.home_score > self.away_score:
            return "1"
        elif self.home_score < self.away_score:
            return "2"
        return "X"


class TeamPrediction(SQLModel, table=True):
    """User's prediction for team advancement in knockout stages."""

    __tablename__ = "team_predictions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)

    team: str = Field(index=True)  # Team name/code
    stage: str  # "round_of_32", "round_of_16", "quarter_final", etc.
    group_position: int | None = None  # 1, 2, or 3 for group stage
    phase: PredictionPhase = Field(default=PredictionPhase.PHASE_1)

    locked_at: datetime | None = Field(default=None, sa_column=utc_datetime_column(nullable=True))

    created_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())
    updated_at: datetime = Field(default_factory=utc_now, sa_column=utc_datetime_column())

    # Relationships
    user: "User" = Relationship(back_populates="team_predictions")

    # One pick per (user, team, stage, phase). `phase` is part of the key so a
    # user's Phase 1 and Phase 2 brackets can both hold the same team/stage.
    # Replaces a `Config.unique_together` that SQLModel silently ignored.
    __table_args__ = (
        UniqueConstraint(
            "user_id", "team", "stage", "phase",
            name="uq_team_predictions_user_team_stage_phase",
        ),
    )
