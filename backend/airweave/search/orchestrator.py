"""Search orchestrator."""

from typing import Any

from airweave.schemas.search import SearchResponse
from airweave.search.context import SearchContext


class SearchOrchestrator:
    """Search orchestrator."""

    def run(self, context: SearchContext) -> SearchResponse:
        """Run the orchestrator."""
        state: dict[str, Any] = {}


orchestrator = SearchOrchestrator()
