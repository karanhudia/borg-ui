# Remote Direct Backup Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Borg UI answer GitHub issue #205 by executing same-host SSH source to SSH repository backups on the source host instead of silently falling back to SSHFS pull mode.

**Architecture:** Keep SSHFS pull mode for local repositories and different SSH source/repository hosts. Treat the existing `remote_direct` route as the source-host execution path, store it in `BackupJob.route_strategy`, derive `BackupJob.execution_mode` as `remote_ssh`, and delegate that job to `RemoteBackupService`. Use `SSHConnection.borg_binary_path` for source-host Borg or wrapper scripts; keep `Repository.remote_path` as the Borg remote repository-side path.

**Tech Stack:** FastAPI, SQLAlchemy models, async backup services, Pytest, React/Vite/MUI backup job tables, Storybook snapshots.

---

## Context

GitHub issue #205 asks whether Borg UI backs up remote sources by mounting/pulling them into the Borg UI container instead of running Borg on the remote host. Current code has both concepts:

- `BackupService` still converts remote source paths to `ssh://...` and mounts them with SSHFS for server-executed jobs.
- `RemoteBackupService` can run Borg through SSH on the source host and push to an SSH repository.
- `plan_repository_route()` already returns `remote_direct` when the SSH source connection and SSH repository connection are the same.
- `BackupPlanExecutionService` stores `execution_mode = route.strategy`, but `BackupService.execute_backup()` only delegates to `RemoteBackupService` for `execution_mode == "remote_ssh"`. A `remote_direct` plan therefore falls through to SSHFS pull behavior.

Product answer:

- Existing server-executed remote-source backups are pull based.
- Same SSH source plus same SSH repository should be direct remote execution.
- `Repository.remote_path` is not the source-host wrapper path. It maps to Borg's repository-side remote path. Source-host wrappers should use `SSHConnection.borg_binary_path`.
- Repository and plan scripts currently execute in the Borg UI control-plane environment. Full source-host pre/post hook execution is a separate feature unless the hook is implemented through the source-host Borg wrapper.

Remote execution metrics model:

- Borg UI still owns the backup job. The Borg UI server creates and stores the same `BackupJob` row before starting any work.
- The remote machine only runs the Borg command over SSH. It does not own Borg UI job state, the database row, Prometheus metrics, dashboard history, or UI polling state.
- `RemoteBackupService` starts an SSH subprocess from the Borg UI server, runs `borg create` on the source host, and streams the remote command's stdout and stderr back through that SSH process.
- As that stream arrives, Borg UI parses Borg's JSON/stats/progress output and writes updates onto the same `BackupJob` row: status, start/end timestamps, progress, progress percent when measurable, original/compressed/deduplicated sizes, file count, error text, and logs.
- Existing dashboard, job-history, and Prometheus metrics continue reading from `BackupJob` and `Repository` tables. The metrics consumers do not need to know whether Borg ran locally, through SSHFS pull mode, or directly on the source host.
- If the SSH command exits non-zero or drops, Borg UI marks the job failed with the SSH/Borg error. If Borg exits successfully, Borg UI marks the same job completed and records the final stats.
- The implementation must not invent precise live percentages when Borg does not provide enough information. It should preserve accurate phase/status messages and final byte/file stats, and only compute a percentage from known totals such as `total_expected_size`.

---

### Task 1: Add Route Execution Helpers

**Files:**
- Modify: `app/services/backup_route_planner.py`
- Test: `tests/unit/test_backup_route_planner.py`

- [ ] **Step 1: Write failing tests for execution mode derivation**

Add these tests to `tests/unit/test_backup_route_planner.py` after `test_plan_repository_route_supported_matrix`:

