# Job System Architecture

## Overview

Borg-UI uses an asynchronous job system for long-running borg operations. All jobs follow a consistent pattern: create job record → execute in background → track progress → update status.

## Job Types

### 1. BackupJob

**Purpose:** Execute `borg create` to backup source directories to a repository

**Database Model:** `backup_jobs` table
- Tracks: progress, speed, file count, compression stats
- Links to: `scheduled_jobs` (if triggered by schedule)

**Service:** `backup_service.py` → `BackupService.execute_backup()`

**API Endpoints:**
- `POST /api/backup/run` - Start manual backup
- `GET /api/backup/jobs/{job_id}` - Get job status
- `GET /api/backup/logs/{job_id}` - Stream logs

**Execution:**
```python
# Triggered by:
1. Manual: User clicks "Backup Now" button
2. Scheduled: Cron scheduler triggers based on schedule

# Process:
1. Create BackupJob record (status: pending)
2. asyncio.create_task(execute_backup)
3. Run: borg create --progress --json-lines
4. Parse progress from stdout (files, size, speed)
5. Update job every 1-2 seconds
6. Mark completed/failed
7. Optional: Run prune/compact if configured
8. Send notification
```

**Progress Tracking:**
- `progress_percent` - Overall completion (0-100%)
- `current_file` - File being processed
- `nfiles` - Files backed up
- `original_size`, `compressed_size`, `deduplicated_size`
- `backup_speed` - MB/s

**Duration:** Minutes to hours (depends on data size)

**Notifications:** Start, Success, Failure

---

### 2. RestoreJob

**Purpose:** Extract archives from repository to filesystem

**Database Model:** `restore_jobs` table
- Tracks: progress, file count, current file
- Stores: repository, archive, destination path

**Service:** `restore_service.py` → `RestoreService.execute_restore()`

**API Endpoints:**
- `POST /api/archives/{archive_id}/restore` - Start restore
- `GET /api/restore/jobs/{job_id}` - Get job status

**Execution:**
```python
# Triggered by:
Manual: User selects archive and clicks "Restore"

# Process:
1. Create RestoreJob record (status: pending)
2. asyncio.create_task(execute_restore)
3. Run: borg extract --progress --list
4. Parse progress from stdout
5. Update job with file count and current file
6. Mark completed/failed
7. Send notification
```

**Progress Tracking:**
- `progress_percent` - Files restored / total files
- `current_file` - File being extracted
- `nfiles` - Number of files restored

**Duration:** Minutes to hours

**Notifications:** Success, Failure

---

### 3. CheckJob

**Purpose:** Verify repository integrity using `borg check`

**Database Model:** `check_jobs` table
- Tracks: progress, segments checked
- Links to: `repositories` table
- Supports: partial checks with `max_duration`

**Service:** `check_service.py` → `CheckService.execute_check()`

**API Endpoints:**
- `POST /api/repositories/{repo_id}/check` - Start check
- `GET /api/repositories/check-jobs/{job_id}` - Get job status
- `GET /api/repositories/{repo_id}/check-jobs` - List check history

**Execution:**
```python
# Triggered by:
1. Manual: User clicks "Check" button on repository
2. Scheduled: Interval-based scheduler (every N days)

# Process:
1. Create CheckJob record (status: pending)
2. asyncio.create_task(execute_check)
3. Run: borg check --progress --log-json
   Optional: --repository-only --max-duration N
4. Parse progress from stderr (borg outputs progress there)
5. Update job with progress message
6. Mark completed/failed
7. Update repository.last_check timestamp
8. Send notification
```

**Progress Tracking:**
- `progress` - Percentage (0-100)
- `progress_message` - E.g., "Checking segments 45%"
- `max_duration` - Limit for partial checks

**Duration:** Seconds to hours (full check can take long time)

**Notifications:** Success, Failure (when scheduled checks are implemented)

---

### 4. CompactJob

**Purpose:** Free unused space in repository using `borg compact`

