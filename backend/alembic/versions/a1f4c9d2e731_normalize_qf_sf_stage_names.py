"""normalize QF/SF stage names from plural to singular

Revision ID: a1f4c9d2e731
Revises: 3c0dc4ec5fd7
Create Date: 2026-05-24 12:00:00.000000

Background: bracket advancement predictions were stored with stage values
'quarter_finals' / 'semi_finals' (plural — the convention the frontend's
BracketPrediction object uses) while scoring (`calculate_advancement_points`
in `app.services.scoring`) and `Fixture.stage` use the singular form
('quarter_final' / 'semi_final'). The mismatch made every QF and SF
advancement prediction score zero points.

Fix: normalize stored values to the singular form so scoring can match.
The frontend writer (`bracketToPredictions`) and the GET-bracket endpoint
have been updated in the same change to use singular on the wire too.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1f4c9d2e731"
down_revision: Union[str, None] = "3c0dc4ec5fd7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE team_predictions SET stage = 'quarter_final' "
        "WHERE stage = 'quarter_finals'"
    )
    op.execute(
        "UPDATE team_predictions SET stage = 'semi_final' "
        "WHERE stage = 'semi_finals'"
    )
    op.execute(
        "UPDATE team_prediction_history SET stage = 'quarter_final' "
        "WHERE stage = 'quarter_finals'"
    )
    op.execute(
        "UPDATE team_prediction_history SET stage = 'semi_final' "
        "WHERE stage = 'semi_finals'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE team_predictions SET stage = 'quarter_finals' "
        "WHERE stage = 'quarter_final'"
    )
    op.execute(
        "UPDATE team_predictions SET stage = 'semi_finals' "
        "WHERE stage = 'semi_final'"
    )
    op.execute(
        "UPDATE team_prediction_history SET stage = 'quarter_finals' "
        "WHERE stage = 'quarter_final'"
    )
    op.execute(
        "UPDATE team_prediction_history SET stage = 'semi_finals' "
        "WHERE stage = 'semi_final'"
    )
