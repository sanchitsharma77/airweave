from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List

from airweave.api.context import ApiContext
from airweave.search.context import SearchContext

if TYPE_CHECKING:
    from airweave.search.emitter import EventEmitter


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
        emitter: "EventEmitter",
    ) -> None:
        """Execute the operation."""
        pass
