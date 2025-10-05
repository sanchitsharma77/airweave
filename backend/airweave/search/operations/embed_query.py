"""Query embedding operation.

Converts text queries into vector embeddings for similarity search.
Generates dense neural embeddings and/or sparse BM25 embeddings based on
the retrieval strategy (hybrid, neural, or keyword).
"""

from typing import Any, List

from airweave.schemas.search import RetrievalStrategy
from airweave.search.context import SearchContext
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class EmbedQuery(SearchOperation):
    """Generate vector embeddings for queries.

    Configuration (from init):
        - strategy: RetrievalStrategy - Determines which embeddings to generate
        - provider: BaseProvider - LLM provider for generating embeddings

    Input (from context):
        - query: str - Original user query

    Input (from state):
        - expanded_queries: List[str] - Query variations (if expansion enabled)

    Output (to state):
        - embeddings: List[List[float]] - Dense neural embeddings
        - sparse_embeddings: List[SparseEmbedding] - Sparse BM25 embeddings (if hybrid/keyword)
    """

    def __init__(self, strategy: RetrievalStrategy, provider: BaseProvider) -> None:
        """Initialize with retrieval strategy and provider.

        Args:
            strategy: Retrieval strategy that determines which embeddings to generate
            provider: LLM provider for embeddings (guaranteed by factory)
        """
        self.strategy = strategy
        self.provider = provider

    def depends_on(self) -> List[str]:
        """Depends on query expansion to get all queries to embed."""
        return ["QueryExpansion"]

    async def execute(self, context: SearchContext, state: dict[str, Any]) -> None:
        """Generate embeddings for queries.

        Args:
            context: Search context with original query
            state: State dictionary to read expansions and write embeddings

        Process:
            1. Determine queries to embed (expanded_queries if available, else query)
            2. Select embedding model (OpenAI if API key, else local)
            3. Generate dense embeddings if strategy is hybrid or neural
            4. Generate sparse BM25 embeddings if strategy is hybrid or keyword
            5. Write embeddings lists to state
        """
        # TODO: Implement embedding generation
        # - Check for expanded_queries in state
        # - Select embedding model based on API key availability
        # - Generate dense embeddings with OpenAIText2Vec or LocalText2Vec
        # - Generate sparse embeddings with BM25Text2Vec
        # - Handle batch embedding for multiple queries
        state["embeddings"] = []
        state["sparse_embeddings"] = []
