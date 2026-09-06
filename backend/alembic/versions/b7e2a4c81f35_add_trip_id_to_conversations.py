"""add trip_id to conversations

Conversations had no link to a trip in either direction, so trip context was
re-derived from message text on every turn -- and the planning graph's
_resolve_trip_id, having only a destination string to work with, **created a new
trip whenever its fuzzy match missed** (B-13). That is silent data corruption:
the user's first sight of it is a duplicate card on the trips page.

NULL is a legitimate permanent state, not a missing value to backfill. Existing
conversations get NULL because nothing reliably links a historical chat to a
trip, and guessing from titles would be inventing data.

SQLite cannot add a foreign key with ALTER TABLE, so the constraint is created
through batch_alter_table, which rebuilds the table. `conversations` holds only
scalar columns, so the rebuild is safe -- but note it is a rebuild, not an
in-place add.

Revision ID: b7e2a4c81f35
Revises: a1f3c9d24e70
Create Date: 2026-09-05 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2a4c81f35'
down_revision: Union[str, None] = 'a1f3c9d24e70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("trip_id", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_conversations_trip_id",
            "trips",
            ["trip_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("fk_conversations_trip_id", type_="foreignkey")
        batch.drop_column("trip_id")
