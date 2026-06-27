"""Prediction schemas."""

import uuid
from collections import Counter
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.prediction import PredictionPhase
from app.schemas.fixture import FixtureScore


class MatchPredictionCreate(BaseModel):
    """Schema for creating a match prediction."""

    fixture_id: uuid.UUID
    home_score: int = Field(ge=0, le=20)
    away_score: int = Field(ge=0, le=20)


class MatchPredictionUpdate(BaseModel):
    """Schema for updating a match prediction."""

    home_score: int = Field(ge=0, le=20)
    away_score: int = Field(ge=0, le=20)


class MatchPredictionRead(BaseModel):
    """Schema for reading a match prediction."""

    id: uuid.UUID
    fixture_id: uuid.UUID
    home_score: int
    away_score: int
    phase: PredictionPhase
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Include fixture info for display
    home_team: str | None = None
    away_team: str | None = None
    kickoff: datetime | None = None
    is_locked: bool = False

    class Config:
        """Pydantic config."""

        from_attributes = True


# Stored stage values are singular, matching Fixture.stage and the scoring
# service. "group" rows carry a group_position; the rest are knockout rounds.
BracketStage = Literal[
    "group",
    "round_of_32",
    "round_of_16",
    "quarter_final",
    "semi_final",
    "final",
    "winner",
]

# Maximum plausible picks per stage for a 48-team World Cup. Anything above
# is junk-row pollution (e.g. three "winner" rows) — reject at the schema.
_STAGE_PICK_LIMITS: dict[str, int] = {
    "group": 48,
    "round_of_32": 32,
    "round_of_16": 16,
    "quarter_final": 8,
    "semi_final": 4,
    "final": 2,
    "winner": 1,
}


class TeamAdvancementPrediction(BaseModel):
    """Single team advancement prediction."""

    team: str = Field(min_length=1, max_length=64)
    stage: BracketStage
    group_position: int | None = Field(default=None, ge=1, le=4)


class BracketPrediction(BaseModel):
    """User's full bracket prediction."""

    group_winners: dict[str, list[str]]  # group -> [1st, 2nd, 3rd (if advances)]
    round_of_32: list[str]
    round_of_16: list[str]
    quarter_finals: list[str]
    semi_finals: list[str]
    final: list[str]
    winner: str


class BracketPredictionUpdate(BaseModel):
    """Schema for updating bracket predictions."""

    # A full bracket is ~120 entries (group positions + every KO round +
    # winner); cap above that to reject storage-abuse payloads.
    predictions: list[TeamAdvancementPrediction] = Field(max_length=200)

    @model_validator(mode="after")
    def _validate_picks(self) -> "BracketPredictionUpdate":
        # Duplicate (team, stage) pairs would otherwise hit the DB unique
        # constraint and surface as a 500 with full rollback.
        pairs = [(p.team, p.stage) for p in self.predictions]
        if len(pairs) != len(set(pairs)):
            raise ValueError("duplicate (team, stage) picks in payload")
        for stage, count in Counter(p.stage for p in self.predictions).items():
            if count > _STAGE_PICK_LIMITS[stage]:
                raise ValueError(
                    f"too many '{stage}' picks: {count} "
                    f"(max {_STAGE_PICK_LIMITS[stage]})"
                )
        return self


# Community predictions schemas (for the results page scatter plot)


class CommunityPrediction(BaseModel):
    """A single user's prediction for a match (anonymized to name only)."""

    user_name: str
    home_score: int
    away_score: int


class CommunityPredictionsResponse(BaseModel):
    """All predictions for a single fixture, for community viewing."""

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    predictions: list[CommunityPrediction]
    actual: FixtureScore | None = None


# Overview schemas — the "who predicted what" distribution pages. All of
# these are aggregates across the whole pool, so the same blind-pool gates
# as the community endpoint apply (Phase 1 deadline / Phase 2 bracket
# deadline) before any of them is served.


class OverviewCountCell(BaseModel):
    """A pick count plus exactly who is behind it (alphabetical names)."""

    count: int
    users: list[str]


