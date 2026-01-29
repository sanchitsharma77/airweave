"""
Smoke test for storage backend verification.

Tests that the configured storage backend is working correctly by:
1. Running a sync that writes data to storage (ARF files)
2. Directly checking the local_storage directory for ARF files
3. Verifying entity data can be read from storage

Runs in local environment only (TEST_ENV=local) via @pytest.mark.local_only.
Skipped automatically in deployed environments (TEST_ENV=dev/prod).
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
    repo_root = test_file.parent.parent.parent.parent.parent
    return repo_root / "local_storage"


@pytest.mark.asyncio
@pytest.mark.local_only
class TestStorageBackend:
    """Test suite for storage backend verification.

    @pytest.mark.local_only ensures this only runs when TEST_ENV=local.
    In deployed environments (TEST_ENV=dev), this is automatically skipped.
    """

    async def test_health_check_passes(self, api_client: httpx.AsyncClient):
        """Test that health check passes."""
        response = await api_client.get("/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        health = response.json()
        assert health.get("status") == "healthy", f"Unhealthy status: {health}"

    async def test_sync_writes_arf_files_to_storage(self, api_client: httpx.AsyncClient, config):
        """Test that sync writes ARF files to the local storage backend.

        1. Creates a stub connection and triggers a sync
        2. Waits for sync to complete
        3. Checks local_storage/raw/{sync_id}/ for ARF files
        4. Verifies manifest and entity files exist and are readable
        """
        storage_path = get_local_storage_path()
        collection_name = f"Storage Test {uuid.uuid4().hex[:8]}"

        # Create test collection
        collection_response = await api_client.post(
            "/collections/", json={"name": collection_name}
        )
        assert collection_response.status_code == 200, (
            f"Failed to create collection: {collection_response.text}"
        )
        collection = collection_response.json()
        collection_id = collection["readable_id"]

        try:
            # Check stub source is available
            sources_response = await api_client.get("/sources/")
            assert sources_response.status_code == 200, f"Sources API failed: {sources_response.text}"
            sources = sources_response.json()
            source_names = [s["short_name"] for s in sources]
            assert "stub" in source_names, (
                f"Stub source not available. ENABLE_INTERNAL_SOURCES must be true. "
                f"Available sources: {source_names}"
            )

            # Create stub connection and trigger sync
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
            assert connection_response.status_code == 200, (
                f"Failed to create stub connection: {connection_response.text}"
            )

            connection = connection_response.json()
            connection_id = connection["id"]
            sync_id = connection.get("sync_id")

            try:
                # Wait for sync to complete
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
                        pytest.fail(f"Sync failed with error: {conn_details}")

                assert sync_completed, f"Sync did not complete within {max_wait}s"
                assert sync_id, "No sync_id returned from connection"

                # VERIFY STORAGE - Check local_storage for ARF files
                arf_path = storage_path / "raw" / str(sync_id)

                # Wait for filesystem writes to complete
                await asyncio.sleep(2)

                # Verify storage directory exists
                assert storage_path.exists(), (
                    f"local_storage not found at {storage_path}. "
                    "Docker volume mount may be misconfigured."
                )

                # Verify ARF directory exists
                assert arf_path.exists(), (
                    f"ARF directory not found at {arf_path}. "
                    f"Sync completed but no ARF files written for sync_id={sync_id}"
                )

                # Verify manifest exists and is valid
                manifest_path = arf_path / "manifest.json"
                assert manifest_path.exists(), f"Manifest not found at {manifest_path}"
                with open(manifest_path) as f:
                    manifest = json.load(f)
                assert manifest, "Manifest is empty"

                # Verify entities directory and files
                entities_path = arf_path / "entities"
                assert entities_path.exists(), f"Entities directory not found at {entities_path}"

                entity_files = list(entities_path.glob("*.json"))
                assert len(entity_files) > 0, (
                    f"No entity files in {entities_path}. Sync reported success but wrote no entities."
                )

                # Verify entity content is valid
                with open(entity_files[0]) as f:
                    entity = json.load(f)
                assert entity, f"Entity file {entity_files[0]} is empty"
                assert "entity_id" in entity or "id" in entity, (
                    f"Entity missing identifier. Keys: {list(entity.keys())}"
                )

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
