"""Add users.token_version for JWT revocation

Tokens embed the user's token_version as a `tv` claim, checked on every
request. Bumping a user's token_version (POST /api/auth/me/logout-all)
invalidates all their outstanding tokens.

Revision ID: f2b5d8c1a3e6
Revises: e1a4c7b2f9d0
Create Date: 2026-05-30 02:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f2b5d8c1a3e6"
down_revision: Union[str, None] = "e1a4c7b2f9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
