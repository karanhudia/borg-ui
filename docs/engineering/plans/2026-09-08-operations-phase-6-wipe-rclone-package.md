# Operations Phase 6: Wipe, Rclone Sync, and Package Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit at the
> end of a task; the phase has one commit gate (G2) at the end, per section
> 19.4 of the spec and `.claude/instructions.md`.

**Goal:** Move repository wipe, rclone mirror sync (and hydrate), and package
install off `repository_wipe_jobs`, `rclone_sync_jobs`, and
`package_install_jobs` onto `operations` plus the two extension tables spec 6.2
names, so all three appear in the Background work board and the Activity union,
wipe queues behind the repository lane instead of being rejected with a 409,
and the wipe follow-up chain (spec 7.4) replaces the `update_stats()` call the
wipe service makes for itself.

**Architecture:** Phase 5's pattern, repeated three times. Each kind keeps its
service body and changes what a job id resolves to: a per-kind facade wraps an
`Operation` (plus its extension row) in the legacy attribute surface that
service and its serializers already read, and `resolve_<kind>_job(db, job_id)`
returns the facade for new work or the real legacy row for a pre-phase-6 id.
Each kind gains a thin executor under `app/services/operations/executors/` that
loads the repository, calls the existing service, and turns the row's final
status into an `Outcome`. Two extension tables (`operation_wipe_details`,
`operation_rclone_details`) arrive in one Alembic revision; `package_install`
gets none, per spec 6.2, and carries `package_id` in `operations.params` with
its captured output in the operation's log file.

**Tech Stack:** FastAPI, SQLAlchemy 1.x declarative models, Alembic, asyncio
subprocess handling in the existing services, `BorgRouter` for the v1/v2/agent
split, pytest with the `test_db` / `test_client` / `admin_headers` fixtures
from `tests/fixtures/api.py` and the in-memory `db` fixture pattern from
`tests/unit/test_operations_job_facade.py`. No new dependencies.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
(sections 6.1, 6.2, 6.3, 7.1 to 7.8, 9.1, 9.3, 13, 19, Appendix A.2,
Appendix B).

## Model

Section 13 gives phase 6 one implement model, Sonnet 5, and Opus 5 as the
reviewer: "Contained kinds with their own services. Wipe's confirm workflow
needs care but is well tested today." This plan was drafted on Opus 5 at the
owner's choice at gate G0 on 2026-09-08, the same deviation phase 4 recorded.

## Global Constraints

- Phase 6 is backend only. No frontend file changes, no i18n keys, no
  stories. Every HTTP response body keeps the exact shape and the exact
  status vocabulary it has today, per section 13: "Phases 5 through 9 are
  internal refactors with no visible change except fewer lock errors."
  Three contracts are load-bearing and pinned by tests in this phase:
  `status` values `completed_compaction_failed` and `failed_partial` on the
  wipe job (`frontend/src/components/RepositoryWipeDialog.tsx:54-72`),
  `triggered_by: "initial"` on a cloud mirror job
  (`frontend/src/components/RunningCloudStorageJobsSection.tsx:31`), and
  `stdout` / `stderr` / `exit_code` on `GET /api/packages/jobs/{id}`.
- Spec 6.2 is verbatim. `operation_wipe_details` and `operation_rclone_details`
  carry exactly the columns it lists, one row per operation, keyed on
  `operations.id` with `ondelete="CASCADE"`. `package_install` gets no
  extension table: `package_id` goes in `operations.params`, `exit_code` in
  `operations.result`, and the captured output in the operation's log file.
- Spec 6.3 is verbatim for kind, category, exclusivity, trigger, and
  priority. `wipe` is category `maintenance` and exclusive; `rclone_sync` is
  category `mirror`, not exclusive, and uses the `rclone` lock scope instead
  of the lane (spec 7.2); `package_install` is category `system` with a null
  `repository_id`. Do not edit `vocab.py`; it already carries all three.
- Spec 7.4's chain table is verbatim and already in `followups.py`: `wipe`
  gets `archive_sync`, `history_merge`, `stats`; `rclone_sync` and
  `package_install` get none. Do not edit `followups.py`.
- Trigger mapping is fixed. Wipe is always `manual` (a person types the
  confirmation phrase). Rclone sync is `manual` for a button or an
  in-request sync, `schedule` for the mirror scheduler, and `import` for the
  initial sync queued when a cloud repository is created, which is the one
  and only `import`-trigger rclone operation and is what the
  `triggered_by: "initial"` contract round-trips through. Package install is
  always `manual`.
- Nothing in this phase writes a new row to `repository_wipe_jobs` (except
  the preview, see Task 2), `rclone_sync_jobs`, or `package_install_jobs`.
  All three tables stay in the schema with their historical rows; phase 9
  deletes them.
- No em dashes anywhere: code comments, docstrings, docs, or commit message.
  Check added lines only, with `git diff -U0`.
- One commit at the end of the phase, at gate G2, after
  `superpowers:verification-before-completion` passes. Nothing is pushed
  without the owner's answer at that gate.

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `app/database/alembic/versions/e5f6a7b8c9d0_add_operation_wipe_and_rclone_details.py` | The one migration: both extension tables. |
| `app/services/operations/details.py` | `wipe_details(db, operation)` and `rclone_details(db, operation)`: get-or-create the extension row for an operation. |
| `app/services/operations/wipe_facade.py` | `WipeJobFacade`, `resolve_wipe_job`, `active_wipe_operation`. |
| `app/services/operations/rclone_facade.py` | `RcloneSyncFacade`, `resolve_rclone_job`, `rclone_activity_type`. |
| `app/services/operations/package_facade.py` | `PackageInstallFacade`, `resolve_package_job`, `active_package_install`, the log file format and its parser. |
| `app/services/operations/executors/wipe.py` | `run_wipe`. |
| `app/services/operations/executors/rclone.py` | `run_rclone_sync`. |
| `app/services/operations/executors/package.py` | `run_package_install`. |
| `tests/unit/test_operations_details.py` | Extension tables, cascade, get-or-create. |
| `tests/unit/test_operations_wipe_facade.py` | Wipe facade and its status round trip. |
| `tests/unit/test_operations_rclone_facade.py` | Rclone facade and the `initial` trigger round trip. |
| `tests/unit/test_operations_package_facade.py` | Package facade and the log file round trip. |
| `tests/unit/test_operations_phase6_executors.py` | The three executors. |

**Modified**

| File | Change |
| --- | --- |
| `app/database/models.py` | `OperationWipeDetails`, `OperationRcloneDetails`. |
| `app/services/operations/executors/__init__.py` | Register the three new modules in `load_default_executors`. |
| `app/services/repository_wipe_service.py` | Resolve through the facade; conflict check reads `operations`; drop the self-made `update_stats`. |
| `app/api/repositories.py` | Wipe confirm enqueues; wipe read/cancel routes resolve either id space; the running-jobs summary and the rclone status payload read operations; the initial cloud mirror sync enqueues instead of spawning a task. |
| `app/services/rclone_repository_service.py` | `sync_repository` and `hydrate_repository` drive an operation. |
| `app/services/rclone_mirror_scheduler.py` | Enqueue instead of spawning tasks. |
| `app/services/package_service.py` | Enqueue-only start; the install body drives an operation. |
| `app/api/packages.py` | Duplicate check, job status, and job list over operations with a legacy fallback. |
| `app/api/activity.py` | Package and rclone log routes resolve operations first; `_operation_activity_items` labels a hydrate row `rclone_hydrate`. |
| `app/services/job_admission.py` | The wipe branch reads operations. |
| `app/services/job_history_retention.py` | Extension-row log columns cleared at `log_retention_days`. |
| `app/services/log_manager.py` | Protect running operation logs. |
| `app/main.py` | Resume interrupted initial mirror syncs as operations, before recovery. |
| `app/scripts/startup_packages.py` | The in-flight check reads `operations`. |
| `docs/architecture/job-system.md`, `docs/api.md` | Task 8. |

---

## Task 1: Extension tables and the details helper

**Files:**
- Create: `app/database/alembic/versions/e5f6a7b8c9d0_add_operation_wipe_and_rclone_details.py`
- Create: `app/services/operations/details.py`
- Modify: `app/database/models.py` (after `class Operation`)
- Test: `tests/unit/test_operations_details.py`

**Interfaces:**
- Consumes: `Operation` from `app/database/models.py` (phase 1).
- Produces: `OperationWipeDetails`, `OperationRcloneDetails`;
  `details.wipe_details(db: Session, operation: Operation) -> OperationWipeDetails`
  and `details.rclone_details(db: Session, operation: Operation) -> OperationRcloneDetails`,
  both get-or-create, both flushing so the row is readable in the same
  transaction. Tasks 2 to 5 use only these two functions; no other module
  constructs an extension row.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_operations_details.py`:

```python
"""Phase 6: the two extension tables spec 6.2 names for wipe and rclone."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Operation,
    OperationRcloneDetails,
    OperationWipeDetails,
    Repository,
)
from app.services.operations.details import rclone_details, wipe_details


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


def _operation(db, repository, kind):
    op = Operation(
        repository_id=repository.id,
        kind=kind,
        category="maintenance" if kind == "wipe" else "mirror",
        status="queued",
        trigger="manual",
        priority=0,
        run_id="run-1",
    )
    db.add(op)
    db.commit()
    return op


def test_wipe_details_is_created_once_per_operation(db, repository):
    op = _operation(db, repository, "wipe")

    first = wipe_details(db, op)
    first.archive_count = 3
    second = wipe_details(db, op)

    assert first.operation_id == op.id
    assert second is first
    assert second.archive_count == 3
    assert db.query(OperationWipeDetails).count() == 1


def test_rclone_details_is_created_once_per_operation(db, repository):
    op = _operation(db, repository, "rclone_sync")

    first = rclone_details(db, op)
    first.direction = "cache_to_remote"
    first.operation = "sync"
    db.commit()

    assert rclone_details(db, op).direction == "cache_to_remote"
    assert db.query(OperationRcloneDetails).count() == 1


def test_details_rows_are_deleted_with_their_operation(db, repository):
    wipe_op = _operation(db, repository, "wipe")
    rclone_op = _operation(db, repository, "rclone_sync")
    wipe_details(db, wipe_op)
    rclone_details(db, rclone_op)
    db.commit()

    db.delete(wipe_op)
    db.delete(rclone_op)
    db.commit()

    assert db.query(OperationWipeDetails).count() == 0
    assert db.query(OperationRcloneDetails).count() == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_operations_details.py -v`
Expected: FAIL, `ImportError: cannot import name 'OperationWipeDetails'`.

- [ ] **Step 3: Add the two models**

In `app/database/models.py`, directly after `class Operation` (which ends with
its `__table_args__` index tuple) and before `class Archive`:

```python
class OperationWipeDetails(Base):
    """Wipe-specific columns for an `operations` row. Spec section 6.2."""

    __tablename__ = "operation_wipe_details"

    operation_id = Column(
        Integer,
        ForeignKey("operations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    phase = Column(String, nullable=True)
    archive_count = Column(Integer, default=0)
    archive_fingerprint = Column(String, nullable=True)
    archive_manifest_json = Column(Text, nullable=True)
    dry_run_output = Column(Text, nullable=True)
    blocking_reason = Column(String, nullable=True)
    protected_archives_json = Column(Text, nullable=True)
    run_compact = Column(Boolean, default=True, nullable=False)
    requested_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at = Column(DateTime, nullable=True)


class OperationRcloneDetails(Base):
    """Rclone-specific columns for an `operations` row. Spec section 6.2.
    The legacy `log_path` is not here: an operation's log lives in
    `operations.log_file_path` (spec 6.1)."""

    __tablename__ = "operation_rclone_details"

    operation_id = Column(
        Integer,
        ForeignKey("operations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    direction = Column(String, nullable=True)
    operation = Column(String, default="sync", nullable=False)
    scheduled_for = Column(DateTime, nullable=True)
    bytes_transferred = Column(BigInteger, nullable=True)
    files_transferred = Column(Integer, nullable=True)
    log_text = Column(Text, nullable=True)
    error_text = Column(Text, nullable=True)
```

- [ ] **Step 4: Write the details helper**

Create `app/services/operations/details.py`:

```python
"""Get-or-create the spec 6.2 extension row for an operation.

Only wipe and rclone sync have one in this phase. The row is flushed, not
committed, so a caller composing several writes keeps one transaction.
"""

from sqlalchemy.orm import Session

from app.database.models import (
    Operation,
    OperationRcloneDetails,
    OperationWipeDetails,
)


def _get_or_create(db: Session, model, operation: Operation):
    row = db.get(model, operation.id)
    if row is None:
        row = model(operation_id=operation.id)
        db.add(row)
        db.flush()
    return row


def wipe_details(db: Session, operation: Operation) -> OperationWipeDetails:
    return _get_or_create(db, OperationWipeDetails, operation)


def rclone_details(db: Session, operation: Operation) -> OperationRcloneDetails:
    return _get_or_create(db, OperationRcloneDetails, operation)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/unit/test_operations_details.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Write the migration**

Create
`app/database/alembic/versions/e5f6a7b8c9d0_add_operation_wipe_and_rclone_details.py`:

```python
"""add operation wipe and rclone extension tables

