"""Base handler protocol for action execution.

Handlers receive resolved actions and persist them to their destination.
All handlers are called concurrently by the ActionDispatcher.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

from airweave.platform.sync.actions.types import (
    ActionBatch,
    DeleteAction,
    InsertAction,
    UpdateAction,
)

if TYPE_CHECKING:
    from airweave.platform.sync.context import SyncContext


class ActionHandler(ABC):
    """Protocol for action handlers.

    Handlers receive resolved actions and persist them to their destination.
    All handlers are called concurrently for each batch by the ActionDispatcher.

    Contract:
    - Handlers MUST be idempotent (safe to retry on failure)
    - Handlers MUST raise SyncFailureError for non-recoverable errors
    - Handlers receive actions AFTER chunking/embedding (for vector handlers)
    - If handle_batch is overridden, individual handlers may not be called

    Execution Order:
    1. All handlers receive the same ActionBatch concurrently
    2. If ANY handler fails, SyncFailureError bubbles up (all-or-nothing)
    3. PostgresMetadataHandler runs AFTER other handlers succeed
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Handler name for logging and debugging."""
        pass

    @abstractmethod
    async def handle_inserts(
        self,
        actions: List[InsertAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle insert actions.

        Args:
            actions: List of InsertAction objects with chunk_entities populated
            sync_context: Sync context with logger, destinations, etc.

        Raises:
            SyncFailureError: If handler cannot complete the inserts
        """
        pass

    @abstractmethod
    async def handle_updates(
        self,
        actions: List[UpdateAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle update actions.

        For vector handlers: clear old chunks, insert new chunks.
        For metadata handlers: update hash in database.

        Args:
            actions: List of UpdateAction objects with chunk_entities populated
            sync_context: Sync context

        Raises:
            SyncFailureError: If handler cannot complete the updates
        """
        pass

    @abstractmethod
    async def handle_deletes(
        self,
        actions: List[DeleteAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle delete actions.

        Args:
            actions: List of DeleteAction objects
            sync_context: Sync context

        Raises:
            SyncFailureError: If handler cannot complete the deletes
        """
        pass

    async def handle_batch(
        self,
        batch: ActionBatch,
        sync_context: "SyncContext",
    ) -> None:
        """Handle a full action batch.

        Default implementation calls individual handlers in order:
        1. handle_deletes (cleanup first)
        2. handle_updates (may need to clear then insert)
        3. handle_inserts (add new)

        Override this method for custom batch handling logic.

        Args:
            batch: ActionBatch with all resolved and processed actions
            sync_context: Sync context

        Raises:
            SyncFailureError: If any operation fails
        """
        if batch.deletes:
            await self.handle_deletes(batch.deletes, sync_context)
        if batch.updates:
            await self.handle_updates(batch.updates, sync_context)
        if batch.inserts:
            await self.handle_inserts(batch.inserts, sync_context)

    async def handle_orphan_cleanup(  # noqa: B027
        self,
        orphan_entity_ids: List[str],
        sync_context: "SyncContext",
    ) -> None:
        """Handle orphaned entity cleanup at sync end.

        Called for entities that exist in the database but were not encountered
        during the current sync run (indicating they were deleted at source).

        Override this method if the handler stores data by entity_id that needs
        to be cleaned up when entities are orphaned.

        Args:
            orphan_entity_ids: List of entity IDs that are orphaned
            sync_context: Sync context

        Raises:
            SyncFailureError: If cleanup fails
        """
        # Default: no-op. Override in handlers that need cleanup.
        pass