**Database Model:** `compact_jobs` table
- Tracks: progress, segments compacted
- Links to: `repositories` table

**Service:** `compact_service.py` → `CompactService.execute_compact()`

**API Endpoints:**
- `POST /api/repositories/{repo_id}/compact` - Start compact
- `GET /api/repositories/compact-jobs/{job_id}` - Get job status
- `GET /api/repositories/{repo_id}/compact-jobs` - List compact history

**Execution:**
```python
# Triggered by:
1. Manual: User clicks "Compact" button (admin only)
2. Automatic: After prune completes (if run_compact_after=true)

# Process:
1. Create CompactJob record (status: pending)
2. asyncio.create_task(execute_compact)
3. Run: borg compact --progress --log-json
4. Parse progress from stderr
5. Update job with progress message
6. Mark completed/failed
7. Update repository.last_compact timestamp
```

**Progress Tracking:**
- `progress` - Percentage (0-100)
- `progress_message` - E.g., "Compacting segments 30%"

**Duration:** Minutes to hours

**Notifications:** None currently (could be added)

---

### 5. ScheduledJob

**Purpose:** Define cron-based backup schedules with optional maintenance

**Database Model:** `scheduled_jobs` table
- NOT an execution job - it's a configuration/schedule definition
- Creates `BackupJob` when triggered by cron

**Service:** `backup_service.py` → Cron scheduler component

**API Endpoints:**
- `GET /api/scheduled-jobs` - List all schedules
- `POST /api/scheduled-jobs` - Create schedule
- `PUT /api/scheduled-jobs/{id}` - Update schedule
- `DELETE /api/scheduled-jobs/{id}` - Delete schedule

**Execution:**
```python
# Not directly executed - it's a schedule definition

# Scheduler Process:
1. Cron daemon evaluates all enabled ScheduledJob records
2. When cron_expression matches current time:
   - Create BackupJob with scheduled_job_id
   - Execute backup
   - If run_prune_after: Execute prune
   - If run_compact_after: Execute compact
3. Update last_run and calculate next_run
```

**Configuration:**
- `cron_expression` - When to run (e.g., "0 2 * * *")
- `repository` - Which repo to backup
- `archive_name_template` - Archive naming pattern
- `run_prune_after` - Auto-prune after backup
- `run_compact_after` - Auto-compact after prune
- Prune retention settings (keep_daily, keep_weekly, etc.)

**Special:** This is the only job type that doesn't represent an execution - it's a schedule definition.

---

### 6. PackageInstallJob

**Purpose:** Install system packages via apt (for borg, git, docker, etc.)

**Database Model:** `package_install_jobs` table
- Tracks: package name, installation status, logs

**Service:** `package_service.py` → `PackageService.install_package()`

**API Endpoints:**
- `POST /api/system/packages/install` - Install package
- `GET /api/system/packages/jobs/{job_id}` - Get install status

**Execution:**
```python
# Triggered by:
Manual: User clicks "Install" on packages page

# Process:
1. Create PackageInstallJob record (status: pending)
2. asyncio.create_task(install_package)
3. Run: sudo apt-get update && sudo apt-get install -y PACKAGE
4. Stream output to logs
5. Mark completed/failed
6. Update package status in database
```

**Duration:** Seconds to minutes

---

## Job Lifecycle

```
┌──────────┐
│ Created  │ ← Job record inserted to database
└────┬─────┘
     │
     ▼
┌──────────┐
│ pending  │ ← Waiting to be picked up
└────┬─────┘
     │
     ▼
┌──────────┐
│ running  │ ← Service executing borg command
└────┬─────┘   Progress updates every 1-2 seconds
     │
     ├─────→ ┌────────────┐
     │       │ completed  │ ← Success (exit code 0)
     │       └────────────┘
     │
     ├─────→ ┌──────────┐
     │       │  failed  │ ← Error or exception
     │       └──────────┘
     │
     └─────→ ┌────────────┐
             │ cancelled  │ ← User cancelled (RestoreJob only)
             └────────────┘
```

