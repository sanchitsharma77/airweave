from abc import ABC, abstractmethod
from typing import List

from airweave.search.context import SearchContext


class SearchOperation(ABC):
    """Base class for all search operations."""

    @classmethod
    @abstractmethod
    def depends_on(cls) -> List[str]:
        """List of operation names this operation depends on."""
        pass

    @abstractmethod
    def execute(self, context: SearchContext) -> None:
        """Execute the operation."""
        pass
