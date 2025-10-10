"""Cleanup utilities for orphaned Temporal workflows and schedules."""

from typing import Any, Dict
from uuid import UUID

from temporalio import activity

from airweave.api.context import ApiContext
from airweave.core.logging import LoggerConfigurator
from airweave.db.session import get_db_context


@activity.defn
async def self_destruct_orphaned_sync_activity(
    sync_id: str,
    ctx_dict: Dict[str, Any],
    reason: str = "Resource not found",
) -> Dict[str, Any]:
    """Self-destruct cleanup for orphaned workflow.

    Called when a workflow detects its sync/source_connection no longer exists.
    Cleans up any remaining schedules and workflows for this sync_id.

    Args:
        sync_id: The sync ID to clean up
        ctx_dict: The API context as dict
        reason: Reason for cleanup (for logging)

    Returns:
        Summary of cleanup actions performed
    """
    from airweave import crud, schemas

    # Reconstruct context
    organization = schemas.Organization(**ctx_dict["organization"])
    user = schemas.User(**ctx_dict["user"]) if ctx_dict.get("user") else None

    ctx = ApiContext(
        request_id=ctx_dict["request_id"],
        organization=organization,
        user=user,
        auth_method=ctx_dict["auth_method"],
        auth_metadata=ctx_dict.get("auth_metadata"),
        logger=LoggerConfigurator.configure_logger(
            "airweave.temporal.cleanup",
            dimensions={
                "sync_id": sync_id,
                "organization_id": str(organization.id),
            },
        ),
    )

    ctx.logger.info(f"🧹 Starting self-destruct cleanup for sync {sync_id}. Reason: {reason}")

    cleanup_summary = {
        "sync_id": sync_id,
        "reason": reason,
        "schedules_deleted": [],
        "workflows_cancelled": [],
        "errors": [],
    }

    # 1. Delete all schedule types using existing schedule service logic
    from airweave.platform.temporal.schedule_service import temporal_schedule_service

    schedule_ids = [
        f"sync-{sync_id}",
        f"minute-sync-{sync_id}",
        f"daily-cleanup-{sync_id}",
    ]

    for schedule_id in schedule_ids:
        try:
            # Reuse existing delete_schedule_handle which doesn't touch the database
            await temporal_schedule_service.delete_schedule_handle(schedule_id)
            ctx.logger.info(f"  ✓ Deleted schedule: {schedule_id}")
            cleanup_summary["schedules_deleted"].append(schedule_id)
        except Exception as e:
            # Schedule doesn't exist or already deleted - this is fine
            ctx.logger.debug(f"  - Schedule {schedule_id} not found: {e}")

    # Note: Other orphaned workflows will self-destruct when they detect missing resources
    ctx.logger.info(
        "  ℹ Schedule cleanup complete. "
        "Any other orphaned workflows will self-destruct when they attempt to run."
    )

    # 3. Verify sync doesn't exist in database
    try:
        async with get_db_context() as db:
            sync = await crud.sync.get(db=db, id=UUID(sync_id), ctx=ctx, with_connections=False)
            if sync:
                ctx.logger.warning(
                    f"  ⚠ Sync {sync_id} still exists in database. "
                    f"This might be a race condition during deletion."
                )
            else:
                ctx.logger.info(f"  ✓ Confirmed sync {sync_id} deleted from database")
    except Exception as e:
        # This is expected if org/user context is invalid
        ctx.logger.debug(f"  - Could not verify sync deletion: {e}")

    ctx.logger.info(
        f"🧹 Self-destruct cleanup complete for sync {sync_id}. "
        f"Deleted {len(cleanup_summary['schedules_deleted'])} schedule(s)."
    )

    return cleanup_summary
