"""Search schemas for Airweave's search API."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from qdrant_client.http.models import Filter as QdrantFilter


class RetrievalStrategy(str, Enum):
    """Retrieval strategies for search."""

    HYBRID = "hybrid"
    NEURAL = "neural"
    KEYWORD = "keyword"


class SearchRequest(BaseModel):
    """Search request schema."""

    query: str = Field(description="The search query text")

    retrieval_strategy: Optional[RetrievalStrategy] = Field(
        description="The retrieval strategy to use"
    )
    filter: Optional[QdrantFilter] = Field(
        description="Qdrant native filter for metadata-based filtering"
    )
    offset: Optional[int] = Field(description="Number of results to skip")
    limit: Optional[int] = Field(description="Maximum number of results to return")

    temporal_relevance: Optional[float] = Field(
        description=(
            "Weight recent content higher than older content; "
            "0 = no recency effect, 1 = only recent items matter"
        )
    )

    expand_query: Optional[bool] = Field(
        description="Generate a few query variations to improve recall"
    )
    rerank: Optional[bool] = Field(
        description=(
            "Reorder the top candidate results for improved relevance. "
            "Max number of results that can be reranked is capped to around 1000."
        )
    )
    interpret_filters: Optional[bool] = Field(
        description="Extract structured filters from natural-language query"
    )

    generate_answer: Optional[bool] = Field(
        description="Generate a natural-language answer to the query"
    )


class SearchDefaults(BaseModel):
    """Default values for search parameters loaded from YAML."""

    retrieval_strategy: RetrievalStrategy
    offset: int
    limit: int
    temporal_relevance: float
    expand_query: bool
    interpret_filters: bool
    rerank: bool
    generate_answer: bool


class SearchResponse(BaseModel):
    """Comprehensive search response containing results and metadata."""

    results: list[dict] = Field(
        description=(
            "Array of search result objects containing the found documents, records, "
            "or data entities."
        )
    )
    completion: Optional[str] = Field(
        description=(
            "AI-generated natural language answer when response_type is 'completion'. This "
            "provides natural language answers to your query based on the content found "
            "across your connected data sources."
        )
    )
