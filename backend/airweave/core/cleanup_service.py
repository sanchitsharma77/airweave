"""Centralized cleanup service using composable contexts.

Provides unified cleanup operations for:
- Source connection deletion (cleanup by sync_id)
- Collection deletion (cleanup by collection_id)

Uses CleanupContextBuilder and DestinationsContextBuilder to construct
the necessary context for deletion operations.
"""

from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from airweave import schemas
from airweave.api.context import ApiContext
from airweave.platform.temporal.schedule_service import temporal_schedule_service


class CleanupService:
    """Service for cleaning up data across destinations."""

    async def cleanup_sync(
        self,
        db: AsyncSession,
        sync_id: UUID,
        collection: schemas.Collection,
        ctx: ApiContext,
    ) -> None:
        """Clean up all data for a sync (used for source connection deletion).

        Removes data from:
        - Qdrant (by sync_id)
        - Vespa (by sync_id)
        - ARF storage (by sync_id)

        Args:
            db: Database session
            sync_id: The sync ID to clean up
            collection: The collection the sync belongs to
            ctx: API context
        """
        ctx.logger.info(f"Starting cleanup for sync {sync_id}")

        # Clean up Qdrant
        await self._cleanup_qdrant_by_sync(sync_id, collection, ctx)

        # Clean up Vespa
        await self._cleanup_vespa_by_sync(sync_id, collection, ctx)

        # Clean up ARF storage
        await self._cleanup_arf(sync_id, ctx)

        ctx.logger.info(f"Completed cleanup for sync {sync_id}")

    async def cleanup_collection(
        self,
        db: AsyncSession,
        collection: schemas.Collection,
        ctx: ApiContext,
    ) -> None:
        """Clean up all data for a collection (used for collection deletion).

        Removes data from:
        - Qdrant (by collection_id)
        - Vespa (by collection_id)

        Args:
            db: Database session
            collection: The collection to clean up
            ctx: API context
        """
        ctx.logger.info(f"Starting cleanup for collection {collection.id}")

        # Clean up Qdrant
        await self._cleanup_qdrant_by_collection(collection, ctx)

        # Clean up Vespa
        await self._cleanup_vespa_by_collection(collection, ctx)

        ctx.logger.info(f"Completed cleanup for collection {collection.id}")

    async def cleanup_temporal_schedules(
        self,
        sync_id: UUID,
        db: AsyncSession,
        ctx: ApiContext,
    ) -> None:
        """Clean up all Temporal schedules for a sync.

        Args:
            sync_id: The sync ID whose schedules should be deleted
            db: Database session
            ctx: API context
        """
        try:
            await temporal_schedule_service.delete_all_schedules_for_sync(
                sync_id=sync_id, db=db, ctx=ctx
            )
        except Exception as e:
            ctx.logger.error(f"Failed to delete schedules for sync {sync_id}: {e}")

    async def cleanup_temporal_schedules_for_syncs(
        self,
        sync_ids: List[UUID],
        ctx: ApiContext,
    ) -> None:
        """Clean up Temporal schedules for multiple syncs.

        Args:
            sync_ids: List of sync IDs whose schedules should be deleted
            ctx: API context
        """
        ctx.logger.info(f"Deleting Temporal schedules for {len(sync_ids)} syncs")

        for sync_id in sync_ids:
            for prefix in ("sync", "minute-sync", "daily-cleanup"):
                schedule_id = f"{prefix}-{sync_id}"
                try:
                    await temporal_schedule_service.delete_schedule_handle(schedule_id)
                except Exception as e:
                    ctx.logger.debug(f"Schedule {schedule_id} not deleted: {e}")

    # -------------------------------------------------------------------------
    # Private: Qdrant cleanup
    # -------------------------------------------------------------------------

    async def _cleanup_qdrant_by_sync(
        self,
        sync_id: UUID,
        collection: schemas.Collection,
        ctx: ApiContext,
    ) -> None:
        """Clean up Qdrant data for a specific sync."""
        try:
            from airweave.platform.destinations.qdrant import QdrantDestination

            qdrant = await QdrantDestination.create(
                credentials=None,
                config=None,
                collection_id=collection.id,
                organization_id=collection.organization_id,
            )
            await qdrant.delete_by_sync_id(sync_id)
            ctx.logger.info(f"Deleted Qdrant data for sync {sync_id}")
        except Exception as e:
            ctx.logger.error(f"Error cleaning up Qdrant for sync {sync_id}: {e}")

    async def _cleanup_qdrant_by_collection(
        self,
        collection: schemas.Collection,
        ctx: ApiContext,
    ) -> None:
        """Clean up Qdrant data for an entire collection."""
        try:
            from qdrant_client.http import models as rest

            from airweave.platform.destinations.qdrant import QdrantDestination

            qdrant = await QdrantDestination.create(
                credentials=None,
                config=None,
                collection_id=collection.id,
                organization_id=collection.organization_id,
            )
            if qdrant.client:
                await qdrant.client.delete(
                    collection_name=qdrant.collection_name,
                    points_selector=rest.FilterSelector(
                        filter=rest.Filter(
                            must=[
                                rest.FieldCondition(
                                    key="airweave_collection_id",
                                    match=rest.MatchValue(value=str(collection.id)),
                                )
                            ]
                        )
                    ),
                    wait=True,
                )
                ctx.logger.info(f"Deleted Qdrant data for collection {collection.id}")
        except Exception as e:
            ctx.logger.error(f"Error cleaning up Qdrant for collection {collection.id}: {e}")

    # -------------------------------------------------------------------------
    # Private: Vespa cleanup
    # -------------------------------------------------------------------------

    async def _cleanup_vespa_by_sync(
        self,
        sync_id: UUID,
        collection: schemas.Collection,
        ctx: ApiContext,
    ) -> None:
        """Clean up Vespa data for a specific sync."""
        try:
            from airweave.platform.destinations.vespa import VespaDestination

            vespa = await VespaDestination.create(
                credentials=None,
                config=None,
                collection_id=collection.id,
                organization_id=collection.organization_id,
                logger=ctx.logger,
                sync_id=sync_id,
            )
            await vespa.delete_by_sync_id(sync_id)
            ctx.logger.info(f"Deleted Vespa data for sync {sync_id}")
        except Exception as e:
            ctx.logger.error(f"Error cleaning up Vespa for sync {sync_id}: {e}")

    async def _cleanup_vespa_by_collection(
        self,
        collection: schemas.Collection,
        ctx: ApiContext,
    ) -> None:
        """Clean up Vespa data for an entire collection."""
        try:
            from airweave.platform.destinations.vespa import VespaDestination

            vespa = await VespaDestination.create(
                credentials=None,
                config=None,
                collection_id=collection.id,
                organization_id=collection.organization_id,
                logger=ctx.logger,
                sync_id=None,
            )
            await vespa.delete_by_collection_id(collection.id)
            ctx.logger.info(f"Deleted Vespa data for collection {collection.id}")
        except Exception as e:
            ctx.logger.error(f"Error cleaning up Vespa for collection {collection.id}: {e}")

    # -------------------------------------------------------------------------
    # Private: ARF cleanup
    # -------------------------------------------------------------------------

    async def _cleanup_arf(self, sync_id: UUID, ctx: ApiContext) -> None:
        """Clean up ARF storage for a sync."""
        try:
            from airweave.platform.sync.arf import arf_service

            sync_id_str = str(sync_id)
            if await arf_service.sync_exists(sync_id_str):
                deleted = await arf_service.delete_sync(sync_id_str)
                if deleted:
                    ctx.logger.info(f"Deleted ARF store for sync {sync_id}")
        except Exception as e:
            ctx.logger.warning(f"Failed to cleanup ARF for sync {sync_id}: {e}")


# Singleton instance
cleanup_service = CleanupService()
