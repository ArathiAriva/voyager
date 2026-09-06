"""add place_anecdotes

There was nowhere to put "the queue was 40 minutes but the mosaics were worth it".
The only user-writable text on a saved place is `notes`, and on the egwene profile
all 73 places have notes -- every one of them agent-written descriptions. `notes`
is also a documented prompt-injection channel: the safety suite plants payloads
there because that text reaches the agent.

So anecdotes get their own table. Provenance stays clean (the user's voice never
mixes with agent- or web-authored copy), more than one per place is possible, and
CASCADE is correct here because an anecdote about a deleted place has no meaning
on its own.

See docs/visited-places-and-anecdotes.md (Stage 2).

Revision ID: d3f7b26c410a
Revises: c9d4e18a52b6
Create Date: 2026-09-05 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f7b26c410a'
down_revision: Union[str, None] = 'c9d4e18a52b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "place_anecdotes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("place_id", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="app"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["saved_places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_place_anecdotes_place_id", "place_anecdotes", ["place_id"])


def downgrade() -> None:
    op.drop_index("ix_place_anecdotes_place_id", table_name="place_anecdotes")
    op.drop_table("place_anecdotes")
