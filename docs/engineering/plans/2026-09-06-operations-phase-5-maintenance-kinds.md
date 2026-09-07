# Operations Phase 5: Maintenance Kinds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit at the
> end of a task; the phase has one commit gate (G2) at the end, per section
> 19.4 of the spec and `.claude/instructions.md`.

**Goal:** Move check, prune, compact, delete archive, and restore check off
their five per-kind job tables onto the `operations` table and the runner, so
they queue behind one lane instead of racing for the Borg lock, appear in the
Background work board, and gain the spec 7.4 follow-up chain in place of the
stats calls each service makes for itself.

**Architecture:** The five services already take a job id and drive a row that
carries status, progress, logs, and timings. Phase 5 keeps those service
bodies and swaps what the id resolves to. A new module
`app/services/operations/job_facade.py` wraps an `Operation` row in the legacy
attribute surface, so `resolve_maintenance_job(db, job_id, kind)` returns an
operation-backed facade for new work and the real legacy row for historical
ids. One lookup line changes per service. A new executor module
`app/services/operations/executors/maintenance.py` registers one executor per
kind; each loads the repository, calls the existing `BorgRouter` entry point
with the operation id, then turns the facade's final status into an `Outcome`.
The start routes and the two schedulers call `enqueue()` instead of
`start_background_maintenance_job()`. The read routes keep their exact HTTP
contract and serve operations first with a legacy fallback, because the
serializers in `app/api/maintenance_jobs.py` are already duck-typed.

**Tech Stack:** FastAPI, SQLAlchemy 1.x declarative models, asyncio subprocess
handling in the existing services, `BorgRouter` for the v1/v2/agent split,
pytest with the `test_db` / `test_client` / `admin_headers` fixtures from
`tests/fixtures/api.py` and the in-memory `db` fixture pattern from
`tests/unit/test_operations_index_executors.py`. No new dependencies, no
migration: `operations` and every column this phase needs already exist from
phase 1.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
(sections 6.1, 6.2, 6.3, 7.1 to 7.8, 9.1, 9.3, 13, 19, Appendix A.2,
Appendix B).

## Model per task

Spec section 13 splits phase 5 between two models. Run `/continue-spec` on the
model of the first unchecked task; gate G0 compares against this table, not
against a single phase model.

| Tasks | Model | Why |
| --- | --- | --- |
| 1 to 2 | Opus 5 | The facade and the check migration are the pattern every other kind copies. Section 13: "Opus 5 for the first kind and the follow-up wiring". |
| 3 to 6 | Sonnet 5 | Prune, compact, delete archive, restore check repeat task 2 against a fixed interface. |
| 7 to 8 | Opus 5 | Maintenance after backup is the behavioural drift the reviewer is told to hunt for, and the retirement task deletes shared helpers. |
| 9 | Sonnet 5 | Documentation and verification. |

## Global Constraints

- Phase 5 is backend only. No frontend file changes, no i18n keys, no
  stories. Every HTTP response body in this phase keeps the exact shape it
  has today, per section 13: "Phases 5 through 9 are internal refactors with
  no visible change except fewer lock errors."
- No new database columns and no Alembic revision. The five legacy tables stay
  in the schema and keep their historical rows; phase 9 deletes them. Nothing
  in this phase writes a new row to `check_jobs`, `prune_jobs`,
  `compact_jobs`, `delete_archive_jobs`, or `restore_check_jobs`.
- Spec 6.2 is verbatim: check, prune, compact, restore check, and delete
  archive get no extension table. Their inputs (`max_duration`,
  `extra_flags`, `probe_paths`, `full_archive`, `archive_name`, the six
  `keep_*` values and `keep_within`) live in `operations.params`, and nothing
  else goes there.
- Spec 6.3 is verbatim for kind, category, exclusivity, trigger, and
  priority. All five kinds are category `maintenance`; check, prune, compact,
  and delete archive are exclusive; `restore_check` is category `restore` and
  not exclusive. Do not edit `vocab.py`; it already carries all five.
- Spec 7.4 chain table is verbatim and already in `followups.py`. Phase 5
  changes no chain. It only makes the chains fire, because until now no
  maintenance kind ever reached a terminal operations status.
- Trigger mapping is fixed: a user pressing the button is `manual`, the check
  and restore-check schedulers are `schedule`, prune or compact or check that
  a backup plan or a scheduled job runs afterwards is `plan`, and the runner's
  own chain is `followup`. Never invent a trigger.
- Every Borg call stays inside the service it lives in today. Do not move
  Borg invocation into the executor, and do not add a second
  `run_serialized_repository_command` wrapper around a service that already
  has one.
- Never commit or push without the user's answer at gate G2. Do not use em
  dashes anywhere: not in code, comments, docstrings, log messages, JSON
  copy, or docs. Use commas, periods, or parentheses.
- Every new module gets unit tests under `tests/unit/`. Every route touched
  gets a test through `test_client`. Run
  `python -m pytest tests/unit -q -x -p no:cacheprovider` and
  `ruff check app tests` before claiming a task done.
- `tests/unit/test_source_discovery.py` has three database-scan failures that
  predate this branch and pass in isolation. They are not yours; do not fix
  them and do not let them block a task.

## File Structure

Created:

- `app/services/operations/job_facade.py` `MAINTENANCE_KINDS`,
  `MaintenanceJobFacade`, `resolve_maintenance_job()`, `claim_running()`,
  `legacy_status()`, `operation_status()`, `params_for()`
- `app/services/operations/executors/maintenance.py` `run_check()`,
  `run_prune()`, `run_compact()`, `run_delete_archive()`,
  `run_restore_check()`, `cancel_watcher()`
- `app/services/operations/maintenance_start.py` `start_maintenance()`,
  the one enqueue helper every route and scheduler calls
- `tests/unit/test_operations_job_facade.py`
- `tests/unit/test_operations_maintenance_executors.py`
- `tests/unit/test_maintenance_start.py`
- `tests/unit/test_api_maintenance_migration.py`

Modified:

- `app/services/operations/executors/__init__.py` load the maintenance module
- `app/services/check_service.py`, `prune_service.py`, `compact_service.py`,
  `delete_archive_service.py`, `restore_check_service.py` one job lookup line
  each, plus the second lookup in `delete_archive_service.py` and
  `restore_check_service.py`
- `app/services/v2/check_service.py`, `v2/prune_service.py`,
  `v2/compact_service.py`, `v2/delete_archive_service.py` the job lookup and
  the conditional claim update
- `app/api/repositories.py` the check, restore check, compact, and prune start
  routes; the eight job read routes; `_dispatch_router_*` helpers deleted
- `app/api/archives.py` the delete route, its status route, and its cancel
  route
- `app/api/activity.py` the two `job_models` maps and `_is_operation_only_kind`
- `app/api/agents.py` `_get_repository_operation_job`,
  `_sync_repository_operation_progress`,
  `_finish_linked_repository_operation_job`
- `app/services/repository_executor.py` `maintenance_table_by_kind` and the
  admission ignore
- `app/services/check_scheduler.py`, `restore_check_scheduler.py` enqueue
  instead of dispatch
- `app/api/schedule.py`, `app/services/backup_plan_execution_service.py`
  maintenance after backup
- `app/utils/process_utils.py` drop the five tables from
  `cleanup_orphaned_jobs`
- `app/api/maintenance_jobs.py` delete the five retired helpers
- `app/services/job_admission.py` drop the five kinds from the maintenance
  admission path
- `docs/architecture/job-system.md`, `docs/api.md`,
  `Borg_UI_API.postman_collection.json`
- The spec's section 19.1 progress row

---

### Task 1: The operation-backed maintenance job facade

The five services all drive a row through the same small attribute surface:
`status`, `started_at`, `completed_at`, `progress`, `progress_message`,
`error_message`, `logs`, `has_logs`, `log_file_path`, `process_pid`,
`process_start_time`, plus their own inputs. Every one of those has a column
on `operations` already (spec 6.1) except `logs` and `has_logs`, which are the
deprecated text mirror of the log file, and the inputs, which spec 6.2 puts in
`params`. This task builds the object that presents an `Operation` through
that surface so the service bodies do not change.

**Files:**
- Create: `app/services/operations/job_facade.py`
- Test: `tests/unit/test_operations_job_facade.py`

**Interfaces:**
- Consumes: `Operation` from `app.database.models`, `operation_log_path()`
  from `app.services.operations.runner`.