Revision ID: e5f6a7b8c9d0
Revises: c3d5e7f9a1b2
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_wipe_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("phase", sa.String(), nullable=True),
        sa.Column("archive_count", sa.Integer(), nullable=True),
        sa.Column("archive_fingerprint", sa.String(), nullable=True),
        sa.Column("archive_manifest_json", sa.Text(), nullable=True),
        sa.Column("dry_run_output", sa.Text(), nullable=True),
        sa.Column("blocking_reason", sa.String(), nullable=True),
        sa.Column("protected_archives_json", sa.Text(), nullable=True),
        sa.Column("run_compact", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "confirmed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "operation_rclone_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("direction", sa.String(), nullable=True),
        sa.Column("operation", sa.String(), nullable=False, server_default="sync"),
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),
        sa.Column("bytes_transferred", sa.BigInteger(), nullable=True),
        sa.Column("files_transferred", sa.Integer(), nullable=True),
        sa.Column("log_text", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("operation_rclone_details")
    op.drop_table("operation_wipe_details")
```

- [ ] **Step 7: Verify the migration applies and is the single head**

Run:
```bash
python -c "
import re, glob, os
revs, downs = {}, set()
for f in glob.glob('app/database/alembic/versions/*.py'):
    s = open(f).read()
    r = re.search(r\"^revision(?::\s*str)?\s*=\s*['\\\"]([^'\\\"]+)\", s, re.M)
    d = re.search(r\"^down_revision(?::[^=]*)?\s*=\s*['\\\"]?([^'\\\"\n]+)\", s, re.M)
    if r: revs[r.group(1)] = os.path.basename(f)
    if d: downs.add(d.group(1).strip())
print('heads:', [h for h in revs if h not in downs])
"
```
Expected: `heads: ['e5f6a7b8c9d0']` and nothing else.

Then apply it against a scratch SQLite database:
```bash
BORG_UI_DATA_DIR=/tmp/phase6-migration alembic -c app/database/alembic.ini upgrade head
```
Expected: exit 0. If the repository's usual invocation differs, follow
`docs/development.md`; do not invent one.

- [ ] **Step 8: Run the touched suites**

Run: `pytest tests/unit/test_operations_details.py tests/unit/test_database_operations.py tests/unit/test_job_history_retention.py -v`
Expected: PASS. Retention already deletes `Operation` rows; the cascade means
the extension rows go with them, which Task 7 pins with its own test.

---

## Task 2: Wipe, the write path

**Files:**
- Create: `app/services/operations/wipe_facade.py`
- Create: `app/services/operations/executors/wipe.py`
- Modify: `app/services/operations/executors/__init__.py`
- Modify: `app/services/repository_wipe_service.py:283-470` (`start_execution`,
  `execute_wipe`, `_best_effort_post_wipe_refresh`)
- Modify: `app/api/repositories.py:5644-5682` (`execute_repository_wipe`)
- Test: `tests/unit/test_operations_wipe_facade.py`,
  `tests/unit/test_operations_phase6_executors.py`,
  `tests/unit/test_repository_wipe_service.py`

**Interfaces:**
- Consumes: `details.wipe_details` (Task 1); `enqueue()` from
  `app/services/operations/enqueue.py`; `Outcome` and `operation_log_path`
  from `app/services/operations/runner.py`.
- Produces:
  - `WipeJobFacade(db, operation)`: the legacy `RepositoryWipeJob` attribute
    surface over an operation and its details row.
  - `resolve_wipe_job(db, job_id) -> WipeJobFacade | RepositoryWipeJob | None`.
  - `active_wipe_operation(db, repository_id) -> Operation | RepositoryWipeJob | None`
    for `queued`/`running` work, with the legacy fallback.
  - `run_wipe(ctx) -> Outcome`, registered for kind `wipe`.

**Design notes the implementer must not re-derive:**

1. **The preview stays in `repository_wipe_jobs`.** A preview is not a unit of
   work: it has no status in spec 6.3's enum (`previewed` is not one), and a
   `queued` operation would be dispatched by the runner the moment it was
   written. `create_preview` is therefore untouched by this phase. Confirming
   the preview creates the `Operation` and copies the preview snapshot into
   `operation_wipe_details`. See Open question 1.
2. **A preview is consumed when an operation's `params["preview_id"]` names
   it.** That is the replacement for today's `preview.status != "previewed"`
   freshness gate, and it needs no new word in the legacy status vocabulary.
   `preview_id` lives in `params`, not in the details row, because spec 6.2
   fixes that table's columns and `params` is where kind-specific input goes.
3. **Status round trip.** The frontend switches on
   `completed_compaction_failed` and `failed_partial`, which are not spec 6.3
   statuses. The facade stores them as `completed_with_warnings` and `failed`
   and reconstructs the legacy word from `details.phase`, which the service
   already sets on the same code paths (`compact_failed`, `compact_skipped`,
   `delete_failed`). `failed_partial` needs one new phase word,
   `delete_failed_partial`, written by the same branch that chooses the
   `failed_partial` status.

- [ ] **Step 1: Write the failing facade test**

Create `tests/unit/test_operations_wipe_facade.py`:

```python
"""Phase 6: an `operations` row wearing the legacy wipe-job surface."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, RepositoryWipeJob
from app.services.operations.wipe_facade import (
    WipeJobFacade,
    active_wipe_operation,
    resolve_wipe_job,
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


def _wipe_operation(db, repository, status="queued", params=None):
    op = Operation(
        repository_id=repository.id,
        kind="wipe",
        category="maintenance",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {"preview_id": 7, "run_compact": True},
    )
    db.add(op)
    db.commit()
    return op


def test_queued_operation_reads_as_pending(db, repository):
    job = WipeJobFacade(db, _wipe_operation(db, repository))
    assert job.status == "pending"


def test_compaction_failure_round_trips_through_the_phase(db, repository):
    op = _wipe_operation(db, repository, status="running")
    job = WipeJobFacade(db, op)

    job.phase = "compact_failed"
    job.status = "completed_compaction_failed"
    db.commit()

    assert op.status == "completed_with_warnings"
    assert job.status == "completed_compaction_failed"
    assert WipeJobFacade(db, op).phase == "compact_failed"


def test_partial_delete_failure_round_trips(db, repository):
    op = _wipe_operation(db, repository, status="running")
    job = WipeJobFacade(db, op)

    job.status = "failed_partial"
    db.commit()

    assert op.status == "failed"
    assert job.status == "failed_partial"


def test_compact_skipped_stays_completed_with_warnings(db, repository):
    op = _wipe_operation(db, repository, status="running")
    job = WipeJobFacade(db, op)

    job.phase = "compact_skipped"
    job.status = "completed_with_warnings"
    db.commit()

    assert op.status == "completed_with_warnings"
    assert job.status == "completed_with_warnings"


def test_preview_snapshot_reads_from_the_details_row(db, repository):
    op = _wipe_operation(db, repository)
    job = WipeJobFacade(db, op)

    job.archive_count = 4
    job.archive_fingerprint = "sha256:abc"
    job.run_compact = False
    db.commit()

    reread = WipeJobFacade(db, db.get(Operation, op.id))
    assert reread.archive_count == 4
    assert reread.archive_fingerprint == "sha256:abc"
    assert reread.run_compact is False


def test_resolve_prefers_operations_then_falls_back_to_the_legacy_row(db, repository):
    op = _wipe_operation(db, repository)
    legacy = RepositoryWipeJob(repository_id=repository.id, status="previewed")
    db.add(legacy)
    db.commit()

    assert isinstance(resolve_wipe_job(db, op.id), WipeJobFacade)
    assert resolve_wipe_job(db, legacy.id) is not None
    assert resolve_wipe_job(db, 9999) is None


def test_active_wipe_operation_sees_queued_work_and_legacy_running_rows(db, repository):
    assert active_wipe_operation(db, repository.id) is None

    op = _wipe_operation(db, repository)
    assert active_wipe_operation(db, repository.id) is op

    op.status = "completed"
    db.commit()
    legacy = RepositoryWipeJob(repository_id=repository.id, status="running")
    db.add(legacy)
    db.commit()
    assert active_wipe_operation(db, repository.id) is legacy
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_operations_wipe_facade.py -v`
Expected: FAIL, `ModuleNotFoundError: app.services.operations.wipe_facade`.

- [ ] **Step 3: Write the facade**

Create `app/services/operations/wipe_facade.py`:

```python
"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
repository-wipe attribute surface.

`repository_wipe_service` and the wipe routes drive a job through a fixed set
of attributes. Phase 6 moves the row to `operations` without rewriting them:
`resolve_wipe_job()` hands them this facade for new work and the real
`RepositoryWipeJob` for an id written before this phase.

Two wipe statuses do not exist in spec 6.3 and the frontend switches on both,
so they are stored as their nearest spec status and reconstructed from
`details.phase`:

| legacy status | operation status | phase |
| --- | --- | --- |
| `completed_compaction_failed` | `completed_with_warnings` | `compact_failed` |
| `failed_partial` | `failed` | `delete_failed_partial` |

Deleted in phase 9 with the legacy table.
"""

from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, Repository, RepositoryWipeJob
from app.services.operations.details import wipe_details

ACTIVE_STATUSES = ("queued", "running")
# A pre-phase-6 install can restart mid-run and leave one of these behind.
# Nothing writes them any more; the tuple goes away in phase 9.
_LEGACY_ACTIVE_STATUSES = ("pending", "running")

PHASE_COMPACT_FAILED = "compact_failed"
PHASE_DELETE_FAILED_PARTIAL = "delete_failed_partial"

_TO_OPERATION = {
    "pending": "queued",
    "completed_compaction_failed": "completed_with_warnings",
    "failed_partial": "failed",
}
_PHASE_FOR_STATUS = {
    "completed_compaction_failed": PHASE_COMPACT_FAILED,
    "failed_partial": PHASE_DELETE_FAILED_PARTIAL,
}
_DETAIL_FIELDS = (
    "phase",
    "archive_count",
    "archive_fingerprint",
    "archive_manifest_json",
    "dry_run_output",
    "blocking_reason",
    "protected_archives_json",
    "run_compact",
    "requested_by_user_id",
    "confirmed_by_user_id",
    "confirmed_at",
)


class WipeJobFacade:
    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "_details", wipe_details(db, operation))

    def __setattr__(self, name: str, value) -> None:
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "_details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        # Only reached when normal lookup fails, so every property below wins.
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "_details"), name)
        raise AttributeError(f"wipe operations carry no {name!r}")

    # -- identity ----------------------------------------------------------

    @property
    def id(self) -> int:
        return self.operation.id

    @property
    def repository_id(self) -> Optional[int]:
        return self.operation.repository_id

    @property
    def repository_path(self) -> Optional[str]:
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
        status = self.operation.status
        phase = self._details.phase
        if status == "queued":
            return "pending"
        if status == "completed_with_warnings" and phase == PHASE_COMPACT_FAILED:
            return "completed_compaction_failed"
        if status == "failed" and phase == PHASE_DELETE_FAILED_PARTIAL:
            return "failed_partial"
        return status

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = _TO_OPERATION.get(value, value)
        phase = _PHASE_FOR_STATUS.get(value)
        if phase is not None:
            self._details.phase = phase

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
        """The legacy table kept a truncated text mirror alongside the file.
        The operation keeps only the file, and the service writes that file
        itself, so this is accepted and dropped rather than clobbering it."""
        return None

    @property
    def has_logs(self) -> bool:
        return bool(self.operation.log_file_path)

    @has_logs.setter
    def has_logs(self, value) -> None:
        return None


def resolve_wipe_job(db: Session, job_id: int) -> Any:
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "wipe")
        .first()
    )
    if operation is not None:
        return WipeJobFacade(db, operation)
    return db.query(RepositoryWipeJob).filter(RepositoryWipeJob.id == job_id).first()


def active_wipe_operation(db: Session, repository_id: int) -> Any:
    """Queued or running wipe work on this repository, operations first, then
    a legacy row a pre-phase-6 install left active. A `previewed` legacy row is
    deliberately not active: a preview holds no lock and blocks nothing."""
    operation = (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "wipe",
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Operation.id.desc())
        .first()
    )
    if operation is not None:
        return operation
    return (
        db.query(RepositoryWipeJob)
        .filter(
            RepositoryWipeJob.repository_id == repository_id,
            RepositoryWipeJob.status.in_(_LEGACY_ACTIVE_STATUSES),
        )
        .order_by(RepositoryWipeJob.id.desc())
        .first()
    )
```

- [ ] **Step 4: Run the facade test to verify it passes**

Run: `pytest tests/unit/test_operations_wipe_facade.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Write the failing service test**

