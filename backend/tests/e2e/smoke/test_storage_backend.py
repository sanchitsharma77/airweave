"""
Smoke test for storage backend verification.

Tests that the configured storage backend is working correctly by:
1. Running a sync that writes data to storage (ARF files)
2. Directly checking the local_storage directory for ARF files
3. Verifying entity data can be read from storage

NOTE: These tests only run in local environment where local_storage is mounted.
For remote environments, storage is verified implicitly through successful syncs.
"""

import asyncio
import json
import uuid
from pathlib import Path

import httpx
import pytest


def get_local_storage_path() -> Path:
    """Get the local_storage path from the repo root.

    Path: backend/tests/e2e/smoke/test_storage_backend.py
    Levels: smoke -> e2e -> tests -> backend -> repo_root
    """
    test_file = Path(__file__)
    # smoke/ -> e2e/ -> tests/ -> backend/ -> repo_root/
    repo_root = test_file.parent.parent.parent.parent.parent
    return repo_root / "local_storage"


@pytest.mark.asyncio
@pytest.mark.local_only
class TestStorageBackend:
    """Test suite for storage backend verification.

    Checks the mounted local_storage directory to verify ARF files are written.
    Only runs in local environment where the storage is accessible.
    """

    async def test_health_check_passes(self, api_client: httpx.AsyncClient):
        """Test that health check passes."""
        response = await api_client.get("/health")

        assert response.status_code == 200, f"Health check failed: {response.text}"

        health = response.json()
        assert health.get("status") == "healthy", f"Unhealthy status: {health}"

    async def test_sync_writes_arf_files_to_storage(self, api_client: httpx.AsyncClient, config):
        """Test that sync writes ARF files to the storage backend.

        This test:
        1. Creates a stub connection and triggers a sync
        2. Waits for sync to complete
        3. Checks local_storage/raw/{sync_id}/ for ARF files
        4. Verifies manifest and entity files exist and are readable
        """
        # Check if we're in local environment with accessible storage
        storage_path = get_local_storage_path()
        if not storage_path.exists():
            pytest.skip(
                f"local_storage not found at {storage_path}. "
                "This test only runs in local environment."
            )

        collection_name = f"Storage Test {uuid.uuid4().hex[:8]}"

        # Step 1: Create test collection
        collection_response = await api_client.post(
            "/collections/", json={"name": collection_name}
        )
        assert collection_response.status_code == 200, (
            f"Failed to create collection: {collection_response.text}"
        )
        collection = collection_response.json()
        collection_id = collection["readable_id"]

        try:
            # Step 2: Check stub source is available
            sources_response = await api_client.get("/sources/")
            assert sources_response.status_code == 200
            sources = sources_response.json()
            source_names = [s["short_name"] for s in sources]

            if "stub" not in source_names:
                pytest.skip(
                    "Stub source not available (ENABLE_INTERNAL_SOURCES=false). "
                    "Storage verification requires internal sources."
                )

            # Step 3: Create stub connection and trigger sync
            connection_response = await api_client.post(
                "/source-connections",
                json={
                    "name": f"Storage Test {uuid.uuid4().hex[:8]}",
                    "short_name": "stub",
                    "readable_collection_id": collection_id,
                    "authentication": {"credentials": {}},
                    "sync_immediately": True,
                },
            )

            if connection_response.status_code != 200:
                pytest.skip(f"Could not create stub connection: {connection_response.text}")

            connection = connection_response.json()
            connection_id = connection["id"]
            sync_id = connection.get("sync_id")

            try:
                # Step 4: Wait for sync to complete
                max_wait = 120
                poll_interval = 3
                elapsed = 0
                sync_completed = False

                while elapsed < max_wait:
                    await asyncio.sleep(poll_interval)
                    elapsed += poll_interval

                    status_response = await api_client.get(
                        f"/source-connections/{connection_id}"
                    )
                    if status_response.status_code != 200:
                        continue

                    conn_details = status_response.json()
                    status = conn_details.get("status")
                    sync_id = conn_details.get("sync_id") or sync_id

                    if status == "active":
                        sync_completed = True
                        break
                    elif status == "error":
                        pytest.fail(f"Sync failed: {conn_details}")

                assert sync_completed, f"Sync did not complete within {max_wait}s"
                assert sync_id, "No sync_id returned"

                # Step 5: VERIFY STORAGE - Check local_storage for ARF files
                arf_path = storage_path / "raw" / str(sync_id)

                # Wait a moment for filesystem writes to complete
                await asyncio.sleep(2)

                assert arf_path.exists(), (
                    f"ARF directory not found at {arf_path}. "
                    "Sync completed but ARF files were not written!"
                )

                # Check manifest exists
                manifest_path = arf_path / "manifest.json"
                assert manifest_path.exists(), (
                    f"Manifest not found at {manifest_path}. "
                    "ARF directory exists but manifest is missing!"
                )

                # Read and verify manifest
                with open(manifest_path) as f:
                    manifest = json.load(f)
                assert manifest, "Manifest is empty"

                # Check entities directory
                entities_path = arf_path / "entities"
                assert entities_path.exists(), (
                    f"Entities directory not found at {entities_path}"
                )

                # List and verify entity files
                entity_files = list(entities_path.glob("*.json"))
                assert len(entity_files) > 0, (
                    f"No entity files found in {entities_path}. "
                    "Sync reported success but no entities were written!"
                )

                # Read first entity to verify content
                with open(entity_files[0]) as f:
                    entity = json.load(f)
                assert entity, f"Entity file {entity_files[0]} is empty"
                assert "entity_id" in entity or "id" in entity, (
                    f"Entity missing identifier: {entity.keys()}"
                )

                # SUCCESS: Storage verified
                # - ARF directory exists
                # - Manifest exists and is valid JSON
                # - Entity files exist and are readable

            finally:
                # Cleanup connection
                try:
                    await api_client.delete(f"/source-connections/{connection_id}")
                except Exception:
                    pass

        finally:
            # Cleanup collection
            try:
                await api_client.delete(f"/collections/{collection_id}")
            except Exception:
                pass

    async def test_storage_directory_accessible(self, api_client: httpx.AsyncClient, config):
        """Basic test that local_storage directory is accessible."""
        storage_path = get_local_storage_path()

        if not storage_path.exists():
            pytest.skip(
                f"local_storage not found at {storage_path}. "
                "This test only runs in local environment."
            )

        # Verify we can list the directory
        assert storage_path.is_dir(), f"{storage_path} is not a directory"

        # Check raw directory exists or can be created
        raw_path = storage_path / "raw"
        # raw/ may not exist until first sync, that's OK
        if raw_path.exists():
            assert raw_path.is_dir(), f"{raw_path} is not a directory"
