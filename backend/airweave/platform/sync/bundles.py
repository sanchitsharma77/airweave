"""Composable bundles for sync operations.

Bundles are focused data containers that group related dependencies.
They enable:
- Decoupled construction via dedicated builders
- Reuse in non-sync contexts (webhooks, cleanup)
- Clear dependency boundaries for handlers

Bundle Hierarchy:
- SyncIdentity: Immutable identity (sync_id, collection_id, organization_id)
- InfraBundle: Core infrastructure (ctx, logger)
- SourceBundle: Source pipeline (source, cursor)
- DestinationBundle: Destination pipeline (destinations, entity_map)
- TrackingBundle: Progress tracking (entity_tracker, state_publisher, guard_rail)
- BatchConfig: Micro-batching settings (batch_size, latency, etc.)

SyncContext holds these bundles directly as first-class fields (depth 1).
For execution behavior (handlers, destinations, cursor), see SyncExecutionConfig.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional
from uuid import UUID

if TYPE_CHECKING:
    from airweave.api.context import ApiContext
    from airweave.core.guard_rail_service import GuardRailService
    from airweave.core.logging import ContextualLogger
    from airweave.platform.destinations._base import BaseDestination
    from airweave.platform.entities._base import BaseEntity
    from airweave.platform.sources._base import BaseSource
    from airweave.platform.sync.cursor import SyncCursor
    from airweave.platform.sync.pipeline.entity_tracker import EntityTracker
    from airweave.platform.sync.state_publisher import SyncStatePublisher


@dataclass(frozen=True)
class SyncIdentity:
    """Immutable identity for any entity operation.

    Can be constructed for sync, webhooks, cleanup - anything that operates
    on entities within a sync's scope.

    Attributes:
        sync_id: The sync configuration ID
        collection_id: The target collection ID
        organization_id: The owning organization ID
        sync_job_id: Optional job ID (None for non-sync operations like cleanup)
    """

    sync_id: UUID
    collection_id: UUID
    organization_id: UUID
    sync_job_id: Optional[UUID] = None

    def __repr__(self) -> str:
        """Compact representation for logging."""
        job_part = f", job={self.sync_job_id}" if self.sync_job_id else ""
        return f"SyncIdentity(sync={self.sync_id}{job_part})"


@dataclass
class InfraBundle:
    """Core infrastructure needed by all operations.

    Attributes:
        ctx: API context for auth and audit
        logger: Contextual logger with operation metadata
    """

    ctx: "ApiContext"
    logger: "ContextualLogger"


@dataclass
class SourceBundle:
    """Everything needed to run the source pipeline.

    Attributes:
        source: Configured source instance
        cursor: Sync cursor for incremental syncs
    """

    source: "BaseSource"
    cursor: "SyncCursor"


@dataclass
class DestinationBundle:
    """Everything needed for destination operations.

    Attributes:
        destinations: List of configured destination instances
        entity_map: Mapping of entity class to entity_definition_id
        has_keyword_index: Whether any destination supports keyword indexing
    """

    destinations: List["BaseDestination"]
    entity_map: Dict[type["BaseEntity"], UUID]
    has_keyword_index: bool = False


@dataclass
class TrackingBundle:
    """Progress tracking - only needed during active sync.

    Attributes:
        entity_tracker: Centralized entity state tracker
        state_publisher: Publishes progress to Redis pubsub
        guard_rail: Rate limiting service (optional)
    """

    entity_tracker: "EntityTracker"
    state_publisher: "SyncStatePublisher"
    guard_rail: Optional["GuardRailService"] = None


@dataclass
class BatchConfig:
    """Micro-batching configuration for entity processing.

    Controls HOW entities are processed (batching behavior).
    For WHAT to process (handlers, destinations), see SyncExecutionConfig.

    Attributes:
        should_batch: Whether to use micro-batched pipeline
        batch_size: Max entities per micro-batch
        max_batch_latency_ms: Max time before flushing partial batch
        force_full_sync: Whether to force full sync (triggers orphan cleanup)
    """

    should_batch: bool = True
    batch_size: int = 64
    max_batch_latency_ms: int = 200
    force_full_sync: bool = False
