"""Generic protocol for action handlers.

Single protocol using generics that both entity and AC handlers implement.
The protocol is parameterized by:
- T: The payload type (BaseEntity or MembershipTuple)
- B: The batch type (EntityActionBatch or ACActionBatch)

Type Aliases:
    EntityActionHandler = ActionHandler[BaseEntity, EntityActionBatch]
    ACActionHandler = ActionHandler[MembershipTuple, ACActionBatch]
"""

from typing import TYPE_CHECKING, Any, Generic, List, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from airweave.platform.contexts import SyncContext
    from airweave.platform.sync.actions.types import (
        DeleteAction,
        InsertAction,
        UpdateAction,
        UpsertAction,
    )

# Generic type variables
T = TypeVar("T")  # Payload type (BaseEntity or MembershipTuple)
B = TypeVar("B")  # Batch type (EntityActionBatch or ACActionBatch)


@runtime_checkable
class ActionHandler(Protocol, Generic[T, B]):
    """Generic protocol for action handlers.

    Handlers receive resolved actions and persist them to their destination.
    Parameterized by payload type T and batch type B.

    Contract:
    - Handlers MUST be idempotent (safe to retry on failure)
    - Handlers MUST raise SyncFailureError for non-recoverable errors

    Type Parameters:
        T: Payload type (e.g., BaseEntity, MembershipTuple)
        B: Batch type (e.g., EntityActionBatch, ACActionBatch)
    """

    @property
    def name(self) -> str:
        """Handler name for logging and debugging."""
        ...

    async def handle_batch(
        self,
        batch: B,
        sync_context: "SyncContext",
    ) -> Any:
        """Handle a full action batch (main entry point).

        Args:
            batch: Action batch of type B
            sync_context: Sync context

        Returns:
            Handler-specific return (None for entity, int for AC)

        Raises:
            SyncFailureError: If any operation fails
        """
        ...

    async def handle_inserts(
        self,
        actions: List["InsertAction[T]"],
        sync_context: "SyncContext",
    ) -> Any:
        """Handle insert actions.

        Args:
            actions: List of InsertAction[T] objects
            sync_context: Sync context

        Returns:
            Handler-specific return

        Raises:
            SyncFailureError: If inserts fail
        """
        ...

    async def handle_updates(
        self,
        actions: List["UpdateAction[T]"],
        sync_context: "SyncContext",
    ) -> Any:
        """Handle update actions.

        Args:
            actions: List of UpdateAction[T] objects
            sync_context: Sync context

        Returns:
            Handler-specific return

        Raises:
            SyncFailureError: If updates fail
        """
        ...

    async def handle_deletes(
        self,
        actions: List["DeleteAction[T]"],
        sync_context: "SyncContext",
    ) -> Any:
        """Handle delete actions.

        Args:
            actions: List of DeleteAction[T] objects
            sync_context: Sync context

        Returns:
            Handler-specific return

        Raises:
            SyncFailureError: If deletes fail
        """
        ...

    async def handle_upserts(
        self,
        actions: List["UpsertAction[T]"],
        sync_context: "SyncContext",
    ) -> Any:
        """Handle upsert actions.

        Args:
            actions: List of UpsertAction[T] objects
            sync_context: Sync context

        Returns:
            Handler-specific return

        Raises:
            SyncFailureError: If upserts fail
        """
        ...

    async def handle_orphan_cleanup(
        self,
        orphan_ids: List[str],
        sync_context: "SyncContext",
    ) -> Any:
        """Handle orphaned item cleanup at sync end.

        Args:
            orphan_ids: List of IDs that are orphaned
            sync_context: Sync context

        Returns:
            Handler-specific return

        Raises:
            SyncFailureError: If cleanup fails
        """
        ...


# =============================================================================
# Type Aliases for Convenience
# =============================================================================

# These are runtime type hints - they help with documentation and IDE support
# but Python's type system doesn't fully enforce generic protocol bounds

EntityActionHandler = ActionHandler["BaseEntity", "EntityActionBatch"]
"""Handler for entity sync - ActionHandler[BaseEntity, EntityActionBatch]"""

ACActionHandler = ActionHandler["MembershipTuple", "ACActionBatch"]
"""Handler for access control sync - ActionHandler[MembershipTuple, ACActionBatch]"""