- Produces:
  - `MAINTENANCE_KINDS: tuple[str, ...]`
  - `PARAM_FIELDS: dict[str, tuple[str, ...]]`
  - `MaintenanceJobFacade(db, operation)` with the attribute surface above
  - `resolve_maintenance_job(db, job_id, kind) -> Any | None`
  - `claim_running(db, job_id, kind, started_at) -> int`
  - `legacy_status(operation_status) -> str`
  - `operation_status(legacy_status) -> str`

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_job_facade.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, CheckJob, Operation, Repository
from app.services.operations.job_facade import (
    MAINTENANCE_KINDS,
    MaintenanceJobFacade,
    claim_running,
    legacy_status,
    operation_status,
    resolve_maintenance_job,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def repository(db):
    repo = Repository(name="nas", path="/repo/nas")
    db.add(repo)
    db.commit()
    return repo


def _operation(db, repository, *, kind="check", params=None, status="running"):
    op = Operation(
        repository_id=repository.id,
        kind=kind,
        category="maintenance",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {},
    )
    db.add(op)
    db.commit()
    return op


def test_every_maintenance_kind_is_a_known_kind():
    from app.services.operations.vocab import KINDS

    for kind in MAINTENANCE_KINDS:
        assert kind in KINDS


def test_status_words_map_both_ways():
    assert operation_status("pending") == "queued"
    assert operation_status("running") == "running"
    assert operation_status("completed") == "completed"
    assert legacy_status("queued") == "pending"
    assert legacy_status("completed_with_warnings") == "completed_with_warnings"


def test_facade_writes_status_through_to_the_operation(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    job.status = "completed"
    db.commit()

    assert op.status == "completed"
    assert job.status == "completed"


def test_facade_maps_pending_to_queued(db, repository):
    op = _operation(db, repository, status="queued")
    job = MaintenanceJobFacade(db, op)

    assert job.status == "pending"

    job.status = "pending"
    assert op.status == "queued"


def test_facade_progress_is_an_integer_percent(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    job.progress = 40
    db.commit()

    assert op.progress_percent == 40.0
    assert job.progress == 40


def test_facade_reads_inputs_from_params(db, repository):
    op = _operation(
        db,
        repository,
        params={"max_duration": 3600, "extra_flags": "--verify-data"},
    )
    job = MaintenanceJobFacade(db, op)

    assert job.max_duration == 3600
    assert job.extra_flags == "--verify-data"
    assert job.scheduled_check is False


def test_facade_rejects_an_input_the_kind_does_not_have(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    with pytest.raises(AttributeError):
        job.keep_daily


def test_facade_logs_round_trip_through_the_log_file(db, repository, tmp_path):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    job.logs = "line one\nline two\n"
    db.commit()

    assert op.log_file_path
    assert job.logs == "line one\nline two\n"
    assert job.has_logs is True


def test_facade_identity_matches_the_operation(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    assert job.id == op.id
    assert job.repository_id == repository.id
    assert job.repository_path == repository.path


def test_resolve_prefers_an_operation_of_the_right_kind(db, repository):
    op = _operation(db, repository, kind="check")

    resolved = resolve_maintenance_job(db, op.id, "check")

    assert isinstance(resolved, MaintenanceJobFacade)
    assert resolved.id == op.id


def test_resolve_ignores_an_operation_of_another_kind(db, repository):
    op = _operation(db, repository, kind="prune")
    legacy = CheckJob(id=op.id, repository_id=repository.id, status="completed")
    db.add(legacy)
    db.commit()

    resolved = resolve_maintenance_job(db, op.id, "check")

    assert isinstance(resolved, CheckJob)


def test_resolve_falls_back_to_the_legacy_row(db, repository):
    legacy = CheckJob(repository_id=repository.id, status="completed")
    db.add(legacy)
    db.commit()

    resolved = resolve_maintenance_job(db, legacy.id, "check")

    assert isinstance(resolved, CheckJob)


def test_resolve_returns_none_when_nothing_matches(db):
    assert resolve_maintenance_job(db, 4242, "check") is None


def test_claim_running_claims_a_queued_operation_once(db, repository):
    from datetime import datetime

    op = _operation(db, repository, status="queued")
    started = datetime(2026, 9, 6, 12, 0, 0)

    assert claim_running(db, op.id, "check", started) == 1
    db.refresh(op)
    assert op.status == "running"
    assert op.started_at == started

    op.status = "completed"
    db.commit()
    assert claim_running(db, op.id, "check", started) == 0
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_job_facade.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.operations.job_facade'`

- [x] **Step 3: Write the facade**

```python
# app/services/operations/job_facade.py
"""An `operations` row wearing the legacy maintenance-job attribute surface.

The five maintenance services (check, prune, compact, delete archive, restore
check) each take a job id and drive one row through a small set of attributes.
Phase 5 (spec section 13) moves the row from a per-kind table to `operations`
without rewriting those services: `resolve_maintenance_job()` hands them this
facade instead of the legacy model, and every attribute write lands on the
operation's own columns (spec 6.1). Kind-specific inputs live in
`operations.params`, since spec 6.2 gives these kinds no extension table.

Deleted in phase 9 with the legacy tables, at which point the services can
read `Operation` directly.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import (
    CheckJob,
    CompactJob,
    DeleteArchiveJob,
    Operation,
    PruneJob,
    Repository,
    RestoreCheckJob,
)

MAINTENANCE_KINDS: tuple[str, ...] = (
    "check",
    "prune",
    "compact",
    "delete_archive",
    "restore_check",
)

LEGACY_MODELS: dict[str, Any] = {
    "check": CheckJob,
    "prune": PruneJob,
    "compact": CompactJob,
    "delete_archive": DeleteArchiveJob,
    "restore_check": RestoreCheckJob,
}

# The inputs each kind carries in `operations.params` (spec 6.2). A service
# reading anything outside its own tuple is a bug, so the facade raises
# rather than returning None and letting a wrong flag through silently.
PARAM_FIELDS: dict[str, tuple[str, ...]] = {
    "check": ("max_duration", "extra_flags", "scheduled_check"),
    "prune": (
        "keep_hourly",
        "keep_daily",
        "keep_weekly",
        "keep_monthly",
        "keep_quarterly",
        "keep_yearly",
        "keep_within",
        "dry_run",
        "scheduled_prune",
    ),
    "compact": ("scheduled_compact",),
    "delete_archive": ("archive_name",),
    "restore_check": (
        "archive_name",
        "probe_paths",
        "full_archive",
        "scheduled_restore_check",
    ),
}

# Params whose absence means False rather than None, so a service testing
# `if job.scheduled_check:` behaves as it does against the legacy column.
_BOOLEAN_PARAMS = frozenset(
    {
        "scheduled_check",
        "scheduled_prune",
        "scheduled_compact",
        "scheduled_restore_check",
        "full_archive",
        "dry_run",
    }
)

# Only "pending" differs between the two vocabularies (spec 6.3); every other
# legacy word is already an operations word.
_LEGACY_TO_OPERATION = {"pending": "queued"}
_OPERATION_TO_LEGACY = {"queued": "pending"}


def operation_status(status: str) -> str:
    """The operations word for a status a legacy service wrote."""
    return _LEGACY_TO_OPERATION.get(status, status)


def legacy_status(status: str) -> str:
    """The legacy word for an operations status, for readers still speaking
    the old vocabulary (the job status routes, the agent callbacks)."""
    return _OPERATION_TO_LEGACY.get(status, status)


class MaintenanceJobFacade:
    """One `Operation` presented as a legacy maintenance job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "_fields", PARAM_FIELDS.get(operation.kind, ()))

    # -- identity ----------------------------------------------------------

    @property
    def id(self) -> int:
        return self.operation.id

    @property
    def kind(self) -> str:
        return self.operation.kind

    @property
    def repository_id(self) -> Optional[int]:
        return self.operation.repository_id

    @property
    def repository_path(self) -> Optional[str]:
        params = self.operation.params or {}
        if params.get("repository_path"):
            return params["repository_path"]
        if self.operation.repository_id is None:
            return None
        repository = self._db.get(Repository, self.operation.repository_id)
        return repository.path if repository is not None else None

    @property
    def created_at(self):
        return self.operation.created_at

    # -- lifecycle ---------------------------------------------------------

    @property
    def status(self) -> str:
        return legacy_status(self.operation.status)

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = operation_status(value)

    @property
    def started_at(self):
        return self.operation.started_at

    @started_at.setter
    def started_at(self, value) -> None:
        self.operation.started_at = value

    @property
    def completed_at(self):
        return self.operation.completed_at

    @completed_at.setter
    def completed_at(self, value) -> None:
        self.operation.completed_at = value

    @property
    def error_message(self):
        return self.operation.error_message

    @error_message.setter
    def error_message(self, value) -> None:
        self.operation.error_message = value

    # -- progress ----------------------------------------------------------

    @property
    def progress(self) -> int:
        return int(self.operation.progress_percent or 0)

    @progress.setter
    def progress(self, value) -> None:
        self.operation.progress_percent = float(value or 0)

    @property
    def progress_message(self):
        return self.operation.progress_message

    @progress_message.setter
    def progress_message(self, value) -> None:
        self.operation.progress_message = value

    # -- process ownership (spec 7.6 reads these on restart) ---------------

    @property
    def process_pid(self):
        return self.operation.process_pid

    @process_pid.setter
    def process_pid(self, value) -> None:
        self.operation.process_pid = value

    @property
    def process_start_time(self):
        return self.operation.process_start_time

    @process_start_time.setter
    def process_start_time(self, value) -> None:
        self.operation.process_start_time = value

    # -- logs --------------------------------------------------------------

    @property
    def log_file_path(self):
        return self.operation.log_file_path

    @log_file_path.setter
    def log_file_path(self, value) -> None:
        self.operation.log_file_path = value

    @property
    def logs(self) -> str:
        """The legacy `logs` column was a text mirror of the log file. The
        operation keeps only the file, so reads come from disk."""
        path = self.operation.log_file_path
        if not path:
            return ""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return ""

    @logs.setter
    def logs(self, value) -> None:
        from app.services.operations.runner import operation_log_path

        text = value or ""
        path = self.operation.log_file_path
        if not path:
            resolved = operation_log_path(self.operation.id)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            path = str(resolved)
            self.operation.log_file_path = path
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            pass

    @property
    def has_logs(self) -> bool:
        return bool(self.logs)

    @has_logs.setter
    def has_logs(self, value) -> None:
        """Derived from the file. Accepted and dropped so a service that sets
        it alongside `logs` keeps working."""
        return None

    # -- kind-specific inputs ---------------------------------------------

    def __getattr__(self, name: str):
        # Only reached when normal lookup fails, so every property above wins.
        fields = object.__getattribute__(self, "_fields")
        if name not in fields:
            raise AttributeError(
                f"{object.__getattribute__(self, 'operation').kind} operations "
                f"carry no {name!r}"
            )
        params = object.__getattribute__(self, "operation").params or {}
        if name in _BOOLEAN_PARAMS:
            return bool(params.get(name, False))
        return params.get(name)


def resolve_maintenance_job(db: Session, job_id: int, kind: str) -> Any:
    """The job a maintenance service should drive for `job_id`.

    Operations win, so new work runs on the new table. Ids that belong to a
    row written before this phase fall back to the legacy table, which keeps
    the job status routes and the agent callbacks working for history.
    """
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == kind)
        .first()
    )
    if operation is not None:
        return MaintenanceJobFacade(db, operation)
    model = LEGACY_MODELS.get(kind)
    if model is None:
        return None
    return db.query(model).filter(model.id == job_id).first()


def claim_running(db: Session, job_id: int, kind: str, started_at: datetime) -> int:
    """Conditionally mark the job running, returning the number of rows
    claimed. The v2 services use this shape so two dispatches of the same id
    cannot both start work."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == kind)
        .first()
    )
    if operation is not None:
        return (
            db.query(Operation)
            .filter(
                Operation.id == job_id,
                Operation.status.in_(("queued", "running")),
            )
            .update(
                {"status": "running", "started_at": started_at},
                synchronize_session=False,
            )
        )
    model = LEGACY_MODELS[kind]
    return (
        db.query(model)
        .filter(model.id == job_id, model.status.in_(("pending", "running")))
        .update(
            {"status": "running", "started_at": started_at},
            synchronize_session=False,
        )
    )
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_job_facade.py -q -p no:cacheprovider`
Expected: PASS, 14 tests.

- [x] **Step 5: Lint**

Run: `ruff check app/services/operations/job_facade.py tests/unit/test_operations_job_facade.py`
Expected: no findings. Do not commit; the phase commits once at G2.

---

### Task 2: Check on the runner, the pattern the other four copy

Check moves in one piece: nothing writes a `check_jobs` row afterwards. The
route, both schedulers, the executor, admission, the read routes, the agent
callbacks, and the startup cleanup all change together, because a half
migrated kind would have work in two tables at once.

Read `app/api/repositories.py:5321-5420` (the start route),
`:6426-6491` (the two read routes), `app/services/check_scheduler.py:180-215`,
and `app/services/check_service.py:50-70` before starting.

**Files:**
- Create: `app/services/operations/maintenance_start.py`
- Create: `app/services/operations/executors/maintenance.py`
- Modify: `app/services/operations/executors/__init__.py`
- Modify: `app/services/job_admission.py`
- Modify: `app/services/check_service.py:59`, `app/services/v2/check_service.py:58,105`
- Modify: `app/api/repositories.py` check start route, both check read routes,
  `_dispatch_router_check`
- Modify: `app/services/check_scheduler.py`
- Modify: `app/api/activity.py:1151,1477`
- Modify: `app/api/agents.py:102,482-560`
- Modify: `app/services/repository_executor.py:337-352`
- Modify: `app/utils/process_utils.py:566-567` and its check branch
- Test: `tests/unit/test_maintenance_start.py`,
  `tests/unit/test_operations_maintenance_executors.py`,
  `tests/unit/test_api_maintenance_migration.py`

**Interfaces:**
- Consumes: `MaintenanceJobFacade`, `resolve_maintenance_job`, `claim_running`
  from Task 1; `enqueue()` from `app.services.operations.enqueue`; `Outcome`
  and `operation_log_path()` from `app.services.operations.runner`.
- Produces:
  - `start_maintenance(db, repository, kind, *, trigger, params, user_id, duplicate_error_key) -> Operation`
  - `active_maintenance_operation(db, repository_id, kind) -> Operation | None`
  - `run_check(ctx) -> Outcome` registered as executor `check`
  - `cancel_watcher(ctx, canceller)` used by every maintenance executor

- [x] **Step 1: Write the failing tests for the enqueue helper**

```python
# tests/unit/test_maintenance_start.py
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.maintenance_start import (
    active_maintenance_operation,
    start_maintenance,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def repository(db):
    repo = Repository(name="nas", path="/repo/nas")
    db.add(repo)
    db.commit()
    return repo


def test_start_enqueues_a_queued_operation(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={"max_duration": 3600, "extra_flags": None},
        user_id=7,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert op.status == "queued"
    assert op.kind == "check"
    assert op.category == "maintenance"
    assert op.trigger == "manual"
    assert op.repository_id == repository.id
    assert op.triggered_by_user_id == 7
    assert op.params["max_duration"] == 3600


def test_start_rejects_a_second_check_on_the_same_repository(db, repository):
    start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    with pytest.raises(HTTPException) as excinfo:
        start_maintenance(
            db,
            repository,
            "check",
            trigger="manual",
            params={},
            user_id=None,
            duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["key"] == "backend.errors.repo.checkAlreadyRunning"


def test_start_allows_a_different_kind_to_queue_alongside(db, repository):
    start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    prune = start_maintenance(
        db,
        repository,
        "prune",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.pruneAlreadyRunning",
    )

    assert prune.status == "queued"


def test_start_allows_a_new_run_once_the_last_one_finished(db, repository):
    first = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )
    first.status = "completed"
    db.commit()

    second = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert second.id != first.id


def test_active_maintenance_operation_finds_queued_and_running(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="schedule",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert active_maintenance_operation(db, repository.id, "check").id == op.id

    op.status = "running"
    db.commit()
    assert active_maintenance_operation(db, repository.id, "check").id == op.id

    op.status = "failed"
    db.commit()
    assert active_maintenance_operation(db, repository.id, "check") is None


def test_params_drop_none_values(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={"max_duration": None, "extra_flags": "--verify-data"},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert "max_duration" not in op.params
    assert op.params["extra_flags"] == "--verify-data"
```

- [x] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/unit/test_maintenance_start.py -q -p no:cacheprovider`
Expected: FAIL, `No module named 'app.services.operations.maintenance_start'`

- [x] **Step 3: Write the enqueue helper**

```python
# app/services/operations/maintenance_start.py
"""The one way a maintenance kind starts (spec 7.1, 7.2 and section 13
phase 5).

Before this phase each route created its own job row and dispatched a task
straight away, so a second kind arriving during a backup was rejected with a
409. Now the route only enqueues; the runner starts the work when the
repository's lane is free. The single rejection left is the duplicate: asking
for a check while a check is already queued or running still answers 409, so
the button keeps behaving as users expect.
"""

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database.models import Operation, Repository
from app.services.operations.enqueue import enqueue
from app.services.operations.job_facade import MAINTENANCE_KINDS

ACTIVE_STATUSES = ("queued", "running")


def active_maintenance_operation(
    db: Session, repository_id: int, kind: str
) -> Optional[Operation]:
    return (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == kind,
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Operation.id.desc())
        .first()
    )


def start_maintenance(
    db: Session,
    repository: Repository,
    kind: str,
    *,
    trigger: str,
    params: dict[str, Any],
    user_id: Optional[int],
    duplicate_error_key: str,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
) -> Operation:
    if kind not in MAINTENANCE_KINDS:
        raise ValueError(f"Not a maintenance kind: {kind!r}")
    if active_maintenance_operation(db, repository.id, kind) is not None:
        raise HTTPException(
            status_code=409, detail={"key": duplicate_error_key}
        )
    # None means "not supplied"; storing it would shadow a service default.
    stored = {key: value for key, value in params.items() if value is not None}
    return enqueue(
        db,
        kind,
        repository_id=repository.id,
        trigger=trigger,
        params=stored,
        triggered_by_user_id=user_id,
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
    )
```

- [x] **Step 4: Run them and watch them pass**

Run: `python -m pytest tests/unit/test_maintenance_start.py -q -p no:cacheprovider`
Expected: PASS, 6 tests.

- [x] **Step 5: Write the failing executor tests**

```python
# tests/unit/test_operations_maintenance_executors.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.executors import get_executor, load_default_executors
from app.services.operations.job_facade import MaintenanceJobFacade


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def repository(db):
    repo = Repository(name="nas", path="/repo/nas")
    db.add(repo)
    db.commit()
    return repo


class FakeContext:
    """The slice of OperationContext a maintenance executor uses."""

    def __init__(self, db, operation):
        self.db = db
        self.operation = operation
        self.operation_id = operation.id
        self.repository_id = operation.repository_id
        self.kind = operation.kind
        self.params = dict(operation.params or {})
        self.lines = []
        self._cancelled = False

    def cancelled(self):
        return self._cancelled

    def log(self, line):
        self.lines.append(line)

    async def progress(self, **kwargs):
        return None


def _operation(db, repository, kind="check", params=None):
    op = Operation(
        repository_id=repository.id,
        kind=kind,
        category="maintenance",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {},
    )
    db.add(op)
    db.commit()
    return op


def test_every_maintenance_kind_has_an_executor():
    load_default_executors()
    for kind in ("check", "prune", "compact", "delete_archive", "restore_check"):
        assert get_executor(kind) is not None


@pytest.mark.asyncio
async def test_check_reports_the_status_the_service_wrote(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, params={"max_duration": 3600})
    ctx = FakeContext(db, op)

    async def fake_check(self, job_id):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.check", fake_check, raising=True
    )

    outcome = await maintenance.run_check(ctx)

    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_check_reports_failure_with_the_services_message(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def fake_check(self, job_id):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = "borg exited 2"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.check", fake_check, raising=True
    )

    outcome = await maintenance.run_check(ctx)

    assert outcome.status == "failed"
    assert outcome.error_message == "borg exited 2"


@pytest.mark.asyncio
async def test_check_skips_when_the_repository_is_gone(db, repository):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    db.delete(repository)
    db.commit()
    ctx = FakeContext(db, op)

    outcome = await maintenance.run_check(ctx)

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"


@pytest.mark.asyncio
async def test_check_stamps_last_check_on_success(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def fake_check(self, job_id):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.check", fake_check, raising=True
    )

    await maintenance.run_check(ctx)

    db.refresh(repository)
    assert repository.last_check is not None
```

- [x] **Step 6: Run them and watch them fail**

Run: `python -m pytest tests/unit/test_operations_maintenance_executors.py -q -p no:cacheprovider`
Expected: FAIL, `No module named 'app.services.operations.executors.maintenance'`

- [x] **Step 7: Write the executor module with check in it**

```python
# app/services/operations/executors/maintenance.py
"""Maintenance executors (spec 6.3 and section 13 phase 5).

Each executor is a thin shell. The work still lives in the service the kind
has always used, reached through `BorgRouter`, which picks the Borg 1, Borg 2,
or managed-agent path. The service drives the operation row through
`MaintenanceJobFacade`, so the shell's whole job is to load the repository,
run the router call, watch for cancellation, and turn the row's final status
into an `Outcome` for the runner.
"""

import asyncio
from typing import Awaitable, Callable, Optional

import structlog

from app.core.borg_router import BorgRouter
from app.database.models import Operation, Repository, utc_now
from app.services.operations import executors
from app.services.operations.job_facade import MaintenanceJobFacade
from app.services.operations.runner import Outcome

logger = structlog.get_logger()

# Kinds that stamp a "last done" column on the repository when they succeed,
# the way the legacy services did from inside their own bodies.
_LAST_DONE_COLUMN = {"check": "last_check", "compact": "last_compact"}

_CANCEL_POLL_SECONDS = 1.0


def _load_repository(ctx) -> Optional[Repository]:
    if ctx.repository_id is None:
        return None
    return ctx.db.get(Repository, ctx.repository_id)


async def cancel_watcher(
    ctx, canceller: Optional[Callable[[int], Awaitable[bool]]]
) -> None:
    """Turn the runner's cooperative cancel flag (spec 7.7) into the process
    kill the legacy cancel routes performed. Returns when the flag is seen or
    the task is cancelled."""
    if canceller is None:
        return
    while True:
        if ctx.cancelled():
            try:
                await canceller(ctx.operation_id)
            except Exception as exc:
                logger.warning(
                    "Maintenance cancel failed",
                    operation_id=ctx.operation_id,
                    error=str(exc),
                )
            return
        await asyncio.sleep(_CANCEL_POLL_SECONDS)


async def _run(
    ctx,
    call: Callable[[BorgRouter, int], Awaitable[None]],
    *,
    canceller: Optional[Callable[[int], Awaitable[bool]]] = None,
) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    watcher = asyncio.create_task(cancel_watcher(ctx, canceller))
    try:
        await call(BorgRouter(repository), ctx.operation_id)
    finally:
        watcher.cancel()

    # The service wrote the outcome onto the row through the facade. Read it
    # back rather than assuming success, so a service that failed quietly is
    # reported as failed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = MaintenanceJobFacade(ctx.db, operation)
    status = operation.status
    if status not in ("completed", "completed_with_warnings", "failed", "cancelled"):
        # Still "running" means the service returned without recording a
        # verdict, which is a bug in the service, not a success.
        return Outcome(
            status="failed",
            error_message=job.error_message or "service returned no result",
        )
    if status in ("completed", "completed_with_warnings"):
        column = _LAST_DONE_COLUMN.get(ctx.kind)
        if column is not None:
            repository = ctx.db.get(Repository, ctx.repository_id)
            if repository is not None:
                setattr(repository, column, utc_now())
                ctx.db.commit()
        return Outcome(status=status, result={"logs": bool(job.log_file_path)})
    if status == "cancelled":
        # `Outcome` has no cancelled status (spec 6.3 gives that to the row,
        # not to the executor's verdict), and the runner rewrites the row to
        # cancelled itself when it sees its own flag set. Report the failure
        # shape and let the runner have the last word.
        return Outcome(
            status="failed", error_message=job.error_message or "cancelled"
        )
    return Outcome(status="failed", error_message=job.error_message)


async def run_check(ctx) -> Outcome:
    from app.services.check_service import check_service

    return await _run(
        ctx,
        lambda router, job_id: router.check(job_id),
        canceller=getattr(check_service, "cancel_check", None),
    )


executors.register("check", run_check)
```

- [x] **Step 8: Load the module in the registry**

```python
# app/services/operations/executors/__init__.py
def load_default_executors() -> None:
    """Import executor modules for their registration side effect."""
    from app.services.operations.executors import (  # noqa: F401
        history,
        index,
        maintenance,
    )
```

- [x] **Step 9: Run the executor tests**

Run: `python -m pytest tests/unit/test_operations_maintenance_executors.py -q -p no:cacheprovider`
Expected: the check tests PASS. The "every kind has an executor" test still
fails on prune, compact, delete_archive, and restore_check; mark it
`@pytest.mark.xfail(reason="tasks 3 to 6")` and remove the marker in Task 6.

- [x] **Step 10: Point the check services at the facade**

`app/services/check_service.py:59`, replace:

```python
            job = db.query(CheckJob).filter(CheckJob.id == job_id).first()
```

with:

```python
            job = resolve_maintenance_job(db, job_id, "check")
```

and add the import at the top of the file:

```python
from app.services.operations.job_facade import resolve_maintenance_job
```

`app/services/v2/check_service.py:58` takes the same change. Its conditional
claim at `:105` becomes:

```python
            def persist_start_state():
                nonlocal claimed
                claimed = claim_running(db, job_id, "check", started_at)
```

with `from app.services.operations.job_facade import claim_running` at the top.

Leave the `CheckJob` import in place in both files only if something else in
the file still uses it; if not, remove it so ruff stays clean.

- [x] **Step 11: Teach admission about running operations**

`break_lock`, wipe, and backup all ask `list_active_repository_work()` what is
running before they start. Once check lives in `operations`, that function
must see it or a break-lock could fire during a check. In
`app/services/job_admission.py`, inside `list_active_repository_work`, after
the existing per-model loop, add:

```python
    from app.database.models import Operation
    from app.services.operations.job_facade import MAINTENANCE_KINDS

    operation_by_kind = {
        "check": OPERATION_CHECK,
        "prune": OPERATION_PRUNE,
        "compact": OPERATION_COMPACT,
        "delete_archive": OPERATION_DELETE_ARCHIVE,
        "restore_check": OPERATION_RESTORE_CHECK,
    }
    for op in (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind.in_(MAINTENANCE_KINDS),
            Operation.status.in_(("queued", "running")),
        )
        .all()
    ):
        work = _active_work(
            repository,
            operation_by_kind[op.kind],
            Operation.__tablename__,
            op,
        )
        if not _is_ignored(work, ignore):
            active.append(work)
```

Read `list_active_repository_work` first: it builds a list of
`ActiveRepositoryWork` through `_active_work(repository, operation, table,
job)` and filters with `_is_ignored`. Use the same list variable it already
appends to, and put this block after the existing per-model loop and before
the wipe query, so ordering stays stable for the error payload that names the
first conflict.

- [x] **Step 12: Rewrite the check start route**

In `app/api/repositories.py`, the agent branch and the
`start_background_maintenance_job` call both go. `BorgRouter.check()` already
routes to the agent, so the executor covers that path. The whole body after
the flag validation becomes:

```python
        check_job = start_maintenance(
            db,
            repository,
            "check",
            trigger="manual",
            params={
                "max_duration": max_duration,
                "extra_flags": check_extra_flags,
                "scheduled_check": False,
            },
            user_id=current_user.id,
            duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
        )

        logger.info(
            "Check operation queued",
            operation_id=check_job.id,
            repository_id=repo_id,
            user=current_user.username,
        )

        return {
            "job_id": check_job.id,
            "status": "pending",
            "message": "backend.success.repo.checkJobStarted",
        }
```

Import `start_maintenance` from `app.services.operations.maintenance_start`.
Delete `_dispatch_router_check` and its import of `CheckJob` if nothing else
uses them.

- [x] **Step 13: Rewrite the two check read routes**

The serializers in `app/api/maintenance_jobs.py` read through `getattr`, so
they accept the facade unchanged. Only the lookup changes.
`GET /check-jobs/{job_id}`:

```python
        job, _ = get_maintenance_job_with_repository(
            db,
            current_user,
            "check",
            job_id,
            not_found_key="backend.errors.repo.checkJobNotFound",
        )
```

Add that helper next to `get_job_with_repository` in
`app/api/maintenance_jobs.py`:

```python
def get_maintenance_job_with_repository(
    db: Session,
    current_user: User,
    kind: str,
    job_id: int,
    *,
    not_found_key: str,
    required_role: str = "viewer",
):
    """Resolve a maintenance job id to an operation, or to the legacy row it
    belonged to before phase 5. Deleted in phase 9."""
    from app.services.operations.job_facade import resolve_maintenance_job

    job = resolve_maintenance_job(db, job_id, kind)
    if job is None:
        raise HTTPException(status_code=404, detail={"key": not_found_key})
    repository = db.query(Repository).filter(Repository.id == job.repository_id).first()
    if not repository:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.repo.repositoryNotFound"}
        )
    check_repo_access(db, current_user, repository, required_role)
    return job, repository
```

`GET /{repo_id}/check-jobs` lists both worlds, newest first, and the list
helper goes in the same module:

```python
def get_repository_maintenance_jobs(
    db: Session,
    current_user: User,
    repo_id: int,
    kind: str,
    *,
    limit: int = 10,
    required_role: str = "viewer",
) -> list[Any]:
    """Operations for this kind, plus the legacy rows written before phase 5,
    newest first. Deleted in phase 9."""
    from app.database.models import Operation
    from app.services.operations.job_facade import (
        LEGACY_MODELS,
        MaintenanceJobFacade,
    )

    repository = get_repository_with_access_or_empty(
        db, current_user, repo_id, required_role=required_role
    )
    if not repository:
        return []

    operations = (
        db.query(Operation)
        .filter(Operation.repository_id == repo_id, Operation.kind == kind)
        .order_by(Operation.id.desc())
        .limit(limit)
        .all()
    )
    rows: list[Any] = [MaintenanceJobFacade(db, op) for op in operations]

    model = LEGACY_MODELS[kind]
    legacy = (
        db.query(model)
        .filter(model.repository_id == repo_id)
        .order_by(model.id.desc())
        .limit(limit)
        .all()
    )
    rows.extend(legacy)
    rows.sort(
        key=lambda row: (row.created_at or row.started_at or datetime.min),
        reverse=True,
    )
    return rows[:limit]
```

The `scheduled_only` filter and the `scheduled_check` field in the response
keep working, because the facade serves `scheduled_check` out of `params`.

- [x] **Step 14: Move the check scheduler onto the queue**

In `app/services/check_scheduler.py`, replace the
`start_background_maintenance_job` call with:

```python
            check_job = start_maintenance(
                db,
                repo,
                "check",
                trigger="schedule",
                params={
                    "max_duration": (
                        repo.check_max_duration
                        if repo.check_max_duration is not None
                        else 3600
                    ),
                    "extra_flags": repo.check_extra_flags,
                    "scheduled_check": True,
                },
                user_id=None,
                duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
            )
```

The log line reading `check_job.max_duration` becomes
`check_job.params.get("max_duration")`. Delete `_dispatch_router_check` and
the `partial` import if unused. The scheduler's own slot accounting
(`available_slots`) stays: it decides how many to enqueue, and
`max_concurrent_scheduled_checks` in `lanes.global_slot_available` decides how
many run at once. The queries at `:60`, `:77`, and `:105` that count pending
and running scheduled checks must now count operations with
`params["scheduled_check"] is True`; on SQLite use
`Operation.params["scheduled_check"].as_boolean()` or filter in Python after
loading the repository's active check operations, whichever the surrounding
code makes cleaner.

- [x] **Step 15: Flip check to operation-only in Activity**

In `app/api/activity.py`, both `job_models` maps drop the `"check": CheckJob`
entry, and `_is_operation_only_kind` gains the legacy fallback so historical
rows keep serving logs:

```python
def _is_operation_only_kind(job_type: str, job_models: dict) -> bool:
    """True for kinds that live only in the operations table in this phase.
    Kinds that still have a legacy table keep resolving that table here; the
    /api/operations routes serve their operations rows by id."""
    return (
        job_type in op_vocab.KINDS
        and job_type not in job_models
        and job_type not in RCLONE_ACTIVITY_OPERATIONS
    )
```

stays as it is, because dropping the map entry is what flips check to the
operations branch. What must change is that the branch no longer 404s a
historical row. `_get_operation_or_404` gains a non-raising sibling next to
it:

```python
def _get_migrated_job(db: Session, job_type: str, job_id: int):
    """A migrated kind's row: the operation if there is one, else the
    pre-phase-5 legacy row. Returns None when neither exists."""
    from app.services.operations.job_facade import LEGACY_MODELS

    op = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == job_type)
        .first()
    )
    if op is not None:
        return op
    model = LEGACY_MODELS.get(job_type)
    if model is None:
        return None
    return db.query(model).filter(model.id == job_id).first()
