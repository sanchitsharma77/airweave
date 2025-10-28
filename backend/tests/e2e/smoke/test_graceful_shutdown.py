"""
E2E test for Temporal worker graceful shutdown.

Tests that workers gracefully complete activities when draining and
do not accept new work after drain is initiated.
"""

import asyncio
import subprocess
from typing import Dict, Optional

import httpx
import pytest


class TestGracefulShutdown:
    """Test suite for worker graceful shutdown functionality."""

    async def _wait_for_job_status(
        self,
        api_client: httpx.AsyncClient,
        conn_id: str,
        job_id: str,
        expected_status: str,
        timeout: int = 60,
    ) -> Optional[Dict]:
        """Wait for a job to reach a specific status."""
        elapsed = 0
        poll_interval = 2

        while elapsed < timeout:
            response = await api_client.get(f"/source-connections/{conn_id}/jobs")
            if response.status_code == 200:
                jobs = response.json()
                job = next((j for j in jobs if j["id"] == job_id), None)
                if job and job["status"] == expected_status:
                    return job

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        return None

    def _drain_worker(self, worker_pod: str, namespace: str = "airweave") -> bool:
        """Drain a specific worker pod via kubectl.

        Args:
            worker_pod: Name of the worker pod to drain
            namespace: Kubernetes namespace

        Returns:
            True if drain succeeded, False otherwise
        """
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "exec",
                    "-n",
                    namespace,
                    worker_pod,
                    "--",
                    "curl",
                    "-s",
                    "-X",
                    "POST",
                    "http://localhost:8888/drain",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "Drain initiated" in result.stdout
        except Exception as e:
            print(f"Failed to drain worker: {e}")
            return False

    def _get_worker_pods(self, namespace: str = "airweave") -> list:
        """Get list of worker pod names."""
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "pods",
                    "-n",
                    namespace,
                    "-l",
                    "app.kubernetes.io/component=sync-worker",
                    "-o",
                    "jsonpath={.items[*].metadata.name}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip().split()
            return []
        except Exception:
            return []

    def _find_worker_running_job(
        self, job_id: str, worker_pods: list, namespace: str = "airweave"
    ) -> Optional[str]:
        """Find which worker pod is running a specific job.

        Args:
            job_id: Job ID to search for
            worker_pods: List of worker pod names
            namespace: Kubernetes namespace

        Returns:
            Pod name if found, None otherwise
        """
        for pod in worker_pods:
            try:
                result = subprocess.run(
                    [
                        "kubectl",
                        "logs",
                        "-n",
                        namespace,
                        pod,
                        "--tail=100",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and job_id in result.stdout:
                    return pod
            except Exception:
                continue
        return None

    @pytest.mark.requires_temporal
    @pytest.mark.asyncio
    async def test_worker_drain_prevents_new_work(
        self, api_client: httpx.AsyncClient, source_connection_medium: Dict, config
    ):
        """Test that draining a worker prevents it from accepting new activities.

        This test requires:
        - Multiple worker pods (>=2) OR ability to drain and observe queuing
        - Kubernetes access (kubectl) for draining workers
        - Temporal enabled

        Flow:
        1. Start Sync 1 (medium duration)
        2. Identify which worker is running it
        3. Drain that worker
        4. Start Sync 2
        5. Verify Sync 2 is NOT picked up by the drained worker
        6. Verify Sync 1 completes successfully on drained worker
        """
        if config.is_local:
            # In local docker, we need multiple workers
            pytest.skip(
                "Graceful shutdown test requires Kubernetes environment or manual multi-worker setup"
            )

        conn_id = source_connection_medium["id"]

        # Get available worker pods
        worker_pods = self._get_worker_pods()
        if len(worker_pods) < 2:
            pytest.skip(f"Test requires at least 2 workers, found {len(worker_pods)}")

        print(f"\nFound {len(worker_pods)} worker pods: {worker_pods}")

        # Start first sync
        response = await api_client.post(f"/source-connections/{conn_id}/run")
        assert response.status_code == 200
        job1 = response.json()
        job1_id = job1["id"]
        print(f"Started Sync 1 (job {job1_id})")

        # Wait for it to start
        await asyncio.sleep(5)

        # Find which worker is running it
        worker_with_job1 = self._find_worker_running_job(job1_id, worker_pods)
        if not worker_with_job1:
            pytest.skip("Could not determine which worker is running the sync")

        print(f"Sync 1 is running on worker: {worker_with_job1}")

        # Drain that worker
        drain_success = self._drain_worker(worker_with_job1)
        assert drain_success, f"Failed to drain worker {worker_with_job1}"
        print(f"Successfully drained worker: {worker_with_job1}")

        # Wait a moment for drain to take effect
        await asyncio.sleep(2)

        # Start second sync
        response = await api_client.post(f"/source-connections/{conn_id}/run")

        # This might fail with "already running" which is OK for this test
        # The key is that if it starts, it should NOT be on the drained worker
        if response.status_code == 200:
            job2 = response.json()
            job2_id = job2["id"]
            print(f"Started Sync 2 (job {job2_id})")

            # Wait for it to be picked up
            await asyncio.sleep(5)

            # Verify it's NOT on the drained worker
            worker_with_job2 = self._find_worker_running_job(job2_id, worker_pods)
            if worker_with_job2:
                print(f"Sync 2 is running on worker: {worker_with_job2}")
                assert (
                    worker_with_job2 != worker_with_job1
                ), f"Drained worker {worker_with_job1} should NOT have picked up new work!"

        # Verify Sync 1 completes successfully (not cancelled)
        completed_job1 = await self._wait_for_job_status(
            api_client, conn_id, job1_id, "completed", timeout=120
        )
        assert (
            completed_job1 is not None
        ), "Sync 1 should complete even after worker was drained"
        assert completed_job1["status"] == "completed"
        print(f"✅ Sync 1 completed successfully on drained worker")

    @pytest.mark.requires_temporal
    @pytest.mark.asyncio
    async def test_worker_health_endpoint(
        self, api_client: httpx.AsyncClient, source_connection_fast: Dict, config
    ):
        """Test that worker health endpoint is accessible and responds correctly."""
        if config.is_local:
            # Local docker test
            result = subprocess.run(
                ["docker", "exec", "airweave-temporal-worker", "curl", "-s", "http://localhost:8888/health"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, "Health endpoint should be accessible"
            assert result.stdout in ["OK", "NOT_RUNNING", "DRAINING"], f"Unexpected health status: {result.stdout}"
        else:
            # Kubernetes test
            worker_pods = self._get_worker_pods()
            assert len(worker_pods) > 0, "No worker pods found"

            for pod in worker_pods:
                result = subprocess.run(
                    [
                        "kubectl",
                        "exec",
                        "-n",
                        "airweave",
                        pod,
                        "--",
                        "curl",
                        "-s",
                        "http://localhost:8888/health",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                assert result.returncode == 0, f"Health endpoint should be accessible on {pod}"
                assert result.stdout in [
                    "OK",
                    "NOT_RUNNING",
                    "DRAINING",
                ], f"Unexpected health status on {pod}: {result.stdout}"

    @pytest.mark.requires_temporal
    @pytest.mark.asyncio
    async def test_sync_completes_during_pod_deletion(
        self, api_client: httpx.AsyncClient, source_connection_medium: Dict, config
    ):
        """Test that sync completes successfully when pod is deleted during execution.

        This is the core graceful shutdown test:
        1. Start a medium-duration sync
        2. Delete the pod running it
        3. Verify sync completes (not cancelled)
        4. Verify new pod is created automatically
        """
        if config.is_local:
            pytest.skip("Pod deletion test requires Kubernetes environment")

        conn_id = source_connection_medium["id"]

        # Get initial pod count
        worker_pods = self._get_worker_pods()
        initial_count = len(worker_pods)
        assert initial_count > 0, "No worker pods found"
        print(f"\nInitial worker count: {initial_count}")

        # Start sync
        response = await api_client.post(f"/source-connections/{conn_id}/run")
        assert response.status_code == 200
        job = response.json()
        job_id = job["id"]
        print(f"Started sync (job {job_id})")

        # Wait for it to start
        await asyncio.sleep(5)

        # Find which worker is running it
        worker_with_job = self._find_worker_running_job(job_id, worker_pods)
        if not worker_with_job:
            pytest.skip("Could not determine which worker is running the sync")

        print(f"Sync is running on worker: {worker_with_job}")

        # Delete the pod
        print(f"Deleting pod {worker_with_job}...")
        result = subprocess.run(
            ["kubectl", "delete", "pod", "-n", "airweave", worker_with_job, "--wait=false"],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0, "Failed to delete pod"
        print(f"Pod deletion initiated")

        # Verify sync completes (not cancelled)
        # This is the critical assertion - sync should complete despite pod deletion
        completed_job = await self._wait_for_job_status(
            api_client, conn_id, job_id, "completed", timeout=300  # 5 minutes
        )

        assert completed_job is not None, (
            "Sync should complete successfully even when pod is deleted. "
            "If this fails, graceful shutdown is not working."
        )
        assert completed_job["status"] == "completed", (
            f"Sync status should be 'completed', got '{completed_job['status']}'. "
            "Graceful shutdown should prevent cancellation during pod deletion."
        )

        print(f"✅ Sync completed successfully despite pod deletion")

        # Verify new pod was created (deployment maintains replica count)
        await asyncio.sleep(10)
        final_pods = self._get_worker_pods()
        final_count = len(final_pods)

        assert final_count == initial_count, (
            f"Worker count should be maintained. Initial: {initial_count}, Final: {final_count}"
        )
        print(f"✅ Worker replica count maintained: {final_count}")

