"""Protocol for handler-compatible contexts."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from airweave.api.context import ApiContext
    from airweave.core.logging import ContextualLogger


@runtime_checkable
class HandlerContext(Protocol):
    """Minimal interface that handlers can work with.

    SyncContext and CleanupContext both implement this protocol.
    Handlers accept this protocol, enabling reuse across different
    operation types (sync, cleanup, webhooks).

    Properties:
        sync_id: Sync ID for scoping operations
        organization_id: Organization ID for access control
        logger: Logger for handler operations
        ctx: API context for CRUD operations
    """

    @property
    def sync_id(self) -> UUID:
        """Sync ID for scoping operations."""
        ...

    @property
    def organization_id(self) -> UUID:
        """Organization ID for access control."""
        ...

    @property
    def logger(self) -> "ContextualLogger":
        """Logger for handler operations."""
        ...

    @property
    def ctx(self) -> "ApiContext":
        """API context for CRUD operations."""
        ...
