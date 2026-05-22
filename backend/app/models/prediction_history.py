"""Append-only audit history for predictions.

Why this exists: the prediction tables themselves only store the latest
state — once a user updates a score, the previous value is gone. If a
user later disputes "I entered 2-1, not 3-0" we have nothing to compare
against. These history tables capture every change at the moment it
happens, including request metadata, so disputes can be resolved.

Design rules:
- Append-only. Never UPDATE or DELETE rows in these tables.
- Same transaction as the prediction change. Either both are written or
  neither — we cannot have a saved prediction with no history row.
- Denormalised query fields (fixture_id, team/stage, question_id) live
  on the rows directly so "show me history for fixture X" is a simple
  index lookup rather than a JSONB filter.
- old_values / new_values store the serialised pre- and post-state.
  For inserts, old_values is null; for deletes, new_values is null.

SQLAlchemy gotcha: a Column object cannot be shared across multiple
table classes — that's why each subclass declares its own `created_at`
and JSON columns rather than inheriting them from a common base.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON
from sqlmodel import Column, Field, SQLModel

from app.models._datetime import utc_datetime_column, utc_now


class PredictionAction(str, Enum):
    """What happened to the prediction."""

    INSERT = "insert"  # First save (no prior row)
    UPDATE = "update"  # Edit of an existing row
    DELETE = "delete"  # Row removed (bracket rewrite path)
    LOCK = "lock"     # Server flipped locked_at (scheduler, not a user edit)


class PredictionSource(str, Enum):
    """Code path that produced the change.

    Helps distinguish user actions from server automation when reading
    the history. Add new values here when a new mutation site is added.
    """

    API_SINGLE = "api_single"                  # PUT /api/predictions/matches/{id}
    API_BATCH = "api_batch"                    # POST /api/predictions/matches/batch
    API_BRACKET_REWRITE = "api_bracket_rewrite"  # PUT /api/predictions/bracket
    API_BONUS_BATCH = "api_bonus_batch"        # POST /api/predictions/bonus
    LOCK_SCHEDULER = "lock_scheduler"          # services/locking.py:lock_predictions
    ADMIN = "admin"                            # /api/admin/*


def _json_column() -> Column:
    """Fresh JSON column per Field — sharing a Column across declarations
    fails at registration."""
    return Column(JSON, nullable=True)


class MatchPredictionHistory(SQLModel, table=True):
    """One row per change to a MatchPrediction."""

    __tablename__ = "match_prediction_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_id: uuid.UUID | None = Field(default=None, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixtures.id", index=True)
    action: PredictionAction
    source: PredictionSource
    performed_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", index=True
    )
    request_id: uuid.UUID | None = Field(default=None, index=True)
    client_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=512)
    old_values: dict[str, Any] | None = Field(default=None, sa_column=_json_column())
    new_values: dict[str, Any] | None = Field(default=None, sa_column=_json_column())
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column(index=True)
    )


class TeamPredictionHistory(SQLModel, table=True):
    """One row per change to a TeamPrediction (bracket pick)."""

    __tablename__ = "team_prediction_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_id: uuid.UUID | None = Field(default=None, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    team: str = Field(index=True, max_length=64)
    stage: str = Field(index=True, max_length=32)
    action: PredictionAction
    source: PredictionSource
    performed_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", index=True
    )
    request_id: uuid.UUID | None = Field(default=None, index=True)
    client_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=512)
    old_values: dict[str, Any] | None = Field(default=None, sa_column=_json_column())
    new_values: dict[str, Any] | None = Field(default=None, sa_column=_json_column())
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column(index=True)
    )


class BonusPredictionHistory(SQLModel, table=True):
    """One row per change to a BonusPrediction."""

    __tablename__ = "bonus_prediction_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_id: uuid.UUID | None = Field(default=None, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    question_id: str = Field(index=True, max_length=64)
    action: PredictionAction
    source: PredictionSource
    performed_by_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", index=True
    )
    request_id: uuid.UUID | None = Field(default=None, index=True)
    client_ip: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=512)
    old_values: dict[str, Any] | None = Field(default=None, sa_column=_json_column())
    new_values: dict[str, Any] | None = Field(default=None, sa_column=_json_column())
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=utc_datetime_column(index=True)
    )
