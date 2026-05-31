"""Add indexes on fixtures.status and fixtures.stage

Scoring, standings, advancement, and the leaderboard repeatedly filter
fixtures by status (== finished) and by stage. These tables are small today,
but the indexes are cheap insurance for the hot read paths.

Revision ID: e1a4c7b2f9d0
Revises: d9e3b7a1c4f2
Create Date: 2026-05-30 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1a4c7b2f9d0"
down_revision: Union[str, None] = "d9e3b7a1c4f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_fixtures_status", "fixtures", ["status"])
    op.create_index("ix_fixtures_stage", "fixtures", ["stage"])


def downgrade() -> None:
    op.drop_index("ix_fixtures_stage", table_name="fixtures")
    op.drop_index("ix_fixtures_status", table_name="fixtures")
