"""Leaderboard schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class PointBreakdown(BaseModel):
    """Detailed point breakdown for a user."""

    match_outcome_points: int = 0
    exact_score_points: int = 0
    group_advancement_points: int = 0
    knockout_advancement_points: int = 0

    @property
    def total(self) -> int:
        """Total points."""
        return (
            self.match_outcome_points
            + self.exact_score_points
            + self.group_advancement_points
            + self.knockout_advancement_points
        )


class UserPoints(BaseModel):
    """Points for a specific category."""

    category: str
    points: int
    details: str | None = None


class LeaderboardEntry(BaseModel):
    """Single entry in the leaderboard."""

    user_id: uuid.UUID
    user_name: str
    position: int
    total_points: int
    breakdown: PointBreakdown
    correct_outcomes: int = 0
    exact_scores: int = 0
    movement: int = 0  # Position change since last update


class LeaderboardResponse(BaseModel):
    """Full leaderboard response."""

    entries: list[LeaderboardEntry]
    last_calculated: datetime
    total_participants: int
