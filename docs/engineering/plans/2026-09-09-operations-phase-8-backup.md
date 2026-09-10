# Operations Phase 8: Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit at the
> end of a task; the phase has one commit gate (G2) at the end, per section
> 19.4 of the spec and `.claude/instructions.md`.

**Goal:** Move backup off `backup_jobs` onto `operations` plus the
`operation_backup_details` extension table spec 6.2 names, so every backup
(manual, retry, scheduled, plan, v2, agent) is enqueued once, dispatched by
the runner on the repository lane, recovered by it after a restart, gets its
index follow-up chain from it (spec 7.4), and appears on the Background work
board and in the Activity union like every other migrated kind, while every
HTTP response body and status word the backup routes return today stays the
same.

**Architecture:** Phase 5's facade pattern, applied to the biggest kind.
`backup_service.execute_backup` and `remote_backup_service` keep their bodies
and change only what a job id resolves to: `resolve_backup_job(db, job_id)`
returns a `BackupJobFacade` over an `Operation` and its details row for new
work, and the real `BackupJob` for an id written before this phase. Seven
creation sites collapse into one `create_backup_operation()` call. Callers
that used to run the service inline and then continue (the multi repository
schedule, the scheduler's post-backup maintenance, the plan runner, the v2
route) enqueue and then `wait_for_backup_operation()`. One thin executor,
`executors/backup.py`, calls the service for server backups or queues and
waits for the agent job for agent backups, watches the runner's cancel flag,
and turns the row's final status into an `Outcome`. Four tables that carry a
foreign key to `backup_jobs` (`agent_jobs`, `script_executions`,
`backup_plan_run_repositories`, `backup_job_retry_lineage`) gain an
operations-side link, since both dialects enforce foreign keys (`PRAGMA
foreign_keys=ON` in `app/database/database.py`).

**Tech Stack:** FastAPI, SQLAlchemy 1.x declarative models, Alembic, asyncio
subprocesses in the existing service, `BorgRouter`, the agent transport in
`app/api/agents.py`, pytest with the `test_db` / `test_client` /
`admin_headers` fixtures from `tests/fixtures/api.py` and the in-memory `db`
fixture pattern from `tests/unit/test_operations_restore_facade.py`.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`,
sections 6.1, 6.2, 6.3, 7.1 to 7.8, 9.3, 13 (phase 8 row), 14, 15 ("Backup
migration scope"), Appendix B. Review focus (19.3): 6.2, 6.3, 7.4, 7.6, the
backup service, Appendix B.

## Model

Section 13 gives phase 8 Fable 5.1 for both implementation and review ("Thirty
five columns, three creation sites, and every integration hangs off it").
This plan was drafted on Fable 5.1 on 2026-09-09, so gate G0 passed without a
deviation. The review wants a fresh Fable 5.1 session.

## Global Constraints

- Phase 8 is backend only. No frontend file changes, no i18n keys, no
  stories. Every HTTP response body keeps the exact shape and the exact
  status vocabulary it has today, per section 13 ("Phases 5 through 9 are
  internal refactors with no visible change except fewer lock errors") and
  section 15 ("The extension table exists precisely so backup columns move,
  not change. Behavioural changes to backups are out of scope"). The
  load-bearing contracts, pinned by tests in this phase: `POST
  /api/backup/start` and `/run` answer `{"job_id", "status": "pending",
  "message": "Backup job started"}`; `POST /api/backup/jobs/{id}/retry`
  answers `{"job_id", "status", "message", retry_attempt,
  retry_original_job_id, retry_source_job_id, retry_requested_by_user_id,
  retry_requested_at}` with 202; `GET /api/backup/jobs` and
  `/api/backup/status/{id}` answer the field set `app/api/backup.py:664-700`
  and `:721-745` build today, including `maintenance_status`,
  `triggered_by`, `execution_mode` (`local`, `remote_ssh`, `agent`),
  `route_strategy`, `archive_pruned_at`, the retry fields, and
  `progress_details` from `serialize_backup_progress_details`; `POST
  /api/backup/cancel/{id}` answers `{"message", "process_terminated"}`; the
  status words are `pending`, `running`, `completed`,
  `completed_with_warnings`, `failed`, `cancelled`; `POST /api/v2/backups/run`
  answers `{"success", "stats", "status", "job_id"}`; backup plan run
  payloads keep `backup_job` as `_serialize_backup_job` builds it.
- Spec 6.2 is the column list for `operation_backup_details`, keyed on
  `operations.id` with `ondelete="CASCADE"`, plus one column the list
  predates and the routes return: `archive_pruned_at` (Open question 1).
  `progress` (an int) and `progress_percent` are both
  `operations.progress_percent`; `logs` is the operation's log file (spec
  6.1); `repository` (a path) becomes `repository_id`; `backup_plan_id` is
  derived from `backup_plan_run_id`; `scheduled_job_id` and
  `backup_plan_run_id` are the spec 6.1 columns; the legacy `execution_mode`
  word `local` is stored as the spec 6.1 word `server` and translated back
  by the facade (Open question 8).
- Spec 6.3 is verbatim and already in `vocab.py`: `backup` is category
  `backup`, exclusive, and the mapping `running_prune` / `running_compact`
  means `running` on the child prune or compact operation while the backup
  itself is `completed`. Do not edit `vocab.py`.
- Spec 7.4 is verbatim and already in `followups.py`: the runner creates
  the `backup` chain (`archive_sync`, `history_merge`, `history_index`,
  `stats`) when the backup succeeds. The two `_enqueue_index_followups`
  calls in `backup_service.py` and the `enqueue_backup_followups` call in
  `app/api/agents.py` stop firing for operations (they were the interim
  path 7.4 describes). Do not edit the `FOLLOWUPS` table.
- Spec 7.3: the runner already applies `max_concurrent_backups` and
  `max_concurrent_scheduled_backups` by trigger in `lanes.py`. The route
  level 409s (`ensure_manual_backup_capacity`, `ensure_repository_admission`)
  stay where they are and learn to count backup operations (Open question 7).
- Nothing in this phase writes a new row to `backup_jobs`. After this
  phase, `grep -rn "BackupJob(" app/ tests/unit/` matches only
  `app/database/models.py` and `tests/unit/test_repository_deletion.py`.
  `AgentJob.backup_job_id`,
  `ScriptExecution.backup_job_id`, and
  `BackupPlanRunRepository.backup_job_id` are written only when the linked
  job is a legacy row, which no production path produces after this phase.
- Numeric job ids stay unqualified while both worlds coexist: an
  `operations` row wins over a legacy row of the same kind with the same id
  on every by-id route (Appendix B).
- No em dashes anywhere: code comments, docstrings, docs, or commit message.
  Check added lines only, with `git diff -U0 origin/main | grep -nP '\xe2\x80\x94'`.
- One commit at the end of the phase, at gate G2, after
  `superpowers:verification-before-completion` passes. Nothing is pushed
  without the owner's answer at that gate.
- Before writing the migration, confirm the parent is the single head.
  Run, from the repository root: `alembic heads` (or `python3 -m alembic
  heads` when the console script is not on the path). Expected: exactly
  `f7a8b9c0d1e2 (head)`. If another head appeared, re-parent onto it and
  record it in the spec's Notes column, as phases 6 and 7 did.

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `app/database/alembic/versions/b8c9d0e1f2a3_add_operation_backup_details.py` | The one migration: the details table, the lineage table, and the three link columns. |
| `app/services/operations/backup_facade.py` | `BackupJobFacade`, `resolve_backup_job`, `refresh_backup_job`, `create_backup_operation`, `wait_for_backup_operation`, the union query helpers, the cancel message constants. |
| `app/services/operations/executors/backup.py` | `run_backup`. |
| `tests/unit/test_operations_backup_facade.py` | Facade round trips, id resolution, creation, the union helpers. |
| `tests/unit/test_operations_backup_executor.py` | The executor. |

**Modified**

| File | Change |
| --- | --- |
| `app/database/models.py` | `OperationBackupDetails`, `OperationBackupRetryLineage`; `AgentJob.operation_id`, `ScriptExecution.operation_id`, `BackupPlanRunRepository.backup_operation_id` and its relationship. |
| `app/services/operations/details.py` | `backup_details(db, operation)`. |
| `app/services/operations/executors/__init__.py` | Register `backup`. |
| `app/services/operations/maintenance_start.py` | `start_inline_maintenance` takes `run_id` and `depends_on_id`. |
| `app/services/operations/followups.py` | Docstring of `enqueue_backup_followups`. |
| `app/services/operations/lanes.py` | `write_maintenance_running` sees details rows. |
| `app/services/backup_service.py` | Five lookups and three refreshes through the facade module; the two follow-up calls removed. |
| `app/services/remote_backup_service.py` | Six lookups through `resolve_backup_job`. |
| `app/services/repository_executor.py` | `queue_agent_backup_job`, `get_agent_job_for_backup`, `cancel_agent_backup_job`, `wait_for_agent_backup_job` operation-aware. |
| `app/services/script_library_executor.py` | `ScriptExecution` link columns; the SSH connection lookup. |
| `app/services/job_admission.py` | Backup operations are active work; the two capacity counts. |
| `app/services/agent_job_reaper.py` | Reaps the linked operation. |
| `app/services/job_history_retention.py` | Lineage purge; `mark_jobs_of_pruned_archives` marks details rows. |
| `app/services/mqtt_service.py`, `app/api/metrics.py`, `app/api/dashboard.py`, `app/services/backup_monitoring_service.py`, `app/utils/archive_job_metadata.py` | Read the union through the facade helpers. |
| `app/api/backup.py`, `app/api/v2/backups.py` | Routes enqueue; by-id routes resolve either id space; list route unions. |
| `app/api/schedule.py` | Three creation sites enqueue; the maintenance runner waits for the operation. |
| `app/services/backup_plan_execution_service.py` | `_execute_repository` enqueues and waits; `_run_maintenance` children join the run. |
| `app/api/agents.py` | Linked backup resolves through `operation_id`; the start guard moves to the agent job row. |
| `app/api/activity.py` | `backup` becomes an operation-first kind; the legacy shape for backup operations. |
| `app/api/ssh_keys.py` | Connection deletion nulls the details row. |
| `app/api/backup_plans.py` | `_serialize_backup_job` gets the facade. |
| `app/utils/process_utils.py` | Stale maintenance sweep covers details rows; comments on the legacy backup branch. |
| `docs/architecture/job-system.md`, `docs/api.md` | Task 9. |
| `tests/unit/test_operations_details.py`, `test_api_backup.py`, `test_api_v2_backups.py`, `test_backup_service.py`, `test_api_schedule_routes.py`, `test_api_backup_plans.py`, `test_api_agents.py`, `test_agent_job_dispatcher.py`, `test_api_activity.py`, `test_activity_union.py`, `test_mqtt_service.py`, `test_api_metrics.py`, `test_api_dashboard.py`, `test_backup_monitoring_service.py`, `test_job_history_retention.py`, `test_api_ssh_keys.py`, `test_operations_lanes.py`, `test_utils.py` | Extended per task. |

---

## Task 1: Schema

**Files:**
- Create: `app/database/alembic/versions/b8c9d0e1f2a3_add_operation_backup_details.py`
- Modify: `app/database/models.py` (`AgentJob` at line 165, `BackupPlanRunRepository` at 1221, after `class OperationRestoreDetails`, `ScriptExecution` at 2241)
- Modify: `app/services/operations/details.py`
- Test: `tests/unit/test_operations_details.py`

**Interfaces:**
- Consumes: `Operation`, `_get_or_create` in `details.py`.
- Produces: `OperationBackupDetails`, `OperationBackupRetryLineage`,
  `AgentJob.operation_id`, `ScriptExecution.operation_id`,
  `BackupPlanRunRepository.backup_operation_id` plus the relationship
  `backup_operation`; `details.backup_details(db, operation) ->
  OperationBackupDetails`, get-or-create, flushing. Tasks 2 onward use only
  this function to reach the row.

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_operations_details.py`, and extend the helper's
category line to `{"wipe": "maintenance", "restore": "restore", "backup":
"backup"}.get(kind, "mirror")`:

```python
def test_backup_details_is_created_once_per_operation(db, repository):
    from app.database.models import OperationBackupDetails
    from app.services.operations.details import backup_details

    op = _operation(db, repository, "backup")

    first = backup_details(db, op)
    first.archive_name = "nas-2026-09-09"
    first.original_size = 3 * 1024**3
    first.maintenance_status = "running_prune"
    second = backup_details(db, op)

    assert first.operation_id == op.id
    assert second is first
    assert second.archive_name == "nas-2026-09-09"
    assert second.original_size == 3 * 1024**3
    assert second.retry_attempt == 1
    assert db.query(OperationBackupDetails).count() == 1


def test_backup_details_row_is_deleted_with_its_operation(db, repository):
    from app.database.models import OperationBackupDetails
    from app.services.operations.details import backup_details

    op = _operation(db, repository, "backup")
    backup_details(db, op)
    db.commit()

    db.delete(op)
    db.commit()

    assert db.query(OperationBackupDetails).count() == 0


def test_agent_job_and_script_execution_link_to_an_operation(db, repository):
    from app.database.models import AgentJob, AgentMachine, ScriptExecution

    op = _operation(db, repository, "backup")
    machine = AgentMachine(
        agent_id="agent-1", name="agent", enrollment_token_id=None, status="online"
    )
    db.add(machine)
    db.flush()
    db.add(
        AgentJob(
            agent_machine_id=machine.id,
            operation_id=op.id,
            job_type="backup",
            status="queued",
            payload={},
        )
    )
    db.add(
        ScriptExecution(
            operation_id=op.id,
            hook_type="pre-backup",
            status="completed",
            triggered_by="backup",
        )
    )
    db.commit()

    db.delete(op)
    db.commit()

    assert db.query(ScriptExecution).count() == 0
    assert db.query(AgentJob).one().operation_id is None
```

