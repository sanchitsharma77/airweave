"""Event types for webhook notifications.

This module defines the event types that can be sent via webhooks,
primarily focused on sync job lifecycle events.
"""

from enum import Enum

from airweave.core.shared_models import SyncJobStatus


class EventType(str, Enum):
    """Enumeration of webhook event types."""

    SYNC_CREATED = "sync.created"
    SYNC_PENDING = "sync.pending"
    SYNC_RUNNING = "sync.running"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"
    SYNC_CANCELLING = "sync.cancelling"
    SYNC_CANCELLED = "sync.cancelled"
    SYNC_INVALID = "sync.invalid"


def event_type_from_sync_job_status(sync_job_status: SyncJobStatus) -> EventType:
    """Convert a SyncJobStatus to the corresponding EventType.

    Args:
        sync_job_status: The sync job status to convert.

    Returns:
        The corresponding EventType, or SYNC_INVALID if not found.
    """
    event_type_map = {
        SyncJobStatus.CREATED: EventType.SYNC_CREATED,
        SyncJobStatus.PENDING: EventType.SYNC_PENDING,
        SyncJobStatus.RUNNING: EventType.SYNC_RUNNING,
        SyncJobStatus.COMPLETED: EventType.SYNC_COMPLETED,
        SyncJobStatus.FAILED: EventType.SYNC_FAILED,
        SyncJobStatus.CANCELLING: EventType.SYNC_CANCELLING,
        SyncJobStatus.CANCELLED: EventType.SYNC_CANCELLED,
    }

    return event_type_map.get(sync_job_status, EventType.SYNC_INVALID)
