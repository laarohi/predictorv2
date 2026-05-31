"""merge players and audit migration branches

Revision ID: ff59fdd71631
Revises: db998dd7cc5e, f2b5d8c1a3e6
Create Date: 2026-05-31 15:54:33.770469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'ff59fdd71631'
down_revision: Union[str, None] = ('db998dd7cc5e', 'f2b5d8c1a3e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
