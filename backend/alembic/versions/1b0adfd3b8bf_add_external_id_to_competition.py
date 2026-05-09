"""add_external_id_to_competition

Revision ID: 1b0adfd3b8bf
Revises: 0ecd447ccd5a
Create Date: 2026-05-09 17:48:26.822551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '1b0adfd3b8bf'
down_revision: Union[str, None] = '0ecd447ccd5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('competitions', sa.Column('external_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_competitions_external_id'), 'competitions', ['external_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_competitions_external_id'), table_name='competitions')
    op.drop_column('competitions', 'external_id')
