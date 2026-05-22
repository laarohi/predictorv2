"""add phase to bonus_predictions

Revision ID: 5c6e46005455
Revises: b03d1f08f869
Create Date: 2026-05-22 05:24:34.523633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5c6e46005455'
down_revision: Union[str, None] = 'b03d1f08f869'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bonus picks are structurally Phase 1 (they lock with phase1_deadline
    # and there is no Phase 2 bonus concept). The server_default backfills
    # every existing row to PHASE_1 at migration time. New rows will use
    # the model-level default from BonusPrediction.phase.
    #
    # The `predictionphase` enum type already exists in the DB — it was
    # created by the initial migration for MatchPrediction.phase, and
    # SQLAlchemy reuses it here without trying to CREATE TYPE again.
    op.add_column(
        'bonus_predictions',
        sa.Column(
            'phase',
            sa.Enum('PHASE_1', 'PHASE_2', name='predictionphase', create_type=False),
            nullable=False,
            server_default='PHASE_1',
        ),
    )


def downgrade() -> None:
    op.drop_column('bonus_predictions', 'phase')
