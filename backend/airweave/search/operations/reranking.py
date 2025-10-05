"""Reranking operation.

Uses LLM (Cohere) to reorder search results based on semantic relevance to
the query. Improves ranking quality by considering full text understanding
beyond just vector similarity.
"""

from typing import Any, List

from airweave.search.context import SearchContext
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class Reranking(SearchOperation):
    """Rerank search results using LLM for improved relevance.

    Configuration (from init):
        - provider: BaseProvider - LLM provider for reranking

    Input (from context):
        - query: str - Original user query

    Input (from state):
        - raw_results: List[dict] - Search results from retrieval

    Output (to state):
        - final_results: List[dict] - Reranked and limited results
    """

    def __init__(self, provider: BaseProvider) -> None:
        """Initialize with LLM provider.

        Args:
            provider: LLM provider for reranking (guaranteed by factory)
        """
        self.provider = provider

    def depends_on(self) -> List[str]:
        """Depends on retrieval to have results to rerank."""
        return ["Retrieval"]

    async def execute(self, context: SearchContext, state: dict[str, Any]) -> None:
        """Rerank results using Cohere API.

        Args:
            context: Search context with original query
            state: State dictionary to read raw_results and write final_results

        Process:
            1. Read raw_results from state
            2. If no results, set final_results to empty and return
            3. Prepare candidates (limit to max_candidates)
            4. Format as YAML for best LLM performance
            5. Call Cohere Rerank API with query and documents
            6. Map reranked indices back to original results
            7. Apply final limit and write to state["final_results"]
        """
        # TODO: Implement Cohere-based reranking
        # - Check for COHERE_API_KEY
        # - Prepare top N candidates (e.g., 100)
        # - Format each result as YAML with Title/Source/Content
        # - Call Cohere AsyncClientV2.rerank()
        # - Map returned indices back to original results
        # - Handle graceful degradation if API fails
        results = state.get("raw_results", [])
        state["final_results"] = results[: context.retrieval.limit] if results else []
