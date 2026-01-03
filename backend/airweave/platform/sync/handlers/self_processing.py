"""Self-processing destination handler.

This handler:
1. Receives resolved actions with raw entities
2. Builds textual representations (text extraction)
3. Does NOT chunk or embed - destination handles this internally
4. Dispatches raw entities to self-processing destinations (e.g., Vespa)

Key characteristics:
- Owns text extraction only (not chunking/embedding)
- Injected with specific destinations at factory time
- Only handles destinations with processing_requirement=RAW_ENTITIES
- Calls bulk_insert() with raw entities (single entity per action, no chunks)
"""

import asyncio
from typing import TYPE_CHECKING, Callable, List

from airweave.platform.destinations._base import BaseDestination
from airweave.platform.entities._base import BaseEntity
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


class SelfProcessingHandler(ActionHandler):
    """Handler for destinations that handle chunking/embedding internally.

    This handler is responsible for:
    1. Building textual representations from entities
    2. Dispatching raw entities to self-processing destinations

    Key differences from VectorDBHandler:
    - Does NOT perform chunking (destination handles this)
    - Does NOT compute embeddings (destination handles this)
    - Calls bulk_insert() with raw entities (not chunk entities)
    - Designed for Vespa and similar self-processing vector DBs
    """

    def __init__(self, destinations: List[BaseDestination]):
        """Initialize handler with specific self-processing destinations.

        Args:
            destinations: List of destinations to dispatch to.
                         These should all have processing_requirement=RAW_ENTITIES.
        """
        self._destinations = destinations

    @property
    def name(self) -> str:
        """Handler name for logging and debugging."""
        if not self._destinations:
            return "self_processing[]"
        dest_names = [d.__class__.__name__ for d in self._destinations]
        return f"self_processing[{','.join(dest_names)}]"

    # -------------------------------------------------------------------------
    # ActionHandler Protocol Implementation
    # -------------------------------------------------------------------------

    async def handle_batch(
        self,
        batch: ActionBatch,
        sync_context: "SyncContext",
    ) -> None:
        """Handle a full action batch with text extraction.

        Override default to add text building before dispatch:
        1. Build textual representations for INSERT/UPDATE entities
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

        # Build textual representations for mutations (no chunking/embedding)
        if batch.has_mutations:
            await self._build_text_representations(batch, sync_context)

        # Dispatch to destinations
        await super().handle_batch(batch, sync_context)

    async def handle_inserts(
        self,
        actions: List[InsertAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle insert actions by dispatching raw entities to all destinations.

        Args:
            actions: Insert actions (entities have textual_representation set)
            sync_context: Sync context

        Raises:
            SyncFailureError: If any destination fails
        """
        if not actions:
            return

        # Collect raw entities (no chunks - destination handles chunking)
        entities = [action.entity for action in actions]
        if not entities:
            return

        sync_context.logger.debug(f"[{self.name}] Inserting {len(entities)} raw entities")

        for dest in self._destinations:
            await self._execute_with_availability_retry(
                operation=lambda d=dest: d.bulk_insert(entities),
                operation_name=f"insert_to_{dest.__class__.__name__}",
                sync_context=sync_context,
            )

    async def handle_updates(
        self,
        actions: List[UpdateAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle update actions: delete old entities, insert new entities.

        Args:
            actions: Update actions (entities have textual_representation set)
            sync_context: Sync context

        Raises:
            SyncFailureError: If any destination fails
        """
        if not actions:
            return

        # 1. Delete old entities by parent_id
        # For self-processing destinations, we delete by original_entity_id
        parent_ids = [action.entity_id for action in actions]
        for dest in self._destinations:
            await self._execute_with_availability_retry(
                operation=lambda d=dest: d.bulk_delete_by_parent_ids(
                    parent_ids, sync_context.sync.id
                ),
                operation_name=f"update_clear_{dest.__class__.__name__}",
                sync_context=sync_context,
            )

        # 2. Insert new entities (raw, no chunks)
        entities = [action.entity for action in actions]
        if entities:
            for dest in self._destinations:
                await self._execute_with_availability_retry(
                    operation=lambda d=dest: d.bulk_insert(entities),
                    operation_name=f"update_insert_{dest.__class__.__name__}",
                    sync_context=sync_context,
                )

    async def handle_deletes(
        self,
        actions: List[DeleteAction],
        sync_context: "SyncContext",
    ) -> None:
        """Handle delete actions by removing entities from destinations.

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
        """Clean up orphaned entities from all destinations.

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
    # Text Extraction (no chunking/embedding)
    # -------------------------------------------------------------------------

    async def _build_text_representations(
        self,
        batch: ActionBatch,
        sync_context: "SyncContext",
    ) -> None:
        """Build textual representations for INSERT/UPDATE actions.

        Only extracts text - no chunking or embedding. The destination
        (e.g., Vespa) handles chunking and embedding server-side.

        Args:
            batch: ActionBatch with INSERT/UPDATE actions
            sync_context: Sync context

        Raises:
            SyncFailureError: If text building fails
        """
        entities_to_process = batch.get_entities_to_process()
        if not entities_to_process:
            return

        # Build textual representations
        processed = await text_builder.build_for_batch(entities_to_process, sync_context)

        # Filter empty representations
        processed = await self._filter_empty_representations(processed, sync_context)

        sync_context.logger.debug(
            f"[{self.name}] Built text representations for {len(processed)} entities"
        )

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

    # -------------------------------------------------------------------------
    # Retry Logic (availability retries - same as VectorDBHandler)
    # -------------------------------------------------------------------------

    async def _execute_with_availability_retry(
        self,
        operation: Callable,
        operation_name: str,
        sync_context: "SyncContext",
        max_retries: int = 4,
    ) -> None:
        """Execute operation with retries ONLY for availability issues.

        Logic:
        - If service is down (ConnectionRefused, 503), wait and retry.
        - If permanent error (400, DataError), fail immediately.

        Args:
            operation: Async callable to execute
            operation_name: Name for logging
            sync_context: Sync context
            max_retries: Maximum retry attempts

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

                # Fail fast on non-network errors
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
