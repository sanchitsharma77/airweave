# Self-Healing Orphaned Workflow Implementation

## Problem Solved

Fixed "Source connection record not found" errors that occurred when Temporal workflows executed after source connections and syncs were deleted. The root cause was a race condition where:

1. SourceConnection deletion cascaded to Sync deletion (same DB transaction)
2. Async schedule cleanup was queued but didn't block
3. Workflows already queued by schedules continued executing with stale cached data
4. Workflows failed when trying to fetch deleted source connection data

## Solution: Self-Healing Workflows

Instead of trying to prevent the race condition, we implemented a **self-healing mechanism** where orphaned workflows detect they're running against deleted resources and clean up after themselves.

## Implementation Details

### 1. New File: `cleanup.py`

**File**: `backend/airweave/platform/temporal/cleanup.py`

Created a new Temporal activity `self_destruct_orphaned_sync_activity` that:
- Deletes all schedule types for a sync (regular, minute-level, daily cleanup)
- Verifies the sync is deleted from the database
- Logs all cleanup actions for audit trail
- Is idempotent (safe to run multiple times)

### 2. Modified: `activities.py`

**File**: `backend/airweave/platform/temporal/activities.py`

#### Changes to `create_sync_job_activity()`:
- Added defensive check to verify sync exists before creating job
- Returns sentinel value `{"_orphaned": True, "sync_id": sync_id}` if sync not found
- Logs at INFO level (not ERROR) to avoid false alarms

#### Changes to `_run_sync_task()`:
- Wraps sync execution to catch `NotFoundException`
- Detects "Source connection record not found" errors
- Re-raises as `Exception("ORPHANED_SYNC: ...")` with clear marker
- Logs at INFO level to indicate expected scenario

### 3. Modified: `workflows.py`

**File**: `backend/airweave/platform/temporal/workflows.py`

#### Two Self-Destruct Trigger Points:

**Early Detection** (after `create_sync_job_activity`):
- Checks if `sync_job_dict.get("_orphaned")` is True
- Triggers self-destruct cleanup immediately
- Exits gracefully without creating a failed workflow

**Late Detection** (during `run_sync_activity`):
- Catches exceptions containing "ORPHANED_SYNC" marker
- Triggers self-destruct cleanup
- Exits gracefully without marking workflow as failed

Both paths:
- Call `self_destruct_orphaned_sync_activity` with 5-minute timeout
- Use retry policy (3 attempts) for robustness
- Log cleanup actions with clear emoji indicators (🧹, ✅, ⚠️)
- Exit gracefully to avoid polluting error logs

### 4. Modified: `factory.py`

**File**: `backend/airweave/platform/sync/factory.py`

Enhanced error message in `_get_source_connection_data()`:
- Provides context about why error occurred
- Explains it's expected during deletion race conditions
- Mentions self-destruct mechanism for troubleshooting

## Benefits

✅ **Self-Healing**: Workflows clean up after themselves automatically
✅ **Race-Condition Safe**: Handles timing issues wherever they occur
✅ **Idempotent**: Multiple workflows can safely run cleanup
✅ **Defensive**: Catches errors at the point they occur
✅ **No False Alarms**: Only triggers when resources are actually missing
✅ **Clear Logging**: Uses INFO level with clear indicators, not ERROR
✅ **Graceful Degradation**: Workflows exit cleanly without failures

## Testing

The implementation should be tested with:

1. **Basic Test**: Create source connection → Delete immediately → Verify no errors
2. **Schedule Test**: Create with schedule → Delete before schedule triggers → Check logs
3. **Concurrent Test**: Multiple workflows for same sync → All self-destruct cleanly
4. **Temporal UI**: Verify schedules are actually deleted
5. **Log Inspection**: No "Source connection record not found" ERRORs, only INFO logs

Run the schedule tests to verify:
```bash
pytest backend/tests/e2e/smoke/test_schedules.py -v
```

## Verification Checklist

- [ ] No "Source connection record not found" ERROR logs
- [ ] Self-destruct cleanup logs appear with 🧹 emoji
- [ ] Schedules deleted from Temporal (verify in Temporal Web UI)
- [ ] Workflows exit gracefully (not marked as failed)
- [ ] Multiple orphaned workflows handle cleanup idempotently
- [ ] Rapid create/delete cycles don't cause errors

## Files Changed

1. **New**: `backend/airweave/platform/temporal/cleanup.py`
2. **Modified**: `backend/airweave/platform/temporal/activities.py`
3. **Modified**: `backend/airweave/platform/temporal/workflows.py`
4. **Modified**: `backend/airweave/platform/sync/factory.py`

## Safety Considerations

- Self-destruct is idempotent (multiple workflows can run it safely)
- Only affects workflows with matching sync_id
- Doesn't cancel self (avoids recursion issues)
- Logs all cleanup actions for debugging
- Fails gracefully if Temporal is unavailable
- Uses retries (3 attempts) for resilience

## Future Enhancements

Optional improvements for consideration:
- Add workflow query capability to list and cancel other orphaned workflows
- Add metrics/monitoring for self-destruct trigger frequency
- Add admin endpoint to manually trigger cleanup for specific sync_id
- Add periodic cleanup job to find and remove orphaned schedules
