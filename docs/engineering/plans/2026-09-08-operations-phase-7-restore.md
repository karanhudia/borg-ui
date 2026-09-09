# Operations Phase 7: Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit at the
> end of a task; the phase has one commit gate (G2) at the end, per section
> 19.4 of the spec and `.claude/instructions.md`.

**Goal:** Move restore off `restore_jobs` onto `operations` plus the
`operation_restore_details` extension table spec 6.2 names, so a restore has
a real `repository_id` (the gap section 13 lists for this phase), appears on
the Background work board and in the Activity union like every other migrated
kind, is dispatched and recovered by the runner, and keeps every response body
and status word the restore routes return today.

**Architecture:** Phase 5's facade pattern, repeated once more, exactly as
phase 6 did for wipe. `restore_service.py` keeps its three execution paths
(local, SSH destination through SSHFS, managed agent) and changes only what a
job id resolves to: `resolve_restore_job(db, job_id)` returns a
`RestoreJobFacade` over an `Operation` and its details row for new work, and
the real `RestoreJob` for an id written before this phase. The start route
enqueues instead of spawning a task; a thin executor under
`app/services/operations/executors/restore.py` loads the repository, calls the
service with the inputs the details row and `params` carry, watches the
runner's cancel flag, and turns the row's final status into an `Outcome`. One
Alembic revision creates the extension table.

**Tech Stack:** FastAPI, SQLAlchemy 1.x declarative models, Alembic, asyncio
subprocess handling in the existing service, `BorgRouter` for the v1/v2
command shape, pytest with the `test_db` / `test_client` / `admin_headers`
fixtures from `tests/fixtures/api.py`, the in-memory `db` fixture pattern from
`tests/unit/test_operations_wipe_facade.py`, and the `testing_session_local`
pattern from `tests/unit/test_restore_service.py`. No new dependencies.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
(sections 6.1, 6.2, 6.3, 7.1, 7.2, 7.4, 7.6, 7.7, 7.8, 9.3, 13, 19,
Appendix A.2, Appendix B).

## Model

Section 13 gives phase 7 Opus 5 for both implementation and review: "Restore
has remote destinations and agent execution paths." This plan was drafted on
Fable 5.1 at the owner's choice at gate G0 on 2026-09-08, the same deviation
phases 4 and 6 recorded for their drafts.

## Global Constraints

- Phase 7 is backend only. No frontend file changes, no i18n keys, no
  stories. Every HTTP response body keeps the exact shape and the exact
  status vocabulary it has today, per section 13: "Phases 5 through 9 are
  internal refactors with no visible change except fewer lock errors."
  The load-bearing contracts, pinned by tests in this phase: `POST
  /api/restore/start` answers `{"job_id", "status": "pending", "message"}`;
  `GET /api/restore/jobs` and `GET /api/restore/status/{id}` answer the
  field set `frontend/src/components/RestoreJobCard.tsx:7-23` reads,
  including `progress_details.{nfiles, current_file, progress_percent,
  restore_speed, estimated_time_remaining}` and `logs`; `POST
  /api/restore/cancel/{id}` answers `{"message", "process_terminated"}` and
  refuses anything but a running job with 400; the status words are
  `pending`, `running`, `completed`, `completed_with_warnings`, `failed`,
  `cancelled`.
- Spec 6.2 is the column list for `operation_restore_details`, keyed on
  `operations.id` with `ondelete="CASCADE"`, plus one column the list
  dropped and the legacy row needs: `original_size` (Open question 1).
  `progress` (an int) is `operations.progress_percent`;
  `estimated_time_remaining` is derived (Open question 2); the legacy
  `execution_mode` words (`local_to_local`, `ssh_to_local`, `local_to_ssh`)
  are not stored, nothing reads them, and `operations.execution_mode` gets
  the spec 6.1 vocabulary (`server` or `agent`); `logs` is the operation's
  log file (spec 6.1); `repository` (a path) becomes `repository_id`.
- Spec 6.3 is verbatim and already in `vocab.py`: `restore` is category
  `restore`, not exclusive ("Reads only. Borg allows concurrent reads."),
  trigger `manual`, priority 0. Do not edit `vocab.py`.
- Spec 7.4 is verbatim and already in `followups.py`: `restore` gets no
  follow-ups. Do not edit `followups.py`.
- Nothing in this phase writes a new row to `restore_jobs`. The table stays
  in the schema with its historical rows; phase 9 deletes it. After this
  phase, `grep -rn "RestoreJob(" app/` must return nothing.
