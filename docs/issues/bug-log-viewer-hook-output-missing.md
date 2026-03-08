# Bug: Pre-backup script output not shown during running state; borg output lost after completion

## Summary

Two related log-visibility gaps caused by the separation between the hook-log path and the
borg-output path:

1. **During a running backup**: pre-backup script (hook) output is invisible in the log
   viewer — only borg output is shown.
2. **After a successful backup**: if the log-save policy is `failed_and_warnings` or
   `failed_only` (the defaults), the log viewer shows only the pre-backup script output —
   the borg output is gone.

## Steps to reproduce

### Issue 1 — Pre-script invisible during run

1. Configure a repository with a pre-backup script (e.g. `echo "starting vault backup"`).
2. Start a backup.
3. Open the log viewer immediately.
4. Observe: only borg output lines appear; the pre-script lines are missing.

### Issue 2 — Borg output missing after completion

1. Run a successful backup (return code 0, no warnings) with `log_save_policy` set to
   `failed_and_warnings` (the default).
2. After the backup completes, open the log viewer.
3. Observe: only the pre-backup script lines appear; the borg `create --stats` output is
   gone.

## Expected behaviour

The log viewer should show a continuous, ordered transcript of everything that happened:
pre-script output → borg output → post-script output — both while running and after
completion.

## Root cause

### Lifecycle mismatch between hook logs and log buffer

The backup execution in `backup_service.py` has two separate log paths:

| Path | Where written | When |
|------|---------------|------|
| `hook_logs` list | in-memory only | pre/post-backup script execution |
| `log_buffer` list | in-memory + temp log file | borg subprocess stdout/stderr |

Pre-backup hooks run **before** `log_buffer` and `log_file_handle` are created (lines
~1395–1441 vs ~1586–1601). Hook output accumulates in `hook_logs` but is never added to
the buffer, so the running-state API (`get_job_logs`) — which reads from `log_buffer` —
never sees it.

```python
# hooks run here, ~line 1400 — log_buffer doesn't exist yet
hook_result = await self._execute_hooks(...)
hook_logs.extend(hook_result["execution_logs"])

# buffer created here, ~line 1590 — hook_logs never added to it
log_buffer = []
self.log_buffers[job_id] = log_buffer
```

### Log-save policy discards borg output for successful jobs

At completion, the code checks `should_save_logs`. For a successful, warning-free backup
with policy `failed_and_warnings`:

```python
should_save_logs = (
    job.status in ['failed', 'cancelled'] or
    actual_returncode not in [0, None] or
    has_warnings
)
# → False for a clean success
```

When `should_save_logs` is `False`, the temp log file (which contains the borg output) is
deleted and only the hook logs are saved to `job.logs`:

```python
if hook_logs:
    job.logs = "\n".join(hook_logs)   # ← only pre-script lines
```

The activity API then falls back to `job.logs` for completed jobs that have no log file,
showing only the pre-script content.

## Fix

### 1 — Prepend pre-hook output to buffer and log file at buffer creation time

Track the pre-hook count, then after creating `log_buffer` and `log_file_handle`, write
the hook lines that have already been collected:

```python
pre_hook_count = len(hook_logs)
self.log_buffers[job_id] = log_buffer

if hook_logs:
    log_buffer.extend(hook_logs)           # visible in running view

if log_file_handle and hook_logs:
    for line in hook_logs:
        log_file_handle.write(line + '\n') # included at top of saved file
```

At the end, only append **post**-backup hooks to the file to avoid duplication:

```python
post_hook_logs = hook_logs[pre_hook_count:]
if post_hook_logs and temp_log_file and temp_log_file.exists():
    with open(temp_log_file, 'a') as f:
        f.write('\n=== Post-backup Hook Logs ===\n')
        f.write('\n'.join(post_hook_logs))
```

### 2 — Save full output to `job.logs` when log file is not kept

When `should_save_logs` is `False`, write the buffer contents (which now include
pre-hooks + borg output) plus any post-backup hooks to `job.logs`:

```python
post_hook_logs_nosave = hook_logs[pre_hook_count:]
combined = list(log_buffer) + list(post_hook_logs_nosave)
job.logs = "\n".join(combined) if combined else None
```

This ensures the completed-job view always has access to the full transcript regardless
of the log-save policy.

## Affected files

- `app/services/backup_service.py` — `run_backup` method, buffer creation and log-save
  sections
- `app/api/activity.py` — indirectly (reads `job.logs` as fallback for completed jobs)

---

## Working implementation

Both sub-issues are fixed and running in a fork. You can pull and test immediately
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