Add to `tests/unit/test_repository_wipe_service.py` (it already builds a
repository, a user, and a preview row; follow the file's existing fixtures):

```python
@pytest.mark.asyncio
async def test_start_execution_enqueues_an_operation_and_copies_the_preview(
    db_session, repository, admin_user, monkeypatch
):
    from app.database.models import Operation, OperationWipeDetails
    from app.services.repository_wipe_service import repository_wipe_service

    preview = RepositoryWipeJob(
        repository_id=repository.id,
        status="previewed",
        archive_count=2,
        archive_fingerprint="sha256:abc",
        archive_manifest_json='[{"identity": "a"}, {"identity": "b"}]',
        protected_archives_json="[]",
        run_compact=True,
        requested_by_user_id=admin_user.id,
    )
    db_session.add(preview)
    db_session.commit()

    async def _list_archives(*args, **kwargs):
        return [{"name": "a", "id": "a"}, {"name": "b", "id": "b"}]

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.list_archives", _list_archives
    )
    monkeypatch.setattr(
        "app.services.repository_wipe_service.compute_archive_fingerprint",
        lambda manifest: "sha256:abc",
    )

    job = await repository_wipe_service.start_execution(
        db_session,
        repository,
        admin_user,
        preview_id=preview.id,
        preview_fingerprint="sha256:abc",
        confirmation_phrase=f"WIPE {repository.name}",
        understood=True,
        run_compact=True,
    )

    operation = db_session.query(Operation).filter(Operation.kind == "wipe").one()
    details = db_session.get(OperationWipeDetails, operation.id)
    assert operation.status == "queued"
    assert operation.trigger == "manual"
    assert operation.params["preview_id"] == preview.id
    assert details.archive_fingerprint == "sha256:abc"
    assert details.archive_count == 2
    assert details.confirmed_by_user_id == admin_user.id
    assert details.confirmed_at is not None
    assert job.id == operation.id
    assert job.status == "pending"


@pytest.mark.asyncio
async def test_start_execution_rejects_a_preview_already_consumed(
    db_session, repository, admin_user, monkeypatch
):
    """The freshness gate is the operation that already names this preview,
    not a status word on the preview row."""
    from app.services.repository_wipe_service import (
        WipeValidationError,
        repository_wipe_service,
    )

    ...  # same setup as above, then run start_execution once

    with pytest.raises(WipeValidationError) as excinfo:
        await repository_wipe_service.start_execution(
            db_session,
            repository,
            admin_user,
            preview_id=preview.id,
            preview_fingerprint="sha256:abc",
            confirmation_phrase=f"WIPE {repository.name}",
            understood=True,
            run_compact=True,
        )
    assert excinfo.value.detail_key == "backend.errors.repo.wipePreviewNotFresh"
```

Replace the `...` with the same monkeypatching and preview creation as the
first test, and one `await repository_wipe_service.start_execution(...)` call
before the `pytest.raises` block. Do not leave an ellipsis in the committed
test.

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/unit/test_repository_wipe_service.py -k enqueues -v`
Expected: FAIL, no `Operation` row is written.

- [ ] **Step 7: Migrate `start_execution`**

In `app/services/repository_wipe_service.py`:

- Keep every validation in `start_execution` except the
  `preview.status != "previewed"` check, which becomes a consumed-preview
  check:

```python
        if _preview_already_consumed(db, preview.id):
            raise WipeValidationError(
                "backend.errors.repo.wipePreviewNotFresh", status_code=409
            )
```

with, at module level:

```python
def _preview_already_consumed(db: Session, preview_id: int) -> bool:
    """True once a wipe operation names this preview. Replaces the legacy
    `status != "previewed"` gate: the preview row keeps its own status and the
    operation is the record of the confirmed run."""
    for operation in (
        db.query(Operation).filter(Operation.kind == "wipe").all()
    ):
        if (operation.params or {}).get("preview_id") == preview_id:
            return True
    return False
```

  (A Python-side scan over `params`, matching `active_delete_for_archive`'s
  shape from phase 5: the JSON column is not portably queryable across SQLite
  and PostgreSQL. Wipe rows are rare, so the scan is cheap.)

- Replace the block that mutates `preview` into a pending job with one that
  enqueues an operation and copies the snapshot:

```python
        async def operation() -> Any:
            self._ensure_no_conflicting_operations(db, repository)
            temp_key_file = None
            try:
                env, temp_key_file = build_repository_borg_env(
                    repository, db, keepalive=True
                )
                current_archives = await BorgRouter(repository).list_archives(env=env)
                current_manifest = normalize_archive_manifest(
                    borg_version=repository.borg_version or 1,
                    archives=current_archives,
                )
                current_fingerprint = compute_archive_fingerprint(current_manifest)
            finally:
                cleanup_temp_key_file(temp_key_file)

            if current_fingerprint != preview_fingerprint:
                preview.phase = "stale"
                db.commit()
                raise WipeArchiveSetChanged()

            op = enqueue(
                db,
                "wipe",
                repository_id=repository.id,
                trigger="manual",
                params={"preview_id": preview.id, "run_compact": bool(run_compact)},
                triggered_by_user_id=current_user.id,
                commit=False,
            )
            details = wipe_details(db, op)
            details.phase = "queued"
            details.archive_count = preview.archive_count
            details.archive_fingerprint = preview.archive_fingerprint
            details.archive_manifest_json = preview.archive_manifest_json
            details.dry_run_output = preview.dry_run_output
            details.blocking_reason = preview.blocking_reason
            details.protected_archives_json = preview.protected_archives_json
            details.run_compact = bool(run_compact)
            details.requested_by_user_id = preview.requested_by_user_id
            details.confirmed_by_user_id = current_user.id
            details.confirmed_at = utc_now()
            op.progress_message = "Repository wipe queued"
            db.commit()
            db.refresh(op)
            wake_runner()
            logger.warning(
                "Repository wipe execution queued",
                repository_id=repository.id,
                operation_id=op.id,
                archive_count=preview.archive_count,
                run_compact=bool(run_compact),
                actor=current_user.username,
            )
            return WipeJobFacade(db, op)
```

  Note `exclude_wipe_job_id` is gone from the `_ensure_no_conflicting_operations`
  call: the preview no longer becomes a pending row, so it can no longer
  conflict with itself. Delete the parameter from the method signature in
  Task 3, where that method is rewritten.

- Imports to add at the top of the module: `Operation` and `utc_now` from
  `app.database.models`, `enqueue` and `wake_runner` from
  `app.services.operations.enqueue`, `wipe_details` from
  `app.services.operations.details`, and `WipeJobFacade`, `resolve_wipe_job`,
  `active_wipe_operation` from `app.services.operations.wipe_facade` (the last
  one is used by Task 3's rewritten conflict check in the same module).

- [ ] **Step 8: Migrate `execute_wipe`**

Two changes, and nothing else in the body:

```python
    async def execute_wipe(self, job_id: int, repository_id: int) -> None:
        db = SessionLocal()
        close_db = getattr(SessionLocal, "return_value", None) is not db
        temp_key_file = None
        log_lines: list[str] = []
        job: Any = None
        try:
            job = resolve_wipe_job(db, job_id)
```

and, in the `if not delete_result.get("success"):` branch, set the phase that
the facade reads back as `failed_partial`:

```python
                if not delete_result.get("success"):
                    partial = _partial_delete_signal(delete_output)
                    job.status = "failed_partial" if partial else "failed"
                    job.phase = (
                        "delete_failed_partial" if partial else "delete_failed"
                    )
```

The facade's status setter writes `delete_failed_partial` itself, so the
explicit `job.phase` assignment above is the non-partial half; keep both lines
so a reader sees the two phases together.

In the `finally` block, `job.log_file_path` and `job.has_logs` already work
through the facade; keep the file write, and note that `job.logs = ...` is now
a no-op on the facade and still a real write on a legacy row.

- [ ] **Step 9: Drop the self-made stats refresh**

In `_best_effort_post_wipe_refresh`, delete the `BorgRouter(repository).update_stats(db)`
block entirely (spec 7.4 gives wipe the chain `archive_sync`,
`history_merge`, `stats`, and section 13 names this as one of the four
scattered stats calls this phase replaces). Keep the archive cache clear and
the MQTT sync: no chain step covers either.

- [ ] **Step 10: Write the failing executor test**

Create `tests/unit/test_operations_phase6_executors.py` with the wipe case
first (rclone and package cases are added in Tasks 4 and 6):

```python
"""Phase 6 executors: wipe, rclone sync, package install."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.executors import get_executor, load_default_executors
from app.services.operations.runner import OperationRunner


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


def _context(db, operation):
    from app.services.operations.runner import OperationContext

    runner = OperationRunner(session_factory=lambda: db)
    return OperationContext(runner, db, operation)


@pytest.mark.asyncio
async def test_run_wipe_reports_the_status_the_service_wrote(
    db, repository, monkeypatch
):
    load_default_executors()
    op = Operation(
        repository_id=repository.id,
        kind="wipe",
        category="maintenance",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params={"preview_id": 1, "run_compact": True},
    )
    db.add(op)
    db.commit()

    async def _execute_wipe(job_id, repository_id):
        target = db.get(Operation, job_id)
        target.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.services.repository_wipe_service.repository_wipe_service.execute_wipe",
        _execute_wipe,
    )

    outcome = await get_executor("wipe")(_context(db, op))

    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_run_wipe_fails_when_the_repository_is_gone(db, repository):
    load_default_executors()
    op = Operation(
        repository_id=None,
        kind="wipe",
        category="maintenance",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-2",
        params={},
    )
    db.add(op)
    db.commit()

    outcome = await get_executor("wipe")(_context(db, op))

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"
```

- [ ] **Step 11: Run it to verify it fails**

Run: `pytest tests/unit/test_operations_phase6_executors.py -v`
Expected: FAIL, `get_executor("wipe")` returns `None`.

- [ ] **Step 12: Write the executor**

Create `app/services/operations/executors/wipe.py`:

```python
"""The wipe executor (spec 6.3, section 13 phase 6).

A thin shell in the shape phase 5's maintenance executors established: the
work stays in `repository_wipe_service.execute_wipe`, which drives the row
through `WipeJobFacade`; the shell loads the repository, runs the service, and
turns the row's final status into an `Outcome`. Wipe has no running-cancel
path today (`cancel_preview` refuses a running job), so no cancel watcher.
"""

import structlog

from app.database.models import Operation, Repository
from app.services.operations import executors
from app.services.operations.runner import Outcome
from app.services.operations.wipe_facade import WipeJobFacade

logger = structlog.get_logger()

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


async def run_wipe(ctx) -> Outcome:
    from app.services.repository_wipe_service import repository_wipe_service

    if ctx.repository_id is None or ctx.db.get(Repository, ctx.repository_id) is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    await repository_wipe_service.execute_wipe(ctx.operation_id, ctx.repository_id)

    # The service ran in its own session and committed there. Expire this one
    # so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = WipeJobFacade(ctx.db, operation)
    if operation.status not in _TERMINAL:
        return Outcome(
            status="failed",
            error_message=job.error_message or "wipe returned no result",
        )
    if operation.status in ("completed", "completed_with_warnings"):
        return Outcome(
            status=operation.status,
            result={"archive_count": job.archive_count, "phase": job.phase},
        )
    # `Outcome` has no cancelled status (spec 6.3 gives that to the row); the
    # runner rewrites the row itself when it sees its own cancel flag.
    return Outcome(status="failed", error_message=job.error_message)


executors.register("wipe", run_wipe)
```

Register the module in `app/services/operations/executors/__init__.py`:

```python
def load_default_executors() -> None:
    """Import executor modules for their registration side effect."""
    from app.services.operations.executors import (  # noqa: F401
        history,
        index,
        maintenance,
        wipe,
    )
```

(`rclone` and `package` join this tuple in Tasks 4 and 6.)

- [ ] **Step 13: Route the confirm endpoint at the runner**

In `app/api/repositories.py`, `execute_repository_wipe`: delete the
`asyncio.create_task(repository_wipe_service.execute_wipe(job.id, repo_id))`
line. `start_execution` now returns a `WipeJobFacade`, and
`repository_wipe_service.serialize_job(job)` already reads it through the same
attributes, so the response body is unchanged apart from `status` being
`pending` rather than `running`, which is what the legacy code returned too
(`start_execution` set `pending` and the task flipped it to `running`
asynchronously).

- [ ] **Step 14: Run the suites**

Run:
```bash
pytest tests/unit/test_operations_wipe_facade.py \
       tests/unit/test_operations_phase6_executors.py \
       tests/unit/test_repository_wipe_service.py \
       tests/unit/test_operations_runner.py -v
```
Expected: PASS. Any legacy test that asserted a `RepositoryWipeJob` row is
written on confirm is rewritten to assert the operation; do not weaken an
assertion to make it pass.

---

## Task 3: Wipe, the read and admission surfaces

**Files:**
- Modify: `app/api/repositories.py:5684-5750` (wipe job read and cancel routes),
  `app/api/repositories.py:6622-6680` (running-jobs summary)
- Modify: `app/services/repository_wipe_service.py:150-200`
  (`_ensure_no_conflicting_operations`), `:500-545` (`cancel_preview`)
- Modify: `app/services/job_admission.py:298-315`
- Test: `tests/unit/test_api_repository_wipe.py`,
  `tests/unit/test_api_repositories_routes.py`,
  `tests/unit/test_job_admission.py`

**Interfaces:**
- Consumes: `resolve_wipe_job`, `active_wipe_operation`, `WipeJobFacade`
  (Task 2); `active_maintenance_operation` from
  `app/services/operations/maintenance_start.py` (phase 5).
- Produces: no new module-level names. Every route keeps its path, its status
  codes, and its response body.

**The live gap this task closes:** `_ensure_no_conflicting_operations` queries
`CheckJob`, `PruneJob`, `CompactJob`, `RestoreCheckJob`, and
`DeleteArchiveJob` directly. Phase 5 stopped writing all five tables, so on
`main` today a wipe preview can be created while a check is running. This is a
real regression introduced by phase 5 and fixed here, not a refactor.

- [ ] **Step 1: Write the failing conflict test**

Add to `tests/unit/test_api_repository_wipe.py`:

```python
def test_wipe_preview_is_rejected_while_a_check_operation_runs(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import Operation

    test_db.add(
        Operation(
            repository_id=repository.id,
            kind="check",
            category="maintenance",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-1",
        )
    )
    test_db.commit()

    response = test_client.post(
        f"/api/repositories/{repository.id}/wipe-preview",
        json={"run_compact": True},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["key"] == (
        "backend.errors.repo.operationAlreadyRunning"
    )


def test_wipe_preview_is_rejected_while_a_wipe_operation_is_queued(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import Operation

    test_db.add(
        Operation(
            repository_id=repository.id,
            kind="wipe",
            category="maintenance",
            status="queued",
            trigger="manual",
            priority=0,
            run_id="run-2",
        )
    )
    test_db.commit()

    response = test_client.post(
        f"/api/repositories/{repository.id}/wipe-preview",
        json={"run_compact": True},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["key"] == "backend.errors.repo.wipeAlreadyRunning"
```

Use the file's existing fixtures for `repository` and `admin_headers`; if it
builds them inline in each test, follow that shape instead of inventing new
fixtures.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_api_repository_wipe.py -k "operation" -v`
Expected: FAIL with 200, because nothing consults `operations`.

- [ ] **Step 3: Rewrite the conflict check**

In `app/services/repository_wipe_service.py`:

```python
    def _ensure_no_conflicting_operations(
        self, db: Session, repository: Repository
    ) -> None:
        """Refuse to preview or wipe while other work holds the repository.

        Operations first: phase 5 and phase 6 moved every exclusive kind onto
        that table, and a queued row counts, because the runner will start it.
        The legacy queries below only ever see a row a pre-upgrade install left
        active; they go away with the tables in phase 9.
        """
        repo_id = repository.id

        if (
            db.query(Operation.id)
            .filter(
                Operation.repository_id == repo_id,
                Operation.kind.in_(_CONFLICTING_KINDS),
                Operation.status.in_(("queued", "running")),
            )
            .first()
        ):
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.operationAlreadyRunning"},
            )

        if active_wipe_operation(db, repo_id) is not None:
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.wipeAlreadyRunning"},
            )

        for model in _LEGACY_CONFLICT_MODELS:
            if (
                db.query(model.id)
                .filter(
                    model.repository_id == repo_id,
                    model.status.in_(RUNNING_STATUSES),
                )
                .first()
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"key": "backend.errors.repo.operationAlreadyRunning"},
                )

        if (
            db.query(RestoreJob.id)
            .filter(
                RestoreJob.repository == repository.path,
                RestoreJob.status.in_(RUNNING_STATUSES),
            )
            .first()
        ):
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.operationAlreadyRunning"},
            )
```

with, at module level:

```python
# Kinds whose queued or running operation blocks a wipe. `restore` is here
# because the legacy check blocked on a running RestoreJob; `rclone_sync` is
# not, because it takes the rclone lock scope, not the repository lane
# (spec 7.2), and mirrors a repository nobody is writing to.
_CONFLICTING_KINDS = (
    "backup",
    "check",
    "prune",
    "compact",
    "delete_archive",
    "restore",
    "restore_check",
)
_LEGACY_CONFLICT_MODELS = (
    BackupJob,
    CheckJob,
    CompactJob,
    PruneJob,
    RestoreCheckJob,
    DeleteArchiveJob,
)
```

`RepositoryWipeJob` leaves the legacy loop: `active_wipe_operation` already
covers both id spaces and gives the wipe-specific error key.

The `exclude_wipe_job_id` parameter is deleted with this rewrite; the only
caller that passed it was `start_execution`, changed in Task 2. Check
`app/api/repositories.py:5268`, which calls this method directly, still
compiles.

- [ ] **Step 4: Run the conflict tests**

Run: `pytest tests/unit/test_api_repository_wipe.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing read-route test**

Add to `tests/unit/test_api_repository_wipe.py`:

```python
def test_wipe_job_route_serves_an_operation(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import Operation
    from app.services.operations.details import wipe_details

    op = Operation(
        repository_id=repository.id,
        kind="wipe",
        category="maintenance",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-3",
        params={"preview_id": 1, "run_compact": True},
        progress_percent=75,
        progress_message="Compacting repository after wipe",
    )
    test_db.add(op)
    test_db.commit()
    details = wipe_details(test_db, op)
    details.phase = "compact"
    details.archive_count = 4
    details.archive_fingerprint = "sha256:abc"
    details.archive_manifest_json = '[{"identity": "a"}]'
    details.protected_archives_json = "[]"
    test_db.commit()

    response = test_client.get(
        f"/api/repositories/{repository.id}/wipe-jobs/{op.id}",
        headers=admin_headers,
    )

    body = response.json()
    assert response.status_code == 200
    assert body["id"] == op.id
    assert body["status"] == "running"
    assert body["phase"] == "compact"
    assert body["progress"] == 75
    assert body["archive_count"] == 4
    assert body["archive_fingerprint"] == "sha256:abc"
    assert body["archives"] == [{"identity": "a"}]


def test_wipe_job_route_still_serves_a_pre_phase_6_row(
    test_client, test_db, admin_headers, repository
):
    job = RepositoryWipeJob(
        repository_id=repository.id,
        status="completed",
        phase="completed",
        archive_count=2,
        archive_manifest_json="[]",
        protected_archives_json="[]",
    )
    test_db.add(job)
    test_db.commit()

    response = test_client.get(
        f"/api/repositories/{repository.id}/wipe-jobs/{job.id}",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_cancelling_a_queued_wipe_operation_cancels_the_operation(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import Operation

    op = Operation(
        repository_id=repository.id,
        kind="wipe",
        category="maintenance",
        status="queued",
        trigger="manual",
        priority=0,
        run_id="run-4",
        params={"preview_id": 1},
    )
    test_db.add(op)
    test_db.commit()

    response = test_client.post(
        f"/api/repositories/{repository.id}/wipe-jobs/{op.id}/cancel",
        headers=admin_headers,
    )

    test_db.refresh(op)
    assert response.status_code == 200
    assert op.status == "cancelled"


def test_cancelling_a_running_wipe_operation_is_refused(
    test_client, test_db, admin_headers, repository
):
    from app.database.models import Operation

    op = Operation(
        repository_id=repository.id,
        kind="wipe",
        category="maintenance",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-5",
        params={"preview_id": 1},
    )
    test_db.add(op)
    test_db.commit()

    response = test_client.post(
        f"/api/repositories/{repository.id}/wipe-jobs/{op.id}/cancel",
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["key"] == (
        "backend.errors.repo.wipeCannotCancelRunning"
    )
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/unit/test_api_repository_wipe.py -k "serves_an_operation or cancelling" -v`
Expected: FAIL with 404, because both routes query `RepositoryWipeJob` only.

- [ ] **Step 7: Migrate the read and cancel routes**

In `app/api/repositories.py`, `get_repository_wipe_job`: replace the
`db.query(RepositoryWipeJob)...first()` block with

```python
        job = resolve_wipe_job(db, job_id)
        if not job or job.repository_id != repository.id:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.wipeJobNotFound"},
            )
```

and leave the `repository_wipe_service.serialize_job(...)` call unchanged: the
facade answers every attribute it reads.

In `cancel_repository_wipe_preview`, the service's `cancel_preview` keeps
handling a legacy preview row, and an operation-backed job routes to the
runner. Rewrite `cancel_preview` in `repository_wipe_service.py`:

```python
    def cancel_preview(
        self,
        db: Session,
        repository: Repository,
        current_user: User,
        *,
        job_id: int,
    ) -> dict[str, Any]:
        job = resolve_wipe_job(db, job_id)
        if not job or job.repository_id != repository.id:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.repo.wipeJobNotFound"},
            )
        if job.status not in ("previewed", "pending"):
            raise HTTPException(
                status_code=409,
                detail={"key": "backend.errors.repo.wipeCannotCancelRunning"},
            )
        job.status = "cancelled"
        job.phase = "cancelled"
        job.completed_at = utc_now()
        job.progress_message = "Wipe preview cancelled"
        db.commit()
        logger.info(
            "Repository wipe cancelled",
            repository_id=repository.id,
            job_id=job_id,
            actor=current_user.username,
        )
        return self.serialize_job(job, include_preview=True)
```

The facade maps `pending` back to `queued` and `cancelled` straight through,
so a queued operation is cancelled in place. The runner never dispatches a row
that is no longer `queued` (spec 7.1), and the operation's dependants become
`skipped` on the next tick; wipe has no dependants at enqueue time, so there
is nothing else to unwind. `db.refresh(job)` is dropped: a facade is not a
mapped instance (phase 5's `refresh_job` finding).

- [ ] **Step 8: Migrate the running-jobs summary**

In `app/api/repositories.py`'s running-jobs route, replace the `wipe_job`
query with the same `_job_or_legacy` shape the four maintenance kinds already
use:

```python
        wipe_operation = active_wipe_operation(db, repo_id)
        wipe_job = (
            WipeJobFacade(db, wipe_operation)
            if isinstance(wipe_operation, Operation)
            else wipe_operation
        )
```

The payload block below is unchanged: `id`, `status`, `phase`, `progress`,
`progress_message`, and `started_at` all resolve through the facade. Import
`WipeJobFacade`, `active_wipe_operation`, and `resolve_wipe_job` from
`app.services.operations.wipe_facade` at the top of
`app/api/repositories.py`, next to the phase 5 imports of
`MaintenanceJobFacade` and `active_maintenance_operation` already there.

- [ ] **Step 9: Migrate job admission**

In `app/services/job_admission.py`, replace the `RepositoryWipeJob` query with
an operations query plus the legacy fallback, following the
`MAINTENANCE_OPERATION_KINDS` block directly above it:

```python
    for op in (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "wipe",
            Operation.status.in_(ACTIVE_OPERATION_STATUSES),
        )
        .all()
    ):
        active.append(
            _active_work(
                repository,
                OPERATION_REPOSITORY_WIPE,
                Operation.__tablename__,
                op,
                status=legacy_status(op.status),
            )
        )

    # Legacy rows only: nothing writes repository_wipe_jobs execution rows
    # after phase 6. A `previewed` row is not active work. Goes away in
    # phase 9 with the table.
    legacy_wipe_jobs = (
        db.query(RepositoryWipeJob)
        .filter(
            RepositoryWipeJob.repository_id == repository.id,
            RepositoryWipeJob.status.in_(ACTIVE_REPOSITORY_WIPE_STATUSES),
        )
        .all()
    )
    active.extend(
        _active_work(
            repository,
            OPERATION_REPOSITORY_WIPE,
            RepositoryWipeJob.__tablename__,
            job,
        )
        for job in legacy_wipe_jobs
    )
```

Check `ACTIVE_REPOSITORY_WIPE_STATUSES` at the top of that module: if it
includes `previewed`, leave it alone for the legacy branch (a pre-phase-6
preview was genuinely blocking) and rely on the operations branch for new
work.

- [ ] **Step 10: Run the suites**

Run:
```bash
pytest tests/unit/test_api_repository_wipe.py \
       tests/unit/test_api_repositories_routes.py \
       tests/unit/test_repository_wipe_service.py \
       tests/unit/test_job_admission.py -v
```
Expected: PASS.

---

## Task 4: Rclone sync, the service and the executor

**Files:**
- Create: `app/services/operations/rclone_facade.py`
- Create: `app/services/operations/executors/rclone.py`
- Modify: `app/services/operations/executors/__init__.py`
- Modify: `app/services/rclone_repository_service.py:420-620`
  (`sync_repository`, `hydrate_repository`)
- Test: `tests/unit/test_operations_rclone_facade.py`,
  `tests/unit/test_operations_phase6_executors.py`,
  `tests/unit/test_rclone_repository_service.py`

**Interfaces:**
- Consumes: `details.rclone_details` (Task 1); `enqueue()`; `Outcome`.
- Produces:
  - `RcloneSyncFacade(db, operation)` with `.id`, `.repository_id`,
    `.direction`, `.operation`, `.status`, `.triggered_by`, `.scheduled_for`,
    `.started_at`, `.completed_at`, `.bytes_transferred`,
    `.files_transferred`, `.log_path`, `.log_text`, `.error_text`,
    `.created_at`.
  - `resolve_rclone_job(db, job_id, *, operation=None)`: operations first
    (kind `rclone_sync`, optionally filtered on `details.operation`), then
    `RcloneSyncJob`.
  - `rclone_activity_type(job) -> "rclone_sync" | "rclone_hydrate"`.
  - `TRIGGER_TO_LEGACY` / `LEGACY_TO_TRIGGER`, the `initial` <-> `import`
    mapping.
  - `run_rclone_sync(ctx) -> Outcome`, registered for kind `rclone_sync`.

**Design notes:**

1. **One kind, two operations.** Spec 6.3 has one `rclone_sync` kind and spec
   6.2 puts `operation` in the details row, so a hydrate is an `rclone_sync`
   operation with `details.operation = "hydrate"`. Activity's two types stay
   as they are, derived from that column.
2. **`triggered_by` round trip.** `manual` and `schedule` are already trigger
   words. `initial` is not, and the frontend reads it, so it maps to the
   spec 6.3 trigger `import` (the initial sync happens exactly once, when a
   cloud repository is created or imported) and maps back on read. No other
   rclone operation uses `import`.
3. **The lane is not consulted; the lock scope is.** Spec 7.2: `rclone_sync`
   uses `run_serialized_repository_command(scope="rclone")` and ignores the
   lane. `lanes.can_start` already only gates exclusive kinds and index
   kinds, so nothing there needs a change. The executor does the wrapping,
   because two of the three call sites wrap today and one (the mirror
   scheduler) does not.

- [ ] **Step 1: Write the failing facade test**

Create `tests/unit/test_operations_rclone_facade.py`, with the same `db` and
`repository` fixtures as `tests/unit/test_operations_details.py`:

```python
def test_initial_trigger_round_trips_as_triggered_by(db, repository):
    from app.database.models import Operation
    from app.services.operations.details import rclone_details
    from app.services.operations.rclone_facade import RcloneSyncFacade

    op = Operation(
        repository_id=repository.id,
        kind="rclone_sync",
        category="mirror",
        status="queued",
        trigger="import",
        priority=0,
        run_id="run-1",
    )
    db.add(op)
    db.commit()
    rclone_details(db, op).operation = "sync"
    db.commit()

    job = RcloneSyncFacade(db, op)
    assert job.triggered_by == "initial"
    assert job.status == "pending"

    job.triggered_by = "schedule"
    assert op.trigger == "schedule"
    assert RcloneSyncFacade(db, op).triggered_by == "schedule"


def test_hydrate_reads_as_the_hydrate_activity_type(db, repository):
    from app.database.models import Operation
    from app.services.operations.details import rclone_details
    from app.services.operations.rclone_facade import (
        RcloneSyncFacade,
        rclone_activity_type,
    )

    op = Operation(
        repository_id=repository.id,
        kind="rclone_sync",
        category="mirror",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-2",
    )
    db.add(op)
    db.commit()
    rclone_details(db, op).operation = "hydrate"
    db.commit()

    assert rclone_activity_type(RcloneSyncFacade(db, op)) == "rclone_hydrate"


def test_resolve_filters_on_the_details_operation(db, repository):
    from app.database.models import Operation, RcloneSyncJob
    from app.services.operations.details import rclone_details
    from app.services.operations.rclone_facade import resolve_rclone_job

    op = Operation(
        repository_id=repository.id,
        kind="rclone_sync",
        category="mirror",
        status="completed",
        trigger="manual",
        priority=0,
        run_id="run-3",
    )
    db.add(op)
    db.commit()
    rclone_details(db, op).operation = "sync"
    db.commit()

    assert resolve_rclone_job(db, op.id, operation="sync") is not None
    assert resolve_rclone_job(db, op.id, operation="hydrate") is None

    legacy = RcloneSyncJob(
        repository_id=repository.id,
        direction="cache_to_remote",
        operation="hydrate",
        status="completed",
        triggered_by="manual",
    )
    db.add(legacy)
    db.commit()
    assert resolve_rclone_job(db, legacy.id, operation="hydrate") is legacy
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_operations_rclone_facade.py -v`
Expected: FAIL, `ModuleNotFoundError: app.services.operations.rclone_facade`.

- [ ] **Step 3: Write the facade**

Create `app/services/operations/rclone_facade.py`:

```python
"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
rclone-sync-job attribute surface.

One kind, `rclone_sync`, covers both the mirror sync and the cache hydrate;
which one it is lives in `details.operation`, per spec 6.2. The legacy
`triggered_by` word `initial` is not a spec 6.3 trigger, so it is stored as
`import` and mapped back here: the frontend switches on it
(`RunningCloudStorageJobsSection.tsx`).

Deleted in phase 9 with the legacy table.
"""

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, RcloneSyncJob
from app.services.operations.details import rclone_details

LEGACY_TO_TRIGGER = {"initial": "import", "manual": "manual", "schedule": "schedule"}
TRIGGER_TO_LEGACY = {"import": "initial", "manual": "manual", "schedule": "schedule"}

_TO_OPERATION_STATUS = {"pending": "queued"}
_TO_LEGACY_STATUS = {"queued": "pending"}

_DETAIL_FIELDS = (
    "direction",
    "operation",
    "scheduled_for",
    "bytes_transferred",
    "files_transferred",
    "log_text",
    "error_text",
)


class RcloneSyncFacade:
    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "_details", rclone_details(db, operation))

    def __setattr__(self, name: str, value) -> None:
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "_details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "_details"), name)
        raise AttributeError(f"rclone_sync operations carry no {name!r}")

    @property
    def id(self) -> int:
        return self.operation.id

    @property
    def repository_id(self) -> Optional[int]:
        return self.operation.repository_id

    @property
    def created_at(self):
        return self.operation.created_at

    @property
    def status(self) -> str:
        return _TO_LEGACY_STATUS.get(self.operation.status, self.operation.status)

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = _TO_OPERATION_STATUS.get(value, value)

    @property
    def triggered_by(self) -> str:
        return TRIGGER_TO_LEGACY.get(self.operation.trigger, self.operation.trigger)

    @triggered_by.setter
    def triggered_by(self, value: str) -> None:
        self.operation.trigger = LEGACY_TO_TRIGGER.get(value, value)

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
    def log_path(self):
        """The legacy column name for what spec 6.1 calls log_file_path."""
        return self.operation.log_file_path

    @log_path.setter
    def log_path(self, value) -> None:
        self.operation.log_file_path = value