```

Both call sites become:

```python
    if _is_operation_only_kind(job_type, job_models):
        row = _get_migrated_job(db, job_type, job_id)
        if row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "key": "backend.errors.activity.jobNotFound",
                    "params": {"jobType": job_type},
                },
            )
        if current_user is not None and row.repository_id is not None:
            repo = db.get(Repository, row.repository_id)
            if repo is not None:
                check_repo_access(db, current_user, repo, "viewer")
        policy = get_log_save_policy(db)
        text = getattr(row, "logs", None)
        if not job_has_logs_by_policy(
            row, policy, output_text=[text, row.error_message],
            file_path=row.log_file_path,
        ):
            raise _no_logs_available_exception()
        return _paginate_log_text(_read_operation_log(row), offset, limit)
```

`_read_operation_log` reads `log_file_path`, which both row shapes carry, so
it needs no change. The delete-by-id route at `:1695` takes the same
treatment.

- [x] **Step 16: Point the agent callbacks at the operation**

In `app/api/agents.py`, `_get_repository_operation_job` resolves through the
facade:

```python
def _get_repository_operation_job(agent_job: AgentJob, db: Session) -> Any | None:
    payload = agent_job.payload or {}
    operation = payload.get("operation") if isinstance(payload, dict) else None
    maintenance_job = (
        operation.get("maintenance_job") if isinstance(operation, dict) else None
    )
    if not isinstance(maintenance_job, dict):
        return None

    kind = str(maintenance_job.get("kind") or "")
    job_id = maintenance_job.get("id")
    if kind not in REPOSITORY_OPERATION_JOB_KINDS or not job_id:
        return None
    return resolve_maintenance_job(db, int(job_id), kind)
