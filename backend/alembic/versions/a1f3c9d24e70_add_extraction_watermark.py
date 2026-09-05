"""add extraction watermark to conversations

Memory extraction runs as a background task, so the LLM call and the Chroma write
are seconds apart. Anything that kills the process in that window -- a deploy, a
crash, uvicorn --reload picking up an edit -- loses the extraction with no error
and no trace, while the user has already been told their preference was noted.

`extracted_through` records how far extraction has *successfully written*, so a
conversation with messages newer than its watermark can be retried. NULL means
"never extracted", which is the correct value for every existing row: their
extractions may well have succeeded, but nothing recorded it, and re-extracting
is idempotent (episodes upsert on conversation_id, preferences on a content hash).

Revision ID: a1f3c9d24e70
Revises: 7283da9ba46c
Create Date: 2026-09-05 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f3c9d24e70'
down_revision: Union[str, None] = '7283da9ba46c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("extracted_through", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "extracted_through")