class OverviewTeamRow(BaseModel):
    """Per-team prediction counts inside one group panel."""

    team: str
    # Index 0..3 — users whose predicted standings (derived from their score
    # picks, same derivation the group_position bonus scores against) put
    # the team 1st/2nd/3rd/4th in its group.
    positions: list[OverviewCountCell]
    # Users whose Phase 1 bracket includes the team in the Round of 32.
    advance: OverviewCountCell


class OverviewFixtureRow(BaseModel):
    """Outcome split (1/X/2) of every player's score pick for one fixture."""

    fixture_id: uuid.UUID
    home_team: str
    away_team: str
    kickoff: datetime
    status: str
    home_count: int
    draw_count: int
    away_count: int
    # Actual result, present once the fixture has a score row (live or final)
    # so the overview can paint finished/in-play matches without a second call.
    actual_home: int | None = None
    actual_away: int | None = None


class OverviewGroup(BaseModel):
    group: str
    teams: list[OverviewTeamRow]
    fixtures: list[OverviewFixtureRow]


class GroupsOverviewResponse(BaseModel):
    total_predictors: int
    groups: list[OverviewGroup]


class KnockoutScoreFixtureRow(OverviewFixtureRow):
    """A single knockout fixture's pool-wide score-pick distribution.

    Same shape as a group fixture row plus the knockout `stage` label
    (``round_of_32`` .. ``final``) so the overview can group rows by round.
    Only fixtures that are individually locked or finished appear — the
    per-match blind-pool gate (``get_fixture_lock_view``) is applied before
    a row is built, so unlocked knockout picks never leak.
    """

    stage: str


class KnockoutScoresOverviewResponse(BaseModel):
    """Pool-wide distribution of Phase 2 knockout match-score picks.

    `total_predictors` counts the distinct (non-ghost) players whose picks
    appear across the *visible* fixtures only. `fixtures` is ordered by
    round (round_of_32 → final) then kickoff. A round that has no
    locked/finished fixtures yet simply contributes no rows.
    """

    total_predictors: int
    fixtures: list[KnockoutScoreFixtureRow]


class BracketOverviewTeamRow(BaseModel):
    """Who (and how many) predicted this team to reach each knockout stage."""

    team: str
    group: str | None
    round_of_32: OverviewCountCell
    round_of_16: OverviewCountCell
    quarter_final: OverviewCountCell
    semi_final: OverviewCountCell
    final: OverviewCountCell
    winner: OverviewCountCell


class BracketOverviewResponse(BaseModel):
    phase: int
    total_predictors: int
    teams: list[BracketOverviewTeamRow]


class BonusOverviewAnswerRow(BaseModel):
    """One distinct answer to a bonus question and who picked it."""

    answer: str
    count: int
    users: list[str]
    # None while the admin hasn't recorded a correct answer for the
    # question; True/False once one exists.
    is_correct: bool | None = None


class BonusOverviewQuestion(BaseModel):
    """A bonus question with the pool-wide answer distribution."""

    id: str
    category: str  # 'group_stage' | 'top_flop' | 'awards'
    label: str
    input_type: str  # 'team' | 'player'
    points: int
    # Recorded correct answer(s) — multiple on ties; empty until entered.
    correct_answers: list[str]
    # Distinct answers, most popular first (ties alphabetical).
    answers: list[BonusOverviewAnswerRow]


class BonusOverviewResponse(BaseModel):
    total_predictors: int
    questions: list[BonusOverviewQuestion]


# ── Group qualification ledger (per-group Phase-1 advancement attribution) ──
class GroupQualTeam(BaseModel):
    """One team's qualification contribution within a completed group."""

    team: str
    predicted_position: int | None
    actual_position: int
    base_points: int  # +round_of_32 for getting out of the group
    position_points: int  # +group_position for the correct finishing spot


class GroupQualEntry(BaseModel):
    """A completed group and the teams that earned the calling user points."""

    group: str
    total: int
    teams: list[GroupQualTeam]