If `AgentMachine` needs more required columns than shown, copy the minimal
constructor `tests/unit/test_api_agents.py` uses.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_details.py -v`
Expected: the three new tests FAIL (`ImportError` on `backup_details`,
`TypeError` on the unknown `operation_id` keyword).

- [x] **Step 3: Add the models and the link columns**

In `app/database/models.py`, directly after `class OperationRestoreDetails`:

```python
class OperationBackupDetails(Base):
    """Backup-specific columns for an `operations` row. Spec section 6.2.

    `archive_pruned_at` is not in the spec's list: the legacy column was
    added after the spec was written (migration a5b7c9d1e3f2) and the routes
    return it. `progress` and `progress_percent` are both
    `operations.progress_percent`; `logs` is the operation's log file;
    `backup_plan_id` is derived from `operations.backup_plan_run_id`. The
    three retry ids are unqualified job ids (Appendix B): a retry of a row
    written before phase 8 names a `backup_jobs` id, so they carry no
    foreign key.
    """

    __tablename__ = "operation_backup_details"

    operation_id = Column(
        Integer,
        ForeignKey("operations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    archive_name = Column(String, nullable=True)
    archive_pruned_at = Column(DateTime, nullable=True)
    original_size = Column(BigInteger, default=0)
    compressed_size = Column(BigInteger, default=0)
    deduplicated_size = Column(BigInteger, default=0)
    nfiles = Column(Integer, default=0)
    current_file = Column(Text, nullable=True)
    backup_speed = Column(Float, default=0.0)
    total_expected_size = Column(BigInteger, default=0)
    estimated_time_remaining = Column(Integer, default=0)
    route_strategy = Column(String, nullable=True)
    source_ssh_connection_id = Column(
        Integer, ForeignKey("ssh_connections.id", ondelete="SET NULL"), nullable=True
    )
    remote_process_pid = Column(Integer, nullable=True)
    remote_hostname = Column(String, nullable=True)
    retry_original_job_id = Column(Integer, nullable=True)
    retry_source_job_id = Column(Integer, nullable=True)
    retry_attempt = Column(Integer, default=1, nullable=False)
    retry_requested_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    retry_requested_at = Column(DateTime, nullable=True)
    maintenance_status = Column(String, nullable=True)


class OperationBackupRetryLineage(Base):
    """The retry audit row `BackupJobRetryLineage` kept, for backups that are
    operations. The three ids are unqualified job ids like the details row's
    retry columns, so they carry no foreign key; retention drops rows by
    `requested_at` as it does for the legacy table."""

    __tablename__ = "operation_backup_retry_lineage"
    __table_args__ = (
        UniqueConstraint(
            "created_operation_id", name="uq_operation_backup_retry_created"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    original_job_id = Column(Integer, nullable=True, index=True)
    retry_source_job_id = Column(Integer, nullable=True, index=True)
    attempt_number = Column(Integer, nullable=False)
    requested_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_at = Column(DateTime, default=utc_now, nullable=False)
    created_operation_id = Column(Integer, nullable=True, index=True)
    request_snapshot = Column(JSON, nullable=False)
```

In `class AgentJob`, after `backup_job_id`:

```python
    # Phase 8: the backup this job transports, when the backup is an
    # operation. `backup_job_id` stays for rows written before the phase.
    operation_id = Column(
        Integer,
        ForeignKey("operations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

In `class ScriptExecution`, after `backup_job_id`:

```python
    operation_id = Column(
        Integer,
        ForeignKey("operations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
```

In `class BackupPlanRunRepository`, after `backup_job_id` and the
relationships:

```python
    backup_operation_id = Column(
        Integer, ForeignKey("operations.id", ondelete="SET NULL"), nullable=True
    )
    ...
    backup_operation = relationship("Operation")
```

- [x] **Step 4: Extend the details helper**

In `app/services/operations/details.py`, import `OperationBackupDetails`,
change the docstring's first paragraph to "Wipe, rclone sync, restore, and
backup have one." and append:

```python
def backup_details(db: Session, operation: Operation) -> OperationBackupDetails:
    return _get_or_create(db, OperationBackupDetails, operation)
```

- [x] **Step 5: Write the migration**

Create `app/database/alembic/versions/b8c9d0e1f2a3_add_operation_backup_details.py`:

```python
"""add operation backup extension tables and links

Revision ID: b8c9d0e1f2a3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operation_backup_details",
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("archive_name", sa.String(), nullable=True),
        sa.Column("archive_pruned_at", sa.DateTime(), nullable=True),
        sa.Column("original_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column("compressed_size", sa.BigInteger(), nullable=True, server_default="0"),
        sa.Column(
            "deduplicated_size", sa.BigInteger(), nullable=True, server_default="0"
        ),
        sa.Column("nfiles", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("current_file", sa.Text(), nullable=True),
        sa.Column("backup_speed", sa.Float(), nullable=True, server_default="0"),
        sa.Column(
            "total_expected_size", sa.BigInteger(), nullable=True, server_default="0"
        ),
        sa.Column(
            "estimated_time_remaining", sa.Integer(), nullable=True, server_default="0"
        ),
        sa.Column("route_strategy", sa.String(), nullable=True),
        sa.Column(
            "source_ssh_connection_id",
            sa.Integer(),
            sa.ForeignKey("ssh_connections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("remote_process_pid", sa.Integer(), nullable=True),
        sa.Column("remote_hostname", sa.String(), nullable=True),
        sa.Column("retry_original_job_id", sa.Integer(), nullable=True),
        sa.Column("retry_source_job_id", sa.Integer(), nullable=True),
        sa.Column("retry_attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "retry_requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("retry_requested_at", sa.DateTime(), nullable=True),
        sa.Column("maintenance_status", sa.String(), nullable=True),
    )
    op.create_table(
        "operation_backup_retry_lineage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("original_job_id", sa.Integer(), nullable=True),
        sa.Column("retry_source_job_id", sa.Integer(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("created_operation_id", sa.Integer(), nullable=True),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "created_operation_id", name="uq_operation_backup_retry_created"
        ),
    )
    for name in ("id", "original_job_id", "retry_source_job_id", "requested_by_user_id", "created_operation_id"):
        op.create_index(
            f"ix_operation_backup_retry_lineage_{name}",
            "operation_backup_retry_lineage",
            [name],
        )
    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.add_column(sa.Column("operation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_jobs_operation_id_operations",
            "operations",
            ["operation_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_agent_jobs_operation_id", ["operation_id"])
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.add_column(sa.Column("operation_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_script_executions_operation_id_operations",
            "operations",
            ["operation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_script_executions_operation_id", ["operation_id"])
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.add_column(
            sa.Column("backup_operation_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_backup_plan_run_repositories_backup_operation_id_operations",
            "operations",
            ["backup_operation_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.drop_constraint(
            "fk_backup_plan_run_repositories_backup_operation_id_operations",
            type_="foreignkey",
        )
        batch_op.drop_column("backup_operation_id")
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.drop_index("ix_script_executions_operation_id")
        batch_op.drop_constraint(
            "fk_script_executions_operation_id_operations", type_="foreignkey"
        )
        batch_op.drop_column("operation_id")
    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.drop_index("ix_agent_jobs_operation_id")
        batch_op.drop_constraint(
            "fk_agent_jobs_operation_id_operations", type_="foreignkey"
        )
        batch_op.drop_column("operation_id")
    op.drop_table("operation_backup_retry_lineage")
    op.drop_table("operation_backup_details")
```

- [x] **Step 6: Run the tests and the migration end to end**

Run: `pytest tests/unit/test_operations_details.py tests/unit/test_db_upgrade.py -v`
Expected: PASS.

Run, against a scratch database:

```bash
export DATABASE_URL=sqlite:////tmp/phase8-scratch.db
alembic upgrade head && alembic heads && alembic downgrade -1 && alembic upgrade head
unset DATABASE_URL
```

Expected: every step succeeds, `alembic heads` prints exactly
`b8c9d0e1f2a3 (head)`. Delete `/tmp/phase8-scratch.db` afterwards.

---

## Task 2: The backup facade module

**Files:**
- Create: `app/services/operations/backup_facade.py`
- Test: `tests/unit/test_operations_backup_facade.py`

**Interfaces:**
- Consumes: `backup_details` (Task 1), `Operation`, `Repository`,
  `BackupJob`, `BackupPlanRun`, `OperationBackupDetails`,
  `operation_log_path` and `operation_runner` from `runner.py`, `enqueue`
  and `wake_runner` from `enqueue.py`, `apply_repository_route_to_backup_job`
  from `backup_route_planner.py`, `IgnoreActiveJob` from `job_admission.py`.
- Produces (every later task uses exactly these names):
  - `BackupJobFacade(db, operation)`: the attribute surface
    `backup_service.py`, `remote_backup_service.py`, `app/api/backup.py`,
    `app/api/agents.py`, `schedule.py`, and the plan runner read and write:
    `id`, `kind`, `operation`, `details`, `repository` (path, read only),
    `repository_id`, `backup_plan_id` (read only), `backup_plan_run_id`,
    `scheduled_job_id`, `triggered_by`, `status`, `started_at`,
    `completed_at`, `error_message`, `progress`, `progress_percent`,
    `execution_mode`, `logs`, `log_file_path`, `created_at`, `current_file`,
    plus every `OperationBackupDetails` column as a plain attribute.
  - `is_backup_operation(job) -> bool`.
  - `resolve_backup_job(db, job_id) -> BackupJobFacade | BackupJob | None`.
  - `refresh_backup_job(db, job) -> None`.
  - `create_backup_operation(db, repository, *, trigger, executor, params=None,
    user_id=None, scheduled_job_id=None, backup_plan_run_id=None,
    retry=None, repository_path=None, commit=True) -> BackupJobFacade`.
  - `wait_for_backup_operation(db, operation_id, *, is_cancelled=None,
    poll_interval_seconds=0.5) -> str` (a legacy status word).
  - `admission_ignore_for(job) -> IgnoreActiveJob`.
  - `backup_job_link_columns(db, job_id) -> dict` with keys
    `backup_job_id` and `operation_id`, one of them set.
  - `backup_job_has_logs(db, job, *, log_save_policy=None) -> bool`.
  - `list_backup_jobs(db, limit, *, scheduled_only=False, manual_only=False,
    repository_path=None) -> list`.
  - `backup_jobs_started_since(db, since, *, until=None, limit=None) -> list`
    newest `started_at` first.
  - `latest_backup_job_for_repository(db, repository, *, statuses=None,
    order="created") -> job | None` where `order` is `created` or
    `completed` (the latter requires both timestamps).
  - `backup_jobs_for_archive_names(db, repository, names) -> list` newest
    first.
  - `latest_backup_jobs_by_repository(db, *, running=False) -> dict[str, job]`
    keyed by repository path.
  - `newest_backup_job(db, *, running=False, terminal=False) -> job | None`.
  - `backup_jobs_in_maintenance(db) -> list` (details rows and legacy rows
    whose `maintenance_status` is a `running_*` word).
  - Constants `CANCELLED_BY_USER`, `CANCELLED_PROCESS_NOT_FOUND`,
    `CANCEL_MESSAGES`, `POST_CREATE_FAILURE_KEYS`, `SERVICE_PARAMS`,
    `AGENT_PARAMS`.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_operations_backup_facade.py`:

```python
"""Phase 8: an `operations` row wearing the legacy backup-job surface."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupJob,
    BackupPlan,
    BackupPlanRun,
    Base,
    Operation,
    Repository,
)
from app.services.operations.backup_facade import (
    BackupJobFacade,
    backup_jobs_for_archive_names,
    backup_jobs_started_since,
    create_backup_operation,
    latest_backup_jobs_by_repository,
    list_backup_jobs,
    newest_backup_job,
    resolve_backup_job,
    wait_for_backup_operation,
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


@pytest.fixture()
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return tmp_path / "logs"


def _backup_operation(db, repository, status="queued", trigger="manual", **kw):
    op = Operation(
        repository_id=repository.id if repository is not None else None,
        kind="backup",
        category="backup",
        status=status,
        trigger=trigger,
        priority=0,
        run_id="run-1",
        params={"executor": "server"},
        **kw,
    )
    db.add(op)
    db.commit()
    return op


def test_facade_maps_status_words_and_progress(db, repository):
    op = _backup_operation(db, repository)
    job = BackupJobFacade(db, op)

    assert job.status == "pending"
    assert job.repository == "/repo/nas"
    assert job.execution_mode == "local"
    assert job.triggered_by == "manual"
    assert job.retry_attempt == 1

    job.status = "running"
    job.progress = 42
    job.progress_percent = 42.5
    job.current_file = "/home/k/docs"
    job.execution_mode = "local"
    db.commit()

    assert op.status == "running"
    assert op.progress_percent == 42.5
    assert job.progress == 42
    assert op.progress_message == "/home/k/docs"
    assert op.execution_mode == "server"


def test_detail_columns_land_on_the_details_row(db, repository):
    op = _backup_operation(db, repository)
    job = BackupJobFacade(db, op)
    job.archive_name = "nas-2026-09-09"
    job.original_size = 5
    job.maintenance_status = "running_prune"
    job.remote_hostname = "box"
    db.commit()

    again = BackupJobFacade(db, db.get(Operation, op.id))
    assert again.archive_name == "nas-2026-09-09"
    assert again.original_size == 5
    assert again.maintenance_status == "running_prune"
    assert again.remote_hostname == "box"
    with pytest.raises(AttributeError):
        again.no_such_column


def test_backup_plan_id_is_derived_from_the_run(db, repository):
    plan = BackupPlan(name="nightly")
    db.add(plan)
    db.flush()
    run = BackupPlanRun(backup_plan_id=plan.id, trigger="manual", status="running")
    db.add(run)
    db.flush()
    op = _backup_operation(db, repository, trigger="plan", backup_plan_run_id=run.id)
    job = BackupJobFacade(db, op)

    assert job.backup_plan_id == plan.id
    assert job.triggered_by == "backup_plan"


def test_logs_go_to_the_operation_log_file(db, repository, log_dir):
    op = _backup_operation(db, repository)
    job = BackupJobFacade(db, op)

    job.logs = "line one\nline two"
    db.commit()

    assert op.log_file_path == str(log_dir / f"operation_{op.id}.log")
    assert job.logs == "line one\nline two"

    job.logs = "Logs saved to: something.log"
    assert job.logs == "line one\nline two"


def test_resolve_prefers_the_operation_and_falls_back_to_legacy(db, repository):
    legacy = BackupJob(repository="/repo/nas", status="completed")
    db.add(legacy)
    db.commit()
    op = _backup_operation(db, repository)

    assert isinstance(resolve_backup_job(db, op.id), BackupJobFacade)
    assert resolve_backup_job(db, legacy.id + 1000) is None
    if legacy.id != op.id:
        assert resolve_backup_job(db, legacy.id) is legacy


def test_create_backup_operation_records_route_and_params(db, repository):
    repository.source_ssh_connection_id = None
    job = create_backup_operation(
        db,
        repository,
        trigger="schedule",
        executor="server",
        params={"archive_name": "nas-{now}", "skip_hooks": None},
        scheduled_job_id=None,
    )

    op = db.get(Operation, job.id)
    assert op.kind == "backup"
    assert op.trigger == "schedule"
    assert op.priority == 5
    assert op.params == {"archive_name": "nas-{now}", "executor": "server"}
    assert op.execution_mode == "server"
    assert job.route_strategy is not None


def test_create_backup_operation_without_a_repository_keeps_the_path(db):
    job = create_backup_operation(
        db, None, trigger="manual", executor="server", repository_path="/nowhere",
        commit=False,
    )
    job.status = "failed"
    db.commit()

    assert job.repository == "/nowhere"
    assert job.repository_id is None
    assert db.get(Operation, job.id).status == "failed"


@pytest.mark.asyncio
async def test_wait_for_backup_operation_returns_the_legacy_word(db, repository):
    op = _backup_operation(db, repository, status="running")

    async def _finish():
        op.status = "completed_with_warnings"
        db.commit()

    import asyncio

    asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(_finish()))
    assert (
        await wait_for_backup_operation(db, op.id, poll_interval_seconds=0.01)
        == "completed_with_warnings"
    )


def test_list_backup_jobs_unions_both_tables_newest_first(db, repository):
    old = BackupJob(
        repository="/repo/nas",
        status="completed",
        created_at=datetime(2026, 9, 1),
    )
    db.add(old)
    db.commit()
    op = _backup_operation(db, repository, status="completed")
    op.created_at = datetime(2026, 9, 9)
    db.commit()

    jobs = list_backup_jobs(db, 10)
    assert [j.id for j in jobs] == [op.id, old.id]
    assert list_backup_jobs(db, 10, manual_only=True)[0].id == op.id
    assert list_backup_jobs(db, 10, scheduled_only=True) == []
    assert list_backup_jobs(db, 10, repository_path="/other") == []


def test_started_since_archive_names_and_per_repository_helpers(db, repository):
    now = datetime.utcnow()
    legacy = BackupJob(
        repository="/repo/nas",
        repository_id=repository.id,
        status="completed",
        archive_name="nas-old",
        started_at=now - timedelta(days=3),
        created_at=now - timedelta(days=3),
    )
    db.add(legacy)
    db.commit()
    op = _backup_operation(db, repository, status="running")
    op.started_at = now - timedelta(hours=1)
    job = BackupJobFacade(db, op)
    job.archive_name = "nas-new"
    db.commit()

    recent = backup_jobs_started_since(db, now - timedelta(days=7))
    assert [j.id for j in recent] == [op.id, legacy.id]
    assert backup_jobs_started_since(db, now - timedelta(days=1))[0].id == op.id

    by_name = backup_jobs_for_archive_names(db, repository, {"nas-old", "nas-new"})
    assert {j.archive_name for j in by_name} == {"nas-old", "nas-new"}

    latest = latest_backup_jobs_by_repository(db)
    assert latest["/repo/nas"].id == op.id
    assert latest_backup_jobs_by_repository(db, running=True)["/repo/nas"].id == op.id
    assert newest_backup_job(db, running=True).id == op.id
    assert newest_backup_job(db, terminal=True).id == legacy.id
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_backup_facade.py -v`
Expected: FAIL at import (`ModuleNotFoundError`).

- [x] **Step 3: Write the module**

Create `app/services/operations/backup_facade.py`:

```python
"""An `operations` row (plus its spec 6.2 details row) wearing the legacy
backup-job attribute surface, and the one place every backup is created.

`backup_service`, `remote_backup_service`, the backup routes, the agent
transport, the scheduler and the plan runner drive a backup through a fixed
set of attributes. Phase 8 moves the row to `operations` without rewriting
them: `resolve_backup_job()` hands them this facade for new work and the real
`BackupJob` for an id written before this phase.

Translations, all in one place:
- `status`: the legacy word `pending` is the operations word `queued`.
- `execution_mode`: the legacy word `local` is the spec 6.1 word `server`.
- `progress` (an int) and `progress_percent` are both
  `operations.progress_percent`.
- `logs`, which the services assign once at the end, is the operation's log
  file (spec 6.1); the marker text "Logs saved to: ..." the local service
  writes when it kept its own file is dropped, since the row already names
  the file.
- `repository` is the path of `repository_id`, or `params["repository"]`
  for the one legacy case with no repository (an unknown path submitted to
  the manual start route, recorded and failed at once).
- `backup_plan_id` is read through `backup_plan_run_id`.

Deleted in phase 9 with the legacy table.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database.models import (
    BackupJob,
    BackupPlanRun,
    Operation,
    OperationBackupDetails,
    Repository,
)
from app.services.operations.details import backup_details
from app.services.operations.vocab import TERMINAL_STATUSES

CANCELLED_BY_USER = json.dumps({"key": "backend.errors.backup.cancelledByUser"})
CANCELLED_PROCESS_NOT_FOUND = json.dumps(
    {"key": "backend.errors.backup.cancelledByUserProcessNotFound"}
)
CANCEL_MESSAGES = (CANCELLED_BY_USER, CANCELLED_PROCESS_NOT_FOUND)

# A backup whose `borg create` succeeded and whose row still ended `failed`
# because a post-backup hook failed. The archive exists, so the executor
# enqueues the index chain itself (Appendix B, phase 6 precedent for a
# failure that changed the repository).
POST_CREATE_FAILURE_KEYS = frozenset(
    {
        "backend.errors.service.postBackupHooksFailed",
        "backend.errors.service.backupWarningPostHooksFailed",
    }
)

# `params` keys handed to `backup_service.execute_backup` by name.
SERVICE_PARAMS = (
    "archive_name",
    "skip_hooks",
    "source_directories",
    "source_ssh_connection_id",
    "source_locations",
    "exclude_patterns_override",
    "compression_override",
    "custom_flags_override",
    "upload_ratelimit_kib",
)
# `params` keys handed to `queue_agent_backup_job`, mapped to its names.
AGENT_PARAMS = {
    "archive_name": "archive_name",
    "source_directories": "source_directories",
    "source_locations": "source_locations",
    "exclude_patterns_override": "exclude_patterns",
    "compression_override": "compression",
    "custom_flags_override": "custom_flags",
    "upload_ratelimit_kib": "upload_ratelimit_kib",
}

RUNNING_MAINTENANCE_WORDS = ("running_prune", "running_compact", "running_check")

_LEGACY_TO_OPERATION_MODE = {"local": "server"}
_OPERATION_TO_LEGACY_MODE = {"server": "local", None: "local"}

# Columns that live on the details row and need no translation.
# `current_file` is not here: it mirrors into `progress_message`.
_DETAIL_FIELDS = tuple(
    column.name
    for column in OperationBackupDetails.__table__.columns
    if column.name not in ("operation_id", "current_file")
)


class BackupJobFacade:
    """One `Operation` presented as a legacy backup job row."""

    def __init__(self, db: Session, operation: Operation):
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "details", backup_details(db, operation))

    def __setattr__(self, name: str, value) -> None:
        if name in _DETAIL_FIELDS:
            setattr(object.__getattribute__(self, "details"), name, value)
            return
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        if name in _DETAIL_FIELDS:
            return getattr(object.__getattribute__(self, "details"), name)
        raise AttributeError(f"backup operations carry no {name!r}")

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
        if self.operation.repository_id is None:
            return (self.operation.params or {}).get("repository")
        repository = self._db.get(Repository, self.operation.repository_id)
        return repository.path if repository is not None else None

    @property
    def scheduled_job_id(self) -> Optional[int]:
        return self.operation.scheduled_job_id

    @property
    def backup_plan_run_id(self) -> Optional[int]:
        return self.operation.backup_plan_run_id

    @property
    def backup_plan_id(self) -> Optional[int]:
        if self.operation.backup_plan_run_id is None:
            return None
        run = self._db.get(BackupPlanRun, self.operation.backup_plan_run_id)
        return run.backup_plan_id if run is not None else None

    @property
    def triggered_by(self) -> str:
        if self.operation.backup_plan_run_id:
            return "backup_plan"
        return "schedule" if self.operation.scheduled_job_id else "manual"

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

    @property
    def execution_mode(self) -> str:
        mode = self.operation.execution_mode
        return _OPERATION_TO_LEGACY_MODE.get(mode, mode)

    @execution_mode.setter
    def execution_mode(self, value) -> None:
        self.operation.execution_mode = _LEGACY_TO_OPERATION_MODE.get(value, value)

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
        return self.details.current_file

    @current_file.setter
    def current_file(self, value) -> None:
        self.details.current_file = value
        self.operation.progress_message = value or None

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
        from app.services.operations.runner import operation_log_path

        if value is None or str(value).startswith("Logs saved to:"):
            return
        path = (
            Path(self.operation.log_file_path)
            if self.operation.log_file_path
            else operation_log_path(self.operation.id)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(value), encoding="utf-8")
        self.operation.log_file_path = str(path)


def is_backup_operation(job: Any) -> bool:
    return isinstance(job, BackupJobFacade)


def resolve_backup_job(db: Session, job_id: int) -> Any:
    """The job a backup caller should drive for `job_id`. Operations win;
    ids from before this phase fall back to the legacy table."""
    operation = (
        db.query(Operation)
        .filter(Operation.id == job_id, Operation.kind == "backup")
        .first()
    )
    if operation is not None:
        return BackupJobFacade(db, operation)
    return db.query(BackupJob).filter(BackupJob.id == job_id).first()


def refresh_backup_job(db: Session, job: Any) -> None:
    """`db.refresh(job)` for either shape: a facade refreshes its two rows."""
    if is_backup_operation(job):
        db.refresh(job.operation)
        db.refresh(job.details)
    else:
        db.refresh(job)


def admission_ignore_for(job: Any):
    from app.services.job_admission import ignore_active_job

    table = Operation.__tablename__ if is_backup_operation(job) else BackupJob.__tablename__
    return ignore_active_job(table, job.id)


def backup_job_link_columns(db: Session, job_id: Optional[int]) -> dict:
    """Which link column a row pointing at backup `job_id` should fill."""
    if job_id is None:
        return {"backup_job_id": None, "operation_id": None}
    if is_backup_operation(resolve_backup_job(db, job_id)):
        return {"backup_job_id": None, "operation_id": job_id}
    return {"backup_job_id": job_id, "operation_id": None}


def create_backup_operation(
    db: Session,
    repository: Optional[Repository],
    *,
    trigger: str,
    executor: str,
    params: Optional[dict] = None,
    user_id: Optional[int] = None,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    retry: Optional[dict] = None,
    repository_path: Optional[str] = None,
    commit: bool = True,
) -> BackupJobFacade:
    """The one creation site (spec 7.1). `executor` is `server` or `agent`
    and decides which path `run_backup` takes. `params` are the
    `execute_backup` keyword arguments the caller wants passed through
    (`SERVICE_PARAMS`); None values are dropped so a service default is not
    shadowed. `retry` holds the details row's retry columns. With
    `repository` None the caller passes the path it was given and is
    expected to fail the row itself before committing."""
    from app.services.backup_route_planner import apply_repository_route_to_backup_job
    from app.services.operations.enqueue import enqueue, wake_runner

    stored = {k: v for k, v in (params or {}).items() if v is not None}
    stored["executor"] = executor
    if repository is None:
        stored["repository"] = repository_path
    operation = enqueue(
        db,
        "backup",
        repository_id=repository.id if repository is not None else None,
        trigger=trigger,
        params=stored,
        triggered_by_user_id=user_id,
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
        commit=False,
    )
    job = BackupJobFacade(db, operation)
    job.source_ssh_connection_id = (
        repository.source_ssh_connection_id if repository is not None else None
    )
    if repository is not None and executor == "agent":
        job.execution_mode = "agent"
    elif repository is not None:
        apply_repository_route_to_backup_job(job, repository)
    else:
        job.execution_mode = "local"
    for name, value in (retry or {}).items():
        setattr(job, name, value)
    if commit:
        db.commit()
        db.refresh(operation)
        wake_runner()
    return job


async def wait_for_backup_operation(
    db: Session,
    operation_id: int,
    *,
    is_cancelled: Optional[Callable[[], bool]] = None,
    poll_interval_seconds: float = 0.5,
) -> str:
    """Block until the operation is terminal and return its legacy status
    word. A caller that learns it was cancelled (a plan run) asks the runner
    to cancel once; the executor's watcher does the rest (spec 7.7)."""
    from app.services.operations.runner import operation_runner

    cancel_sent = False
    while True:
        db.expire_all()
        operation = db.get(Operation, operation_id)
        if operation is None:
            return "failed"
        if operation.status in TERMINAL_STATUSES:
            return "pending" if operation.status == "queued" else operation.status
        if is_cancelled is not None and not cancel_sent and is_cancelled():
            cancel_sent = True
            await operation_runner.request_cancel(operation_id)
        await asyncio.sleep(poll_interval_seconds)


def backup_job_has_logs(
    db: Session, job: Any, *, log_save_policy: Optional[str] = None
) -> bool:
    """The `has_logs` answer for either shape, agent logs included."""
    from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
    from app.services.repository_executor import get_agent_job_for_backup

    policy = log_save_policy or get_log_save_policy(db)
    output_text: list = [job.logs, job.error_message]
    agent_job = None
    if job.execution_mode == "agent":
        agent_job = get_agent_job_for_backup(db, job)
        if agent_job:
            output_text.append(agent_job.error_message)
    if job_has_logs_by_policy(
        job, policy, output_text=output_text, file_path=job.log_file_path
    ):
        return True
    if policy == "failed_and_warnings" and agent_job is not None:
        from app.database.models import AgentJobLog

        messages = [
            log.message
            for log in db.query(AgentJobLog)
            .filter(AgentJobLog.agent_job_id == agent_job.id)
            .order_by(AgentJobLog.sequence.asc(), AgentJobLog.id.asc())
            .all()
        ]
        if messages:
            return job_has_logs_by_policy(
                job,
                policy,
                output_text=[*output_text, *messages],
                file_path=job.log_file_path,
            )
    return False


# -- union queries --------------------------------------------------------
#
# Each helper reads both tables and merges in Python. Both cuts rank by the
# same key the merge uses (the phase 7 lesson: cutting a source by id while
# merging by timestamp drops rows wherever the two orders disagree).


def _sort_key(attr: str):
    def key(job):
        value = getattr(job, attr, None) or getattr(job, "created_at", None)
        return (value or datetime.min, job.id)

    return key


def _operations_query(db: Session):
    return db.query(Operation).filter(Operation.kind == "backup")


def _facades(db: Session, operations: Iterable[Operation]) -> list:
    return [BackupJobFacade(db, op) for op in operations]


def list_backup_jobs(
    db: Session,
    limit: int,
    *,
    scheduled_only: bool = False,
    manual_only: bool = False,
    repository_path: Optional[str] = None,
) -> list:
    ops = _operations_query(db)
    legacy = db.query(BackupJob)
    if scheduled_only:
        ops = ops.filter(Operation.scheduled_job_id.isnot(None))
        legacy = legacy.filter(BackupJob.scheduled_job_id.isnot(None))
    elif manual_only:
        ops = ops.filter(
            Operation.scheduled_job_id.is_(None), Operation.backup_plan_run_id.is_(None)
        )
        legacy = legacy.filter(
            BackupJob.scheduled_job_id.is_(None), BackupJob.backup_plan_id.is_(None)
        )
    if repository_path:
        repository = (
            db.query(Repository).filter(Repository.path == repository_path).first()
        )
        ops = ops.filter(
            Operation.repository_id == (repository.id if repository else -1)
        )
        legacy = legacy.filter(BackupJob.repository == repository_path)
    jobs = _facades(
        db,
        ops.order_by(Operation.created_at.desc(), Operation.id.desc())
        .limit(limit)
        .all(),
    ) + list(
        legacy.order_by(BackupJob.created_at.desc(), BackupJob.id.desc())
        .limit(limit)
        .all()
    )
    jobs.sort(key=_sort_key("created_at"), reverse=True)
    return jobs[:limit]


def backup_jobs_started_since(
    db: Session, since, *, until=None, limit: Optional[int] = None
) -> list:
    ops = _operations_query(db).filter(Operation.started_at >= since)
    legacy = db.query(BackupJob).filter(BackupJob.started_at >= since)
    if until is not None:
        ops = ops.filter(Operation.started_at <= until)
        legacy = legacy.filter(BackupJob.started_at <= until)
    ops = ops.order_by(Operation.started_at.desc(), Operation.id.desc())
    legacy = legacy.order_by(BackupJob.started_at.desc(), BackupJob.id.desc())
    if limit is not None:
        ops = ops.limit(limit)
        legacy = legacy.limit(limit)
    jobs = _facades(db, ops.all()) + list(legacy.all())
    jobs.sort(key=_sort_key("started_at"), reverse=True)
    return jobs[:limit] if limit is not None else jobs


def latest_backup_job_for_repository(
    db: Session,
    repository: Repository,
    *,
    statuses: Optional[Iterable[str]] = None,
    order: str = "created",
) -> Any:
    ops = _operations_query(db).filter(Operation.repository_id == repository.id)
    legacy = db.query(BackupJob).filter(BackupJob.repository == repository.path)
    if statuses is not None:
        ops = ops.filter(Operation.status.in_(tuple(statuses)))
        legacy = legacy.filter(BackupJob.status.in_(tuple(statuses)))
    if order == "completed":
        ops = ops.filter(Operation.started_at.isnot(None), Operation.completed_at.isnot(None))
        legacy = legacy.filter(
            BackupJob.started_at.isnot(None), BackupJob.completed_at.isnot(None)
        )
        ops = ops.order_by(Operation.completed_at.desc(), Operation.id.desc())
        legacy = legacy.order_by(BackupJob.completed_at.desc(), BackupJob.id.desc())
    else:
        ops = ops.order_by(Operation.created_at.desc(), Operation.id.desc())
        legacy = legacy.order_by(BackupJob.created_at.desc(), BackupJob.id.desc())
    candidates = _facades(db, ops.limit(1).all()) + list(legacy.limit(1).all())
    if not candidates:
        return None
    attr = "completed_at" if order == "completed" else "created_at"
    return max(candidates, key=_sort_key(attr))


def backup_jobs_for_archive_names(db: Session, repository: Repository, names) -> list:
    names = list(names)
    if not names:
        return []
    ops = (
        _operations_query(db)
        .join(OperationBackupDetails, OperationBackupDetails.operation_id == Operation.id)
        .filter(
            Operation.repository_id == repository.id,
            OperationBackupDetails.archive_name.in_(names),
        )
        .all()
    )
    filters = [BackupJob.archive_name.in_(names)]
    owners = []
    if getattr(repository, "id", None) is not None:
        owners.append(BackupJob.repository_id == repository.id)
    if getattr(repository, "path", None):
        owners.append(BackupJob.repository == repository.path)
    if owners:
        filters.append(or_(*owners))
    legacy = db.query(BackupJob).filter(*filters).all()
    jobs = _facades(db, ops) + list(legacy)
    jobs.sort(key=_sort_key("created_at"), reverse=True)
    return jobs


def latest_backup_jobs_by_repository(db: Session, *, running: bool = False) -> dict:
    """Newest (or newest running) backup per repository path, both tables."""
    ops = _operations_query(db).filter(Operation.repository_id.isnot(None))
    legacy = db.query(BackupJob).filter(BackupJob.repository.isnot(None))
    if running:
        ops = ops.filter(Operation.status == "running")
        legacy = legacy.filter(BackupJob.status == "running")
    attr = "started_at" if running else "created_at"
    result: dict = {}
    for job in _facades(db, ops.all()) + list(legacy.all()):
        path = job.repository
        if not path:
            continue
        if path not in result or _sort_key(attr)(job) > _sort_key(attr)(result[path]):
            result[path] = job
    return result


def newest_backup_job(
    db: Session, *, running: bool = False, terminal: bool = False
) -> Any:
    ops = _operations_query(db)
    legacy = db.query(BackupJob)
    attr = "created_at"
    if running:
        ops = ops.filter(Operation.status == "running")
        legacy = legacy.filter(BackupJob.status == "running")
        attr = "started_at"
    elif terminal:
        ops = ops.filter(Operation.status.in_(tuple(TERMINAL_STATUSES)))
        legacy = legacy.filter(BackupJob.status.in_(tuple(TERMINAL_STATUSES)))
        attr = "completed_at"
    column = {"created_at": Operation.created_at, "started_at": Operation.started_at, "completed_at": Operation.completed_at}[attr]
    legacy_column = getattr(BackupJob, attr)
    candidates = _facades(
        db, ops.order_by(column.desc(), Operation.id.desc()).limit(1).all()
    ) + list(legacy.order_by(legacy_column.desc(), BackupJob.id.desc()).limit(1).all())
    return max(candidates, key=_sort_key(attr)) if candidates else None


def backup_jobs_in_maintenance(db: Session) -> list:
    ops = (
        _operations_query(db)
        .join(OperationBackupDetails, OperationBackupDetails.operation_id == Operation.id)
        .filter(OperationBackupDetails.maintenance_status.in_(RUNNING_MAINTENANCE_WORDS))
        .all()
    )
    legacy = (
        db.query(BackupJob)
        .filter(BackupJob.maintenance_status.in_(RUNNING_MAINTENANCE_WORDS))
        .all()
    )
    return _facades(db, ops) + list(legacy)
```

Note for the implementer: `apply_repository_route_to_backup_job` writes
`route_strategy`, `execution_mode`, and `source_ssh_connection_id` on the
facade through its setters, so the legacy words it uses (`local`,
`remote_ssh`) are translated on the way in. `TERMINAL_STATUSES` from
`vocab.py` contains `skipped`; a backup operation is never skipped by the
runner except for a missing executor, and `wait_for_backup_operation`
returning `skipped` is treated by every caller as "not completed".

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_operations_backup_facade.py -v`
Expected: PASS. If `test_create_backup_operation_records_route_and_params`
fails on `route_strategy`, check `plan_repository_route` for a local
repository with no source directories; construct the fixture repository with
`source_directories='["/data"]'` if the route is otherwise unsupported.

---

## Task 3: Service seams

**Files:**
- Modify: `app/services/backup_service.py` (lines 486, 759, 1376, 1494, 3104 lookups; 1885, 2032, 2123 refreshes; 570-592 and the two call sites at 2584 and 2699)
- Modify: `app/services/remote_backup_service.py` (lines 126, 219, 273, 583, 700, 873)
- Modify: `app/services/repository_executor.py` (`queue_agent_backup_job` at 430, `get_agent_job_for_backup` at 620, `cancel_agent_backup_job` at 684, `wait_for_agent_backup_job` at 712)
- Modify: `app/services/script_library_executor.py` (lines 44-53 and 331-340)
- Modify: `app/services/operations/followups.py` (docstring only)
- Test: `tests/unit/test_backup_service.py`, `tests/unit/test_remote_backup_service.py`, `tests/unit/test_api_agents.py`

**Interfaces:**
- Consumes: `resolve_backup_job`, `refresh_backup_job`,
  `admission_ignore_for`, `backup_job_link_columns`, `is_backup_operation`.
- Produces: `get_agent_job_for_backup(db, job)` now takes the job object
  (facade or legacy) instead of an id; `queue_agent_backup_job` fills
  `AgentJob.operation_id` for a facade; `wait_for_agent_backup_job` resolves
  its backup through the facade module. `backup_service.execute_backup`,
  `remote_backup_service.execute_remote_backup`, and both `cancel_*` keep
  their signatures.

- [x] **Step 1: Write the failing tests**

In `tests/unit/test_backup_service.py`, next to the existing test that drives
`execute_backup` with a `FakeProcess` (search for `create_subprocess_exec`
patches), add a test that creates the job as an operation instead of a
`BackupJob`:

```python
@pytest.mark.asyncio
async def test_execute_backup_drives_an_operation_row(tmp_path, monkeypatch):
    from app.services.operations.backup_facade import BackupJobFacade

    # Reuse the session factory, repository, and settings setup of the
    # existing local backup test in this module; only the job row differs.
    session, repo = _local_repository_session(tmp_path)  # helper already here or extract one
    op = Operation(
        repository_id=repo.id,
        kind="backup",
        category="backup",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params={"executor": "server"},
    )
    session.add(op)
    session.commit()
    process = FakeProcess(returncode=0, stdout_lines=[])
    with (
        patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)),
        patch("app.services.backup_service.SessionLocal", lambda: session),
    ):
        await BackupService().execute_backup(op.id, repo.path, session, archive_name="a1")

    session.refresh(op)
    job = BackupJobFacade(session, op)
    assert job.status == "completed"
    assert job.archive_name == "a1"
    assert session.query(Operation).filter(Operation.kind == "archive_sync").count() == 0
```

The last assertion pins that the service no longer enqueues follow-ups (the
runner does, Task 4). Any existing test in this module asserting an
`archive_sync` row after `execute_backup` moves that assertion to the
executor test in Task 4.

In `tests/unit/test_api_agents.py`, next to the tests that link an
`AgentJob` to a `BackupJob` (lines 779, 832, 880, 985), add one that links
through `operation_id` and asserts `get_agent_job_for_backup(db, facade)`
finds it and `cancel_agent_backup_job(db, facade)` writes `cancelled` on the
operation when the agent job is still queued.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_backup_service.py tests/unit/test_api_agents.py -k "operation" -v`
Expected: FAIL (`resolve_backup_job` not used yet; `get_agent_job_for_backup`
takes an id).

- [x] **Step 3: Route the service lookups through the facade**

In `app/services/backup_service.py`:

- Replace the import `from app.services.operations.followups import
  enqueue_backup_followups` with
  `from app.services.operations.backup_facade import refresh_backup_job,
  resolve_backup_job`.
- Replace every `db.query(BackupJob).filter(BackupJob.id == job_id).first()`
  (lines 486, 759, 1376, 1494) and the `retry_db` one at 3104 with
  `resolve_backup_job(db, job_id)` (and `resolve_backup_job(retry_db,
  job_id)`).
- Replace `db.refresh(job)` at 1885, 2032, and 2123 with
  `refresh_backup_job(db, job)`.
- Delete `_enqueue_index_followups` (570-592) and its two call sites (2584,
  2699). The runner enqueues the chain when the executor returns (spec 7.4);
  the executor covers the post-hook failure case.
- `BackupJob` stays imported for the `_uses_remote_execution` annotation.

In `app/services/remote_backup_service.py`: import `resolve_backup_job` and
replace the six `db.query(BackupJob).filter(BackupJob.id == job_id).first()`
lookups with `resolve_backup_job(db, job_id)`.

In `app/services/repository_executor.py`:

```python
def queue_agent_backup_job(db, backup_job, repository, *, archive_name=None, ...):
    ...
    ensure_repository_admission(
        db,
        repository,
        OPERATION_BACKUP,
        ignore=admission_ignore_for(backup_job),
    )
    ...
    agent_job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="queued",
        payload=build_agent_backup_payload(...),
        created_at=now,
        updated_at=now,
        **backup_job_link_columns(db, backup_job.id),
    )
```

```python
def get_agent_job_for_backup(db: Session, backup_job: Any) -> Optional[AgentJob]:
    """The transport job for a backup, whichever shape the backup has."""
    column = (
        AgentJob.operation_id
        if is_backup_operation(backup_job)
        else AgentJob.backup_job_id
    )
    return (
        db.query(AgentJob)
        .filter(column == backup_job.id)
        .order_by(AgentJob.id.desc())
        .first()
    )
```

`cancel_agent_backup_job` already passes the job object; change its call to
`get_agent_job_for_backup(db, backup_job)`. In `wait_for_agent_backup_job`
replace the `BackupJob` query with `resolve_backup_job(db, backup_job_id)`.
Update the three callers of `get_agent_job_for_backup` in `app/api/backup.py`
(lines 776, 859, and inside `_backup_job_has_logs`) to pass `job` instead of
`job.id` (Task 5 rewrites those functions anyway; make the argument change
now so the module imports cleanly).

In `app/services/script_library_executor.py`, the SSH connection lookup at
line 49 becomes `job = resolve_backup_job(db, backup_job_id)`, and the
`ScriptExecution(...)` at 331 replaces `backup_job_id=backup_job_id,` with
`**backup_job_link_columns(self.db, backup_job_id),`.

In `app/services/operations/followups.py`, change the first paragraph of the
`enqueue_backup_followups` docstring to: "Enqueue the `backup` chain for a
backup that completed outside the runner: an agent completion report for a
row written before phase 8, or for an operation the runner is no longer
running (failed by restart recovery and finished by the agent afterwards).
Every other backup gets its chain from the runner (spec 7.4)."

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_backup_service.py tests/unit/test_backup_service_mocks.py tests/unit/test_remote_backup_service.py tests/unit/test_api_agents.py tests/unit/test_agent_job_dispatcher.py -v`
Expected: PASS. Tests that patched `app.services.backup_service.enqueue_backup_followups`
or asserted the chain from the service are updated to the Task 4 executor
test.

---

## Task 4: The backup executor

**Files:**
- Create: `app/services/operations/executors/backup.py`
- Modify: `app/services/operations/executors/__init__.py` (add `backup` to `load_default_executors`)
- Test: `tests/unit/test_operations_backup_executor.py`

**Interfaces:**
- Consumes: `BackupJobFacade`, `SERVICE_PARAMS`, `AGENT_PARAMS`,
  `CANCEL_MESSAGES`, `CANCELLED_BY_USER`, `POST_CREATE_FAILURE_KEYS`,
  `resolve_backup_job`; `cancel_watcher` from `executors/maintenance.py`;
  `backup_service.execute_backup`, `backup_service.cancel_backup`,
  `remote_backup_service.cancel_remote_backup`, `_uses_remote_execution`;
  `queue_agent_backup_job`, `dispatch_agent_job_best_effort`,
  `dispatch_agent_cancel_if_connected`, `cancel_agent_backup_job`,
  `wait_for_agent_backup_job`; `enqueue_chain`, `chain_for`,
  `history_enabled`, `registered_kinds`.
- Produces: `run_backup(ctx) -> Outcome`, registered as `backup`.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_operations_backup_executor.py` with the `db`,
`repository`, and `FakeContext` fixtures copied verbatim from
`tests/unit/test_operations_restore_executor.py`, then:

```python
def _operation(db, repository, params=None, status="running"):
    op = Operation(
        repository_id=repository.id if repository is not None else None,
        kind="backup",
        category="backup",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {"executor": "server", "archive_name": "nas-1", "skip_hooks": True},
    )
    db.add(op)
    db.commit()
    return op


@pytest.mark.asyncio
async def test_run_backup_passes_params_to_the_service(db, repository, monkeypatch):
    load_default_executors()
    op = _operation(db, repository)
    seen = {}

    async def _execute_backup(job_id, repository_path, session, **kw):
        seen.update(job_id=job_id, repository_path=repository_path, session=session, **kw)
        job = BackupJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        job.archive_name = kw["archive_name"]
        job.original_size = 12
        db.commit()

    monkeypatch.setattr(
        "app.services.backup_service.backup_service.execute_backup", _execute_backup
    )
    outcome = await get_executor("backup")(FakeContext(db, op))

    assert seen == {
        "job_id": op.id,
        "repository_path": "/repo/nas",
        "session": None,
        "archive_name": "nas-1",
        "skip_hooks": True,
    }
    assert outcome.status == "completed"
    assert outcome.result == {
        "archive_name": "nas-1",
        "original_size": 12,
        "compressed_size": 0,
        "deduplicated_size": 0,
        "nfiles": 0,
    }


@pytest.mark.asyncio
async def test_run_backup_keeps_the_cancelled_verdict(db, repository, monkeypatch):
    load_default_executors()
    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def _execute_backup(job_id, repository_path, session, **kw):
        ctx._cancelled = True
        job = BackupJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = "borg died"
        db.commit()

    monkeypatch.setattr(
        "app.services.backup_service.backup_service.execute_backup", _execute_backup
    )
    outcome = await get_executor("backup")(ctx)

    assert outcome.status == "failed"
    assert db.get(Operation, op.id).status == "cancelled"
    assert db.get(Operation, op.id).error_message == CANCELLED_BY_USER


@pytest.mark.asyncio
async def test_post_hook_failure_still_enqueues_the_index_chain(db, repository, monkeypatch):
    load_default_executors()
    op = _operation(db, repository)

    async def _execute_backup(job_id, repository_path, session, **kw):
        job = BackupJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = json.dumps(
            {"key": "backend.errors.service.postBackupHooksFailed", "params": {}}
        )
        db.commit()

    monkeypatch.setattr(
        "app.services.backup_service.backup_service.execute_backup", _execute_backup
    )
    monkeypatch.setattr(
        "app.services.operations.followups.history_enabled", lambda db: False
    )
    outcome = await get_executor("backup")(FakeContext(db, op))

    assert outcome.status == "failed"
    chain = (
        db.query(Operation)
        .filter(Operation.run_id == "run-1", Operation.kind != "backup")
        .order_by(Operation.id)
        .all()
    )
    assert [c.kind for c in chain] == ["archive_sync", "history_merge", "stats"]
    assert chain[0].depends_on_id is None
    assert chain[0].trigger == "followup"


@pytest.mark.asyncio
async def test_run_backup_agent_path_queues_and_waits(db, repository, monkeypatch):
    load_default_executors()
    repository.executor_type = "agent"
    db.commit()
    op = _operation(
        db,
        repository,
        params={"executor": "agent", "archive_name": "nas-1", "compression_override": "zstd"},
    )
    seen = {}

    def _queue(session, backup_job, repo, **kw):
        seen["queue"] = kw
        backup_job.execution_mode = "agent"
        return SimpleNamespace(id=77, payload={})

    async def _dispatch(session, agent_job, **context):
        seen["dispatch"] = agent_job.id
        return True

    async def _wait(session, agent_job_id, backup_job_id, is_cancelled, **kw):
        job = BackupJobFacade(db, db.get(Operation, backup_job_id))
        job.status = "completed_with_warnings"
        job.archive_name = "nas-1"
        db.commit()
        return "completed_with_warnings"

    monkeypatch.setattr("app.services.operations.executors.backup.queue_agent_backup_job", _queue)
    monkeypatch.setattr("app.services.operations.executors.backup.dispatch_agent_job_best_effort", _dispatch)
    monkeypatch.setattr("app.services.operations.executors.backup.wait_for_agent_backup_job", _wait)
    outcome = await get_executor("backup")(FakeContext(db, op))

    assert seen["queue"] == {"archive_name": "nas-1", "compression": "zstd"}
    assert seen["dispatch"] == 77
    assert outcome.status == "completed_with_warnings"
    assert db.get(Operation, op.id).execution_mode == "agent"


@pytest.mark.asyncio
async def test_run_backup_without_a_repository_is_skipped(db):
    load_default_executors()
    op = _operation(db, None)
    outcome = await get_executor("backup")(FakeContext(db, op))
    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_backup_executor.py -v`
Expected: FAIL (`get_executor("backup")` is None).

- [x] **Step 3: Write the executor**

Create `app/services/operations/executors/backup.py`:

```python
"""The backup executor (spec 6.3, section 13 phase 8).

A thin shell in the shape phase 5 established: the work stays in
`backup_service.execute_backup` (local and SSHFS sources, or the remote
service it delegates to) or in the agent transport; the shell loads the
repository, hands the service or the agent queue the inputs `params`
carries, watches the runner's cancel flag, and turns the row's final status
into an `Outcome`. Notifications and MQTT publishes stay where they are: the
service sends them for server backups, the agent transport for agent
backups. The runner enqueues the index chain on success (spec 7.4); the one
failure that still changed the repository, a post-backup hook failing after
`borg create` succeeded, enqueues the chain from here (Appendix B).
"""

import asyncio
import json
from typing import Optional

import structlog

from app.database.models import Operation, Repository
from app.services.agent_job_dispatcher import (
    dispatch_agent_cancel_if_connected,
    dispatch_agent_job_best_effort,
)
from app.services.operations import executors
from app.services.operations.backup_facade import (
    AGENT_PARAMS,
    CANCEL_MESSAGES,
    CANCELLED_BY_USER,
    POST_CREATE_FAILURE_KEYS,
    SERVICE_PARAMS,
    BackupJobFacade,
    resolve_backup_job,
)
from app.services.operations.executors.maintenance import cancel_watcher
from app.services.operations.runner import Outcome
from app.services.repository_executor import (
    cancel_agent_backup_job,
    get_agent_job_for_backup,
    queue_agent_backup_job,
    wait_for_agent_backup_job,
)

logger = structlog.get_logger()

_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


def _error_key(message: Optional[str]) -> Optional[str]:
    try:
        parsed = json.loads(message or "")
    except (TypeError, ValueError):
        return None
    return parsed.get("key") if isinstance(parsed, dict) else None


async def _cancel_server_backup(operation_id: int) -> bool:
    from app.services.backup_service import _uses_remote_execution, backup_service
    from app.services.remote_backup_service import remote_backup_service
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        job = resolve_backup_job(db, operation_id)
        remote = job is not None and _uses_remote_execution(job)
    finally:
        db.close()
    if remote:
        return await remote_backup_service.cancel_remote_backup(operation_id)
    return await backup_service.cancel_backup(operation_id)


async def _cancel_agent_backup(operation_id: int) -> bool:
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        job = resolve_backup_job(db, operation_id)
        if job is None:
            return True
        agent_job = get_agent_job_for_backup(db, job)
        if agent_job is None:
            return False
        cancel_agent_backup_job(db, job)
        db.commit()
        await dispatch_agent_cancel_if_connected(agent_job)
        return True
    finally:
        db.close()


def _enqueue_post_create_chain(ctx, operation: Operation) -> None:
    from app.services.operations.enqueue import enqueue_chain
    from app.services.operations.executors import registered_kinds
    from app.services.operations.followups import chain_for, history_enabled

    kinds = chain_for("backup", available=registered_kinds(), history=history_enabled(ctx.db))
    if not kinds:
        return
    enqueue_chain(
        ctx.db,
        kinds,
        repository_id=operation.repository_id,
        trigger="followup",
        run_id=operation.run_id,
        triggered_by_user_id=operation.triggered_by_user_id,
        scheduled_job_id=operation.scheduled_job_id,
        backup_plan_run_id=operation.backup_plan_run_id,
    )


async def run_backup(ctx) -> Outcome:
    from app.services.backup_service import backup_service

    repository = (
        ctx.db.get(Repository, ctx.repository_id)
        if ctx.repository_id is not None
        else None
    )
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")

    params = ctx.params
    job = BackupJobFacade(ctx.db, ctx.db.get(Operation, ctx.operation_id))

    if params.get("executor") == "agent":
        # Raises the admission's 409 while the repository is busy, which the
        # runner turns into a deferral (spec 7.1 step 5).
        agent_job = queue_agent_backup_job(
            ctx.db,
            job,
            repository,
            **{
                AGENT_PARAMS[key]: params[key]
                for key in AGENT_PARAMS
                if params.get(key) is not None
            },
        )
        ctx.db.commit()
        await dispatch_agent_job_best_effort(
            ctx.db,
            agent_job,
            source="operation_runner",
            operation_id=ctx.operation_id,
            repository_id=repository.id,
        )
        watcher = asyncio.create_task(cancel_watcher(ctx, _cancel_agent_backup))
        try:
            await wait_for_agent_backup_job(
                ctx.db, agent_job.id, ctx.operation_id, ctx.cancelled
            )
        finally:
            watcher.cancel()
    else:
        watcher = asyncio.create_task(cancel_watcher(ctx, _cancel_server_backup))
        try:
            await backup_service.execute_backup(
                ctx.operation_id,
                repository.path,
                None,
                **{key: params[key] for key in SERVICE_PARAMS if key in params},
            )
        finally:
            watcher.cancel()

    # The service ran in its own session and committed there. Expire this one
    # so the verdict it wrote is read back rather than assumed.
    ctx.db.expire_all()
    operation = ctx.db.get(Operation, ctx.operation_id)
    job = BackupJobFacade(ctx.db, operation)

    if ctx.cancelled():
        operation.status = "cancelled"
        if operation.error_message not in CANCEL_MESSAGES:
            operation.error_message = CANCELLED_BY_USER
        ctx.db.commit()
        return Outcome(status="failed", error_message=operation.error_message)

    status = operation.status
    if status not in _TERMINAL:
        return Outcome(
            status="failed",
            error_message=job.error_message or "backup returned no result",
        )
    if status in ("completed", "completed_with_warnings"):
        return Outcome(
            status=status,
            result={
                "archive_name": job.archive_name,
                "original_size": job.original_size or 0,
                "compressed_size": job.compressed_size or 0,
                "deduplicated_size": job.deduplicated_size or 0,
                "nfiles": job.nfiles or 0,
            },
        )
    if status == "failed" and _error_key(job.error_message) in POST_CREATE_FAILURE_KEYS:
        _enqueue_post_create_chain(ctx, operation)
    return Outcome(status="failed", error_message=job.error_message)


executors.register("backup", run_backup)
```

Add `backup,` to the import list in `load_default_executors`.

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_operations_backup_executor.py tests/unit/test_operations_runner.py -v`
Expected: PASS.

---

## Task 5: The routes (v1 and v2)

**Files:**
- Modify: `app/api/backup.py` (`_start_backup_impl` 382-473, `retry_backup_job` 495-611, `get_all_backup_jobs` 613-703, `get_backup_status` 706-750, `cancel_backup` 753-816, `download_backup_logs` 819-940, `stream_backup_logs` 943-1057, `_backup_job_has_logs` 197-229, `_cancel_running_maintenance_job` 326-380)
- Modify: `app/api/v2/backups.py` (111-162)
- Test: `tests/unit/test_api_backup.py`, `tests/unit/test_api_v2_backups.py`

**Interfaces:**
- Consumes: `create_backup_operation`, `resolve_backup_job`,
  `list_backup_jobs`, `is_backup_operation`, `backup_job_has_logs`,
  `wait_for_backup_operation`, `CANCELLED_BY_USER`,
  `CANCELLED_PROCESS_NOT_FOUND`, `OperationBackupRetryLineage`,
  `operation_runner.request_cancel`.
- Produces: no new interface; every response body unchanged.

- [x] **Step 1: Write the failing tests**

In `tests/unit/test_api_backup.py`, rewrite `TestBackupStart` so a start
creates an operation instead of spawning a task, and add the contract tests:

```python
    def test_start_backup_enqueues_an_operation(self, test_client, admin_headers, test_db):
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()

        response = test_client.post(
            "/api/backup/start", json={"repository": "/test/repo"}, headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["message"] == "Backup job started"
        op = test_db.get(Operation, body["job_id"])
        assert op.kind == "backup"
        assert op.status == "queued"
        assert op.trigger == "manual"
        assert op.params["executor"] == "server"
        assert test_db.query(BackupJob).count() == 0

    def test_start_backup_unknown_path_is_recorded_and_failed(self, test_client, admin_headers, test_db):
        response = test_client.post(
            "/api/backup/start", json={"repository": "/nope"}, headers=admin_headers
        )
        assert response.status_code == 200
        op = test_db.get(Operation, response.json()["job_id"])
        assert op.status == "failed"
        assert op.repository_id is None
        status = test_client.get(f"/api/backup/status/{op.id}", headers=admin_headers).json()
        assert status["repository"] == "/nope"
        assert status["status"] == "failed"

    def test_retry_creates_a_retry_operation_with_lineage(self, test_client, admin_headers, test_db):
        from app.database.models import OperationBackupRetryLineage

        repo = Repository(name="r", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        source = Operation(repository_id=repo.id, kind="backup", category="backup", status="failed", trigger="manual", priority=0, run_id="r1", params={"executor": "server"})
        test_db.add(source)
        test_db.commit()

        response = test_client.post(f"/api/backup/jobs/{source.id}/retry", headers=admin_headers)

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "pending"
        assert body["retry_attempt"] == 2
        assert body["retry_original_job_id"] == source.id
        assert body["retry_source_job_id"] == source.id
        retry = test_db.get(Operation, body["job_id"])
        assert retry.trigger == "retry"
        lineage = test_db.query(OperationBackupRetryLineage).one()
        assert lineage.created_operation_id == retry.id
        assert lineage.attempt_number == 2
        assert lineage.request_snapshot["kind"] == "backup_job_retry"

    def test_list_and_status_serve_operations_and_legacy_rows(self, test_client, admin_headers, test_db):
        repo = Repository(name="r", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        legacy = BackupJob(repository="/test/repo", status="completed")
        test_db.add(legacy)
        test_db.commit()
        op = Operation(repository_id=repo.id, kind="backup", category="backup", status="running", trigger="schedule", priority=5, run_id="r1", params={"executor": "server", "archive_name": "a"}, progress_percent=40.0)
        test_db.add(op)
        test_db.commit()

        jobs = test_client.get("/api/backup/jobs", headers=admin_headers).json()["jobs"]
        assert {j["id"] for j in jobs} == {legacy.id, op.id}
        mine = next(j for j in jobs if j["id"] == op.id)
        assert mine["status"] == "running"
        assert mine["progress"] == 40
        assert mine["triggered_by"] == "schedule"
        assert mine["execution_mode"] == "local"
        assert mine["archive_name"] == "a"
        assert set(mine) == set(next(j for j in jobs if j["id"] == legacy.id))

    def test_cancel_running_operation_raises_the_flag_then_kills(self, test_client, admin_headers, test_db):
        repo = Repository(name="r", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        op = Operation(repository_id=repo.id, kind="backup", category="backup", status="running", trigger="manual", priority=0, run_id="r1", params={"executor": "server"})
        test_db.add(op)
        test_db.commit()
        calls = []

        async def _request_cancel(operation_id):
            calls.append(("flag", operation_id))
            return True

        async def _kill(job_id):
            calls.append(("kill", job_id))
            return True

        with (
            patch("app.api.backup.operation_runner.request_cancel", _request_cancel),
            patch("app.api.backup.backup_service.cancel_backup", _kill),
        ):
            response = test_client.post(f"/api/backup/cancel/{op.id}", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == {"message": "backend.success.backup.backupCancelled", "process_terminated": True}
        assert calls == [("flag", op.id), ("kill", op.id)]
        test_db.refresh(op)
        assert op.status == "cancelled"
        assert json.loads(op.error_message)["key"] == "backend.errors.backup.cancelledByUser"
```

In `tests/unit/test_api_v2_backups.py`, replace the
`app.api.v2.backups.backup_service.execute_backup` patches (lines 85, 110,
140) with a patch of `app.api.v2.backups.wait_for_backup_operation` that
marks the operation and its details (`archive_name`, sizes) and returns the
status word; assert the response `stats` come from the details row and
`job_id` is the operation id.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_api_backup.py tests/unit/test_api_v2_backups.py -v`
Expected: the new tests FAIL.

- [x] **Step 3: Rewrite the creation routes**

`_start_backup_impl` body after the access checks:

```python
        ensure_manual_backup_capacity(db)
        if repo_record is not None:
            ensure_repository_admission(db, repo_record, OPERATION_BACKUP)

        if backup_request.repository and repo_record is None:
            # Legacy contract: an unknown path is accepted and fails at once,
            # so polling clients get a terminal state. Created uncommitted so
            # the runner never sees it queued.
            backup_job = create_backup_operation(
                db,
                None,
                trigger="manual",
                executor="server",
                user_id=current_user.id,
                repository_path=backup_request.repository,
                commit=False,
            )
            backup_job.status = "failed"
            backup_job.error_message = json.dumps({"key": "backend.errors.borg.unknownError"})
            backup_job.logs = (
                f"Repository record not found in database: {backup_request.repository}"
            )
            backup_job.completed_at = datetime.utcnow()
            db.commit()
        else:
            backup_job = create_backup_operation(
                db,
                repo_record,
                trigger="manual",
                executor="agent"
                if repo_record is not None and is_agent_executor(repo_record)
                else "server",
                user_id=current_user.id,
                repository_path=backup_request.repository or "default",
            )

        logger.info("Backup job created", job_id=backup_job.id, user=current_user.username)
        return BackupResponse(job_id=backup_job.id, status="pending", message="Backup job started")
```

When `backup_request.repository` is empty (legacy "default"), `repo_record`
is None too; the second branch handles it with `repository=None`, which
`create_backup_operation` records as an unrepositoried row that the executor
skips with `repository_missing`. Keep the legacy behaviour instead: route
the empty-path case through the first branch as well (`if repo_record is
None:`), since a backup with no repository never ran before either.

Delete `_run_in_background` and `_background_tasks` (no caller remains) and
the `queue_agent_backup_job` and `dispatch_agent_job_best_effort` imports
from this module (the executor owns them).

`retry_backup_job`:

```python
    source_job = resolve_backup_job(db, job_id)
    if not source_job:
        raise HTTPException(404, detail={"key": "backend.errors.backup.backupJobNotFound"})
    _ensure_backup_retry_supported(source_job)
    repo = _get_backup_job_repository(db, source_job)
    if not repo:
        raise HTTPException(400, detail={"key": "backend.errors.backup.retryRequestNotReconstructable"})
    check_repo_access(db, current_user, repo, "operator")

    ensure_manual_backup_capacity(db)
    attempt_number = (source_job.retry_attempt or 1) + 1
    original_job_id = source_job.retry_original_job_id or source_job.id
    requested_at = datetime.utcnow()
    agent = is_agent_executor(repo)
    if agent:
        validate_agent_backup_repository(db, repo)
    else:
        ensure_repository_admission(db, repo, OPERATION_BACKUP)

    retry_job = create_backup_operation(
        db,
        repo,
        trigger="retry",
        executor="agent" if agent else "server",
        user_id=current_user.id,
        retry={
            "retry_original_job_id": original_job_id,
            "retry_source_job_id": source_job.id,
            "retry_attempt": attempt_number,
            "retry_requested_by_user_id": current_user.id,
            "retry_requested_at": requested_at,
        },
        commit=False,
    )
    db.add(
        OperationBackupRetryLineage(
            original_job_id=original_job_id,
            retry_source_job_id=source_job.id,
            attempt_number=attempt_number,
            requested_by_user_id=current_user.id,
            requested_at=requested_at,
            created_operation_id=retry_job.id,
            request_snapshot=_backup_retry_request_snapshot(
                source_job=source_job, retry_job=retry_job, repo=repo
            ),
        )
    )
    db.commit()
    wake_runner()
    logger.info("Backup retry created", source_job_id=source_job.id, retry_job_id=retry_job.id, user=current_user.username)
    return _backup_retry_response(retry_job)
```

`_backup_retry_request_snapshot` loses its `agent_payload` parameter (the
agent job is queued by the executor now; the snapshot records the request,
not the transport). `_get_backup_job_repository` and `_get_job_repository`
work unchanged against the facade (`repository_id`, `repository`).

`get_all_backup_jobs`: replace the query block with

```python
        jobs = list_backup_jobs(
            db,
            limit,
            scheduled_only=scheduled_only,
            manual_only=manual_only,
            repository_path=repository,
        )
```

and keep the visibility loop and the serialisation exactly as they are
(`_retry_metadata`, `serialize_backup_progress_details`, `getattr(job,
"archive_name", None)` all work on the facade). `_backup_job_has_logs`
becomes a one-line delegate to `backup_job_has_logs`.

`get_backup_status`, `download_backup_logs`, `stream_backup_logs`: replace
the lookup with `resolve_backup_job(db, job_id)`; nothing else changes (a
facade's `logs` returns file text, so the "Logs saved to:" branches are
simply not taken for operations).

`cancel_backup`:

```python
        job = resolve_backup_job(db, job_id)
        if not job:
            raise HTTPException(404, detail={"key": "backend.errors.backup.backupJobNotFound"})
        repo = _get_job_repository(db, job.repository)
        if repo:
            check_repo_access(db, current_user, repo, "operator")

        operation = is_backup_operation(job)
        if job.execution_mode == "agent":
            if operation:
                await operation_runner.request_cancel(job.id)
            cancel_agent_backup_job(db, job)
            process_killed = False
        elif job.status == "running":
            if operation:
                # Spec 7.7: the flag first, so the executor keeps `cancelled`
                # over the service's later `failed` write for the killed
                # process (the phase 7 restore pattern).
                await operation_runner.request_cancel(job.id)
            process_killed = await backup_service.cancel_backup(job_id)
            job.status = "cancelled"
            job.completed_at = datetime.utcnow()
            job.error_message = CANCELLED_BY_USER if process_killed else CANCELLED_PROCESS_NOT_FOUND
        elif operation and job.status == "pending":
            # A queued backup is new in this phase (it waits for the lane);
            # the runner marks it cancelled directly.
            await operation_runner.request_cancel(job.id)
            process_killed = False
        elif job.maintenance_status in RUNNING_BACKUP_MAINTENANCE_FAILURES:
            ... unchanged ...
        else:
            raise HTTPException(400, detail={"key": "backend.errors.backup.canOnlyCancelRunningJobs"})
        db.commit()
```

Import `operation_runner` from `app.services.operations.runner` at module
level so tests can patch `app.api.backup.operation_runner.request_cancel`.

`_cancel_running_maintenance_job` and `_get_running_maintenance_job` read
`backup_job.repository` and `maintenance_status`, both on the facade; the
child lookup already goes through the legacy tables and, since phase 5, the
prune and compact services' own cancel paths. Leave them.

`app/api/v2/backups.py` `run_backup`:

```python
    ensure_repository_admission(db, repo, OPERATION_BACKUP)
    backup_job = create_backup_operation(
        db,
        repo,
        trigger="manual",
        executor="server",
        user_id=current_user.id,
        params={"archive_name": data.archive_name},
    )
    final_status = await wait_for_backup_operation(db, backup_job.id)
    refresh_backup_job(db, backup_job)

    if final_status not in {"completed", "completed_with_warnings"}:
        raise HTTPException(500, detail={"key": "backend.errors.backup.failed", "params": {"error": backup_job.error_message or "Backup failed"}})

    return {
        "success": True,
        "stats": {
            "original_size": backup_job.original_size or 0,
            "compressed_size": backup_job.compressed_size or 0,
            "deduplicated_size": backup_job.deduplicated_size or 0,
            "nfiles": backup_job.nfiles or 0,
        },
        "status": backup_job.status,
        "job_id": backup_job.id,
    }
```

The v2 route did not run admission before; add it, since the row now waits
on the lane and a request blocked behind a wipe would otherwise hang until
the wipe ends (Open question 7).

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_backup.py tests/unit/test_api_v2_backups.py -v`
Expected: PASS. Every pre-existing test in these modules that created a
`BackupJob` to exercise a by-id route keeps passing through the legacy
fallback; tests that patched `_run_in_background` or asserted
`queue_agent_backup_job` was called from the route are rewritten to assert
the operation row and its `params["executor"]`.

---

## Task 6: Scheduler and plan runner

**Files:**
- Modify: `app/api/schedule.py` (1766-1800, 2140-2155 and 2254-2262, 2560-2760, 2877-2912)
- Modify: `app/services/backup_plan_execution_service.py` (1975-2070, 2113-2226)
- Modify: `app/services/operations/maintenance_start.py` (`start_inline_maintenance`)
- Test: `tests/unit/test_api_schedule_routes.py`, `tests/unit/test_schedulers.py`, `tests/unit/test_api_backup_plans.py`, `tests/unit/test_operations_maintenance_executors.py` (or wherever `start_inline_maintenance` is tested)

**Interfaces:**
- Consumes: `create_backup_operation`, `wait_for_backup_operation`,
  `resolve_backup_job`, `refresh_backup_job`, `is_backup_operation`.
- Produces: `start_inline_maintenance(..., run_id=None, depends_on_id=None)`;
  `execute_scheduled_backup_with_maintenance(backup_job_id, repository_path,
  scheduled_job_id, archive_name=None)` keeps its signature and now waits
  for the operation instead of running the service; `BackupPlanRunRepository.
  backup_operation_id` is filled by the plan runner.

- [x] **Step 1: Write the failing tests**

In `tests/unit/test_api_schedule_routes.py`, the test around line 430 that
patches `execute_scheduled_backup_with_maintenance` for "run now" adds:

```python
        op = test_db.query(Operation).filter(Operation.kind == "backup").one()
        assert op.trigger == "schedule"
        assert op.scheduled_job_id == job_id
        assert op.params["archive_name"]
        assert test_db.query(BackupJob).count() == 0
```

and the test around line 491 that patches `execute_backup` for the
multi-repository schedule patches `app.api.schedule.wait_for_backup_operation`
instead, with a side effect that marks the operation `completed`, and asserts
one backup operation per repository.

In `tests/unit/test_api_backup_plans.py`, the run test at 2357 (which
patches `asyncio.create_task`) gains a sibling that runs
`_execute_repository` directly with `wait_for_backup_operation` patched to
mark the operation `completed` with an `archive_name`, and asserts:
`BackupPlanRunRepository.backup_operation_id == op.id`, `op.trigger ==
"plan"`, `op.backup_plan_run_id == run.id`, `op.params` carrying
`source_directories`, `exclude_patterns_override`, `compression_override`,
`custom_flags_override`, `skip_hooks`, and the plan run payload's
`backup_job.id == op.id` with `backup_job.maintenance_status ==
"maintenance_completed"` when `run_prune_after` is on and the inline prune is
patched to succeed.

For `start_inline_maintenance`, add to its existing test module:

```python
def test_start_inline_maintenance_can_join_a_run(db, repository):
    parent = Operation(repository_id=repository.id, kind="backup", category="backup", status="completed", trigger="plan", priority=0, run_id="run-9")
    db.add(parent)
    db.commit()
    child = start_inline_maintenance(
        db, repository, "prune", params={}, user_id=None, run_id="run-9", depends_on_id=parent.id
    )
    assert child.run_id == "run-9"
    assert child.depends_on_id == parent.id
    assert child.status == "running"
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_api_schedule_routes.py tests/unit/test_api_backup_plans.py -k "operation or join" -v`
Expected: FAIL.

- [x] **Step 3: Give inline maintenance a run**

In `maintenance_start.py`:

```python
def start_inline_maintenance(
    db, repository, kind, *, params, user_id, run_id=None, depends_on_id=None
) -> Operation:
    """... Post-backup maintenance passes the backup's `run_id` and id so the
    child is the backup's child in the run (spec 6.3: `running_prune` is
    `running` on the child prune operation while the backup is completed)."""
    operation = enqueue(
        db, kind, repository_id=repository.id, trigger="manual",
        params={...}, triggered_by_user_id=user_id,
        run_id=run_id, depends_on_id=depends_on_id, commit=False,
    )
```

- [x] **Step 4: Rewrite the three schedule creation sites**

At each of the three `BackupJob(...)` sites (1768, 2142, 2879) replace the
row creation, `apply_repository_route_to_backup_job`, `db.add`, `db.commit`,
`db.refresh` block and the archive name generation order so the archive name
is computed first and stored in `params`:

```python
            archive_name = build_archive_name(...)  # unchanged arguments
            backup_job = create_backup_operation(
                db,
                repo,
                trigger="schedule",
                executor="server",
                params={"archive_name": archive_name},
                scheduled_job_id=job.id,          # scheduled_job.id in the multi-repo loop
            )
```

The `run now` site (1768) and the scheduler tick (2879) keep their
`asyncio.create_task(execute_scheduled_backup_with_maintenance(backup_job.id,
repo.path, job.id, archive_name=archive_name))`. The multi-repository loop
(2142) adds `"skip_hooks": scheduled_job.run_repository_scripts` to
`params` and replaces the `await backup_service.execute_backup(...)` at 2254
with:

```python
            final_status = await wait_for_backup_operation(db, backup_job.id)
```

Every `db.refresh(backup_job)` in the loop (2272, 2357) becomes
`refresh_backup_job(db, backup_job)`. The three `start_inline_maintenance`
calls in the loop and in `execute_scheduled_backup_with_maintenance` pass
`run_id=backup_job.operation.run_id, depends_on_id=backup_job.id`.

`execute_scheduled_backup_with_maintenance`: replace the `execute_backup`
call and the following `BackupJob` query with

```python
        await wait_for_backup_operation(db, backup_job_id)
        backup_job = resolve_backup_job(db, backup_job_id)
        if not backup_job or backup_job.status not in ["completed", "completed_with_warnings"]:
            ... unchanged early return ...
```

and drop the local `from app.database.models import Repository, BackupJob`
import's `BackupJob` half. The scheduler tick's 409 deferral (`Deferring
scheduled backup for active repository work`) stays as it is: admission
still runs before the row is created (Open question 7).

- [x] **Step 5: Rewrite the plan runner**

In `_execute_repository`, replace the `BackupJob(...)` creation through the
agent/server branches (1982-2067) with:

```python
            archive_name = build_archive_name(...)   # unchanged, moved up
            backup_job = create_backup_operation(
                db,
                repo,
                trigger="plan",
                executor="agent" if is_agent_executor(repo) else "server",
                backup_plan_run_id=run_id,
                params={
                    "archive_name": archive_name,
                    "skip_hooks": not context.run_repository_scripts,
                    "source_directories": context.source_directories,
                    "source_ssh_connection_id": (
                        context.source_ssh_connection_id
                        if context.source_type == "remote"
                        else None
                    ),
                    "source_locations": context.source_locations,
                    "exclude_patterns_override": context.exclude_patterns,
                    "compression_override": repository_context.compression,
                    "custom_flags_override": repository_context.custom_flags,
                    "upload_ratelimit_kib": repository_context.upload_ratelimit_kib,
                },
                commit=False,
            )
            if not is_agent_executor(repo):
                backup_job.execution_mode = execution_mode_for_route(route)
            backup_job.route_strategy = route.strategy
            child.backup_operation_id = backup_job.id
            child.status = "running"
            child.started_at = datetime.utcnow()
            db.commit()
            wake_runner()

            final_status = await wait_for_backup_operation(
                db, backup_job.id, is_cancelled=lambda: self._is_run_cancelled(run_id)
            )
            refresh_backup_job(db, backup_job)
```

`child.backup_job_id` is no longer written. The `ensure_repository_admission`
call before it stays. The `wait_for_agent_backup_job` import and the
`queue_agent_backup_job` and `dispatch_agent_job_best_effort` imports leave
this module if nothing else uses them. In `_run_maintenance` the three
`start_inline_maintenance` calls pass `run_id=backup_job.operation.run_id,
depends_on_id=backup_job.id`. The `backup_job: BackupJob` annotation becomes
`backup_job: Any`.

In `app/api/backup_plans.py`, the three `joinedload(BackupPlanRunRepository.backup_job)`
options gain a sibling `joinedload(BackupPlanRunRepository.backup_operation)`,
and `_serialize_plan_run_repository` passes
`BackupJobFacade(db, link.backup_operation) if link.backup_operation is not
None else link.backup_job` to `_serialize_backup_job`. That function needs a
`db` parameter for this; thread it through from the three callers.

- [x] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_schedule_routes.py tests/unit/test_schedulers.py tests/unit/test_api_backup_plans.py tests/unit/test_backup_plan_execution_ssh.py tests/unit/test_operations_maintenance_executors.py -v`
Expected: PASS.

---

## Task 7: Agent transport, reaper, admission, lanes

**Files:**
- Modify: `app/api/agents.py` (`_get_linked_backup_job` 424, `_mark_agent_job_started` 639-680, `_finish_linked_backup_job` 456-517)
- Modify: `app/services/agent_job_reaper.py` (110-145, 174-190)
- Modify: `app/services/job_admission.py` (`list_active_repository_work` 260-300, `count_active_manual_backup_jobs` 444, `count_active_scheduled_backup_jobs` 480)
- Modify: `app/services/operations/lanes.py` (`write_maintenance_running`)
- Test: `tests/unit/test_api_agents.py`, `tests/unit/test_agent_job_abandon.py` or `test_agent_job_requeue_window.py` (whichever covers the reaper), `tests/unit/test_operations_lanes.py`, the admission tests (`grep -l list_active_repository_work tests/unit`)

- [x] **Step 1: Write the failing tests**

`tests/unit/test_api_agents.py`, modelled on the existing linked-backup tests
at 779-1000:

```python
    def test_agent_reports_drive_the_linked_operation(self, test_client, test_db, agent_headers_and_job):
        # Fixture shape as in the neighbouring tests: an enrolled agent, one
        # queued AgentJob. Link it to a backup operation instead of a BackupJob.
        agent_headers, job = agent_headers_and_job
        op = Operation(repository_id=None, kind="backup", category="backup", status="running", trigger="manual", priority=0, run_id="r1", params={"executor": "agent"})
        test_db.add(op)
        test_db.flush()
        job.operation_id = op.id
        test_db.commit()

        with patch("app.api.agents.notification_service.send_backup_start", new=AsyncMock()) as start:
            test_client.post(f"/api/agents/jobs/{job.id}/start", headers=agent_headers, json={})
            test_client.post(f"/api/agents/jobs/{job.id}/start", headers=agent_headers, json={})
        assert start.await_count == 1

        test_client.post(f"/api/agents/jobs/{job.id}/progress", headers=agent_headers, json={"progress_percent": 55.0, "current_file": "/x", "nfiles": 3})
        test_db.refresh(op)
        assert op.progress_percent == 55.0
        assert op.progress_message == "/x"

        test_client.post(f"/api/agents/jobs/{job.id}/complete", headers=agent_headers, json={"result": {"return_code": 0, "archive_name": "agent-1"}})
        test_db.refresh(op)
        assert op.status == "completed"
        details = test_db.get(OperationBackupDetails, op.id)
        assert details.archive_name == "agent-1"
        assert details.nfiles == 3
        assert test_db.query(Operation).filter(Operation.kind == "archive_sync").count() == 0
```

Adapt the route paths and the request bodies to the ones the neighbouring
tests use; the assertions are the contract. The last line pins that the
transport does not enqueue follow-ups for an operation (the runner does when
the executor returns).

Reaper test, in the module that covers `reap_stale_agent_jobs`:

```python
def test_reaper_fails_the_linked_operation(db):
    op = Operation(kind="backup", category="backup", status="running", trigger="manual", priority=0, run_id="r1")
    db.add(op); db.flush()
    job = AgentJob(agent_machine_id=machine.id, operation_id=op.id, job_type="backup", status="running", payload={}, claimed_at=old, started_at=old, updated_at=old)
    db.add(job); db.commit()
    failed = []
    assert reap_stale_agent_jobs(db, failed_backup_job_ids=failed) == 1
    db.refresh(op)
    assert op.status == "failed"
    assert failed == [op.id]
```

Admission test (in the module that already tests
`list_active_repository_work` with an `Operation` of kind `check`): a
queued backup operation on the repository is listed as `OPERATION_BACKUP`
with `job_table == "operations"` and status `pending`, and
`ensure_repository_admission(db, repo, OPERATION_BACKUP)` raises 409 while
it exists. `count_active_manual_backup_jobs` counts a queued manual backup
operation and not a scheduled one.

Lanes test in `tests/unit/test_operations_lanes.py`: a backup operation
whose details row says `running_prune` makes `write_maintenance_running`
true.

- [x] **Step 2: Run the tests to verify they fail**

Run the four modules with `-k "operation"`. Expected: FAIL.

- [x] **Step 3: Agent transport**

`app/api/agents.py`:

```python
def _get_linked_backup_job(job: AgentJob, db: Session) -> Any:
    if job.operation_id:
        operation = db.get(Operation, job.operation_id)
        return BackupJobFacade(db, operation) if operation is not None else None
    if not job.backup_job_id:
        return None
    return db.query(BackupJob).filter(BackupJob.id == job.backup_job_id).first()
```

`_mark_agent_job_started`: the exactly-once guard moves from the backup row
to the agent job row, which both shapes share (a facade's `started_at` is
already set by the runner at dispatch, so a NULL test on it can never fire):

```python
    now = _now_utc()
    if job.claimed_at is None:
        job.claimed_at = now
    started = _normalize_agent_timestamp(started_at)
    # Guarded write: the first start report claims started_at even against a
    # concurrent report on the other transport, so exactly one report
    # triggers the backup-start notification. A requeued job keeps its
    # original started_at and does not notify again.
    first_start = (
        db.query(AgentJob)
        .filter(AgentJob.id == job.id, AgentJob.started_at.is_(None))
        .update({AgentJob.started_at: started}, synchronize_session=False)
    )
    db.expire(job, ["started_at"])
    if job.status != "cancel_requested":
        job.status = "running"
    newly_started_backup_job = None
    backup_job = _get_linked_backup_job(job, db)
    if backup_job:
        if first_start:
            backup_job.started_at = job.started_at
            newly_started_backup_job = backup_job
        backup_job.status = "running"
    else:
        _sync_repository_operation_progress(job, db)
    job.updated_at = now
    return newly_started_backup_job
```

`_finish_linked_backup_job`: the follow-up block runs only for a legacy row,
or for an operation the runner is not running:

```python
        if repository:
            repository.updated_at = _now_utc()
            from app.services.operations.runner import operation_runner

            if (
                is_backup_operation(backup_job)
                and backup_job.id in operation_runner.running_tasks
            ):
                # The executor is waiting on this agent job and the runner
                # enqueues the chain when it returns (spec 7.4).
                return
            ... existing savepoint block, unchanged ...
```

`_apply_agent_job_progress` and `_sync_backup_progress` need no change: the
facade takes every field they set. `backup_job.logs =` in
`_finish_linked_backup_job` writes the operation's log file.

`app/services/agent_job_reaper.py`, after the `if job.backup_job_id:` block:

```python
        if job.operation_id:
            operation_failed = (
                db.query(Operation)
                .filter(
                    Operation.id == job.operation_id,
                    Operation.kind == "backup",
                    Operation.status.notin_(tuple(TERMINAL_BACKUP_STATUSES)),
                )
                .update(
                    {
                        Operation.status: "failed",
                        Operation.completed_at: now,
                        Operation.error_message: message,
                    },
                    synchronize_session=False,
                )
            )
            if operation_failed and failed_backup_job_ids is not None:
                failed_backup_job_ids.append(job.operation_id)
```

and `_notify_reaped_backup_jobs` resolves each id with
`resolve_backup_job(db, backup_job_id)`.

- [x] **Step 4: Admission and lanes**

`job_admission.py`: extend `MAINTENANCE_OPERATION_KINDS` with `"backup":
OPERATION_BACKUP` and rename it `MIGRATED_OPERATION_KINDS` (update the two
readers, `lanes.py` and `agents.py`, with `grep -rn MAINTENANCE_OPERATION_KINDS
app tests`). The loop in `list_active_repository_work` then lists backup
operations with the legacy status word through `legacy_status`. Both counts:

```python
def count_active_manual_backup_jobs(db: Session) -> int:
    legacy = ... unchanged ...
    operations = (
        db.query(Operation)
        .filter(
            Operation.kind == "backup",
            Operation.status.in_(tuple(ACTIVE_OPERATION_STATUSES)),
            Operation.scheduled_job_id.is_(None),
            Operation.backup_plan_run_id.is_(None),
        )
        .count()
    )
    return legacy + operations
```

and the scheduled variant with `Operation.scheduled_job_id.isnot(None)`.

`lanes.py` `write_maintenance_running`, after the `BackupJob.maintenance_status`
query:

```python
    from app.database.models import OperationBackupDetails

    if (
        db.query(OperationBackupDetails.operation_id)
        .join(Operation, Operation.id == OperationBackupDetails.operation_id)
        .filter(
            Operation.repository_id == repository_id,
            OperationBackupDetails.maintenance_status.in_(
                _LEGACY_MAINTENANCE_BACKUP_STATUSES
            ),
        )
        .first()
    ):
        return True
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_agents.py tests/unit/test_agent_job_abandon.py tests/unit/test_agent_job_requeue_window.py tests/unit/test_operations_lanes.py tests/unit/test_job_admission*.py -v`
Expected: PASS.

---

## Task 8: Readers of the union

**Files:**
- Modify: `app/api/activity.py` (`_MIGRATED_LEGACY_MODELS` 318, `_operation_log_sources` 160, `_apply_legacy_activity_shape` 465, the three `job_models` dicts at 1286, 1610, 1823, `_get_agent_job_for_backup` 54)
- Modify: `app/services/mqtt_service.py` (190-290, 517-535)
- Modify: `app/api/metrics.py` (244-320)
- Modify: `app/api/dashboard.py` (552, 896, 1038)
- Modify: `app/services/backup_monitoring_service.py` (336)
- Modify: `app/utils/archive_job_metadata.py` (96)
- Modify: `app/services/job_history_retention.py` (366 table list, 436-460)
- Modify: `app/api/ssh_keys.py` (2387)
- Modify: `app/api/schedule.py` (1438)
- Modify: `app/utils/process_utils.py` (199, 313, 606)
- Test: `tests/unit/test_api_activity.py`, `test_activity_union.py`, `test_mqtt_service.py`, `test_api_metrics.py`, `test_api_dashboard.py`, `test_backup_monitoring_service.py`, `test_job_history_retention.py`, `test_api_ssh_keys.py`, `test_utils.py`

- [x] **Step 1: Write the failing tests**

One test per reader, each creating one legacy `BackupJob` and one backup
`Operation` (with a details row where the reader needs `archive_name` or
sizes) and asserting both appear. Concretely:

- `test_api_activity.py`: `GET /api/activity/recent` lists the operation as
  `type == "backup"` with `triggered_by == "backup_plan"` when its
  `backup_plan_run_id` is set, `schedule_name` when `scheduled_job_id` is
  set, `archive_name` from the details row, `archive_pruned_at`, and
  `has_logs` false under policy `failed_only` for a completed row;
  `GET /api/activity/backup/{op.id}/logs` serves the operation's log file
  and, for `execution_mode == "agent"`, the agent's log lines;
  `DELETE /api/activity/backup/{op.id}` deletes the operation and its
  details row; the same three routes with a legacy id still resolve the
  legacy row.
- `test_mqtt_service.py`: `publish_server_state_from_db` picks the running
  operation as `running_job` and the legacy terminal row as
  `latest_terminal_job`; `fetch_failed_repositories` sees a failed
  operation as the repository's latest.
- `test_api_metrics.py`: `borg_backup_last_job_success` and the size gauges
  read the newer operation.
- `test_api_dashboard.py`: `get_recent_jobs` and the 30-day success rate
  count both.
- `test_backup_monitoring_service.py`: the report lists both.
- `test_utils.py` (archive metadata): an archive named on a details row is
  enriched with the operation's trigger.
- `test_job_history_retention.py`: `mark_jobs_of_pruned_archives` stamps
  `OperationBackupDetails.archive_pruned_at`; an old
  `OperationBackupRetryLineage` row is purged; a purged backup operation
  takes its details row with it.
- `test_api_ssh_keys.py`: deleting a connection nulls
  `OperationBackupDetails.source_ssh_connection_id`.
- `test_utils.py` (process utils): `_mark_stale_backup_maintenance_failed`
  turns a details row's `running_compact` into `compact_failed`.

- [x] **Step 2: Run the tests to verify they fail**

Expected: FAIL.

- [x] **Step 3: Activity**

- Add `"backup": BackupJob` to `_MIGRATED_LEGACY_MODELS` and remove the
  `"backup": BackupJob` entry from the three `job_models` dicts, so
  `_is_operation_only_kind("backup", ...)` is true and the three routes take
  the operation branch with the legacy fallback `_get_operation_or_404`
  already implements.
- `_get_agent_job_for_backup(db, backup_job_id)` is replaced by the
  operation-aware `get_agent_job_for_backup(db, job)` from
  `repository_executor`; the one remaining legacy branch that called it (the
  `job_type == "backup" and execution_mode == "agent"` block at 1377) moves
  into `_operation_log_sources`:

```python
    if job_type == "backup":
        job = BackupJobFacade(db, op) if isinstance(op, Operation) else op
        text = _read_operation_log(op)
        if job.execution_mode == "agent":
            agent_job = get_agent_job_for_backup(db, job)
            if agent_job is not None:
                text = "\n".join(_get_agent_log_lines(db, agent_job.id)) or text
        return {
            "output_text": [job.logs, job.error_message],
            "file_path": getattr(op, "log_file_path", None),
            "exit_code": None,
            "text": text,
            "has_logs": backup_job_has_logs(db, job),
        }
```

  and the operation branch of `get_job_logs` and `download_job_logs` honours
  `sources.get("has_logs")` when present instead of recomputing
  `job_has_logs_by_policy` (agent logs count toward the policy, as the
  legacy branch's `_backup_job_has_logs` did).
- `_apply_legacy_activity_shape` gains a `backup` branch before the
  `rclone_sync` one:

```python
    if op.kind == "backup":
        job = BackupJobFacade(db, op)
        item["triggered_by"] = job.triggered_by
        item["backup_plan_id"] = job.backup_plan_id
        item["archive_name"] = job.archive_name
        item["archive_pruned_at"] = job.archive_pruned_at
        item["has_logs"] = backup_job_has_logs(db, job, log_save_policy=log_save_policy)
        if job.scheduled_job_id:
            scheduled_job = db.get(ScheduledJob, job.scheduled_job_id)
            item["schedule_name"] = scheduled_job.name if scheduled_job else None
        if job.backup_plan_id:
            plan = db.get(BackupPlan, job.backup_plan_id)
            item["backup_plan_name"] = plan.name if plan else None
        return
```

  `OperationItem` (`app/api/operations.py:80`) gains
  `archive_pruned_at: Optional[datetime] = None` so the field survives the
  response model; `ActivityItem` already has it.

- [x] **Step 4: MQTT, metrics, dashboard, monitoring, archive metadata**

- `mqtt_service.py`: `fetch_latest_backup_jobs_by_repository` returns
  `latest_backup_jobs_by_repository(db)`,
  `fetch_running_backup_jobs_by_repository` returns
  `latest_backup_jobs_by_repository(db, running=True)`,
  `fetch_failed_repositories` builds its set from the first of those
  (`status == "failed"` per path), and `publish_server_state_from_db` uses
  `newest_backup_job(db, running=True)`, `newest_backup_job(db)`, and
  `newest_backup_job(db, terminal=True)`. Delete `_latest_jobs_subquery`.
- `metrics.py`: the four per-repository queries become
  `latest_backup_job_for_repository(db, repo)`,
  `latest_backup_job_for_repository(db, repo, order="completed")`, and twice
  `latest_backup_job_for_repository(db, repo, statuses=("completed",
  "completed_with_warnings"), order="completed")`.
- `dashboard.py`: `get_recent_jobs` uses `backup_jobs_started_since(db,
  datetime.min, limit=limit)` (the legacy query ordered by `started_at`
  with NULLs last on SQLite; keep that by sorting the helper's result with
  `started_at is None` last, or filter `started_at.isnot(None)` if the
  existing dashboard tests accept it); the 30-day and 14-day windows use
  `backup_jobs_started_since(db, thirty_days_ago)` and
  `backup_jobs_started_since(db, fourteen_days_ago)`.
- `backup_monitoring_service.py`: `backup_jobs_started_since(db,
  period_start, until=now_naive, limit=10)`.
- `archive_job_metadata.py`: `jobs = backup_jobs_for_archive_names(db,
  repository, archive_names)`; the rest of the function reads
  `backup_plan_run_id`, `archive_name`, `scheduled_job_id`, `id` on either
  shape.

- [x] **Step 5: Retention, connection deletion, schedule deletion, startup sweep**

- `job_history_retention.py`: add `(OperationBackupRetryLineage,
  (OperationBackupRetryLineage.requested_at < cutoff,))` next to the legacy
  lineage entry at 366; in `mark_jobs_of_pruned_archives` add, after the
  legacy chunk loop, one update per chunk on the details rows:

```python
        operation_ids = [
            row.operation_id
            for row in db.query(OperationBackupDetails.operation_id)
            .join(Operation, Operation.id == OperationBackupDetails.operation_id)
            .filter(
                Operation.repository_id == repository_id,
                OperationBackupDetails.archive_pruned_at.is_(None),
                OperationBackupDetails.archive_name.in_(names[start : start + CHUNK_SIZE]),
                *([Operation.created_at <= created_before] if created_before is not None else []),
            )
            .all()
        ]
        if operation_ids:
            marked += (
                db.query(OperationBackupDetails)
                .filter(OperationBackupDetails.operation_id.in_(operation_ids))
                .update({OperationBackupDetails.archive_pruned_at: pruned_at}, synchronize_session=False)
            )
            db.commit()
```

- `ssh_keys.py` 2387: add the same `update` for
  `OperationBackupDetails.source_ssh_connection_id`.
- `schedule.py` 1438: add `db.query(Operation).filter_by(scheduled_job_id=job_id).update({"scheduled_job_id": None}, synchronize_session=False)` next to the legacy line, for the same reason the comment there gives.
- `process_utils.py`: `_mark_stale_backup_maintenance_failed` and
  `reconcile_stale_backup_maintenance` iterate `backup_jobs_in_maintenance(db)`
  instead of their `BackupJob` queries (the rest of both functions reads
  attributes the facade has). Above the `active_backup_jobs` query at 606
  add the comment the restore branch carries: rows written before phase 8;
  new backups are recovered by `OperationRunner.recover_on_startup` (spec
  7.6), which fails them the same way since a backup records no pid; empty
  after the first restart past the upgrade; goes away in phase 9.
- `app/api/repositories.py` 5248: add the same one-line comment (legacy
  rows only; operations cascade with the repository).

- [x] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_activity.py tests/unit/test_activity_union.py tests/unit/test_mqtt_service.py tests/unit/test_api_metrics.py tests/unit/test_api_dashboard.py tests/unit/test_backup_monitoring_service.py tests/unit/test_job_history_retention.py tests/unit/test_api_ssh_keys.py tests/unit/test_utils.py -v`
Expected: PASS.

---

## Task 9: Documentation and verification

**Files:**
- Modify: `docs/architecture/job-system.md` ("Backup Jobs" 44-57, "Restart Cleanup" 166-207, "Operations runner" where follow-ups are described)
- Modify: `docs/api.md` ("Start a manual backup" 48-77, "Poll job status")

- [x] **Step 1: job-system.md**

Replace the "Backup Jobs" section body with: as of section 13 phase 8 of
the operations spec, a backup is a row in `operations` (kind `backup`,
category `backup`, exclusive) with its backup columns on
`operation_backup_details` (archive name and sizes, progress fields, route
and source connection, remote host, retry lineage columns, maintenance
status). Every creation site (`POST /api/backup/start` and `/run`, the retry
route, single and multi repository schedules, backup plan runs, `POST
/api/v2/backups/run`) enqueues through `create_backup_operation`; the
runner dispatches when the repository lane is free and the concurrency
limits allow, and enqueues the index follow-up chain (`archive_sync`,
`history_merge`, `history_index`, `stats`) when the backup succeeds. Keep
the numbered flow, adding "0. enqueue" and noting that steps 5 to 7 happen
inside the executor or the calling scheduler exactly as before. Describe
the two execution paths (server: `backup_service.execute_backup`, local,
SSHFS source, or remote direct through `remote_backup_service`; agent: an
`agent_jobs` row with `operation_id`, the transport reports writing to the
operation, the executor waiting on it) and the cancel semantics (running:
flag then kill; queued: cancelled directly; agent: cancel request to the
agent). Note post-backup prune, compact and check are child operations in
the backup's run, with `maintenance_status` on the details row mirroring
them. Note that backup rows written before phase 8 stay in `backup_jobs`
and are read through the same routes until phase 9.

"Restart Cleanup": change "running backup jobs are marked `failed`" to
"running legacy backup rows are marked `failed`" and add backup to the list
of kinds the operations runner recovers; update the bullet about
`running_prune` / `running_compact` to say both the legacy column and the
details row are normalised.

- [x] **Step 2: api.md**

Under "Start a manual backup", after the response shape, add two sentences:
the `job_id` is an operations id (shared with `GET /api/operations/{id}`
and the Activity log routes with job type `backup`); a job stays `pending`
while another exclusive operation holds the repository, and `POST
/api/backup/cancel/{id}` cancels a pending job as well as a running one.

- [ ] **Step 3: Verification (superpowers:verification-before-completion)**

Run, from the worktree root, and record each result in the spec's Notes
column at G2:

```bash
pytest tests/unit -p no:randomly -q
ruff check app tests && ruff format --check app tests
git diff -U0 origin/main | grep -nP '\xe2\x80\x94' ; echo "em dashes above (expect none)"
git diff --stat origin/main -- frontend   # expect empty
grep -rn "BackupJob(" app/ | grep -v "models.py\|app/tests/"   # expect empty
alembic heads                              # expect b8c9d0e1f2a3 (head)
pytest tests/integration -q               # compare with a clean origin/main run
```

Expected: the unit suite has no failures beyond the 14 OIDC failures the
main checkout's `.env` causes (none in the worktree without an `.env`);
ruff clean; no em dashes; no frontend diff; no `BackupJob(` outside the
model and the legacy test; one Alembic head; the integration failures
identical to origin/main's (phase 7 recorded 3 failed and 15 errors from
`test_api_maintenance_jobs_integration`, `test_api_repositories_integration`,
`test_mount_shadowing_aggressive`). Then stop at gate G2.

---

## Self-review

Spec coverage: 6.1 (columns reused, `execution_mode` in spec words) Task 2;
6.2 (extension table, columns moved not changed) Task 1; 6.3 (status
mapping, maintenance children) Tasks 2 and 6; 7.1 (enqueue, deferral on the
agent 409) Tasks 4 and 5; 7.2 (lane, `write_maintenance_running`) Task 7;
7.3 (limits) already in `lanes.py`, route counts Task 7; 7.4 (runner
follow-ups) Tasks 3 and 4; 7.6 (recovery) inherited from the runner, sweep
Task 8; 7.7 (cancel) Tasks 4 and 5; 7.8 (retention) Task 8; 9.3 (Activity
union) Task 8; section 13 phase 8 row items: v1 and v2 routes Task 5, plan
execution Task 6, retry lineage Tasks 1 and 5, `AgentJob.operation_id`
Tasks 1, 3, 7, maintenance states as child operations Task 6,
notifications and MQTT Tasks 4 (unchanged senders) and 8; section 15
(columns move, not change) throughout; Appendix B (unqualified ids, phase 6
partial-failure precedent) Tasks 2 and 4.

Type consistency: `get_agent_job_for_backup(db, job)` takes the job object
in Tasks 3, 4, 5, 8; `create_backup_operation` keyword set is identical in
Tasks 2, 5, 6; `wait_for_backup_operation(db, id, *, is_cancelled,
poll_interval_seconds)` in Tasks 2, 5, 6; `backup_job_has_logs(db, job, *,
log_save_policy)` in Tasks 2, 5, 8; `MIGRATED_OPERATION_KINDS` rename in
Task 7 only.

## Open questions

Each takes its default unless the owner says otherwise at G1.

1. **`archive_pruned_at` on the details row.** Spec 6.2's list predates
   the column (migration a5b7c9d1e3f2), and the list, status, Activity, and
   plan run payloads return it. Default: add it, as phase 7 added
   `original_size`. Alternative: derive it from the `archives` table at read
   time, which changes the meaning (the archives table knows removals only
   after a listing).
2. **A new `operation_backup_retry_lineage` table with unqualified ids.**
   `backup_job_retry_lineage` has three foreign keys into `backup_jobs`,
   enforced on both dialects, so it cannot hold operation ids. Default: a
   parallel table keyed to operations with no foreign keys on the three id
   columns (a retry of a pre-phase-8 job names a legacy id, Appendix B),
   purged by `requested_at` like the old one, which phase 9 deletes.
   Alternative: drop the three constraints from the old table by migration
   and keep writing it, mixing id spaces in one table until phase 9.
3. **Inline callers enqueue and wait.** The multi repository schedule, the
   scheduler's post-backup maintenance, the plan runner, and the v2 route
   ran `execute_backup` in their own task and continued afterwards.
   Default: they enqueue and `wait_for_backup_operation`, so every backup
   is dispatched by the runner on the lane (spec 2, "one runner owns the
   repository lane"). Alternative: create the row `running` and run the
   service inline as phase 5 did for post-backup maintenance, which keeps
   backups outside the lane and the limits.
4. **A post-hook failure after a successful `borg create` still gets the
   index chain**, enqueued by the executor with the parent's `run_id` and
   no dependency, the phase 6 precedent Appendix B records. Spec 7.4 as
   written would leave the new archive unlisted until the next reconcile.
5. **Post-backup prune, compact, and check join the backup's run**
   (`run_id` and `depends_on_id` on `start_inline_maintenance`), which is
   what spec 6.3's "child" wording means. Visible effect: with
   `collapse_runs` the Activity list nests them under the backup instead of
   listing them as top-level rows. Alternative: leave them as separate runs.
6. **The agent start notification's exactly-once guard moves to the
   `agent_jobs` row.** The legacy guard was a NULL test on
   `backup_jobs.started_at`; an operation's `started_at` is written by the
   runner at dispatch, before the agent claims the job, so that test can
   never fire. The agent job's own `started_at` is shared by both transports
   and both shapes.
7. **Route level admission and capacity 409s stay** (`ensure_repository_admission`,
   `ensure_manual_backup_capacity`, the scheduler's deferral on 409), now
   counting backup operations, so a manual backup during a wipe still
   answers 409 exactly as today; the lane is the second guard for anything
   admission did not see. The v2 route gains the admission check it lacked,
   since a queued row blocked behind a wipe would otherwise hang the
   request. Alternative: drop the route 409s and let every backup queue
   (more "fewer lock errors", but a visible change on the manual route).
8. **`operations.execution_mode` stores the spec 6.1 word `server`** for
   what the legacy column called `local`; the facade translates both ways,
   so the routes keep answering `local` and the Background work board reads
   the spec vocabulary.
9. **Prometheus, MQTT, dashboard, and the backup report read the union.**
   Phases 5 to 7 left their kinds' metrics on the legacy tables until phase
   9; backup is the metric people alert on, so leaving it would be a
   regression from the day the phase ships.
10. **Crash recovery for agent backups** matches the legacy sweep: a
    `running` backup operation with no live pid is failed at startup
    ("interrupted by restart"); an agent completion report that arrives
    later overwrites the verdict through the facade, as it overwrote the
    legacy row, and enqueues the index chain itself since the runner no
    longer holds the task (Task 7).
