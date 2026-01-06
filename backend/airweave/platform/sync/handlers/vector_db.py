"""Vector DB destination handler with integrated content processing.

This handler:
1. Receives resolved actions with raw entities
2. Processes content (text → chunks → embeddings) for vector storage
3. Dispatches to all configured vector DB destinations (Qdrant, Pinecone, etc.)

Key characteristics:
- Owns content processing (text building, chunking, embedding)
- Injected with specific destinations at factory time
- Only handles destinations with processing_requirement=CHUNKS_AND_EMBEDDINGS

Retry Strategy:
- Implements "Availability Retries" for service down/unreachable scenarios
- Destination adapters implement "Protocol Retries" (batch splitting, 429s, payload size)
"""

import asyncio
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

from airweave.platform.destinations._base import BaseDestination
from airweave.platform.entities._base import BaseEntity, CodeFileEntity
from airweave.platform.sync.actions.types import (
    ActionBatch,
    DeleteAction,
    InsertAction,
    UpdateAction,
)
from airweave.platform.sync.exceptions import SyncFailureError
from airweave.platform.sync.handlers.base import ActionHandler
from airweave.platform.sync.pipeline.text_builder import text_builder

if TYPE_CHECKING:
    from airweave.platform.sync.context import SyncContext


class VectorDBHandler(ActionHandler):
    """Handler for vector DB destinations that need Airweave-side chunking/embedding.

    This handler is responsible for:
    1. Building textual representations from entities
    2. Chunking text into smaller segments
    3. Computing embeddings for each chunk
    4. Dispatching processed chunks to vector DB destinations

    Key differences from SelfProcessingHandler:
    - Performs chunking and embedding before dispatch
    - Uses bulk_insert() with chunk entities (not raw entities)
    - Designed for vector DBs that need pre-computed embeddings
    """

    def __init__(self, destinations: List[BaseDestination]):
        """Initialize handler with specific vector DB destinations.

        Args:
            destinations: List of vector DB destinations to dispatch to.
                         These should all have processing_requirement=CHUNKS_AND_EMBEDDINGS.
        """
        self._destinations = destinations

    @property
    def name(self) -> str:
        """Handler name for logging and debugging."""
        if not self._destinations:
            return "vector_db[]"
        dest_names = [d.__class__.__name__ for d in self._destinations]
        return f"vector_db[{','.join(dest_names)}]"

    # -------------------------------------------------------------------------
    # ActionHandler Protocol Implementation
    # -------------------------------------------------------------------------

    async def handle_batch(
        self,
        batch: ActionBatch,
        sync_context: "SyncContext",
    ) -> None:
        """Handle a full action batch with integrated content processing.

        Override default to add content processing before dispatch:
        1. Process content (text → chunks → embeddings) for INSERT/UPDATE
        2. Call parent's handle_batch for dispatch

        Args:
            batch: ActionBatch with resolved actions
            sync_context: Sync context

        Raises:
            SyncFailureError: If processing or dispatch fails
        """
        if not self._destinations:
            sync_context.logger.debug(f"[{self.name}] No destinations configured, skipping")
            return

        # Process content for mutations (sets chunk_entities on actions)
        if batch.has_mutations:
            await self._process_content(batch, sync_context)

        # Dispatch to destinations
        await super().handle_batch(batch, sync_context)

    async def handle_inserts(
        self,
        actions: List[InsertAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle insert actions by dispatching chunks to all vector DBs.

        Args:
            actions: Insert actions with chunk_entities populated
            sync_context: Sync context

        Raises:
            SyncFailureError: If any destination fails
        """
        if not actions:
            return

        all_chunks = [chunk for action in actions for chunk in action.chunk_entities]
        if not all_chunks:
            return

        sync_context.logger.debug(
            f"[{self.name}] Inserting {len(all_chunks)} chunks from {len(actions)} entities"
        )

        for dest in self._destinations:
            await self._execute_with_availability_retry(
                operation=lambda d=dest: d.bulk_insert(all_chunks),
                operation_name=f"insert_to_{dest.__class__.__name__}",
                sync_context=sync_context,
            )

    async def handle_updates(
        self,
        actions: List[UpdateAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle update actions: delete old chunks, insert new chunks.

        Args:
            actions: Update actions with chunk_entities populated
            sync_context: Sync context

        Raises:
            SyncFailureError: If any destination fails
        """
        if not actions:
            return

        # 1. Delete old chunks
        parent_ids = [action.entity_id for action in actions]
        for dest in self._destinations:
            await self._execute_with_availability_retry(
                operation=lambda d=dest: d.bulk_delete_by_parent_ids(
                    parent_ids, sync_context.sync.id
                ),
                operation_name=f"update_clear_{dest.__class__.__name__}",
                sync_context=sync_context,
            )

        # 2. Insert new chunks
        all_chunks = [chunk for action in actions for chunk in action.chunk_entities]
        if all_chunks:
            for dest in self._destinations:
                await self._execute_with_availability_retry(
                    operation=lambda d=dest: d.bulk_insert(all_chunks),
                    operation_name=f"update_insert_{dest.__class__.__name__}",
                    sync_context=sync_context,
                )

    async def handle_deletes(
        self,
        actions: List[DeleteAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle delete actions by removing all chunks for entity.

        Args:
            actions: Delete actions
            sync_context: Sync context

        Raises:
            SyncFailureError: If any destination fails
        """
        if not actions:
            return

        parent_ids = [action.entity_id for action in actions]
        sync_context.logger.debug(f"[{self.name}] Deleting {len(parent_ids)} entities")

        for dest in self._destinations:
            await self._execute_with_availability_retry(
                operation=lambda d=dest: d.bulk_delete_by_parent_ids(
                    parent_ids, sync_context.sync.id
                ),
                operation_name=f"delete_{dest.__class__.__name__}",
                sync_context=sync_context,
            )

    async def handle_orphan_cleanup(
        self,
        orphan_entity_ids: List[str],
        sync_context: "SyncContext",
    ) -> None:
        """Clean up orphaned entities from all vector DBs.

        Args:
            orphan_entity_ids: Entity IDs to clean up
            sync_context: Sync context

        Raises:
            SyncFailureError: If any destination fails
        """
        if not orphan_entity_ids:
            return

        sync_context.logger.debug(
            f"[{self.name}] Cleaning up {len(orphan_entity_ids)} orphaned entities"
        )

        for dest in self._destinations:
            await self._execute_with_availability_retry(
                operation=lambda d=dest: d.bulk_delete_by_parent_ids(
                    orphan_entity_ids, sync_context.sync.id
                ),
                operation_name=f"orphan_cleanup_{dest.__class__.__name__}",
                sync_context=sync_context,
            )

    # -------------------------------------------------------------------------
    # Content Processing (text → chunks → embeddings)
    # -------------------------------------------------------------------------

    async def _process_content(
        self,
        batch: ActionBatch,
        sync_context: "SyncContext",
    ) -> None:
        """Process content for INSERT/UPDATE actions.

        Builds textual representations, chunks, and computes embeddings.
        Sets chunk_entities on each action.

        Args:
            batch: ActionBatch with INSERT/UPDATE actions
            sync_context: Sync context

        Raises:
            SyncFailureError: If processing fails
        """
        entities_to_process = batch.get_entities_to_process()
        if not entities_to_process:
            return

        # Build textual representations
        processed = await text_builder.build_for_batch(entities_to_process, sync_context)

        # Filter empty representations
        processed = await self._filter_empty_representations(processed, sync_context)
        if not processed:
            sync_context.logger.debug(f"[{self.name}] No entities to chunk - all failed conversion")
            return

        # Chunk entities (entity multiplication)
        chunk_entities = await self._chunk_entities(processed, sync_context)

        # Release textual bodies from parent entities (memory optimization)
        for entity in processed:
            entity.textual_representation = None

        # Embed chunk entities
        await self._embed_entities(chunk_entities, sync_context)

        # Assign chunks to their corresponding actions
        self._assign_chunks_to_actions(batch, chunk_entities)

    async def _filter_empty_representations(
        self,
        entities: List[BaseEntity],
        sync_context: "SyncContext",
    ) -> List[BaseEntity]:
        """Filter out entities with empty textual_representation.

        Args:
            entities: Entities to filter
            sync_context: Sync context

        Returns:
            Entities with non-empty textual representations
        """
        valid_entities = []
        for entity in entities:
            text = entity.textual_representation
            if not text or not text.strip():
                sync_context.logger.warning(
                    f"[{self.name}] Entity {entity.__class__.__name__}[{entity.entity_id}] "
                    f"has empty textual_representation, skipping."
                )
                continue
            valid_entities.append(entity)

        skipped = len(entities) - len(valid_entities)
        if skipped:
            await sync_context.entity_tracker.record_skipped(skipped)

        return valid_entities

    async def _chunk_entities(
        self,
        entities: List[BaseEntity],
        sync_context: "SyncContext",
    ) -> List[BaseEntity]:
        """Chunk entities using type-specific chunkers.

        Args:
            entities: Entities to chunk
            sync_context: Sync context

        Returns:
            List of chunk entities
        """
        if not entities:
            return []

        code_entities = [e for e in entities if isinstance(e, CodeFileEntity)]
        textual_entities = [e for e in entities if not isinstance(e, CodeFileEntity)]

        sync_context.logger.debug(
            f"[{self.name}] Entity routing: {len(code_entities)} code, "
            f"{len(textual_entities)} textual"
        )

        all_chunk_entities = []

        if code_entities:
            code_chunks = await self._chunk_code_entities(code_entities, sync_context)
            all_chunk_entities.extend(code_chunks)

        if textual_entities:
            textual_chunks = await self._chunk_textual_entities(textual_entities, sync_context)
            all_chunk_entities.extend(textual_chunks)

        sync_context.logger.debug(
            f"[{self.name}] Entity multiplication: "
            f"{len(entities)} → {len(all_chunk_entities)} chunks"
        )

        return all_chunk_entities

    async def _chunk_code_entities(
        self,
        entities: List[BaseEntity],
        sync_context: "SyncContext",
    ) -> List[BaseEntity]:
        """Chunk code entities with CodeChunker.

        Args:
            entities: Code entities to chunk
            sync_context: Sync context

        Returns:
            List of code chunk entities
        """
        from airweave.platform.chunkers.code import CodeChunker

        supported, unsupported = await self._filter_unsupported_code_languages(
            entities, sync_context
        )

        if unsupported:
            await sync_context.entity_tracker.record_skipped(len(unsupported))

        if not supported:
            return []

        chunker = CodeChunker()
        texts = [e.textual_representation for e in supported]

        try:
            chunk_lists = await chunker.chunk_batch(texts)
        except Exception as e:
            raise SyncFailureError(f"[{self.name}] CodeChunker failed: {e}")

        return await self._multiply_entities_from_chunks(supported, chunk_lists, sync_context)

    async def _chunk_textual_entities(
        self,
        entities: List[BaseEntity],
        sync_context: "SyncContext",
    ) -> List[BaseEntity]:
        """Chunk textual entities with SemanticChunker.

        Args:
            entities: Textual entities to chunk
            sync_context: Sync context

        Returns:
            List of textual chunk entities
        """
        from airweave.platform.chunkers.semantic import SemanticChunker

        chunker = SemanticChunker()
        texts = [e.textual_representation for e in entities]

        try:
            chunk_lists = await chunker.chunk_batch(texts)
        except Exception as e:
            raise SyncFailureError(f"[{self.name}] SemanticChunker failed: {e}")

        return await self._multiply_entities_from_chunks(entities, chunk_lists, sync_context)

    async def _filter_unsupported_code_languages(
        self,
        entities: List[BaseEntity],
        sync_context: "SyncContext",
    ) -> Tuple[List[BaseEntity], List[BaseEntity]]:
        """Filter code entities with unsupported tree-sitter languages.

        Args:
            entities: Code entities to filter
            sync_context: Sync context

        Returns:
            Tuple of (supported, unsupported) entities
        """
        code_entities = [e for e in entities if isinstance(e, CodeFileEntity)]
        if not code_entities:
            return entities, []

        try:
            from magika import Magika
            from tree_sitter_language_pack import get_parser
        except ImportError:
            return entities, []

        magika = Magika()
        supported = []
        unsupported = []

        for entity in code_entities:
            try:
                text_bytes = entity.textual_representation.encode("utf-8")
                result = magika.identify_bytes(text_bytes)
                detected_lang = result.output.label.lower()

                try:
                    get_parser(detected_lang)
                    supported.append(entity)
                except LookupError:
                    unsupported.append(entity)
            except Exception:
                unsupported.append(entity)

        return supported, unsupported

    async def _multiply_entities_from_chunks(
        self,
        entities: List[BaseEntity],
        chunk_lists: List[List[Dict[str, Any]]],
        sync_context: "SyncContext",
    ) -> List[BaseEntity]:
        """Create chunk entities from chunk dicts.

        Args:
            entities: Parent entities
            chunk_lists: List of chunk dicts per entity
            sync_context: Sync context

        Returns:
            List of chunk entities
        """
        chunk_entities: List[BaseEntity] = []
        failed_count = 0

        for entity, chunks in zip(entities, chunk_lists, strict=True):
            if not chunks:
                failed_count += 1
                continue

            original_entity_id = entity.entity_id

            for chunk_idx, chunk in enumerate(chunks):
                chunk_text = chunk.get("text", "")
                if not chunk_text or not chunk_text.strip():
                    failed_count += 1
                    break

                chunk_entity = entity.model_copy(
                    update={'textual_representation': chunk_text}, deep=True
                )
                chunk_entity.entity_id = f"{original_entity_id}__chunk_{chunk_idx}"

                if chunk_entity.airweave_system_metadata is None:
                    raise SyncFailureError(f"[{self.name}] No metadata for {entity.entity_id}")

                chunk_entity.airweave_system_metadata.chunk_index = chunk_idx
                chunk_entity.airweave_system_metadata.original_entity_id = original_entity_id

                chunk_entities.append(chunk_entity)

        if failed_count:
            await sync_context.entity_tracker.record_skipped(failed_count)

        return chunk_entities

    async def _embed_entities(
        self,
        chunk_entities: List[BaseEntity],
        sync_context: "SyncContext",
    ) -> None:
        """Compute dense and sparse embeddings for chunk entities.

        Args:
            chunk_entities: Chunk entities to embed
            sync_context: Sync context

        Raises:
            SyncFailureError: If embedding fails or results are invalid
        """
        if not chunk_entities:
            return

        dense_texts = [e.textual_representation for e in chunk_entities]
        sparse_texts = [
            json.dumps(
                e.model_dump(mode="json", exclude={"airweave_system_metadata"}),
                sort_keys=True,
            )
            for e in chunk_entities
        ]

        from airweave.platform.embedders import DenseEmbedder

        dense_embedder = DenseEmbedder(vector_size=sync_context.collection.vector_size)
        dense_embeddings = await dense_embedder.embed_many(dense_texts, sync_context)

        sparse_embeddings = None
        if sync_context.has_keyword_index:
            from airweave.platform.embedders import SparseEmbedder

            sparse_embedder = SparseEmbedder()
            sparse_embeddings = await sparse_embedder.embed_many(sparse_texts, sync_context)

        for i, entity in enumerate(chunk_entities):
            dense_vector = dense_embeddings[i]
            sparse_vector = sparse_embeddings[i] if sparse_embeddings else None
            entity.airweave_system_metadata.vectors = [dense_vector, sparse_vector]

        # Validate
        for entity in chunk_entities:
            if not entity.airweave_system_metadata.vectors:
                raise SyncFailureError(f"[{self.name}] Entity {entity.entity_id} has no vectors")
            if entity.airweave_system_metadata.vectors[0] is None:
                raise SyncFailureError(
                    f"[{self.name}] Entity {entity.entity_id} has no dense vector"
                )

        sync_context.logger.debug(
            f"[{self.name}] Embedded {len(chunk_entities)} chunks "
            f"(dense: {len(dense_embeddings)}, "
            f"sparse: {len(sparse_embeddings) if sparse_embeddings else 0})"
        )

    def _assign_chunks_to_actions(
        self,
        batch: ActionBatch,
        chunk_entities: List[BaseEntity],
    ) -> None:
        """Assign chunk entities to their parent action.

        Args:
            batch: ActionBatch to update
            chunk_entities: Chunk entities with original_entity_id set
        """
        # Build map of original_entity_id -> chunks
        chunks_by_parent: Dict[str, List[BaseEntity]] = defaultdict(list)
        for chunk in chunk_entities:
            original_id = chunk.airweave_system_metadata.original_entity_id
            chunks_by_parent[original_id].append(chunk)

        # Assign to insert actions
        for action in batch.inserts:
            action.chunk_entities = chunks_by_parent.get(action.entity_id, [])

        # Assign to update actions
        for action in batch.updates:
            action.chunk_entities = chunks_by_parent.get(action.entity_id, [])

    # -------------------------------------------------------------------------
    # Retry Logic (availability retries)
    # -------------------------------------------------------------------------

    async def _execute_with_availability_retry(
        self,
        operation: Callable,
        operation_name: str,
        sync_context: "SyncContext",
        max_retries: int = 4,
    ) -> Any:
        """Execute operation with retries ONLY for availability issues.

        Logic:
        - If service is down (ConnectionRefused, 503), wait and retry.
        - If permanent error (400, DataError), fail immediately.
        - Relies on Destination adapter to handle protocol-specifics (splitting, 429).

        Args:
            operation: Async callable to execute
            operation_name: Name for logging
            sync_context: Sync context
            max_retries: Maximum retry attempts

        Returns:
            Operation result

        Raises:
            SyncFailureError: If operation fails after retries or encounters permanent error
        """
        # Define what constitutes an availability failure
        retryable_errors = (
            ConnectionError,
            TimeoutError,
        )

        # Try to import httpcore/httpx for network errors if available
        try:
            import httpcore
            import httpx

            retryable_errors += (
                httpx.NetworkError,
                httpx.TimeoutException,
                httpcore.NetworkError,
                httpcore.TimeoutException,
            )
        except ImportError:
            pass

        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except retryable_errors as e:
                if attempt < max_retries:
                    wait_time = 2 * (2**attempt)  # 2, 4, 8, 16s
                    sync_context.logger.warning(
                        f"⚠️ [{self.name}] {operation_name} unavailable "
                        f"(attempt {attempt + 1}/{max_retries}): "
                        f"{type(e).__name__} - {e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    sync_context.logger.error(
                        f"💥 [{self.name}] {operation_name} unavailable "
                        f"after {max_retries} retries."
                    )
                    raise SyncFailureError(f"Destination unavailable: {e}") from e
            except Exception as e:
                # Check for permanent errors (like 400 Bad Request)
                if self._is_permanent_error(e):
                    sync_context.logger.error(
                        f"💥 [{self.name}] Permanent error in {operation_name}: {e}"
                    )
                    raise SyncFailureError(f"Destination error: {e}") from e

                # Fail fast on non-network errors to respect UoW
                sync_context.logger.error(f"💥 [{self.name}] Error in {operation_name}: {e}")
                raise SyncFailureError(f"Destination failed: {e}") from e

    def _is_permanent_error(self, e: Exception) -> bool:
        """Check if error is definitely permanent.

        Args:
            e: Exception to check

        Returns:
            True if error is permanent (should not retry)
        """
        msg = str(e).lower()
        return any(x in msg for x in ["400", "401", "403", "404", "validation error"])
