"""User filter operation.

Applies user-provided Qdrant filters and merges them with filters extracted
from query interpretation. Responsible for creating the final filter that
will be passed to the retrieval operation.
"""

from typing import Any, List

from qdrant_client.http.models import Filter as QdrantFilter

from airweave.search.context import SearchContext

from ._base import SearchOperation


class UserFilter(SearchOperation):
    """Merge user-provided filter with extracted filters.

    Configuration (from init):
        - filter: QdrantFilter - User-provided Qdrant filter from search request

    Input (from state):
        - extracted_filter: dict - Filter extracted by query interpretation (optional)

    Output (to state):
        - filter: dict - Final merged Qdrant filter for retrieval
    """

    def __init__(self, filter: QdrantFilter) -> None:
        """Initialize with user-provided filter.

        Args:
            filter: Qdrant filter for metadata-based filtering
        """
        self.filter = filter

    def depends_on(self) -> List[str]:
        """Depends on query interpretation to get extracted filter for merging."""
        return ["QueryInterpretation"]

    async def execute(self, context: SearchContext, state: dict[str, Any]) -> None:
        """Merge user filter with extracted filter.

        Args:
            context: Search context
            state: State dictionary to read extracted_filter and write final filter

        Process:
            1. Read extracted_filter from state (if query interpretation ran)
            2. Normalize user filter field names to Qdrant payload paths
            3. Merge user filter and extracted filter using AND semantics
            4. Write final merged filter to state["filter"]
        """
        # TODO: Implement filter merging
        # - Map user filter keys to Qdrant paths
        #   (e.g., source_name -> airweave_system_metadata.source_name)
        # - Get extracted_filter from state if present
        # - Merge filters: concatenate "must" and "must_not",
        #   combine "should" with minimum_should_match
        # - Handle edge cases: both None, one None, both present
        state["filter"] = self.filter.model_dump(exclude_none=True) if self.filter else None
