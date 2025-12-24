"""Unified storage backend for Airweave.

Provides a single abstract interface with Filesystem and Azure Blob implementations.
All methods are async-first to work well with FastAPI.

Usage:
    from airweave.platform.storage import get_storage_backend

    backend = get_storage_backend()  # Auto-resolves based on ENVIRONMENT
    await backend.write_json("snapshots/my_data/manifest.json", {"key": "value"})
    data = await backend.read_json("snapshots/my_data/manifest.json")
"""

import json
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Union

from airweave.core.logging import logger
from airweave.platform.storage.exceptions import (
    StorageException,
    StorageNotFoundError,
)


class StorageBackend(ABC):
    """Abstract storage backend interface.

    Provides a simple, unified API for storing:
    - JSON data (serialized dicts)
    - Binary files (bytes)

    All paths are relative strings (e.g., "snapshots/gmail_abc123/manifest.json").
    Implementations handle the actual storage location.
    """

    @abstractmethod
    async def write_json(self, path: str, data: Dict[str, Any]) -> None:
        """Write JSON data to storage.

        Args:
            path: Relative path (e.g., "snapshots/data.json")
            data: Dict to serialize as JSON
        """
        pass

    @abstractmethod
    async def read_json(self, path: str) -> Dict[str, Any]:
        """Read JSON data from storage.

        Args:
            path: Relative path

        Returns:
            Deserialized dict

        Raises:
            StorageNotFoundError: If path doesn't exist
        """
        pass

    @abstractmethod
    async def write_file(self, path: str, content: bytes) -> None:
        """Write binary content to storage.

        Args:
            path: Relative path
            content: Binary content
        """
        pass

    @abstractmethod
    async def read_file(self, path: str) -> bytes:
        """Read binary content from storage.

        Args:
            path: Relative path

        Returns:
            Binary content

        Raises:
            StorageNotFoundError: If path doesn't exist
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if a path exists.

        Args:
            path: Relative path

        Returns:
            True if exists
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete a file or directory.

        Args:
            path: Relative path

        Returns:
            True if deleted, False if didn't exist
        """
        pass

    @abstractmethod
    async def list_files(self, prefix: str = "") -> List[str]:
        """List files under a prefix (recursive).

        Args:
            prefix: Path prefix to filter by

        Returns:
            List of relative paths
        """
        pass

    @abstractmethod
    async def list_dirs(self, prefix: str = "") -> List[str]:
        """List immediate subdirectories under a prefix.

        Args:
            prefix: Path prefix

        Returns:
            List of directory paths
        """
        pass


