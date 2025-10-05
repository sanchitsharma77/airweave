"""Query interpretation operation.

Uses LLM to interpret natural language queries and extract structured Qdrant filters.
Enables users to filter results using natural language without knowing filter syntax.
"""

from typing import Any, List

from airweave.search.context import SearchContext
from airweave.search.providers._base import BaseProvider

from ._base import SearchOperation


class QueryInterpretation(SearchOperation):
    """Extract structured Qdrant filters from natural language query.

    Configuration (from init):
        - provider: BaseProvider - LLM provider for extracting filters

    Input (from context):
        - query: str - Original user query

    Input (from state):
        - expanded_queries: List[str] - Query variations (if expansion enabled)

    Output (to state):
        - extracted_filter: dict - Qdrant filter extracted from query
    """

    def __init__(self, provider: BaseProvider) -> None:
        """Initialize with LLM provider.

        Args:
            provider: LLM provider for structured output (guaranteed by factory)
        """
        self.provider = provider

    def depends_on(self) -> List[str]:
        """Depends on query expansion to get all query variations."""
        return ["QueryExpansion"]

    async def execute(self, context: SearchContext, state: dict[str, Any]) -> None:
        """Extract filters from query using LLM.

        Args:
            context: Search context with original query
            state: State dictionary to read expansions and write filter

        Process:
            1. Read query and optionally expanded_queries from state
            2. Discover available fields from collection's entity definitions
            3. Use LLM to extract structured filters (source_name, time ranges, etc.)
            4. Validate extracted filters against available fields
            5. Write validated filter dict to state["extracted_filter"]
        """
        # TODO: Implement LLM-based query interpretation
        # - Use Groq client with structured outputs
        # - Discover available fields from DB
        # - Extract filters with confidence scoring
        # - Map field names to Qdrant payload paths
        # - Validate against collection schema
        pass
