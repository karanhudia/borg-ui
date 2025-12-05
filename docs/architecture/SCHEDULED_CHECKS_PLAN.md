# Scheduled Checks Implementation Plan

## Feature Request: Issue #76
Add scheduled repository checks with notifications.

---

## Implementation Strategy

### Phase 1: Documentation ✅ COMPLETED
- Created comprehensive job system documentation
- Documented all 6 job types and their workflows
- File: `docs/architecture/job-system.md`

### Phase 2: Check Notifications (Days 2-3)

#### 2.1 Database Changes

**Add to `system_settings` table:**
```sql
ALTER TABLE system_settings
ADD COLUMN notify_on_check_success BOOLEAN DEFAULT 0;

ALTER TABLE system_settings
ADD COLUMN notify_on_check_failure BOOLEAN DEFAULT 1;
```

**Migration:** `025_add_check_notifications.py`

#### 2.2 Backend Changes

**File:** `app/services/notification_service.py`

Add method:
```python
async def send_check_notification(
    self,
    check_job: CheckJob,
    repository: Repository,
    settings: SystemSettings
):
    """Send notification for check job completion"""
    if check_job.status == "completed" and settings.notify_on_check_success:
        await self.send_notification(
            title="✅ Repository Check Completed",
            message=f"Repository: {repository.name}\nDuration: {duration}",
            ...
        )
    elif check_job.status == "failed" and settings.notify_on_check_failure:
        await self.send_notification(
            title="❌ Repository Check Failed",
            message=f"Repository: {repository.name}\nError: {check_job.error_message}",
            ...
        )
```

**File:** `app/services/check_service.py`

Update `execute_check()` to call notifications:
```python
# At end of execute_check():
if settings.notify_on_check_success or settings.notify_on_check_failure:
    await notification_service.send_check_notification(job, repository, settings)
```

#### 2.3 Frontend Changes

**File:** `frontend/src/components/NotificationsTab.tsx`

Add checkboxes:
```tsx
<FormControlLabel
  control={<Checkbox checked={settings.notify_on_check_success} />}
  label="Notify on check success"
/>
<FormControlLabel
  control={<Checkbox checked={settings.notify_on_check_failure} />}
  label="Notify on check failure"
/>
```

---

### Phase 3: Scheduled Checks (Days 4-7)

#### 3.1 Database Changes

**Option:** Add interval-based scheduling to `repositories` table

```sql
ALTER TABLE repositories
ADD COLUMN check_interval_days INTEGER NULL;  -- NULL = disabled

ALTER TABLE repositories
ADD COLUMN last_scheduled_check DATETIME NULL;

ALTER TABLE repositories
ADD COLUMN next_scheduled_check DATETIME NULL;

ALTER TABLE repositories
ADD COLUMN check_max_duration INTEGER DEFAULT 3600;

ALTER TABLE repositories
ADD COLUMN notify_on_check_success BOOLEAN DEFAULT 0;

ALTER TABLE repositories
ADD COLUMN notify_on_check_failure BOOLEAN DEFAULT 1;
```

**Migration:** `026_add_scheduled_checks.py`

**Why this approach:**
- Simple: No new tables needed
- Per-repository configuration (makes sense - each repo has different check needs)
- Easy to display in UI
- Reuses existing CheckJob infrastructure

#### 3.2 Backend Changes

**New File:** `app/services/check_scheduler.py`

```python
class CheckScheduler:
    """Scheduler for interval-based repository checks"""

    async def run_scheduled_checks(self):
        """Called every hour by cron or background task"""
        db = SessionLocal()
        try:
            # Find repos that need checking
            now = datetime.utcnow()
            repos = db.query(Repository).filter(
                Repository.check_interval_days.isnot(None),
                Repository.check_interval_days > 0,
                or_(
                    Repository.next_scheduled_check.is_(None),
                    Repository.next_scheduled_check <= now
                )
            ).all()

            for repo in repos:
                # Create and execute check job
                check_job = CheckJob(
                    repository_id=repo.id,
                    status="pending",
                    max_duration=repo.check_max_duration
                )
                db.add(check_job)
                db.commit()

                # Execute asynchronously
                asyncio.create_task(
                    check_service.execute_check(check_job.id, repo.id)
                )

                # Update schedule
                repo.last_scheduled_check = now
                repo.next_scheduled_check = now + timedelta(days=repo.check_interval_days)
                db.commit()

                logger.info(
                    "Scheduled check started",
                    repo_id=repo.id,
                    check_job_id=check_job.id,
                    next_check=repo.next_scheduled_check
                )
        finally:
            db.close()
```

**File:** `app/main.py`

Add background task to run scheduler:
```python
@app.on_event("startup")
async def start_check_scheduler():
    """Start the check scheduler background task"""
    async def run_scheduler():
        check_scheduler = CheckScheduler()
        while True:
            try:
                await check_scheduler.run_scheduled_checks()
            except Exception as e:
                logger.error("Check scheduler error", error=str(e))
            await asyncio.sleep(3600)  # Run every hour

    asyncio.create_task(run_scheduler())
```

