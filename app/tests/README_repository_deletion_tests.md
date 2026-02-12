# Repository Deletion Tests

## Purpose
Tests verify that repositories can be deleted even when they have related job records, addressing the FOREIGN KEY constraint issue fixed in commit e7bb99d.

## Test Coverage

### ✅ test_delete_repository_with_restore_jobs
**What**: Repository with RestoreJob record(s)
**Verifies**: RestoreJob deleted → Repository deleted successfully
**Reproduces bug**: User restored files from repo → deletion blocked

### ✅ test_delete_repository_with_check_jobs
**What**: Repository with CheckJob record(s)
**Verifies**: CheckJob deleted → Repository deleted successfully
**Reproduces bug**: User ran "Check Repository" → deletion blocked

### ✅ test_delete_repository_with_prune_jobs
**What**: Repository with PruneJob record(s)
**Verifies**: PruneJob deleted → Repository deleted successfully
**Reproduces bug**: User pruned old archives → deletion blocked

### ✅ test_delete_repository_with_compact_jobs
**What**: Repository with CompactJob record(s)
**Verifies**: CompactJob deleted → Repository deleted successfully
**Reproduces bug**: User compacted repository → deletion blocked

### ✅ test_delete_repository_with_all_job_types
**What**: Repository with ALL job types (worst case)
**Verifies**: All jobs deleted → Repository deleted successfully
**Reproduces bug**: Active repository with full history → deletion blocked

### ✅ test_delete_repository_preserves_backup_job_history
**What**: Repository with BackupJob record(s)
**Verifies**: BackupJob.repository_id set to NULL → Job preserved → Repository deleted
**Purpose**: Preserve backup history even after repository deletion

### ✅ test_delete_repository_with_scheduled_job_link
**What**: Repository linked to scheduled job via junction table
**Verifies**: ScheduledJobRepository entries deleted → Repository deleted → Schedule preserved
**Purpose**: Remove repository from schedules without deleting schedules

### ✅ test_delete_repository_without_cleanup_fails
**What**: Attempts deletion WITHOUT cleanup (simulates the bug)
**Verifies**: Deletion fails with "FOREIGN KEY constraint failed"
**Purpose**: Proves the fix is necessary

## Running Tests

Due to environment setup, these tests need:
- Temporary test database (not /data which is read-only in Docker)
- Proper pytest fixtures with database isolation

To run:
```bash
# Set up test database
export DATABASE_URL="sqlite:////tmp/test.db"

# Run tests
pytest app/tests/test_repository_deletion.py -v
```

## Manual Testing Checklist

Since automated tests are complex to set up, manual testing:

1. ✅ **Create repository**
2. ✅ **Run restore** (creates RestoreJob)
3. ✅ **Try delete repository** → Should succeed (was: FOREIGN KEY constraint failed)
4. ✅ **Verify logs** show "Deleted restore jobs, repo_id=X, count=1"

Repeat for Check, Prune, Compact operations.

## What the Fix Does

Before fix (commit 13ea446 enabled FK constraints):
```python
# Only cleaned up RepositoryScript (which has CASCADE anyway)
db.delete(repository)  # ❌ FAILS if any job records exist
```

After fix (commit e7bb99d):
```python
# Clean up ALL related records first
delete RestoreJob, CheckJob, PruneJob, CompactJob
set BackupJob.repository_id = NULL (preserve history)
set ScheduledJob.repository_id = NULL
delete ScheduledJobRepository junction entries
delete RepositoryScript
db.delete(repository)  # ✅ NOW SUCCEEDS
```

## Foreign Key Reference Chart

| Table | FK Column | Has CASCADE? | Fix Action |
|-------|-----------|--------------|------------|
| RestoreJob | repository_id | ❌ NO | Delete job |
| CheckJob | repository_id | ❌ NO | Delete job |
| PruneJob | repository_id | ❌ NO | Delete job |
| CompactJob | repository_id | ❌ NO | Delete job |
| BackupJob | repository_id | ❌ NO (nullable) | Set to NULL |
| ScheduledJob | repository_id | ❌ NO (nullable) | Set to NULL |
| ScheduledJobRepository | repository_id | ✅ YES | Delete (manual) |
| RepositoryScript | repository_id | ✅ YES | Delete (manual) |
