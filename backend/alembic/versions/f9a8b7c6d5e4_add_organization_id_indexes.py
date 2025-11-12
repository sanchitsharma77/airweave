"""Add organization_id indexes to org-scoped tables

Revision ID: f9a8b7c6d5e4
Revises: cb4843afd172
Create Date: 2025-01-12 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f9a8b7c6d5e4'
down_revision = 'cb4843afd172'
branch_labels = None
depends_on = None


# Tables that inherit from OrganizationBase and should get the index
# Entity is explicitly excluded (too large, better indexes on sync_id)
TABLES_TO_INDEX = [
    'source_connection',
    'source_rate_limit',
    'collection',
    'sync',
    'usage',
    'sync_job',
    'sync_cursor',
    'search_query',
    'redirect_session',
    'pg_field_catalog_table',
    'pg_field_catalog_column',
    'integration_credential',
    'connection_init_session',
    'api_key',
]


def upgrade() -> None:
    """Add organization_id indexes for efficient org-scoped queries."""
    for table_name in TABLES_TO_INDEX:
        index_name = f'ix_{table_name}_organization_id'
        op.create_index(
            index_name,
            table_name,
            ['organization_id'],
            unique=False,
            postgresql_using='btree'
        )


def downgrade() -> None:
    """Remove organization_id indexes."""
    for table_name in TABLES_TO_INDEX:
        index_name = f'ix_{table_name}_organization_id'
        op.drop_index(index_name, table_name=table_name)

