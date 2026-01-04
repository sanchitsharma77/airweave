"""Infrastructure builder for sync operations.

Creates the core infrastructure bundle (logger, ctx) needed by all other builders.
"""

from uuid import UUID

from airweave import schemas
from airweave.api.context import ApiContext
from airweave.core.logging import ContextualLogger, LoggerConfigurator
from airweave.platform.sync.bundles import InfraBundle


class InfraBuilder:
    """Builds core infrastructure for sync operations."""

    @classmethod
    def build(
        cls,
        sync: schemas.Sync,
        sync_job: schemas.SyncJob,
        collection: schemas.Collection,
        source_connection_id: UUID,
        ctx: ApiContext,
    ) -> tuple[InfraBundle, ContextualLogger]:
        """Build infrastructure bundle with contextual logger.

        Args:
            sync: Sync configuration
            sync_job: The sync job being executed
            collection: Target collection
            source_connection_id: Source connection ID for logging dimensions
            ctx: API context

        Returns:
            Tuple of (InfraBundle, ContextualLogger)
            Logger is returned separately for use by other builders.
        """
        # Create a contextualized logger with all job metadata
        logger = LoggerConfigurator.configure_logger(
            "airweave.platform.sync",
            dimensions={
                "sync_id": str(sync.id),
                "sync_job_id": str(sync_job.id),
                "organization_id": str(ctx.organization.id),
                "source_connection_id": str(source_connection_id),
                "collection_readable_id": str(collection.readable_id),
                "organization_name": ctx.organization.name,
                "scheduled": str(sync_job.scheduled),
            },
        )

        infra = InfraBundle(ctx=ctx, logger=logger)

        return infra, logger

    @classmethod
    def build_minimal(
        cls,
        ctx: ApiContext,
        operation: str,
        sync_id: UUID,
        collection_id: UUID,
    ) -> InfraBundle:
        """Build minimal infrastructure for non-sync operations.

        Use this for cleanup, webhooks, and other operations that don't
        have a full sync context.

        Args:
            ctx: API context
            operation: Operation name for logging (e.g., "cleanup", "webhook")
            sync_id: Sync ID for logging
            collection_id: Collection ID for logging

        Returns:
            InfraBundle with minimal logger
        """
        from airweave.core.logging import get_logger

        logger = get_logger().with_context(
            operation=operation,
            sync_id=str(sync_id),
            collection_id=str(collection_id),
            organization_id=str(ctx.organization.id),
        )

        return InfraBundle(ctx=ctx, logger=logger)

