"""Add organization_feature_flag table for feature flag management

Revision ID: add_feature_flags_001
Revises: add_yearly_prepay_001
Create Date: 2025-10-07 12:00:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "add_feature_flags_001"
down_revision = "add_yearly_prepay_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create feature_flag table
    op.create_table(
        "feature_flag",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flag", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
        ),
        sa.Column(
            "modified_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(NOW() AT TIME ZONE 'UTC')"),
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "flag", name="uq_org_flag"),
    )

    # Create index on organization_id for efficient lookups
    op.create_index("ix_feature_flag_organization_id", "feature_flag", ["organization_id"])


def downgrade() -> None:
    # Drop index
    op.drop_index("ix_feature_flag_organization_id", table_name="feature_flag")

    # Drop table
    op.drop_table("feature_flag")
