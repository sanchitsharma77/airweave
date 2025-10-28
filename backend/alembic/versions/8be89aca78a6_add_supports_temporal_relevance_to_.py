"""add_supports_temporal_relevance_to_source

Revision ID: 8be89aca78a6
Revises: 7312a103766e
Create Date: 2025-10-28 14:12:34.969190

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8be89aca78a6'
down_revision = '7312a103766e'
branch_labels = None
depends_on = None


def upgrade():
    # Add supports_temporal_relevance column to source table
    op.add_column(
        'source',
        sa.Column('supports_temporal_relevance', sa.Boolean(), nullable=False, server_default='true')
    )

    # Set False for code repository sources that don't have file-level timestamps
    op.execute(
        "UPDATE source SET supports_temporal_relevance = false "
        "WHERE short_name IN ('github', 'gitlab', 'bitbucket')"
    )


def downgrade():
    # Remove supports_temporal_relevance column from source table
    op.drop_column('source', 'supports_temporal_relevance')
