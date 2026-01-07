"""Sync context builder - orchestrates all context builders.

Returns the existing SyncContext from sync/context.py for backwards compatibility.
"""

import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from airweave import schemas
from airweave.api.context import ApiContext
from airweave.platform.builders.destinations import DestinationsContextBuilder
from airweave.platform.builders.infra import InfraContextBuilder
from airweave.platform.builders.source import SourceContextBuilder
from airweave.platform.builders.tracking import TrackingContextBuilder
from airweave.platform.sync.config import SyncExecutionConfig

# Import the EXISTING SyncContext for backwards compatibility
from airweave.platform.sync.context import SyncContext


class SyncContextBuilder:
    """Orchestrates all context builders to create SyncContext.

    Returns the existing SyncContext from sync/context.py to maintain
    backwards compatibility with all existing code.
    """

    @classmethod
    async def build(
        cls,
        db: AsyncSession,
        sync: schemas.Sync,
        sync_job: schemas.SyncJob,
        collection: schemas.Collection,
        connection: schemas.Connection,
        ctx: ApiContext,
        access_token: Optional[str] = None,
        force_full_sync: bool = False,
        execution_config: Optional[SyncExecutionConfig] = None,
    ) -> SyncContext:
        """Build complete sync context using all builders.

        This method coordinates the builders to construct all sub-contexts,
        then assembles them into the existing SyncContext for backwards compat.

        Args:
            db: Database session
            sync: The sync configuration
            sync_job: The sync job
            collection: The collection to sync to
            connection: The connection
            ctx: The API context
            access_token: Optional token to use instead of stored credentials
            force_full_sync: If True, forces a full sync with orphaned entity deletion
            execution_config: Optional execution config for controlling sync behavior

        Returns:
            SyncContext (from sync/context.py) with all components assembled.
        """
        # Step 1: Get source connection ID early (needed for logger dimensions)
        source_connection_id = await SourceContextBuilder.get_source_connection_id(db, sync, ctx)

        # Step 2: Build infrastructure context (needed by all other builders)
        infra = InfraContextBuilder.build(
            sync=sync,
            sync_job=sync_job,
            collection=collection,
            source_connection_id=source_connection_id,
            ctx=ctx,
        )

        infra.logger.info("Building sync context via context builders...")

        # Step 3: Build all remaining contexts in parallel
        source_task = SourceContextBuilder.build(
            db=db,
            sync=sync,
            sync_job=sync_job,
            infra=infra,
            access_token=access_token,
            force_full_sync=force_full_sync,
            execution_config=execution_config,
        )

        destinations_task = DestinationsContextBuilder.build(
            db=db,
            sync=sync,
            collection=collection,
            infra=infra,
            execution_config=execution_config,
        )

        tracking_task = TrackingContextBuilder.build(
            db=db,
            sync=sync,
            sync_job=sync_job,
            infra=infra,
        )

        # Run all builders in parallel
        source_ctx, destinations_ctx, tracking_ctx = await asyncio.gather(
            source_task,
            destinations_task,
            tracking_task,
        )

        # Step 4: Precompute destination keyword-index capability
        has_keyword_index = False
        try:
            if destinations_ctx.destinations:
                has_keyword_index = any(
                    await asyncio.gather(
                        *[dest.has_keyword_index() for dest in destinations_ctx.destinations]
                    )
                )
        except Exception as e:
            infra.logger.warning(f"Failed to precompute keyword index capability: {e}")
            has_keyword_index = False

        # Step 5: Set cursor on source so it can access cursor data
        source_ctx.source.set_cursor(source_ctx.cursor)

        # Step 6: Assemble into EXISTING SyncContext for backwards compatibility
        sync_context = SyncContext(
            source=source_ctx.source,
            destinations=destinations_ctx.destinations,
            sync=sync,
            sync_job=sync_job,
            entity_tracker=tracking_ctx.entity_tracker,
            state_publisher=tracking_ctx.state_publisher,
            cursor=source_ctx.cursor,
            collection=collection,
            connection=connection,
            entity_map=destinations_ctx.entity_map,
            ctx=infra.ctx,
            guard_rail=tracking_ctx.guard_rail,
            logger=infra.logger,
            force_full_sync=force_full_sync,
            has_keyword_index=has_keyword_index,
            execution_config=execution_config,
        )

        infra.logger.info("Sync context created via context builders")

        return sync_context
