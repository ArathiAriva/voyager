"""add retrieval_log

Revision ID: 50836dc99bd3
Revises: 66ab624754ee
Create Date: 2026-09-03 22:54:15.546993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50836dc99bd3'
down_revision: Union[str, None] = '66ab624754ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('retrieval_log',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('collection', sa.String(), nullable=False),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('filters', sa.JSON(), nullable=False),
    sa.Column('n_requested', sa.Integer(), nullable=False),
    sa.Column('n_returned', sa.Integer(), nullable=False),
    sa.Column('result_ids', sa.JSON(), nullable=False),
    sa.Column('distances', sa.JSON(), nullable=False),
    sa.Column('caller', sa.String(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # Summary queries filter by collection and scan by recency.
    op.create_index('ix_retrieval_log_collection', 'retrieval_log', ['collection'])
    op.create_index('ix_retrieval_log_created_at', 'retrieval_log', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_retrieval_log_created_at', table_name='retrieval_log')
    op.drop_index('ix_retrieval_log_collection', table_name='retrieval_log')
    op.drop_table('retrieval_log')
