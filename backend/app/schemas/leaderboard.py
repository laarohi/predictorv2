"""Leaderboard schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, computed_field


class PhaseBreakdown(BaseModel):
    """Points breakdown for a single phase."""

    # Match predictions
    match_outcome_points: int = 0
    exact_score_points: int = 0
    hybrid_bonus_points: int = 0

    # Bracket predictions - by stage
    group_advance_points: int = 0
    group_position_points: int = 0
    round_of_32_points: int = 0
    round_of_16_points: int = 0
    quarter_final_points: int = 0
    semi_final_points: int = 0
    final_points: int = 0
    winner_points: int = 0

    @computed_field
    @property
    def match_total(self) -> int:
        """Total points from match predictions."""
        return self.match_outcome_points + self.exact_score_points + self.hybrid_bonus_points

    @computed_field
    @property
    def bracket_total(self) -> int:
        """Total points from bracket predictions."""
        return (
            self.group_advance_points
            + self.group_position_points
            + self.round_of_32_points
            + self.round_of_16_points
            + self.quarter_final_points
            + self.semi_final_points
            + self.final_points
            + self.winner_points
        )

    @computed_field
    @property
    def total(self) -> int:
        """Total points for this phase."""
        return self.match_total + self.bracket_total


class PointBreakdown(BaseModel):
    """Full breakdown with phase separation."""

    phase1: PhaseBreakdown = PhaseBreakdown()
    phase2: PhaseBreakdown = PhaseBreakdown()

    # Aggregate statistics (for display)
    correct_outcomes: int = 0
    exact_scores: int = 0
    total_predictions: int = 0

    @computed_field
    @property
    def match_total(self) -> int:
        """Combined match total across phases."""
        return self.phase1.match_total + self.phase2.match_total

    @computed_field
    @property
    def bracket_total(self) -> int:
        """Combined bracket total across phases."""
        return self.phase1.bracket_total + self.phase2.bracket_total

    @computed_field
    @property
    def total(self) -> int:
        """Total points across all phases."""
        return self.phase1.total + self.phase2.total

    # Legacy computed fields for backwards compatibility
    @computed_field
    @property
    def match_outcome_points(self) -> int:
        """Combined match outcome points (legacy)."""
        return self.phase1.match_outcome_points + self.phase2.match_outcome_points

    @computed_field
    @property
    def exact_score_points(self) -> int:
        """Combined exact score points (legacy)."""
        return self.phase1.exact_score_points + self.phase2.exact_score_points

    @computed_field
    @property
    def hybrid_bonus_points(self) -> int:
        """Combined hybrid bonus points (legacy)."""
        return self.phase1.hybrid_bonus_points + self.phase2.hybrid_bonus_points

    @computed_field
    @property
    def group_advance_points(self) -> int:
        """Combined group advance points (legacy)."""
        return self.phase1.group_advance_points + self.phase2.group_advance_points

    @computed_field
    @property
    def group_position_points(self) -> int:
        """Combined group position points (legacy)."""
        return self.phase1.group_position_points + self.phase2.group_position_points

    @computed_field
    @property
    def round_of_32_points(self) -> int:
        """Combined R32 points (legacy)."""
        return self.phase1.round_of_32_points + self.phase2.round_of_32_points

    @computed_field
    @property
    def round_of_16_points(self) -> int:
        """Combined R16 points (legacy)."""
        return self.phase1.round_of_16_points + self.phase2.round_of_16_points

    @computed_field
    @property
    def quarter_final_points(self) -> int:
        """Combined QF points (legacy)."""
        return self.phase1.quarter_final_points + self.phase2.quarter_final_points

    @computed_field
    @property
    def semi_final_points(self) -> int:
        """Combined SF points (legacy)."""
        return self.phase1.semi_final_points + self.phase2.semi_final_points

    @computed_field
    @property
    def final_points(self) -> int:
        """Combined final points (legacy)."""
        return self.phase1.final_points + self.phase2.final_points

    @computed_field
    @property
    def winner_points(self) -> int:
        """Combined winner points (legacy)."""
        return self.phase1.winner_points + self.phase2.winner_points


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
    phase: str | None = None  # Which phase this leaderboard is for (None = overall)