## Common Patterns

### All Job Services Share:

1. **Database Session Management**
   ```python
   db = SessionLocal()  # New session for background task
   try:
       # ... work ...
   finally:
       db.close()
   ```

2. **Status Transitions**
   ```python
   job.status = "running"
   job.started_at = datetime.utcnow()
   db.commit()
   # ... execute ...
   job.status = "completed"
   job.completed_at = datetime.utcnow()
   db.commit()
   ```

3. **Environment Setup**
   ```python
   env = os.environ.copy()
   if repository.passphrase:
       env['BORG_PASSPHRASE'] = repository.passphrase
   env['BORG_RSH'] = 'ssh -o StrictHostKeyChecking=no ...'
   ```

4. **Process Management**
   ```python
   process = await asyncio.create_subprocess_exec(
       *cmd,
       stdout=asyncio.subprocess.PIPE,
       stderr=asyncio.subprocess.PIPE,
       env=env
   )
   # Store PID for orphan detection
   job.process_pid = process.pid
   ```

5. **Progress Parsing**
   - Borg outputs JSON lines to stdout/stderr
   - Services parse and update job.progress_*
   - Different commands have different formats

6. **Error Handling**
   ```python
   except Exception as e:
       job.status = "failed"
       job.error_message = str(e)
       job.completed_at = datetime.utcnow()
       db.commit()
       logger.error("Job failed", job_id=job.id, error=str(e))
   ```

## Progress Tracking

### Real-time Updates

Jobs update progress in database every 1-2 seconds:
- Frontend polls `GET /api/.../jobs/{id}` every 2 seconds
- Alternative: WebSocket (future enhancement)

### Progress Types

**Percentage-based:**
- CheckJob: Segments checked / total segments
- CompactJob: Segments compacted / total segments
- RestoreJob: Files extracted / total files

**Throughput-based:**
- BackupJob: Bytes processed, speed MB/s, ETA

**Status-based:**
- PackageInstallJob: apt output logs

### Log Storage

- **Streaming:** Logs written to `/data/logs/{job_id}.log` during execution
- **Database:** Full logs stored in `job.logs` after completion
- **Retention:** Configurable (default: keep last 100 jobs)

## Notifications

Configured in `system_settings` table:

```python
notify_on_backup_start = False
notify_on_backup_success = False
notify_on_backup_failure = True
notify_on_restore_success = False
notify_on_restore_failure = True
notify_on_schedule_failure = True
# notify_on_check_success = False  # To be added
# notify_on_check_failure = True   # To be added
```

Notification channels:
- Email (SMTP)
- Slack webhook
- Discord webhook
- Ntfy.sh
- Apprise (supports 90+ services)

## Adding New Job Types

### Steps:

1. **Create Database Model** (`app/database/models.py`)
   ```python
   class MyNewJob(Base):
       __tablename__ = "my_new_jobs"

       id = Column(Integer, primary_key=True)
       repository_id = Column(Integer, ForeignKey("repositories.id"))
       status = Column(String, default="pending")
       started_at = Column(DateTime, nullable=True)
       completed_at = Column(DateTime, nullable=True)
       progress = Column(Integer, default=0)
       error_message = Column(Text, nullable=True)
       logs = Column(Text, nullable=True)
       # ... custom fields ...
       created_at = Column(DateTime, default=utc_now)
   ```

2. **Create Migration** (`app/database/migrations/NNN_add_my_new_job.py`)
   ```python
   def upgrade(connection):
       connection.execute(text("""
           CREATE TABLE my_new_jobs (
               id INTEGER PRIMARY KEY,
               repository_id INTEGER,
               status TEXT,
               ...
           )
       """))
   ```

