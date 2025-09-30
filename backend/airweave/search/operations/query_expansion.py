"""Expand the user's query."""

from typing import Any, List

from airweave.search.context import SearchContext

from ._base import SearchOperation


class QueryExpansion(SearchOperation):
    """Expand the user's query."""

    def depends_on(self) -> List[str]:
        """List of operation names this operation depends on."""
        return []

    def execute(self, context: SearchContext, state: dict[str, Any]) -> None:
        """Execute the operation."""
        state["expanded_queries"] = []
