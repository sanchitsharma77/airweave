"""Answer generation operation.

Generates natural language answers from search results using LLM.
Synthesizes information from multiple results into a coherent response
with inline citations.
"""

from typing import Any, List

from airweave.search.context import SearchContext
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class GenerateAnswer(SearchOperation):
    """Generate AI completion from search results.

    Configuration (from init):
        - provider: BaseProvider - LLM provider for text generation

    Input (from context):
        - query: str - Original user query

    Input (from state):
        - final_results: List[dict] - Reranked results (if reranking enabled)
        - raw_results: List[dict] - Fallback if reranking disabled

    Output (to state):
        - completion: str - Generated natural language answer with citations
    """

    def __init__(self, provider: BaseProvider) -> None:
        """Initialize with LLM provider.

        Args:
            provider: LLM provider for text generation (guaranteed by factory)
        """
        self.provider = provider

    def depends_on(self) -> List[str]:
        """Depends on retrieval and reranking to have results."""
        return ["Retrieval", "Reranking"]

    async def execute(self, context: SearchContext, state: dict[str, Any]) -> None:
        """Generate natural language answer from results.

        Args:
            context: Search context with original query
            state: State dictionary to read results and write completion

        Process:
            1. Read final_results if available, else raw_results
            2. If no results, return "No results found"
            3. Format results as context with entity IDs for citations
            4. Build system prompt with context and user prompt with query
            5. Call Groq LLM (streaming if request_id present)
            6. Generate completion with inline [[entity_id]] citations
            7. Write answer to state["completion"]
        """
        # TODO: Implement completion generation
        # - Check for GROQ_API_KEY
        # - Get results (prefer final_results, fallback to raw_results)
        # - Format results with entity IDs and content
        # - Budget tokens to fit ~120k context window
        # - Use Groq AsyncClient with chat completions
        # - Stream chunks if in streaming mode
        # - Write final completion to state
        results = state.get("final_results", state.get("raw_results", []))
        if not results:
            state["completion"] = "No results found for your query."
        else:
            state["completion"] = None  # Placeholder until implemented
