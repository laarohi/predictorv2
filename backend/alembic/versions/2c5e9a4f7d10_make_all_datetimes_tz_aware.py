"""Make all datetime columns timezone-aware (TIMESTAMPTZ)

System-wide rule: every datetime is timezone-aware UTC. Existing naive
values stored in TIMESTAMP columns are assumed to be UTC (per the
codebase convention prior to this migration), so each ALTER uses
`<col> AT TIME ZONE 'UTC'` to preserve the moment.

Revision ID: 2c5e9a4f7d10
Revises: 1b0adfd3b8bf
Create Date: 2026-05-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2c5e9a4f7d10'
down_revision: Union[str, None] = '1b0adfd3b8bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) tuples for every datetime field across the schema.
TZ_AWARE_COLUMNS = [
    ('users', 'created_at'),
    ('users', 'updated_at'),

    ('competitions', 'phase1_deadline'),
    ('competitions', 'phase2_activated_at'),
    ('competitions', 'phase2_bracket_deadline'),
    ('competitions', 'phase2_deadline'),
    ('competitions', 'created_at'),
    ('competitions', 'updated_at'),

    ('fixtures', 'kickoff'),
    ('fixtures', 'created_at'),
    ('fixtures', 'updated_at'),

    ('match_predictions', 'locked_at'),
    ('match_predictions', 'created_at'),
    ('match_predictions', 'updated_at'),

    ('team_predictions', 'locked_at'),
    ('team_predictions', 'created_at'),
    ('team_predictions', 'updated_at'),

    ('scores', 'created_at'),
    ('scores', 'updated_at'),
]


def upgrade() -> None:
    """Convert TIMESTAMP → TIMESTAMP WITH TIME ZONE.

    Each existing naive value is assumed to be UTC and gets the UTC
    timezone applied via `AT TIME ZONE 'UTC'`.
    """
    for table, column in TZ_AWARE_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Convert back to TIMESTAMP (naive). Existing aware values get their
    timezone offset stripped (treated as UTC since that's our convention)."""
    for table, column in TZ_AWARE_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
