"""Module for sync context.

SyncContext is the main context container used during sync execution.
It holds bundles directly as first-class fields (depth 1 architecture).
"""

from dataclasses import dataclass
from typing import Optional

from airweave import schemas
from airweave.platform.sync.bundles import (
    BatchConfig,
    DestinationBundle,
    InfraBundle,
    SourceBundle,
    SyncIdentity,
    TrackingBundle,
)
from airweave.platform.sync.config import SyncExecutionConfig


@dataclass
class SyncContext:
    """Context container for a sync.

    Holds bundles directly as first-class fields. Each bundle represents
    a disjoint concern:

    - identity: Immutable IDs (sync, collection, organization, job)
    - infra: Core infrastructure (ctx, logger)
    - source: Source pipeline (source instance, cursor)
    - destinations: Destination pipeline (destinations, entity_map)
    - tracking: Progress tracking (entity_tracker, state_publisher, guard_rail)
    - batch_config: Micro-batching settings
    - execution_config: Handler/destination filtering

    Schema objects are kept at top level for convenience (sync, sync_job,
    collection, connection).
    """

    # Bundles (depth 1)
    identity: SyncIdentity
    infra: InfraBundle
    source: SourceBundle
    destinations: DestinationBundle
    tracking: TrackingBundle
    batch_config: BatchConfig

    # Schema objects (frequently accessed, kept at top level)
    sync: schemas.Sync
    sync_job: schemas.SyncJob
    collection: schemas.Collection
    connection: schemas.Connection

    # Optional execution config
    execution_config: Optional[SyncExecutionConfig] = None

    # -------------------------------------------------------------------------
    # Convenience Accessors (for common patterns)
    # -------------------------------------------------------------------------

    @property
    def logger(self):
        """Shortcut to infra.logger (used everywhere)."""
        return self.infra.logger

    @property
    def ctx(self):
        """Shortcut to infra.ctx (used everywhere)."""
        return self.infra.ctx

    @property
    def entity_map(self):
        """Shortcut to destinations.entity_map."""
        return self.destinations.entity_map

    @property
    def cursor(self):
        """Shortcut to source.cursor."""
        return self.source.cursor

    @property
    def source_instance(self):
        """Shortcut to source.source (the actual BaseSource instance)."""
        return self.source.source

    @property
    def destination_list(self):
        """Shortcut to destinations.destinations (the list of BaseDestination)."""
        return self.destinations.destinations

    @property
    def entity_tracker(self):
        """Shortcut to tracking.entity_tracker."""
        return self.tracking.entity_tracker

    @property
    def state_publisher(self):
        """Shortcut to tracking.state_publisher."""
        return self.tracking.state_publisher

    @property
    def guard_rail(self):
        """Shortcut to tracking.guard_rail."""
        return self.tracking.guard_rail

    @property
    def force_full_sync(self) -> bool:
        """Shortcut to batch_config.force_full_sync."""
        return self.batch_config.force_full_sync

    @property
    def should_batch(self) -> bool:
        """Shortcut to batch_config.should_batch."""
        return self.batch_config.should_batch

    @property
    def batch_size(self) -> int:
        """Shortcut to batch_config.batch_size."""
        return self.batch_config.batch_size

    @property
    def max_batch_latency_ms(self) -> int:
        """Shortcut to batch_config.max_batch_latency_ms."""
        return self.batch_config.max_batch_latency_ms

    @property
    def has_keyword_index(self) -> bool:
        """Shortcut to destinations.has_keyword_index."""
        return self.destinations.has_keyword_index