def rclone_activity_type(job: Any) -> str:
    return "rclone_hydrate" if job.operation == "hydrate" else "rclone_sync"


def resolve_rclone_job(
    db: Session, job_id: int, *, operation: Optional[str] = None
) -> Any:
    row = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "rclone_sync")
        .first()
    )
    if row is not None:
        facade = RcloneSyncFacade(db, row)
        if operation is not None and facade.operation != operation:
            return None
        return facade
    query = db.query(RcloneSyncJob).filter(RcloneSyncJob.id == job_id)
    if operation is not None:
        query = query.filter(RcloneSyncJob.operation == operation)
    return query.first()
```

- [ ] **Step 4: Run the facade test to verify it passes**

Run: `pytest tests/unit/test_operations_rclone_facade.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Write the failing service test**

Add to `tests/unit/test_rclone_repository_service.py`, alongside the existing
sync tests (which today assert an `RcloneSyncJob` row): rewrite those
assertions to the operation and add the hydrate case.

```python
@pytest.mark.asyncio
async def test_sync_repository_writes_an_operation_and_its_details(
    db_session, repository, rclone_storage, monkeypatch
):
    from app.database.models import Operation, OperationRcloneDetails

    ...  # the file's existing stubbing of rclone_repository_service.service.sync

    await rclone_repository_service.sync_repository(
        db_session, repository, triggered_by="manual"
    )

    op = db_session.query(Operation).filter(Operation.kind == "rclone_sync").one()
    details = db_session.get(OperationRcloneDetails, op.id)
    assert op.category == "mirror"
    assert op.trigger == "manual"
    assert op.status == "completed"
    assert details.operation == "sync"
    assert details.direction == rclone_storage.sync_direction
    assert db_session.query(RcloneSyncJob).count() == 0


@pytest.mark.asyncio
async def test_sync_repository_reuses_the_operation_the_runner_dispatched(
    db_session, repository, rclone_storage, monkeypatch
):
    """The executor passes its own operation id; the service must drive that
    row rather than create a second one."""
    from app.database.models import Operation
    from app.services.operations.enqueue import enqueue

    op = enqueue(
        db_session,
        "rclone_sync",
        repository_id=repository.id,
        trigger="schedule",
    )

    ...  # same stubbing as above

    await rclone_repository_service.sync_repository(
        db_session, repository, triggered_by="schedule", job_id=op.id
    )

    assert db_session.query(Operation).filter(Operation.kind == "rclone_sync").count() == 1
    db_session.refresh(op)
    assert op.status == "completed"


@pytest.mark.asyncio
async def test_hydrate_repository_writes_a_hydrate_operation(
    db_session, repository, rclone_storage, monkeypatch
):
    from app.database.models import Operation, OperationRcloneDetails

    ...  # the file's existing stubbing for hydrate

    await rclone_repository_service.hydrate_repository(db_session, repository)

    op = db_session.query(Operation).filter(Operation.kind == "rclone_sync").one()
    assert db_session.get(OperationRcloneDetails, op.id).operation == "hydrate"
```

