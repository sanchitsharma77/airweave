"""Vespa destination implementation.

Vespa handles chunking and embedding internally via schema definition,
so this destination only transforms entities and feeds them to Vespa.

IMPORTANT: pyvespa methods are synchronous and would block the event loop.
All pyvespa calls are wrapped in asyncio.to_thread() to maintain concurrency.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from airweave.core.config import settings
from airweave.core.logging import ContextualLogger
from airweave.core.logging import logger as default_logger
from airweave.platform.decorators import destination
from airweave.platform.destinations._base import VectorDBDestination
from airweave.platform.entities._base import (
    BaseEntity,
    CodeFileEntity,
    EmailEntity,
    FileEntity,
    WebEntity,
)

if TYPE_CHECKING:
    from vespa.application import Vespa


# Flattened system metadata fields that are stored as top-level Vespa fields
# These come from AirweaveSystemMetadata but are flattened for Vespa compatibility
SYSTEM_METADATA_FIELDS = {
    "airweave_system_metadata",  # Original nested field (excluded from entity_dict)
    "collection_id",
    "sync_id",
    "sync_job_id",
    "content_hash",
    "original_entity_id",
    "source_name",
    "entity_type",
}


def _get_schema_fields_for_entity(entity: BaseEntity) -> set[str]:
    """Get all fields that have Vespa schema columns (not payload) for an entity.

    This derives the field list dynamically from the entity class hierarchy,
    making the entity class definitions the single source of truth.

    Args:
        entity: The entity to get schema fields for

    Returns:
        Set of field names that should NOT go into the payload JSON
    """
    # Start with BaseEntity fields
    fields = set(BaseEntity.model_fields.keys())

    # Add system metadata fields (flattened)
    fields |= SYSTEM_METADATA_FIELDS

    # Add type-specific fields based on entity class hierarchy
    if isinstance(entity, WebEntity):
        # WebEntity adds crawl_url
        fields |= set(WebEntity.model_fields.keys()) - set(BaseEntity.model_fields.keys())
    if isinstance(entity, FileEntity):
        # FileEntity adds url, size, file_type, mime_type, local_path
        fields |= set(FileEntity.model_fields.keys()) - set(BaseEntity.model_fields.keys())
    if isinstance(entity, CodeFileEntity):
        # CodeFileEntity adds repo_name, path_in_repo, repo_owner, language, commit_id
        fields |= set(CodeFileEntity.model_fields.keys()) - set(FileEntity.model_fields.keys())
    # EmailEntity doesn't add any fields beyond FileEntity

    return fields


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

    def _get_vespa_schema(self, entity: BaseEntity) -> str:
        """Determine the Vespa schema name for an entity.

        Args:
            entity: The entity to get schema for

        Returns:
            Vespa schema name (e.g., "base_entity", "file_entity", "code_file_entity")
        """
        # Check in order of specificity (most specific first)
        if isinstance(entity, CodeFileEntity):
            return "code_file_entity"
        elif isinstance(entity, EmailEntity):
            return "email_entity"
        elif isinstance(entity, FileEntity):
            return "file_entity"
        elif isinstance(entity, WebEntity):
            return "web_entity"
        else:
            return "base_entity"

    def _transform_entity(self, entity: BaseEntity) -> tuple[str, dict]:
        """Transform BaseEntity to Vespa document format.

        Args:
            entity: The entity to transform

        Returns:
            Tuple of (schema_name, doc_dict) where doc_dict has 'id' and 'fields' keys
        """
        # Get entity type from metadata or class name
        entity_type = (
            entity.airweave_system_metadata.entity_type
            if entity.airweave_system_metadata and entity.airweave_system_metadata.entity_type
            else entity.__class__.__name__
        )

        # Determine the Vespa schema for this entity
        schema = self._get_vespa_schema(entity)

        # Composite document ID: entity_type + entity_id for uniqueness
        doc_id = f"{entity_type}_{entity.entity_id}"

        # Build fields dict with base entity fields
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

        # Add web-specific fields if this is a WebEntity
        if isinstance(entity, WebEntity):
            fields["crawl_url"] = entity.crawl_url

        # Add file-specific fields if this is a FileEntity
        if isinstance(entity, FileEntity):
            fields["url"] = entity.url
            fields["size"] = entity.size
            fields["file_type"] = entity.file_type
            if entity.mime_type:
                fields["mime_type"] = entity.mime_type
            if entity.local_path:
                fields["local_path"] = entity.local_path

        # Add code-specific fields if this is a CodeFileEntity
        if isinstance(entity, CodeFileEntity):
            fields["repo_name"] = entity.repo_name
            fields["path_in_repo"] = entity.path_in_repo
            fields["repo_owner"] = entity.repo_owner
            fields["language"] = entity.language
            fields["commit_id"] = entity.commit_id

        # Extract extra fields into payload JSON
        # Use dynamic field derivation so entity class definitions are the single source of truth
        schema_fields = _get_schema_fields_for_entity(entity)
        entity_dict = entity.model_dump(mode="json")
        payload = {k: v for k, v in entity_dict.items() if k not in schema_fields}
        if payload:
            fields["payload"] = json.dumps(payload)

        # Remove None values from top-level fields
        fields = {k: v for k, v in fields.items() if v is not None}

        return schema, {
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

        Entities are grouped by schema type and fed separately to the correct schema.

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

        # Transform all entities to Vespa format, grouped by schema
        docs_by_schema: dict[str, list[dict]] = defaultdict(list)
        for entity in entities:
            try:
                schema, vespa_doc = self._transform_entity(entity)
                docs_by_schema[schema].append(vespa_doc)
            except Exception as e:
                self.logger.error(f"Failed to transform entity {entity.entity_id}: {e}")

        total_docs = sum(len(docs) for docs in docs_by_schema.values())
        if total_docs == 0:
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

        # Define the synchronous feed operation for a specific schema
        def _feed_schema_sync(schema: str, docs: list[dict]):
            self.app.feed_iterable(
                iter=docs,
                schema=schema,
                namespace="airweave",
                callback=callback,
                max_queue_size=500,
                max_workers=16,
                max_connections=16,
            )

        # Feed each schema's documents
        for schema, docs in docs_by_schema.items():
            self.logger.debug(f"Feeding {len(docs)} documents to schema '{schema}'")
            await asyncio.to_thread(_feed_schema_sync, schema, docs)

        self.logger.info(f"Vespa feed complete: {success_count} success, {len(failed_docs)} failed")

        if failed_docs:
            self.logger.error(f"{len(failed_docs)}/{total_docs} documents failed to feed")
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
                f"Vespa feed failed: {len(failed_docs)}/{total_docs} documents. "
                f"First error ({first_doc_id}): {error_msg}"
            )

    # All Vespa schemas that we need to query/delete from
    VESPA_SCHEMAS = ["base_entity", "file_entity", "code_file_entity", "email_entity", "web_entity"]

    async def delete(self, db_entity_id: UUID) -> None:
        """Delete a single entity from Vespa by db_entity_id.

        Args:
            db_entity_id: The database entity ID
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        # Query for documents with this db_entity_id in the collection
        # Note: we don't have db_entity_id as a field - using original_entity_id instead
        # Search across all schemas
        for schema in self.VESPA_SCHEMAS:
            yql = (
                f"select documentid from {schema} where "
                f"original_entity_id contains '{db_entity_id}' and "
                f"collection_id contains '{self.collection_id}'"
            )
            await self._delete_by_query(yql, schema)

    async def delete_by_sync_id(self, sync_id: UUID) -> None:
        """Delete all documents from a sync run.

        Args:
            sync_id: The sync ID to delete documents for
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        # Search across all schemas
        for schema in self.VESPA_SCHEMAS:
            yql = (
                f"select documentid from {schema} where "
                f"sync_id contains '{sync_id}' and "
                f"collection_id contains '{self.collection_id}'"
            )
            await self._delete_by_query(yql, schema)

    async def delete_by_collection_id(self, collection_id: UUID) -> None:
        """Delete all documents for a collection.

        Used when deleting an entire collection.

        Args:
            collection_id: The collection ID to delete documents for
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        # Search across all schemas
        for schema in self.VESPA_SCHEMAS:
            yql = f"select documentid from {schema} where collection_id contains '{collection_id}'"
            await self._delete_by_query(yql, schema)

    async def bulk_delete(self, entity_ids: list[str], sync_id: UUID) -> None:
        """Delete specific entities by entity_id within a sync.

        Args:
            entity_ids: List of entity IDs to delete
            sync_id: The sync ID for scoping
        """
        if not entity_ids or not self.app:
            return

        # Delete each entity from all schemas
        for entity_id in entity_ids:
            for schema in self.VESPA_SCHEMAS:
                yql = (
                    f"select documentid from {schema} where "
                    f"entity_id contains '{entity_id}' and "
                    f"sync_id contains '{sync_id}' and "
                    f"collection_id contains '{self.collection_id}'"
                )
                await self._delete_by_query(yql, schema)

    async def bulk_delete_by_parent_id(self, parent_id: str, sync_id: UUID | str) -> None:
        """Delete all chunks for a parent entity.

        Args:
            parent_id: The original entity ID (before chunking)
            sync_id: The sync ID for scoping
        """
        if not self.app:
            raise RuntimeError("Vespa client not initialized")

        # Search across all schemas
        for schema in self.VESPA_SCHEMAS:
            yql = (
                f"select documentid from {schema} where "
                f"original_entity_id contains '{parent_id}' and "
                f"collection_id contains '{self.collection_id}'"
            )
            await self._delete_by_query(yql, schema)

    async def bulk_delete_by_parent_ids(self, parent_ids: list[str], sync_id: UUID) -> None:
        """Delete all documents for multiple parent IDs.

        Args:
            parent_ids: List of parent entity IDs
            sync_id: The sync ID for scoping
        """
        for parent_id in parent_ids:
            await self.bulk_delete_by_parent_id(parent_id, sync_id)

    async def _delete_by_query(self, yql: str, schema: str) -> None:
        """Execute a delete operation based on a YQL query with pagination.

        IMPORTANT: pyvespa query() and delete_data() are synchronous,
        so we run them in a thread pool to avoid blocking the event loop.

        Uses pagination to handle large result sets that may exceed Vespa's
        configured max hits limit.

        Args:
            yql: YQL query to find documents to delete
            schema: The Vespa schema to delete from
        """
        if not self.app:
            return

        batch_size = 400  # Vespa's default maxHits limit
        total_deleted = 0

        try:
            # Paginate through all matching documents
            while True:
                # Run synchronous query in thread pool
                response = await asyncio.to_thread(self.app.query, yql=yql, hits=batch_size)

                if not response.is_successful():
                    self.logger.error(f"Error during delete operation: {response.json}")
                    return

                hits = response.hits or []
                if not hits:
                    if total_deleted > 0:
                        self.logger.info(
                            f"Deleted {total_deleted} total documents from Vespa schema '{schema}'"
                        )
                    else:
                        self.logger.debug(f"No documents found to delete from {schema}")
                    return

                self.logger.debug(
                    f"Deleting batch of {len(hits)} documents from Vespa schema '{schema}'"
                )

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
                # Use default arg to bind loop variable (avoids late binding issues)
                def _delete_batch_sync(ids: list = doc_ids_to_delete) -> int:
                    deleted = 0
                    for user_id in ids:
                        delete_response = self.app.delete_data(
                            schema=schema,
                            data_id=user_id,
                            namespace="airweave",
                        )
                        if delete_response.is_successful():
                            deleted += 1
                    return deleted

                # Run synchronous deletes in thread pool
                deleted = await asyncio.to_thread(_delete_batch_sync)
                total_deleted += deleted

                # If we got fewer hits than batch_size, we're done
                if len(hits) < batch_size:
                    if total_deleted > 0:
                        self.logger.info(
                            f"Deleted {total_deleted} total documents from Vespa schema '{schema}'"
                        )
                    break

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