```python
from app.services.backup_route_planner import (
    execution_mode_for_route,
    plan_repository_route,
)


@pytest.mark.parametrize(
    "repository,sources,expected_execution_mode",
    [
        (repo(), [local_source()], "local"),
        (
            repo(repository_type="ssh", connection_id=2, path="ssh://borg@host/repo"),
            [local_source()],
            "local",
        ),
        (repo(), [ssh_source(3)], "local"),
        (
            repo(repository_type="ssh", connection_id=3),
            [ssh_source(3)],
            "remote_ssh",
        ),
        (
            repo(repository_type="ssh", connection_id=4),
            [ssh_source(3)],
            "local",
        ),
        (
            repo(executor_type="agent", execution_target="agent", agent_machine_id=10),
            [agent_source(10)],
            "agent",
        ),
    ],
)
def test_execution_mode_for_route(repository, sources, expected_execution_mode):
    route = plan_repository_route(repository, sources)

    assert route.supported is True
    assert execution_mode_for_route(route) == expected_execution_mode
```

- [ ] **Step 2: Run the focused route planner tests and confirm failure**

Run:

```bash
pytest tests/unit/test_backup_route_planner.py -q
```

Expected: FAIL because `execution_mode_for_route` does not exist.

- [ ] **Step 3: Implement `execution_mode_for_route`**

Add this helper near the bottom of `app/services/backup_route_planner.py`:

```python
def execution_mode_for_route(route: BackupRoutePlan) -> str:
    if route.executor == EXECUTOR_AGENT:
        return EXECUTOR_AGENT
    if route.strategy == "remote_direct":
        return "remote_ssh"
    return "local"
```

- [ ] **Step 4: Run route planner tests**

Run:

```bash
pytest tests/unit/test_backup_route_planner.py -q
```

Expected: PASS.

---

### Task 2: Use Remote Direct Execution In Backup Plans

**Files:**
- Modify: `app/services/backup_plan_execution_service.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] **Step 1: Write a failing backup-plan execution test**

Add this test near `test_execute_plan_run_uses_remote_plan_source_settings` in `tests/unit/test_api_backup_plans.py`:

```python
@pytest.mark.asyncio
async def test_execute_plan_run_uses_remote_direct_for_same_ssh_source_and_repo(
    self, test_db
):
    source_connection = _create_ssh_connection(
        test_db,
        is_backup_source=True,
        borg_binary_path="/usr/local/bin/borg-wrapper",
    )
    repo = _create_repo(
        test_db,
        "Primary",
        "/repos/primary",
        repository_type="ssh",
        connection_id=source_connection.id,
    )
    _plan, run = _create_execution_plan(
        test_db,
        [repo],
        source_type="remote",
        source_ssh_connection_id=source_connection.id,
        source_directories=json.dumps(["/var/lib/docker/volumes/app"]),
        source_locations=json.dumps(
            [
                {
                    "source_type": "remote",
                    "source_ssh_connection_id": source_connection.id,
                    "agent_machine_id": None,
                    "paths": ["/var/lib/docker/volumes/app"],
                }
            ]
        ),
    )

    async def fake_execute_backup(job_id, repository, db, **kwargs):
        job = db.query(BackupJob).filter_by(id=job_id).one()
        assert job.route_strategy == "remote_direct"
        assert job.execution_mode == "remote_ssh"
        assert job.source_ssh_connection_id == source_connection.id
        assert kwargs["source_ssh_connection_id"] == source_connection.id
        assert kwargs["source_directories"] == ["/var/lib/docker/volumes/app"]
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()

    with patch(
        "app.services.backup_plan_execution_service.backup_service.execute_backup",
        side_effect=fake_execute_backup,
    ):
        await backup_plan_execution_service.execute_run(run.id)

    test_db.expire_all()
    backup_job = test_db.query(BackupJob).filter_by(backup_plan_run_id=run.id).one()
    assert backup_job.route_strategy == "remote_direct"
    assert backup_job.execution_mode == "remote_ssh"