Replace every `...` with the stubbing the file already uses for these paths
(it monkeypatches `rclone_repository_service.service.sync` with a fake
returning a success result). Do not leave an ellipsis in the committed test.

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/unit/test_rclone_repository_service.py -k "operation" -v`
Expected: FAIL, no `Operation` row.

- [ ] **Step 7: Migrate `sync_repository`**

In `app/services/rclone_repository_service.py`, replace the job resolution
block at the top of `sync_repository` (the `if job_id is not None: ... else:
sync_job = RcloneSyncJob(...)` pair) with:

```python
        if job_id is not None:
            sync_job = resolve_rclone_job(db, job_id)
            if sync_job is None or sync_job.repository_id != repository.id:
                raise ValueError(f"rclone sync job {job_id} was not found")
        else:
            operation = enqueue(
                db,
                "rclone_sync",
                repository_id=repository.id,
                trigger=LEGACY_TO_TRIGGER.get(triggered_by, "manual"),
                commit=False,
            )
            sync_job = RcloneSyncFacade(db, operation)
        sync_job.direction = storage.sync_direction
        sync_job.operation = "sync"
        sync_job.status = "running"
        sync_job.triggered_by = triggered_by
        sync_job.scheduled_for = to_utc_naive(scheduled_for) if scheduled_for else None
        sync_job.started_at = started_at
        sync_job.completed_at = None
        sync_job.error_text = None
```

Everything below (the `storage.sync_status` writes, the try/except, the
terminal status writes) is unchanged: each attribute exists on the facade. The
one line to delete is `db.refresh(sync_job)` after the commit, for the same
`UnmappedInstanceError` reason phase 5 found; the facade's `.operation`
attribute is the mapped object and nothing here needs a refresh.

Apply the same treatment to `hydrate_repository`: replace the
`hydrate_job = RcloneSyncJob(...)` construction with an `enqueue()` plus
facade, setting `sync_job.operation = "hydrate"` and
`direction = "remote_to_cache"`, and drop its `db.refresh(hydrate_job)`.

Imports to add: `enqueue` from `app.services.operations.enqueue`;
`LEGACY_TO_TRIGGER`, `RcloneSyncFacade`, `resolve_rclone_job` from
`app.services.operations.rclone_facade`.

- [ ] **Step 8: Run the service tests**

Run: `pytest tests/unit/test_rclone_repository_service.py -v`
Expected: PASS.

- [ ] **Step 9: Write the failing executor test**

Add to `tests/unit/test_operations_phase6_executors.py`:

```python
@pytest.mark.asyncio
async def test_run_rclone_sync_calls_the_service_with_its_own_operation_id(
    db, repository, monkeypatch
):
    from app.services.operations.details import rclone_details

    load_default_executors()
    op = Operation(
        repository_id=repository.id,
        kind="rclone_sync",
        category="mirror",
        status="running",
        trigger="schedule",
        priority=5,
        run_id="run-6",
    )
    db.add(op)
    db.commit()
    rclone_details(db, op).operation = "sync"
    db.commit()

    seen = {}

    async def _sync(session, repo, *, timeout=None, triggered_by="manual",
                    scheduled_for=None, job_id=None):
        seen["job_id"] = job_id
        seen["triggered_by"] = triggered_by
        target = session.get(Operation, job_id)
        target.status = "completed"
        session.commit()
        return {}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service.sync_repository",
        _sync,
    )

    outcome = await get_executor("rclone_sync")(_context(db, op))

    assert seen["job_id"] == op.id
    assert seen["triggered_by"] == "schedule"
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_run_rclone_sync_dispatches_a_hydrate_to_hydrate_repository(
    db, repository, monkeypatch
):
    from app.services.operations.details import rclone_details

    load_default_executors()
    op = Operation(
        repository_id=repository.id,
        kind="rclone_sync",
        category="mirror",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-7",
    )
    db.add(op)
    db.commit()
    rclone_details(db, op).operation = "hydrate"
    db.commit()

    called = {}

    async def _hydrate(session, repo, *, timeout=None, job_id=None):
        called["job_id"] = job_id
        target = session.get(Operation, job_id)
        target.status = "completed"
        session.commit()
        return {}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service.hydrate_repository",
        _hydrate,
    )

    outcome = await get_executor("rclone_sync")(_context(db, op))

    assert called["job_id"] == op.id
    assert outcome.status == "completed"
```

- [ ] **Step 10: Run it to verify it fails**

Run: `pytest tests/unit/test_operations_phase6_executors.py -k rclone -v`
Expected: FAIL, `get_executor("rclone_sync")` returns `None`.

- [ ] **Step 11: Write the executor**

Create `app/services/operations/executors/rclone.py`:

```python
"""The rclone mirror executor (spec 6.3, 7.2, section 13 phase 6).

`rclone_sync` ignores the repository lane and takes the `rclone` lock scope
instead (spec 7.2). Two of the three pre-phase-6 dispatch paths wrapped the
call in that lock and the mirror scheduler did not, so the wrapping moves here
and every path gets it.

`hydrate_repository` needs a `job_id` parameter it did not have before phase 6
(the legacy code always created its own row); Task 4 step 7 adds it.
"""

import structlog

from app.database.models import Operation, Repository
from app.services.operations import executors
from app.services.operations.rclone_facade import RcloneSyncFacade
from app.services.operations.runner import Outcome
from app.services.repository_command_lock import run_serialized_repository_command

logger = structlog.get_logger()

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


async def run_rclone_sync(ctx) -> Outcome:
    from app.services.rclone_repository_service import rclone_repository_service

    repository = (
        ctx.db.get(Repository, ctx.repository_id)
        if ctx.repository_id is not None
        else None
    )
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    operation = ctx.db.get(Operation, ctx.operation_id)
    job = RcloneSyncFacade(ctx.db, operation)
    is_hydrate = job.operation == "hydrate"
    triggered_by = job.triggered_by
    scheduled_for = job.scheduled_for

    async def call():
        if is_hydrate:
            return await rclone_repository_service.hydrate_repository(
                ctx.db, repository, job_id=ctx.operation_id
            )
        return await rclone_repository_service.sync_repository(
            ctx.db,
            repository,
            triggered_by=triggered_by,
            scheduled_for=scheduled_for,
            job_id=ctx.operation_id,
        )

    await run_serialized_repository_command(repository.id, call, scope="rclone")

    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    if operation.status not in _TERMINAL:
        return Outcome(
            status="failed",
            error_message=RcloneSyncFacade(ctx.db, operation).error_text
            or "rclone sync returned no result",
        )
    if operation.status in ("completed", "completed_with_warnings"):
        return Outcome(status=operation.status)
    return Outcome(
        status="failed",
        error_message=RcloneSyncFacade(ctx.db, operation).error_text,
    )


executors.register("rclone_sync", run_rclone_sync)
```

Add `rclone` to `load_default_executors`.

Add the `job_id` parameter to `hydrate_repository` in step 7's edit if it was
not added there: `job_id: int | None = None`, resolved exactly as
`sync_repository` resolves it.

- [ ] **Step 12: Run the suites**

Run:
```bash
pytest tests/unit/test_operations_rclone_facade.py \
       tests/unit/test_operations_phase6_executors.py \
       tests/unit/test_rclone_repository_service.py -v
