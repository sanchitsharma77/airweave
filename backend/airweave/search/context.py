"""Search context."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
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


class SearchContext(BaseModel):
    """Search context."""

    model_config = {"arbitrary_types_allowed": True}

    request_id: str = Field()
    collection_id: UUID = Field()
    readable_collection_id: str = Field()
    stream: bool = Field()

    query: str = Field()

    query_expansion: Optional[QueryExpansion] = Field()
    query_interpretation: Optional[QueryInterpretation] = Field()
    embed_query: EmbedQuery = Field()
    user_filter: Optional[UserFilter] = Field()
    temporal_relevance: Optional[TemporalRelevance] = Field()
    retrieval: Retrieval = Field()
    reranking: Optional[Reranking] = Field()
    generate_answer: Optional[GenerateAnswer] = Field()
