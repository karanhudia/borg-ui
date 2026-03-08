# Bug: "Waiting for logs" placeholder lines repeat on every poll during running backup

## Summary

When a backup job is running but the log buffer hasn't been populated yet, the log viewer
appends the same 5 placeholder lines on every 2-second poll, producing an ever-growing
block of identical text before the real log output eventually appears.

## Steps to reproduce

1. Start a backup job that takes a few seconds to produce its first log line (e.g. has a
   pre-backup script, or is slow to connect).
2. Open the log viewer dialog immediately after starting.
3. Observe the terminal panel over the next 10–20 seconds.

## Expected behaviour

The placeholder message ("Waiting for logs…") appears once while the buffer is empty,
then disappears and is replaced by real log lines when they arrive.

## Actual behaviour

The placeholder block is appended fresh every 2 seconds. After 10 seconds you see the
same 5 lines repeated 5 times before real output starts.

```
1  Backup is currently running...
2
3  Waiting for logs...
4
5  Note: Showing last 500 lines from in-memory buffer...
6  Backup is currently running...
7
8  Waiting for logs...
9
10 Note: Showing last 500 lines from in-memory buffer...
...
```

## Root cause

Two interacting bugs:

**Backend** (`app/api/activity.py` — `get_job_logs`):
When the in-memory log buffer doesn't exist yet (`buffer_exists = False`) or exists but is
empty, the endpoint unconditionally returns 5 placeholder lines numbered 1–5, ignoring the
`offset` query parameter:

```python
lines = [
    "Backup is currently running...",
    "",
    "Waiting for logs...",
    "",
    "Note: Showing last 500 lines from in-memory buffer. Full logs not saved to disk."
]
return {
    'lines': [{'line_number': i + 1, 'content': line} for i, line in enumerate(lines)],
    'total_lines': len(lines),
    'has_more': False
}
```

Because `total_lines` is returned as 5, the frontend's next request uses `offset=5`.
The backend ignores that offset and returns lines 1–5 again.

**Frontend** (`frontend/src/components/TerminalLogViewer.tsx`):
The component uses an accumulate-and-append model (offset = current log count), so every
response with `lines.length > 0` is appended rather than replacing the display. There is
no deduplication guard.

## Fix

In `get_job_logs`, return an empty response when `offset > 0` and the buffer is not ready,
so placeholder lines are sent exactly once:

```python
if offset > 0:
    return {'lines': [], 'total_lines': 0, 'has_more': False}
```

Apply this guard to both the "buffer not created yet" and "buffer empty" branches.

## Affected files

- `app/api/activity.py` — `get_job_logs` endpoint, running-backup branch

---

## Working implementation

This fix is implemented and running in a fork. You can pull and test it immediately
without building anything:

```bash
docker run -d \
  --name borg-ui-test \
  -p 8082:8081 \
  -e SECRET_KEY=changeme \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=admin \
  ghcr.io/djlongy/borg-ui:latest
```

Or clone and build yourself:

```bash
git clone https://github.com/djlongy/borg-ui.git
cd borg-ui
# Native build (arm64 / Apple Silicon)
docker build -f Dockerfile.dev -t borg-ui-dev .
# Cross-compile for amd64
docker buildx build --platform linux/amd64 -f Dockerfile.dev -t borg-ui-dev:amd64 .
```

**Relevant commit**: [`c8f5e74`](https://github.com/djlongy/borg-ui/commit/c8f5e74)
`feat(sudo): add use_sudo option for remote SSH backups + fix log viewer`

**Fork**: https://github.com/djlongy/borg-ui
