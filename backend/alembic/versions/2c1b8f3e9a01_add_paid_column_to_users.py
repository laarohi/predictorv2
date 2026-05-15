"""Add paid column to users

Revision ID: 2c1b8f3e9a01
Revises: f06b6a2077d3
Create Date: 2026-05-15 09:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2c1b8f3e9a01'
down_revision: Union[str, None] = 'f06b6a2077d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add paid boolean column to users with server_default=false so existing
    rows back-fill cleanly."""
    op.add_column(
        'users',
        sa.Column('paid', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Drop the paid column."""
    op.drop_column('users', 'paid')
