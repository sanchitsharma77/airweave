"""Unit tests for backwards compatibility between legacy and new search schemas."""

import pytest

from airweave.schemas.search import SearchRequest
from airweave.schemas.search_legacy import (
    LegacySearchRequest,
    QueryExpansionStrategy,
    ResponseType,
)
from airweave.search.legacy_adapter import (
    convert_legacy_request_to_new,
    convert_new_response_to_legacy,
)


class TestLegacySearchCompatibility:
    """Test suite for legacy search schema backwards compatibility."""

    def test_convert_legacy_to_new_basic(self):
        """Test basic conversion from legacy to new format."""
        legacy_request = LegacySearchRequest(
            query="test query",
            limit=50,
            offset=10,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert isinstance(new_request, SearchRequest)
        assert new_request.query == "test query"
        assert new_request.limit == 50
        assert new_request.offset == 10

    def test_convert_response_type_to_generate_answer(self):
        """Test that response_type='completion' maps to generate_answer=True."""
        legacy_request = LegacySearchRequest(
            query="test",
            response_type=ResponseType.COMPLETION,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.generate_answer is True

        # Test RAW maps to False
        legacy_request = LegacySearchRequest(
            query="test",
            response_type=ResponseType.RAW,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.generate_answer is False

    def test_convert_search_method_to_retrieval_strategy(self):
        """Test that search_method maps to retrieval_strategy."""
        legacy_request = LegacySearchRequest(
            query="test",
            search_method="hybrid",
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.retrieval_strategy == "hybrid"

    def test_convert_recency_bias_to_temporal_relevance(self):
        """Test that recency_bias maps to temporal_relevance."""
        legacy_request = LegacySearchRequest(
            query="test",
            recency_bias=0.5,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.temporal_relevance == 0.5

    def test_convert_expansion_strategy_to_expand_query(self):
        """Test that expansion_strategy maps to expand_query boolean."""
        # NO_EXPANSION should map to False
        legacy_request = LegacySearchRequest(
            query="test",
            expansion_strategy=QueryExpansionStrategy.NO_EXPANSION,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.expand_query is False

        # AUTO should map to True
        legacy_request = LegacySearchRequest(
            query="test",
            expansion_strategy=QueryExpansionStrategy.AUTO,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.expand_query is True

        # LLM should map to True
        legacy_request = LegacySearchRequest(
            query="test",
            expansion_strategy=QueryExpansionStrategy.LLM,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.expand_query is True

    def test_convert_enable_reranking_to_rerank(self):
        """Test that enable_reranking maps to rerank."""
        legacy_request = LegacySearchRequest(
            query="test",
            enable_reranking=True,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.rerank is True

    def test_convert_enable_query_interpretation_to_interpret_filters(self):
        """Test that enable_query_interpretation maps to interpret_filters."""
        legacy_request = LegacySearchRequest(
            query="test",
            enable_query_interpretation=True,
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.interpret_filters is True

    def test_convert_all_legacy_fields_together(self):
        """Test converting a legacy request with all fields set."""
        legacy_request = LegacySearchRequest(
            query="test query",
            response_type=ResponseType.COMPLETION,
            search_method="neural",
            recency_bias=0.7,
            expansion_strategy=QueryExpansionStrategy.LLM,
            enable_reranking=True,
            enable_query_interpretation=True,
            limit=100,
            offset=20,
            score_threshold=0.8,  # This field is deprecated and should be ignored
        )

        new_request = convert_legacy_request_to_new(legacy_request)

        assert new_request.query == "test query"
        assert new_request.generate_answer is True
        assert new_request.retrieval_strategy == "neural"
        assert new_request.temporal_relevance == 0.7
        assert new_request.expand_query is True
        assert new_request.rerank is True
        assert new_request.interpret_filters is True
        assert new_request.limit == 100
        assert new_request.offset == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