```

- [ ] **Step 2: Run the focused backup-plan test and confirm failure**

Run:

```bash
pytest tests/unit/test_api_backup_plans.py::TestBackupPlanExecution::test_execute_plan_run_uses_remote_direct_for_same_ssh_source_and_repo -q
```

Expected: FAIL because the job currently stores `execution_mode == "remote_direct"`.

- [ ] **Step 3: Derive execution mode from the route**

In `app/services/backup_plan_execution_service.py`, import the helper:

```python
from app.services.backup_route_planner import (
    execution_mode_for_route,
    plan_repository_route,
)
```

Replace this assignment in `_execute_repository`:

```python
backup_job.execution_mode = route.strategy or "local"
```

with:

```python
backup_job.execution_mode = execution_mode_for_route(route)
backup_job.route_strategy = route.strategy
```

Remove any later duplicate `backup_job.route_strategy = route.strategy` assignment in the same branch after adding the replacement above. After this task, `route_strategy` should be assigned once for server-executed backup plan jobs, and `execution_mode` should be assigned only through `execution_mode_for_route(route)`.

- [ ] **Step 4: Run related backup-plan tests**

Run:

```bash
pytest tests/unit/test_api_backup_plans.py::TestBackupPlanExecution -q
```

Expected: PASS.

---

### Task 3: Delegate Remote SSH Jobs To `RemoteBackupService`

**Files:**
- Modify: `app/services/backup_service.py`
- Test: `tests/unit/test_backup_service.py`

- [ ] **Step 1: Write a failing delegation test**

Add this test to the `TestBackupService` class in `tests/unit/test_backup_service.py`:

```python
@pytest.mark.asyncio
async def test_execute_backup_delegates_remote_ssh_execution_mode(
    self, backup_service, db_session, monkeypatch
):
    source_connection = SSHConnection(
        host="docker-host.example",
        username="backup",
        port=22,
        is_backup_source=True,
        borg_binary_path="/usr/local/bin/borg-wrapper",
    )
    repository = Repository(
        name="remote-direct",
        path="/repos/remote-direct",
        repository_type="ssh",
        connection_id=1,
        source_directories=json.dumps(["/var/lib/docker/volumes/app"]),
        compression="lz4",
    )
    db_session.add_all([source_connection, repository])
    db_session.flush()
    repository.connection_id = source_connection.id
    job = BackupJob(
        repository=repository.path,
        status="pending",
        execution_mode="remote_ssh",
        route_strategy="remote_direct",
        source_ssh_connection_id=source_connection.id,
    )
    db_session.add(job)
    db_session.commit()

    calls = []

    class FakeRemoteBackupService:
        async def execute_remote_backup(self, **kwargs):
            calls.append(kwargs)
            job.status = "completed"
            db_session.commit()

    monkeypatch.setattr(
        "app.services.backup_service.SessionLocal",
        lambda: db_session,
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.remote_backup_service",
        FakeRemoteBackupService(),
    )

    await backup_service.execute_backup(job.id, repository.path)

    assert calls == [
        {
            "job_id": job.id,
            "source_ssh_connection_id": source_connection.id,
            "repository_id": repository.id,
            "source_paths": ["/var/lib/docker/volumes/app"],
            "exclude_patterns": [],
            "compression": "lz4",
            "custom_flags": None,
            "upload_ratelimit_kib": None,
        }
    ]
```

- [ ] **Step 2: Run the focused backup service test and confirm failure**

Run:

```bash
pytest tests/unit/test_backup_service.py::TestBackupService::test_execute_backup_delegates_remote_ssh_execution_mode -q
```

Expected: FAIL if the monkeypatch target or delegation payload does not match current code. Adjust only the test fixture details needed to use existing local fixtures; keep the assertions about remote delegation intact.

- [ ] **Step 3: Centralize the remote execution-mode check**

In `app/services/backup_service.py`, add this module-level helper near imports or near `BackupService`:

```python
REMOTE_EXECUTION_MODES = {"remote_ssh"}


def _uses_remote_execution(job: BackupJob) -> bool:
    # Keep the route_strategy fallback for old rows and in-memory tests where
    # remote_direct was set before execution_mode was normalized to remote_ssh.
    # This mirrors the frontend label fallback in Task 5.
    return (
        (job.execution_mode or "").strip().lower() in REMOTE_EXECUTION_MODES
        or (job.route_strategy or "").strip().lower() == "remote_direct"
    )