class FilesystemBackend(StorageBackend):
    """Filesystem-based storage backend.

    Works with:
    - Local development: ./local_storage
    - Kubernetes: PVC-mounted path (e.g., /data/airweave-storage)

    Thread-safe for basic operations (relies on OS-level file locking).
    """

    def __init__(self, base_path: Union[str, Path]):
        """Initialize filesystem backend.

        Args:
            base_path: Root directory for all storage operations
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"FilesystemBackend initialized at {self.base_path}")

    def _resolve(self, path: str) -> Path:
        """Resolve relative path to absolute."""
        # Normalize path separators
        normalized = path.replace("/", os.sep)
        return self.base_path / normalized

    async def write_json(self, path: str, data: Dict[str, Any]) -> None:
        """Write JSON to filesystem."""
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            raise StorageException(f"Failed to write JSON to {path}: {e}")

    async def read_json(self, path: str) -> Dict[str, Any]:
        """Read JSON from filesystem."""
        full_path = self._resolve(path)

        if not full_path.exists():
            raise StorageNotFoundError(f"Path not found: {path}")

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise StorageException(f"Invalid JSON at {path}: {e}")
        except Exception as e:
            raise StorageException(f"Failed to read JSON from {path}: {e}")

    async def write_file(self, path: str, content: bytes) -> None:
        """Write binary content to filesystem."""
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(full_path, "wb") as f:
                f.write(content)
        except Exception as e:
            raise StorageException(f"Failed to write file to {path}: {e}")

    async def read_file(self, path: str) -> bytes:
        """Read binary content from filesystem."""
        full_path = self._resolve(path)

        if not full_path.exists():
            raise StorageNotFoundError(f"Path not found: {path}")

        try:
            with open(full_path, "rb") as f:
                return f.read()
        except Exception as e:
            raise StorageException(f"Failed to read file from {path}: {e}")

    async def exists(self, path: str) -> bool:
        """Check if path exists on filesystem."""
        return self._resolve(path).exists()

    async def delete(self, path: str) -> bool:
        """Delete file or directory from filesystem."""
        full_path = self._resolve(path)

        if not full_path.exists():
            return False

        try:
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to delete {path}: {e}")
            return False

    async def list_files(self, prefix: str = "") -> List[str]:
        """List all files under prefix (recursive)."""
        base = self._resolve(prefix) if prefix else self.base_path
        if not base.exists():
            return []

        files = []
        for item in base.rglob("*"):
            if item.is_file():
                rel_path = str(item.relative_to(self.base_path))
                # Normalize to forward slashes for consistency
                files.append(rel_path.replace(os.sep, "/"))

        return sorted(files)

    async def list_dirs(self, prefix: str = "") -> List[str]:
        """List immediate subdirectories under prefix."""
        base = self._resolve(prefix) if prefix else self.base_path
        if not base.exists():
            return []

        dirs = []
        for item in base.iterdir():
            if item.is_dir():
                rel_path = str(item.relative_to(self.base_path))
                dirs.append(rel_path.replace(os.sep, "/"))

        return sorted(dirs)


class AzureBlobBackend(StorageBackend):
    """Azure Blob Storage backend.

    Uses DefaultAzureCredential for authentication (works with Azure CLI,
    managed identity, service principal, etc.).
    """

    def __init__(
        self,
        storage_account: str,
        container: str,
        prefix: str = "",
    ):
        """Initialize Azure Blob backend.

        Args:
            storage_account: Azure storage account name
            container: Container name
            prefix: Optional prefix for all paths
        """
        self.storage_account = storage_account
        self.container_name = container
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._blob_service_client = None
        self._container_client = None

        logger.debug(
            f"AzureBlobBackend initialized: {storage_account}/{container}"
            f"{f'/{prefix}' if prefix else ''}"
        )

    @property
    def blob_service_client(self):
        """Lazy-load blob service client."""
        if self._blob_service_client is None:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.storage.blob import BlobServiceClient

                account_url = f"https://{self.storage_account}.blob.core.windows.net"
                credential = DefaultAzureCredential()
                self._blob_service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=credential,
                )
            except ImportError as e:
                raise StorageException(
                    "Azure SDK not installed. Install with: "
                    "pip install azure-storage-blob azure-identity"
                ) from e
        return self._blob_service_client

    @property
    def container_client(self):
        """Lazy-load container client."""
        if self._container_client is None:
            self._container_client = self.blob_service_client.get_container_client(
                self.container_name
            )
        return self._container_client

    def _resolve(self, path: str) -> str:
        """Resolve path with prefix."""
        return f"{self.prefix}{path}"

    async def write_json(self, path: str, data: Dict[str, Any]) -> None:
        """Write JSON to Azure Blob."""
        blob_path = self._resolve(path)
        try:
            content = json.dumps(data, indent=2, default=str)
            blob_client = self.container_client.get_blob_client(blob_path)
            blob_client.upload_blob(content, overwrite=True)
        except Exception as e:
            raise StorageException(f"Failed to write JSON to {path}: {e}")

    async def read_json(self, path: str) -> Dict[str, Any]:
        """Read JSON from Azure Blob."""
        blob_path = self._resolve(path)
        try:
            blob_client = self.container_client.get_blob_client(blob_path)
            if not blob_client.exists():
                raise StorageNotFoundError(f"Path not found: {path}")
            content = blob_client.download_blob().readall().decode("utf-8")
            return json.loads(content)
        except StorageNotFoundError:
            raise
        except json.JSONDecodeError as e:
            raise StorageException(f"Invalid JSON at {path}: {e}")
        except Exception as e:
            raise StorageException(f"Failed to read JSON from {path}: {e}")

    async def write_file(self, path: str, content: bytes) -> None:
        """Write binary content to Azure Blob."""
        blob_path = self._resolve(path)
        try:
            blob_client = self.container_client.get_blob_client(blob_path)
            blob_client.upload_blob(content, overwrite=True)
        except Exception as e:
            raise StorageException(f"Failed to write file to {path}: {e}")

    async def read_file(self, path: str) -> bytes:
        """Read binary content from Azure Blob."""
        blob_path = self._resolve(path)
        try:
            blob_client = self.container_client.get_blob_client(blob_path)
            if not blob_client.exists():
                raise StorageNotFoundError(f"Path not found: {path}")
            return blob_client.download_blob().readall()
        except StorageNotFoundError:
            raise
        except Exception as e:
            raise StorageException(f"Failed to read file from {path}: {e}")

    async def exists(self, path: str) -> bool:
        """Check if blob exists."""
        blob_path = self._resolve(path)
        try:
            blob_client = self.container_client.get_blob_client(blob_path)
            return blob_client.exists()
        except Exception:
            return False

    async def delete(self, path: str) -> bool:
        """Delete blob or all blobs under prefix."""
        blob_path = self._resolve(path)

        deleted_count = 0
        try:
            # Try direct blob delete first
            blob_client = self.container_client.get_blob_client(blob_path)
            if blob_client.exists():
                blob_client.delete_blob()
                return True

            # If not a blob, try as prefix (directory-like)
            prefix = blob_path if blob_path.endswith("/") else blob_path + "/"
            for blob in self.container_client.list_blobs(name_starts_with=prefix):
                self.container_client.get_blob_client(blob.name).delete_blob()
                deleted_count += 1

            return deleted_count > 0

        except Exception as e:
            logger.error(f"Failed to delete {path}: {e}")
            return False

    async def list_files(self, prefix: str = "") -> List[str]:
        """List all blobs under prefix."""
        full_prefix = self._resolve(prefix)
        if prefix and not full_prefix.endswith("/"):
            full_prefix += "/"

        files = []
        try:
            for blob in self.container_client.list_blobs(name_starts_with=full_prefix):
                # Return path relative to our prefix
                rel_path = blob.name
                if self.prefix and rel_path.startswith(self.prefix):
                    rel_path = rel_path[len(self.prefix) :]
                files.append(rel_path)
        except Exception as e:
            logger.error(f"Failed to list files in {prefix}: {e}")

        return sorted(files)

    async def list_dirs(self, prefix: str = "") -> List[str]:
        """List 'directories' under prefix (unique path components)."""
        full_prefix = self._resolve(prefix)
        if not full_prefix.endswith("/"):
            full_prefix += "/"

        dirs = set()
        try:
            for blob in self.container_client.list_blobs(name_starts_with=full_prefix):
                # Extract first path component after prefix
                rel_path = blob.name[len(full_prefix) :]
                if "/" in rel_path:
                    dir_name = rel_path.split("/")[0]
                    full_dir = f"{prefix}/{dir_name}" if prefix else dir_name
                    dirs.add(full_dir)
        except Exception as e:
            logger.error(f"Failed to list dirs in {prefix}: {e}")

        return sorted(dirs)
