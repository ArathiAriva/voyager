"""add visited flag to saved_places

A saved place could not be marked as visited, so a restaurant the user booked and
loved and one they bookmarked and skipped were the same row. That makes "where did
I actually eat in Rome" unanswerable, lets Voyager re-recommend somewhere they
already went, and throws away the strongest preference signal in the app: what
they *did*, versus what they merely considered.

`visited` is a boolean rather than a status enum -- "planned / visited / skipped"
invites a third state nobody maintains, and not-visited is the correct default for
every existing row. `visited_at` is optional: marking a place visited should not
require also remembering the date.

See docs/visited-places-and-anecdotes.md (Stage 1).

Revision ID: c9d4e18a52b6
Revises: b7e2a4c81f35
Create Date: 2026-09-05 20:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d4e18a52b6'
down_revision: Union[str, None] = 'b7e2a4c81f35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "saved_places",
        sa.Column("visited", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("saved_places", sa.Column("visited_at", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("saved_places", "visited_at")
    op.drop_column("saved_places", "visited")