- The restore executor takes no repository lock and the lane rules treat it
  as non-exclusive, matching the legacy service and Appendix B ("Restore is
  non-exclusive"). See Open question 3.
- No em dashes anywhere: code comments, docstrings, docs, or commit message.
  Check added lines only, with `git diff -U0`.
- One commit at the end of the phase, at gate G2, after
  `superpowers:verification-before-completion` passes. Nothing is pushed
  without the owner's answer at that gate.

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `app/database/alembic/versions/f7a8b9c0d1e2_add_operation_restore_details.py` | The one migration: the extension table. |
| `app/services/operations/restore_facade.py` | `RestoreJobFacade`, `resolve_restore_job`, `list_restore_jobs`, the two cancel message constants. |
| `app/services/operations/executors/restore.py` | `run_restore`. |
| `tests/unit/test_operations_restore_facade.py` | Facade round trips, id resolution, the union list. |
| `tests/unit/test_operations_restore_executor.py` | The executor. |

**Modified**

| File | Change |
| --- | --- |
| `app/database/models.py` | `OperationRestoreDetails` after `OperationRcloneDetails`. |
| `app/services/operations/details.py` | `restore_details(db, operation)`. |
| `app/services/operations/executors/__init__.py` | Register `restore` in `load_default_executors`. |
| `app/api/restore.py` | Start enqueues; list, status, and cancel resolve either id space. |
| `app/services/restore_service.py` | Every job lookup goes through `resolve_restore_job`. |
| `app/api/activity.py` | `restore` becomes an operation-first kind on the three log routes. |
| `app/api/ssh_keys.py` | Connection deletion nulls the details row's `destination_connection_id`. |
| `app/utils/process_utils.py` | Comment on the legacy restore branch. |
| `app/services/repository_wipe_service.py` | Comment on the legacy restore query. |
| `docs/architecture/job-system.md`, `docs/api.md` | Task 7. |
| `tests/unit/test_operations_details.py`, `tests/unit/test_api_restore.py`, `tests/unit/test_restore_service.py`, `tests/unit/test_api_activity.py`, `tests/unit/test_api_ssh_keys.py`, `tests/unit/test_job_history_retention.py` | Extended per task. |

---

## Task 1: Extension table and the details helper

**Files:**
- Create: `app/database/alembic/versions/f7a8b9c0d1e2_add_operation_restore_details.py`
- Modify: `app/database/models.py` (after `class OperationRcloneDetails`, before `class Archive`)
- Modify: `app/services/operations/details.py`
- Test: `tests/unit/test_operations_details.py`

**Interfaces:**
- Consumes: `Operation` (phase 1), `_get_or_create` in `details.py` (phase 6).
- Produces: `OperationRestoreDetails`;
  `details.restore_details(db: Session, operation: Operation) -> OperationRestoreDetails`,
  get-or-create, flushing so the row is readable in the same transaction.
  Tasks 2 and 3 use only this function; no other module constructs the row.

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_operations_details.py` (the `db`, `repository`,
and `_operation` helpers already exist there; extend `_operation`'s category
line so `restore` maps to `restore`):

```python
def test_restore_details_is_created_once_per_operation(db, repository):
    from app.database.models import OperationRestoreDetails
    from app.services.operations.details import restore_details

    op = _operation(db, repository, "restore")

    first = restore_details(db, op)
    first.archive = "nas-2026-09-08"
    first.original_size = 3 * 1024**3
    second = restore_details(db, op)

    assert first.operation_id == op.id
    assert second is first
    assert second.archive == "nas-2026-09-08"
    assert second.original_size == 3 * 1024**3
    assert db.query(OperationRestoreDetails).count() == 1


def test_restore_details_row_is_deleted_with_its_operation(db, repository):
    from app.database.models import OperationRestoreDetails
    from app.services.operations.details import restore_details

    op = _operation(db, repository, "restore")
    restore_details(db, op)
    db.commit()

    db.delete(op)
    db.commit()

    assert db.query(OperationRestoreDetails).count() == 0
```

Change the existing helper's category expression to:

```python
category={"wipe": "maintenance", "restore": "restore"}.get(kind, "mirror"),
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_details.py -v`
Expected: the two new tests FAIL with `ImportError: cannot import name
'OperationRestoreDetails'`; the existing tests still pass.

- [x] **Step 3: Add the model**

In `app/database/models.py`, directly after `class OperationRcloneDetails`
and before `class Archive`:

```python
class OperationRestoreDetails(Base):
    """Restore-specific columns for an `operations` row. Spec section 6.2.

    `original_size` is not in the spec's list. The legacy row kept it (the
    byte total borg reports, from which the percentage and the ETA are
    computed) and it cannot ride in `operations.progress_total`, an Integer
    column that overflows at 2 GiB on PostgreSQL. `estimated_time_remaining`
    and `progress` are not here either: the first is arithmetic over the
    sizes and the speed, the second is `operations.progress_percent`.
    """

    __tablename__ = "operation_restore_details"

    operation_id = Column(
        Integer,
        ForeignKey("operations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    archive = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    destination_type = Column(String(50), default="local")
    destination_connection_id = Column(
        Integer, ForeignKey("ssh_connections.id", ondelete="SET NULL"), nullable=True
    )
    temp_extraction_path = Column(String(255), nullable=True)
    destination_hostname = Column(String(255), nullable=True)
    repository_type = Column(String(50), default="local")
    original_size = Column(BigInteger, default=0)
    restored_size = Column(BigInteger, default=0)
    restore_speed = Column(Float, default=0.0)
    nfiles = Column(Integer, default=0)
    current_file = Column(Text, nullable=True)
```

- [x] **Step 4: Extend the details helper**

In `app/services/operations/details.py`, add `OperationRestoreDetails` to
the import and append:

```python
def restore_details(db: Session, operation: Operation) -> OperationRestoreDetails:
    return _get_or_create(db, OperationRestoreDetails, operation)
```

Update the module docstring's first paragraph to "Wipe, rclone sync, and
restore have one."

- [x] **Step 5: Write the migration**

Create `app/database/alembic/versions/f7a8b9c0d1e2_add_operation_restore_details.py`:

```python
"""add operation restore extension table

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_restore_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("archive", sa.String(), nullable=True),
        sa.Column("destination", sa.String(), nullable=True),
        sa.Column(
            "destination_type", sa.String(length=50), nullable=True, server_default="local"
        ),
        sa.Column(
            "destination_connection_id",
            sa.Integer(),
            sa.ForeignKey("ssh_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("temp_extraction_path", sa.String(length=255), nullable=True),
        sa.Column("destination_hostname", sa.String(length=255), nullable=True),
        sa.Column(
            "repository_type", sa.String(length=50), nullable=True, server_default="local"
        ),
        sa.Column("original_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("restored_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("restore_speed", sa.Float(), nullable=True, server_default="0"),
        sa.Column("nfiles", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("current_file", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("operation_restore_details")
```

Before writing it, confirm the parent is still the single head:

Run, from the repository root (where `alembic.ini` lives): `alembic heads`
Expected: one line, `e5f6a7b8c9d0 (head)`. If a second head appears (another
branch merged a migration since this plan was written), re-parent onto that
head instead and record it in the spec's Notes column, as phase 6 did.

- [x] **Step 6: Run the tests and the migration end to end**

Run: `pytest tests/unit/test_operations_details.py -v`
Expected: PASS.

Run, against a scratch database:

```bash
export DATABASE_URL=sqlite:////tmp/phase7-scratch.db
alembic upgrade head && alembic heads
unset DATABASE_URL
```

Expected: upgrade succeeds, `alembic heads` prints exactly
`f7a8b9c0d1e2 (head)`. Delete `/tmp/phase7-scratch.db` afterwards.

---

## Task 2: The restore facade

**Files:**
- Create: `app/services/operations/restore_facade.py`
- Test: `tests/unit/test_operations_restore_facade.py`

**Interfaces:**
- Consumes: `restore_details` (Task 1), `Operation`, `Repository`,
  `RestoreJob`, `operation_log_path` from `app/services/operations/runner.py`.
- Produces:
  - `RestoreJobFacade(db, operation)`: the attribute surface
    `restore_service.py` and `app/api/restore.py` read and write: `id`,
    `repository` (path, read only), `repository_id`, `status`, `started_at`,
    `completed_at`, `error_message`, `progress`, `progress_percent`,
    `original_size`, `estimated_time_remaining`, `logs`, `log_file_path`,
    `created_at`, plus every spec 6.2 column as a plain attribute.
  - `resolve_restore_job(db, job_id) -> RestoreJobFacade | RestoreJob | None`.
  - `list_restore_jobs(db, limit) -> list`: newest first across both tables.
  - `CANCELLED_BY_USER`, `CANCELLED_PROCESS_NOT_FOUND`, `CANCEL_MESSAGES`:
    the JSON error messages the cancel route writes, shared with Task 5.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_operations_restore_facade.py`:

```python
"""Phase 7: an `operations` row wearing the legacy restore-job surface."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, RestoreJob
from app.services.operations.details import restore_details
from app.services.operations.restore_facade import (
    RestoreJobFacade,
    list_restore_jobs,
    resolve_restore_job,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repository(db):
    repo = Repository(name="nas", path="/repo/nas", borg_version=1)
    db.add(repo)
    db.commit()
    return repo


@pytest.fixture()
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return tmp_path / "logs"


def _restore_operation(db, repository, status="queued", params=None):
    op = Operation(
        repository_id=repository.id,
        kind="restore",
        category="restore",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {"archive_name": "nas-2026-09-08", "paths": []},
    )
    db.add(op)
    db.flush()
    restore_details(db, op).archive = op.params["archive_name"]
    db.commit()
    return op


def test_queued_operation_reads_as_pending_and_pending_writes_queued(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    assert job.status == "pending"

    job.status = "running"
    assert job.operation.status == "running"
    job.status = "pending"
    assert job.operation.status == "queued"


def test_repository_is_the_path_of_the_operations_repository(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    assert job.repository == "/repo/nas"
    assert job.repository_id == repository.id


def test_details_columns_round_trip_through_the_extension_row(db, repository):
    from app.database.models import OperationRestoreDetails

    op = _restore_operation(db, repository)
    job = RestoreJobFacade(db, op)
    job.archive = "nas-2026-09-08"
    job.destination = "/restore/here"
    job.destination_type = "ssh"
    job.destination_hostname = "backup.example"
    job.repository_type = "local"
    job.restored_size = 512
    job.restore_speed = 2.5
    job.nfiles = 3
    db.commit()

    row = db.get(OperationRestoreDetails, op.id)
    assert row.archive == "nas-2026-09-08"
    assert row.destination == "/restore/here"
    assert row.destination_type == "ssh"
    assert row.destination_hostname == "backup.example"
    assert row.restored_size == 512
    assert row.restore_speed == 2.5
    assert row.nfiles == 3
    assert RestoreJobFacade(db, op).nfiles == 3


def test_progress_int_and_percent_share_one_column(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    job.progress_percent = 42.6
    assert job.progress == 42
    job.progress = 100
    assert job.operation.progress_percent == 100.0


def test_original_size_and_eta_follow_the_legacy_arithmetic(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    job.original_size = 10 * 1024 * 1024
    job.restored_size = 4 * 1024 * 1024
    job.restore_speed = 2.0  # MB/s

    assert job.original_size == 10 * 1024 * 1024
    assert job.estimated_time_remaining == 3

    job.restore_speed = 0.0
    assert job.estimated_time_remaining == 0
    job.restore_speed = 2.0
    job.restored_size = job.original_size
    assert job.estimated_time_remaining == 0

    # The service also assigns the ETA it computed; the facade accepts and
    # drops the write because the value is derived.
    job.estimated_time_remaining = 999
    assert job.estimated_time_remaining == 0


def test_current_file_is_mirrored_into_progress_message(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    job.current_file = "docs/report.txt"
    assert job.current_file == "docs/report.txt"
    assert job.operation.progress_message == "docs/report.txt"


def test_logs_are_written_to_and_read_from_the_operation_log_file(
    db, repository, log_dir
):
    op = _restore_operation(db, repository)
    job = RestoreJobFacade(db, op)
    assert job.logs == ""

    job.logs = "STDOUT:\nrestored\n\nSTDERR:\n(no output)"
    db.commit()

    assert op.log_file_path == str(log_dir / f"operation_{op.id}.log")
    assert (log_dir / f"operation_{op.id}.log").read_text() == (
        "STDOUT:\nrestored\n\nSTDERR:\n(no output)"
    )
    assert RestoreJobFacade(db, op).logs.startswith("STDOUT:")


def test_unknown_attributes_raise(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    with pytest.raises(AttributeError):
        job.no_such_column


def test_resolve_prefers_operations_then_falls_back_to_the_legacy_row(db, repository):
    op = _restore_operation(db, repository)
    # Distinct ids on purpose: on a fresh database both tables start at 1, and
    # a shared id would resolve to the operation and never exercise the legacy
    # branch this test is about.
    legacy = RestoreJob(
        id=op.id + 1000, repository=repository.path, archive="old", status="completed"
    )
    db.add(legacy)
    db.commit()

    assert isinstance(resolve_restore_job(db, op.id), RestoreJobFacade)
    assert resolve_restore_job(db, legacy.id) is legacy
    assert resolve_restore_job(db, 9999) is None


def test_list_restore_jobs_unions_both_tables_newest_first(db, repository):
    from datetime import datetime, timedelta

    base = datetime(2026, 9, 8, 12, 0, 0)
    old = RestoreJob(
        repository=repository.path, archive="a", status="completed", created_at=base
    )
    db.add(old)
    db.commit()
    op = _restore_operation(db, repository)
    op.created_at = base + timedelta(minutes=5)
    newer_legacy = RestoreJob(
        repository=repository.path,
        archive="b",
        status="completed",
        created_at=base + timedelta(minutes=10),
    )
    db.add(newer_legacy)
    db.commit()

    jobs = list_restore_jobs(db, limit=2)

    assert [j.archive for j in jobs] == ["b", "nas-2026-09-08"]
    assert isinstance(jobs[1], RestoreJobFacade)
    assert len(list_restore_jobs(db, limit=10)) == 3
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_restore_facade.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named
'app.services.operations.restore_facade'`.

- [x] **Step 3: Write the facade**

Create `app/services/operations/restore_facade.py`:

```python
"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
restore-job attribute surface.

`restore_service` and the restore routes drive a job through a fixed set of
attributes. Phase 7 moves the row to `operations` without rewriting them:
`resolve_restore_job()` hands them this facade for new work and the real
`RestoreJob` for an id written before this phase.

Three legacy columns have no column of their own here. `progress` (an int) is
`operations.progress_percent`; `estimated_time_remaining` is arithmetic over
the sizes and the speed, exactly the arithmetic the service performs before
assigning it; `logs`, which the service builds once at the end, goes to the
operation's log file (spec 6.1), which the Activity log routes and log
retention already read and expire.

Deleted in phase 9 with the legacy table.
"""

import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, Repository, RestoreJob
from app.services.operations.details import restore_details

CANCELLED_BY_USER = json.dumps({"key": "backend.errors.restore.cancelledByUser"})
CANCELLED_PROCESS_NOT_FOUND = json.dumps(
    {"key": "backend.errors.restore.cancelledByUserProcessNotFound"}
)
CANCEL_MESSAGES = (CANCELLED_BY_USER, CANCELLED_PROCESS_NOT_FOUND)

_BYTES_PER_MB = 1024 * 1024

# Spec 6.2 columns that live on the details row and need no translation.
# `current_file` is not here: it has a property below so the Background work
# board's progress message follows it.
_DETAIL_FIELDS = (
    "archive",
    "destination",
    "destination_type",
    "destination_connection_id",
    "temp_extraction_path",
    "destination_hostname",
    "repository_type",
    "original_size",
    "restored_size",
    "restore_speed",
    "nfiles",
)


class RestoreJobFacade:
    """One `Operation` presented as a legacy restore job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "_details", restore_details(db, operation))

    def __setattr__(self, name: str, value) -> None:
        # A restore-specific column lives on the details row, not on this
        # object, so a plain `object.__setattr__` would silently drop it.
        # Everything else (status, progress, ...) is a real property below
        # and goes through the normal descriptor path.
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "_details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        # Only reached when normal lookup fails, so every property below wins.
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "_details"), name)
        raise AttributeError(f"restore operations carry no {name!r}")

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
    def repository(self) -> Optional[str]:
        """The repository path, which is what the legacy row stored and what
        the routes still answer under this name."""
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
        return "pending" if self.operation.status == "queued" else self.operation.status

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = "queued" if value == "pending" else value

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
    def progress_percent(self) -> float:
        return float(self.operation.progress_percent or 0.0)

    @progress_percent.setter
    def progress_percent(self, value) -> None:
        self.operation.progress_percent = float(value or 0.0)

    @property
    def current_file(self) -> Optional[str]:
        return self._details.current_file

    @current_file.setter
    def current_file(self, value) -> None:
        self._details.current_file = value
        self.operation.progress_message = value or None

    @property
    def estimated_time_remaining(self) -> int:
        speed = self._details.restore_speed or 0.0
        remaining = (self._details.original_size or 0) - (
            self._details.restored_size or 0
        )
        if remaining <= 0 or speed <= 0:
            return 0
        return int((remaining / _BYTES_PER_MB) / speed)

    @estimated_time_remaining.setter
    def estimated_time_remaining(self, value) -> None:
        """Derived from the sizes and the speed the service also writes; the
        legacy column stored the result of the same arithmetic. Accepted and
        dropped."""
        return None

    # -- logs --------------------------------------------------------------

    @property
    def log_file_path(self):
        return self.operation.log_file_path

    @log_file_path.setter
    def log_file_path(self, value) -> None:
        self.operation.log_file_path = value

    @property
    def logs(self) -> str:
        path = self.operation.log_file_path
        if not path:
            return ""
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return ""

    @logs.setter
    def logs(self, value) -> None:
        """The service captures the process output and assigns it once, at the
        end. The operation keeps it in its log file rather than on the row."""
        from app.services.operations.runner import operation_log_path

        if value is None:
            return
        path = (
            Path(self.operation.log_file_path)
            if self.operation.log_file_path
            else operation_log_path(self.operation.id)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        self.operation.log_file_path = str(path)


def resolve_restore_job(db: Session, job_id: int) -> Any:
    """The job a restore caller should drive for `job_id`.

    Operations win, so new work runs on the new table. Ids that belong to a
    row written before this phase fall back to the legacy table, which keeps
    the status and cancel routes working for history.
    """
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "restore")
        .first()
    )
    if operation is not None:
        return RestoreJobFacade(db, operation)
    return db.query(RestoreJob).filter(RestoreJob.id == job_id).first()


def list_restore_jobs(db: Session, limit: int) -> list:
    """The newest `limit` restore jobs across both tables, newest first, for
    the list route. Each table contributes its own newest `limit` rows, then
    the merge cuts to `limit`, so the answer is exact either way."""
    operations = (
        db.query(Operation)
        .filter(Operation.kind == "restore")
        .order_by(Operation.id.desc())
        .limit(limit)
        .all()
    )
    legacy = db.query(RestoreJob).order_by(RestoreJob.id.desc()).limit(limit).all()
    jobs = [RestoreJobFacade(db, op) for op in operations] + list(legacy)
    jobs.sort(key=lambda job: job.created_at, reverse=True)
    return jobs[:limit]
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_operations_restore_facade.py -v`
Expected: PASS, eleven tests.

Then: `pytest tests/unit/test_operations_details.py tests/unit/test_operations_wipe_facade.py -q`
Expected: still green.

---

## Task 3: The restore routes enqueue and resolve either id space

**Files:**
- Modify: `app/api/restore.py`
- Test: `tests/unit/test_api_restore.py`

**Interfaces:**
- Consumes: `enqueue`, `wake_runner` from `app/services/operations/enqueue.py`;
  `restore_details` (Task 1); `RestoreJobFacade`, `resolve_restore_job`,
  `list_restore_jobs`, `CANCELLED_BY_USER`, `CANCELLED_PROCESS_NOT_FOUND`
  (Task 2); `operation_runner.request_cancel` (phase 1);
  `is_agent_executor` from `app/services/repository_executor.py`.
- Produces: an `operations` row of kind `restore` with `params` =
  `{"archive_name", "paths", "restore_layout", "path_metadata"}` and a
  details row carrying `archive`, `destination`, `destination_type`,
  `destination_connection_id`, `destination_hostname`, `repository_type`.
  Task 5's executor reads exactly these.

- [x] **Step 1: Write the failing tests**

In `tests/unit/test_api_restore.py`, replace
`test_start_restore_accepts_repository_id_in_repository_field` and
`test_start_restore_passes_restore_layout_and_path_metadata` (both patch
`asyncio.create_task`, which the route no longer calls) with these two, and
add the three that follow. Add `from unittest.mock import AsyncMock, patch`
and `from app.database.models import Operation, OperationRestoreDetails` to
the imports if missing.

```python
    def test_start_restore_enqueues_an_operation_with_details(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # The live runner may dispatch the row before this test reads it back;
        # a mocked service keeps that harmless. The assertions below do not
        # depend on whether it ran.
        with patch(
            "app.services.restore_service.restore_service.execute_restore",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                "/api/restore/start",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": ["docs/"],
                    "destination": "/restore/target",
                    "restore_layout": "contents_only",
                    "path_metadata": [{"path": "docs/", "type": "directory"}],
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["message"] == "backend.success.restore.restoreJobStarted"

        operation = test_db.get(Operation, body["job_id"])
        assert operation.kind == "restore"
        assert operation.category == "restore"
        assert operation.trigger == "manual"
        assert operation.repository_id == repo.id
        assert operation.execution_mode == "server"
        assert operation.params == {
            "archive_name": "test-archive",
            "paths": ["docs/"],
            "restore_layout": "contents_only",
            "path_metadata": [{"path": "docs/", "type": "directory"}],
        }
        details = test_db.get(OperationRestoreDetails, operation.id)
        assert details.archive == "test-archive"
        assert details.destination == "/restore/target"
        assert details.destination_type == "local"
        assert details.repository_type == "local"
        assert test_db.query(RestoreJob).count() == 0

    def test_start_restore_records_the_ssh_destination_on_the_details_row(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.database.models import SSHConnection

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        connection = SSHConnection(host="backup.example", username="borg", port=22)
        test_db.add_all([repo, connection])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(connection)

        with patch(
            "app.services.restore_service.restore_service.execute_restore",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                "/api/restore/start",
                json={
                    "repository": repo.path,
                    "repository_id": repo.id,
                    "archive": "test-archive",
                    "paths": [],
                    "destination": "/srv/restore",
                    "destination_type": "ssh",
                    "destination_connection_id": connection.id,
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        details = test_db.get(OperationRestoreDetails, response.json()["job_id"])
        assert details.destination_type == "ssh"
        assert details.destination_connection_id == connection.id
        assert details.destination_hostname == "backup.example"

    def test_status_reads_an_operation_with_the_legacy_shape(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.details import restore_details

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-status",
            progress_percent=40.0,
            params={"archive_name": "test-archive"},
        )
        test_db.add(op)
        test_db.flush()
        details = restore_details(test_db, op)
        details.archive = "test-archive"
        details.destination = "/restore/target"
        details.original_size = 10 * 1024 * 1024
        details.restored_size = 4 * 1024 * 1024
        details.restore_speed = 2.0
        details.nfiles = 7
        details.current_file = "docs/report.txt"
        test_db.commit()

        response = test_client.get(f"/api/restore/status/{op.id}", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == op.id
        assert body["repository"] == repo.path
        assert body["archive"] == "test-archive"
        assert body["destination"] == "/restore/target"
        assert body["status"] == "running"
        assert body["progress"] == 40
        assert body["progress_details"] == {
            "nfiles": 7,
            "current_file": "docs/report.txt",
            "progress_percent": 40.0,
            "restore_speed": 2.0,
            "estimated_time_remaining": 3,
        }

    def test_list_unions_operations_and_legacy_rows(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.details import restore_details

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        legacy = RestoreJob(
            repository=repo.path, archive="old", destination="/x", status="completed"
        )
        op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="completed",
            trigger="manual",
            priority=0,
            run_id="run-list",
            params={"archive_name": "new"},
        )
        test_db.add_all([legacy, op])
        test_db.flush()
        restore_details(test_db, op).archive = "new"
        test_db.commit()

        response = test_client.get("/api/restore/jobs", headers=admin_headers)

        assert response.status_code == 200
        archives = {job["archive"] for job in response.json()["jobs"]}
        assert archives == {"old", "new"}

    def test_cancel_running_operation_kills_the_process_and_flags_the_runner(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.restore_facade import CANCELLED_BY_USER

        repo = Repository(
            name="Restore Repo",
            path="/test/restore-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-cancel",
        )
        test_db.add(op)
        test_db.commit()

        with (
            patch(
                "app.api.restore.operation_runner.request_cancel",
                new=AsyncMock(return_value=True),
            ) as request_cancel,
            patch(
                "app.api.restore.restore_service.cancel_restore",
                new=AsyncMock(return_value=True),
            ) as cancel_restore,
        ):
            response = test_client.post(
                f"/api/restore/cancel/{op.id}", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json()["process_terminated"] is True
        request_cancel.assert_awaited_once_with(op.id)
        cancel_restore.assert_awaited_once_with(op.id)
        test_db.expire_all()
        assert op.status == "cancelled"
        assert op.error_message == CANCELLED_BY_USER
        assert op.completed_at is not None
```

Keep every other test in the file as it is: the legacy-row tests (cancel on
a `RestoreJob`, the speed and ETA fields, the log policy cases) now exercise
the fallback branch and must keep passing unchanged.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_api_restore.py -v -k "enqueues or ssh_destination or reads_an_operation or unions or flags_the_runner"`
Expected: the five FAIL (the start route still writes `RestoreJob`, so the
first asserts on `params` fail; the status route 404s on an operation id).

- [x] **Step 3: Rewrite the start route**

In `app/api/restore.py`, add the imports:

```python
from app.services.operations.details import restore_details
from app.services.operations.enqueue import enqueue, wake_runner
from app.services.operations.restore_facade import (
    CANCELLED_BY_USER,
    CANCELLED_PROCESS_NOT_FOUND,
    list_restore_jobs,
    resolve_restore_job,
)
from app.services.operations.runner import operation_runner
from app.services.repository_executor import is_agent_executor
```

Drop `RestoreJob` from the `app.database.models` import and remove the
`import asyncio` line (nothing else in the file uses it). Change
`_restore_job_logs_visible`'s annotation to `job: Any` (import `Any` from
`typing`); it reads `logs` and `error_message`, which both shapes carry.

Replace the block from `# Create restore job record with new fields` through
the `return {...}` in `start_restore` with:

```python
        # Phase 7: the row is an operation (spec 6.1) with its restore columns
        # on the details row (spec 6.2). The runner dispatches it (spec 7.1);
        # this route spawns nothing of its own.
        operation = enqueue(
            db,
            "restore",
            repository_id=repository.id,
            trigger="manual",
            params={
                "archive_name": restore_request.archive,
                "paths": list(restore_request.paths),
                "restore_layout": restore_request.restore_layout,
                "path_metadata": [
                    _restore_path_metadata_to_dict(item)
                    for item in restore_request.path_metadata
                ],
            },
            triggered_by_user_id=current_user.id,
            execution_mode="agent" if is_agent_executor(repository) else "server",
            commit=False,
        )
        details = restore_details(db, operation)
        details.archive = restore_request.archive
        details.destination = restore_request.destination
        details.destination_type = restore_request.destination_type
        details.destination_connection_id = restore_request.destination_connection_id
        details.destination_hostname = destination_hostname
        details.repository_type = repository.repository_type
        db.commit()
        wake_runner()

        logger.info(
            "Restore job created",
            job_id=operation.id,
            user=current_user.username,
            execution_mode=execution_mode,
            restore_layout=restore_request.restore_layout,
        )

        return {
            "job_id": operation.id,
            "status": "pending",
            "message": "backend.success.restore.restoreJobStarted",
        }
```

`execution_mode` (the legacy `local_to_local` word) stays as the log field
it already is; nothing stores it. `archive_name` appears in `params` as well
as on the details row because `serialize_operation` in
`app/services/operations/models.py` reads `params["archive_name"]` for every
operations route (Open question 6).

- [x] **Step 4: Resolve either id space on the list, status, and cancel routes**

In `get_restore_jobs`, replace the query line with:

```python
        jobs = list_restore_jobs(db, limit)
```

In `get_restore_status` and `cancel_restore`, replace
`db.query(RestoreJob).filter(RestoreJob.id == job_id).first()` with
`resolve_restore_job(db, job_id)`.

In `cancel_restore`, replace the block from `# Try to terminate the actual
process` through `db.commit()` with:

```python
        # Order matters. The runner's flag has to be raised while the row is
        # still `running` (request_cancel refuses any other status), and it is
        # what makes the executor keep `cancelled` if the service writes
        # `failed` for the killed process a moment later (spec 7.7). A
        # pre-phase-7 row has no operation and no task; request_cancel
        # answers False for it and the legacy write below still applies.
        await operation_runner.request_cancel(job_id)
        process_killed = await restore_service.cancel_restore(job_id)

        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = (
            CANCELLED_BY_USER if process_killed else CANCELLED_PROCESS_NOT_FOUND
        )
        db.commit()
```

and move `from datetime import datetime` to the module imports (`timezone` is
already imported there). Remove the now unused `import json`.

- [x] **Step 5: Run the restore API tests**

Run: `pytest tests/unit/test_api_restore.py -v`
Expected: PASS, every test, including the untouched legacy-row ones.

- [x] **Step 6: Confirm nothing in `app/` writes the legacy table**

Run: `grep -rn "RestoreJob(" app/`
Expected: no output.

---

## Task 4: The service drives the facade

**Files:**
- Modify: `app/services/restore_service.py`
- Test: `tests/unit/test_restore_service.py`

**Interfaces:**
- Consumes: `resolve_restore_job` (Task 2).
- Produces: `execute_restore(job_id, ...)` and `cancel_restore(job_id)`
  unchanged in signature, now working for an operation id. Task 5 calls
  `execute_restore` with the operation id.

- [x] **Step 1: Write the failing tests**

Add to `tests/unit/test_restore_service.py`, after the `restore_job` fixture:

```python
@pytest.fixture
def restore_operation(db_session, restore_repository, tmp_path, monkeypatch):
    from app.database.models import Operation
    from app.services.operations.details import restore_details

    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    op = Operation(
        repository_id=restore_repository.id,
        kind="restore",
        category="restore",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-service",
        params={"archive_name": "archive-1", "paths": []},
    )
    db_session.add(op)
    db_session.flush()
    details = restore_details(db_session, op)
    details.archive = "archive-1"
    details.destination = str(tmp_path / "restore-target")
    details.repository_type = "local"
    details.destination_type = "local"
    db_session.commit()
    db_session.refresh(op)
    return op
```

and, inside `TestRestoreServiceExecution`:

```python
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_local_restore_on_an_operation_writes_the_row_and_its_log_file(
        self, testing_session_local, restore_operation, restore_repository, tmp_path
    ):
        from app.database.models import Operation, OperationRestoreDetails

        service = RestoreService()
        process = FakeRestoreProcess(
            returncode=0,
            stderr_chunks=[
                json.dumps(
                    {
                        "type": "progress_percent",
                        "current": 10,
                        "total": 20,
                        "info": ["docs/report.txt"],
                        "finished": False,
                    }
                )
                + "\n"
            ],
            stdout_lines=[b"restored\n"],
        )
        notification_mock = SimpleNamespace(
            send_restore_success=AsyncMock(return_value=None),
            send_restore_failure=AsyncMock(return_value=None),
        )

        with (
            patch("app.services.restore_service.SessionLocal", testing_session_local),
            patch(
                "app.services.restore_service.asyncio.create_subprocess_exec",
                return_value=process,
            ),
            patch("app.services.restore_service.notification_service", notification_mock),
        ):
            await service._execute_local_to_local(
                restore_operation.id,
                restore_repository.path,
                "archive-1",
                str(tmp_path / "restore-target"),
                None,
            )

        verification = testing_session_local()
        op = verification.get(Operation, restore_operation.id)
        details = verification.get(OperationRestoreDetails, restore_operation.id)
        assert op.status == "completed"
        assert op.progress_percent == 100.0
        assert op.log_file_path == str(tmp_path / "logs" / f"operation_{op.id}.log")
        assert "STDOUT:" in (tmp_path / "logs" / f"operation_{op.id}.log").read_text()
        assert details.original_size == 20
        assert details.restored_size == 10
        assert details.nfiles == 1
        assert details.current_file == "docs/report.txt"
        assert verification.query(RestoreJob).count() == 0
        notification_mock.send_restore_success.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_terminal_state_lands_on_the_operation(
        self, db_session, restore_operation
    ):
        from app.database.models import Operation
        from app.services.operations.restore_facade import RestoreJobFacade

        service = RestoreService()
        job = RestoreJobFacade(db_session, restore_operation)
        agent_job = SimpleNamespace(
            id=1, status="completed", result={"warning": True, "return_code": 1}
        )
        with patch.object(service, "_collect_agent_job_logs", return_value="agent log"):
            service._apply_agent_restore_terminal(db_session, job, agent_job)
        db_session.commit()

        op = db_session.get(Operation, restore_operation.id)
        assert op.status == "completed_with_warnings"
        assert op.progress_percent == 100.0
        assert json.loads(op.error_message)["params"]["exitCode"] == 1
        assert op.log_file_path is not None
        assert job.logs == "agent log"
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_restore_service.py -v -k "on_an_operation or lands_on_the_operation"`
Expected: the first FAILS (the service looks the id up in `restore_jobs`,
finds nothing, and returns without writing; the status assertion fails); the
second passes already because `_apply_agent_restore_terminal` only assigns
attributes. Keep it: it pins the facade's log handling on that path.

- [x] **Step 3: Route every job lookup through the facade**

In `app/services/restore_service.py`, add the import:

```python
from app.services.operations.restore_facade import resolve_restore_job
```

and replace each of these eight lookups with `resolve_restore_job(<session>, job_id)`,
keeping the surrounding `if not job:` / `if job is None:` guards exactly as
they are:

| Line (as of this plan) | Method | Session name |
| --- | --- | --- |
| `:209` | `execute_restore`, unsupported-mode branch | `db_session` |
| `:266` | `_execute_agent_restore`, entry | `db` |
| `:339` | `_execute_agent_restore`, `except` block | `db` |
| `:374` | `_await_agent_restore_job`, loop body | `db` |
| `:539` | `_execute_local_to_local`, entry | `db_session` |
| `:1045` | `_execute_local_to_local`, outer `except` | `db_session` |
| `:1210` | `_execute_local_to_ssh`, entry | `db_session` |
| `:1577` | `_execute_local_to_ssh`, `except` | `db_session` |

The table lists every `RestoreJob.id == job_id` query in the file. The
`RestoreJob` import stays only if a type annotation
still names it; the `job: RestoreJob` annotations on `_fail_agent_restore`,
`_notify_agent_restore`, `_mirror_agent_progress`, and
`_apply_agent_restore_terminal` change to `job: Any` (import `Any` from
`typing`), after which the `RestoreJob` import is removed.

Nothing else in the service changes. The attribute writes it makes (`status`,
`started_at`, `completed_at`, `error_message`, `progress`,
`progress_percent`, `original_size`, `restored_size`, `restore_speed`,
`estimated_time_remaining`, `nfiles`, `current_file`, `logs`) are all
properties or details columns on the facade (Task 2), and every
`db_session.commit()` commits the operation and its details row.

- [x] **Step 4: Run the service tests**

Run: `pytest tests/unit/test_restore_service.py tests/unit/test_restore_agent_delegation.py tests/unit/test_v2_restore_service.py -v`
Expected: PASS. The legacy `restore_job` fixture tests keep passing through
the fallback branch of `resolve_restore_job`.

---

## Task 5: The restore executor

**Files:**
- Create: `app/services/operations/executors/restore.py`
- Modify: `app/services/operations/executors/__init__.py`
- Test: `tests/unit/test_operations_restore_executor.py`

**Interfaces:**
- Consumes: `RestoreJobFacade`, `CANCEL_MESSAGES`, `CANCELLED_BY_USER`
  (Task 2); `cancel_watcher` from `executors/maintenance.py` (phase 5);
  `restore_service.execute_restore` and `cancel_restore` (Task 4);
  `Outcome`, `OperationContext` (phase 1).
- Produces: `run_restore(ctx) -> Outcome`, registered under `restore`.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_operations_restore_executor.py`:

```python
"""Phase 7: the restore executor is a thin shell around restore_service."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.details import restore_details
from app.services.operations.executors import get_executor, load_default_executors
from app.services.operations.restore_facade import (
    CANCELLED_BY_USER,
    RestoreJobFacade,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repository(db):
    repo = Repository(
        name="nas", path="/repo/nas", borg_version=1, repository_type="local"
    )
    db.add(repo)
    db.commit()
    return repo


class FakeContext:
    """The slice of OperationContext an executor uses, matching the shape
    `tests/unit/test_operations_phase6_executors.py` established."""

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


def _operation(db, repository, params=None):
    op = Operation(
        repository_id=repository.id if repository is not None else None,
        kind="restore",
        category="restore",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params
        or {
            "archive_name": "nas-2026-09-08",
            "paths": ["docs/"],
            "restore_layout": "contents_only",
            "path_metadata": [{"path": "docs/", "type": "directory"}],
        },
    )
    db.add(op)
    db.flush()
    details = restore_details(db, op)
    details.archive = "nas-2026-09-08"
    details.destination = "/restore/target"
    details.destination_type = "local"
    details.repository_type = "local"
    db.commit()
    return op


@pytest.mark.asyncio
async def test_run_restore_passes_the_details_and_params_to_the_service(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(db, repository)
    seen = {}

    async def _execute_restore(job_id, repository_path, archive, destination, paths, **kw):
        seen.update(
            job_id=job_id,
            repository_path=repository_path,
            archive=archive,
            destination=destination,
            paths=paths,
            **kw,
        )
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        job.nfiles = 4
        job.restored_size = 2048
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "completed"
    assert outcome.result == {"nfiles": 4, "restored_size": 2048}
    assert seen == {
        "job_id": op.id,
        "repository_path": "/repo/nas",
        "archive": "nas-2026-09-08",
        "destination": "/restore/target",
        "paths": ["docs/"],
        "repository_type": "local",
        "destination_type": "local",
        "destination_connection_id": None,
        "ssh_connection_id": None,
        "restore_layout": "contents_only",
        "path_metadata": [{"path": "docs/", "type": "directory"}],
    }


@pytest.mark.asyncio
async def test_run_restore_skips_when_the_repository_is_gone(db, repository):
    load_default_executors()
    op = _operation(db, repository)
    op.repository_id = None
    db.commit()

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"


@pytest.mark.asyncio
async def test_run_restore_reports_a_failure_the_service_wrote(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(db, repository)

    async def _execute_restore(job_id, *args, **kw):
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = '{"key": "backend.errors.service.restoreFailed"}'
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "failed"
    assert outcome.error_message == '{"key": "backend.errors.service.restoreFailed"}'


@pytest.mark.asyncio
async def test_run_restore_fails_when_the_service_returns_without_a_verdict(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(db, repository)

    async def _execute_restore(*args, **kw):
        return None

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "failed"
    assert outcome.error_message == "restore returned no result"


@pytest.mark.asyncio
async def test_run_restore_keeps_cancelled_over_the_killed_process_failure(
    db, repository, monkeypatch
):
    """The cancel route raises the runner's flag, kills the process, and
    writes `cancelled`; the service's read loop then sees the non-zero exit
    and writes `failed`. Whichever lands last, the executor answers for the
    flag (spec 7.7)."""
    load_default_executors()
    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def _execute_restore(job_id, *args, **kw):
        ctx._cancelled = True
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = '{"key": "backend.errors.service.restoreFailedExitCode"}'
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(ctx)

    assert db.get(Operation, op.id).status == "cancelled"
    assert outcome.status == "failed"
    assert outcome.error_message == CANCELLED_BY_USER


@pytest.mark.asyncio
async def test_run_restore_keeps_the_cancel_message_the_route_wrote(
    db, repository, monkeypatch
):
    from app.services.operations.restore_facade import CANCELLED_PROCESS_NOT_FOUND

    load_default_executors()
    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def _execute_restore(job_id, *args, **kw):
        ctx._cancelled = True
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "cancelled"
        job.error_message = CANCELLED_PROCESS_NOT_FOUND
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(ctx)

    assert outcome.error_message == CANCELLED_PROCESS_NOT_FOUND
```

In the two cancel tests the fake flips the flag on the very context object
the executor reads, which is why `ctx` is built once and passed in.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_restore_executor.py -v`
Expected: FAIL, `get_executor("restore")` returns `None` so the call raises
`TypeError: 'NoneType' object is not callable`.

- [x] **Step 3: Write the executor**

Create `app/services/operations/executors/restore.py`:

```python
"""The restore executor (spec 6.3, section 13 phase 7).

A thin shell in the shape phase 5's maintenance executors established: the
work stays in `restore_service.execute_restore`, which drives the row through
`RestoreJobFacade` down whichever of its three paths applies (local
destination, SSH destination over SSHFS, managed agent); the shell loads the
repository, hands the service the inputs the details row and `params` carry,
watches the runner's cancel flag, and turns the row's final status into an
`Outcome`.

Restore is not exclusive (spec 6.3, Appendix B) and the legacy service took no
repository lock, so neither does this shell.
"""

import asyncio

import structlog

from app.database.models import Operation, Repository
from app.services.operations import executors
from app.services.operations.executors.maintenance import cancel_watcher
from app.services.operations.restore_facade import (
    CANCEL_MESSAGES,
    CANCELLED_BY_USER,
    RestoreJobFacade,
)
from app.services.operations.runner import Outcome
from app.utils.restore_layout import RESTORE_LAYOUT_PRESERVE_PATH

logger = structlog.get_logger()

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


async def run_restore(ctx) -> Outcome:
    from app.services.restore_service import restore_service

    repository = (
        ctx.db.get(Repository, ctx.repository_id)
        if ctx.repository_id is not None
        else None
    )
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    job = RestoreJobFacade(ctx.db, ctx.db.get(Operation, ctx.operation_id))
    params = ctx.params
    watcher = asyncio.create_task(cancel_watcher(ctx, restore_service.cancel_restore))
    try:
        await restore_service.execute_restore(
            ctx.operation_id,
            repository.path,
            job.archive,
            job.destination,
            list(params.get("paths") or []),
            repository_type=job.repository_type or repository.repository_type,
            destination_type=job.destination_type or "local",
            destination_connection_id=job.destination_connection_id,
            ssh_connection_id=(
                repository.connection_id if repository.repository_type == "ssh" else None
            ),
            restore_layout=params.get("restore_layout") or RESTORE_LAYOUT_PRESERVE_PATH,
            path_metadata=list(params.get("path_metadata") or []),
        )
    finally:
        watcher.cancel()

    # The service ran in its own session and committed there. Expire this one
    # so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = RestoreJobFacade(ctx.db, operation)

    if ctx.cancelled():
        # The cancel route killed the process and wrote `cancelled`; the
        # service's read loop may have written `failed` for the killed process
        # after that. The flag is the truth (spec 7.7): restore the verdict
        # and the message the route chose, and let the runner keep it.
        operation.status = "cancelled"
        if operation.error_message not in CANCEL_MESSAGES:
            operation.error_message = CANCELLED_BY_USER
        ctx.db.commit()
        return Outcome(status="failed", error_message=operation.error_message)

    status = operation.status
    if status not in _TERMINAL:
        # Still running means the service returned without recording a
        # verdict, which is a bug in the service, not a success.
        return Outcome(
            status="failed",
            error_message=job.error_message or "restore returned no result",
        )
    if status in ("completed", "completed_with_warnings"):
        return Outcome(
            status=status,
            result={"nfiles": job.nfiles or 0, "restored_size": job.restored_size or 0},
        )
    # `Outcome` has no cancelled status (spec 6.3 gives that to the row, not to
    # the executor's verdict); a row the service itself marked cancelled (an
    # agent that reported `canceled`) reaches the runner as a failure shape
    # with the row already saying cancelled, and the runner keeps the row.
    return Outcome(status="failed", error_message=job.error_message)


executors.register("restore", run_restore)
```

The runner's final write (`runner.py:462-470`) keeps `cancelled` whenever the
row already says so, which is why the executor writes the status itself
before returning the failure shape.

- [x] **Step 4: Register it**

In `app/services/operations/executors/__init__.py`, add `restore` to the
import list in `load_default_executors` (alphabetical, between `rclone` and
`wipe`).

- [x] **Step 5: Run the executor tests and the runner's**

Run: `pytest tests/unit/test_operations_restore_executor.py tests/unit/test_operations_runner.py tests/unit/test_operations_phase6_executors.py -v`
Expected: PASS.

---

## Task 6: Activity, connection deletion, retention, and the legacy sweeps

**Files:**
- Modify: `app/api/activity.py`
- Modify: `app/api/ssh_keys.py`
- Modify: `app/utils/process_utils.py:691-693` (comment only)
- Modify: `app/services/repository_wipe_service.py:238` (comment only)
- Test: `tests/unit/test_api_activity.py`, `tests/unit/test_api_ssh_keys.py`,
  `tests/unit/test_job_history_retention.py`

**Interfaces:**
- Consumes: `RestoreJobFacade`, `restore_details` (Tasks 1 and 2);
  `_is_operation_only_kind`, `_get_operation_or_404`,
  `_operation_log_sources`, `_PHASE6_LEGACY_MODELS` (phase 6).
- Produces: `/api/activity/recent?job_type=restore` lists restore operations
  beside pre-phase-7 rows; `/api/activity/restore/{id}/logs`,
  `/logs/download`, and `DELETE /api/activity/restore/{id}` resolve an
  operation first and a legacy row second.

- [x] **Step 1: Write the failing tests**

In `tests/unit/test_api_activity.py`, add beside
`test_failed_restore_visible_under_all_policies`:

```python
    def test_restore_operation_appears_in_activity_with_its_archive_and_log(
        self, test_client, admin_headers, test_db, tmp_path
    ):
        from app.database.models import Operation
        from app.services.operations.details import restore_details

        _set_log_save_policy(test_db, "all_jobs")
        repo = _create_activity_repository(test_db, "Restore Ops")
        log_path = tmp_path / "operation_restore.log"
        log_path.write_text("STDOUT:\nrestored\n\nSTDERR:\n(no output)")
        op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="completed",
            trigger="manual",
            priority=0,
            run_id="run-activity",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=str(log_path),
            params={"archive_name": "archive-1"},
        )
        test_db.add(op)
        test_db.flush()
        restore_details(test_db, op).archive = "archive-1"
        test_db.commit()

        response = test_client.get(
            "/api/activity/recent?job_type=restore", headers=admin_headers
        )
        assert response.status_code == 200
        item = next(i for i in response.json() if i["id"] == op.id)
        assert item["type"] == "restore"
        assert item["status"] == "completed"
        assert item["archive_name"] == "archive-1"
        assert item["repository"] == repo.name
        assert item["repository_path"] == repo.path
        assert item["triggered_by"] == "manual"
        assert item["has_logs"] is True

        logs = test_client.get(
            f"/api/activity/restore/{op.id}/logs", headers=admin_headers
        )
        assert logs.status_code == 200
        assert logs.json()["lines"][0]["content"] == "STDOUT:"

    def test_restore_legacy_row_still_serves_logs_after_phase_7(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import RestoreJob

        _set_log_save_policy(test_db, "all_jobs")
        repo = _create_activity_repository(test_db, "Restore Legacy")
        job = RestoreJob(
            repository=repo.path,
            archive="archive-1",
            destination="/restore",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="legacy line 1\nlegacy line 2",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            f"/api/activity/restore/{job.id}/logs", headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["lines"][1]["content"] == "legacy line 2"
```

In `tests/unit/test_api_ssh_keys.py`, in the connection-deletion test that
creates `restore_job` (around line 1218), add a restore operation whose
details row points at the connection and assert it is nulled too:

```python
        from app.database.models import Operation, OperationRestoreDetails
        from app.services.operations.details import restore_details

        restore_op = Operation(
            repository_id=repo.id,
            kind="restore",
            category="restore",
            status="completed",
            trigger="manual",
            priority=0,
            run_id="run-ssh-delete",
        )
        test_db.add(restore_op)
        test_db.flush()
        restore_details(test_db, restore_op).destination_connection_id = conn_id
```

before the existing `test_db.commit()`, capture `restore_op_id =
restore_op.id` beside the other ids, and after the existing `restore_after`
assertions add:

```python
        details_after = test_db.get(OperationRestoreDetails, restore_op_id)
        assert details_after is not None
        assert details_after.destination_connection_id is None
```

(`repo` is created earlier in that test; if it is added after the jobs, move
the operation below it so `repo.id` is set.)

In `tests/unit/test_job_history_retention.py`, extend
`test_deleting_an_operation_takes_its_extension_rows`: add a
`restore` operation through `_phase6_operation` (extend its category
expression to `{"wipe": "maintenance", "restore": "restore"}.get(kind, "mirror")`),
give it a details row with `restore_details(db, op).archive = "a"`, and
assert `db.query(OperationRestoreDetails).count() == 0` after `run_retention`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_api_activity.py -k "restore_operation_appears or legacy_row_still_serves" tests/unit/test_api_ssh_keys.py -k "delete" tests/unit/test_job_history_retention.py -k extension_rows -v`
Expected: the activity operation test FAILS at the logs call (404: `restore`
still resolves only the legacy table on that route); the SSH test FAILS on
the details assertion only if the test database does not enforce foreign
keys (otherwise it passes through `ondelete="SET NULL"`; the explicit update
in Step 4 is still added, matching how the route treats every other table);
the retention test FAILS on the import until Task 1 is in place, then
passes.

- [x] **Step 3: Make `restore` an operation-first kind on the log routes**

In `app/api/activity.py`:

1. Rename `_PHASE6_LEGACY_MODELS` to `_MIGRATED_LEGACY_MODELS`, update its
   comment to "Legacy tables for the kinds phases 6 and 7 migrated", and add
   `"restore": RestoreJob`. Update the one reference in
   `_get_operation_or_404`.
2. Remove the `"restore": RestoreJob,` entry from the three `job_models`
   dicts in `get_job_logs` (`:1281`), `download_job_logs` (`:1606`), and
   `delete_job` (`:1820`). With it gone, `_is_operation_only_kind("restore",
   ...)` is true and the operation-first branch handles both shapes: an
   operation reads its log file, a legacy row reads its `logs` column
   through `_read_operation_log`'s fallback.
3. Leave the legacy `RestoreJob` query in `list_recent_activity` (`:828-862`)
   in place with this comment above it:

```python
    # Restore rows written before phase 7 moved restore to `operations`. New
    # restores come through _operation_activity_items; this query is empty
    # once retention has dropped the last legacy row and goes away with the
    # table in phase 9.
```

The `_apply_legacy_activity_shape` helper needs no restore branch:
`serialize_operation` already reads `archive_name` from `params`, the trigger
is always `manual`, and `has_logs` is judged from the log file.

- [x] **Step 4: Null the details row on connection deletion**

In `app/api/ssh_keys.py`, after the `RestoreJob` update at `:2389-2391`:

```python
        db.query(OperationRestoreDetails).filter(
            OperationRestoreDetails.destination_connection_id == connection_id
        ).update({"destination_connection_id": None}, synchronize_session=False)
```

and add `OperationRestoreDetails` to the models import.

- [x] **Step 5: Mark the two legacy sweeps**

In `app/utils/process_utils.py`, replace the comment at `:693` with:

```python
        # Rows written before phase 7 moved restore to `operations`. New
        # restores are recovered by OperationRunner.recover_on_startup (spec
        # 7.6), which fails them the same way: a restore records no pid to
        # reattach to. Empty after the first restart past the upgrade; goes
        # away with the table in phase 9.
```

In `app/services/repository_wipe_service.py`, above the `RestoreJob` query at
`:238`, add:

```python
        # Pre-phase-7 restore rows; new restores are `restore` operations and
        # already counted in CONFLICTING_KINDS above.
```

- [x] **Step 6: Run the tests**

Run: `pytest tests/unit/test_api_activity.py tests/unit/test_api_ssh_keys.py tests/unit/test_job_history_retention.py tests/unit/test_process_utils.py tests/unit/test_repository_wipe_service.py -v`
Expected: PASS.

---

## Task 7: Documentation

**Files:**
- Modify: `docs/architecture/job-system.md` (sections "Restore Jobs" at
  `:59`, "Restart Cleanup" at `:144`, "Concurrency" at `:217`)
- Modify: `docs/api.md` (after "Repository wipe, cloud mirror, and package
  install jobs" at `:185`)

- [x] **Step 1: Rewrite the restore section of `job-system.md`**

Replace the "Restore Jobs" section body with:

```markdown
## Restore Jobs

As of section 13 phase 7 of the operations spec, a restore is a row in the
`operations` table (kind `restore`, category `restore`) with its restore
columns on `operation_restore_details`: archive, destination, destination
type and SSH connection, repository type, and the live byte and file counts.
`POST /api/restore/start` enqueues the row; the operations runner dispatches
it. Restore is not exclusive (Borg allows concurrent reads), so it runs
beside a backup or check on the same repository rather than waiting for the
lane, exactly as it did before the migration.

The restore service keeps its three execution paths and drives the row
through a facade that presents the legacy attribute surface:

- local destination: `borg extract` in the container, progress parsed from
  `--log-json`
- SSH destination: the destination is mounted over SSHFS and extracted into
  directly
- managed-agent repository: a `repository.restore` agent job is queued and
  its progress mirrored onto the operation

Cancelling a running restore (`POST /api/restore/cancel/{id}`) raises the
runner's cancel flag, terminates the extract process (or asks the agent to
cancel), and marks the row `cancelled`; the executor keeps that verdict even
when the service records the killed process's exit afterwards.

Restore logs are the operation's log file, written once at the end from the
captured output. Rows written before phase 7 stay in `restore_jobs` and are
served by the same routes until retention drops them; the table is deleted
in phase 9.

Notifications can be sent for restore success or failure.
```

- [x] **Step 2: Update the restart cleanup list**

In "Restart Cleanup", change the "Startup cleanup currently covers" list
entry `- restore jobs` to:

```markdown
- restore rows in their legacy table, written by an install that has not
  restarted since upgrading to phase 7
```

change the sentence "Check, prune, compact, and restore-check now run as
operations" to "Check, prune, compact, restore-check, and restore now run as
operations", and change the "What happens" entry `- running restore jobs are
marked \`failed\`` to `- running legacy restore rows are marked \`failed\``.

- [x] **Step 3: Add the API note**

In `docs/api.md`, after the wipe section's last paragraph, add:

```markdown
## Restore jobs

As of section 13 phase 7 a restore is an `operations` row as well.
`POST /api/restore/start` still answers `{"job_id", "status": "pending",
"message"}`; the id is now an operations row id. `GET /api/restore/jobs`,
`GET /api/restore/status/{id}`, and `POST /api/restore/cancel/{id}` keep
their bodies and status words, serve operations first, and fall back to the
pre-phase-7 row for that id. `progress_details.estimated_time_remaining` is
computed from the sizes and the speed rather than stored. The restore's
logs are its operation log file, readable through
`GET /api/activity/restore/{id}/logs` as before.
```

- [x] **Step 4: Check the docs for em dashes**

Run: `git diff -U0 -- docs | grep "^+" | grep -c $'\xe2\x80\x94'` (the bytes of an em dash; macOS grep has no `-P`)
Expected: `0`.

---

## Verification (before gate G2)

Run `superpowers:verification-before-completion`, then, from the worktree:

1. `pytest tests/unit -p no:randomly -q`. Expected: 0 failed; the count
   grows by the tests this plan adds (about 25). `tests/unit/test_api_auth.py`
   runs clean only without a `.env` in the checkout (see the memory note on
   `PUBLIC_BASE_URL`).
2. `ruff check app tests && ruff format --check app tests`. Expected: clean.
3. `git diff -U0 origin/main | grep "^+" | grep -c $'\xe2\x80\x94'`. Expected: `0`.
4. `git diff --stat origin/main -- frontend`. Expected: empty.
5. `grep -rn "RestoreJob(" app/`. Expected: no output.
6. `alembic heads` from the repository root. Expected: exactly one head,
   `f7a8b9c0d1e2`.
7. `pytest tests/integration -q` and compare with the same command run on
   `origin/main` with this branch's changes stashed. Expected: the same
   failures on both (phase 6 recorded three pre-existing failures and
   fifteen errors there), none new.

## Open questions

Defaults are what the plan implements; G1 can change any of them.

1. **`original_size` on the extension table.** Spec 6.2's restore column
   list drops `original_size`, but it is the divisor for the percentage and
   the ETA and cannot live in `operations.progress_total` (an Integer column
   that overflows at 2 GiB on PostgreSQL, which `app/config.py` supports).
   Default: add `original_size BigInteger` to `operation_restore_details`
   and record the deviation in Appendix B at G1.
2. **`estimated_time_remaining` is derived, not stored.** The service
   computes it from `original_size`, `restored_size`, and `restore_speed`
   and assigns the result; the facade reproduces the arithmetic on read and
   drops the write. One visible difference: a completed restore answers 0
   where the legacy row kept the last in-flight estimate. Default: derive.
3. **No repository lock around the extract.** The legacy service took none,
   spec 6.3 and Appendix B make restore non-exclusive, and spec 7.2's
   "executors also wrap Borg calls in the metadata lock" would queue a
   restore behind every `borg info` and `list`. Default: no lock, matching
   today.
4. **Prometheus metrics stay on the legacy table.** `borg_restore_jobs_total`
   and the active-restore gauge in `app/api/metrics.py` read `restore_jobs`,
   as the phase 5 and 6 kinds' metrics still read theirs. Default: leave
   for phase 9, which rewrites Activity and metrics over `operations`, and
   note it in the phase's spec row.
5. **Admission refusals on agent restores stay failures.** The service
   catches the 409 from `queue_agent_repository_operation_job` and marks
   the row failed, as before; spec 7.1's deferral would need the exception
   to reach the runner. Default: keep the legacy outcome; a deferral is a
   behaviour change section 13 rules out for these phases.
6. **`archive_name` in `params` as well as `archive` on the details row.**
   `serialize_operation` reads `params["archive_name"]` on every operations
   route (board, per-repository view, `/api/operations/{id}`) and the
   `restore_check` and `delete_archive` kinds already use that key.
   Default: write both.
7. **`current_file` mirrored into `progress_message`.** The Background work
   board shows `progress_message` under a running row; without the mirror a
   restore shows a percentage and nothing else. Default: mirror.