```
Expected: PASS.

---

## Task 5: Rclone sync, the call sites and the read surfaces

**Files:**
- Modify: `app/api/repositories.py:1960-2130` (`_rclone_status_payload`,
  `_mark_background_rclone_sync_failed`, `_run_background_rclone_sync_job`,
  `_queue_initial_cloud_mirror_sync`,
  `resume_pending_initial_cloud_mirror_sync_jobs`)
- Modify: `app/services/rclone_mirror_scheduler.py:100-200, 240-309`
- Modify: `app/main.py:383`
- Modify: `app/api/activity.py:265-330, 1063-1110, 1169-1180, 1494-1505,
  1705-1715`
- Test: `tests/unit/test_api_rclone.py`, `tests/unit/test_api_activity.py`,
  `tests/unit/test_api_schedule_routes.py`

**Interfaces:**
- Consumes: everything Task 4 produced.
- Produces: `resume_pending_initial_cloud_mirror_sync_operations()` in
  `app/api/repositories.py`, replacing
  `resume_pending_initial_cloud_mirror_sync_jobs()`. Same call site in
  `app/main.py`, same return type (`int`, the number resumed).

**Design notes:**

1. **The initial sync becomes a queued operation.** `_queue_initial_cloud_mirror_sync`
   enqueues an `rclone_sync` operation with `trigger="import"` and
   `details.operation = "sync"`, and stops spawning a task. The runner
   dispatches it. `_run_background_rclone_sync_job`,
   `_mark_background_rclone_sync_failed`, and
   `_log_background_rclone_sync_task_result` are deleted: the runner owns
   dispatch, failure recording, and cancellation now.
2. **Restart resume runs before recovery.** Spec 7.6 marks a non-index
   `running` operation with a dead pid as `failed`. An interrupted initial
   sync used to resume, so the replacement flips interrupted `rclone_sync`
   rows back to `queued` *before* `OperationRunner.recover_on_startup` sees
   them. Check the ordering in `app/main.py`: the resume call must come
   before the recovery call. Rclone syncs are idempotent (`rclone sync` is
   itself a reconciliation), so re-running one is safe.
3. **The scheduler enqueues.** `dispatch_due_scheduled_rclone_mirrors` and
   `run_due_scheduled_rclone_mirrors` both stop spawning tasks or awaiting
   the service and instead enqueue an operation with `trigger="schedule"` and
   `details.scheduled_for`. `_scheduled_job_exists` (the idempotence guard
   against enqueueing the same `scheduled_for` twice) queries operations
   first, then the legacy table. `_record_scheduler_failure` keeps recording
   a storage-level failure but writes its job row as an operation.
   `_active_scheduled_mirror_tasks` and `_track_scheduled_mirror_task` are
   deleted with the tasks they tracked.

- [ ] **Step 1: Write the failing initial-sync test**

Add to `tests/unit/test_api_rclone.py`, next to the existing initial-sync
tests (around line 4830, which asserts an `RcloneSyncJob` row):

```python
def test_creating_a_cloud_repository_enqueues_an_initial_sync_operation(
    test_client, test_db, admin_headers, rclone_remote
):
    from app.database.models import Operation, OperationRcloneDetails

    ...  # the file's existing repository-creation payload for an rclone backend

    op = test_db.query(Operation).filter(Operation.kind == "rclone_sync").one()
    assert op.status == "queued"
    assert op.trigger == "import"
    assert test_db.get(OperationRcloneDetails, op.id).operation == "sync"
    assert test_db.query(RcloneSyncJob).count() == 0


def test_resume_requeues_an_interrupted_initial_sync_operation(test_db):
    from app.api.repositories import (
        resume_pending_initial_cloud_mirror_sync_operations,
    )
    from app.database.models import Operation

    ...  # build a repository with rclone storage, then:
    op = Operation(
        repository_id=repository.id,
        kind="rclone_sync",
        category="mirror",
        status="running",
        trigger="import",
        priority=0,
        run_id="run-1",
    )
    test_db.add(op)
    test_db.commit()

    assert resume_pending_initial_cloud_mirror_sync_operations() == 1
    test_db.refresh(op)
    assert op.status == "queued"
```

Replace each `...` with the concrete setup the file already uses. Note the
second test needs `SessionLocal` pointed at `test_db`; follow whatever pattern
the file's existing `resume_pending_initial_cloud_mirror_sync_jobs` test uses
(around line 4890).

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_api_rclone.py -k "initial_sync_operation or resume_requeues" -v`
Expected: FAIL, `ImportError` on the new function name.

- [ ] **Step 3: Migrate the initial sync**

In `app/api/repositories.py`:

```python
def _queue_initial_cloud_mirror_sync(db: Session, repository: Repository) -> None:
    """Queue the first mirror sync for a newly created cloud repository. The
    runner dispatches it (spec 7.1); nothing is spawned here."""
    storage = (
        db.query(RepositoryStorage)
        .filter(RepositoryStorage.repository_id == repository.id)
        .first()
    )
    if not storage or storage.backend != "rclone":
        return
    operation = enqueue(
        db,
        "rclone_sync",
        repository_id=repository.id,
        trigger="import",
        commit=False,
    )
    job = RcloneSyncFacade(db, operation)
    job.direction = storage.sync_direction
    job.operation = "sync"
    storage.sync_status = "pending"
    storage.last_sync_error = None
    db.commit()
    wake_runner()


def resume_pending_initial_cloud_mirror_sync_operations() -> int:
    """Requeue an initial mirror sync a restart interrupted.

    Spec 7.6 would mark a `running` non-index operation failed, which is right
    for a Borg command holding a lock and wrong for a mirror sync: `rclone
    sync` is itself a reconciliation, so re-running it is safe and is what the
    pre-phase-6 code did. Runs before `OperationRunner.recover_on_startup`, so
    recovery sees a `queued` row and leaves it alone.
    """
    db = SessionLocal()
    try:
        operations = (
            db.query(Operation)
            .filter(
                Operation.kind == "rclone_sync",
                Operation.trigger == "import",
                Operation.status.in_(("queued", "running")),
            )
            .order_by(Operation.id.asc())
            .all()
        )
        resumed = 0
        for operation in operations:
            storage = (
                db.query(RepositoryStorage)
                .filter(RepositoryStorage.repository_id == operation.repository_id)
                .first()
            )
            if storage:
                storage.sync_status = "pending"
                storage.last_sync_error = None
            operation.status = "queued"
            operation.started_at = None
            resumed += 1
        db.commit()
        return resumed
    finally:
        db.close()
```

Delete `_run_background_rclone_sync_job`, `_mark_background_rclone_sync_failed`,
`_log_background_rclone_sync_task_result`, and
`resume_pending_initial_cloud_mirror_sync_jobs`. Grep for each name before
deleting; the only expected caller of the last one is `app/main.py:383`,
which becomes:

```python
            repositories.resume_pending_initial_cloud_mirror_sync_operations()
```

Confirm this line runs before the `operation_runner.recover_on_startup(...)`
call in the same startup path. If it does not, move it above, with a comment
naming the reason.

- [ ] **Step 4: Migrate `_rclone_status_payload`**

The `latest_sync_job` block reads the newest row. Replace the query with the
newer of the operation and the legacy row, in the shape phase 5 used for the
status strip:

```python
    latest_operation = (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "rclone_sync",
        )
        .order_by(Operation.created_at.desc(), Operation.id.desc())
        .first()
    )
    latest_legacy = (
        db.query(RcloneSyncJob)
        .filter(RcloneSyncJob.repository_id == repository.id)
        .order_by(RcloneSyncJob.created_at.desc(), RcloneSyncJob.id.desc())
        .first()
    )
    latest_job = _newer_rclone_job(db, latest_operation, latest_legacy)
```

with, at module level:

```python
def _newer_rclone_job(db: Session, operation, legacy):
    """The newer of an operations row and a pre-phase-6 legacy row. Both
    tables can hold history for the same repository until phase 9."""
    if operation is None:
        return legacy
    if legacy is None:
        return RcloneSyncFacade(db, operation)
    if legacy.created_at and operation.created_at < legacy.created_at:
        return legacy
    return RcloneSyncFacade(db, operation)
```

The payload block below is unchanged: `triggered_by`, `status`,
`scheduled_for`, `started_at`, `completed_at`, `error_text`, `operation`, and
`log_path` all resolve through the facade.

- [ ] **Step 5: Write the failing scheduler test**

Add to `tests/unit/test_api_schedule_routes.py` (or
`tests/unit/test_rclone_mirror_scheduler.py` if that file exists; check
first), replacing the assertion at line 599 that a scheduled `RcloneSyncJob`
was created:

```python
def test_due_scheduled_mirror_enqueues_an_operation(test_db, ...):
    from app.database.models import Operation, OperationRcloneDetails
    from app.services.rclone_mirror_scheduler import (
        dispatch_due_scheduled_rclone_mirrors,
    )

    ...  # storage due for a scheduled sync, as the file already builds it

    dispatched = dispatch_due_scheduled_rclone_mirrors(test_db, now)

    op = test_db.query(Operation).filter(Operation.kind == "rclone_sync").one()
    assert dispatched == 1
    assert op.status == "queued"
    assert op.trigger == "schedule"
    assert test_db.get(OperationRcloneDetails, op.id).scheduled_for is not None


def test_a_second_tick_does_not_enqueue_the_same_scheduled_run_twice(test_db, ...):
    from app.database.models import Operation
    from app.services.rclone_mirror_scheduler import (
        dispatch_due_scheduled_rclone_mirrors,
    )

    ...  # same setup

    dispatch_due_scheduled_rclone_mirrors(test_db, now)
    dispatch_due_scheduled_rclone_mirrors(test_db, now)

    assert test_db.query(Operation).filter(Operation.kind == "rclone_sync").count() == 1
```

Replace each `...` with the concrete setup those files already use, including
the `now` the scheduler is given. Do not leave an ellipsis in the committed
test.

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/unit/test_api_schedule_routes.py -k mirror -v`
Expected: FAIL.

- [ ] **Step 7: Migrate the mirror scheduler**

In `app/services/rclone_mirror_scheduler.py`:

- `_scheduled_job_exists` gains the operations query, Python-side on
  `details.scheduled_for`:

```python
def _scheduled_job_exists(
    db: Session, *, repository_id: int, scheduled_for: datetime
) -> bool:
    exists = (
        db.query(Operation.id)
        .join(
            OperationRcloneDetails,
            OperationRcloneDetails.operation_id == Operation.id,
        )
        .filter(
            Operation.repository_id == repository_id,
            Operation.kind == "rclone_sync",
            Operation.trigger == "schedule",
            OperationRcloneDetails.scheduled_for == scheduled_for,
        )
        .first()
    )
    if exists is not None:
        return True
    # Pre-phase-6 rows only; goes away with the table in phase 9.
    return (
        db.query(RcloneSyncJob.id)
        .filter(
            RcloneSyncJob.repository_id == repository_id,
            RcloneSyncJob.triggered_by == "schedule",
            RcloneSyncJob.scheduled_for == scheduled_for,
        )
        .first()
        is not None
    )
```

- Both `dispatch_due_scheduled_rclone_mirrors` and
  `run_due_scheduled_rclone_mirrors` replace their task spawn / awaited
  `sync_repository` call with one enqueue, guarded by `_scheduled_job_exists`:

```python
def _enqueue_scheduled_mirror(
    db: Session, *, repository_id: int, direction: str, scheduled_for: datetime
) -> bool:
    if _scheduled_job_exists(
        db, repository_id=repository_id, scheduled_for=scheduled_for
    ):
        return False
    operation = enqueue(
        db,
        "rclone_sync",
        repository_id=repository_id,
        trigger="schedule",
        commit=False,
    )
    job = RcloneSyncFacade(db, operation)
    job.direction = direction
    job.operation = "sync"
    job.scheduled_for = scheduled_for
    db.commit()
    wake_runner()
    return True
```

  Keep the `storage.next_scheduled_sync_at` recalculation exactly as it is:
  that is the scheduler's own bookkeeping and is unrelated to dispatch. Both
  functions become the same loop over due storages calling
  `_enqueue_scheduled_mirror`; `run_due_scheduled_rclone_mirrors` no longer
  awaits anything, so keep it `async def` (its caller awaits it) with no
  await inside, or convert the caller. Prefer keeping the signature: fewer
  call sites move.

- `_run_scheduled_rclone_mirror_task`, `_track_scheduled_mirror_task`,
  `_active_scheduled_mirror_tasks`, and `_record_scheduler_failure` are
  deleted. Failure recording now belongs to the runner: it writes `failed`
  with the error on the operation. The one thing the runner does not do is
  the storage-level bookkeeping (`storage.sync_status = "failed"`,
  `last_sync_error`, `last_scheduled_sync_at`), which `sync_repository`
  already writes on its own failure path, so nothing is lost.

  Verify that last claim before deleting `_record_scheduler_failure`: read
  `sync_repository`'s `except` block. If a failure before the service is
  reached (a missing storage row, say) would leave `storage.sync_status`
  stale, keep a small failure hook and say so in the code comment.

- [ ] **Step 8: Migrate the Activity surfaces**

In `app/api/activity.py`:

- `_get_rclone_job` resolves operations first:

```python
def _get_rclone_job(db: Session, job_type: str, job_id: int):
    from app.services.operations.rclone_facade import resolve_rclone_job

    return resolve_rclone_job(
        db, job_id, operation=RCLONE_ACTIVITY_OPERATIONS[job_type]
    )
```

- `_format_rclone_job_logs` is unchanged (it reads `log_text` and
  `error_text`, which the facade answers).
- `_operation_activity_items` labels an rclone row by its details column.
  Find where it sets the item's `type` from `op.kind` and special-case the
  one kind whose activity type is not its kind name:

```python
        item_type = op.kind
        if op.kind == "rclone_sync":
            item_type = rclone_activity_type(RcloneSyncFacade(db, op))
```

  and make the `job_type` filter accept both activity names:

```python
    if job_type:
        if job_type in RCLONE_ACTIVITY_OPERATIONS:
            q = q.filter(Operation.kind == "rclone_sync")
        elif job_type not in op_vocab.KINDS:
            return []
        else:
            q = q.filter(Operation.kind == job_type)
```

  With `job_type == "rclone_hydrate"` the query returns both operations, so
  filter the built items by `item_type == job_type` before returning. Add a
  test for exactly that: a sync and a hydrate on one repository, filtered to
  `rclone_hydrate`, returns one item. Import `RcloneSyncFacade` and
  `rclone_activity_type` from `app.services.operations.rclone_facade` at the
  top of `app/api/activity.py`.

- The legacy rclone fetch block at line 1063 stays: it serves pre-phase-6
  history. Nothing new writes those rows, so there is no double counting.

- [ ] **Step 9: Run the suites**

Run:
```bash
pytest tests/unit/test_api_rclone.py tests/unit/test_api_activity.py \
       tests/unit/test_api_schedule_routes.py \
       tests/unit/test_rclone_repository_service.py -v