```

Then replace:

```python
if job.execution_mode == "remote_ssh":
```

with:

```python
if _uses_remote_execution(job):
```

- [ ] **Step 4: Run backup service tests**

Run:

```bash
pytest tests/unit/test_backup_service.py::TestBackupService::test_execute_backup_delegates_remote_ssh_execution_mode tests/unit/test_backup_service.py::TestBackupService::test_prepare_source_paths_resolves_relative_remote_paths -q
```

Expected: PASS. The SSHFS preparation test proves non-remote-direct remote sources still use pull mode.

- [ ] **Step 5: Prove remote execution still updates job metrics**

Add or extend remote-backup service tests so a remote SSH backup writes to the same `BackupJob` row used by dashboards, job history, and Prometheus metrics. Cover at least:

- `status`, `started_at`, and `completed_at` are updated on success and failure.
- streamed Borg JSON/stats fields update `original_size`, `compressed_size`, `deduplicated_size`, and `nfiles`.
- `progress` and `progress_percent` are updated only when the service has a known total such as `total_expected_size`; otherwise the UI should rely on phase/status text and final stats.
- stderr or command failure output is retained as job error/log evidence.

Suggested focused tests:

```bash
pytest tests/unit/test_remote_backup_service.py tests/unit/test_api_metrics.py -q
```

Expected: PASS. The remote service tests prove source-host execution still persists job telemetry, and the metrics tests prove the existing metrics endpoint continues reading those persisted `BackupJob` fields.

---

### Task 4: Apply The Same Route To Manual And Scheduled Repository Backups

**Files:**
- Modify: `app/services/backup_route_planner.py`
- Modify: `app/api/backup.py`
- Modify: `app/api/schedule.py`
- Test: `tests/unit/test_api_backup.py`
- Test: `tests/unit/test_api_schedule.py` or `tests/unit/test_api_schedule_routes.py`

- [ ] **Step 1: Add a helper for repository-stored source settings**

In `app/services/backup_route_planner.py`, extend the imports:

```python
import json
from typing import Any, TYPE_CHECKING

from app.utils.source_locations import decode_source_locations

if TYPE_CHECKING:
    from app.database.models import BackupJob
```

Add:

```python
def source_locations_for_repository(repository: Repository) -> list[dict[str, Any]]:
    source_directories = []
    raw_sources = getattr(repository, "source_directories", None)
    if raw_sources:
        if isinstance(raw_sources, list):
            source_directories = raw_sources
        else:
            try:
                source_directories = json.loads(raw_sources)
            except (TypeError, json.JSONDecodeError):
                source_directories = []
    return decode_source_locations(
        getattr(repository, "source_locations", None),
        source_type="remote"
        if getattr(repository, "source_ssh_connection_id", None)
        else "local",
        source_ssh_connection_id=getattr(repository, "source_ssh_connection_id", None),
        source_directories=source_directories,
    )
```

- [ ] **Step 2: Add a helper to stamp backup jobs**

Add:

```python
def apply_repository_route_to_backup_job(
    backup_job: "BackupJob", repository: Repository
) -> None:
    route = plan_repository_route(repository, source_locations_for_repository(repository))
    if route.supported:
        backup_job.route_strategy = route.strategy
        backup_job.execution_mode = execution_mode_for_route(route)
```

Keep the `BackupJob` annotation behind `TYPE_CHECKING` so runtime imports stay one-way while static readers still see the expected object shape.

- [ ] **Step 3: Use the helper in manual backups**

In `app/api/backup.py`, import:

```python
from app.services.backup_route_planner import apply_repository_route_to_backup_job
```

After `backup_job = BackupJob(...)` in `_start_backup_impl`, before `db.add(backup_job)`, add:

```python
if repo_record is not None and not is_agent_executor(repo_record):
    apply_repository_route_to_backup_job(backup_job, repo_record)