3. **Create Service** (`app/services/my_new_service.py`)
   ```python
   class MyNewService:
       async def execute_my_operation(self, job_id: int):
           db = SessionLocal()
           try:
               job = db.query(MyNewJob).filter(MyNewJob.id == job_id).first()
               job.status = "running"

               # Execute borg command
               process = await asyncio.create_subprocess_exec(...)

               # Track progress
               # ...

               job.status = "completed"
           except Exception as e:
               job.status = "failed"
               job.error_message = str(e)
           finally:
               db.close()
   ```

4. **Create API Endpoint** (`app/api/repositories.py` or new file)
   ```python
   @router.post("/{repo_id}/my-operation")
   async def start_my_operation(repo_id: int):
       job = MyNewJob(repository_id=repo_id, status="pending")
       db.add(job)
       db.commit()

       asyncio.create_task(my_new_service.execute_my_operation(job.id))

       return {"job_id": job.id, "status": "pending"}
   ```

5. **Add Frontend UI** (Optional)
   - Button to trigger operation
   - Status display
   - Progress indicator

6. **Add Notifications** (Optional)
   - Add settings to SystemSettings model
   - Call notification_service on completion

### Example: Scheduled Checks (Current Task)

Will follow this pattern:
1. ✅ CheckJob model already exists
2. ✅ check_service.py already exists
3. ✅ API endpoints already exist
4. ⚠️ Add: Interval-based scheduler
5. ⚠️ Add: Notification settings
6. ⚠️ Add: Schedule UI in Schedule tab

## Performance Considerations

### Concurrency

- Multiple jobs can run simultaneously
- Each job runs in separate asyncio task
- Database uses SQLite with WAL mode (concurrent reads)
- Borg supports parallel operations to different repos

### Resource Limits

- No hard limit on concurrent jobs
- System limited by: CPU, RAM, I/O, network
- Consider: Rate limiting for package installs
- Consider: Queue system for many simultaneous backups

### Orphan Detection

Problem: If container restarts, running jobs become orphaned

Solution:
- Store `process_pid` and `process_start_time`
- On startup: Check if PIDs still exist
- Mark stale jobs as "failed" with "Container restarted"

Implementation: In `BackupService.__init__()`, `CheckService.__init__()`, etc.

## Testing

### Unit Tests

Test individual components:
- Job model creation
- Service command building
- Progress parsing logic

### Integration Tests

Test full workflow:
- Create job → Execute → Verify completion
- Test with real borg commands
- Test error scenarios

### Manual Testing

- Create jobs via UI
- Monitor progress
- Check logs
- Verify notifications

## Troubleshooting

### Job Stuck in "pending"

**Cause:** Service not running or exception during startup

**Fix:**
1. Check container logs
2. Verify asyncio.create_task() was called
3. Check for exceptions in service

### Job Stuck in "running"

**Cause:** Borg process hung or orphaned

**Fix:**
1. Check process: `ps aux | grep borg`
2. Kill manually: `kill <pid>`
3. Update job status in database

### No Progress Updates

**Cause:** Progress parsing broken or borg not outputting progress

**Fix:**
1. Check logs in `/data/logs/{job_id}.log`
2. Verify borg command includes `--progress`
3. Check stderr parsing logic

### High Memory Usage

**Cause:** Large log accumulation in database

**Fix:**
1. Implement log rotation
2. Store logs in files, not database
3. Clean up old job records

## Future Enhancements

- [ ] WebSocket for real-time progress (eliminate polling)
- [ ] Job queue with priority
- [ ] Retry logic for failed jobs
- [ ] Job templates
- [ ] Webhook support (call external API on job completion)
- [ ] Resource limits per job type
- [ ] Job chains (backup → check → compact)
- [ ] Distributed job execution (multiple workers)

---

## Summary

Borg-UI's job system provides a consistent, asynchronous execution framework for all borg operations. Each job type follows the same lifecycle (pending → running → completed/failed) with real-time progress tracking and notification support. The system is extensible - adding new job types requires implementing a service class and creating database models, following established patterns.
