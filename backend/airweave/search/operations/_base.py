from abc import ABC, abstractmethod
from typing import Any, List

from airweave.api.context import ApiContext
from airweave.search.context import SearchContext


class SearchOperation(ABC):
    """Base class for all search operations."""

    @abstractmethod
    def depends_on(self) -> List[str]:
        """List of operation names this operation depends on."""
        pass

    @abstractmethod
    async def execute(
        self,
        context: SearchContext,
        state: dict[str, Any],
        ctx: ApiContext,
    ) -> None:
        """Execute the operation."""
        pass
