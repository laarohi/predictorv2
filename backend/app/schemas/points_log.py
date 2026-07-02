"""Points-log response schemas.

One `PointsLogEvent` per point award (or graded miss) for one user, anchored
to the timestamp of the underlying football moment. Built by
`services/points_log.build_points_log`; served by
`GET /users/{user_id}/points-log`.

The event is a single flat model with kind-specific optional fields (rather
than a union) — the frontend switches on `kind` and reads the fields that
kind guarantees, mirroring how the audit-log events are shaped.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PointsLogChip(BaseModel):
    """One component of an event's points (e.g. Outcome +5, Exact +10)."""

    label: str
    points: int


class PointsLogEvent(BaseModel):
    """One timestamped point award (or graded 0-point miss)."""

    id: str
    kind: Literal["match", "advance", "bonus"]
    ts: datetime
    points: int
    is_miss: bool
    # 'phase_1' | 'phase_2' for match events; 'phase_1' | 'phase_2' | 'both'
    # for advance events (both = P1 and P2 brackets scored the same team+stage);
    # None for bonus (cross-phase).
    phase: str | None = None
    # True when the Phase-2 component came from the Phase-1 bracket carried
    # forward (user never submitted a Phase-2 bracket).
    p2_fallback: bool = False
    # Fixture stage for match events; predicted stage for advance events.
    stage: str | None = None
    group: str | None = None

    # --- match events ---
    fixture_id: uuid.UUID | None = None
    home_team: str | None = None
    away_team: str | None = None
    predicted: str | None = None  # "2-0"
    actual: str | None = None  # display score (ET folded in), "1-1"
    result: str | None = None  # 'exact' | 'outcome' | 'miss'

    # --- advance events ---
    team: str | None = None
    predicted_position: int | None = None  # R32 events (group finishing spot)
    actual_position: int | None = None
    third_place: bool = False  # qualified (or died) via the best-thirds cut
    elim_stage: str | None = None  # where the team's run ended ('group', 'round_of_32', ...)

    # --- bonus events ---
    question_label: str | None = None
    answer: str | None = None
    correct_answers: list[str] = []

    chips: list[PointsLogChip] = []


class PointsLogResponse(BaseModel):
    """Full chronological (desc) points log for one user."""

    user_id: uuid.UUID
    user_name: str
    total_points: int  # sum of event points — reconciles with the leaderboard
    events: list[PointsLogEvent]