```

`REPOSITORY_OPERATION_JOB_MODELS` becomes
`REPOSITORY_OPERATION_JOB_KINDS = ("check", "compact", "prune", "delete_archive")`.
In `_finish_linked_repository_operation_job` the two `isinstance` tests become
kind tests, since the object may now be a facade:

```python
    kind = getattr(operation_job, "kind", None) or _legacy_kind(operation_job)
    if repository and status_value in ("completed", "completed_with_warnings"):
        if kind == "check":
            repository.last_check = completed_at
        elif kind == "compact":
            repository.last_compact = completed_at
        repository.updated_at = _now_utc()
```

Do the same for the `PruneJob` and `DeleteArchiveJob` branches further down.
`_legacy_kind` is a two-line helper mapping a legacy model instance back to
its kind, for rows that predate the phase.

- [x] **Step 17: Stop the agent admission ignoring a table that no longer gets rows**

In `app/services/repository_executor.py`, `maintenance_table_by_kind` maps
`"check"` to `"check_jobs"` so admission can ignore the row the caller just
made. The caller now makes an operation, so the map entry becomes
`"operations"` for migrated kinds. Change the dict to:

```python
    maintenance_table_by_kind = {
        "check": "operations",
        "restore_check": "restore_check_jobs",
        "compact": "compact_jobs",
        "prune": "prune_jobs",
        "delete_archive": "delete_archive_jobs",
    }
```

and move each remaining kind to `"operations"` as its task lands, so by the
end of Task 6 every value reads `"operations"` and the dict collapses to a
constant.

- [x] **Step 18: Drop check from the startup orphan sweep**

Spec 7.6 gives recovery to `OperationRunner.recover_on_startup`, which
`app/main.py` already calls. In `app/utils/process_utils.py`, delete the
`running_check_jobs` query and the loop that consumes it. Leave the other four
until their tasks.

- [x] **Step 19: Write the route-level tests**

```python
# tests/unit/test_api_maintenance_migration.py
"""Phase 5: the five maintenance kinds answer from `operations` and write no
legacy rows."""

from app.database.models import CheckJob, Operation


