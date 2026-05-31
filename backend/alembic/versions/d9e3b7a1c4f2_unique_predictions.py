"""Add DB-level uniqueness to prediction tables

The MatchPrediction/TeamPrediction models declared `Config.unique_together`,
which SQLModel/SQLAlchemy silently ignores — so the upsert write paths
(SELECT-then-INSERT) could insert duplicate rows under a concurrent/double-tap
save, double-counting points and breaking the 100%-integrity invariant.

This enforces the keys at the DB level:
- match_predictions: UNIQUE(user_id, fixture_id)
- team_predictions:  UNIQUE(user_id, team, stage, phase)
  (phase is part of the key so a user's Phase 1 and Phase 2 brackets may both
   hold the same team/stage)

Revision ID: d9e3b7a1c4f2
Revises: cf53eb42651f
Create Date: 2026-05-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d9e3b7a1c4f2"
down_revision: Union[str, None] = "cf53eb42651f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_match_predictions_user_fixture",
        "match_predictions",
        ["user_id", "fixture_id"],
    )
    op.create_unique_constraint(
        "uq_team_predictions_user_team_stage_phase",
        "team_predictions",
        ["user_id", "team", "stage", "phase"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_team_predictions_user_team_stage_phase",
        "team_predictions",
        type_="unique",
    )
    op.drop_constraint(
        "uq_match_predictions_user_fixture",
        "match_predictions",
        type_="unique",
    )
