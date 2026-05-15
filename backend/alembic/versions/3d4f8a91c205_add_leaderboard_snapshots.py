"""Add leaderboard_snapshots table

Revision ID: 3d4f8a91c205
Revises: 2c1b8f3e9a01
Create Date: 2026-05-15 10:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '3d4f8a91c205'
down_revision: Union[str, None] = '2c1b8f3e9a01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create leaderboard_snapshots with a unique (user_id, captured_date)
    constraint so the daily snapshot writer can be idempotent."""
    op.create_table(
        'leaderboard_snapshots',
        sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('total_points', sa.Integer(), nullable=False),
        sa.Column('captured_date', sa.Date(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('user_id', 'captured_date', name='uq_snapshot_user_date'),
    )
    op.create_index(
        'ix_leaderboard_snapshots_user_id',
        'leaderboard_snapshots',
        ['user_id'],
    )
    op.create_index(
        'ix_leaderboard_snapshots_captured_date',
        'leaderboard_snapshots',
        ['captured_date'],
    )


def downgrade() -> None:
    op.drop_index('ix_leaderboard_snapshots_captured_date', table_name='leaderboard_snapshots')
    op.drop_index('ix_leaderboard_snapshots_user_id', table_name='leaderboard_snapshots')
    op.drop_table('leaderboard_snapshots')
