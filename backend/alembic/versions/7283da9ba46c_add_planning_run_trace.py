"""add planning run trace

Revision ID: 7283da9ba46c
Revises: 50836dc99bd3
Create Date: 2026-09-04 09:17:44.174427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7283da9ba46c'
down_revision: Union[str, None] = '50836dc99bd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('planning_run',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=True),
    sa.Column('user_message', sa.Text(), nullable=False),
    sa.Column('destination', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('intent', sa.String(), nullable=True),
    sa.Column('critic_score', sa.Integer(), nullable=True),
    sa.Column('revision_count', sa.Integer(), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('planning_step',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('run_id', sa.String(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('node', sa.String(), nullable=False),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('output', sa.JSON(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['planning_run.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('planning_step')
    op.drop_table('planning_run')