**New API Endpoints:** `app/api/repositories.py`

```python
@router.put("/{repo_id}/check-schedule")
async def update_check_schedule(
    repo_id: int,
    request: dict,
    db: Session = Depends(get_db)
):
    """Update scheduled check configuration for repository"""
    repo = db.query(Repository).filter(Repository.id == repo_id).first()

    repo.check_interval_days = request.get("interval_days")
    repo.check_max_duration = request.get("max_duration", 3600)
    repo.notify_on_check_success = request.get("notify_on_success", False)
    repo.notify_on_check_failure = request.get("notify_on_failure", True)

    # Calculate next check time
    if repo.check_interval_days:
        last_check = repo.last_scheduled_check or datetime.utcnow()
        repo.next_scheduled_check = last_check + timedelta(days=repo.check_interval_days)
    else:
        repo.next_scheduled_check = None

    db.commit()

    return {"success": True, "next_check": repo.next_scheduled_check}
```

#### 3.3 Frontend Changes

**File:** `frontend/src/pages/Schedule.tsx`

**Add Scheduled Checks Section:**

```tsx
// Add state for scheduled checks
const [scheduledChecks, setScheduledChecks] = useState<ScheduledCheck[]>([])

// Fetch scheduled checks
const fetchScheduledChecks = async () => {
  const response = await api.get('/api/repositories')
  const checks = response.data
    .filter((repo: Repository) => repo.check_interval_days > 0)
    .map((repo: Repository) => ({
      id: repo.id,
      repository_name: repo.name,
      repository_path: repo.path,
      interval_days: repo.check_interval_days,
      last_check: repo.last_scheduled_check,
      next_check: repo.next_scheduled_check,
      max_duration: repo.check_max_duration,
      enabled: repo.check_interval_days > 0,
      notify_on_success: repo.notify_on_check_success,
      notify_on_failure: repo.notify_on_check_failure
    }))
  setScheduledChecks(checks)
}

// Render in unified Schedule tab:
<Box>
  {/* Existing Scheduled Backups Section */}
  <Typography variant="h6" gutterBottom>
    Scheduled Backups
  </Typography>
  <DataTable
    data={scheduledJobs}
    columns={scheduledJobsColumns}
    actions={scheduledJobsActions}
  />

  {/* NEW: Scheduled Checks Section */}
  <Typography variant="h6" gutterBottom sx={{ mt: 4 }}>
    Scheduled Checks
  </Typography>
  <DataTable
    data={scheduledChecks}
    columns={scheduledChecksColumns}
    actions={scheduledChecksActions}
  />

  <Button
    variant="outlined"
    startIcon={<Plus />}
    onClick={openAddCheckScheduleDialog}
  >
    Add Check Schedule
  </Button>
</Box>

// Column definitions for scheduled checks:
const scheduledChecksColumns: Column<ScheduledCheck>[] = [
  {
    id: 'repository',
    label: 'Repository',
    render: (check) => (
      <>
        <Typography variant="body2" fontWeight={500}>
          {check.repository_name}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {check.repository_path}
        </Typography>
      </>
    )
  },
  {
    id: 'interval',
    label: 'Interval',
    render: (check) => (
      <Chip
        label={`Every ${check.interval_days} days`}
        size="small"
        color="info"
        variant="outlined"
      />
    )
  },
  {
    id: 'last_check',
    label: 'Last Check',
    render: (check) => (
      check.last_check ? formatDate(check.last_check) : 'Never'
    )
  },
  {
    id: 'next_check',
    label: 'Next Check',
    render: (check) => (
      <>
        <Typography variant="body2">
          {formatDate(check.next_check)}
        </Typography>
        <Typography variant="caption" color="primary.main">
          {formatRelativeTime(check.next_check)}
        </Typography>
      </>
    )
  },
  {
    id: 'status',
    label: 'Enabled',
    align: 'center',
    render: (check) => (
      <Switch
        checked={check.enabled}
        onChange={() => handleToggleCheckSchedule(check)}
        size="small"
      />
    )
  }
]

// Actions for scheduled checks:
const scheduledChecksActions: ActionButton<ScheduledCheck>[] = [
  {
    icon: <Play size={16} />,
    label: 'Run Now',
    onClick: (check) => handleRunCheckNow(check),
    color: 'primary',
    tooltip: 'Run Check Now'
  },
  {
    icon: <Edit size={16} />,
    label: 'Edit',
    onClick: (check) => openEditCheckScheduleDialog(check),
    color: 'default',
    tooltip: 'Edit Schedule'
  },
  {
    icon: <Trash2 size={16} />,
    label: 'Delete',
    onClick: (check) => handleDeleteCheckSchedule(check),
    color: 'error',
    tooltip: 'Delete Schedule'
  }
]
```

