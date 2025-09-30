"""Search factory."""

from uuid import UUID

from fastapi import HTTPException

from airweave.schemas.search import SearchDefaults, SearchRequest
from airweave.search.context import SearchContext
from airweave.search.helpers import search_helpers
from airweave.search.operations import (
    EmbedQuery,
    GenerateAnswer,
    QueryExpansion,
    QueryInterpretation,
    Reranking,
    Retrieval,
    TemporalRelevance,
    UserFilter,
)

defaults = SearchDefaults(**search_helpers.load_defaults())

# TODO: LLM PROVIDER FALLBACK ORDER
# TODO: define default models per provider in YAML


class SearchFactory:
    """Create search context."""

    def build(
        self,
        request_id: str,
        collection_id: UUID,
        search_request: SearchRequest,
        stream: bool,
    ) -> SearchContext:
        """Build SearchContext from request with validated YAML defaults."""
        if not search_request.query or not search_request.query.strip():
            raise ValueError("Query is required")

        retrieval_strategy = (
            search_request.retrieval_strategy
            if search_request.retrieval_strategy is not None
            else defaults.retrieval_strategy
        )

        offset = search_request.offset if search_request.offset is not None else defaults.offset
        limit = search_request.limit if search_request.limit is not None else defaults.limit
        # Validate numeric ranges
        if offset < 0:
            raise HTTPException(status_code=422, detail="offset must be >= 0")
        if limit < 1:
            raise HTTPException(status_code=422, detail="limit must be >= 1")

        expand_query = (
            search_request.expand_query
            if search_request.expand_query is not None
            else defaults.expand_query
        )
        interpret_filters = (
            search_request.interpret_filters
            if search_request.interpret_filters is not None
            else defaults.interpret_filters
        )
        rerank = search_request.rerank if search_request.rerank is not None else defaults.rerank
        generate_answer = (
            search_request.generate_answer
            if search_request.generate_answer is not None
            else defaults.generate_answer
        )

        temporal_value = (
            search_request.temporal_relevance
            if search_request.temporal_relevance is not None
            else defaults.temporal_relevance
        )

        # Validate temporal_relevance range
        if not (0 <= temporal_value <= 1):
            raise HTTPException(
                status_code=422, detail="temporal_relevance must be between 0 and 1"
            )

        return SearchContext(
            request_id=request_id,
            collection_id=collection_id,
            stream=stream,
            query=search_request.query,
            retrieval_strategy=retrieval_strategy,
            offset=offset,
            limit=limit,
            query_expansion=QueryExpansion() if expand_query else None,
            query_interpretation=QueryInterpretation() if interpret_filters else None,
            embed_query=EmbedQuery(),
            temporal_relevance=TemporalRelevance() if temporal_value > 0 else None,
            user_filter=UserFilter() if search_request.filter else None,
            retrieval=Retrieval(),
            reranking=Reranking() if rerank else None,
            generate_answer=GenerateAnswer() if generate_answer else None,
        )


factory = SearchFactory()
