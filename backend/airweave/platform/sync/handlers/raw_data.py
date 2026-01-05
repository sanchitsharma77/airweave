"""Raw data storage handler for entity persistence.

Stores raw entity data to the storage backend (local filesystem or cloud storage)
for debugging, replay, and audit purposes.
"""

from typing import TYPE_CHECKING, List

from airweave.platform.sync.actions.types import DeleteAction, InsertAction, UpdateAction
from airweave.platform.sync.handlers.base import ActionHandler

if TYPE_CHECKING:
    from airweave.platform.sync.context import SyncContext


class RawDataHandler(ActionHandler):
    """Handler for raw entity storage.

    Stores entity JSON to the raw data store (entity-level files).
    This enables replay of syncs with different configurations and provides
    an audit trail of what was synced.

    Storage structure:
        raw/{sync_id}/
        ├── manifest.json
        ├── entities/
        │   └── {entity_id}.json
        └── files/
            └── {entity_id}_{name}.{ext}
    """

    def __init__(self):
        """Initialize handler with manifest tracking."""
        self._manifest_initialized = False

    @property
    def name(self) -> str:
        """Handler name."""
        return "raw_data"

    async def _ensure_manifest(self, sync_context: "SyncContext") -> None:
        """Ensure manifest exists for this sync (called once per sync)."""
        if self._manifest_initialized:
            return

        from airweave.platform.sync import raw_data_service

        try:
            await raw_data_service.upsert_manifest(sync_context)
            self._manifest_initialized = True
        except Exception as e:
            sync_context.logger.warning(f"[RawData] Failed to upsert manifest: {e}")

    async def handle_inserts(
        self,
        actions: List[InsertAction],
        sync_context: "SyncContext",
    ) -> None:
        """Store inserted entities to raw data store.

        Args:
            actions: Insert actions (uses entity, not chunk_entities)
            sync_context: Sync context
        """
        if not actions:
            return

        # Ensure manifest exists (lazily created on first write)
        await self._ensure_manifest(sync_context)

        from airweave.platform.sync import raw_data_service

        # Store the original entities (before chunking)
        entities = [action.entity for action in actions]

        try:
            count = await raw_data_service.upsert_entities(
                entities=entities,
                sync_context=sync_context,
            )
            if count:
                sync_context.logger.debug(f"[RawData] Stored {count} inserted entities")
        except Exception as e:
            # Raw data storage is non-critical - log and continue
            # We don't want raw data failures to fail the sync
            sync_context.logger.warning(f"[RawData] Failed to store inserted entities: {e}")

    async def handle_updates(
        self,
        actions: List[UpdateAction],
        sync_context: "SyncContext",
    ) -> None:
        """Update entities in raw data store.

        Args:
            actions: Update actions (uses entity, not chunk_entities)
            sync_context: Sync context
        """
        if not actions:
            return

        # Ensure manifest exists (lazily created on first write)
        await self._ensure_manifest(sync_context)

        from airweave.platform.sync import raw_data_service

        entities = [action.entity for action in actions]

        try:
            count = await raw_data_service.upsert_entities(
                entities=entities,
                sync_context=sync_context,
            )
            if count:
                sync_context.logger.debug(f"[RawData] Updated {count} entities")
        except Exception as e:
            sync_context.logger.warning(f"[RawData] Failed to update entities: {e}")

    async def handle_deletes(
        self,
        actions: List[DeleteAction],
        sync_context: "SyncContext",
    ) -> None:
        """Delete entities from raw data store.

        Args:
            actions: Delete actions
            sync_context: Sync context
        """
        if not actions:
            return

        from airweave.platform.sync import raw_data_service

        entity_ids = [str(action.entity_id) for action in actions]

        try:
            deleted = await raw_data_service.delete_entities(
                entity_ids=entity_ids,
                sync_context=sync_context,
            )
            if deleted:
                sync_context.logger.debug(f"[RawData] Deleted {deleted} entities")
        except Exception as e:
            sync_context.logger.warning(f"[RawData] Failed to delete entities: {e}")

    async def handle_orphan_cleanup(
        self,
        orphan_entity_ids: List[str],
        sync_context: "SyncContext",
    ) -> None:
        """Delete orphaned entities from raw data store.

        Args:
            orphan_entity_ids: Entity IDs to delete
            sync_context: Sync context
        """
        if not orphan_entity_ids:
            return

        from airweave.platform.sync import raw_data_service

        try:
            deleted = await raw_data_service.delete_entities(
                entity_ids=orphan_entity_ids,
                sync_context=sync_context,
            )
            if deleted:
                sync_context.logger.debug(f"[RawData] Deleted {deleted} orphaned entities")
        except Exception as e:
            sync_context.logger.warning(f"[RawData] Failed to delete orphaned entities: {e}")
