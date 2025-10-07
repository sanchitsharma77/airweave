"""Update search_queries table for refactored search module

Revision ID: d4e5f6g7h8i9
Revises: c60291fb2129
Create Date: 2025-10-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6g7h8i9'
down_revision = 'c60291fb2129'
branch_labels = None
depends_on = None


def upgrade():
    """Update search_queries table to match new search module schema.

    Changes:
    - Remove: search_type, response_type, score_threshold, recency_bias, search_method, status
    - Remove: query_expansion_enabled, reranking_enabled, query_interpretation_enabled
    - Add: is_streaming, retrieval_strategy, temporal_relevance
    - Add: expand_query, interpret_filters, rerank, generate_answer
    - Update indexes
    """
    # Drop old indexes
    op.drop_index('ix_search_queries_status', table_name='search_queries')
    op.drop_index('ix_search_queries_search_type', table_name='search_queries')

    # Add new columns with defaults for existing rows
    op.add_column('search_queries', sa.Column('is_streaming', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('search_queries', sa.Column('retrieval_strategy', sa.String(length=20), nullable=True))
    op.add_column('search_queries', sa.Column('temporal_relevance', sa.Float(), nullable=True))
    op.add_column('search_queries', sa.Column('expand_query', sa.Boolean(), nullable=True))
    op.add_column('search_queries', sa.Column('interpret_filters', sa.Boolean(), nullable=True))
    op.add_column('search_queries', sa.Column('rerank', sa.Boolean(), nullable=True))
    op.add_column('search_queries', sa.Column('generate_answer', sa.Boolean(), nullable=True))

    # Migrate data from old columns to new columns where possible
    # Map old search_method -> retrieval_strategy (values are the same: hybrid, neural, keyword)
    op.execute("""
        UPDATE search_queries
        SET retrieval_strategy = search_method
        WHERE search_method IS NOT NULL
    """)

    # Map old recency_bias -> temporal_relevance (same meaning, different name)
    op.execute("""
        UPDATE search_queries
        SET temporal_relevance = recency_bias
        WHERE recency_bias IS NOT NULL
    """)

    # Map old query_expansion_enabled -> expand_query
    op.execute("""
        UPDATE search_queries
        SET expand_query = query_expansion_enabled
        WHERE query_expansion_enabled IS NOT NULL
    """)

    # Map old reranking_enabled -> rerank
    op.execute("""
        UPDATE search_queries
        SET rerank = reranking_enabled
        WHERE reranking_enabled IS NOT NULL
    """)

    # Map old query_interpretation_enabled -> interpret_filters
    op.execute("""
        UPDATE search_queries
        SET interpret_filters = query_interpretation_enabled
        WHERE query_interpretation_enabled IS NOT NULL
    """)

    # Map old response_type to generate_answer
    # response_type='completion' -> generate_answer=true, response_type='raw' -> generate_answer=false
    op.execute("""
        UPDATE search_queries
        SET generate_answer = CASE
            WHEN response_type = 'completion' THEN true
            WHEN response_type = 'raw' THEN false
            ELSE NULL
        END
        WHERE response_type IS NOT NULL
    """)

    # Drop old columns
    op.drop_column('search_queries', 'search_type')
    op.drop_column('search_queries', 'response_type')
    op.drop_column('search_queries', 'score_threshold')
    op.drop_column('search_queries', 'recency_bias')
    op.drop_column('search_queries', 'search_method')
    op.drop_column('search_queries', 'status')
    op.drop_column('search_queries', 'query_expansion_enabled')
    op.drop_column('search_queries', 'reranking_enabled')
    op.drop_column('search_queries', 'query_interpretation_enabled')

    # Create new indexes
    op.create_index('ix_search_queries_is_streaming', 'search_queries', ['is_streaming'])
    op.create_index('ix_search_queries_retrieval_strategy', 'search_queries', ['retrieval_strategy'])


def downgrade():
    """Restore old schema."""
    # Drop new indexes
    op.drop_index('ix_search_queries_retrieval_strategy', table_name='search_queries')
    op.drop_index('ix_search_queries_is_streaming', table_name='search_queries')

    # Add old columns back
    op.add_column('search_queries', sa.Column('search_type', sa.String(length=20), nullable=True))
    op.add_column('search_queries', sa.Column('response_type', sa.String(length=20), nullable=True))
    op.add_column('search_queries', sa.Column('score_threshold', sa.Float(), nullable=True))
    op.add_column('search_queries', sa.Column('recency_bias', sa.Float(), nullable=True))
    op.add_column('search_queries', sa.Column('search_method', sa.String(length=20), nullable=True))
    op.add_column('search_queries', sa.Column('status', sa.String(length=20), nullable=True))
    op.add_column('search_queries', sa.Column('query_expansion_enabled', sa.Boolean(), nullable=True))
    op.add_column('search_queries', sa.Column('reranking_enabled', sa.Boolean(), nullable=True))
    op.add_column('search_queries', sa.Column('query_interpretation_enabled', sa.Boolean(), nullable=True))

    # Migrate data back
    op.execute("""
        UPDATE search_queries
        SET search_method = retrieval_strategy
        WHERE retrieval_strategy IS NOT NULL
    """)

    op.execute("""
        UPDATE search_queries
        SET recency_bias = temporal_relevance
        WHERE temporal_relevance IS NOT NULL
    """)

    op.execute("""
        UPDATE search_queries
        SET query_expansion_enabled = expand_query
        WHERE expand_query IS NOT NULL
    """)

    op.execute("""
        UPDATE search_queries
        SET reranking_enabled = rerank
        WHERE rerank IS NOT NULL
    """)

    op.execute("""
        UPDATE search_queries
        SET query_interpretation_enabled = interpret_filters
        WHERE interpret_filters IS NOT NULL
    """)

    op.execute("""
        UPDATE search_queries
        SET response_type = CASE
            WHEN generate_answer = true THEN 'completion'
            WHEN generate_answer = false THEN 'raw'
            ELSE NULL
        END
        WHERE generate_answer IS NOT NULL
    """)

    # Set default values for required fields
    op.execute("UPDATE search_queries SET search_type = 'basic' WHERE search_type IS NULL")
    op.execute("UPDATE search_queries SET status = 'success' WHERE status IS NULL")

    # Make required columns non-nullable
    op.alter_column('search_queries', 'search_type', nullable=False)
    op.alter_column('search_queries', 'status', nullable=False)

    # Drop new columns
    op.drop_column('search_queries', 'is_streaming')
    op.drop_column('search_queries', 'retrieval_strategy')
    op.drop_column('search_queries', 'temporal_relevance')
    op.drop_column('search_queries', 'expand_query')
    op.drop_column('search_queries', 'interpret_filters')
    op.drop_column('search_queries', 'rerank')
    op.drop_column('search_queries', 'generate_answer')

    # Recreate old indexes
    op.create_index('ix_search_queries_status', 'search_queries', ['status'])
    op.create_index('ix_search_queries_search_type', 'search_queries', ['search_type'])
