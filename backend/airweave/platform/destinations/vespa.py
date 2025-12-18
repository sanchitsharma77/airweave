"""Vespa destination implementation.

Vespa handles chunking and embedding internally via schema definition,
so this destination only transforms entities and feeds them to Vespa.

IMPORTANT: pyvespa methods are synchronous and would block the event loop.
All pyvespa calls are wrapped in asyncio.to_thread() to maintain concurrency.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from airweave.core.config import settings
from airweave.core.logging import ContextualLogger
from airweave.core.logging import logger as default_logger
from airweave.platform.decorators import destination
from airweave.platform.destinations._base import VectorDBDestination
from airweave.platform.entities._base import BaseEntity

if TYPE_CHECKING:
    from vespa.application import Vespa


# Fields that belong to the base_entity schema (not payload)
# These are either explicit document fields or come from airweave_system_metadata
BASE_FIELDS = {
    "entity_id",
    "breadcrumbs",
    "name",
    "created_at",
    "updated_at",
    "textual_representation",
    # Flattened system metadata fields
    "airweave_system_metadata",  # Original nested field (excluded from entity_dict)
    "collection_id",
    "sync_id",
    "sync_job_id",
    "content_hash",
    "original_entity_id",
    "source_name",
    "entity_type",
}


@destination("Vespa", "vespa", supports_vector=True)
class VespaDestination(VectorDBDestination):
    """Vespa destination - Vespa handles chunking/embedding internally."""

    def __init__(self):
        """Initialize the Vespa destination."""
        super().__init__()
        self.collection_id: UUID | None = None
        self.sync_id: UUID | None = None
        self.organization_id: UUID | None = None
        self.app: Optional[Vespa] = None

    @classmethod
    async def create(
        cls,
        credentials: Optional[any] = None,
        config: Optional[dict] = None,
        collection_id: Optional[UUID] = None,
        organization_id: Optional[UUID] = None,
        vector_size: Optional[int] = None,
        logger: Optional[ContextualLogger] = None,
        **kwargs,
    ) -> "VespaDestination":
        """Create and return a connected Vespa destination.

        Args:
            credentials: Optional credentials (unused for native Vespa)
            config: Optional configuration (unused)
            collection_id: SQL collection UUID for multi-tenant filtering
            organization_id: Organization UUID
            vector_size: Vector dimensions (unused - Vespa handles embeddings)
            logger: Logger instance

        Returns:
            Configured VespaDestination instance
        """
        from vespa.application import Vespa

        instance = cls()
        instance.set_logger(logger or default_logger)
        instance.collection_id = collection_id
        instance.organization_id = organization_id

        # Connect to Vespa
        instance.app = Vespa(url=settings.VESPA_URL, port=settings.VESPA_PORT)

        instance.logger.info(
            f"Connected to Vespa at {settings.vespa_url} for collection {collection_id}"
        )

        return instance

    def _transform_entity(self, entity: BaseEntity) -> dict:
        """Transform BaseEntity to Vespa document format.

        Args:
            entity: The entity to transform

        Returns:
            Dict in Vespa feed format with 'id' and 'fields' keys
        """
        # Get entity type from metadata or class name
        entity_type = (
            entity.airweave_system_metadata.entity_type
            if entity.airweave_system_metadata and entity.airweave_system_metadata.entity_type
            else entity.__class__.__name__
        )

        # Composite document ID: entity_type + entity_id for uniqueness
        doc_id = f"{entity_type}_{entity.entity_id}"

        # Build fields dict
        fields = {
            "entity_id": entity.entity_id,
            "name": entity.name,
        }

        # Breadcrumbs (array of struct)
        if entity.breadcrumbs:
            fields["breadcrumbs"] = [b.model_dump() for b in entity.breadcrumbs]

        # Timestamps as epoch seconds (Vespa expects long)
        if entity.created_at:
            fields["created_at"] = int(entity.created_at.timestamp())
        if entity.updated_at:
            fields["updated_at"] = int(entity.updated_at.timestamp())

        # Textual representation - this is what Vespa chunks and embeds
        if entity.textual_representation:
            fields["textual_representation"] = entity.textual_representation

        # System metadata fields (flattened for Vespa compatibility)
        # Vespa doesn't support struct-field attributes on simple structs
        fields["collection_id"] = str(self.collection_id) if self.collection_id else None
        fields["entity_type"] = entity_type

        if entity.airweave_system_metadata:
            meta = entity.airweave_system_metadata
            fields["sync_id"] = str(meta.sync_id) if meta.sync_id else None
            fields["sync_job_id"] = str(meta.sync_job_id) if meta.sync_job_id else None
            fields["content_hash"] = meta.hash
            fields["original_entity_id"] = entity.entity_id  # Parent tracking for chunk deletion
            fields["source_name"] = meta.source_name

        # Extract extra fields into payload JSON
        entity_dict = entity.model_dump(mode="json")
        payload = {k: v for k, v in entity_dict.items() if k not in BASE_FIELDS}
        if payload:
            fields["payload"] = json.dumps(payload)

        # Remove None values from top-level fields
        fields = {k: v for k, v in fields.items() if v is not None}

        return {
            "id": doc_id,
            "fields": fields,
        }

    async def setup_collection(self, vector_size: int | None = None) -> None:
        """Set up collection in Vespa.

        Note: Vespa schema is deployed separately via vespa-deploy.
        This method is a no-op but kept for interface compatibility.
        """
        self.logger.debug("Vespa schema is managed via vespa-deploy, skipping setup_collection")

    async def insert(self, entity: BaseEntity) -> None:
        """Insert a single entity into Vespa.

        Args:
            entity: The entity to insert
        """
        await self.bulk_insert([entity])

    async def bulk_insert(self, entities: list[BaseEntity]) -> None:
        """Transform entities and batch feed to Vespa using feed_iterable.

        Uses pyvespa's feed_iterable for efficient concurrent feeding via HTTP/2
        multiplexing. This is much faster than sequential feed_data_point calls.

        IMPORTANT: feed_iterable is synchronous, so we run it in a thread pool
        to avoid blocking the async event loop.

        Args:
            entities: List of entities to insert
        """
        if not entities:
            return

        if not self.app:
            raise RuntimeError("Vespa client not initialized. Call create() first.")

        self.logger.info(f"Feeding {len(entities)} entities to Vespa (batch)")

        # Transform all entities to Vespa format
        vespa_docs = []
        for entity in entities:
            try:
                vespa_doc = self._transform_entity(entity)
                vespa_docs.append(vespa_doc)
            except Exception as e:
                self.logger.error(f"Failed to transform entity {entity.entity_id}: {e}")

        if not vespa_docs:
            self.logger.warning("No documents to feed after transformation")
            return

        # Track results via callback (must be thread-safe since feed_iterable uses threads)
        success_count = 0
        failed_docs: list[tuple[str, int, dict]] = []

        def callback(response, doc_id: str):
            nonlocal success_count
            if response.is_successful():
                success_count += 1
            else:
                failed_docs.append((doc_id, response.status_code, response.json))

        # Define the synchronous feed operation
        def _feed_sync():
            self.app.feed_iterable(
                iter=vespa_docs,
                schema="base_entity",
                namespace="airweave",
                callback=callback,
                max_queue_size=500,
                max_workers=16,
                max_connections=16,
            )

        # Run synchronous pyvespa method in thread pool to avoid blocking event loop
        await asyncio.to_thread(_feed_sync)

        self.logger.info(f"Vespa feed complete: {success_count} success, {len(failed_docs)} failed")

        if failed_docs:
            self.logger.error(f"{len(failed_docs)}/{len(vespa_docs)} documents failed to feed")
            # Log first few failures for debugging
            for doc_id, status, body in failed_docs[:5]:
                self.logger.error(f"  Failed {doc_id}: status={status}, body={body}")

            # Raise exception to fail the sync - consistent with QdrantDestination behavior
            first_doc_id, first_status, first_body = failed_docs[0]
            error_msg = (
                first_body.get("Exception", str(first_body))
                if isinstance(first_body, dict)
                else str(first_body)
            )
            raise RuntimeError(
                f"Vespa feed failed: {len(failed_docs)}/{len(vespa_docs)} documents. "
                f"First error ({first_doc_id}): {error_msg}"
            )

    async def delete(self, db_entity_id: UUID) -> None:
        """Delete a single entity from Vespa by db_entity_id.

        Args:
            db_entity_id: The database entity ID
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        # Query for documents with this db_entity_id in the collection
        # Note: we don't have db_entity_id as a field - using original_entity_id instead
        yql = (
            f"select documentid from base_entity where "
            f"original_entity_id contains '{db_entity_id}' and "
            f"collection_id contains '{self.collection_id}'"
        )

        await self._delete_by_query(yql)

    async def delete_by_sync_id(self, sync_id: UUID) -> None:
        """Delete all documents from a sync run.

        Args:
            sync_id: The sync ID to delete documents for
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        yql = (
            f"select documentid from base_entity where "
            f"sync_id contains '{sync_id}' and "
            f"collection_id contains '{self.collection_id}'"
        )

        await self._delete_by_query(yql)

    async def delete_by_collection_id(self, collection_id: UUID) -> None:
        """Delete all documents for a collection.

        Used when deleting an entire collection.

        Args:
            collection_id: The collection ID to delete documents for
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        yql = f"select documentid from base_entity where collection_id contains '{collection_id}'"

        await self._delete_by_query(yql)

    async def bulk_delete(self, entity_ids: list[str], sync_id: UUID) -> None:
        """Delete specific entities by entity_id within a sync.

        Args:
            entity_ids: List of entity IDs to delete
            sync_id: The sync ID for scoping
        """
        if not entity_ids or not self.app:
            return

        # Delete each entity
        for entity_id in entity_ids:
            yql = (
                f"select documentid from base_entity where "
                f"entity_id contains '{entity_id}' and "
                f"sync_id contains '{sync_id}' and "
                f"collection_id contains '{self.collection_id}'"
            )
            await self._delete_by_query(yql)

    async def bulk_delete_by_parent_id(self, parent_id: str, sync_id: UUID | str) -> None:
        """Delete all chunks for a parent entity.

        Args:
            parent_id: The original entity ID (before chunking)
            sync_id: The sync ID for scoping
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        yql = (
            f"select documentid from base_entity where "
            f"original_entity_id contains '{parent_id}' and "
            f"collection_id contains '{self.collection_id}'"
        )

        await self._delete_by_query(yql)

    async def bulk_delete_by_parent_ids(self, parent_ids: list[str], sync_id: UUID) -> None:
        """Delete all documents for multiple parent IDs.

        Args:
            parent_ids: List of parent entity IDs
            sync_id: The sync ID for scoping
        """
        for parent_id in parent_ids:
            await self.bulk_delete_by_parent_id(parent_id, sync_id)

    async def _delete_by_query(self, yql: str) -> None:
        """Execute a delete operation based on a YQL query.

        IMPORTANT: pyvespa query() and delete_data() are synchronous,
        so we run them in a thread pool to avoid blocking the event loop.

        Args:
            yql: YQL query to find documents to delete
        """
        if not self.app:
            return

        try:
            # Run synchronous query in thread pool
            response = await asyncio.to_thread(self.app.query, yql=yql, hits=10000)

            if not response.is_successful():
                self.logger.error(f"Query failed: {response.json}")
                return

            hits = response.hits or []
            if not hits:
                self.logger.debug("No documents found to delete")
                return

            self.logger.info(f"Deleting {len(hits)} documents from Vespa")

            # Collect document IDs to delete
            doc_ids_to_delete = []
            for hit in hits:
                doc_id = hit.get("id", "")
                if doc_id:
                    # Extract the user-specified ID from the full document ID
                    # Format: id:namespace:doctype::user_id
                    parts = doc_id.split("::")
                    if len(parts) >= 2:
                        doc_ids_to_delete.append(parts[-1])

            # Define synchronous delete operation for batch
            def _delete_batch_sync() -> int:
                deleted = 0
                for user_id in doc_ids_to_delete:
                    delete_response = self.app.delete_data(
                        schema="base_entity",
                        data_id=user_id,
                        namespace="airweave",
                    )
                    if delete_response.is_successful():
                        deleted += 1
                return deleted

            # Run synchronous deletes in thread pool
            deleted = await asyncio.to_thread(_delete_batch_sync)
            self.logger.info(f"Deleted {deleted} documents from Vespa")

        except Exception as e:
            self.logger.error(f"Error during delete operation: {e}")

    async def search(
        self,
        query_vector: list[float],
        limit: int = 100,
        score_threshold: float | None = None,
        with_payload: bool = True,
        filter: dict | None = None,
        **kwargs,
    ) -> list[dict]:
        """Search Vespa (stub - search will be implemented separately).

        Args:
            query_vector: Query vector (unused - Vespa embeds queries)
            limit: Number of results
            score_threshold: Minimum score threshold
            with_payload: Whether to include payload
            filter: Additional filters

        Returns:
            List of search results
        """
        # Search implementation will be done in the search module
        # This is just a stub for interface compatibility
        self.logger.warning("VespaDestination.search() is a stub - use search module instead")
        return []

    async def has_keyword_index(self) -> bool:
        """Check if Vespa has keyword index.

        Returns:
            True - Vespa always has BM25 via schema configuration
        """
        return True

    async def get_vector_config_names(self) -> list[str]:
        """Get vector config names.

        Returns:
            List of vector field names configured in Vespa schema
        """
        return ["chunk_small_embeddings", "chunk_large_embeddings"]

    async def close_connection(self) -> None:
        """Close the Vespa connection."""
        if self.app:
            self.logger.debug("Closing Vespa connection")
            self.app = None
