"""
Smoke test for storage backend verification.

Tests that the configured storage backend is working correctly by:
1. Running a sync that writes data to storage (ARF files)
2. Verifying ARF files exist INSIDE the Docker container via docker exec
3. Verifying manifest and entity files are readable

Runs in local environment only (TEST_ENV=local) via @pytest.mark.local_only.
Skipped automatically in deployed environments (TEST_ENV=dev/prod).
"""

import asyncio
import subprocess
import uuid

import httpx
import pytest


def docker_exec(container: str, command: str) -> tuple[int, str, str]:
    """Run a command inside a Docker container.

    Returns (exit_code, stdout, stderr).
    """
    result = subprocess.run(
        ["docker", "exec", container, "sh", "-c", command],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def verify_arf_files_in_container(sync_id: str, container: str = "airweave-backend") -> dict:
    """Verify ARF files exist inside the Docker container.

    Returns dict with verification results.
    """
    storage_path = "/app/local_storage"
    arf_path = f"{storage_path}/raw/{sync_id}"

    results = {
        "storage_exists": False,
        "arf_dir_exists": False,
        "manifest_exists": False,
        "manifest_valid": False,
        "entities_dir_exists": False,
        "entity_count": 0,
        "errors": [],
    }

    # Check storage directory
    code, out, err = docker_exec(container, f"test -d {storage_path} && echo 'yes' || echo 'no'")
    results["storage_exists"] = out.strip() == "yes"
    if not results["storage_exists"]:
        results["errors"].append(f"Storage directory {storage_path} not found in container")
        return results

    # Check ARF directory
    code, out, err = docker_exec(container, f"test -d {arf_path} && echo 'yes' || echo 'no'")
    results["arf_dir_exists"] = out.strip() == "yes"
    if not results["arf_dir_exists"]:
        # List what's in raw/ to help debug
        code, out, err = docker_exec(container, f"ls -la {storage_path}/raw/ 2>/dev/null || echo 'raw dir missing'")
        results["errors"].append(f"ARF directory {arf_path} not found. Contents of raw/: {out.strip()}")
        return results

    # Check manifest
    manifest_path = f"{arf_path}/manifest.json"
    code, out, err = docker_exec(container, f"test -f {manifest_path} && echo 'yes' || echo 'no'")
    results["manifest_exists"] = out.strip() == "yes"
    if results["manifest_exists"]:
        # Validate JSON
        code, out, err = docker_exec(container, f"python3 -c \"import json; json.load(open('{manifest_path}'))\" && echo 'valid'")
        results["manifest_valid"] = "valid" in out

    # Check entities directory
    entities_path = f"{arf_path}/entities"
    code, out, err = docker_exec(container, f"test -d {entities_path} && echo 'yes' || echo 'no'")
    results["entities_dir_exists"] = out.strip() == "yes"
    if results["entities_dir_exists"]:
        # Count entity files
        code, out, err = docker_exec(container, f"ls -1 {entities_path}/*.json 2>/dev/null | wc -l")
        try:
            results["entity_count"] = int(out.strip())
        except ValueError:
            results["entity_count"] = 0

    return results


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
        """Test that sync writes ARF files to the storage backend.

        1. Creates a stub connection and triggers a sync
        2. Waits for sync to complete
        3. Uses docker exec to verify ARF files inside the container
        """
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
                    "authentication": {"credentials": {"stub_key": "test"}},
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

                # Wait for filesystem writes to complete
                await asyncio.sleep(2)

                # VERIFY STORAGE inside Docker container
                results = verify_arf_files_in_container(sync_id)

                # Assert all checks passed
                assert results["storage_exists"], (
                    f"Storage directory not found in container. Errors: {results['errors']}"
                )
                assert results["arf_dir_exists"], (
                    f"ARF directory not found for sync_id={sync_id}. Errors: {results['errors']}"
                )
                assert results["manifest_exists"], (
                    f"Manifest not found for sync_id={sync_id}"
                )
                assert results["manifest_valid"], (
                    f"Manifest is not valid JSON for sync_id={sync_id}"
                )
                assert results["entities_dir_exists"], (
                    f"Entities directory not found for sync_id={sync_id}"
                )
                assert results["entity_count"] > 0, (
                    f"No entity files found for sync_id={sync_id}"
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