```

- [ ] **Step 4: Use the helper in single-repository scheduled backups**

In `app/api/schedule.py`, import the same helper and call it after each single-repository `BackupJob(...)` is created and before `db.add(backup_job)`.

Apply this in the run-now path and in the scheduled dispatcher path. Do not change multi-repository schedule behavior until a route-specific test covers it, because Backup Plans are the preferred multi-repository route-aware path.

- [ ] **Step 5: Add API tests**

In `tests/unit/test_api_backup.py`, add a manual backup test that creates one SSH connection, a repository with both `connection_id` and `source_ssh_connection_id` set to that connection, starts a backup, and asserts:

```python
backup_job.execution_mode == "remote_ssh"
backup_job.route_strategy == "remote_direct"
```

In `tests/unit/test_api_schedule.py` or `tests/unit/test_api_schedule_routes.py`, add the same assertion for a single-repository schedule run-now path.

- [ ] **Step 6: Run API tests**

Run:

```bash
pytest tests/unit/test_api_backup.py tests/unit/test_api_schedule.py tests/unit/test_api_schedule_routes.py -q
```

Expected: PASS.

---

### Task 5: Expose Route Strategy And Label Remote Direct Jobs

**Files:**
- Modify: `app/api/backup.py`
- Modify: `frontend/src/types/jobs.ts`
- Modify: `frontend/src/components/BackupJobsTable.tsx`
- Modify: `frontend/src/components/__tests__/BackupJobsTable.test.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Storybook: update or add the nearest `BackupJobsTable` story if one exists

- [ ] **Step 1: Add backend response tests**

In `tests/unit/test_api_backup.py`, add assertions to the existing job list and status tests:

```python
job = BackupJob(
    repository=repo.path,
    status="running",
    execution_mode="remote_ssh",
    route_strategy="remote_direct",
)
```

Assert both `/api/backup/jobs` and `/api/backup/status/{job.id}` include:

```python
assert payload_job["execution_mode"] == "remote_ssh"
assert payload_job["route_strategy"] == "remote_direct"
```

- [ ] **Step 2: Include `route_strategy` in backup API payloads**

In `app/api/backup.py`, add:

```python
"route_strategy": job.route_strategy,
```

to both the `/api/backup/jobs` list item and `/api/backup/status/{job_id}` response.

- [ ] **Step 3: Update frontend types**

In `frontend/src/types/jobs.ts`, add:

```ts
route_strategy?: string | null
```

to `Job`.

- [ ] **Step 4: Update transport label logic**

Change `getTransportLabel` in `frontend/src/components/BackupJobsTable.tsx` to accept the route strategy:

```tsx
const getTransportLabel = (
  executionMode: string | null | undefined,
  routeStrategy: string | null | undefined,
  t: (key: string) => string
) => {
  if (executionMode === 'agent') return t('backupJobsTable.transport.agent')
  if (executionMode === 'remote_ssh' || routeStrategy === 'remote_direct') {
    return t('backupJobsTable.transport.remoteSsh')
  }
  if (!executionMode) return null
  return t('backupJobsTable.transport.server')
}
```

Update the render call:

```tsx
const transportLabel = getTransportLabel(
  job.execution_mode,
  job.route_strategy,
  t
)
```

- [ ] **Step 5: Add locale keys**

Add this key in each locale file:

```json
"remoteSsh": "Remote SSH"
```

Use the English value in non-English files if localized product terminology is not already obvious in the file.

- [ ] **Step 6: Add frontend tests**

In `frontend/src/components/__tests__/BackupJobsTable.test.tsx`, add:

```tsx
it('displays remote SSH transport for remote-direct backup jobs', () => {
  renderWithProviders(
    <BackupJobsTable
      jobs={[
        {
          ...mockJobs[0],
          id: 45,
          execution_mode: 'remote_ssh',
          route_strategy: 'remote_direct',
        } as MockBackupJob & {
          execution_mode: 'remote_ssh'
          route_strategy: 'remote_direct'
        },
      ]}
    />
  )

  expect(screen.getByText('Remote SSH')).toBeInTheDocument()
})
```

- [ ] **Step 7: Add or update Storybook coverage**

If a `BackupJobsTable` story exists, add a remote-direct job row. If no story exists, add the smallest story under the existing component story pattern that renders:

- one server job,
- one remote SSH job,
- one agent job.

Use chips only; do not add heavy left accent borders.

- [ ] **Step 8: Run frontend validation and snapshots**

Run from `frontend/`:

```bash
npm run check:locales
npm run typecheck
npm run lint
npm run build
npm run snapshots
```

Expected: all commands PASS, with updated snapshots committed under `frontend/storybook-snapshots/`.

