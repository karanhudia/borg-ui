# Bug: Log viewer dialog status badge stays on "Running" after backup completes

## Summary

The status badge inside the log viewer dialog never updates from "Running" to "Completed"
(or "Failed") after a backup job finishes. The "Backup in progress…" indicator and the
live-streaming chip also remain visible indefinitely, even though the job has completed.

## Steps to reproduce

1. Start a backup job.
2. Immediately open the log viewer dialog while the job is running.
3. Wait for the backup to finish (visible on the background activity list).
4. Observe the log viewer dialog — the status badge still shows "Running".

## Expected behaviour

Within a few seconds of the job completing, the status badge updates to "Completed" (or
"Failed"), the "Live Streaming" chip disappears, and the log polling stops.

## Actual behaviour

The dialog continues to show `status="running"` indefinitely. The live-streaming chip
stays visible and log polling continues every 2 seconds even though the job is done.
The TerminalLogViewer never transitions out of its running state.

## Root cause

`LogViewerDialog` receives the job as a prop (`job: T`) and passes `job.status` directly
to `TerminalLogViewer` and `StatusBadge`. This prop is a snapshot of the job's state at
the time the dialog was opened — it is never refreshed:

```tsx
// LogViewerDialog.tsx — status is read once and never updated
<StatusBadge status={job.status} />
<TerminalLogViewer
  status={job.status}   // always the value from mount time
  ...
/>
```

`TerminalLogViewer` uses `status` to decide whether to poll:

```tsx
if (status === 'running') {
  const interval = setInterval(fetchLogs, 2000)
  return () => clearInterval(interval)
}
```

Because `status` never changes, the interval is never cleared.

## Fix

`LogViewerDialog` should maintain a `currentStatus` state initialised from `job.status`
and poll the activity API every 3 seconds while `currentStatus === 'running'`:

```tsx
const [currentStatus, setCurrentStatus] = useState(job?.status || 'unknown')

useEffect(() => {
  if (!open || !jobId || currentStatus !== 'running') return
  const poll = async () => {
    const res = await fetch(`/api/activity/recent?job_type=${jobType}&limit=100`, ...)
    const items = await res.json()
    const item = items.find(i => String(i.id) === String(jobId) && i.type === jobType)
    if (item && item.status !== 'running') setCurrentStatus(item.status)
  }
  const interval = setInterval(poll, 3000)
  return () => clearInterval(interval)
}, [open, jobId, jobType, currentStatus])
```

Pass `currentStatus` instead of `job.status` to both `StatusBadge` and `TerminalLogViewer`.

## Affected files

- `frontend/src/components/LogViewerDialog.tsx`

---

## Working implementation

This fix is implemented in a fork. Clone and build to try it:

```bash
git clone https://github.com/djlongy/borg-ui.git
cd borg-ui
docker build -f Dockerfile.dev -t borg-ui-dev .
docker run -d \
  --name borg-ui-test \
  -p 8082:8081 \
  -e SECRET_KEY=changeme \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=admin \
  borg-ui-dev
```

Start a backup, open the log viewer, and wait for it to finish — the status badge
updates to "Completed" within 3 seconds of the job ending.

> `Dockerfile.dev` uses `npx vite build` (skips TypeScript type-checking) so the
> build completes even if dev dependencies are mismatched. On amd64 hosts use
> `docker buildx build --platform linux/amd64 -f Dockerfile.dev ...` instead.

**Relevant commit**: [`c8f5e74`](https://github.com/djlongy/borg-ui/commit/c8f5e74)
`feat(sudo): add use_sudo option for remote SSH backups + fix log viewer`

**Fork**: https://github.com/djlongy/borg-ui
