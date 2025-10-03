# airweave/crud/crud_collection.py

"""CRUD operations for collections."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from airweave import crud
from airweave.api.context import ApiContext
from airweave.core.exceptions import NotFoundException
from airweave.core.shared_models import CollectionStatus
from airweave.crud._base_organization import CRUDBaseOrganization
from airweave.models.collection import Collection
from airweave.schemas.collection import CollectionCreate, CollectionUpdate


class CRUDCollection(CRUDBaseOrganization[Collection, CollectionCreate, CollectionUpdate]):
    """CRUD operations for collections."""

    async def _compute_collection_status(
        self, db: AsyncSession, collection: Collection, ctx: ApiContext
    ) -> CollectionStatus:
        """Compute the ephemeral status of a collection based on its source connections.

        Logic:
        - If no authenticated source connections or no syncs completed yet: NEEDS_SOURCE
        - If at least one connection has completed or is running: ACTIVE
        - If all connections have failed: ERROR

        Args:
            db: The database session
            collection: The collection
            ctx: The API context

        Returns:
            The computed ephemeral status
        """
        # Get source connections with their stats to compute proper status
        connections_with_stats = await crud.source_connection.get_multi_with_stats(
            db, ctx=ctx, collection_id=collection.readable_id
        )

        if not connections_with_stats:
            return CollectionStatus.NEEDS_SOURCE

        # Filter out pending shells to evaluate the status of active connections
        active_connections = [
            conn for conn in connections_with_stats if conn.get("is_authenticated", False)
        ]

        # If there are no authenticated connections, it's effectively the same as needing a source
        if not active_connections:
            return CollectionStatus.NEEDS_SOURCE

        # Count connections by their sync status
        working_count = 0  # Connections with completed or in-progress syncs
        failing_count = 0  # Connections with failed syncs

        for conn in active_connections:
            # Get last job status to compute connection status
            last_job = conn.get("last_job", {})
            last_job_status = last_job.get("status") if last_job else None

            # Only count connections that have completed or are actively syncing
            if last_job_status == "completed":
                working_count += 1
            elif last_job_status in ("running", "cancelling"):
                working_count += 1
            elif last_job_status == "failed":
                failing_count += 1
            # Connections with no jobs, pending, created, or cancelled are not counted

        # If at least one connection has successfully synced or is syncing, collection is active
        if working_count > 0:
            return CollectionStatus.ACTIVE

        # If all active connections have failed, the collection is in error
        if failing_count == len(active_connections):
            return CollectionStatus.ERROR

        # No working connections and not all failed - treat as needing source
        # (connections exist but haven't successfully synced yet)
        return CollectionStatus.NEEDS_SOURCE

    async def _attach_ephemeral_status(
        self, db: AsyncSession, collections: List[Collection], ctx: ApiContext
    ) -> List[Collection]:
        """Attach ephemeral status to collections.

        Args:
            db: The database session
            collections: The collections to process
            ctx: The API context

        Returns:
            Collections with computed status
        """
        if not collections:
            return []

        for collection in collections:
            # Compute and set the ephemeral status
            collection.status = await self._compute_collection_status(db, collection, ctx)

        return collections

    async def get(self, db: AsyncSession, id: UUID, ctx: ApiContext) -> Optional[Collection]:
        """Get a collection by its ID with computed ephemeral status."""
        # Get the collection using the parent method
        collection = await super().get(db, id=id, ctx=ctx)

        if collection:
            # Compute and set the ephemeral status
            collection = (await self._attach_ephemeral_status(db, [collection], ctx))[0]

        return collection

    async def get_by_readable_id(
        self, db: AsyncSession, readable_id: str, ctx: ApiContext
    ) -> Optional[Collection]:
        """Get a collection by its readable ID with computed ephemeral status."""
        result = await db.execute(select(Collection).where(Collection.readable_id == readable_id))
        collection = result.scalar_one_or_none()

        if not collection:
            raise NotFoundException(f"Collection with readable ID {readable_id} not found")

        await self._validate_organization_access(ctx, collection.organization_id)

        # Compute and set the ephemeral status
        collection = (await self._attach_ephemeral_status(db, [collection], ctx))[0]

        return collection

    async def get_multi(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100, ctx: ApiContext
    ) -> List[Collection]:
        """Get multiple collections with computed ephemeral statuses."""
        # Get collections using the parent method
        collections = await super().get_multi(db, skip=skip, limit=limit, ctx=ctx)

        # Compute and set the ephemeral status for each collection
        collections = await self._attach_ephemeral_status(db, collections, ctx)

        return collections


collection = CRUDCollection(Collection)