```
Expected: PASS. `test_api_rclone.py` is the file with the known event-loop
teardown noise recorded in phase 5's notes; run it alone if the noise makes a
real failure hard to read.

---

## Task 6: Package install

**Files:**
- Create: `app/services/operations/package_facade.py`
- Create: `app/services/operations/executors/package.py`
- Modify: `app/services/operations/executors/__init__.py`
- Modify: `app/services/package_service.py`
- Modify: `app/api/packages.py:93-135, 250-295`
- Modify: `app/api/activity.py:287-300, 961-1005, 1169-1180, 1494-1505, 1705-1715`
- Modify: `app/scripts/startup_packages.py:60-75`
- Test: `tests/unit/test_operations_package_facade.py`,
  `tests/unit/test_operations_phase6_executors.py`,
  `tests/unit/test_api_packages.py`, `tests/unit/test_package_service.py`

**Interfaces:**
- Consumes: `enqueue()`, `Outcome`, `operation_log_path`.
- Produces:
  - `PackageInstallFacade(db, operation)` with `.id`, `.package_id`,
    `.status`, `.started_at`, `.completed_at`, `.exit_code`, `.stdout`,
    `.stderr`, `.error_message`, `.process_pid`, `.process_start_time`,
    `.created_at`, and a `write_output(stdout, stderr)` method.
  - `resolve_package_job(db, job_id)`, `active_package_install(db, package_id)`.
  - `run_package_install(ctx) -> Outcome`, registered for `package_install`.

**Design notes:**

1. **No extension table**, per spec 6.2. `params = {"package_id": n}`,
   `result = {"exit_code": n}`, and the captured output goes to the
   operation's log file in a fixed layout the facade parses back, so
   `GET /api/packages/jobs/{id}` keeps returning `stdout` and `stderr`
   separately. The sentinels are deliberately unlikely to appear in apt
   output. See Open question 2.
2. **`installing` is the legacy word for `running`.** The route contract and
   the frontend both use it, so the facade maps in both directions, exactly
   as phase 5 mapped `pending` to `queued`.
3. **`repository_id` is null** (spec 6.3), which means the Activity union
   already scopes it out of repository-filtered views the same way the
   legacy branch did with `and not repository_scoped`.

- [ ] **Step 1: Write the failing facade test**

Create `tests/unit/test_operations_package_facade.py` with the `db` fixture
pattern from `tests/unit/test_operations_details.py` (no repository needed):

```python
def test_status_maps_installing_to_running(db, tmp_path, monkeypatch):
    from app.database.models import Operation
    from app.services.operations.package_facade import PackageInstallFacade

    op = Operation(
        kind="package_install",
        category="system",
        status="queued",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params={"package_id": 3},
    )
    db.add(op)
    db.commit()

    job = PackageInstallFacade(db, op)
    assert job.status == "pending"
    assert job.package_id == 3

    job.status = "installing"
    db.commit()
    assert op.status == "running"
    assert PackageInstallFacade(db, op).status == "installing"


def test_output_round_trips_through_the_log_file(db, tmp_path, monkeypatch):
    from app.database.models import Operation
    from app.services.operations.package_facade import PackageInstallFacade

    monkeypatch.setattr(
        "app.services.operations.runner.app_settings.data_dir", str(tmp_path)
    )
    op = Operation(
        kind="package_install",
        category="system",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-2",
        params={"package_id": 3},
    )
    db.add(op)
    db.commit()

    job = PackageInstallFacade(db, op)
    job.write_output("Reading package lists...\nDone", "W: apt does not have a stable CLI")
    db.commit()

    reread = PackageInstallFacade(db, op)
    assert reread.stdout == "Reading package lists...\nDone"
    assert reread.stderr == "W: apt does not have a stable CLI"
    assert op.log_file_path is not None


def test_missing_output_reads_as_empty_strings(db):
    from app.database.models import Operation
    from app.services.operations.package_facade import PackageInstallFacade

    op = Operation(
        kind="package_install",
        category="system",
        status="queued",
        trigger="manual",
        priority=0,
        run_id="run-3",
        params={"package_id": 3},
    )
    db.add(op)
    db.commit()

    job = PackageInstallFacade(db, op)
    assert job.stdout == ""
    assert job.stderr == ""
    assert job.exit_code is None
```

Confirm the monkeypatch target for `data_dir` against
`app/services/operations/runner.py`'s import (`app_settings`); if the name
differs, patch what `operation_log_path` actually reads.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_operations_package_facade.py -v`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Write the facade**

Create `app/services/operations/package_facade.py`:

```python
"""An `operations` row wearing the legacy package-install-job surface.

Spec 6.2 gives `package_install` no extension table, so the input
(`package_id`) lives in `operations.params`, the exit code in
`operations.result`, and the captured output in the operation's log file. The
two streams are separated by sentinel lines this module writes and parses, so
`GET /api/packages/jobs/{id}` keeps returning `stdout` and `stderr` apart.

Deleted in phase 9 with the legacy table.
"""

from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, PackageInstallJob

STDOUT_SENTINEL = "===== BORG-UI PACKAGE STDOUT ====="
STDERR_SENTINEL = "===== BORG-UI PACKAGE STDERR ====="

ACTIVE_STATUSES = ("queued", "running")
_LEGACY_ACTIVE_STATUSES = ("pending", "installing")

_TO_OPERATION = {"pending": "queued", "installing": "running"}
_TO_LEGACY = {"queued": "pending", "running": "installing"}


class PackageInstallFacade:
    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)

    @property
    def id(self) -> int:
        return self.operation.id

    @property
    def package_id(self) -> Optional[int]:
        return (self.operation.params or {}).get("package_id")

    @property
    def created_at(self):
        return self.operation.created_at

    @property
    def status(self) -> str:
        return _TO_LEGACY.get(self.operation.status, self.operation.status)

    @status.setter
    def status(self, value: str) -> None:
        self.operation.status = _TO_OPERATION.get(value, value)

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
        self.operation.process_start_time = (
            None if value is None else float(value)
        )

    @property
    def exit_code(self):
        return (self.operation.result or {}).get("exit_code")

    @exit_code.setter
    def exit_code(self, value) -> None:
        result = dict(self.operation.result or {})
        result["exit_code"] = value
        self.operation.result = result

    @property
    def log_file_path(self):
        return self.operation.log_file_path

    # -- captured output ---------------------------------------------------

    def write_output(self, stdout: str, stderr: str) -> None:
        from app.services.operations.runner import operation_log_path

        path = Path(self.operation.log_file_path or operation_log_path(
            self.operation.id
        ))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{STDOUT_SENTINEL}\n{stdout or ''}\n{STDERR_SENTINEL}\n{stderr or ''}",
            encoding="utf-8",
        )
        self.operation.log_file_path = str(path)

    def _streams(self) -> tuple[str, str]:
        path = self.operation.log_file_path
        if not path:
            return "", ""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            return "", ""
        if STDOUT_SENTINEL not in text:
            # A log written by something other than write_output (the runner's
            # ctx.log, say). Treat the whole file as stdout.
            return text, ""
        _, _, rest = text.partition(f"{STDOUT_SENTINEL}\n")
        stdout, _, stderr = rest.partition(f"\n{STDERR_SENTINEL}\n")
        return stdout, stderr

    @property
    def stdout(self) -> str:
        return self._streams()[0]

    @property
    def stderr(self) -> str:
        return self._streams()[1]


def resolve_package_job(db: Session, job_id: int) -> Any:
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "package_install")
        .first()
    )
    if operation is not None:
        return PackageInstallFacade(db, operation)
    return db.query(PackageInstallJob).filter(PackageInstallJob.id == job_id).first()


def active_package_install(db: Session, package_id: int) -> Any:
    """The queued or running install for this package, if any. Params are
    scanned in Python because a JSON column is not portably queryable across
    SQLite and PostgreSQL, the same shape phase 5 used for
    `active_delete_for_archive`."""
    for operation in (
        db.query(Operation)
        .filter(
            Operation.kind == "package_install",
            Operation.status.in_(ACTIVE_STATUSES),
        )
        .all()
    ):
        if (operation.params or {}).get("package_id") == package_id:
            return PackageInstallFacade(db, operation)
    return (
        db.query(PackageInstallJob)
        .filter(
            PackageInstallJob.package_id == package_id,
            PackageInstallJob.status.in_(_LEGACY_ACTIVE_STATUSES),
        )
        .first()
    )
```

- [ ] **Step 4: Run the facade test to verify it passes**

Run: `pytest tests/unit/test_operations_package_facade.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Write the failing service and route tests**

In `tests/unit/test_package_service.py`, rewrite the tests that build a
`PackageInstallJob` to build an operation, and add:

```python
@pytest.mark.asyncio
async def test_start_install_job_enqueues_and_does_not_spawn(
    db_session, installed_package, monkeypatch
):
    from app.database.models import Operation, PackageInstallJob
    from app.services.package_service import package_service

    spawned = []
    monkeypatch.setattr(
        "asyncio.create_task", lambda coro: spawned.append(coro)
    )

    job = await package_service.start_install_job(db_session, installed_package.id)

    op = db_session.query(Operation).one()
    assert op.kind == "package_install"
    assert op.category == "system"
    assert op.repository_id is None
    assert op.params == {"package_id": installed_package.id}
    assert op.status == "queued"
    assert job.status == "pending"
    assert spawned == []
    assert db_session.query(PackageInstallJob).count() == 0
```

In `tests/unit/test_api_packages.py`, add:

```python
def test_install_returns_the_in_flight_operation_instead_of_a_second_one(
    test_client, test_db, admin_headers, package
):
    from app.database.models import Operation

    existing = Operation(
        kind="package_install",
        category="system",
        status="queued",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params={"package_id": package.id},
    )
    test_db.add(existing)
    test_db.commit()

    response = test_client.post(
        f"/api/packages/{package.id}/install", headers=admin_headers
    )

    body = response.json()
    assert body["job_id"] == existing.id
    assert body["status"] == "pending"
    assert test_db.query(Operation).count() == 1


def test_job_status_serves_an_operation_with_its_captured_output(
    test_client, test_db, admin_headers, package, tmp_path
):
    from app.database.models import Operation
    from app.services.operations.package_facade import PackageInstallFacade

    op = Operation(
        kind="package_install",
        category="system",
        status="completed",
        trigger="manual",
        priority=0,
        run_id="run-2",
        params={"package_id": package.id},
        result={"exit_code": 0},
    )
    test_db.add(op)
    test_db.commit()
    PackageInstallFacade(test_db, op).write_output("installed", "")
    test_db.commit()

    response = test_client.get(f"/api/packages/jobs/{op.id}", headers=admin_headers)

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["exit_code"] == 0
    assert body["stdout"] == "installed"
    assert body["stderr"] == ""
```

- [ ] **Step 6: Run them to verify they fail**

Run: `pytest tests/unit/test_package_service.py tests/unit/test_api_packages.py -k "operation or enqueues or in_flight" -v`
Expected: FAIL.

- [ ] **Step 7: Migrate the service**

In `app/services/package_service.py`:

```python
    async def start_install_job(self, db: Session, package_id: int):
        """Queue an install. The runner dispatches it (spec 7.1); nothing is
        spawned here."""
        package = (
            db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
        )
        if not package:
            raise ValueError(f"Package {package_id} not found")

        operation = enqueue(
            db,
            "package_install",
            trigger="manual",
            params={"package_id": package_id},
        )
        logger.info(
            "Queued package install operation",
            operation_id=operation.id,
            package=package.name,
        )
        return PackageInstallFacade(db, operation)

    async def run_install_job(self, job_id: int) -> None:
        """The install itself, driven by the runner's executor. The body below
        is the pre-phase-6 `_run_install_job`, with the job resolved through
        the facade and the captured output written to the operation's log
        file instead of two columns."""
```

Rename `_run_install_job` to `run_install_job(self, job_id)`, and inside it:

- resolve with `job = resolve_package_job(db, job_id)` and read
  `package_id = job.package_id`, `install_command` and `package_name` from the
  `InstalledPackage` row (they were parameters before; the executor has only
  the operation id);
- replace `job.stdout = stdout_str` / `job.stderr = stderr_str` with
  `job.write_output(stdout_str, stderr_str)`;
- keep every other line, including the two status writes, the PID capture,
  the timeout, and the package-status bookkeeping;
- drop `self.running_jobs` entirely: the runner owns task handles now
  (`OperationRunner.running_tasks`), and `get_running_jobs` below is a
  database query, not a memory read.

`get_running_jobs` becomes:

```python
    def get_running_jobs(self, db: Session) -> list:
        operations = (
            db.query(Operation)
            .filter(
                Operation.kind == "package_install",
                Operation.status.in_(("queued", "running")),
            )
            .all()
        )
        jobs = [PackageInstallFacade(db, op) for op in operations]
        # Pre-phase-6 rows only; goes away with the table in phase 9.
        jobs.extend(
            db.query(PackageInstallJob)
            .filter(PackageInstallJob.status.in_(("pending", "installing")))
            .all()
        )
        return jobs
```

`get_job_status` becomes `return resolve_package_job(db, job_id)`.

- [ ] **Step 8: Write the executor**

Create `app/services/operations/executors/package.py`:

```python
"""The package install executor (spec 6.3, section 13 phase 6).

`package_install` is category `system` with a null `repository_id`, so there
is no repository to load and no lane to take. The install body stays in
`package_service`; this shell runs it and reads the verdict back.
"""

import structlog

from app.database.models import Operation
from app.services.operations import executors
from app.services.operations.package_facade import PackageInstallFacade
from app.services.operations.runner import Outcome

logger = structlog.get_logger()

_TERMINAL = ("completed", "failed", "cancelled")


async def run_package_install(ctx) -> Outcome:
    from app.services.package_service import package_service

    await package_service.run_install_job(ctx.operation_id)

    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = PackageInstallFacade(ctx.db, operation)
    if operation.status not in _TERMINAL:
        return Outcome(
            status="failed",
            error_message=job.error_message or "package install returned no result",
        )
    if operation.status == "completed":
        return Outcome(status="completed", result={"exit_code": job.exit_code})
    return Outcome(status="failed", error_message=job.error_message)