def test_starting_a_check_creates_an_operation_and_no_check_job(
    test_client, test_db, admin_headers, repository
):
    response = test_client.post(
        f"/api/repositories/{repository.id}/check",
        json={"max_duration": 3600},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"

    op = test_db.get(Operation, body["job_id"])
    assert op is not None
    assert op.kind == "check"
    assert op.status == "queued"
    assert op.trigger == "manual"
    assert test_db.query(CheckJob).count() == 0


def test_a_second_check_is_rejected_with_409(
    test_client, test_db, admin_headers, repository
):
    test_client.post(
        f"/api/repositories/{repository.id}/check",
        json={},
        headers=admin_headers,
    )
    second = test_client.post(
        f"/api/repositories/{repository.id}/check",
        json={},
        headers=admin_headers,
    )

    assert second.status_code == 409
    assert second.json()["detail"]["key"] == "backend.errors.repo.checkAlreadyRunning"


def test_check_job_status_route_serves_the_operation(
    test_client, test_db, admin_headers, repository
):
    started = test_client.post(
        f"/api/repositories/{repository.id}/check",
        json={},
        headers=admin_headers,
    ).json()

    response = test_client.get(
        f"/api/repositories/check-jobs/{started['job_id']}", headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == started["job_id"]
    assert body["status"] == "pending"
    assert "progress" in body


def test_check_job_status_route_still_serves_a_legacy_row(
    test_client, test_db, admin_headers, repository
):
    legacy = CheckJob(repository_id=repository.id, status="completed", progress=100)
    test_db.add(legacy)
    test_db.commit()

    response = test_client.get(
        f"/api/repositories/check-jobs/{legacy.id}", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_repository_check_jobs_lists_both_worlds(
    test_client, test_db, admin_headers, repository
):
    legacy = CheckJob(repository_id=repository.id, status="completed")
    test_db.add(legacy)
    test_db.commit()
    test_client.post(
        f"/api/repositories/{repository.id}/check", json={}, headers=admin_headers
    )

    response = test_client.get(
        f"/api/repositories/{repository.id}/check-jobs", headers=admin_headers
    )

    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 2


def test_a_check_queues_behind_a_running_backup_instead_of_409(
    test_client, test_db, admin_headers, repository
):
    """The point of the phase: work waits for the lane rather than being
    refused (spec 7.2)."""
    from app.database.models import BackupJob

    test_db.add(
        BackupJob(repository_id=repository.id, repository=repository.path, status="running")
    )
    test_db.commit()

    response = test_client.post(
        f"/api/repositories/{repository.id}/check", json={}, headers=admin_headers
    )

    assert response.status_code == 200
    assert test_db.get(Operation, response.json()["job_id"]).status == "queued"
```

Use the fixture names the existing suite uses; read
`tests/unit/test_api_operations.py` for the `test_client`, `test_db`,
`admin_headers`, and repository fixture shapes before writing these, and match
them rather than inventing new ones.

- [x] **Step 20: Run the whole backend suite**

Run: `python -m pytest tests/unit -q -p no:cacheprovider`
Expected: every test passes except the three known `test_source_discovery.py`
failures. Any failure in `test_api_maintenance_jobs.py`,
`test_maintenance_state.py`, or `test_ssh_key_in_maintenance_services.py` is
yours: those suites assert the old dispatch, so update their expectations to
the operations table in the same task.

Run: `ruff check app tests`
Expected: no findings.

---


**Deviations recorded during Task 2 (2026-09-06):**

1. **Spec 7.6's lock break was missing from the runner.** The per-table sweep
   in `cleanup_orphaned_jobs` did more than fail an orphaned check: for a local
   repository it also called `break_repository_lock`, which spec 7.6 requires
   and `OperationRunner.recover_on_startup` did not do. Phase 5 is the first
   phase to put an exclusive Borg kind in `operations`, so the lock break moved
   into the runner as `_recover_repository_lock`, gated on `is_exclusive(kind)`
   and skipped for remote repositories. Without this, a container restart
   during a check would have left the repository locked.
2. **The legacy startup sweep stays, against the plan's Task 2 step 18.**
   Removing check from `cleanup_orphaned_jobs` strands any `check_jobs` row
   left running by a pre-upgrade process: nothing would ever fail it, and its
   parent backup would sit in `running_check` forever. The sweep is kept and
   relabelled as a legacy-only path (it is empty on any install that has
   restarted since the upgrade), while `OperationRunner.recover_on_startup`
   owns operations. Task 8 step 2 is amended to match. Removing the query also
   broke six `test_utils.py` tests that mock `db.query` positionally, which is
   how the stranding was noticed.
3. **`_has_running_check_child` had to learn about operations.** It guards
   `_mark_stale_backup_maintenance_failed` from failing a backup whose check
   child is genuinely still running. Left alone it would have seen no check
   rows and wrongly failed the backup.
4. **The repository list route counted running work from the legacy tables.**
   `GET /api/repositories` reports `has_check`, `has_compact`, and `has_prune`
   from one block; it now reads `operations` first with a legacy fallback. All
   three changed at once because they share the block, even though compact and
   prune migrate in tasks 3 and 4.
5. **Scheduler tests rewritten, not just repatched.** They mocked the
   dispatcher and asserted on its kwargs, which no longer exists. They now
   assert on the enqueued operation. The SQLite lock test became a real
   end-to-end run through `OperationRunner`, which is stronger: it proves a
   transient lock on the dispatch commit leaves the row queued for the next
   tick rather than losing the work.
6. **Route tests must not assert `queued`.** The test app runs the runner, so
   an unblocked operation is picked up inside the request. Tests assert
   `status in ("queued", "running")` unless the lane is deliberately blocked.
7. **Tests that mock `db.query` per model need an `Operation` branch.**
   `resolve_maintenance_job` queries `operations` first; a `MagicMock` that
   answers every model returns a truthy row and the service drives a mock.
   `test_ssh_key_in_maintenance_services.py` needed `Operation` mapped to
   `None`. Tasks 3 to 6 will hit the same thing for their kinds.
8. **Writing a log through the facade must not touch the shared data dir in
   tests.** The facade resolves `operation_log_path()` from
   `settings.data_dir`; a test that writes there leaks `operation_<id>.log`
   into other suites. Monkeypatch `app.config.settings.data_dir` in any test
   that sets `job.logs`.

### Task 3: Prune on the runner, including the synchronous dry run

Prune has one shape check does not: a dry run answers inside the request with
the output of `borg prune --dry-run`, because the UI shows the user what would
be deleted before they commit. A queued operation cannot answer a request, so
the dry run keeps running inline. It still gets an operation row, created
already `running` and finished by the route, the way `record_import_connect`
records work the runner never dispatches (spec 7.1 dispatches only `queued`
rows, so an inline row is never picked up twice).

**Files:**
- Modify: `app/services/operations/executors/maintenance.py`
- Modify: `app/services/prune_service.py:76`, `app/services/v2/prune_service.py:101,264`
- Modify: `app/api/repositories.py` prune start route, both prune read routes,
  `_dispatch_router_prune`
- Modify: `app/services/repository_executor.py` map entry for `prune`
- Modify: `app/utils/process_utils.py` prune branch
- Modify: `app/api/activity.py` both `job_models` maps
- Test: `tests/unit/test_operations_maintenance_executors.py`,
  `tests/unit/test_api_maintenance_migration.py`

**Interfaces:**
- Consumes: `start_maintenance()`, `_run()`, `MaintenanceJobFacade`.
- Produces: `run_prune(ctx) -> Outcome` registered as executor `prune`;
  `start_inline_maintenance(db, repository, kind, params, user_id) -> Operation`
  in `maintenance_start.py`.

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_maintenance_executors.py (append)
@pytest.mark.asyncio
async def test_prune_passes_the_retention_policy_from_params(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(
        db,
        repository,
        kind="prune",
        params={
            "keep_hourly": 0,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 6,
            "keep_quarterly": 0,
            "keep_yearly": 1,
            "keep_within": "2d",
        },
    )
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_prune(self, job_id, *args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.prune", fake_prune, raising=True
    )

    outcome = await maintenance.run_prune(ctx)

    assert outcome.status == "completed"
    assert seen["args"] == (0, 7, 4, 6, 0, 1, False)
    assert seen["kwargs"]["keep_within"] == "2d"


@pytest.mark.asyncio
async def test_prune_omits_keep_within_when_it_is_not_set(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="prune", params={"keep_daily": 7})
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_prune(self, job_id, *args, **kwargs):
        seen["kwargs"] = kwargs
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.prune", fake_prune, raising=True
    )

    await maintenance.run_prune(ctx)

    assert "keep_within" not in seen["kwargs"]
```

- [x] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/unit/test_operations_maintenance_executors.py -q -p no:cacheprovider -k prune`
Expected: FAIL, `module 'app.services.operations.executors.maintenance' has no attribute 'run_prune'`

- [x] **Step 3: Add the executor**

```python
# app/services/operations/executors/maintenance.py (append before the register calls)
_PRUNE_DEFAULTS = {
    "keep_hourly": 0,
    "keep_daily": 7,
    "keep_weekly": 4,
    "keep_monthly": 6,
    "keep_quarterly": 0,
    "keep_yearly": 1,
}


async def run_prune(ctx) -> Outcome:
    from app.services.prune_service import prune_service

    params = ctx.params
    retention = tuple(
        params.get(name, default) for name, default in _PRUNE_DEFAULTS.items()
    )
    keep_within = params.get("keep_within")
    kwargs = {"keep_within": keep_within} if keep_within is not None else {}

    async def call(router, job_id):
        await router.prune(job_id, *retention, False, **kwargs)

    return await _run(
        ctx, call, canceller=getattr(prune_service, "cancel_prune", None)
    )


executors.register("prune", run_prune)
```

The literal `False` is `dry_run`: a queued prune is never a dry run, because
a dry run answers inside the request (Step 6).

- [x] **Step 4: Point the prune services at the facade**

`app/services/prune_service.py:76` becomes
`job = resolve_maintenance_job(db, job_id, "prune")` with the import added.
`app/services/v2/prune_service.py:101` takes the same change, `:264` too, and
its claim update becomes `claim_running(db, job_id, "prune", started_at)`.

- [x] **Step 5: Add the inline starter**

```python
# app/services/operations/maintenance_start.py (append)
def start_inline_maintenance(
    db: Session,
    repository: Repository,
    kind: str,
    *,
    params: dict[str, Any],
    user_id: Optional[int],
) -> Operation:
    """An operation the caller runs itself, right now, instead of leaving to
    the runner. Created `running` so the runner's queued-only sweep (spec 7.1)
    never picks it up a second time. The caller is responsible for the
    terminal status."""
    from app.database.models import utc_now

    operation = enqueue(
        db,
        kind,
        repository_id=repository.id,
        trigger="manual",
        params={key: value for key, value in params.items() if value is not None},
        triggered_by_user_id=user_id,
        commit=False,
    )
    operation.status = "running"
    operation.started_at = utc_now()
    db.commit()
    db.refresh(operation)
    return operation
```

- [x] **Step 6: Rewrite the prune start route**

Delete the agent branch and the `ensure_repository_admission` call. The whole
body after the retention values are read becomes:

```python
        if not dry_run:
            prune_job = start_maintenance(
                db,
                repository,
                "prune",
                trigger="manual",
                params={
                    "keep_hourly": keep_hourly,
                    "keep_daily": keep_daily,
                    "keep_weekly": keep_weekly,
                    "keep_monthly": keep_monthly,
                    "keep_quarterly": keep_quarterly,
                    "keep_yearly": keep_yearly,
                    "keep_within": keep_within,
                    "scheduled_prune": False,
                },
                user_id=current_user.id,
                duplicate_error_key="backend.errors.repo.pruneAlreadyRunning",
            )
            logger.info(
                "Prune operation queued",
                operation_id=prune_job.id,
                repository_id=repo_id,
                user=current_user.username,
            )
            return {
                "job_id": prune_job.id,
                "status": "pending",
                "message": "backend.success.repo.pruneJobStarted",
            }

        prune_job = start_inline_maintenance(
            db,
            repository,
            "prune",
            params={
                "keep_hourly": keep_hourly,
                "keep_daily": keep_daily,
                "keep_weekly": keep_weekly,
                "keep_monthly": keep_monthly,
                "keep_quarterly": keep_quarterly,
                "keep_yearly": keep_yearly,
                "keep_within": keep_within,
                "dry_run": True,
                "scheduled_prune": False,
            },
            user_id=current_user.id,
        )
```

The `await BorgRouter(repository).prune(...)` call below it stays exactly as
it is, including the agent path inside the router, which now reports onto the
operation through the facade. Replace `db.refresh(prune_job)` with
`db.refresh(prune_job)` on the operation row (it is a mapped instance, so
refresh still works) and wrap it for reading:

```python
        db.refresh(prune_job)
        prune_view = MaintenanceJobFacade(db, prune_job)
        stdout_output = read_job_logs(
            prune_view, fallback_to_logs=True, log_save_policy="all_jobs"
        )
```

and read `prune_view.status` and `prune_view.error_message` in the response
body, so the dry-run payload keeps the legacy status words.

- [x] **Step 7: Rewrite the prune read routes**

`GET /prune-jobs/{job_id}` and `GET /{repo_id}/prune-jobs` switch to
`get_maintenance_job_with_repository(db, current_user, "prune", job_id, ...)`
and `get_repository_maintenance_jobs(db, current_user, repo_id, "prune", limit=limit)`
from Task 2.

- [x] **Step 8: Finish the sweep for prune**

Drop `"prune": PruneJob` from both `job_models` maps in `app/api/activity.py`;
change `maintenance_table_by_kind["prune"]` to `"operations"`; delete the
prune branch from `cleanup_orphaned_jobs`; delete `_dispatch_router_prune`.

- [x] **Step 9: Add the route tests**

```python
# tests/unit/test_api_maintenance_migration.py (append)
def test_starting_a_prune_creates_an_operation_with_the_policy(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import PruneJob

    response = test_client.post(
        f"/api/repositories/{repository.id}/prune",
        json={"keep_daily": 5, "keep_within": "2d"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    op = test_db.get(Operation, response.json()["job_id"])
    assert op.kind == "prune"
    assert op.params["keep_daily"] == 5
    assert op.params["keep_within"] == "2d"
    assert test_db.query(PruneJob).count() == 0


def test_a_dry_run_prune_answers_inline_and_is_never_queued(
    test_client, test_db, admin_headers, repository, monkeypatch
):
    async def fake_prune(self, job_id, *args, **kwargs):
        from app.services.operations.job_facade import MaintenanceJobFacade

        op = test_db.get(Operation, job_id)
        MaintenanceJobFacade(test_db, op).status = "completed"
        test_db.commit()

    monkeypatch.setattr("app.core.borg_router.BorgRouter.prune", fake_prune)

    response = test_client.post(
        f"/api/repositories/{repository.id}/prune",
        json={"dry_run": True},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    op = test_db.get(Operation, body["job_id"])
    assert op.status == "completed"
```

- [x] **Step 10: Run the suite**

Run: `python -m pytest tests/unit -q -p no:cacheprovider` then
`ruff check app tests`.
Expected: green apart from the three known `test_source_discovery.py` failures.
`tests/unit/test_prune_service.py` and `tests/unit/test_v2_prune_service.py`
build `PruneJob` rows directly; they keep passing through the legacy fallback
in `resolve_maintenance_job`, and if one asserts on dispatch it is yours to
update.

---

### Task 4: Compact on the runner

Compact is the simplest of the five: no inputs beyond a scheduled flag, no
dry run, no cancellation subtleties beyond the existing `cancel_compact`.

**Files:**
- Modify: `app/services/operations/executors/maintenance.py`
- Modify: `app/services/compact_service.py:88`, `app/services/v2/compact_service.py:94,142`
- Modify: `app/api/repositories.py` compact start route, both compact read
  routes, `_dispatch_router_compact`
- Modify: `app/services/repository_executor.py`, `app/api/activity.py`,
  `app/utils/process_utils.py`
- Test: `tests/unit/test_operations_maintenance_executors.py`,
  `tests/unit/test_api_maintenance_migration.py`

**Interfaces:**
- Produces: `run_compact(ctx) -> Outcome` registered as executor `compact`.

- [x] **Step 1: Write the failing test**

```python
# tests/unit/test_operations_maintenance_executors.py (append)
@pytest.mark.asyncio
async def test_compact_stamps_last_compact_on_success(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="compact")
    ctx = FakeContext(db, op)

    async def fake_compact(self, job_id):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(ctx)

    assert outcome.status == "completed"
    db.refresh(repository)
    assert repository.last_compact is not None
```

- [x] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/unit/test_operations_maintenance_executors.py -q -p no:cacheprovider -k compact`
Expected: FAIL, no attribute `run_compact`.

- [x] **Step 3: Add the executor**

```python
# app/services/operations/executors/maintenance.py (append)
async def run_compact(ctx) -> Outcome:
    from app.services.compact_service import compact_service

    return await _run(
        ctx,
        lambda router, job_id: router.compact(job_id),
        canceller=getattr(compact_service, "cancel_compact", None),
    )


executors.register("compact", run_compact)
```

- [x] **Step 4: Point the compact services at the facade**

`app/services/compact_service.py:88` becomes
`job = resolve_maintenance_job(db, job_id, "compact")`.
`app/services/v2/compact_service.py:94` the same, and its claim update at
`:142` becomes `claim_running(db, job_id, "compact", started_at)`.

- [x] **Step 5: Rewrite the compact start route**

Delete the agent branch and the `start_background_maintenance_job` call:

```python
        compact_job = start_maintenance(
            db,
            repository,
            "compact",
            trigger="manual",
            params={"scheduled_compact": False},
            user_id=current_user.id,
            duplicate_error_key="backend.errors.repo.compactAlreadyRunning",
        )

        logger.info(
            "Compact operation queued",
            operation_id=compact_job.id,
            repository_id=repo_id,
            user=current_user.username,
        )

        return {
            "job_id": compact_job.id,
            "status": "pending",
            "message": "backend.success.repo.compactJobStarted",
        }
```

- [x] **Step 6: Rewrite the compact read routes**

`GET /compact-jobs/{job_id}` and `GET /{repo_id}/compact-jobs` use the two
helpers from Task 2 with kind `"compact"`.

- [x] **Step 7: Finish the sweep for compact**

Drop `"compact": CompactJob` from both `job_models` maps; set
`maintenance_table_by_kind["compact"] = "operations"`; delete the compact
branch from `cleanup_orphaned_jobs`; delete `_dispatch_router_compact`.

- [x] **Step 8: Add the route test**

```python
# tests/unit/test_api_maintenance_migration.py (append)
def test_starting_a_compact_creates_an_operation(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import CompactJob

    response = test_client.post(
        f"/api/repositories/{repository.id}/compact", headers=admin_headers
    )

    assert response.status_code == 200
    op = test_db.get(Operation, response.json()["job_id"])
    assert op.kind == "compact"
    assert op.status == "queued"
    assert test_db.query(CompactJob).count() == 0
```

- [x] **Step 9: Run the suite**

Run: `python -m pytest tests/unit -q -p no:cacheprovider` then
`ruff check app tests`.

---

### Task 5: Delete archive on the runner

Delete archive is the one kind whose routes live in `app/api/archives.py`, and
the only one with a cancel route of its own. Its duplicate rule is narrower
than the others: today it rejects a second delete of *the same archive*, not a
second delete on the repository, so the enqueue helper needs the archive name
in the check.

**Files:**
- Modify: `app/services/operations/executors/maintenance.py`
- Modify: `app/services/operations/maintenance_start.py`
- Modify: `app/services/delete_archive_service.py:59,324`,
  `app/services/v2/delete_archive_service.py:38,170`
- Modify: `app/api/archives.py` delete route, status route, cancel route
- Modify: `app/services/repository_executor.py`, `app/api/activity.py`,
  `app/utils/process_utils.py`
- Test: `tests/unit/test_operations_maintenance_executors.py`,
  `tests/unit/test_api_maintenance_migration.py`

**Interfaces:**
- Produces: `run_delete_archive(ctx) -> Outcome` registered as executor
  `delete_archive`; `active_delete_for_archive(db, repository_id, archive_name)`
  in `maintenance_start.py`.

- [x] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_maintenance_executors.py (append)
@pytest.mark.asyncio
async def test_delete_archive_passes_the_archive_name(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(
        db,
        repository,
        kind="delete_archive",
        params={"archive_name": "aid:deadbeef"},
    )
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_delete(self, job_id, archive_name):
        seen["archive"] = archive_name
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.delete_archive", fake_delete, raising=True
    )

    outcome = await maintenance.run_delete_archive(ctx)

    assert outcome.status == "completed"
    assert seen["archive"] == "aid:deadbeef"


@pytest.mark.asyncio
async def test_delete_archive_fails_without_an_archive_name(db, repository):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="delete_archive", params={})
    ctx = FakeContext(db, op)

    outcome = await maintenance.run_delete_archive(ctx)

    assert outcome.status == "failed"
```

- [x] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/unit/test_operations_maintenance_executors.py -q -p no:cacheprovider -k delete_archive`
Expected: FAIL, no attribute `run_delete_archive`.

- [x] **Step 3: Add the executor**

```python
# app/services/operations/executors/maintenance.py (append)
async def run_delete_archive(ctx) -> Outcome:
    from app.services.delete_archive_service import delete_archive_service

    archive_name = ctx.params.get("archive_name")
    if not archive_name:
        return Outcome(
            status="failed", error_message="delete_archive requires an archive name"
        )

    async def cancel(operation_id):
        return await delete_archive_service.cancel_delete(operation_id, ctx.db)

    return await _run(
        ctx,
        lambda router, job_id: router.delete_archive(job_id, archive_name),
        canceller=cancel,
    )


executors.register("delete_archive", run_delete_archive)
```

- [x] **Step 4: Point the delete services at the facade**

Four lookups change to `resolve_maintenance_job(db, job_id, "delete_archive")`:
`app/services/delete_archive_service.py:59` and `:324` (the cancel path), and
`app/services/v2/delete_archive_service.py:38`, whose claim update at `:170`
becomes `claim_running(db, job_id, "delete_archive", started_at)`.

- [x] **Step 5: Add the per-archive duplicate check**

```python
# app/services/operations/maintenance_start.py (append)
def active_delete_for_archive(
    db: Session, repository_id: int, archive_name: str
) -> Optional[Operation]:
    """Deletes are rejected per archive, not per repository: two different
    archives may be removed at once, the same one may not."""
    candidates = (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "delete_archive",
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .all()
    )
    for candidate in candidates:
        if (candidate.params or {}).get("archive_name") == archive_name:
            return candidate
    return None
```

- [x] **Step 6: Rewrite the delete route**

In `app/api/archives.py`, the `DeleteArchiveJob` query, the row creation, and
the `asyncio.create_task(BorgRouter(...).delete_archive(...))` all go:

```python
        running_job = active_delete_for_archive(db, repo.id, archive_id)
        if running_job:
            raise HTTPException(
                status_code=409,
                detail={
                    "key": "backend.errors.archives.deleteAlreadyRunning",
                    "params": {"jobId": running_job.id},
                },
            )

        delete_job = enqueue(
            db,
            "delete_archive",
            repository_id=repo.id,
            trigger="manual",
            params={"archive_name": archive_id},
            triggered_by_user_id=current_user.id,
        )

        logger.info(
            "Delete archive operation queued",
            operation_id=delete_job.id,
            repository_id=repo.id,
            archive=archive_id,
            user=current_user.username,
        )

        return {
            "job_id": delete_job.id,
            "status": "pending",
            "message": "backend.success.archives.deletionStarted",
        }
```

Use `enqueue()` here rather than `start_maintenance()`, because the duplicate
rule is per archive and already checked above. The `SimpleNamespace` snapshot
disappears with the task: the executor loads the real repository row.

- [x] **Step 7: Rewrite the delete status and cancel routes**

`GET /delete-jobs/{job_id}` resolves through
`resolve_maintenance_job(db, job_id, "delete_archive")` and keeps its
hand-built payload, reading `job.archive_name`, `job.progress`,
`job.progress_message`, `job.logs`, and `job.log_file_path` off whatever comes
back. `POST /delete-jobs/{job_id}/cancel` asks the runner first, so a queued
operation is cancelled without touching a process:

```python
        job = resolve_maintenance_job(db, job_id, "delete_archive")
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.archives.deleteJobNotFound"},
            )
        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if repo:
            check_repo_access(db, current_user, repo, "operator")
        if isinstance(job, MaintenanceJobFacade):
            from app.services.operations.runner import operation_runner

            await operation_runner.request_cancel(job_id)
        else:
            await delete_archive_service.cancel_delete(job_id, db)
        return {"message": "backend.success.archives.deletionCancelled"}
```

`request_cancel` sets the flag the executor's `cancel_watcher` turns into the
process kill (spec 7.7), so the running case still terminates Borg.

- [x] **Step 8: Finish the sweep for delete archive**

`delete_archive` is not in the `job_models` maps in `app/api/activity.py`, so
there is nothing to remove there; confirm it resolves as operation-only by
reading `_is_operation_only_kind`. Set
`maintenance_table_by_kind["delete_archive"] = "operations"`. Delete the
delete-archive branch from `cleanup_orphaned_jobs` if it has one.

- [x] **Step 9: Add the route tests**

```python
# tests/unit/test_api_maintenance_migration.py (append)
def test_deleting_an_archive_queues_an_operation(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import DeleteArchiveJob

    response = test_client.delete(
        f"/api/archives/nightly-2026-09-01?repository={repository.path}",
        headers=admin_headers,
    )

    assert response.status_code == 200
    op = test_db.get(Operation, response.json()["job_id"])
    assert op.kind == "delete_archive"
    assert op.params["archive_name"] == "nightly-2026-09-01"
    assert test_db.query(DeleteArchiveJob).count() == 0


def test_a_second_delete_of_the_same_archive_is_rejected(
    test_client, test_db, admin_headers, repository
):
    test_client.delete(
        f"/api/archives/nightly-2026-09-01?repository={repository.path}",
        headers=admin_headers,
    )
    second = test_client.delete(
        f"/api/archives/nightly-2026-09-01?repository={repository.path}",
        headers=admin_headers,
    )

    assert second.status_code == 409


def test_a_delete_of_another_archive_is_allowed(
    test_client, test_db, admin_headers, repository
):
    test_client.delete(
        f"/api/archives/nightly-2026-09-01?repository={repository.path}",
        headers=admin_headers,
    )
    other = test_client.delete(
        f"/api/archives/nightly-2026-09-02?repository={repository.path}",
        headers=admin_headers,
    )

    assert other.status_code == 200
```

Check the real query-parameter shape of the delete route before writing these;
it takes `repository` as a query parameter and the archive id in the path.

- [x] **Step 10: Run the suite**

Run: `python -m pytest tests/unit -q -p no:cacheprovider` then
`ruff check app tests`. `tests/unit/test_delete_archive_service.py` exercises
the service against a legacy row and should still pass through the fallback.

---

### Task 6: Restore check on the runner

Restore check is category `restore`, not `maintenance` (spec 6.3), and it is
not exclusive: it only reads. It keeps its own scheduler. Its inputs are the
probe paths (a JSON string, exactly as the legacy column stored them, so the
service's `json.loads` is unchanged) and the full-archive flag.

**Files:**
- Modify: `app/services/operations/executors/maintenance.py`
- Modify: `app/services/restore_check_service.py:216,459`
- Modify: `app/api/repositories.py` restore-check start route and both
  restore-check read routes
- Modify: `app/services/restore_check_scheduler.py`
- Modify: `app/services/repository_executor.py`, `app/api/activity.py`,
  `app/utils/process_utils.py`
- Test: `tests/unit/test_operations_maintenance_executors.py`,
  `tests/unit/test_api_maintenance_migration.py`

**Interfaces:**
- Produces: `run_restore_check(ctx) -> Outcome` registered as executor
  `restore_check`.

- [x] **Step 1: Write the failing test**

```python
# tests/unit/test_operations_maintenance_executors.py (append)
@pytest.mark.asyncio
async def test_restore_check_runs_the_service_with_the_operation_id(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(
        db,
        repository,
        kind="restore_check",
        params={"probe_paths": "[]", "full_archive": True},
    )
    op.category = "restore"
    db.commit()
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_execute(job_id, repository_id):
        seen["job_id"] = job_id
        seen["repository_id"] = repository_id
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_check_service.restore_check_service.execute_restore_check",
        fake_execute,
        raising=True,
    )

    outcome = await maintenance.run_restore_check(ctx)

    assert outcome.status == "completed"
    assert seen["job_id"] == op.id
    assert seen["repository_id"] == repository.id
```

- [x] **Step 2: Run it and watch it fail**

Run: `python -m pytest tests/unit/test_operations_maintenance_executors.py -q -p no:cacheprovider -k restore_check`
Expected: FAIL, no attribute `run_restore_check`.

- [x] **Step 3: Add the executor**

Restore check does not go through `BorgRouter`; the route calls the service
directly today, so the executor does too. It reuses `_run`'s status read-back
by passing a call that ignores the router argument:

```python
# app/services/operations/executors/maintenance.py (append)
async def run_restore_check(ctx) -> Outcome:
    from app.services.restore_check_service import restore_check_service

    async def call(_router, job_id):
        await restore_check_service.execute_restore_check(job_id, ctx.repository_id)

    return await _run(ctx, call)


executors.register("restore_check", run_restore_check)
```

- [x] **Step 4: Point the restore check service at the facade**

`app/services/restore_check_service.py:216` becomes
`job = resolve_maintenance_job(db, job_id, "restore_check")`. The second
lookup at `:459` is inside the agent branch; give it the same treatment. The
`maintenance_job_kind="restore_check"` payload it builds at `:611` keeps
working once `repository_executor`'s map points at `"operations"`.

- [x] **Step 5: Rewrite the restore-check start route**

```python
        restore_check_job = start_maintenance(
            db,
            repository,
            "restore_check",
            trigger="manual",
            params={
                "probe_paths": json.dumps(probe_paths),
                "full_archive": full_archive,
                "scheduled_restore_check": False,
            },
            user_id=current_user.id,
            duplicate_error_key="backend.errors.repo.restoreCheckAlreadyRunning",
        )
```

The canary handling above it is untouched.

- [x] **Step 6: Rewrite the restore-check read routes**

`GET /restore-check-jobs/{job_id}` and `GET /{repo_id}/restore-check-jobs` use
the Task 2 helpers with kind `"restore_check"`. The list route's
`scheduled_only` filter reads `scheduled_restore_check` off the facade.

- [x] **Step 7: Move the restore-check scheduler onto the queue**

`app/services/restore_check_scheduler.py:76` currently calls
`start_background_maintenance_job` with a dispatcher lambda. Replace it with
`start_maintenance(..., trigger="schedule", params={..., "scheduled_restore_check": True}, user_id=None, duplicate_error_key="backend.errors.repo.restoreCheckAlreadyRunning")`
and delete the lambda.

- [x] **Step 8: Finish the sweep**

Drop `"restore_check": RestoreCheckJob` from both `job_models` maps; set
`maintenance_table_by_kind["restore_check"] = "operations"`, which makes every
value in that dict `"operations"`, so collapse it to a single constant string
and delete the dict; delete the restore-check branch from
`cleanup_orphaned_jobs`.

- [x] **Step 9: Remove the xfail from Task 2**

`test_every_maintenance_kind_has_an_executor` now passes for all five kinds.
Delete the `@pytest.mark.xfail` marker added in Task 2 Step 9.

- [x] **Step 10: Add the route test and run the suite**

```python
# tests/unit/test_api_maintenance_migration.py (append)
def test_starting_a_restore_check_creates_a_restore_category_operation(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import RestoreCheckJob

    response = test_client.post(
        f"/api/repositories/{repository.id}/restore-check",
        json={"full_archive": True},
        headers=admin_headers,
    )

    assert response.status_code == 200
    op = test_db.get(Operation, response.json()["job_id"])
    assert op.kind == "restore_check"
    assert op.category == "restore"
    assert test_db.query(RestoreCheckJob).count() == 0
```

Run: `python -m pytest tests/unit -q -p no:cacheprovider` then
`ruff check app tests`.
Expected: green apart from the three known `test_source_discovery.py` failures.
`tests/unit/test_restore_check_service.py` and `test_restore_check_canary.py`
build legacy rows and keep working through the fallback.

---

### Task 7: The v2 routes and maintenance after a backup

Two families of caller still make legacy rows: the Borg 2 routes in
`app/api/v2/backups.py`, and the two places that run prune, compact, or check
straight after a backup. The second is the behavioural drift section 13 warns
about, so read this task's reasoning before writing code.

**Why post-backup maintenance stays inline.** Today the caller awaits
`BorgRouter(repo).prune(...)` and then reads the job's status to decide
whether to write `prune_completed` or `prune_failed` onto
`BackupJob.maintenance_status`. If that prune became a queued operation, it
would never start: the backup job is still a legacy row in status
`running_prune`, and `lanes.legacy_running_exclusive()` counts exactly that
status as an exclusive holder, so the lane would stay closed until the backup
row finished, which is waiting for the prune. Phase 5 therefore keeps these
calls inline through `start_inline_maintenance()` from Task 3, which records a
real operation without handing it to the runner. Spec 6.3's mapping of
`running_prune` to a child operation while the backup completes arrives in
phase 8, when the backup itself becomes an operation and can be a parent.

**Files:**
- Modify: `app/api/v2/backups.py` prune, compact, and check routes
- Modify: `app/api/schedule.py:2608-2700` (scheduled prune, compact, check
  after a backup)
- Modify: `app/services/backup_plan_execution_service.py:2106-2190`
- Modify: `app/services/operations/maintenance_start.py`
- Test: `tests/unit/test_api_v2_backups.py`,
  `tests/unit/test_api_maintenance_migration.py`,
  `tests/unit/test_maintenance_state.py`

**Interfaces:**
- Consumes: `start_maintenance()`, `start_inline_maintenance()`.
- Produces: `finish_inline_maintenance(db, operation, *, enqueue_followups=True)`
  in `maintenance_start.py`.

- [x] **Step 1: Write the failing test for the inline finisher**

```python
# tests/unit/test_maintenance_start.py (append)
def test_finish_inline_enqueues_the_followup_chain(db, repository):
    from app.services.operations.executors import load_default_executors
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    load_default_executors()

    op = start_inline_maintenance(
        db, repository, "prune", params={"keep_daily": 7}, user_id=None
    )
    op.status = "completed"
    db.commit()

    finish_inline_maintenance(db, op)

    followups = (
        db.query(Operation)
        .filter(Operation.depends_on_id.isnot(None), Operation.run_id == op.run_id)
        .order_by(Operation.id.asc())
        .all()
    )
    # Spec 7.4: prune is followed by archive_sync, history_merge, stats.
    # history_merge is not plan gated (only history_index is), so the chain is
    # the same on Community.
    assert [f.kind for f in followups] == [
        "archive_sync",
        "history_merge",
        "stats",
    ]
    assert all(f.trigger == "followup" for f in followups)


def test_finish_inline_enqueues_nothing_after_a_failure(db, repository):
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(
        db, repository, "prune", params={}, user_id=None
    )
    op.status = "failed"
    db.commit()

    finish_inline_maintenance(db, op)

    assert db.query(Operation).count() == 1
```

- [x] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/unit/test_maintenance_start.py -q -p no:cacheprovider -k inline`
Expected: FAIL, cannot import `finish_inline_maintenance`.

- [x] **Step 3: Write the finisher**

The runner enqueues the spec 7.4 chain when an operation it dispatched
succeeds. An inline operation never passes through the runner, so its caller
has to do the same thing, or a dry-run prune and a post-backup prune would
leave the archive list stale, which is the bug the phase is meant to remove.

```python
# app/services/operations/maintenance_start.py (append)
def finish_inline_maintenance(
    db: Session, operation: Operation, *, enqueue_followups: bool = True
) -> None:
    """Give an inline operation the follow-up chain the runner would have
    enqueued for it (spec 7.4). Call after the caller has written the terminal
    status."""
    from app.services.operations.enqueue import enqueue_chain
    from app.services.operations.executors import registered_kinds
    from app.services.operations.followups import chain_for, history_enabled
    from app.services.operations.vocab import SUCCESS_STATUSES

    if not enqueue_followups or operation.status not in SUCCESS_STATUSES:
        return
    kinds = chain_for(
        operation.kind,
        available=registered_kinds(),
        history=history_enabled(db),
    )
    if not kinds:
        return
    enqueue_chain(
        db,
        kinds,
        repository_id=operation.repository_id,
        trigger="followup",
        run_id=operation.run_id,
        depends_on_id=operation.id,
        triggered_by_user_id=operation.triggered_by_user_id,
    )
```

- [x] **Step 4: Call the finisher from the dry-run prune route**

In `app/api/repositories.py`, after the dry-run prune has written its terminal
status, call `finish_inline_maintenance(db, prune_job, enqueue_followups=False)`.
A dry run changed nothing, so it gets no chain; passing the flag explicitly
documents that rather than leaving the reader to wonder.

- [x] **Step 5: Migrate the three v2 routes**

`app/api/v2/backups.py` gets the same treatment as the v1 routes. Prune:

```python
    if not data.dry_run:
        prune_job = start_maintenance(
            db,
            repo,
            "prune",
            trigger="manual",
            params={
                "keep_hourly": data.keep_hourly,
                "keep_daily": data.keep_daily,
                "keep_weekly": data.keep_weekly,
                "keep_monthly": data.keep_monthly,
                "keep_quarterly": data.keep_quarterly,
                "keep_yearly": data.keep_yearly,
                "keep_within": keep_within,
                "scheduled_prune": False,
            },
            user_id=current_user.id,
            duplicate_error_key="backend.errors.prune.alreadyRunning",
        )
```

Compact and check follow the shape of their v1 counterparts from Tasks 4 and
2. Delete the `CheckJob`, `CompactJob`, and `PruneJob` imports and the
`start_background_maintenance_job` import once nothing in the file uses them.

- [x] **Step 6: Delete the stats call the chain now covers**

`app/api/v2/backups.py:251` calls `await BorgRouter(repo).update_stats(db)`
after a prune, and `app/services/v2/prune_service.py:223` does the same inside
the service. Both are the scattered refresh spec section 13 replaces with the
follow-up convention: prune's chain already ends in `stats` (spec 7.4). Delete
both calls.

Section 13 says "the four scattered stats calls". Grep
`grep -rn "update_stats(" app/` and you find six, of which only these two
belong to phase 5's kinds. Of the rest, `app/services/repository_wipe_service.py:474`
is wipe (phase 6), and the two in `app/routers/config.py` plus the one in
`app/api/settings.py` refresh after a settings change rather than after a job,
so no follow-up chain replaces them. Delete two here, leave four, and record
the count in the phase notes rather than hunting for two that do not exist.

- [x] **Step 7: Migrate post-backup maintenance in the scheduler**

In `app/api/schedule.py`, each of the three blocks changes the same way. The
prune block becomes:

```python
                prune_job = start_inline_maintenance(
                    db,
                    repo,
                    "prune",
                    params={
                        "keep_hourly": scheduled_job.prune_keep_hourly,
                        "keep_daily": scheduled_job.prune_keep_daily,
                        "keep_weekly": scheduled_job.prune_keep_weekly,
                        "keep_monthly": scheduled_job.prune_keep_monthly,
                        "keep_quarterly": scheduled_job.prune_keep_quarterly,
                        "keep_yearly": scheduled_job.prune_keep_yearly,
                        "keep_within": scheduled_job.prune_keep_within,
                        "scheduled_prune": True,
                    },
                    user_id=None,
                )

                backup_job.maintenance_status = "running_prune"
                db.commit()

                await BorgRouter(repo).prune(
                    job_id=prune_job.id,
                    keep_hourly=scheduled_job.prune_keep_hourly,
                    keep_daily=scheduled_job.prune_keep_daily,
                    keep_weekly=scheduled_job.prune_keep_weekly,
                    keep_monthly=scheduled_job.prune_keep_monthly,
                    keep_quarterly=scheduled_job.prune_keep_quarterly,
                    keep_yearly=scheduled_job.prune_keep_yearly,
                    dry_run=False,
                    keep_within=scheduled_job.prune_keep_within,
                )

                db.refresh(prune_job)
                finish_inline_maintenance(db, prune_job)

                if prune_job.status == "completed":
```

`prune_job` is now an `Operation`, so `db.refresh()` still works and
`prune_job.status` reads the operations vocabulary. The comparison against
`"completed"` is unchanged, because `completed` means the same in both
vocabularies. Keep `backup_job.maintenance_status` exactly as it is: the
backup job is still a legacy row until phase 8.

Do the same for the compact and check blocks in the same function, using
`params={"scheduled_compact": True}` and the check block's existing
`max_duration` and `extra_flags` values.

- [x] **Step 8: Migrate post-backup maintenance in the plan executor**

`app/services/backup_plan_execution_service.py:2106-2190` has the same three
blocks with `create_started_maintenance_job`. Replace each with
`start_inline_maintenance(...)` plus `finish_inline_maintenance(...)` after
the refresh, keeping `scheduled_prune`, `scheduled_compact`, and
`scheduled_check` at `False` as they are today. The cancellation path at
`:836-853`, which finds the running `PruneJob` to cancel, changes to find the
running prune operation:

```python
                maintenance_job = (
                    db.query(Operation)
                    .filter(
                        Operation.repository_id == repo.id,
                        Operation.kind == "prune",
                        Operation.status == "running",
                    )
                    .order_by(Operation.id.desc())
                    .first()
                )
```

The `cancel_prune(maintenance_job.id)` call below it is unchanged: the service
resolves that id through the facade.

- [x] **Step 9: Run the affected suites**

Run: `python -m pytest tests/unit/test_maintenance_state.py tests/unit/test_api_v2_backups.py tests/unit/test_schedulers.py tests/unit/test_backup_plan_execution.py -q -p no:cacheprovider`
Expected: PASS. `test_maintenance_state.py` asserts the `maintenance_status`
transitions; they must be identical after this task. If one fails because it
counted `PruneJob` rows, change it to count prune operations and say so in the
progress notes: the state machine itself must not change.

Then the whole suite: `python -m pytest tests/unit -q -p no:cacheprovider` and
`ruff check app tests`.

---

### Task 8: Retire the old machinery

Nothing writes the five tables now, so the helpers that wrote them go, along
with their startup sweep. This is deletion with a full suite behind it.

**Files:**
- Modify: `app/api/maintenance_jobs.py`
- Modify: `app/utils/process_utils.py`
- Modify: `app/services/job_admission.py`
- Modify: `app/services/job_history_retention.py`
- Test: the existing suites, updated in place

- [x] **Step 1: Delete the dead helpers**

From `app/api/maintenance_jobs.py` delete `ensure_no_running_job`,
`create_maintenance_job`, `create_running_maintenance_job`,
`create_started_maintenance_job`, `schedule_background_job`, and
`start_background_maintenance_job`. Keep `get_repository_with_access`,
`get_repository_with_access_or_empty`, `job_has_logs_for_policy`,
`read_job_logs`, `serialize_job_status`, `serialize_job_summary`, and the two
helpers Task 2 added. Keep `get_job_with_repository` and `get_repository_jobs`
only if a caller outside the five kinds still uses them; grep first.

Run `grep -rn "start_background_maintenance_job\|create_started_maintenance_job\|create_running_maintenance_job\|ensure_no_running_job" app tests`
and expect no hits outside the tests you are about to update.

- [x] **Step 2: Finish the startup sweep**

**Amended during Task 2.** Do not delete the five branches. Removing one
strands any legacy row a pre-upgrade process left running: nothing fails it,
and a parent backup stuck in `running_check` never resolves. Instead, relabel
each branch as a legacy-only path in a comment, noting that new work is
recovered by `OperationRunner.recover_on_startup` (spec 7.6), which also makes
the local lock-break attempt. The queries are empty on any install that has
restarted since the upgrade, and the branches go away with the tables in
phase 9. Six `test_utils.py` tests mock `db.query` positionally, so removing a
query shifts every later mock and breaks them; that is the signal you removed
too much.

- [x] **Step 3: Take the five models out of the admission scan**

In `app/services/job_admission.py`, `list_active_repository_work` no longer
needs to query `CheckJob`, `RestoreCheckJob`, `CompactJob`, `PruneJob`, or
`DeleteArchiveJob`: Task 2 added the operations query that covers them, and
nothing writes new rows to those tables. Remove them from the per-model loop,
keeping `BackupJob`, `RepositoryWipeJob`, and the agent job scan. Historical
rows are all terminal, so dropping them changes nothing that is live.

- [x] **Step 4: Confirm retention still covers both worlds**

`app/services/job_history_retention.py` gained `operations` in phase 1. Read
it and confirm the five legacy tables are still in its list, since their
historical rows must keep aging out. Add a test if none asserts it:

```python
def test_retention_covers_operations_and_the_legacy_maintenance_tables():
    from app.services.job_history_retention import RETENTION_TABLES

    names = {table.__tablename__ for table in RETENTION_TABLES}
    assert "operations" in names
    assert {"check_jobs", "prune_jobs", "compact_jobs"} <= names
```

Match the real symbol name in that module; read it before writing the test.

- [x] **Step 5: Prove the status strip needs no change**

`GET /repositories/{id}/status-strip` (spec 9.2) already reads the operation
first and only prefers `latest_legacy_terminal()` when the legacy row is
newer (`app/api/archive_index.py:295-312`). A migrated kind therefore takes
over the cell on its first run with no edit. Do not touch `legacy_status.py`;
phase 9 deletes it. Add the test that pins this:

```python
def test_status_strip_prefers_a_new_check_operation_over_the_legacy_row(
    test_client, test_db, admin_headers, repository
):
    from datetime import datetime, timedelta

    from app.database.models import CheckJob, Operation

    old = datetime(2026, 9, 1, 12, 0, 0)
    test_db.add(
        CheckJob(repository_id=repository.id, status="failed", completed_at=old)
    )
    test_db.add(
        Operation(
            repository_id=repository.id,
            kind="check",
            category="maintenance",
            status="completed",
            trigger="manual",
            priority=0,
            run_id="run-strip",
            completed_at=old + timedelta(hours=1),
        )
    )
    test_db.commit()

    response = test_client.get(
        f"/api/repositories/{repository.id}/status-strip", headers=admin_headers
    )

    cells = {cell["cell"]: cell for cell in response.json()["cells"]}
    assert cells["check"]["status"] == "completed"
    assert cells["check"]["source"] == "operations"
```

Read the real response shape in `tests/unit/test_api_archive_index.py` before
writing this and match its key names.

- [x] **Step 6: Run everything**

Run: `python -m pytest tests/unit -q -p no:cacheprovider`
Run: `ruff check app tests`
Expected: green apart from the three known `test_source_discovery.py` failures.

---

### Task 9: Documentation, Postman, and phase verification

- [x] **Step 1: Update the job system document**

`docs/architecture/job-system.md` describes per-kind tables and per-kind
startup cleanup. Rewrite the maintenance section: the five kinds are rows in
`operations`, the runner owns dispatch and the lane, recovery is spec 7.6, and
the legacy tables hold history only until phase 9. Do not describe phases 6 to
8 as done.

- [x] **Step 2: Update the API document**

`docs/api.md`: the start routes still return `{"job_id", "status", "message"}`,
and `job_id` is now an operation id. Say so once, in the maintenance section,
and note that the job status routes serve operations first and fall back to
pre-phase-5 rows.

- [x] **Step 3: Postman**

`Borg_UI_API.postman_collection.json` needs no new requests. Check the saved
example responses for the check, prune, compact, restore check, and delete
routes still match; update any that named a legacy field.

- [x] **Step 4: Full verification**

Run and record the output of each:

```bash
python -m pytest tests/unit -q -p no:cacheprovider
ruff check app tests
cd frontend && npx tsc --noEmit && npm run lint && npx vitest run
```

The frontend must be untouched; run it to prove that. Then check no em dashes
entered the diff:

```bash
git diff origin/main...HEAD --name-only | xargs grep -l "—" || echo "no em dashes"
```

Use the merge-base form. The literal `main` form over-reports, as the phase 4
notes in the spec record.

- [x] **Step 5: Confirm nothing writes the five tables**

```bash
grep -rn "CheckJob(\|PruneJob(\|CompactJob(\|DeleteArchiveJob(\|RestoreCheckJob(" app/
```

Expected: no constructor calls outside `app/database/models.py`. Any hit is a
writer this phase missed.

- [x] **Step 6: Update the spec's progress table**

Set phase 5 to `in review` in section 19.1 with the branch name, the plan
path, and notes covering: the facade design, the inline exception for dry-run
prune and post-backup maintenance, which suites changed expectations, and the
verification numbers. Then stop at gate G2 and ask the user whether to commit.

---

## Open questions

Answer these at gate G1. Each has a default the implementer follows if the
user approves the plan without comment; approved defaults are recorded in the
spec's Appendix B.

1. **Id space overlap between operations and the legacy tables.**
   `resolve_maintenance_job()` tries operations first, so if operation 7 is a
   check and `check_jobs` row 7 is also a check, `GET /check-jobs/7` serves
   the operation and the historical row becomes unreachable by id. It still
   appears in Activity and in the repository job list, which read both.
   Default: accept it. The frontend only polls ids it has just been handed,
   and phase 9 deletes the tables. The alternative, offsetting legacy ids in
   the response, breaks the contract this phase promises not to change.

2. **Progress events for maintenance work.** The facade writes
   `progress_percent` straight to the row, so the Background work board sees
   progress on its next poll but gets no `operation.progress` SSE event, which
   the index executors do send through `ctx.progress()`. Default: leave it.
   The board polls, the legacy status routes poll, and threading an async
   broadcast through five synchronous service bodies is a phase 8 concern when
   backup brings real progress reporting. If the user wants live maintenance
   progress now, it becomes its own task.

3. **`scheduled_check` counting in the check scheduler.** The scheduler counts
   pending and running scheduled checks to decide how many to dispatch. On
   operations that flag lives inside the `params` JSON, which SQLite can query
   but not index. Default: load the repository's active check operations and
   filter in Python, since the row count is tiny. The alternative, a real
   column, contradicts the "no new columns" constraint and spec 6.2.

4. **Post-backup maintenance stays inline.** Explained in Task 7. Default: as
   written, with spec 6.3's parent-child mapping arriving in phase 8. The
   alternative, queueing it, deadlocks against `legacy_running_exclusive`
   while the backup row sits in `running_prune`.

5. **Cancelling a queued maintenance operation.** The legacy cancel routes
   killed a process; a queued operation has none. `POST /api/operations/{id}/cancel`
   already handles both (spec 7.7), and Task 5 routes the delete cancel through
   it. Default: leave the other four kinds without a cancel route, exactly as
   today, rather than adding one this phase. Users reach it through the
   Background work board.

6. **Agent repositories.** The route's agent branch disappears because
   `BorgRouter` already routes to the agent and waits. That makes an agent
   maintenance run occupy a runner slot for its whole duration, where before
   it occupied an `asyncio` task. Default: accept it. `index_workers` does not
   apply to maintenance kinds, and the lane is the point. Flag it in the phase
   notes so the phase 8 backup migration knows the pattern.
