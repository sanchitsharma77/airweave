"""Search context."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from airweave.schemas.search import RetrievalStrategy
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

    request_id: str = Field()
    collection_id: UUID = Field()
    stream: bool = Field()

    query: str = Field()
    retrieval_strategy: RetrievalStrategy = Field()
    offset: int = Field()
    limit: int = Field()

    query_expansion: Optional[QueryExpansion] = Field()
    query_interpretation: Optional[QueryInterpretation] = Field()
    embed_query: EmbedQuery = Field()
    temporal_relevance: Optional[TemporalRelevance] = Field()
    user_filter: Optional[UserFilter] = Field()
    retrieval: Retrieval = Field()
    reranking: Optional[Reranking] = Field()
    generate_answer: Optional[GenerateAnswer] = Field()
