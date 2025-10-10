"""add_sync_job_cleanup_indexes

Revision ID: e3a7e8db826c
Revises: 45e94120d9e8
Create Date: 2025-10-10 16:00:14.659486

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e3a7e8db826c"
down_revision = "45e94120d9e8"
branch_labels = None
depends_on = None


def upgrade():
    # Create indexes for efficient cleanup queries
    op.create_index("idx_sync_job_status", "sync_job", ["status"])
    op.create_index("idx_sync_job_status_modified_at", "sync_job", ["status", "modified_at"])
    op.create_index("idx_sync_job_status_started_at", "sync_job", ["status", "started_at"])


def downgrade():
    # Drop indexes
    op.drop_index("idx_sync_job_status_started_at", table_name="sync_job")
    op.drop_index("idx_sync_job_status_modified_at", table_name="sync_job")
    op.drop_index("idx_sync_job_status", table_name="sync_job")
