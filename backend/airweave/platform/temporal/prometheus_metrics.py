"""Prometheus metrics for Temporal workers."""

from typing import Dict, Any
from prometheus_client import CollectorRegistry, Gauge, Info, generate_latest, ProcessCollector

# Create a custom registry for worker metrics
# (separate from any other Prometheus metrics in the system)
worker_registry = CollectorRegistry()

# Add process metrics (memory, CPU, file descriptors, etc.)
# This provides standard process-level metrics automatically
ProcessCollector(registry=worker_registry, namespace="airweave_worker")


def _clear_worker_metrics(metric, worker_id: str) -> None:
    """Clear all metric label combinations for a specific worker.

    This is a helper to remove stale metrics when syncs complete.
    Uses internal _metrics dict as Prometheus client doesn't provide public API for this.

    Args:
        metric: Prometheus metric object (Gauge)
        worker_id: Worker ID to clear metrics for
    """
    if hasattr(metric, "_metrics"):
        to_remove = []
        for labels_tuple in list(metric._metrics.keys()):
            # worker_id is always the first label in our metrics
            if labels_tuple and labels_tuple[0] == worker_id:
                to_remove.append(labels_tuple)

        for labels_tuple in to_remove:
            metric._metrics.pop(labels_tuple, None)


# Info metric for static worker information
worker_info = Info(
    "airweave_worker",
    "Static information about this Temporal worker",
    registry=worker_registry,
)

# Gauge for worker uptime in seconds
worker_uptime_seconds = Gauge(
    "airweave_worker_uptime_seconds",
    "Worker uptime in seconds since start",
    ["worker_id"],
    registry=worker_registry,
)

# Gauge for worker status (0=stopped, 1=running, 2=draining)
worker_status = Gauge(
    "airweave_worker_status",
    "Worker status: 0=stopped, 1=running, 2=draining",
    ["worker_id"],
    registry=worker_registry,
)

# Gauge for number of active activities
worker_active_activities = Gauge(
    "airweave_worker_active_activities",
    "Number of activities currently executing",
    ["worker_id"],
    registry=worker_registry,
)

# Gauge for number of active sync jobs
worker_active_sync_jobs = Gauge(
    "airweave_worker_active_sync_jobs",
    "Number of unique sync jobs currently being processed",
    ["worker_id"],
    registry=worker_registry,
)

# Gauge for worker pool active workers count
worker_pool_active_workers = Gauge(
    "airweave_worker_pool_active_workers",
    "Number of concurrent workers currently being used from the worker pool",
    ["worker_id"],
    registry=worker_registry,
)

worker_pool_active_by_connector = Gauge(
    "airweave_worker_pool_active_by_connector",
    "Number of concurrent workers by connector type",
    ["worker_id", "connector_type"],
    registry=worker_registry,
)

worker_active_syncs_by_connector = Gauge(
    "airweave_worker_active_syncs_by_connector",
    "Number of active syncs by connector type",
    ["worker_id", "connector_type"],
    registry=worker_registry,
)

# Config value gauges (from environment variables)
worker_sync_max_workers_config = Gauge(
    "airweave_worker_sync_max_workers_config",
    "Configured max async workers per sync (SYNC_MAX_WORKERS)",
    ["worker_id"],
    registry=worker_registry,
)

worker_thread_pool_size_config = Gauge(
    "airweave_worker_thread_pool_size_config",
    "Configured thread pool size per worker pod (SYNC_THREAD_POOL_SIZE)",
    ["worker_id"],
    registry=worker_registry,
)

# Active thread pool usage
worker_thread_pool_active = Gauge(
    "airweave_worker_thread_pool_active",
    "Number of threads currently executing in the shared thread pool",
    ["worker_id"],
    registry=worker_registry,
)


def update_worker_metrics(
    worker_id: str,
    status: str,
    uptime_seconds: float,
    active_activities_count: int,
    active_sync_jobs_count: int,
    task_queue: str,
    worker_pool_active_count: int = 0,
    connector_metrics: Dict[str, Dict[str, int]] = None,
    sync_max_workers: int = 20,
    thread_pool_size: int = 100,
    thread_pool_active: int = 0,
) -> None:
    """Update all Prometheus worker metrics.

    Args:
        worker_id: Unique identifier for the worker (pod ordinal like '0', '1', '2')
        status: Worker status string ("running", "draining", "stopped")
        uptime_seconds: Worker uptime in seconds
        active_activities_count: Number of currently executing activities
        active_sync_jobs_count: Number of unique sync jobs being processed
        task_queue: Task queue name this worker is polling
        worker_pool_active_count: Number of concurrent workers currently being used
        connector_metrics: Dict mapping connector_type to metrics (active_syncs, active_workers)
        sync_max_workers: Configured SYNC_MAX_WORKERS value
        thread_pool_size: Configured SYNC_THREAD_POOL_SIZE value
        thread_pool_active: Number of threads currently executing in the shared thread pool
    """
    # Update info metric (static data)
    worker_info.info(
        {
            "worker_id": worker_id,
            "task_queue": task_queue,
        }
    )

    # Map status string to numeric value
    status_value = {"stopped": 0, "running": 1, "draining": 2}.get(status, 0)

    # Update all gauges
    worker_uptime_seconds.labels(worker_id=worker_id).set(uptime_seconds)
    worker_status.labels(worker_id=worker_id).set(status_value)
    worker_active_activities.labels(worker_id=worker_id).set(active_activities_count)
    worker_active_sync_jobs.labels(worker_id=worker_id).set(active_sync_jobs_count)

    # Update worker pool active workers count
    worker_pool_active_workers.labels(worker_id=worker_id).set(worker_pool_active_count)

    # Clear and update connector-type aggregated metrics (low cardinality)
    _clear_worker_metrics(worker_pool_active_by_connector, worker_id)
    _clear_worker_metrics(worker_active_syncs_by_connector, worker_id)

    if connector_metrics:
        for connector_type, metrics in connector_metrics.items():
            worker_pool_active_by_connector.labels(
                worker_id=worker_id,
                connector_type=connector_type,
            ).set(metrics.get("active_workers", 0))

            worker_active_syncs_by_connector.labels(
                worker_id=worker_id,
                connector_type=connector_type,
            ).set(metrics.get("active_syncs", 0))

    # Update config value gauges
    worker_sync_max_workers_config.labels(worker_id=worker_id).set(sync_max_workers)
    worker_thread_pool_size_config.labels(worker_id=worker_id).set(thread_pool_size)

    # Update thread pool active threads
    worker_thread_pool_active.labels(worker_id=worker_id).set(thread_pool_active)


def get_prometheus_metrics() -> bytes:
    """Generate Prometheus metrics in text format.

    Returns:
        Prometheus metrics in text format (bytes)
    """
    return generate_latest(worker_registry)
