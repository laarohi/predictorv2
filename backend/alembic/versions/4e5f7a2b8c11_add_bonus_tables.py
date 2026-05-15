"""Add bonus_predictions + bonus_answers tables

Revision ID: 4e5f7a2b8c11
Revises: 3d4f8a91c205
Create Date: 2026-05-15 11:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4e5f7a2b8c11'
down_revision: Union[str, None] = '3d4f8a91c205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two new tables backing the bonus-questions feature. The questions
    themselves live in config/worldcup2026.yml under bonus: — these tables
    only track per-user picks and per-competition correct answers."""

    op.create_table(
        'bonus_predictions',
        sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('question_id', sa.String(length=64), nullable=False),
        sa.Column('answer', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.UniqueConstraint('user_id', 'question_id', name='uq_bonus_pred_user_q'),
    )
    op.create_index('ix_bonus_predictions_user_id', 'bonus_predictions', ['user_id'])
    op.create_index('ix_bonus_predictions_question_id', 'bonus_predictions', ['question_id'])

    op.create_table(
        'bonus_answers',
        sa.Column('id', sa.Uuid(), primary_key=True, nullable=False),
        sa.Column('competition_id', sa.Uuid(), nullable=False),
        sa.Column('question_id', sa.String(length=64), nullable=False),
        sa.Column('correct_answer', sa.String(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['competition_id'], ['competitions.id']),
        sa.UniqueConstraint('competition_id', 'question_id', name='uq_bonus_ans_comp_q'),
    )
    op.create_index('ix_bonus_answers_competition_id', 'bonus_answers', ['competition_id'])
    op.create_index('ix_bonus_answers_question_id', 'bonus_answers', ['question_id'])


def downgrade() -> None:
    op.drop_index('ix_bonus_answers_question_id', table_name='bonus_answers')
    op.drop_index('ix_bonus_answers_competition_id', table_name='bonus_answers')
    op.drop_table('bonus_answers')
    op.drop_index('ix_bonus_predictions_question_id', table_name='bonus_predictions')
    op.drop_index('ix_bonus_predictions_user_id', table_name='bonus_predictions')
    op.drop_table('bonus_predictions')