```

Register it, and add `package` to `load_default_executors`.

- [ ] **Step 9: Migrate the routes**

In `app/api/packages.py`:

- `install_package`'s duplicate check becomes
  `existing_job = active_package_install(db, package_id)`, and its early
  return keeps its exact body (`job_id`, `message`, `status`), which now
  reads `pending` or `installing` off the facade.
- `get_job_status` resolves with `resolve_package_job(db, job_id)` and keeps
  its response dict verbatim: `package_id`, `status`, `started_at`,
  `completed_at`, `exit_code`, `stdout`, `stderr`, `error_message` all answer
  through the facade.
- `list_jobs` unions the two tables, newest first:

```python
    operations = (
        db.query(Operation)
        .filter(Operation.kind == "package_install")
        .order_by(Operation.created_at.desc())
        .limit(50)
        .all()
    )
    jobs = [PackageInstallFacade(db, op) for op in operations]
    jobs.extend(
        db.query(PackageInstallJob)
        .order_by(PackageInstallJob.created_at.desc())
        .limit(50)
        .all()
    )
    jobs.sort(key=lambda job: job.created_at, reverse=True)
    jobs = jobs[:50]
```

  keeping the existing comprehension that builds the response bodies.

- [ ] **Step 10: Migrate the Activity surfaces**

In `app/api/activity.py`:

- Drop `"package": PackageInstallJob` from the three `job_models` maps
  (lines 1172, 1497, 1708) so `_is_operation_only_kind` sends `package` down
  the operations path, and teach `_get_operation_or_404` the package fallback:
  `LEGACY_MODELS` covers only the five maintenance kinds, so add a local map
  for the phase 6 kinds:

```python
_PHASE6_LEGACY_MODELS = {
    "wipe": RepositoryWipeJob,
    "package": PackageInstallJob,
}
```

  and consult it after `LEGACY_MODELS` in `_get_operation_or_404`.

  Careful: the Activity job type is `package`, while the operation kind is
  `package_install`. Add the alias where `_get_operation_or_404` filters on
  `Operation.kind`, and where `_operation_activity_items` labels an item:
  a `package_install` operation is Activity type `package`. Pin both with a
  test.

- `_format_package_install_logs` already reads `job.stdout`, `job.stderr`,
  `job.exit_code`, and `job.package_id`, so it works against the facade
  unchanged.
- The legacy package fetch block at line 962 stays, for pre-phase-6 history.

- [ ] **Step 11: Migrate the startup script**

In `app/scripts/startup_packages.py`, the `NOT EXISTS` subquery must also see
an in-flight operation, or a package queued at shutdown is installed twice:

```sql
                    SELECT p.id, p.name, p.status, p.install_command
                    FROM installed_packages p
                    WHERE NOT EXISTS (
                        SELECT 1 FROM package_install_jobs j
                        WHERE j.package_id = p.id
                        AND j.status IN ('pending', 'installing')
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM operations o
                        WHERE o.kind = 'package_install'
                        AND o.status IN ('queued', 'running')
                        AND json_extract(o.params, '$.package_id') = p.id
                    )
```

`json_extract` is SQLite-only. Check what database this script runs against
(`_database_absent()` and the engine it builds at the top of the file); if it
can run against PostgreSQL, use a dialect-neutral form instead, for example
comparing `o.params ->> 'package_id'` under PostgreSQL, chosen from
`engine.dialect.name`. Write the check as one small Python helper with a
branch per dialect rather than one clever SQL string.

- [ ] **Step 12: Run the suites**

Run:
```bash
pytest tests/unit/test_operations_package_facade.py \
       tests/unit/test_operations_phase6_executors.py \
       tests/unit/test_package_service.py tests/unit/test_api_packages.py \
       tests/unit/test_api_activity.py tests/unit/test_startup_packages.py -v
```
Expected: PASS.

---

## Task 7: Retention, log protection, and the startup sweep

**Files:**
- Modify: `app/services/job_history_retention.py`
- Modify: `app/services/log_manager.py:138-150`
- Test: `tests/unit/test_job_history_retention.py`,
  `tests/unit/test_log_manager.py`

**Interfaces:**
- Consumes: the two extension models (Task 1) and the three facades.
- Produces: no new public names.

**Design note.** Spec 7.8 says the retention job "gains `operations` and the
extension tables in its table list". `_JOB_TABLES` entries are `(model,
inline log columns)` pairs filtered by an age expression over
`completed_at` / `updated_at` / `started_at` / `created_at`, and an extension
row has none of those: its age is its operation's. The cascade delete on
`operations.id` already removes extension rows with their operation, which is
the outcome spec 7.8 asks for, so the table list keeps only `Operation` and
this task adds two things instead: a test pinning the cascade, and the
log-column clearing for `operation_rclone_details.log_text` and
`.error_text` at `log_retention_days`, which the cascade does not cover
because those rows outlive the log window but not the cleanup window.

- [ ] **Step 1: Write the failing retention test**

Add to `tests/unit/test_job_history_retention.py`:

```python
def test_deleting_an_operation_takes_its_extension_rows(db):
    from app.database.models import (
        Operation,
        OperationRcloneDetails,
        OperationWipeDetails,
    )

    ...  # build an old wipe operation and an old rclone operation with details

    run_job_history_retention(db)

    assert db.query(Operation).count() == 0
    assert db.query(OperationWipeDetails).count() == 0
    assert db.query(OperationRcloneDetails).count() == 0


def test_rclone_log_text_is_cleared_at_the_log_retention_window(db):
    from app.database.models import Operation, OperationRcloneDetails

    ...  # an rclone operation completed inside cleanup_retention_days but
         # outside log_retention_days, with details.log_text set

    run_job_history_retention(db)

    assert db.query(Operation).count() == 1
    assert db.get(OperationRcloneDetails, op.id).log_text is None
```

Replace each `...` with the file's own row-building code; do not leave an
ellipsis in the committed test. Use the file's existing helper for building an
aged row and its entry point name (the file already calls into the retention service around line 221; match
that call, do not invent `run_job_history_retention` if the real name
differs).

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_job_history_retention.py -k "extension or log_text" -v`
Expected: FAIL on the log-text clearing (the cascade test may already pass,
which is fine: it is a pin, and a passing pin still belongs in the suite).

- [ ] **Step 3: Clear the extension log columns**

In `app/services/job_history_retention.py`, alongside the loop that clears
inline log columns for `_JOB_TABLES`, add the extension pass:

```python
def _clear_operation_detail_logs(db: Session, log_cutoff) -> int:
    """`operation_rclone_details` keeps the sync output the legacy
    `rclone_sync_jobs.log_text` column kept. Its age is its operation's, so it
    cannot ride in _JOB_TABLES; clear it here at the same log window."""
    stale = (
        db.query(OperationRcloneDetails)
        .join(Operation, Operation.id == OperationRcloneDetails.operation_id)
        .filter(
            Operation.completed_at.isnot(None),
            Operation.completed_at < log_cutoff,
            or_(
                OperationRcloneDetails.log_text.isnot(None),
                OperationRcloneDetails.error_text.isnot(None),
            ),
        )
        .all()
    )
    for row in stale:
        row.log_text = None
        row.error_text = None
    return len(stale)
```

Call it from the same place the inline log clearing happens, and add its count
to whatever summary that function logs. Follow the module's `CHUNK_SIZE`
convention if the surrounding code chunks its writes.

`operation_wipe_details.dry_run_output` is the wipe equivalent and is also
log-shaped; clear it in the same pass, with the same reasoning in the comment.

- [ ] **Step 4: Protect running operation logs**

In `app/services/log_manager.py`, the running-job log protection queries a
list of legacy models for `status == "running"`. Add operations:

```python
            for op in (
                db.query(Operation)
                .filter(Operation.status == "running")
                .all()
            ):
                if op.log_file_path:
                    protected_paths.add(str(op.log_file_path))
```

and drop `PackageInstallJob` from the legacy list: its running word was
`installing`, so that entry never matched anything, and new work is an
operation. Keep the other legacy models until phase 9.

- [ ] **Step 5: Run the suites**

Run: `pytest tests/unit/test_job_history_retention.py tests/unit/test_log_manager.py -v`
Expected: PASS.

---

## Task 8: Documentation and verification

**Files:**
- Modify: `docs/architecture/job-system.md`
- Modify: `docs/api.md`
- Modify: the spec's 19.1 progress table

- [ ] **Step 1: Update `docs/architecture/job-system.md`**

Three edits:

1. In "Main Job Types", say that repository wipe, cloud mirror sync and
   hydrate, and package install are `operations` rows (`wipe`, `rclone_sync`,
   `package_install`), with `repository_wipe_jobs`, `rclone_sync_jobs`, and
   `package_install_jobs` now legacy-only tables holding pre-phase-6 history.
2. Add a short section after "Check, Prune, Compact, Archive Delete, and
   Restore Check" covering the three kinds this phase moved: that the wipe
   preview still lives in `repository_wipe_jobs` and is not a unit of work,
   that a confirmed wipe queues behind the repository lane instead of being
   rejected with a 409, that `rclone_sync` takes the `rclone` lock scope and
   not the lane, that a hydrate is an `rclone_sync` operation with
   `operation = "hydrate"` in its details row, and that `package_install`
   carries its output in the operation log file rather than two columns.
3. In "Restart Cleanup", record that an interrupted initial mirror sync is
   requeued before `OperationRunner.recover_on_startup` runs, and why.

- [ ] **Step 2: Update `docs/api.md`**

Add a section next to the phase 5 "Maintenance jobs" one, saying that
`/api/repositories/{id}/wipe-jobs/{job_id}`, the cloud mirror
`latest_sync_job`, and `/api/packages/jobs/{job_id}` now take an operation id,
that a pre-phase-6 id still resolves against its legacy table, and that the
response bodies and their status words are unchanged, including
`completed_compaction_failed`, `failed_partial`, and
`triggered_by: "initial"`.

- [ ] **Step 3: Check the Postman collection**

Phase 5 found that the collection carries no saved example responses on any
request, so nothing needed changing. Re-check with a grep for a `response`
array with entries; if it is still empty, record that and change nothing.

- [ ] **Step 4: Run `superpowers:verification-before-completion`**

At minimum:

```bash
pytest tests/unit -x -q
ruff check app tests
ruff format --check $(git diff --name-only main -- '*.py')
git diff -U0 main | grep -n '^+.*—' || echo "no em dashes added"
grep -rn "RepositoryWipeJob(\|RcloneSyncJob(\|PackageInstallJob(" app | grep -v "app/database/models.py"
```

The last grep must return nothing outside `app/database/models.py`: no code
path may construct a legacy row after this phase. Known pre-existing failures,
carried from phase 5's notes, are the order-dependent `test_source_discovery`
database scans and the `test_api_rclone.py` event-loop teardown noise in a
single-process full run. Reproduce any failure against an untouched checkout
before calling it pre-existing, and say so in the G2 report either way.

Frontend: this phase touches no frontend file. Confirm with
`git diff --stat main -- frontend` returning empty, and say so at G2 rather
than running the frontend suites.

- [ ] **Step 5: Update the spec's progress table**

Set phase 6 to `in review` in section 19.1 with the plan file, the branch, and
a Notes entry recording what was built, every deviation from this plan, and
the verification output. Then stop at gate G2 and ask the owner whether to
commit.

---

## Open questions

1. **The wipe preview stays in `repository_wipe_jobs`.** A preview has no
   spec 6.3 status (`previewed` is not one) and a `queued` operation would be
   dispatched immediately, so this plan keeps `create_preview` writing the
   legacy table and makes the confirmed wipe the operation. That leaves
   `repository_wipe_jobs` alive past phase 9, which plans to delete it: phase
   9 will need either a small dedicated preview table or a `wipe_previews`
   rename. Confirm the split, or say the preview should become an operation
   in some other status and how the runner should be kept off it.
2. **Package output lives in the operation log file, split by sentinels.**
   Spec 6.2 says `package_install` gets no extension table, and
   `operations.result` is specified as small, so `stdout` and `stderr` go to
   the log file with `===== BORG-UI PACKAGE STDOUT =====` and
   `===== BORG-UI PACKAGE STDERR =====` markers that the facade parses back
   for the route contract. The alternative is an `operation_package_details`
   extension table, which contradicts spec 6.2 and would need gate G5.
   Confirm the sentinel approach.
3. **`initial` maps to the spec 6.3 trigger `import`.** The frontend reads
   `triggered_by: "initial"` on a mirror job, and `initial` is not a trigger
   word. The mapping round-trips because the initial sync is the only rclone
   operation with that trigger. Confirm, or add `initial` to the trigger
   enumeration in spec 6.3 (a spec change, so gate G5).
4. **Wipe blocks on a queued operation, not only a running one.** The legacy
   check refused while a legacy row was `pending` or `running`, so this keeps
   the same reach: a queued check now blocks a wipe preview. The alternative
   is to let the preview through and let the lane serialize the execution.
   Confirm the stricter reading.
5. **The mirror scheduler stops running syncs itself.** After this phase it
   only enqueues, so a scheduled sync that the runner cannot start (paused
   background work, spec 7.3's `background_paused`) waits in the queue
   instead of running. `background_paused` stops `followup` and `reconcile`
   triggers only, so a `schedule` trigger is unaffected, but confirm that a
   queued-not-yet-run scheduled mirror is acceptable where the previous code
   started immediately.
6. **`repository_wipe_service._ensure_no_conflicting_operations` is a live
   bug on `main`.** It reads only the five legacy maintenance tables, which
   phase 5 stopped writing, so a wipe can currently be previewed while a
   check runs. This plan fixes it in Task 3 as part of the migration. Confirm
   that is the right home, rather than a separate fix pushed ahead of this
   phase.
