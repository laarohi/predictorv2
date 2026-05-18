"""Drop unique(competition_id, question_id) on bonus_answers

Allows multiple correct answers per (competition, question) — used when
two or more teams tie on the relevant criterion (e.g. most goals scored
in the group stage). Each correct answer becomes its own row; a user's
prediction wins points if it matches any of the rows for the question.

Revision ID: 5a8c1e2f3b09
Revises: 4e5f7a2b8c11
Create Date: 2026-05-16 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5a8c1e2f3b09'
down_revision: Union[str, None] = '4e5f7a2b8c11'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the (competition_id, question_id) unique constraint so the
    table can hold multiple correct answers per question. No data
    transformation needed — every existing single-answer row keeps the
    same semantics (it's now "one of possibly many correct answers")."""
    op.drop_constraint('uq_bonus_ans_comp_q', 'bonus_answers', type_='unique')


def downgrade() -> None:
    """Restore the unique constraint. WARNING: this will fail if any
    (competition, question) currently has more than one row — the
    operator would need to deduplicate manually before running it."""
    op.create_unique_constraint(
        'uq_bonus_ans_comp_q',
        'bonus_answers',
        ['competition_id', 'question_id'],
    )
