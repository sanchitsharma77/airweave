"""Base class for search operations.

This module defines the minimal interface that all search operations
must implement. We use a lightweight abstract base class to ensure
consistency while avoiding over-engineering.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class SearchOperation(ABC):
    """Base class for all search operations.

    Each operation is a self-contained unit that:
    - Knows its configuration and defaults
    - Declares its dependencies on other operations
    - Executes its logic by modifying the context
    - Can be optional (failure doesn't stop the pipeline)

    The context is a simple dictionary that flows through all operations,
    accumulating data as each operation executes.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this operation.

        This name is used for:
        - Dependency resolution
        - Logging and debugging
        - Timing measurements
        - Error reporting

        Returns:
            str: Unique operation name
        """
        pass

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> None:
        """Execute the operation.

        This method performs the actual work of the operation.
        It should:
        - Read inputs from the context
        - Perform its processing
        - Write outputs back to the context
        - Log important events via context["logger"]

        The context typically contains:
        - query: The search query (possibly modified by previous ops)
        - config: The SearchConfig object
        - db: Database session
        - logger: Contextual logger for this request
        - expanded_queries: List of expanded queries (if expansion ran)
        - embeddings: Query embeddings (if embedding ran)
        - filter: Qdrant filter (if filter generation ran)
        - raw_results: Initial search results
        - final_results: Processed/reranked results
        - completion: AI-generated completion
        - timings: Dict of operation timings
        - errors: List of non-fatal errors

        Args:
            context: Mutable context dictionary

        Raises:
            Exception: If operation fails and is not optional
        """
        pass

    @property
    def depends_on(self) -> List[str]:
        """List of operation names this operation depends on.

        The executor uses this to determine execution order.
        Operations can only run after all their dependencies
        have completed successfully.

        Returns:
            List[str]: Names of required operations
        """
        return []

    @property
    def optional(self) -> bool:
        """Whether this operation is optional.

        Optional operations can fail without stopping the entire
        pipeline. This is useful for operations that enhance
        results but aren't critical (e.g., auto filter generation).

        Returns:
            bool: True if operation can fail safely
        """
        return False

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"{self.__class__.__name__}(name='{self.name}', optional={self.optional})"
