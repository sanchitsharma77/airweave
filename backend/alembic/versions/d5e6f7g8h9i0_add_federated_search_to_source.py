"""Add federated_search field to source table

Revision ID: d5e6f7g8h9i0
Revises: cb4843afd172
Create Date: 2025-10-08 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5e6f7g8h9i0"
down_revision: Union[str, None] = "cb4843afd172"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add federated_search column to source table."""
    op.add_column(
        "source",
        sa.Column("federated_search", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Remove federated_search column from source table."""
    op.drop_column("source", "federated_search")