**Dialog for Adding/Editing Check Schedule:**

```tsx
<Dialog open={checkScheduleDialogOpen} onClose={closeCheckScheduleDialog}>
  <DialogTitle>
    {editingCheckSchedule ? 'Edit Check Schedule' : 'Add Check Schedule'}
  </DialogTitle>
  <DialogContent>
    <Select
      label="Repository"
      value={checkScheduleForm.repository_id}
      onChange={(e) => setCheckScheduleForm({...checkScheduleForm, repository_id: e.target.value})}
    >
      {repositories.map(repo => (
        <MenuItem key={repo.id} value={repo.id}>{repo.name}</MenuItem>
      ))}
    </Select>

    <Select
      label="Check Interval"
      value={checkScheduleForm.interval_days}
      onChange={(e) => setCheckScheduleForm({...checkScheduleForm, interval_days: e.target.value})}
    >
      <MenuItem value={7}>Every 7 days (weekly)</MenuItem>
      <MenuItem value={14}>Every 14 days</MenuItem>
      <MenuItem value={30}>Every 30 days (monthly)</MenuItem>
      <MenuItem value={90}>Every 90 days (quarterly)</MenuItem>
      <MenuItem value={0}>Custom...</MenuItem>
    </Select>

    {checkScheduleForm.interval_days === 0 && (
      <TextField
        label="Custom Interval (days)"
        type="number"
        value={checkScheduleForm.custom_interval}
        onChange={(e) => setCheckScheduleForm({...checkScheduleForm, custom_interval: parseInt(e.target.value)})}
      />
    )}

    <TextField
      label="Max Duration (seconds)"
      type="number"
      value={checkScheduleForm.max_duration}
      helperText="Time limit for check (0 = unlimited)"
    />

    <FormControlLabel
      control={<Checkbox checked={checkScheduleForm.notify_on_success} />}
      label="Notify on success"
    />
    <FormControlLabel
      control={<Checkbox checked={checkScheduleForm.notify_on_failure} />}
      label="Notify on failure"
    />
  </DialogContent>
  <DialogActions>
    <Button onClick={closeCheckScheduleDialog}>Cancel</Button>
    <Button onClick={handleSaveCheckSchedule} variant="contained">
      {editingCheckSchedule ? 'Update' : 'Create'}
    </Button>
  </DialogActions>
</Dialog>
```

---

## UI Mockup: Unified Schedule Tab

```
┌─ Schedule Tab ───────────────────────────────────────────────────┐
│                                                                   │
│ ▼ Scheduled Backups                                              │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ Daily Backup        Repository: /mnt/backup             │   │
│   │ 0 2 * * *          Next run: Today at 2:00 AM          │   │
│   │ [Edit] [Delete] [Run Now]                   [Toggle]    │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│   [+ Add Backup Schedule]                                        │
│                                                                   │
│ ▼ Scheduled Checks                                               │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ /mnt/backup         Every 7 days                        │   │
│   │ Last: 2 days ago    Next: in 5 days                    │   │
│   │ [Edit] [Delete] [Run Now]                   [Toggle]    │   │
│   └─────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ /mnt/offsite        Every 30 days                       │   │
│   │ Last: 15 days ago   Next: in 15 days                   │   │
│   │ [Edit] [Delete] [Run Now]                   [Toggle]    │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│   [+ Add Check Schedule]                                         │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## Testing Plan

### Unit Tests
- ✅ Test CheckScheduler.run_scheduled_checks()
- ✅ Test interval calculation logic
- ✅ Test notification triggering

### Integration Tests
- ✅ Create check schedule via API
- ✅ Wait for scheduled check to run
- ✅ Verify CheckJob created
- ✅ Verify notifications sent

### Manual Testing
- ✅ Configure check schedule in UI
- ✅ Wait for scheduled check
- ✅ Verify check runs automatically
- ✅ Verify notifications received
- ✅ Edit/disable schedule
- ✅ Delete schedule

---

## Rollout Plan

### Phase 2 Release (v1.26.0)
- Check notifications
- Settings UI for notifications
- Documentation

**Timeline:** 2-3 days

### Phase 3 Release (v1.27.0)
- Scheduled checks
- Unified Schedule tab UI
- Complete feature documentation

**Timeline:** 5-7 days

---

## Success Criteria

✅ Users can enable notifications for check success/failure
✅ Users can schedule checks with N-day intervals
✅ Scheduled checks run automatically in background
✅ Scheduled checks visible in unified Schedule tab
✅ Check history tracked in CheckJob table
✅ Notifications sent when checks complete
✅ Documentation complete and accurate

---

## Future Enhancements (Not in Initial Release)

- Cron-based check schedules (in addition to interval-based)
- Check templates (quick, full, repair)
- Health dashboard showing all repo check statuses
- Automatic checks after N backups
- Check reminders (warn if not checked in X days)
