"""Snapshot source for replaying raw data captures.

This source reads entities from the raw data storage structure:
    {path}/
    ├── manifest.json           # Sync metadata
    ├── entities/
    │   └── {entity_id}.json    # One file per entity
    └── files/
        └── {entity_id}_{name}  # File attachments

Usage:
    Create a source connection with:
    - short_name: "snapshot"
    - config: {"path": "/path/to/raw/sync-id"}
    - credentials: {"placeholder": "snapshot"} (required for API)
"""

import importlib
import json
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from airweave.platform.configs.auth import SnapshotAuthConfig
from airweave.platform.configs.config import SnapshotConfig
from airweave.platform.decorators import source
from airweave.platform.entities._base import BaseEntity
from airweave.platform.sources._base import BaseSource
from airweave.schemas.source_connection import AuthenticationMethod


@source(
    name="Snapshot",
    short_name="snapshot",
    auth_methods=[AuthenticationMethod.DIRECT],
    oauth_type=None,
    auth_config_class="SnapshotAuthConfig",
    config_class="SnapshotConfig",
    labels=["Internal", "Replay"],
    supports_continuous=False,
)
class SnapshotSource(BaseSource):
    """Source that replays entities from raw data captures.

    Reads entities from local filesystem.
    Supports file restoration for FileEntity types.
    """

    def __init__(self):
        """Initialize snapshot source."""
        super().__init__()
        self.path: str = ""
        self.restore_files: bool = True
        self._temp_dir: Optional[Path] = None
        self._base_path: Optional[Path] = None

    @classmethod
    async def create(
        cls,
        credentials: Optional[Union[Dict[str, Any], SnapshotAuthConfig]] = None,
        config: Optional[Union[Dict[str, Any], SnapshotConfig]] = None,
    ) -> "SnapshotSource":
        """Create a new snapshot source instance.

        Args:
            credentials: Optional SnapshotAuthConfig (placeholder for API compatibility)
            config: SnapshotConfig with path to raw data directory

        Returns:
            Configured SnapshotSource instance
        """
        instance = cls()

        # Extract config
        if config is None:
            raise ValueError("config with 'path' is required for SnapshotSource")

        if isinstance(config, dict):
            instance.path = config.get("path", "")
            instance.restore_files = config.get("restore_files", True)
        else:
            instance.path = config.path
            instance.restore_files = config.restore_files

        if not instance.path:
            raise ValueError("path is required in config")

        # Set up base path
        instance._base_path = Path(instance.path)

        return instance

    async def _read_json(self, relative_path: str) -> Dict[str, Any]:
        """Read a JSON file from the snapshot directory."""
        file_path = self._base_path / relative_path
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def _list_entity_files(self) -> List[str]:
        """List all entity JSON files."""
        entities_dir = self._base_path / "entities"
        if not entities_dir.exists():
            return []
        return [
            f"entities/{f.name}"
            for f in entities_dir.iterdir()
            if f.is_file() and f.suffix == ".json"
        ]

    async def _restore_file(self, stored_file_path: str) -> Optional[str]:
        """Restore a file attachment to temp directory.

        Args:
            stored_file_path: Relative path to file in storage

        Returns:
            Local path to restored file, or None if restoration failed
        """
        if not self.restore_files:
            return None

        try:
            source_path = self._base_path / stored_file_path
            if not source_path.exists():
                return None

            # Create temp directory if needed
            if self._temp_dir is None:
                self._temp_dir = Path(tempfile.mkdtemp(prefix="snapshot_files_"))

            # Extract filename from path
            filename = source_path.name
            local_path = self._temp_dir / filename
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            with open(source_path, "rb") as src, open(local_path, "wb") as dst:
                dst.write(src.read())

            return str(local_path)

        except Exception as e:
            self.logger.warning(f"Failed to restore file {stored_file_path}: {e}")
            return None

    def _reconstruct_entity(
        self, entity_dict: Dict[str, Any], restored_file_path: Optional[str] = None
    ) -> BaseEntity:
        """Reconstruct a BaseEntity from stored dict.

        Args:
            entity_dict: Dict with entity data and __entity_class__/__entity_module__
            restored_file_path: Optional local path to restored file

        Returns:
            Reconstructed entity instance
        """
        # Make a copy to avoid mutating
        entity_dict = dict(entity_dict)

        # Extract metadata
        entity_class_name = entity_dict.pop("__entity_class__", None)
        entity_module = entity_dict.pop("__entity_module__", None)
        entity_dict.pop("__captured_at__", None)
        entity_dict.pop("__stored_file__", None)

        if not entity_class_name or not entity_module:
            raise ValueError("Entity dict missing __entity_class__ or __entity_module__")

        # Import entity class
        try:
            module = importlib.import_module(entity_module)
            entity_class = getattr(module, entity_class_name)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Cannot reconstruct {entity_module}.{entity_class_name}: {e}")

        # Update local_path if file was restored
        if restored_file_path:
            entity_dict["local_path"] = restored_file_path

        return entity_class(**entity_dict)

    async def generate_entities(self) -> AsyncGenerator[BaseEntity, None]:
        """Generate entities from raw data storage.

        Reads manifest and iterates over all entity JSON files,
        reconstructing BaseEntity objects and optionally restoring files.
        """
        # Read manifest for logging
        try:
            manifest = await self._read_json("manifest.json")
            self.logger.info(
                f"Replaying snapshot: {manifest.get('entity_count', '?')} entities "
                f"from {manifest.get('source_short_name', 'unknown')} source"
            )
        except Exception as e:
            self.logger.warning(f"Could not read manifest: {e}")

        # List and process entity files
        entity_files = await self._list_entity_files()
        self.logger.info(f"Found {len(entity_files)} entity files to replay")

        for file_path in entity_files:
            try:
                entity_dict = await self._read_json(file_path)

                # Check if file needs to be restored
                stored_file = entity_dict.get("__stored_file__")
                restored_path = None
                if stored_file and self.restore_files:
                    restored_path = await self._restore_file(stored_file)

                # Reconstruct entity
                entity = self._reconstruct_entity(entity_dict, restored_path)
                yield entity

            except Exception as e:
                self.logger.warning(f"Failed to reconstruct entity from {file_path}: {e}")
                continue

    async def validate(self) -> bool:
        """Validate that the snapshot path exists and is readable."""
        self.logger.info(f"Validating snapshot source with path: {self.path}")
        if not self.path:
            self.logger.error("Snapshot validation failed: path is empty")
            return False

        if not self._base_path or not self._base_path.exists():
            self.logger.error(f"Snapshot validation failed: path does not exist: {self.path}")
            return False

        try:
            manifest = await self._read_json("manifest.json")
            return "sync_id" in manifest
        except Exception as e:
            self.logger.error(f"Snapshot validation failed: {e}")
            return False

    def cleanup(self) -> None:
        """Clean up temp files."""
        if self._temp_dir and self._temp_dir.exists():
            import shutil

            shutil.rmtree(self._temp_dir)
            self._temp_dir = None