---

### Task 6: Document Source-Host Borg Wrapper Semantics

**Files:**
- Modify: `docs/ssh-keys.md`
- Modify: `docs/troubleshooting.md`
- Optional Modify: `docs/configuration.md`

- [ ] **Step 1: Document remote direct behavior**

In `docs/ssh-keys.md`, add a short section near the remote machine backup source configuration:

```markdown
## Remote Direct Backups

When a backup plan uses an SSH source and an SSH repository on the same SSH
connection, Borg UI runs `borg create` on that remote machine and sends data
directly to the repository. This avoids SSHFS pull mode and keeps high-I/O
source reads on the Docker host.

Use the connection's Borg binary path when the source host needs a wrapper
script, for example to pause Docker containers before Borg starts and resume
them after Borg exits. The repository `remote_path` setting is different: it is
passed to Borg as the repository-side remote Borg path.
```

- [ ] **Step 2: Document fallback behavior**

In `docs/troubleshooting.md`, add:

```markdown
Remote source backups use SSHFS pull mode unless the source SSH connection and
the SSH repository connection are the same. Different SSH source/repository
pairs still run on the Borg UI server and may see warnings when active files
change during backup.
```

- [ ] **Step 3: Run docs-adjacent checks**

Run:

```bash
rg -n "Remote Direct Backups|repository-side remote Borg path" docs
```

Expected: both new documentation references are found.

---

### Task 7: Backend Validation

**Files:**
- No new files unless previous tasks required test fixture adjustments

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
pytest tests/unit/test_backup_route_planner.py tests/unit/test_api_backup.py tests/unit/test_api_backup_plans.py tests/unit/test_api_schedule.py tests/unit/test_api_schedule_routes.py tests/unit/test_backup_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Run required backend lint/format checks**

Run:

```bash
ruff check app tests
ruff format --check app tests
```

Expected: PASS.

- [ ] **Step 3: Run whitespace/conflict-marker check**

Run:

```bash
git diff --check
```

Expected: PASS with no output.

---

### Task 8: Runtime Smoke Check

**Files:**
- No committed file changes from temporary smoke configuration

- [ ] **Step 1: Launch Borg UI**

Run one of the existing runtime paths:

```bash
./scripts/dev.sh
```

or:

```bash
docker compose up -d --build
```

Expected: backend and frontend start successfully.

- [ ] **Step 2: Validate the user path**

In the running app:

1. Add or use one SSH connection that is enabled as a backup source and has a Borg binary path.
2. Create an SSH repository using the same SSH connection.
3. Create a backup plan whose source is that same SSH connection.
4. Run the plan.
5. Confirm the job row shows `Remote SSH`.
6. Confirm job details show `route_strategy = remote_direct` in API output.
7. Confirm logs or service traces show `RemoteBackupService` executing SSH, not SSHFS mount preparation.
8. Confirm the job status/progress API and `/metrics` endpoint still reflect the same backup job after the remote command completes.

- [ ] **Step 3: Clean temporary runtime state**

Remove any local test SSH connection, repository, or backup plan records created only for the smoke run unless they live in disposable development data.

---

## Non-Goals

- Do not make every remote source backup execute remotely. Different SSH source/repository pairs still use server SSHFS pull plus Borg SSH until a separate design covers multi-hop direct execution.
- Do not reinterpret `Repository.remote_path` as a source-host wrapper. Use `SSHConnection.borg_binary_path` for source-host wrappers.
- Do not add remote source-host script-library execution in this slice. Source-host pre/post hooks need a separate security and UX design because scripts currently live and execute in the Borg UI control-plane context.

## Self-Review

- Spec coverage: Covers the GitHub issue answer, the confirmed route mismatch, direct remote execution, job telemetry/metrics flow, wrapper semantics, UI labeling, docs, and validation.
- Placeholder scan: No unresolved placeholders remain.
- Type consistency: Uses existing `BackupRoutePlan.strategy`, `BackupJob.route_strategy`, `BackupJob.execution_mode`, `SSHConnection.borg_binary_path`, and `Repository.remote_path` names.
