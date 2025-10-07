"""add_missing_column_comments

Revision ID: c3edd3ce34ce
Revises: ed3f647344ef
Create Date: 2025-10-07 16:18:36.830577

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3edd3ce34ce'
down_revision = 'ed3f647344ef'
branch_labels = None
depends_on = None


def upgrade():
    """Add missing column comments to search_queries table."""

    # Add comments to search_queries columns
    op.alter_column('search_queries', 'is_streaming',
                    existing_type=sa.Boolean(),
                    comment='Whether this was a streaming search',
                    existing_nullable=False)

    op.alter_column('search_queries', 'retrieval_strategy',
                    existing_type=sa.String(length=20),
                    comment="Retrieval strategy: 'hybrid', 'neural', 'keyword'",
                    existing_nullable=False)

    op.alter_column('search_queries', 'temporal_relevance',
                    existing_type=sa.Float(),
                    comment='Temporal relevance weight (0.0 to 1.0)',
                    existing_nullable=False)

    op.alter_column('search_queries', 'filter',
                    existing_type=sa.JSON(),
                    comment='Qdrant filter applied (if any)',
                    existing_nullable=True)

    op.alter_column('search_queries', 'expand_query',
                    existing_type=sa.Boolean(),
                    comment='Whether query expansion was enabled',
                    existing_nullable=False)

    op.alter_column('search_queries', 'interpret_filters',
                    existing_type=sa.Boolean(),
                    comment='Whether query interpretation was enabled',
                    existing_nullable=False)

    op.alter_column('search_queries', 'rerank',
                    existing_type=sa.Boolean(),
                    comment='Whether LLM reranking was enabled',
                    existing_nullable=False)

    op.alter_column('search_queries', 'generate_answer',
                    existing_type=sa.Boolean(),
                    comment='Whether answer generation was enabled',
                    existing_nullable=False)


def downgrade():
    """Remove column comments."""

    # Remove comments from search_queries columns
    op.alter_column('search_queries', 'is_streaming',
                    existing_type=sa.Boolean(),
                    comment=None,
                    existing_nullable=False)

    op.alter_column('search_queries', 'retrieval_strategy',
                    existing_type=sa.String(length=20),
                    comment=None,
                    existing_nullable=False)

    op.alter_column('search_queries', 'temporal_relevance',
                    existing_type=sa.Float(),
                    comment=None,
                    existing_nullable=False)

    op.alter_column('search_queries', 'filter',
                    existing_type=sa.JSON(),
                    comment=None,
                    existing_nullable=True)

    op.alter_column('search_queries', 'expand_query',
                    existing_type=sa.Boolean(),
                    comment=None,
                    existing_nullable=False)

    op.alter_column('search_queries', 'interpret_filters',
                    existing_type=sa.Boolean(),
                    comment=None,
                    existing_nullable=False)

    op.alter_column('search_queries', 'rerank',
                    existing_type=sa.Boolean(),
                    comment=None,
                    existing_nullable=False)

    op.alter_column('search_queries', 'generate_answer',
                    existing_type=sa.Boolean(),
                    comment=None,
                    existing_nullable=False)
