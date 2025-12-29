"""Cleanup service for orphaned entities and temp files."""

import asyncio
import os
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Callable, Dict, List

from airweave import crud, models
from airweave.db.session import get_db_context
from airweave.platform.entities._base import FileEntity
from airweave.platform.sync.exceptions import SyncFailureError

if TYPE_CHECKING:
    from airweave.platform.sync.context import SyncContext


class CleanupService:
    """Service for cleaning up orphaned entities and temporary files.

    Handles:
    - Orphaned entity detection and removal (entities in DB not seen during sync)
    - Progressive temp file cleanup (after each batch)
    - Final temp directory cleanup (safety net in finally block)
    """

    # ------------------------------------------------------------------------------------
    # Orphaned Entity Cleanup
    # ------------------------------------------------------------------------------------

    async def cleanup_orphaned_entities(self, sync_context: "SyncContext") -> None:
        """Remove entities from database/destinations that were not encountered during sync."""
        try:
            orphaned = await self._identify_orphaned_entities(sync_context)

            if not orphaned:
                return

            await self._remove_orphaned_entities(orphaned, sync_context)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            sync_context.logger.error(f"💥 Cleanup failed: {str(e)}", exc_info=True)
            raise

    async def _identify_orphaned_entities(self, sync_context: "SyncContext") -> List[models.Entity]:
        """Fetch stored entities and filter to those not encountered during sync."""
        query_start = time.time()
        sync_context.logger.info(
            "🔍 [ORPHAN CLEANUP] Fetching all stored entities from database..."
        )

        async with get_db_context() as db:
            stored_entities = await crud.entity.get_by_sync_id(db=db, sync_id=sync_context.sync.id)

        query_duration = time.time() - query_start
        sync_context.logger.info(
            f"✅ [ORPHAN CLEANUP] Retrieved {len(stored_entities)} stored entities "
            f"in {query_duration:.2f}s"
        )

        if not stored_entities:
            return []

        if not sync_context.entity_tracker:
            sync_context.logger.warning(
                "Entity tracker not available in sync context - skipping orphan detection"
            )
            return []

        compare_start = time.time()
        encountered_ids_map = sync_context.entity_tracker.get_encountered_ids()
        encountered_ids = set().union(*encountered_ids_map.values())
        orphaned = [e for e in stored_entities if e.entity_id not in encountered_ids]
        compare_duration = time.time() - compare_start

        sync_context.logger.info(
            f"📊 [ORPHAN CLEANUP] Analysis complete in {compare_duration:.2f}s: "
            f"{len(encountered_ids)} encountered, {len(orphaned)} orphaned "
            f"out of {len(stored_entities)} total"
        )

        return orphaned

    async def _remove_orphaned_entities(
        self, orphaned_entities: List[models.Entity], sync_context: "SyncContext"
    ) -> None:
        """Remove orphaned entities from destinations and database, update trackers."""
        entity_ids = [e.entity_id for e in orphaned_entities]
        db_ids = [e.id for e in orphaned_entities]

        # Delete all chunks for these parent entities
        for destination in sync_context.destinations:
            await self._execute_safe(
                operation=lambda dest=destination: dest.bulk_delete_by_parent_ids(
                    entity_ids, sync_context.sync.id
                ),
                operation_name="orphan cleanup delete",
                sync_context=sync_context,
            )

        async with get_db_context() as db:
            await crud.entity.bulk_remove(db=db, ids=db_ids, ctx=sync_context.ctx)
            await db.commit()

        # Update entity tracker with deletion counts
        await self._update_entity_tracker(orphaned_entities, sync_context)

    async def _execute_safe(
        self,
        operation: Callable,
        operation_name: str,
        sync_context: "SyncContext",
    ) -> None:
        """Execute operation with error logging (simple retry wrapper replacement)."""
        try:
            await operation()
        except Exception as e:
            sync_context.logger.warning(f"Cleanup {operation_name} failed: {e}")
            raise

    async def _update_entity_tracker(
        self, orphaned_entities: List[models.Entity], sync_context: "SyncContext"
    ) -> None:
        """Update entity tracker with deletion counts by entity definition."""
        if not sync_context.entity_tracker:
            return

        counts_by_def = defaultdict(int)
        for entity in orphaned_entities:
            if hasattr(entity, "entity_definition_id") and entity.entity_definition_id:
                counts_by_def[entity.entity_definition_id] += 1

        for def_id, count in counts_by_def.items():
            await sync_context.entity_tracker.record_deletes(
                entity_definition_id=def_id, count=count
            )

    # ------------------------------------------------------------------------------------
    # Temp File Cleanup
    # ------------------------------------------------------------------------------------

    async def cleanup_processed_files(
        self,
        partitions: Dict[str, Any],
        sync_context: "SyncContext",
    ) -> None:
        """Delete temporary files after batch processing (progressive cleanup).

        Called after entities are persisted to destinations and database.
        Raises SyncFailureError if deletion fails to prevent disk space issues.

        Args:
            partitions: Entity partitions from action determination
            sync_context: Sync context with logger
        """
        entities_to_clean = partitions["inserts"] + partitions["updates"]
        cleaned_count = 0
        failed_deletions = []

        for entity in entities_to_clean:
            # Only clean up file entities
            if not isinstance(entity, FileEntity):
                continue

            # FileEntity without local_path is a programming error
            if not hasattr(entity, "local_path") or not entity.local_path:
                raise SyncFailureError(
                    f"FileEntity {entity.__class__.__name__}[{entity.entity_id}] "
                    f"has no local_path after processing. This indicates download/save failed "
                    f"but entity was not filtered out."
                )

            local_path = entity.local_path

            try:
                if os.path.exists(local_path):
                    os.remove(local_path)

                    if os.path.exists(local_path):
                        failed_deletions.append(local_path)
                        sync_context.logger.error(f"Failed to delete temp file: {local_path}")
                    else:
                        cleaned_count += 1
                        sync_context.logger.debug(f"Deleted temp file: {local_path}")

            except Exception as e:
                failed_deletions.append(local_path)
                sync_context.logger.error(f"Error deleting temp file {local_path}: {e}")

        if cleaned_count > 0:
            sync_context.logger.debug(f"Progressive cleanup: deleted {cleaned_count} temp files")

        if failed_deletions:
            raise SyncFailureError(
                f"Failed to delete {len(failed_deletions)} temp files. "
                f"This can cause pod eviction. Files: {failed_deletions[:5]}"
            )

    async def cleanup_temp_files(self, sync_context: "SyncContext") -> None:
        """Remove entire sync_job_id directory (final cleanup safety net).

        Called in orchestrator's finally block to ensure cleanup happens even if
        pipeline fails. Removes entire /tmp/airweave/processing/{sync_job_id}/ directory.

        Args:
            sync_context: Sync context with source and logger

        Note:
            Some sources don't download files (e.g., Airtable, Jira without attachments).
            For these sources, file_downloader won't be set, which is expected.
        """
        try:
            if not hasattr(sync_context.source, "file_downloader"):
                sync_context.logger.debug(
                    "Source has no file downloader (API-only source), skipping temp cleanup"
                )
                return

            downloader = sync_context.source.file_downloader
            if downloader is None:
                sync_context.logger.debug("File downloader not initialized, skipping temp cleanup")
                return

            await downloader.cleanup_sync_directory(sync_context.logger)

        except Exception as e:
            sync_context.logger.warning(
                f"Final temp file cleanup failed (non-fatal): {e}", exc_info=True
            )


# Singleton instance
cleanup_service = CleanupService()
