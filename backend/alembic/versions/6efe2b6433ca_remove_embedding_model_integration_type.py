"""remove_embedding_model_integration_type

Revision ID: 6efe2b6433ca
Revises: f1a2b3c4d5e6
Create Date: 2025-10-27 11:21:37.801627

This migration removes EMBEDDING_MODEL from the integrationtype enum.
Embedding models are no longer managed as connections - they're handled by
DenseEmbedder and SparseEmbedder singletons in the new sync architecture.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6efe2b6433ca'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    """Remove EMBEDDING_MODEL connections and enum value from database."""

    # Step 1: Delete any connections with integration_type='EMBEDDING_MODEL'
    # This includes the local_text2vec native connection
    op.execute("""
        DELETE FROM sync_connection
        WHERE connection_id IN (
            SELECT id FROM connection WHERE integration_type = 'EMBEDDING_MODEL'
        )
    """)

    op.execute("""
        DELETE FROM connection
        WHERE integration_type = 'EMBEDDING_MODEL'
    """)

    # Step 2: Remove EMBEDDING_MODEL from integrationtype enum
    # PostgreSQL doesn't support removing enum values directly, so we need to recreate it

    # 2a. Create new enum without EMBEDDING_MODEL
    op.execute("""
        CREATE TYPE integrationtype_new AS ENUM (
            'SOURCE',
            'DESTINATION',
            'AUTH_PROVIDER'
        )
    """)

    # 2b. Convert connection table to use new enum
    op.execute("""
        ALTER TABLE connection
        ALTER COLUMN integration_type TYPE integrationtype_new
        USING integration_type::text::integrationtype_new
    """)

    # 2c. Drop old enum
    op.execute("DROP TYPE integrationtype")

    # 2d. Rename new enum to original name
    op.execute("ALTER TYPE integrationtype_new RENAME TO integrationtype")


def downgrade():
    """Restore EMBEDDING_MODEL enum value and connections."""

    # Step 1: Recreate enum with EMBEDDING_MODEL
    op.execute("""
        CREATE TYPE integrationtype_new AS ENUM (
            'SOURCE',
            'DESTINATION',
            'AUTH_PROVIDER',
            'EMBEDDING_MODEL'
        )
    """)

    # Convert column to new enum
    op.execute("""
        ALTER TABLE connection
        ALTER COLUMN integration_type TYPE integrationtype_new
        USING integration_type::text::integrationtype_new
    """)

    # Drop old enum and rename
    op.execute("DROP TYPE integrationtype")
    op.execute("ALTER TYPE integrationtype_new RENAME TO integrationtype")

    # Note: We don't restore the deleted connections as they're deprecated
    # Manual restoration would be needed if truly required
