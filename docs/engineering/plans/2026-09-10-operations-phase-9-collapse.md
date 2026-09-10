# Operations Phase 9: Collapse and Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit at the
> end of a task; the phase has one commit gate (G2) at the end, per section
> 19.4 of the spec and `.claude/instructions.md`.

**Goal:** Finish the migration the spec started in phase 1: every job kind
already runs as an `operations` row, so this phase deletes the ten legacy job
tables and every branch of code that still reads them, makes Activity read
`operations` alone (spec 9.3, A.2), removes `legacy_running_exclusive` (spec
7.2) and the unqualified id ambiguity Appendix B tolerated, and rewrites the
job documentation, `docs/api.md`, and the Postman collection around operations
(spec 18), without changing a single HTTP response body or status word.

**Architecture:** One Alembic revision does the destructive work in two steps:
it copies every legacy row into `operations` (plus the spec 6.2 details rows,
the retry lineage table, and the three link columns phase 8 added), then drops
the tables and the legacy link columns. The copy is section 14's "explicit
one-off copy": no release has shipped any of phases 5 to 8 (the newest tag,
`v2.3.0-alpha.1`, predates phase 1), so every real install would go straight
from full legacy tables to the collapse and the retention window section 14
offers as the alternative cannot have elapsed for anyone. The copy lives in a
plain module (`app/database/legacy_job_collapse.py`) driven by frozen
SQLAlchemy Core table definitions (`app/database/legacy_job_tables.py`), so it
is unit tested against a scratch database and callable from both the revision
and the pre-Alembic upgrade path. That path (`db_upgrade.alembic_init`) must
change too: it builds the target at head and copies rows by model metadata, so
once the models are gone a `v2.2.x` install's job history would be silently
skipped. It now upgrades the target to the last pre-collapse revision, copies
rows by the target's reflected schema, and then continues to head so the
collapse revision folds the rows it just received. The five facades stay as
the attribute adapter the services drive; only their legacy fallbacks go.

**Tech Stack:** FastAPI, SQLAlchemy 1.x (declarative models for the app, Core
`Table` objects for the frozen legacy schema), Alembic with `batch_alter_table`
for SQLite, pytest with the `test_db` / `test_client` / `admin_headers`
fixtures from `tests/fixtures/api.py`, the in-memory `db` fixture pattern from
`tests/unit/test_operations_backup_facade.py`, and the `_migrate(url, target)`
helper pattern from `tests/unit/test_backup_job_archive_pruned_at_migration.py`.
No new dependencies.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`,
sections 6.2, 6.3 (the status mapping table), 7.2, 7.6, 9.3, 13 (phase 9
row), 14, 18, Appendix A.1, A.2, Appendix B. Review focus (19.3): 9.3, 14,
18, Appendix B.

## Model

Section 13 gives phase 9 Opus 5 to implement and Sonnet 5 to review
("Deletion and documentation with a full test suite behind it"). This plan
was drafted on Fable 5.1 at the owner's choice at gate G0 on 2026-09-10, the
same deviation phases 4, 6 and 7 recorded for their drafts.

## Global Constraints

- Phase 9 is backend and documentation only. No frontend file changes, no
  i18n keys, no stories. Every HTTP response body keeps the exact shape and
  the exact status vocabulary it has today, per section 13 ("Phases 5
  through 9 are internal refactors with no visible change except fewer lock
  errors"). The load-bearing contracts, already pinned by the phase 5 to 8
  tests and kept green here: `GET /api/activity/recent` items, the four
  Activity log and delete routes by `{job_type}/{job_id}`, `GET
  /api/backup/jobs`, `/status/{id}`, `/cancel/{id}`, the maintenance status
  and list routes, `GET /api/restore/jobs` and `/status/{id}`, the wipe
  status route, `GET /api/packages/jobs`, the dashboard payloads, the
  Prometheus text format, and the MQTT topics.
- The only rows that may disappear are rows that were already unreachable:
  a legacy row whose repository no longer exists and whose kind requires
  one (Open question 3). Everything else is copied. After the revision,
  `SELECT count(*) FROM operations` has grown by the number of legacy rows
  copied, and the test in Task 2 asserts the per-table counts.
- Copied rows get new ids. Nothing in the frontend or the API contract
  promises id stability across an upgrade (rows are keyed on
  `activity_key`, lists are refetched), and the three link columns are
  rewritten to the new ids. This is the mechanism that removes the
  Appendix B ambiguity: after this phase there is one id space.
- `repository_wipe_jobs` is not a job table any more and is not deleted. It
  is the wipe preview store (Appendix B, phase 6: "the wipe preview stays
  in `repository_wipe_jobs`"). Its executed rows (status other than
  `previewed`) are copied to `wipe` operations and deleted; its `previewed`
  rows stay; the model class stays under its current name (Open question
  4).
- `app/database/migrations/` (the frozen pre-Alembic ladder) is not touched.
  It exists to catch a `v2.2.x` database up before the transfer and must
  keep producing the legacy tables that transfer then copies.
- Spec 6.3 is verbatim and already in `vocab.py`; `LEGACY_STATUS_MAP` is the
  mapping the copy uses (`pending` to `queued`, `needs_backup` to
  `skipped`, the maintenance words to `running` or `failed`). Do not edit
  `vocab.py`. Do not edit `followups.py`.
- After this phase, these greps return nothing outside
  `app/database/legacy_job_tables.py`, `app/database/legacy_job_collapse.py`,
  and the Alembic versions directory:
  `grep -rnE '\b(BackupJob|CheckJob|PruneJob|CompactJob|RestoreCheckJob|DeleteArchiveJob|RcloneSyncJob|PackageInstallJob|RestoreJob|BackupJobRetryLineage)\b' app/`
  and `grep -rn "legacy_running_exclusive\|legacy_status\b\|LEGACY_MODELS\|_MIGRATED_LEGACY_MODELS\|_LEGACY_ACTIVE_STATUSES" app/`.
  `RepositoryWipeJob` may still appear, in the wipe service and the two
  wipe routes only, and only for previews.
- No em dashes anywhere: code comments, docstrings, docs, or commit message.
  Check added lines only, with `git diff -U0 origin/main | grep -nP '\xe2\x80\x94'`.
- One commit at the end of the phase, at gate G2, after
  `superpowers:verification-before-completion` passes. Nothing is pushed
  without the owner's answer at that gate.
- Before writing the migration, confirm the parent is the single head. Run,
  from the worktree root: `alembic heads` (or `python3 -m alembic heads`).
  Expected: exactly `b8c9d0e1f2a3 (head)`. If another head appeared (the
  agent upgrades phase 4 branch adds revisions), re-parent onto it, update
  `PRE_COLLAPSE_REVISION` in Task 3 to that head, and record it in the
  spec's Notes column, as phases 6 and 7 did.
- Worktree: `.worktrees/operations-phase-9`, branch `feat/operations-phase-9`
  off `origin/main`, per the owner's standing instruction to work in a
  worktree.

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `app/database/legacy_job_tables.py` | Frozen Core `Table` definitions of the ten legacy tables on their own `MetaData`, exactly as `models.py` declared them before this phase. Used by the copy, the revision's downgrade, and the tests. |
| `app/database/legacy_job_collapse.py` | `collapse_legacy_job_tables(connection, *, log_dir) -> CollapseReport`: the copy, one function per table, id maps, link rewrites, log file materialisation. Core only, no ORM. |
| `app/database/alembic/versions/d0e1f2a3b4c5_collapse_legacy_job_tables.py` | The one revision: copy, then drop nine tables and three link columns, then delete executed wipe rows. |
| `tests/unit/test_legacy_job_collapse.py` | The copy against a scratch SQLite built at `b8c9d0e1f2a3`, table by table. |
| `tests/unit/test_collapse_legacy_job_tables_migration.py` | The revision up and down, the one-head check, the counts. |

**Modified**

| File | Change |
| --- | --- |
| `app/database/models.py` | Delete `RcloneSyncJob`, `BackupJob`, `BackupJobRetryLineage`, `RestoreJob`, `CheckJob`, `RestoreCheckJob`, `CompactJob`, `PruneJob`, `DeleteArchiveJob`, `PackageInstallJob`; delete `AgentJob.backup_job_id`, `ScriptExecution.backup_job_id` and its `backup_job` relationship, `BackupPlanRunRepository.backup_job_id` and its `backup_job` relationship. `RepositoryWipeJob` stays. |
| `app/database/db_upgrade.py` | `PRE_COLLAPSE_REVISION`; `_upgrade_to(url, revision, engine)`; `_transfer` reads the target's reflected schema; `alembic_init` runs upgrade-to-pre-collapse, transfer, upgrade-to-head. |
| `app/services/operations/job_facade.py` | `LEGACY_MODELS` gone; `resolve_maintenance_job` and `claim_running` operations only. `legacy_status` / `operation_status` stay (the routes still speak `pending`). |
| `app/services/operations/backup_facade.py` | `resolve_backup_job`, `admission_ignore_for`, `backup_job_link_columns`, and the seven union helpers read one table. |
| `app/services/operations/restore_facade.py`, `wipe_facade.py`, `rclone_facade.py`, `package_facade.py`, `maintenance_start.py` | Legacy fallbacks and `_LEGACY_ACTIVE_STATUSES` gone. |
| `app/services/operations/legacy_status.py` | Deleted. |
| `app/services/operations/lanes.py` | `legacy_running_exclusive` deleted; `lane_free` and `write_maintenance_running` read operations and details rows only. |
| `app/services/operations/repository_status.py` | The `legacy` source and the two `latest_legacy_*` calls gone; the deletion evidence reads operations and wipe previews' executed rows no longer exist. |
| `app/services/job_admission.py` | Backup and wipe active work from operations; `MAINTENANCE_MODEL_OPERATIONS` gone; `count_active_manual_backup_jobs` one query. |
| `app/api/activity.py` | `list_recent_activity` reads operations, plan-run skips, availability skips, and script executions; per-table blocks, `_MIGRATED_LEGACY_MODELS`, the legacy branches of `_get_operation_or_404`, `_read_operation_log`, `_operation_log_sources`, and `_get_agent_job_for_backup` gone. |
| `app/utils/process_utils.py` | `cleanup_orphaned_jobs` keeps the stale maintenance sweep and the plan run normalisation; the five legacy loops, `_has_running_check_child`'s legacy branch, `_MAINTENANCE_CHILD_MODELS`, `_ORPHAN_MAINTENANCE_MODELS`, and `reconcile_orphaned_maintenance_jobs` go. |
| `app/services/agent_job_reaper.py` | The `backup_job_id` branch gone; `_notify_reaped_backup_jobs` takes operation ids; `reap_once` drops the orphan pass. |
| `app/services/check_scheduler.py` | `cleanup_stale_scheduled_check_jobs` deleted; `count_active_scheduled_check_jobs` is the operations count. |
| `app/services/log_manager.py` | The legacy model list gone. |
| `app/services/job_history_retention.py` | `_JOB_TABLES` keeps `AgentJob`, `RepositoryWipeJob` (previews), `ScriptExecution`, `BackupPlanRun`, `AvailabilityScheduleSkip`, `Operation`; the `BackupJobRetryLineage` purge and the legacy branch of `mark_jobs_of_pruned_archives` go. |
| `app/core/borg_router.py` | `_fail_orphaned_maintenance_job` fails the `Operation`; `update_stats` deleted. |
| `app/services/rclone_mirror_scheduler.py` | The `RcloneSyncJob` dedupe branch gone. |
| `app/api/backup.py` | `_get_running_maintenance_job` finds the running child operation; the `"Logs saved to:"` branches of `_resolve_backup_log_file`, the download route, and the stream route go. |
| `app/api/maintenance_jobs.py` | `get_repository_maintenance_jobs` reads operations. |
| `app/api/packages.py`, `app/services/package_service.py` | Operations only. |
| `app/api/repositories.py` | `_newer_rclone_job` and the `RcloneSyncJob` query gone; `_legacy_running` gone; the delete route drops the five legacy loops and the backup unlink. |
| `app/services/repository_wipe_service.py` | The legacy model loop and the `RestoreJob` loop gone; previews unchanged. |
| `app/api/schedule.py` | The `BackupJob` unlink on schedule delete and the availability `last_success` query read operations. |
| `app/api/agents.py` | `_get_linked_backup_job` reads `operation_id`; `_maintenance_kind` reads the facade; `LEGACY_MODELS` import gone. |
| `app/api/ssh_keys.py` | The two legacy nulling updates gone. |
| `app/api/dashboard.py` | Latest restore check and the 14-day check, compact, prune, restore check lists read operations. |
| `app/api/metrics.py` | Every family reads operations; `borg_backup_orphaned_jobs_total` is emitted empty. |
| `app/api/settings.py`, `app/routers/config.py` | Callers of `update_stats` enqueue `stats` and `archive_sync`. |
| `app/services/agent_job_notifications.py`, `app/services/restore_check_service.py`, `app/services/v2/prune_service.py`, `app/services/v2/delete_archive_service.py`, `app/services/v2/compact_service.py`, `app/utils/archive_job_metadata.py`, `app/services/backup_progress_contract.py`, `app/services/backup_route_planner.py`, `app/services/script_library_executor.py`, `app/services/repository_executor.py`, `app/services/remote_backup_service.py`, `app/services/backup_service.py`, `app/services/backup_plan_execution_service.py`, `app/api/backup_plans.py`, `app/api/v2/backups.py`, `app/api/scripts.py` | Type hints, imports, docstrings, and the two v2 `except` branches. |
| `app/tests/test_repository_deletion.py` | Deleted (not collected; tested legacy tables). |
| `docs/architecture/job-system.md`, `docs/api.md`, `docs/navigation.md`, `docs/METRICS.md`, `Borg_UI_API.postman_collection.json` | Task 9. |
| Tests, per task: `test_db_upgrade.py`, `test_operations_job_facade.py`, `test_operations_backup_facade.py`, `test_operations_backup_union_readers.py`, `test_operations_restore_facade.py`, `test_operations_wipe_facade.py`, `test_operations_rclone_facade.py`, `test_operations_package_facade.py`, `test_maintenance_start.py`, `test_operations_lanes.py`, `test_repository_last_runs.py`, `test_api_activity.py`, `test_activity_union.py`, `test_utils.py`, `test_schedulers.py`, `test_log_manager.py`, `test_job_history_retention.py`, `test_api_backup.py`, `test_api_maintenance_migration.py`, `test_api_maintenance_jobs.py`, `test_api_packages.py`, `test_package_service.py`, `test_startup_packages.py`, `test_api_repositories.py`, `test_api_repositories_routes.py`, `test_api_repository_wipe.py`, `test_repository_wipe_service.py`, `test_api_rclone.py`, `test_rclone_repository_service.py`, `test_api_schedule.py`, `test_api_schedule_routes.py`, `test_api_agents.py`, `test_api_ssh_keys.py`, `test_api_dashboard.py`, `test_api_metrics.py`, `test_mqtt_service.py`, `test_backup_service.py`, `test_backup_service_mocks.py`, `test_remote_backup_service.py`, `test_api_restore.py`, `test_restore_service.py`, `test_restore_check_service.py`, `test_prune_service.py`, `test_delete_archive_service.py`, `test_v2_services.py`, `test_v2_prune_service.py`, `test_api_backup_plans.py`, `test_api_archives.py`, `test_api_archive_index.py`, `test_api_v2_archives.py`, `test_api_v2_backups.py`, `test_api_v2_repositories.py`, `test_borg_router.py`, `test_backup_monitoring_service.py`, `test_notification_service.py`, `test_restore_agent_delegation.py`, `test_ssh_key_in_maintenance_services.py`, `tests/integration/test_scheduled_jobs_bugfixes.py`, `test_api_schedule_integration.py`, `test_backup_workflows_integration.py`, `test_api_maintenance_jobs_integration.py` | Every construction of a legacy row becomes an operation (Task 7 lists the helper), every "still serves a pre-phase-N row" test is deleted. |

---

## Task 1: Frozen legacy schema and the copy

**Files:**
- Create: `app/database/legacy_job_tables.py`
- Create: `app/database/legacy_job_collapse.py`
- Test: `tests/unit/test_legacy_job_collapse.py`

**Interfaces:**
- Consumes: the `operations`, `operation_*_details`, `operation_backup_retry_lineage`, `agent_jobs`, `script_executions`, `backup_plan_run_repositories`, and `repositories` tables as they stand at revision `b8c9d0e1f2a3`, reflected from the connection. `app.services.operations.vocab.LEGACY_STATUS_MAP`, `category_for`, `priority_for_trigger`. `app.services.operations.rclone_facade.LEGACY_TO_TRIGGER`. `app.services.operations.wipe_facade._TO_OPERATION`, `_PHASE_FOR_STATUS`. `app.services.operations.package_facade._HEADER_PREFIX`.
- Produces: `legacy_job_tables.metadata` (a `MetaData`) and the ten `Table` objects `backup_jobs`, `backup_job_retry_lineage`, `restore_jobs`, `check_jobs`, `restore_check_jobs`, `compact_jobs`, `prune_jobs`, `delete_archive_jobs`, `repository_wipe_jobs`, `rclone_sync_jobs`, `package_install_jobs`; `LEGACY_JOB_TABLE_NAMES` (the nine dropped tables, in drop order); `collapse_legacy_job_tables(connection, *, log_dir: Path) -> CollapseReport` with `CollapseReport.copied: dict[str, int]`, `.skipped: dict[str, int]`, `.id_maps: dict[str, dict[int, int]]`.

- [x] **Step 1: Write the frozen table module**

Copy every column of the ten legacy classes from `app/database/models.py`
(`RcloneSyncJob` 654-677, `BackupJob` 694-779, `BackupJobRetryLineage`
781-812, `RestoreJob` 814-859, `CheckJob` 1267-1302, `RestoreCheckJob`
1304-1348, `CompactJob` 1350-1381, `PruneJob` 1383-1406, `DeleteArchiveJob`
1408-1437, `RepositoryWipeJob` 1439-1480, `PackageInstallJob` 2181-2205) into
Core `Table` definitions. The file starts:

```python
"""The legacy job tables, frozen at the moment phase 9 deleted them.

Core definitions on their own MetaData, never on `Base`: the ORM must not know
these tables exist any more. Three readers need them: the collapse copy
(`legacy_job_collapse`), the collapse revision's downgrade (which recreates
them empty), and the tests that build a pre-collapse database. Column order,
types, and foreign keys are exactly what `models.py` declared at revision
b8c9d0e1f2a3. Do not add columns; do not reuse these for new code.
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

backup_jobs = Table(
    "backup_jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("repository", String),
    Column("repository_id", Integer, ForeignKey("repositories.id", ondelete="SET NULL")),
    Column("backup_plan_id", Integer, ForeignKey("backup_plans.id", ondelete="SET NULL")),
    Column("backup_plan_run_id", Integer, ForeignKey("backup_plan_runs.id", ondelete="SET NULL")),
    Column("status", String, default="pending"),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("progress", Integer, default=0),
    Column("error_message", Text),
    Column("logs", Text),
    Column("log_file_path", String),
    Column("scheduled_job_id", Integer, ForeignKey("scheduled_jobs.id")),
    Column("original_size", BigInteger, default=0),
    Column("compressed_size", BigInteger, default=0),
    Column("deduplicated_size", BigInteger, default=0),
    Column("nfiles", Integer, default=0),
    Column("current_file", Text),
    Column("progress_percent", Float, default=0.0),
    Column("backup_speed", Float, default=0.0),
    Column("total_expected_size", BigInteger, default=0),
    Column("estimated_time_remaining", Integer, default=0),
    Column("archive_name", String),
    Column("archive_pruned_at", DateTime),
    Column("maintenance_status", String),
    Column("execution_mode", String, default="local"),
    Column("route_strategy", String),
    Column("source_ssh_connection_id", Integer, ForeignKey("ssh_connections.id")),
    Column("remote_process_pid", Integer),
    Column("remote_hostname", String),
    Column("retry_original_job_id", Integer, ForeignKey("backup_jobs.id", ondelete="SET NULL")),
    Column("retry_source_job_id", Integer, ForeignKey("backup_jobs.id", ondelete="SET NULL")),
    Column("retry_attempt", Integer, default=1, nullable=False),
    Column("retry_requested_by_user_id", Integer, ForeignKey("users.id", ondelete="SET NULL")),
    Column("retry_requested_at", DateTime),
    Column("created_at", DateTime),
)
```

Continue in the same shape for the other nine tables, one `Table` each,
including `repository_wipe_jobs` (needed by the copy of executed rows and by
the tests; it is not in the drop list). Close the module with:

```python
# Dropped by the collapse revision, children before parents so PostgreSQL
# never sees a dangling foreign key. `repository_wipe_jobs` is deliberately
# absent: it is the wipe preview store and survives the phase.
LEGACY_JOB_TABLE_NAMES = (
    "backup_job_retry_lineage",
    "backup_jobs",
    "restore_jobs",
    "check_jobs",
    "restore_check_jobs",
    "compact_jobs",
    "prune_jobs",
    "delete_archive_jobs",
    "rclone_sync_jobs",
    "package_install_jobs",
)
```

Foreign keys that pointed at `backup_jobs` from other tables
(`agent_jobs.backup_job_id`, `script_executions.backup_job_id`,
`backup_plan_run_repositories.backup_job_id`) are not defined here; they are
columns of surviving tables and are handled by the revision.

- [x] **Step 2: Write the failing copy tests**

`tests/unit/test_legacy_job_collapse.py` builds a scratch SQLite at revision
`b8c9d0e1f2a3` (every legacy table present, every operations table present),
inserts rows through the frozen tables, runs the copy, and reads back through
the reflected operations tables. The fixture:

```python
"""The one-off copy of legacy job rows into `operations` (spec section 14)."""

import json
from datetime import datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import MetaData, insert, select, text

from app.database import legacy_job_tables as legacy
from app.database.db_upgrade import _alembic_config, _engine
from app.database.legacy_job_collapse import collapse_legacy_job_tables

PRE_COLLAPSE = "b8c9d0e1f2a3"
NOW = datetime(2026, 9, 1, 12, 0, 0)


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, PRE_COLLAPSE)
        connection.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def log_dir(tmp_path):
    return tmp_path / "logs"


def _tables(connection):
    meta = MetaData()
    meta.reflect(bind=connection)
    return meta.tables


def _seed_repository(connection, repo_id=1, path="/srv/repo"):
    tables = _tables(connection)
    connection.execute(
        insert(tables["repositories"]).values(
            id=repo_id, name=f"repo{repo_id}", path=path, encryption="none",
            compression="lz4", mode="full", created_at=NOW,
        )
    )


def _operations(connection, kind):
    tables = _tables(connection)
    ops = tables["operations"]
    return connection.execute(
        select(ops).where(ops.c.kind == kind).order_by(ops.c.id)
    ).mappings().all()
```

Then the tests, one per table plus the links. Write them all before the
implementation; each names the mapping it pins:

```python
@pytest.mark.unit
def test_backup_rows_become_backup_operations_with_details(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        connection.execute(
            insert(legacy.backup_jobs).values(
                id=7, repository="/srv/repo", repository_id=1, status="completed",
                started_at=NOW, completed_at=NOW + timedelta(minutes=5),
                progress=100, progress_percent=100.0, archive_name="daily-1",
                original_size=10, compressed_size=5, deduplicated_size=2, nfiles=3,
                execution_mode="local", route_strategy="local", created_at=NOW,
                scheduled_job_id=None, maintenance_status="maintenance_completed",
            )
        )
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    assert report.copied["backup_jobs"] == 1
    with engine.connect() as connection:
        [op] = _operations(connection, "backup")
        assert op["category"] == "backup"
        assert op["status"] == "completed"
        assert op["trigger"] == "manual"
        assert op["priority"] == 0
        assert op["repository_id"] == 1
        assert op["execution_mode"] == "server"
        assert op["progress_percent"] == 100.0
        assert op["started_at"] == NOW
        assert op["created_at"] == NOW
        assert len(op["run_id"]) == 36
        details = _tables(connection)["operation_backup_details"]
        [row] = connection.execute(
            select(details).where(details.c.operation_id == op["id"])
        ).mappings().all()
        assert row["archive_name"] == "daily-1"
        assert row["nfiles"] == 3
        assert row["maintenance_status"] == "maintenance_completed"
        assert row["retry_attempt"] == 1
    assert report.id_maps["backup_jobs"] == {7: op["id"]}


@pytest.mark.unit
def test_backup_trigger_and_status_words(engine, log_dir):
    """pending -> queued; a plan run row is trigger plan; a schedule row is
    trigger schedule at priority 5; a retry row is trigger retry."""
    with engine.begin() as connection:
        _seed_repository(connection)
        tables = _tables(connection)
        connection.execute(
            insert(tables["scheduled_jobs"]).values(
                id=3, name="nightly", cron_expression="0 2 * * *", enabled=True,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(tables["backup_plan_runs"]).values(
                id=9, trigger="manual", status="completed", created_at=NOW
            )
        )
        connection.execute(
            insert(legacy.backup_jobs),
            [
                dict(id=1, repository="/srv/repo", repository_id=1, status="pending", created_at=NOW),
                dict(id=2, repository="/srv/repo", repository_id=1, status="failed", scheduled_job_id=3, created_at=NOW),
                dict(id=3, repository="/srv/repo", repository_id=1, status="completed", backup_plan_run_id=9, created_at=NOW),
                dict(id=4, repository="/srv/repo", repository_id=1, status="cancelled", retry_source_job_id=2, retry_original_job_id=2, retry_attempt=2, created_at=NOW),
            ],
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        ops = _operations(connection, "backup")
        by_old = {op["params"]["legacy_id"]: op for op in ops}
        assert by_old[1]["status"] == "queued"
        assert by_old[2]["trigger"] == "schedule" and by_old[2]["priority"] == 5
        assert by_old[2]["scheduled_job_id"] == 3
        assert by_old[3]["trigger"] == "plan" and by_old[3]["backup_plan_run_id"] == 9
        assert by_old[4]["trigger"] == "retry"
        details = _tables(connection)["operation_backup_details"]
        [retry] = connection.execute(
            select(details).where(details.c.operation_id == by_old[4]["id"])
        ).mappings().all()
        assert retry["retry_source_job_id"] == by_old[2]["id"]
        assert retry["retry_original_job_id"] == by_old[2]["id"]


@pytest.mark.unit
def test_backup_repository_resolved_by_path_when_id_missing(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection, repo_id=4, path="/srv/old")
        connection.execute(
            insert(legacy.backup_jobs),
            [
                dict(id=1, repository="/srv/old/", status="completed", created_at=NOW),
                dict(id=2, repository="/nowhere", status="failed", created_at=NOW),
            ],
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        ops = _operations(connection, "backup")
        by_old = {op["params"]["legacy_id"]: op for op in ops}
        assert by_old[1]["repository_id"] == 4
        assert by_old[2]["repository_id"] is None
        assert by_old[2]["params"]["repository"] == "/nowhere"


@pytest.mark.unit
def test_backup_inline_logs_become_the_operation_log_file(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        (log_dir).mkdir()
        (log_dir / "backup_job_2.log").write_text("from file\n")
        connection.execute(
            insert(legacy.backup_jobs),
            [
                dict(id=1, repository="/srv/repo", repository_id=1, status="failed", logs="inline text", created_at=NOW),
                dict(id=2, repository="/srv/repo", repository_id=1, status="failed", logs="Logs saved to: backup_job_2.log", created_at=NOW),
                dict(id=3, repository="/srv/repo", repository_id=1, status="completed", log_file_path=str(log_dir / "backup_job_2.log"), created_at=NOW),
            ],
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        ops = {op["params"]["legacy_id"]: op for op in _operations(connection, "backup")}
    assert ops[1]["log_file_path"] == str(log_dir / f"operation_{ops[1]['id']}.log")
    assert (log_dir / f"operation_{ops[1]['id']}.log").read_text() == "inline text"
    assert ops[2]["log_file_path"] == str(log_dir / "backup_job_2.log")
    assert ops[3]["log_file_path"] == str(log_dir / "backup_job_2.log")


@pytest.mark.unit
def test_links_are_rewritten_to_the_new_ids(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        tables = _tables(connection)
        connection.execute(
            insert(legacy.backup_jobs).values(id=5, repository="/srv/repo", repository_id=1, status="completed", created_at=NOW)
        )
        connection.execute(
            insert(tables["agent_machines"]).values(id=1, name="m", token_hash="x", status="online", created_at=NOW, updated_at=NOW)
        )
        connection.execute(
            insert(tables["agent_jobs"]).values(id=1, agent_machine_id=1, backup_job_id=5, job_type="backup", status="completed", payload={}, created_at=NOW, updated_at=NOW)
        )
        connection.execute(
            insert(tables["backup_plan_runs"]).values(id=1, trigger="manual", status="completed", created_at=NOW)
        )
        connection.execute(
            insert(tables["backup_plan_run_repositories"]).values(id=1, backup_plan_run_id=1, repository_id=1, backup_job_id=5, status="completed")
        )
        connection.execute(
            insert(tables["script_executions"]).values(id=1, backup_job_id=5, hook_type="pre_backup", status="completed", created_at=NOW)
        )
        connection.execute(
            insert(legacy.backup_job_retry_lineage).values(
                id=1, original_job_id=5, retry_source_job_id=5, attempt_number=2,
                requested_at=NOW, created_job_id=5, request_snapshot={"kind": "backup_job_retry"},
            )
        )
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    new_id = report.id_maps["backup_jobs"][5]
    with engine.connect() as connection:
        tables = _tables(connection)
        assert connection.execute(select(tables["agent_jobs"].c.operation_id)).scalar() == new_id
        assert connection.execute(select(tables["backup_plan_run_repositories"].c.backup_operation_id)).scalar() == new_id
        assert connection.execute(select(tables["script_executions"].c.operation_id)).scalar() == new_id
        [lineage] = connection.execute(select(tables["operation_backup_retry_lineage"])).mappings().all()
        assert (lineage["original_job_id"], lineage["retry_source_job_id"], lineage["created_operation_id"]) == (new_id, new_id, new_id)
        assert lineage["request_snapshot"] == {"kind": "backup_job_retry"}
```

Add one test per remaining table in the same style, asserting the mapping
rows of Step 3's tables:

```python
@pytest.mark.unit
def test_restore_rows(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        connection.execute(
            insert(legacy.restore_jobs).values(
                id=1, repository="/srv/repo", archive="daily-1", destination="/tmp/out",
                status="completed", progress=100, nfiles=4, original_size=100,
                restored_size=100, restore_speed=1.5, destination_type="local",
                repository_type="local", logs="restored ok", created_at=NOW,
            )
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        [op] = _operations(connection, "restore")
        assert op["category"] == "restore" and op["repository_id"] == 1
        assert op["execution_mode"] == "server"
        details = _tables(connection)["operation_restore_details"]
        [row] = connection.execute(select(details)).mappings().all()
        assert (row["archive"], row["destination"], row["nfiles"], row["restored_size"]) == ("daily-1", "/tmp/out", 4, 100)
        assert (log_dir / f"operation_{op['id']}.log").read_text() == "restored ok"


@pytest.mark.unit
def test_maintenance_rows_carry_their_inputs_in_params(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        connection.execute(insert(legacy.check_jobs).values(id=1, repository_id=1, repository_path="/srv/repo", status="completed", progress=100, progress_message="done", max_duration=3600, extra_flags="--verify-data", scheduled_check=True, process_pid=12, process_start_time=34, created_at=NOW))
        connection.execute(insert(legacy.restore_check_jobs).values(id=1, repository_id=1, archive_name="daily-1", status="needs_backup", probe_paths=json.dumps(["/etc"]), full_archive=False, scheduled_restore_check=False, created_at=NOW))
        connection.execute(insert(legacy.compact_jobs).values(id=1, repository_id=1, status="running", scheduled_compact=True, created_at=NOW))
        connection.execute(insert(legacy.prune_jobs).values(id=1, repository_id=1, status="pending", scheduled_prune=False, created_at=NOW))
        connection.execute(insert(legacy.delete_archive_jobs).values(id=1, repository_id=1, archive_name="daily-0", status="failed", error_message="boom", created_at=NOW))
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        [check] = _operations(connection, "check")
        assert check["params"] == {"legacy_id": 1, "max_duration": 3600, "extra_flags": "--verify-data", "scheduled_check": True}
        assert check["trigger"] == "schedule" and check["process_pid"] == 12 and check["process_start_time"] == 34.0
        assert check["progress_message"] == "done"
        [rc] = _operations(connection, "restore_check")
        assert rc["status"] == "skipped" and rc["skip_reason"] == "needs_backup"
        assert rc["params"]["probe_paths"] == ["/etc"] and rc["params"]["archive_name"] == "daily-1"
        [compact] = _operations(connection, "compact")
        assert compact["status"] == "running" and compact["params"]["scheduled_compact"] is True
        [prune] = _operations(connection, "prune")
        assert prune["status"] == "queued" and prune["trigger"] == "manual"
        [delete] = _operations(connection, "delete_archive")
        assert delete["params"]["archive_name"] == "daily-0" and delete["error_message"] == "boom"


@pytest.mark.unit
def test_executed_wipes_move_and_previews_stay(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        connection.execute(
            insert(legacy.repository_wipe_jobs),
            [
                dict(id=1, repository_id=1, status="previewed", phase="preview", archive_count=2, run_compact=True, created_at=NOW),
                dict(id=2, repository_id=1, status="completed_compaction_failed", phase="compact", archive_count=2, run_compact=True, confirmed_at=NOW, started_at=NOW, completed_at=NOW, created_at=NOW),
                dict(id=3, repository_id=1, status="failed_partial", phase="delete", archive_count=2, run_compact=False, created_at=NOW),
            ],
        )
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    assert report.copied["repository_wipe_jobs"] == 2
    with engine.connect() as connection:
        remaining = connection.execute(select(legacy.repository_wipe_jobs.c.id)).scalars().all()
        assert remaining == [1]
        ops = {op["params"]["legacy_id"]: op for op in _operations(connection, "wipe")}
        assert ops[2]["status"] == "completed_with_warnings"
        assert ops[3]["status"] == "failed"
        details = _tables(connection)["operation_wipe_details"]
        rows = {r["operation_id"]: r for r in connection.execute(select(details)).mappings().all()}
        assert rows[ops[2]["id"]]["phase"] == "compact_failed"
        assert rows[ops[3]["id"]]["phase"] == "delete_failed_partial"
        assert rows[ops[3]["id"]]["run_compact"] is False


@pytest.mark.unit
def test_rclone_and_package_rows(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        tables = _tables(connection)
        connection.execute(insert(tables["installed_packages"]).values(id=1, name="rsync", status="installed", created_at=NOW))
        connection.execute(insert(legacy.rclone_sync_jobs).values(id=1, repository_id=1, direction="push", operation="hydrate", status="completed", triggered_by="initial", bytes_transferred=10, files_transferred=2, log_path="/var/log/x", log_text="synced", created_at=NOW))
        connection.execute(insert(legacy.package_install_jobs).values(id=1, package_id=1, status="installing", exit_code=None, stdout="out", stderr="err", created_at=NOW))
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        [rclone] = _operations(connection, "rclone_sync")
        assert rclone["category"] == "mirror" and rclone["trigger"] == "import" and rclone["log_file_path"] == "/var/log/x"
        details = _tables(connection)["operation_rclone_details"]
        [row] = connection.execute(select(details)).mappings().all()
        assert (row["operation"], row["direction"], row["bytes_transferred"], row["log_text"]) == ("hydrate", "push", 10, "synced")
        [package] = _operations(connection, "package_install")
        assert package["status"] == "running" and package["category"] == "system"
        assert package["repository_id"] is None and package["params"] == {"legacy_id": 1, "package_id": 1}
        body = (log_dir / f"operation_{package['id']}.log").read_text()
        assert body.startswith("# borg-ui package streams stdout=3 stderr=3\n")
        assert body.endswith("outerr")


@pytest.mark.unit
def test_rows_whose_repository_is_gone_are_skipped_for_kinds_that_need_one(engine, log_dir):
    """A check row's repository_id has no ondelete, so SQLite installs can
    hold rows pointing at deleted repositories. `operations.repository_id`
    is a real foreign key on both dialects; those rows cannot be copied."""
    with engine.begin() as connection:
        connection.execute(insert(legacy.check_jobs).values(id=1, repository_id=99, status="completed", created_at=NOW))
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    assert report.copied["check_jobs"] == 0 and report.skipped["check_jobs"] == 1


@pytest.mark.unit
def test_copy_is_idempotent_on_an_empty_legacy_set(engine, log_dir):
    with engine.begin() as connection:
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    assert sum(report.copied.values()) == 0
```

Read `_HEADER_PREFIX` from `app/services/operations/package_facade.py` before
writing the package assertion; the literal in the test above must equal it.

- [x] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/unit/test_legacy_job_collapse.py -q`
Expected: every test errors with `ModuleNotFoundError: app.database.legacy_job_collapse`.

- [x] **Step 4: Write the copy module**

`app/database/legacy_job_collapse.py`. Core only, chunked, one function per
table. The shape:

```python
"""The one-off copy of legacy job rows into `operations` (spec section 14).

Runs inside the collapse revision, on the migration's connection, before the
legacy tables are dropped. Every row becomes an `operations` row with a fresh
id and, where spec 6.2 gives the kind an extension table, a details row. The
old id is kept in `params["legacy_id"]` so a copied row can be traced back
from a log line, and the three link columns phase 8 added (`agent_jobs.
operation_id`, `script_executions.operation_id`, `backup_plan_run_repositories.
backup_operation_id`) are rewritten from the id maps. Inline log text that the
legacy tables kept on the row is written to the operation's log file, which is
where every reader looks now (spec 6.1).

Core statements rather than the ORM: the ORM no longer knows the legacy
tables, and a migration must not depend on model classes that will move on.
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import MetaData, Table, insert, select, update, delete
from sqlalchemy.engine import Connection

from app.database import legacy_job_tables as legacy
from app.services.operations.vocab import (
    LEGACY_STATUS_MAP,
    category_for,
    priority_for_trigger,
)

CHUNK = 500

# Legacy status words with no operations equivalent in LEGACY_STATUS_MAP.
_PACKAGE_STATUS = {"pending": "queued", "installing": "running"}
_WIPE_STATUS = {
    "pending": "queued",
    "completed_compaction_failed": "completed_with_warnings",
    "failed_partial": "failed",
}
_WIPE_PHASE_FOR_STATUS = {
    "completed_compaction_failed": "compact_failed",
    "failed_partial": "delete_failed_partial",
}
_RCLONE_TRIGGER = {"initial": "import", "manual": "manual", "schedule": "schedule"}
_BACKUP_MODE = {None: "server", "": "server", "local": "server"}
_LOG_MARKER = "Logs saved to: "
_PACKAGE_HEADER = "# borg-ui package streams"


@dataclass
class CollapseReport:
    copied: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    id_maps: dict[str, dict[int, int]] = field(default_factory=dict)


class _Target:
    """The surviving tables, reflected from the connection so the copy sees
    exactly the schema the revision it runs in has."""

    def __init__(self, connection: Connection):
        meta = MetaData()
        meta.reflect(bind=connection)
        self.operations = meta.tables["operations"]
        self.backup_details = meta.tables["operation_backup_details"]
        self.restore_details = meta.tables["operation_restore_details"]
        self.wipe_details = meta.tables["operation_wipe_details"]
        self.rclone_details = meta.tables["operation_rclone_details"]
        self.retry_lineage = meta.tables["operation_backup_retry_lineage"]
        self.repositories = meta.tables["repositories"]
        self.agent_jobs = meta.tables["agent_jobs"]
        self.script_executions = meta.tables["script_executions"]
        self.plan_run_repositories = meta.tables["backup_plan_run_repositories"]
        self.plan_runs = meta.tables["backup_plan_runs"]


def _status(value: Optional[str], extra: Optional[dict] = None) -> str:
    word = value or "queued"
    if extra and word in extra:
        return extra[word]
    return LEGACY_STATUS_MAP.get(word, word)


def _repository_ids(connection: Connection, target: _Target) -> tuple[set[int], dict[str, int]]:
    """Existing repository ids, and a path index for rows that only kept
    the path (backup and restore rows written before the id column)."""
    rows = connection.execute(
        select(target.repositories.c.id, target.repositories.c.path)
    ).all()
    ids = {row.id for row in rows}
    by_path = {}
    for row in rows:
        if row.path:
            by_path[row.path.rstrip("/") or row.path] = row.id
    return ids, by_path


def _resolve_repository(row, ids: set[int], by_path: dict[str, int], *, path_column: str = "repository") -> Optional[int]:
    repository_id = row._mapping.get("repository_id")
    if repository_id is not None and repository_id in ids:
        return repository_id
    path = row._mapping.get(path_column)
    if path:
        return by_path.get(path.rstrip("/") or path)
    return None


def _insert_operation(connection: Connection, target: _Target, values: dict) -> int:
    values.setdefault("run_id", str(uuid.uuid4()))
    values.setdefault("priority", priority_for_trigger(values["trigger"]))
    values.setdefault("category", category_for(values["kind"]))
    values.setdefault("status", "queued")
    result = connection.execute(insert(target.operations).values(**values))
    return int(result.inserted_primary_key[0])


def _write_log(log_dir: Path, operation_id: int, text: str) -> str:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"operation_{operation_id}.log"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _log_path_for(row, log_dir: Path, operation_id: int, *, text_column: str = "logs") -> Optional[str]:
    """The log file a copied row points at: its own file when it had one,
    the file a `Logs saved to:` marker names when that exists, else a new
    file holding the inline text. Nothing is written for a row without logs."""
    existing = row._mapping.get("log_file_path")
    if existing:
        return existing
    text = row._mapping.get(text_column)
    if not text:
        return None
    if text.startswith(_LOG_MARKER):
        candidate = log_dir / text[len(_LOG_MARKER):].strip()
        return str(candidate) if candidate.exists() else None
    return _write_log(log_dir, operation_id, text)


def _iter(connection: Connection, table: Table):
    """Rows in id order, in chunks, so a large table does not sit in memory."""
    last = 0
    while True:
        rows = connection.execute(
            select(table).where(table.c.id > last).order_by(table.c.id).limit(CHUNK)
        ).all()
        if not rows:
            return
        for row in rows:
            yield row
        last = rows[-1].id
```

Then the per-table functions. Backup, which carries the most:

```python
def _copy_backups(connection, target, log_dir, ids, by_path, report):
    id_map: dict[int, int] = {}
    pending_retry: list[tuple[int, Optional[int], Optional[int]]] = []
    copied = 0
    for row in _iter(connection, legacy.backup_jobs):
        m = row._mapping
        repository_id = _resolve_repository(row, ids, by_path)
        if m["backup_plan_run_id"]:
            trigger = "plan"
        elif m["scheduled_job_id"]:
            trigger = "schedule"
        elif m["retry_source_job_id"]:
            trigger = "retry"
        else:
            trigger = "manual"
        params: dict[str, Any] = {"legacy_id": m["id"]}
        if repository_id is None:
            params["repository"] = m["repository"]
        mode = m["execution_mode"]
        operation_id = _insert_operation(connection, target, dict(
            kind="backup",
            repository_id=repository_id,
            status=_status(m["status"]),
            trigger=trigger,
            scheduled_job_id=m["scheduled_job_id"],
            backup_plan_run_id=m["backup_plan_run_id"],
            triggered_by_user_id=m["retry_requested_by_user_id"],
            execution_mode=_BACKUP_MODE.get(mode, mode),
            progress_percent=m["progress_percent"] if m["progress_percent"] else float(m["progress"] or 0),
            progress_message=m["current_file"],
            error_message=m["error_message"],
            params=params,
            created_at=m["created_at"],
            started_at=m["started_at"],
            completed_at=m["completed_at"],
        ))
        log_path = _log_path_for(row, log_dir, operation_id)
        if log_path:
            connection.execute(update(target.operations).where(target.operations.c.id == operation_id).values(log_file_path=log_path))
        connection.execute(insert(target.backup_details).values(
            operation_id=operation_id,
            archive_name=m["archive_name"],
            archive_pruned_at=m["archive_pruned_at"],
            original_size=m["original_size"] or 0,
            compressed_size=m["compressed_size"] or 0,
            deduplicated_size=m["deduplicated_size"] or 0,
            nfiles=m["nfiles"] or 0,
            current_file=m["current_file"],
            backup_speed=m["backup_speed"] or 0.0,
            total_expected_size=m["total_expected_size"] or 0,
            estimated_time_remaining=m["estimated_time_remaining"] or 0,
            route_strategy=m["route_strategy"],
            source_ssh_connection_id=m["source_ssh_connection_id"],
            remote_process_pid=m["remote_process_pid"],
            remote_hostname=m["remote_hostname"],
            retry_attempt=m["retry_attempt"] or 1,
            retry_requested_by_user_id=m["retry_requested_by_user_id"],
            retry_requested_at=m["retry_requested_at"],
            maintenance_status=m["maintenance_status"],
        ))
        id_map[m["id"]] = operation_id
        if m["retry_original_job_id"] or m["retry_source_job_id"]:
            pending_retry.append((operation_id, m["retry_original_job_id"], m["retry_source_job_id"]))
        copied += 1
    # Retry ids point at other backup rows, possibly later ones: rewrite once
    # every row has its new id.
    for operation_id, original, source in pending_retry:
        connection.execute(update(target.backup_details).where(target.backup_details.c.operation_id == operation_id).values(
            retry_original_job_id=id_map.get(original),
            retry_source_job_id=id_map.get(source),
        ))
    report.copied["backup_jobs"] = copied
    report.skipped["backup_jobs"] = 0
    report.id_maps["backup_jobs"] = id_map
    return id_map
```

`source_ssh_connection_id` and `retry_requested_by_user_id` are foreign keys
on the details table too; clear each when its target row is missing (query
`ssh_connections.id` and `users.id` once into sets, the same way
`_repository_ids` does) so PostgreSQL does not reject the insert.

Links and lineage, after the backup map exists:

```python
def _rewrite_backup_links(connection, target, id_map, report):
    for table, old_col, new_col in (
        (target.agent_jobs, "backup_job_id", "operation_id"),
        (target.script_executions, "backup_job_id", "operation_id"),
        (target.plan_run_repositories, "backup_job_id", "backup_operation_id"),
    ):
        rows = connection.execute(
            select(table.c.id, table.c[old_col]).where(table.c[old_col].isnot(None))
        ).all()
        for row in rows:
            new_id = id_map.get(row[1])
            if new_id is None:
                continue
            connection.execute(update(table).where(table.c.id == row[0]).values({new_col: new_id}))
    copied = 0
    for row in _iter(connection, legacy.backup_job_retry_lineage):
        m = row._mapping
        connection.execute(insert(target.retry_lineage).values(
            original_job_id=id_map.get(m["original_job_id"]),
            retry_source_job_id=id_map.get(m["retry_source_job_id"]),
            attempt_number=m["attempt_number"],
            requested_by_user_id=m["requested_by_user_id"],
            requested_at=m["requested_at"],
            created_operation_id=id_map.get(m["created_job_id"]),
            request_snapshot=m["request_snapshot"],
        ))
        copied += 1
    report.copied["backup_job_retry_lineage"] = copied
```

Restore (`repository` is a path; `execution_mode` becomes `server`, the
legacy words `local_to_local` and friends are not stored, as phase 7 decided):

```python
def _copy_restores(connection, target, log_dir, ids, by_path, report):
    copied = 0
    for row in _iter(connection, legacy.restore_jobs):
        m = row._mapping
        repository_id = _resolve_repository(row, ids, by_path)
        operation_id = _insert_operation(connection, target, dict(
            kind="restore", repository_id=repository_id, status=_status(m["status"]),
            trigger="manual", execution_mode="server",
            progress_percent=m["progress_percent"] if m["progress_percent"] else float(m["progress"] or 0),
            progress_message=m["current_file"], error_message=m["error_message"],
            params={"legacy_id": m["id"], **({"repository": m["repository"]} if repository_id is None else {})},
            created_at=m["created_at"], started_at=m["started_at"], completed_at=m["completed_at"],
        ))
        log_path = _log_path_for(row, log_dir, operation_id)
        if log_path:
            connection.execute(update(target.operations).where(target.operations.c.id == operation_id).values(log_file_path=log_path))
        connection.execute(insert(target.restore_details).values(
            operation_id=operation_id, archive=m["archive"], destination=m["destination"],
            destination_type=m["destination_type"] or "local",
            destination_connection_id=m["destination_connection_id"],
            temp_extraction_path=m["temp_extraction_path"], destination_hostname=m["destination_hostname"],
            repository_type=m["repository_type"] or "local", original_size=m["original_size"] or 0,
            restored_size=m["restored_size"] or 0, restore_speed=m["restore_speed"] or 0.0,
            nfiles=m["nfiles"] or 0, current_file=m["current_file"],
        ))
        copied += 1
    report.copied["restore_jobs"] = copied
```

The five maintenance kinds share one function driven by a table:

```python
# (legacy table, kind, params columns, scheduled flag column, trigger word for
# the flag). `params` keys are the ones `job_facade.PARAM_FIELDS` names.
_MAINTENANCE = (
    (legacy.check_jobs, "check", ("max_duration", "extra_flags", "scheduled_check"), "scheduled_check"),
    (legacy.restore_check_jobs, "restore_check", ("archive_name", "probe_paths", "full_archive", "scheduled_restore_check"), "scheduled_restore_check"),
    (legacy.compact_jobs, "compact", ("scheduled_compact",), "scheduled_compact"),
    (legacy.prune_jobs, "prune", ("scheduled_prune",), "scheduled_prune"),
    (legacy.delete_archive_jobs, "delete_archive", ("archive_name",), None),
)


def _copy_maintenance(connection, target, log_dir, ids, report):
    for table, kind, param_columns, flag in _MAINTENANCE:
        copied = skipped = 0
        for row in _iter(connection, table):
            m = row._mapping
            if m["repository_id"] not in ids:
                skipped += 1
                continue
            params: dict[str, Any] = {"legacy_id": m["id"]}
            for column in param_columns:
                value = m.get(column)
                if column == "probe_paths" and isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        value = [value]
                if value is not None:
                    params[column] = bool(value) if column.startswith(("scheduled_", "full_")) else value
            status = _status(m["status"])
            operation_id = _insert_operation(connection, target, dict(
                kind=kind, repository_id=m["repository_id"], status=status,
                skip_reason="needs_backup" if m["status"] == "needs_backup" else None,
                trigger="schedule" if flag and m.get(flag) else "manual",
                execution_mode="server",
                progress_percent=float(m["progress"]) if m.get("progress") is not None else None,
                progress_message=m.get("progress_message"), error_message=m["error_message"],
                process_pid=m.get("process_pid"),
                process_start_time=float(m["process_start_time"]) if m.get("process_start_time") is not None else None,
                params=params, created_at=m["created_at"], started_at=m["started_at"], completed_at=m["completed_at"],
            ))
            log_path = _log_path_for(row, log_dir, operation_id)
            if log_path:
                connection.execute(update(target.operations).where(target.operations.c.id == operation_id).values(log_file_path=log_path))
            copied += 1
        report.copied[table.name] = copied
        report.skipped[table.name] = skipped
```

Executed wipes (delete the copied rows; previews stay):

```python
def _copy_wipes(connection, target, log_dir, ids, report):
    copied = skipped = 0
    moved: list[int] = []
    for row in _iter(connection, legacy.repository_wipe_jobs):
        m = row._mapping
        if m["status"] == "previewed":
            continue
        if m["repository_id"] is not None and m["repository_id"] not in ids:
            skipped += 1
            moved.append(m["id"])
            continue
        operation_id = _insert_operation(connection, target, dict(
            kind="wipe", repository_id=m["repository_id"], status=_status(m["status"], _WIPE_STATUS),
            trigger="manual", execution_mode="server", triggered_by_user_id=m["confirmed_by_user_id"] or m["requested_by_user_id"],
            progress_percent=float(m["progress"]) if m["progress"] is not None else None,
            progress_message=m["progress_message"], error_message=m["error_message"],
            params={"legacy_id": m["id"], "run_compact": bool(m["run_compact"])},
            created_at=m["created_at"], started_at=m["started_at"], completed_at=m["completed_at"],
        ))
        log_path = _log_path_for(row, log_dir, operation_id)
        if log_path:
            connection.execute(update(target.operations).where(target.operations.c.id == operation_id).values(log_file_path=log_path))
        connection.execute(insert(target.wipe_details).values(
            operation_id=operation_id,
            phase=_WIPE_PHASE_FOR_STATUS.get(m["status"], m["phase"]),
            archive_count=m["archive_count"] or 0, archive_fingerprint=m["archive_fingerprint"],
            archive_manifest_json=m["archive_manifest_json"], dry_run_output=m["dry_run_output"],
            blocking_reason=m["blocking_reason"], protected_archives_json=m["protected_archives_json"],
            run_compact=bool(m["run_compact"]), requested_by_user_id=m["requested_by_user_id"],
            confirmed_by_user_id=m["confirmed_by_user_id"], confirmed_at=m["confirmed_at"],
        ))
        moved.append(m["id"])
        copied += 1
    for start in range(0, len(moved), CHUNK):
        connection.execute(delete(legacy.repository_wipe_jobs).where(legacy.repository_wipe_jobs.c.id.in_(moved[start:start + CHUNK])))
    report.copied["repository_wipe_jobs"] = copied
    report.skipped["repository_wipe_jobs"] = skipped
```

Before writing this function, read `WipeJobFacade` in `wipe_facade.py` for
the exact params key the facade reads `run_compact` from (it may read the
details row only); match it, and drop the key from `params` if the facade
never reads it.

Rclone and package:

```python
def _copy_rclone(connection, target, ids, report):
    copied = skipped = 0
    for row in _iter(connection, legacy.rclone_sync_jobs):
        m = row._mapping
        if m["repository_id"] not in ids:
            skipped += 1
            continue
        operation_id = _insert_operation(connection, target, dict(
            kind="rclone_sync", repository_id=m["repository_id"], status=_status(m["status"]),
            trigger=_RCLONE_TRIGGER.get(m["triggered_by"], "manual"), execution_mode="rclone",
            error_message=m["error_text"], log_file_path=m["log_path"],
            params={"legacy_id": m["id"]}, created_at=m["created_at"], started_at=m["started_at"], completed_at=m["completed_at"],
        ))
        connection.execute(insert(target.rclone_details).values(
            operation_id=operation_id, direction=m["direction"], operation=m["operation"] or "sync",
            scheduled_for=m["scheduled_for"], bytes_transferred=m["bytes_transferred"],
            files_transferred=m["files_transferred"], log_text=m["log_text"], error_text=m["error_text"],
        ))
        copied += 1
    report.copied["rclone_sync_jobs"] = copied
    report.skipped["rclone_sync_jobs"] = skipped


def _copy_packages(connection, target, log_dir, report):
    copied = 0
    for row in _iter(connection, legacy.package_install_jobs):
        m = row._mapping
        operation_id = _insert_operation(connection, target, dict(
            kind="package_install", repository_id=None, status=_status(m["status"], _PACKAGE_STATUS),
            trigger="manual", execution_mode="server", error_message=m["error_message"],
            result={"exit_code": m["exit_code"]} if m["exit_code"] is not None else None,
            process_pid=m["process_pid"],
            process_start_time=float(m["process_start_time"]) if m["process_start_time"] is not None else None,
            params={"legacy_id": m["id"], "package_id": m["package_id"]},
            created_at=m["created_at"], started_at=m["started_at"], completed_at=m["completed_at"],
        ))
        stdout, stderr = m["stdout"] or "", m["stderr"] or ""
        if stdout or stderr:
            text = f"{_PACKAGE_HEADER} stdout={len(stdout)} stderr={len(stderr)}\n{stdout}{stderr}"
            connection.execute(update(target.operations).where(target.operations.c.id == operation_id).values(log_file_path=_write_log(log_dir, operation_id, text)))
        copied += 1
    report.copied["package_install_jobs"] = copied
```

`_PACKAGE_HEADER` must equal `package_facade._HEADER_PREFIX`; import it from
there rather than restating it if the import is clean (the facade module
imports `Operation`, which is fine inside a migration because `env.py`
already imports the models). The entry point:

```python
def collapse_legacy_job_tables(connection: Connection, *, log_dir: Path) -> CollapseReport:
    """Copy every legacy job row into `operations`, in dependency order:
    backups first (the link columns and the retry lineage point at them),
    everything else after. Runs in the caller's transaction."""
    report = CollapseReport()
    target = _Target(connection)
    ids, by_path = _repository_ids(connection, target)
    backup_map = _copy_backups(connection, target, log_dir, ids, by_path, report)
    _rewrite_backup_links(connection, target, backup_map, report)
    _copy_restores(connection, target, log_dir, ids, by_path, report)
    _copy_maintenance(connection, target, log_dir, ids, report)
    _copy_wipes(connection, target, log_dir, ids, report)
    _copy_rclone(connection, target, ids, report)
    _copy_packages(connection, target, log_dir, report)
    return report
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_legacy_job_collapse.py -q`
Expected: all pass. Fix column names against the reflected tables where a
test fails on an unknown column (the seed rows in the tests name only the
NOT NULL columns of each surviving table; check `models.py` for each and add
what the insert refuses).

---

## Task 2: The collapse revision and the model deletions

**Files:**
- Create: `app/database/alembic/versions/d0e1f2a3b4c5_collapse_legacy_job_tables.py`
- Modify: `app/database/models.py`
- Test: `tests/unit/test_collapse_legacy_job_tables_migration.py`

**Interfaces:**
- Consumes: `collapse_legacy_job_tables`, `legacy_job_tables.metadata`, `LEGACY_JOB_TABLE_NAMES`, `app.config.settings.data_dir`.
- Produces: revision `d0e1f2a3b4c5` (down `b8c9d0e1f2a3`), the new single head; `models.py` without the ten classes and the three `backup_job_id` columns.

- [x] **Step 1: Write the failing migration tests**

```python
"""Tests for revision d0e1f2a3b4c5 (collapse of the legacy job tables)."""

from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, inspect, insert, select

from app.database import legacy_job_tables as legacy
from app.database.db_upgrade import _alembic_config, _engine

REVISION = "d0e1f2a3b4c5"
PREVIOUS = "b8c9d0e1f2a3"
NOW = datetime(2026, 9, 1, 12, 0, 0)


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _tables(url):
    engine = _engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _columns(url, table):
    engine = _engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_copies_then_drops_and_downgrade_recreates_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    with engine.begin() as connection:
        meta = MetaData()
        meta.reflect(bind=connection)
        connection.execute(insert(meta.tables["repositories"]).values(
            id=1, name="r", path="/srv/r", encryption="none", compression="lz4", mode="full", created_at=NOW,
        ))
        connection.execute(insert(legacy.backup_jobs).values(id=1, repository="/srv/r", repository_id=1, status="completed", created_at=NOW))
        connection.execute(insert(legacy.check_jobs).values(id=1, repository_id=1, status="completed", created_at=NOW))
        connection.execute(insert(legacy.repository_wipe_jobs).values(id=1, repository_id=1, status="previewed", run_compact=True, created_at=NOW))
    engine.dispose()

    _migrate(url, REVISION)
    assert not (set(legacy.LEGACY_JOB_TABLE_NAMES) & _tables(url))
    assert "repository_wipe_jobs" in _tables(url)
    assert "backup_job_id" not in _columns(url, "agent_jobs")
    assert "backup_job_id" not in _columns(url, "script_executions")
    assert "backup_job_id" not in _columns(url, "backup_plan_run_repositories")
    engine = _engine(url)
    with engine.connect() as connection:
        meta = MetaData()
        meta.reflect(bind=connection)
        kinds = connection.execute(select(meta.tables["operations"].c.kind)).scalars().all()
        assert sorted(kinds) == ["backup", "check"]
        previews = connection.execute(select(legacy.repository_wipe_jobs.c.status)).scalars().all()
        assert previews == ["previewed"]
    engine.dispose()

    _migrate(url, PREVIOUS, down=True)
    assert set(legacy.LEGACY_JOB_TABLE_NAMES) <= _tables(url)
    assert "backup_job_id" in _columns(url, "agent_jobs")
    engine = _engine(url)
    with engine.connect() as connection:
        assert connection.execute(select(legacy.backup_jobs.c.id)).all() == []
    engine.dispose()


@pytest.mark.unit
def test_revision_chains_on_the_previous_head_and_leaves_one_head():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config("sqlite://"))
    assert script.get_revision(REVISION).down_revision == PREVIOUS
    assert len(script.get_heads()) == 1
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_collapse_legacy_job_tables_migration.py -q`
Expected: FAIL, `Can't locate revision identified by 'd0e1f2a3b4c5'`.

- [x] **Step 3: Write the revision**

```python
"""collapse the legacy job tables into operations

Revision ID: d0e1f2a3b4c5
Revises: b8c9d0e1f2a3
Create Date: 2026-09-10

Spec section 13 phase 9 and section 14: the legacy job rows are copied into
`operations` once (the "explicit one-off copy"), then the nine legacy tables
and the three legacy link columns are dropped. `repository_wipe_jobs` stays
as the wipe preview store; only its executed rows move.

The downgrade recreates the tables empty and restores the link columns. The
copied rows stay in `operations`; a downgrade is a schema rollback, not a
data restore.
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa

from app.config import settings
from app.database import legacy_job_tables as legacy
from app.database.legacy_job_collapse import collapse_legacy_job_tables

revision = "d0e1f2a3b4c5"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    report = collapse_legacy_job_tables(
        connection, log_dir=Path(settings.data_dir) / "logs"
    )
    for table, count in sorted(report.copied.items()):
        print(f"collapsed {table}: {count} rows copied, {report.skipped.get(table, 0)} skipped")

    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.drop_index("ix_agent_jobs_backup_job_id")
        batch_op.drop_column("backup_job_id")
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.drop_index("ix_script_executions_backup_job_id")
        batch_op.drop_column("backup_job_id")
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.drop_column("backup_job_id")
    for name in legacy.LEGACY_JOB_TABLE_NAMES:
        op.drop_table(name)


def downgrade() -> None:
    connection = op.get_bind()
    # Parents before children: reversed drop order.
    for name in reversed(legacy.LEGACY_JOB_TABLE_NAMES):
        legacy.metadata.tables[name].create(connection)
    with op.batch_alter_table("backup_plan_run_repositories") as batch_op:
        batch_op.add_column(sa.Column("backup_job_id", sa.Integer(), sa.ForeignKey("backup_jobs.id", ondelete="SET NULL"), nullable=True))
    with op.batch_alter_table("script_executions") as batch_op:
        batch_op.add_column(sa.Column("backup_job_id", sa.Integer(), sa.ForeignKey("backup_jobs.id", ondelete="CASCADE"), nullable=True))
        batch_op.create_index("ix_script_executions_backup_job_id", ["backup_job_id"])
    with op.batch_alter_table("agent_jobs") as batch_op:
        batch_op.add_column(sa.Column("backup_job_id", sa.Integer(), sa.ForeignKey("backup_jobs.id", ondelete="SET NULL"), nullable=True))
        batch_op.create_index("ix_agent_jobs_backup_job_id", ["backup_job_id"])
```

Verify the two index names before running: open a scratch database at
`b8c9d0e1f2a3` and run `PRAGMA index_list('agent_jobs')` and
`PRAGMA index_list('script_executions')`. SQLAlchemy names an `index=True`
column index `ix_<table>_<column>`; if the baseline revision named them
differently, use the names it did. On PostgreSQL `drop_column` removes the
column's foreign key with it; on SQLite the batch recreate does the same.

- [x] **Step 4: Delete the models**

In `app/database/models.py` delete the ten classes named in File Structure,
`AgentJob.backup_job_id` (lines 175-180 and the comment after them),
`BackupPlanRunRepository.backup_job_id` and `backup_job = relationship("BackupJob")`
(1250-1252 and 1263), `ScriptExecution.backup_job_id` and its
`backup_job = relationship("BackupJob")` (2345-2350 and 2407). Keep
`RepositoryWipeJob` and add to its docstring: "The wipe preview store since
section 13 phase 6. Executed wipes are `operations` rows; phase 9 moved the
rows written before phase 6 there and this table holds `previewed` rows
only." Delete the `__repr__` of `PackageInstallJob` with the class.

- [x] **Step 5: Run the migration tests and the model import**

Run: `pytest tests/unit/test_collapse_legacy_job_tables_migration.py tests/unit/test_legacy_job_collapse.py -q && python -c "import app.database.models"`
Expected: the tests pass; the import succeeds. `alembic heads` prints
`d0e1f2a3b4c5 (head)`. The rest of the suite does not import yet; that is
Tasks 4 to 8.

---

## Task 3: The pre-Alembic upgrade path lands rows before the collapse

**Files:**
- Modify: `app/database/db_upgrade.py`
- Test: `tests/unit/test_db_upgrade.py`

**Interfaces:**
- Consumes: revision ids from Task 2.
- Produces: `PRE_COLLAPSE_REVISION = "b8c9d0e1f2a3"`; `_upgrade_to(url, revision, engine=None)`; `_transfer(source, target)` reading a reflected target.

- [x] **Step 1: Write the failing tests**

Replace `test_a_self_reference_pointing_forward_survives` (it builds its
legacy database with `BackupJob`, which no longer exists) with the same case
on `BackupPlanRun.retry_source_run_id`:

```python
def populate(s):
    s.add(BackupPlanRun(id=1, trigger="manual", status="failed", retry_source_run_id=2))
    s.add(BackupPlanRun(id=2, trigger="manual", status="completed"))
...
assert session.get(BackupPlanRun, 1).retry_source_run_id == 2
assert session.get(BackupPlanRun, 2).retry_source_run_id is None
```

Add the test that pins this task:

```python
@pytest.mark.unit
def test_legacy_job_rows_reach_operations_through_the_transfer(tmp_path, monkeypatch):
    """A v2.2.x database has backup_jobs and friends; the transfer must land
    them at the pre-collapse revision so the collapse copies them."""
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    from app.database import legacy_job_tables as legacy
    from app.database.models import Operation

    db = tmp_path / "borg.db"

    def populate(s):
        s.add(Repository(id=1, name="r", path="/srv/r"))

    _legacy_db(db, populate)
    engine = create_engine(f"sqlite:///{db}")
    legacy.backup_jobs.create(engine)
    legacy.check_jobs.create(engine)
    with engine.begin() as conn:
        conn.execute(legacy.backup_jobs.insert().values(id=1, repository="/srv/r", repository_id=1, status="completed", created_at=datetime(2026, 1, 1)))
        conn.execute(legacy.check_jobs.insert().values(id=1, repository_id=1, status="failed", created_at=datetime(2026, 1, 1)))
    engine.dispose()

    report = alembic_init(db)

    assert report.action == "transferred"
    session = _open(db)
    kinds = sorted(op.kind for op in session.query(Operation).all())
    assert kinds == ["backup", "check"]
    session.close()
    with create_engine(f"sqlite:///{db}").connect() as conn:
        assert "backup_jobs" not in inspect(conn).get_table_names()
```

`_legacy_db` builds the current model's tables; the legacy job tables are
added from the frozen definitions, which is what the ladder would have left
on a real install.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_db_upgrade.py -q -k "legacy_job_rows or self_reference"`
Expected: the new test fails: `kinds == []` (rows never transferred), and
the self-reference test passes once rewritten.

- [x] **Step 3: Change `db_upgrade.py`**

Add, next to `_upgrade_to_head`:

```python
# The last revision whose schema still holds the legacy job tables. A
# pre-Alembic database is transferred onto this revision, not onto head, so
# the collapse revision (d0e1f2a3b4c5) folds its job history into
# `operations` instead of the transfer silently skipping tables head no
# longer has.
PRE_COLLAPSE_REVISION = "b8c9d0e1f2a3"


def _upgrade_to(url: str, revision: str, engine: Engine | None = None) -> None:
    """Apply revisions up to `revision` (`"head"` for all of them)."""
    log.info("applying database migrations up to %s", revision)
    config = _alembic_config(url)
    if engine is None:
        command.upgrade(config, revision)
        return
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
        connection.commit()


def _upgrade_to_head(url: str, engine: Engine | None = None) -> None:
    """Build the baseline schema. See `_upgrade_to`."""
    _upgrade_to(url, "head", engine)
```

In `_transfer`, replace the `Base.metadata.sorted_tables` loop source with
the target's reflected schema, so the tables copied are the ones the target
actually has at the revision it stands on:

```python
    log.info("transferring rows")
    reflected = MetaData()
    reflected.reflect(bind=source)
    target_meta = MetaData()
    target_meta.reflect(bind=target)

    with source.connect() as src, target.begin() as dst:
        deferred: list[tuple] = []

        # sorted_tables is topological: parents before children, which is what
        # Postgres requires -- it checks every foreign key at insert time.
        for table in target_meta.sorted_tables:
            if table.name == "alembic_version":
                continue
            source_table = reflected.tables.get(table.name)
```

`_self_referencing_columns(table)` and `_orphan_columns` read
`table.foreign_keys`, which reflection provides. Check the `Base` import is
still used elsewhere in the module; remove it if not.

In `alembic_init`, the transfer block becomes:

```python
    try:
        _upgrade_to(target_url, PRE_COLLAPSE_REVISION, target_engine)

        report = _transfer(source_engine, target_engine)
        report.target_url = _safe_url(target_url)

        # The transferred legacy job rows are folded into `operations` here.
        _upgrade_to_head(target_url, target_engine)

        if to_postgres:
            report.sequences_reset = _reset_sequences(target_engine)
```

`_reset_sequences` runs after the collapse so the `operations` sequence
covers the copied rows. Read `_reset_sequences` (line 635) to confirm it
walks every table with an integer primary key rather than a fixed list; if it
is a fixed list, `operations` and the details tables must be on it.

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_db_upgrade.py tests/unit/test_db_upgrade_ensure_schema.py -q`
Expected: PASS (the Postgres cases skip without `BORG_TEST_POSTGRES_URL`).

---

## Task 4: Facades, lanes, admission, and status read one table

**Files:**
- Modify: `app/services/operations/job_facade.py`, `backup_facade.py`, `restore_facade.py`, `wipe_facade.py`, `rclone_facade.py`, `package_facade.py`, `maintenance_start.py`, `lanes.py`, `repository_status.py`
- Delete: `app/services/operations/legacy_status.py`
- Modify: `app/services/job_admission.py`
- Test: `tests/unit/test_operations_job_facade.py`, `test_operations_backup_facade.py`, `test_operations_backup_union_readers.py`, `test_operations_restore_facade.py`, `test_operations_wipe_facade.py`, `test_operations_rclone_facade.py`, `test_operations_package_facade.py`, `test_maintenance_start.py`, `test_operations_lanes.py`, `test_repository_last_runs.py`

**Interfaces:**
- Produces: `resolve_maintenance_job(db, job_id, kind) -> Optional[MaintenanceJobFacade]`, `resolve_backup_job(db, job_id) -> Optional[BackupJobFacade]`, `resolve_restore_job`, `resolve_wipe_job`, `resolve_rclone_job`, `resolve_package_job` likewise (operations only, `None` when absent). `backup_job_link_columns(db, job_id) -> {"operation_id": job_id}`. `lanes.lane_free` without the legacy call. `job_facade.legacy_status` and `operation_status` kept.

- [x] **Step 1: Rewrite the tests**

In each facade test module delete the tests whose name says "falls back to
legacy", "still serves a pre-phase", or "unions both tables", and rewrite
the ones that seed a legacy row so the row is an operation instead
(`test_resolve_prefers_the_operation_and_falls_back_to_legacy` becomes
`test_resolve_returns_none_for_an_unknown_id`;
`test_list_backup_jobs_unions_both_tables_newest_first` becomes
`test_list_backup_jobs_newest_first` over two operations;
`test_mqtt_reads_both_tables`, `test_archive_metadata_enriches_from_both_tables`,
`test_latest_by_repository_loads_only_the_newest_row_per_table`, and
`test_reaped_notifications_resolve_the_table_they_came_from` lose their legacy
half). In `test_operations_lanes.py` delete `test_legacy_running_backup_blocks_lane`
and `test_legacy_completed_check_does_not_block`; add:

```python
def test_a_running_backup_operation_blocks_the_lane(db, repo, settings):
    running = enqueue(db, "backup", repository_id=repo.id)
    running.status = "running"
    db.commit()
    check = enqueue(db, "check", repository_id=repo.id)
    assert can_start(db, check, settings) is False
```

In `test_repository_last_runs.py` rewrite the `PruneJob` and
`RepositoryWipeJob` seeds as `prune` and `wipe` operations (with
`operation_wipe_details` through `details.wipe_details`) and delete the test
whose docstring says "like every other legacy table until phase 9".

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_job_facade.py tests/unit/test_operations_backup_facade.py tests/unit/test_operations_backup_union_readers.py tests/unit/test_operations_restore_facade.py tests/unit/test_operations_wipe_facade.py tests/unit/test_operations_rclone_facade.py tests/unit/test_operations_package_facade.py tests/unit/test_maintenance_start.py tests/unit/test_operations_lanes.py tests/unit/test_repository_last_runs.py -q`
Expected: import errors (`cannot import name 'BackupJob'`) until Step 3.

- [x] **Step 3: Strip the legacy branches**

`job_facade.py`: delete `LEGACY_MODELS` and the six legacy imports;
`resolve_maintenance_job` returns the facade or `None`; `claim_running`
keeps only its operations branch; `refresh_job` keeps its `isinstance`
shape (a caller may still hold a bare `Operation`). Module docstring: the
facade is the attribute surface the maintenance services drive; "Deleted in
phase 9" becomes "Kept after phase 9 as that surface; retiring it is a
service-by-service refactor, not a migration step."

`backup_facade.py`: `resolve_backup_job` returns the facade or `None`;
`admission_ignore_for` always names `Operation.__tablename__`;
`backup_job_link_columns` returns `{"operation_id": job_id}` (or
`{"operation_id": None}`); the seven readers (`list_backup_jobs`,
`backup_jobs_started_since`, `recent_backup_jobs`,
`latest_backup_job_for_repository`, `backup_jobs_for_archive_names`,
`latest_backup_jobs_by_repository`, `newest_backup_job`,
`backup_jobs_in_maintenance`) drop their `legacy` query and the merge, keep
their ordering and limits, and return facades. `_newest_per_group` stays for
`latest_backup_jobs_by_repository`. `is_backup_operation` stays (callers use
it); document that it is now always true for a resolved job.

`restore_facade.py`: `resolve_restore_job` operations only;
`list_restore_jobs` one query. `wipe_facade.py`: `resolve_wipe_job`
operations only (the two wipe routes resolve previews through the service,
see Task 7); `active_wipe_operation` operations only;
`_LEGACY_ACTIVE_STATUSES` gone. `rclone_facade.py`: `resolve_rclone_job`
returns the facade when the sub-type matches, else `None`.
`package_facade.py`: `resolve_package_job` and `active_package_install`
operations only. `maintenance_start.py`: `active_maintenance_operation`
and `active_delete_for_archive` operations only; `_LEGACY_ACTIVE_STATUSES`
gone.

`lanes.py`: delete `legacy_running_exclusive`, `LEGACY_RUNNING_STATUSES`,
`_WRITE_MAINTENANCE_MODELS`, `_LEGACY_MAINTENANCE_BACKUP_STATUSES`, and the
six model imports; `lane_free` is `not running_exclusive_operation(...)`;
`write_maintenance_running` keeps the operations query and the
`OperationBackupDetails.maintenance_status` query phase 8 added, and loses
the `BackupJob` and the four legacy model queries.

`repository_status.py`: delete the `legacy_status` import and the two calls
(`latest_legacy_terminal` in `job_evidence`, `latest_legacy_success_by_repository`
in `last_runs`), the `"legacy"` source word, and the `DeleteArchiveJob` and
`RepositoryWipeJob` entries in the deletion evidence sources (executed wipes
are operations now; the `previewed` rows never had `started_at`). Update the
comment at 219-220. Delete `legacy_status.py`.

`job_admission.py`: `list_active_repository_work` builds backup entries from
`Operation` rows of kind `backup` (add `"backup"` to the operations loop it
already runs, which `MIGRATED_OPERATION_KINDS` already includes; delete the
`BackupJob` block and `_repository_backup_filter`), deletes the
`RepositoryWipeJob` block, and `count_active_manual_backup_jobs` keeps the
operations count only. Delete `MAINTENANCE_MODEL_OPERATIONS`,
`operation_for_maintenance_model`, `ACTIVE_REPOSITORY_WIPE_STATUSES`,
`ACTIVE_BACKUP_STATUSES` if nothing else reads them (grep), and the model
imports.

- [x] **Step 4: Run the tests to verify they pass**

Run the Step 2 command again. Expected: PASS.

---

## Task 5: Activity reads only operations

**Files:**
- Modify: `app/api/activity.py`
- Test: `tests/unit/test_api_activity.py`, `tests/unit/test_activity_union.py`

**Interfaces:**
- Consumes: `_operation_activity_items` (unchanged signature), `resolve_*` from Task 4.
- Produces: `list_recent_activity` with four sources: operations, plan-run availability skips, availability schedule skips, script executions. `_get_operation_or_404` returns an `Operation` only. `_read_operation_log(op)` reads the file only. `_get_agent_job_for_backup(db, operation_id)` filters `AgentJob.operation_id`.

- [x] **Step 1: Rewrite the tests**

`tests/unit/test_api_activity.py`: every `BackupJob(...)`, `RestoreJob(...)`,
`CheckJob(...)`, `RestoreCheckJob(...)`, `CompactJob(...)`, `PruneJob(...)`,
`PackageInstallJob(...)`, `RcloneSyncJob(...)` seed becomes an operation
built with one helper added at the top of the module:

```python
from app.services.operations.details import (
    backup_details, rclone_details, restore_details,
)
from app.services.operations.enqueue import enqueue


def _op(db, kind, *, repository=None, status="completed", trigger="manual",
        params=None, error_message=None, log_file_path=None, started_at=None,
        completed_at=None, details=None):
    op = enqueue(db, kind, repository_id=repository.id if repository else None,
                 trigger=trigger, params=params, commit=False)
    op.status = status
    op.error_message = error_message
    op.log_file_path = log_file_path
    op.started_at = started_at
    op.completed_at = completed_at
    if kind == "backup":
        row = backup_details(db, op)
    elif kind == "restore":
        row = restore_details(db, op)
    elif kind == "rclone_sync":
        row = rclone_details(db, op)
    else:
        row = None
    for name, value in (details or {}).items():
        setattr(row, name, value)
    db.commit()
    db.refresh(op)
    return op
```

The legacy `logs` text column has no operation equivalent: tests that
asserted "database log fallback" (`test_get_job_logs_uses_database_log_fallback`,
`test_download_job_logs_uses_database_logs_when_no_file`,
`test_download_job_logs_uses_legacy_row_logs_when_no_file`,
`test_restore_legacy_row_still_serves_logs_after_phase_7`) are deleted; the
file-backed tests stay and seed `log_file_path`. Package tests seed the log
file through `PackageInstallFacade(db, op).write_output(stdout, stderr)`.
Rclone tests set `log_text` and `error_text` on the details row. Types in the
requests stay the legacy activity words (`backup`, `restore`, `check`,
`restore_check`, `compact`, `prune`, `package`, `rclone_sync`,
`rclone_hydrate`, `script_execution`); the response shapes stay.

`tests/unit/test_activity_union.py`: `test_legacy_and_operations_merge_ordered_by_time`
becomes `test_two_operations_ordered_by_time` (a completed `prune` operation
two hours old and an `import_connect` one hour old); the rest is unchanged.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_api_activity.py tests/unit/test_activity_union.py -q`
Expected: import errors, then failures in the per-table blocks.

- [x] **Step 3: Collapse `list_recent_activity`**

Delete the `backup`, `restore`, `check`, `restore_check`, `compact`, `prune`,
`package`, and `rclone` blocks (lines 675-1230 today, every block that
queries a legacy model). Keep the availability skip blocks and the script
execution block. The tail stays as it is: set `category`, `trigger`,
`followups` defaults on the non-operation items, apply the `category` and
`trigger` filters to them, extend with `_operation_activity_items(...)`,
sort, cut to `limit`.

`_is_operation_only_kind(job_type, job_models)` keeps its name and its
signature (the three routes pass `job_models`) and now reads:

```python
def _is_operation_only_kind(job_type: str, job_models: dict) -> bool:
    """True for every kind that is an `operations` row, which since phase 9
    is every kind except script executions."""
    return job_type not in job_models and (
        operation_kind_for_activity_type(job_type) in op_vocab.KINDS
        or job_type in RCLONE_ACTIVITY_OPERATIONS
    )
```

Delete `_MIGRATED_LEGACY_MODELS` and the fallback in `_get_operation_or_404`
(the function 404s when the operation is absent). `_read_operation_log`
loses the `getattr(op, "logs", "")` branch. `_operation_log_sources` loses
the `isinstance(op, Operation)` conditionals (always an operation).
`_get_agent_job_for_backup` filters `AgentJob.operation_id`. Delete the
model imports and `_LEGACY_CATEGORY_BY_TYPE` if `_legacy_category` no longer
needs it (script executions and availability skips still need a category:
keep `_legacy_category` for those two words and rename it
`_category_for_non_operation_type`). The three by-id routes keep their
`job_models = {"script_execution": ScriptExecution}` dicts.

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_activity.py tests/unit/test_activity_union.py -q`
Expected: PASS.

---

## Task 6: Startup sweeps, reapers, retention, and schedulers

**Files:**
- Modify: `app/utils/process_utils.py`, `app/services/agent_job_reaper.py`, `app/services/check_scheduler.py`, `app/services/log_manager.py`, `app/services/job_history_retention.py`, `app/core/borg_router.py`, `app/services/rclone_mirror_scheduler.py`
- Test: `tests/unit/test_utils.py`, `tests/unit/test_schedulers.py`, `tests/unit/test_log_manager.py`, `tests/unit/test_job_history_retention.py`, `tests/unit/test_borg_router.py`, `tests/unit/test_agent_job_abandon.py`

**Interfaces:**
- Produces: `cleanup_orphaned_jobs(db)` (stale maintenance sweep and plan run normalisation only); `reconcile_stale_backup_maintenance(db, ...)` unchanged; `reconcile_orphaned_maintenance_jobs` deleted; `_fail_orphaned_maintenance_job(db, kind, operation_id)` on `Operation`; `check_scheduler.count_active_scheduled_check_jobs(db, now)` returns `count_active_scheduled_operations(db)`; `_JOB_TABLES` without the legacy models.

- [x] **Step 1: Rewrite the tests**

`tests/unit/test_utils.py`: delete `test_cleanup_orphaned_jobs` (the
five-table sweep), the four `running_check` parent/child tests that seed
`CheckJob`, `test_cleanup_orphaned_jobs_marks_pending_backup_job_failed`, and
every `reconcile_orphaned_*` test. Rewrite the `reconcile_stale_backup_maintenance`
tests and `test_cleanup_orphaned_jobs_finishes_interrupted_backup_plan_run`
over backup operations (`create_backup_operation` from `backup_facade` with
`maintenance_status` set on the facade). Keep
`test_reap_once_runs_all_three_reaper_passes` but assert two passes.
`tests/unit/test_schedulers.py`: delete the stale scheduled check tests that
seed `CheckJob`; add one that a queued scheduled check operation counts and a
completed one does not. `tests/unit/test_log_manager.py`: the running-log
protection test seeds a running operation with a `log_file_path`.
`tests/unit/test_job_history_retention.py`: every legacy seed becomes an
operation; the lineage purge test targets `OperationBackupRetryLineage`
only; `mark_jobs_of_pruned_archives` tests use backup operations with
`archive_name` on the details row. `tests/unit/test_borg_router.py`: the
orphaned-maintenance test seeds a queued `check` operation and asserts it
ends `failed`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_utils.py tests/unit/test_schedulers.py tests/unit/test_log_manager.py tests/unit/test_job_history_retention.py tests/unit/test_borg_router.py tests/unit/test_agent_job_abandon.py -q`
Expected: import errors.

- [x] **Step 3: Delete the legacy sweeps**

`process_utils.py`: `cleanup_orphaned_jobs` becomes

```python
def cleanup_orphaned_jobs(db: Session):
    """Normalise what a restart leaves behind that the operations runner's
    own recovery (spec 7.6) does not cover: backup rows still in a running
    maintenance state, and backup plan runs left active."""
    logger.info("Checking for orphaned jobs...")
    now = datetime.utcnow()
    stale_backup_jobs = _mark_stale_backup_maintenance_failed(db, now)
    active_backup_plan_runs = (
        db.query(BackupPlanRun)
        .filter(BackupPlanRun.status.in_(ACTIVE_PLAN_RUN_STATUSES))
        .all()
    )
    logger.info(
        "Found interrupted work",
        stale_backup_maintenance_jobs=stale_backup_jobs,
        active_backup_plan_runs=len(active_backup_plan_runs),
    )
    if not stale_backup_jobs and not active_backup_plan_runs:
        logger.info("No orphaned jobs found")
        return
    normalized_plan_runs = _normalize_interrupted_backup_plan_runs(
        db, now, active_backup_plan_runs
    )
    if normalized_plan_runs:
        logger.info("Cleaned up interrupted backup plan runs", count=normalized_plan_runs)
    db.commit()
    logger.info("Orphaned job cleanup completed")
```

`_has_running_check_child` keeps its operations query only.
`_has_running_maintenance_child` keeps the operations query only; delete
`_MAINTENANCE_CHILD_MODELS`. Delete `_mark_backup_job_failed_after_restart`,
`ACTIVE_JOB_STATUSES`, `CONTAINER_RESTARTED_DURING_BACKUP` if unused after
this (grep), `_ORPHAN_MAINTENANCE_MODELS`, `_has_active_agent_job_for`,
`reconcile_orphaned_maintenance_jobs`, and the seven model imports. Check
`_normalize_interrupted_backup_plan_runs` and
`_fail_backup_plan_child_after_restart` (lines 66-140) for
`BackupPlanRunRepository.backup_job` reads; they read
`backup_operation_id` since phase 8 (verify, and fix any remaining
`.backup_job` access to `resolve_backup_job(db, link.backup_operation_id)`).

`agent_job_reaper.py`: delete the `if job.backup_job_id:` block;
`failed_backup_job_ids` becomes a list of operation ids;
`_notify_reaped_backup_jobs(operation_ids)` resolves each with
`resolve_backup_job`; `reap_once` drops the
`reconcile_orphaned_maintenance_jobs` call.

`check_scheduler.py`: delete `_mark_stale_scheduled_check_failed`,
`cleanup_stale_scheduled_check_jobs`, and the legacy half of
`count_active_scheduled_check_jobs`; grep for callers of the deleted
function (the dispatcher in `schedule.py` or `check_scheduler.py` itself)
and remove the call. Keep `STALE_PENDING_SCHEDULED_CHECK_AFTER` only if
still read.

`log_manager.py`: delete the `job_models` list and its loop.

`job_history_retention.py`: `_JOB_TABLES` becomes `(AgentJob, ()),
(RepositoryWipeJob, ("logs",)), (ScriptExecution, ("stdout", "stderr")),
(BackupPlanRun, ()), (AvailabilityScheduleSkip, ()), (Operation, ())`
(previews are the only rows left in `repository_wipe_jobs`, and they still
expire). Delete the `BackupJobRetryLineage` purge; keep the
`OperationBackupRetryLineage` one. `mark_jobs_of_pruned_archives` keeps the
details-row update phase 8 added and loses the `BackupJob` update. Delete
the model imports (note the duplicated `Operation` import at the top; tidy
it).

`borg_router.py`: `_fail_orphaned_maintenance_job` loads
`db.get(Operation, maintenance_job_id)` (kind checked against
`maintenance_kind`) and marks it `failed` with the same message; delete
`update_stats` (Task 8 handles its callers). `rclone_mirror_scheduler.py`:
delete the `RcloneSyncJob` branch.

- [x] **Step 4: Run the tests to verify they pass**

Run the Step 2 command again. Expected: PASS.

---

## Task 7: Routes and readers

**Files:**
- Modify: `app/api/backup.py`, `app/api/maintenance_jobs.py`, `app/api/packages.py`, `app/services/package_service.py`, `app/api/repositories.py`, `app/services/repository_wipe_service.py`, `app/api/schedule.py`, `app/api/agents.py`, `app/api/ssh_keys.py`, `app/api/dashboard.py`, `app/api/metrics.py`, and the hint-only files listed in File Structure
- Delete: `app/tests/test_repository_deletion.py`
- Test: every remaining test module in File Structure's last row

**Interfaces:**
- Consumes: Task 4's resolvers.
- Produces: no new names. `metrics.py` emits the same families from operations.

- [x] **Step 1: Rewrite the tests**

Apply the same rule as Task 5 to each module: legacy seeds become
operations (reuse Task 5's `_op` helper by moving it to
`tests/utils/operations.py` as `seed_operation(db, kind, **kwargs)` and
importing it everywhere), "still serves a pre-phase-N row" and "both
worlds" tests are deleted. Named cases:

- `test_api_backup.py`: `test_..._legacy` at 206, the union tests at 477 and
  646; the retry route test that reads `BackupJobRetryLineage` reads
  `OperationBackupRetryLineage`.
- `test_api_maintenance_migration.py`: delete
  `test_status_route_still_serves_a_pre_phase_5_row` and
  `test_list_route_shows_both_worlds`; the rest already asserts operations.
- `test_api_repositories.py` 1534, 2868, 3540 and
  `test_api_repositories_routes.py` 118-140: `check`, `restore_check`,
  `compact`, `prune` operations; the delete-repository tests add one
  assertion that an operation on the repository is gone after the delete
  (cascade).
- `test_api_repository_wipe.py`, `test_repository_wipe_service.py`: seeds of
  executed `RepositoryWipeJob` rows become `wipe` operations; preview seeds
  stay.
- `test_api_rclone.py`, `test_rclone_repository_service.py`: `rclone_sync`
  operations with details.
- `test_api_schedule.py` 2 refs, `test_api_schedule_routes.py`,
  `tests/integration/test_scheduled_jobs_bugfixes.py`: backup operations.
- `test_api_agents.py`: `AgentJob(operation_id=...)`; the
  `_get_linked_backup_job` cases through operations.
- `test_api_ssh_keys.py`: deletion nulls `OperationBackupDetails.source_ssh_connection_id`
  and `OperationRestoreDetails.destination_connection_id` (phase 7 and 8
  tests already exist; delete the legacy halves).
- `test_api_dashboard.py` 400-460: `restore_check` operations with
  `params["archive_name"]`.
- `test_api_metrics.py`: operations; the orphaned family asserts the two
  header lines and no samples.
- `test_mqtt_service.py`, `test_backup_service.py`,
  `test_backup_service_mocks.py`, `test_remote_backup_service.py`,
  `test_backup_monitoring_service.py`, `test_notification_service.py`,
  `test_api_backup_plans.py`, `test_api_v2_backups.py`: backup operations.
  `test_backup_service_mocks.py` builds `BackupJob(id=..., status=...)` as a
  bare object for mocking; replace with `SimpleNamespace` carrying the same
  attributes where the service only reads them, else a facade over an
  enqueued operation.
- `test_api_restore.py` 509, 712, 756, `test_restore_service.py` 100,
  `test_restore_agent_delegation.py`: restore operations.
- `test_restore_check_service.py`, `test_prune_service.py`,
  `test_delete_archive_service.py`, `test_v2_services.py`,
  `test_v2_prune_service.py`, `test_ssh_key_in_maintenance_services.py`,
  `test_api_maintenance_jobs.py`, `tests/integration/test_api_maintenance_jobs_integration.py`:
  maintenance operations via `enqueue` or `start_maintenance`.
- `test_api_packages.py`, `test_package_service.py`,
  `test_startup_packages.py`: `package_install` operations.
- `test_api_archives.py`, `test_api_archive_index.py`,
  `test_api_v2_archives.py`, `test_api_v2_repositories.py`: the archive
  enrichment seeds backup operations with `archive_name` on the details
  row.
- `tests/integration/test_api_schedule_integration.py`,
  `test_backup_workflows_integration.py`: read through
  `resolve_backup_job`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit -q -x` (stop at the first import error).
Expected: `ImportError` from one of the route modules.

- [x] **Step 3: Strip the routes and readers**

`backup.py`: `_get_running_maintenance_job(db, backup_job, maintenance_status)`
returns the running child operation:

```python
_MAINTENANCE_STATUS_KIND = {
    "running_prune": "prune",
    "running_compact": "compact",
    "running_check": "check",
}


def _get_running_maintenance_job(db, backup_job, maintenance_status):
    kind = _MAINTENANCE_STATUS_KIND.get(maintenance_status or "")
    if kind is None or backup_job.repository_id is None:
        return None
    operation = (
        db.query(Operation)
        .filter(
            Operation.repository_id == backup_job.repository_id,
            Operation.kind == kind,
            Operation.status == "running",
        )
        .order_by(Operation.id.desc())
        .first()
    )
    return MaintenanceJobFacade(db, operation) if operation is not None else None
```

`_cancel_running_maintenance_job` then works unchanged (it calls the
service cancel by `maintenance_job.id` and writes status through the
facade). `_resolve_backup_log_file` keeps the `log_file_path` branch only;
the download and stream routes lose their `"Logs saved to:"` and
"Legacy: logs stored in database" branches (a job with no `log_file_path`
and no agent logs answers the existing "no logs" responses). The `.logs`
facade property still reads the file, so `job.logs` reads stay valid.
Delete the four model imports; type hints become `BackupJobFacade`.

`maintenance_jobs.py`: `get_repository_maintenance_jobs` returns the
operations query only; `get_maintenance_job_with_access` docstring loses
"Deleted in phase 9". `packages.py` `list_jobs` and
`package_service.get_running_jobs`: operations only.

`repositories.py`: the rclone latest-sync block uses the operation only
(delete `_newer_rclone_job` and the `RcloneSyncJob` query); the repositories
list drops `_legacy_running` and the `or` halves; the delete route (5185-5260)
drops the five legacy loops and the backup unlink block (operations cascade
with the repository through `repository_id ... ondelete="CASCADE"`; keep the
scheduled job handling that follows). Delete the model imports.
`repository_wipe_service.py`: delete the `legacy_models` loop and the
`RestoreJob` loop in the admission check (the `CONFLICTING_KINDS` operations
query above them already covers every kind); keep the preview code; the
`serialize_job` hint becomes `Any`. In the two wipe routes
(`get_repository_wipe_job` at 5798 and `cancel_repository_wipe_preview`),
resolve previews explicitly: `resolve_wipe_job(db, job_id)` first, then
`db.query(RepositoryWipeJob).filter(id == job_id, status == "previewed")`
so a preview id still answers on the status route as it does today.

`schedule.py`: the delete-schedule unlink keeps the `Operation` update only;
the availability `last_success` query reads
`Operation.completed_at` for `kind == "backup"`, `scheduled_job_id == job.id`,
`status in SUCCESS_STATUSES`. `agents.py`: `_get_linked_backup_job` reads
`operation_id` only; `_maintenance_kind` returns `operation_job.kind`;
delete `LEGACY_MODELS`, `BackupJob`; `_mark_agent_job_started` hint.
`ssh_keys.py`: delete the two legacy updates. `dashboard.py`: the latest
restore check per repository is the newest `restore_check` operation per
`repository_id` (use `_newest_per_group` from `backup_facade` with
`Operation` grouped by `repository_id`, filtered to the kind) wrapped in
`MaintenanceJobFacade`; the 14-day lists are `Operation` queries by kind
with `started_at >= fourteen_days_ago`, wrapped in facades; hints become
`Any`. Read the health builders for the attributes they touch
(`archive_name`, `status`, `completed_at`, `started_at`, `progress_message`)
and confirm the facade exposes each.

`metrics.py`: every family reads `Operation` (joined with `Repository` for
the per-repository labels; backup by `repository_id` rather than by path,
which is why the orphaned family has no rows any more); the active-job
gauges count `status in ("queued", "running")` per kind and report the
legacy word in the label as today (`type="backup"`, ...). Emit the
`borg_backup_orphaned_jobs_total` HELP and TYPE lines with no samples.
Update `docs/METRICS.md` in Task 9.

The hint-only files: replace `BackupJob` with `Any` or `BackupJobFacade`,
`CheckJob` with `MaintenanceJobFacade`, `RestoreCheckJob` likewise,
`RestoreJob` with `RestoreJobFacade`; the two v2 `except` branches
(`prune_service.py` 277, `delete_archive_service.py` 187) resolve through
`resolve_maintenance_job`. Delete `app/tests/test_repository_deletion.py`
and `app/tests/README_repository_deletion_tests.md`.

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit -q -p no:randomly`
Expected: PASS apart from the 14 OIDC failures the main checkout's `.env`
causes (none in a worktree without an `.env`). Then `pytest tests/integration -q`
and compare with a clean `origin/main` run.

---

## Task 8: `BorgRouter.update_stats` retires

**Files:**
- Modify: `app/core/borg_router.py` (done in Task 6), `app/api/settings.py`, `app/routers/config.py`
- Test: `tests/unit/test_api_settings.py` (or the module that covers the stats refresh route), `tests/unit/test_borg_router.py`

**Interfaces:**
- Consumes: `enqueue_chain(db, ["stats", "archive_sync"], repository_id=..., trigger="manual")`.
- Produces: `settings._run_stats_refresh_background(repo_ids, username)` enqueues one chain per repository and counts enqueued rows as successes; the config import routes enqueue the same chain per created repository.

- [x] **Step 1: Write the failing test**

```python
def test_stats_refresh_enqueues_an_index_chain_per_repository(test_client, test_db, admin_headers):
    repos = [_repo(test_db, name=f"r{i}") for i in range(2)]
    response = test_client.post("/api/settings/system/refresh-stats", headers=admin_headers)
    assert response.status_code == 200
    kinds = sorted((op.repository_id, op.kind) for op in test_db.query(Operation).all())
    assert kinds == sorted((r.id, k) for r in repos for k in ("stats", "archive_sync"))
```

Find the exact route path and its response shape in `settings.py` around
line 1160 before writing the test; keep the response shape.

- [x] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit -q -k stats_refresh`
Expected: FAIL (`AttributeError: 'BorgRouter' object has no attribute 'update_stats'`).

- [x] **Step 3: Replace the callers**

`_run_stats_refresh_background` enqueues
`enqueue_chain(db, ["stats", "archive_sync"], repository_id=repo.id, trigger="manual")`
inside the loop and counts a success per repository; the
`last_stats_refresh` write stays. `app/routers/config.py` (both branches
after an import) does the same per created repository. Grep
`update_repository_stats` afterwards: if `BorgRouter.update_stats` was its
only caller, delete `update_repository_stats` from `app/api/repositories.py`
as well and note it in the spec's Notes (A.1 listed it as the phase 1
executor's predecessor).

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit -q -k "stats_refresh or borg_router or config"`
Expected: PASS.

---

## Task 9: Documentation, Postman, spec

**Files:**
- Modify: `docs/architecture/job-system.md`, `docs/api.md`, `docs/navigation.md`, `docs/METRICS.md`, `Borg_UI_API.postman_collection.json`, the spec's Appendix B and progress table

- [x] **Step 1: `docs/architecture/job-system.md`**

Rewrite around operations (spec 18, "phase 1, then phase 9"):

- "Job Lifecycle": the operations vocabulary (`queued`, `running`,
  `completed`, `completed_with_warnings`, `failed`, `cancelled`,
  `skipped`), with the note that the HTTP routes still answer `pending`
  for `queued`.
- "Main Job Types": the kind table from spec 6.3 (kind, category,
  exclusive), replacing the legacy list. Delete the paragraph about
  `repository_wipe_jobs`, `rclone_sync_jobs`, `package_install_jobs` being
  legacy tables; say the preview lives in `repository_wipe_jobs` and nothing
  else does.
- "Backup Jobs", "Restore Jobs", "Check, Prune, ...": delete every
  "rows written before phase N stay in ... until phase 9" sentence and the
  "Pre-phase-5 installs still have history" paragraph.
- "Restart Cleanup": the list is the operations runner's recovery (spec
  7.6) plus the two remaining sweeps (stale backup maintenance state, plan
  runs); delete the five legacy bullets.
- "Stale Scheduled Checks": delete the section (the dispatcher no longer
  fails stale rows; a queued check waits for its lane).
- "Deleting Job Entries": unchanged list, one sentence that the row is an
  operation and its log file goes with it.
- "Operations runner": replace "A backup that completes through the legacy
  backup paths" with the current wording (the runner enqueues the chain).
- Add a short "Upgrading from a release before the operations runner"
  paragraph: the first start after the upgrade copies every legacy job
  row into `operations` with new ids (spec 14), inline logs become
  operation log files, and rows whose repository was deleted are not
  copied.

- [x] **Step 2: `docs/api.md`**

Delete the four "falls back to the pre-phase-N row" sentences (lines 188,
195, 204, 226 today) and the "Legacy: logs stored in database" implication
in "Poll job logs". Add two sections after "Restore jobs":

"## Operations" with a route table for `/api/operations` (`GET /`, `GET
/queue`, `GET /repositories`, `GET /repositories/{id}`, `POST /reconcile`,
`POST /pause`, `POST /resume`, `PUT /limits`, `GET /{id}`, `POST
/{id}/cancel`, `GET /{id}/logs`, `GET /{id}/logs/download`), one line each
from the route docstrings in `app/api/operations.py`, and a sentence that
every `job_id` the job routes return is an operation id usable here.

"## Activity" with `GET /api/activity/recent` and its parameters (`limit`,
`job_type`, `status`, `category[]`, `trigger[]`, `repository_id`,
`collapse_runs`), the item shape (`activity_key`, `type`, `category`,
`trigger`, `followups`, and the legacy fields), and the three by-type
routes.

- [x] **Step 3: `docs/navigation.md`, `docs/METRICS.md`**

Activity row: "Review job history as operations: queued, running, and
finished work with follow-up index steps nested under their parent, live or
recent logs, and failures." `docs/METRICS.md`: under
`borg_backup_orphaned_jobs_total` add "(always empty since the job tables
collapsed into `operations`; kept so existing dashboards keep parsing)".

- [x] **Step 4: Postman**

Add a folder `25. Operations` with the twelve requests from Step 2 (same
`{{base_url}}` and auth header style as folder `12. Activity`), and extend
`List Recent Activity` in folder 12 with `category`, `trigger`,
`repository_id`, and `collapse_runs` query parameters. Validate with
`python3 -c "import json; json.load(open('Borg_UI_API.postman_collection.json'))"`.

- [x] **Step 5: Spec bookkeeping**

Append to Appendix B one row: "Phase 9 plan defaults accepted at G1
(2026-09-10): ..." listing the answers to the Open questions below. Update
the progress table row per 19.2 at each state change.

---

## Verification (before gate G2)

Run, from the worktree root, and record each result in the spec's Notes
column at G2:

```bash
pytest tests/unit -p no:randomly -q
pytest tests/integration -q               # compare with a clean origin/main run
ruff check app tests && ruff format --check app tests
git diff -U0 origin/main | grep -nP '\xe2\x80\x94' ; echo "em dashes above (expect none)"
git diff --stat origin/main -- frontend   # expect empty
grep -rnE '\b(BackupJob|CheckJob|PruneJob|CompactJob|RestoreCheckJob|DeleteArchiveJob|RcloneSyncJob|PackageInstallJob|RestoreJob|BackupJobRetryLineage)\b' app/ | grep -v "legacy_job_tables.py\|legacy_job_collapse.py\|alembic/versions"   # expect empty
grep -rn "legacy_running_exclusive\|LEGACY_MODELS\|_MIGRATED_LEGACY_MODELS\|_LEGACY_ACTIVE_STATUSES\|legacy_status import" app/   # expect empty
alembic heads                              # expect d0e1f2a3b4c5 (head)
python -m app.database.db_upgrade          # against a copy of a v2.2.x borg.db from a real install, if one is at hand
```

Then stop at gate G2.

---

## Self-review

Spec coverage: 9.3 (Activity reads operations; the union is gone) Task 5;
7.2 (`legacy_running_exclusive` deleted) Task 4; 7.6 (the legacy startup
sweeps deleted, the runner's recovery is the recovery) Task 6; 13 phase 9
row (delete legacy tables Tasks 1 to 3, `legacy_running_exclusive` Task 4,
`job-system.md`, `api.md`, `navigation.md`, Postman Task 9); 14 (the
one-off copy, previews kept, both upgrade paths) Tasks 1 to 3; 18 Task 9;
A.1 (`BorgRouter.update_stats` removed) Task 8; A.2 (`activity.py` single
query) Task 5; Appendix B (unqualified ids resolved, wipe preview decision
kept, no subagents) throughout. The section 14 feature flags
(`background_work_tab`, `archive_history` in `BetaFeaturesTab`) were checked
and do not exist as beta switches on `main` (`archive_history` is the plan
feature key, `background_work_tab` was never added), so there is nothing to
remove; recorded here rather than as a task.

Type consistency: `collapse_legacy_job_tables(connection, *, log_dir)` in
Tasks 1, 2, 3; `resolve_backup_job` returns `Optional[BackupJobFacade]` in
Tasks 4, 6, 7; `backup_job_link_columns` returns `{"operation_id": ...}` in
Tasks 4 and 7 (`script_library_executor` spreads it into `ScriptExecution`,
which no longer has `backup_job_id`); `_MAINTENANCE_STATUS_KIND` exists in
both `process_utils.py` (kept) and `backup.py` (Task 7); import it from
`app/utils/backup_maintenance.py` instead of defining it twice: add it
there in Task 6 and use it in both.

## Open questions

Each takes its default unless the owner says otherwise at G1.

1. **Copy versus drop.** Section 14 allows dropping the tables once
   `cleanup_retention_days` has elapsed since phase 8 shipped, or after an
   explicit one-off copy. No release has shipped phases 5 to 8, so the
   window cannot have elapsed for any install. Default: the copy, in the
   revision, for both upgrade paths. Alternatives: drop without copying
   and accept that every install loses its job history at the next
   release; or keep the tables one more release, which keeps every legacy
   branch this phase deletes.
2. **New ids for copied rows.** Default: yes; the link columns are
   rewritten and `params["legacy_id"]` keeps the old id for tracing.
   Alternative: preserve ids by offsetting the `operations` sequence, which
   cannot work because the legacy tables' id spaces overlap each other.
3. **Rows whose repository is gone.** `check_jobs.repository_id` and its
   four siblings have no `ondelete`, so SQLite installs can hold rows
   pointing at deleted repositories. `operations.repository_id` is
   enforced on both dialects. Default: skip those rows and count them in
   the report (they were unreachable through any route already, because
   every reader joined on the repository). Backup and restore rows keep
   their path in `params["repository"]` with a null `repository_id`, the
   shape phase 8 already uses for an unknown path.
4. **`repository_wipe_jobs` survives as the preview store** under its
   current table and class name, with only `previewed` rows. Alternative:
   rename to `repository_wipe_previews` and drop the execution columns,
   which is a second batch rewrite of a table for no behaviour change.
5. **Facades stay.** The six facade modules remain the attribute surface
   the services drive; this phase removes their legacy fallbacks only.
   Alternative: rewrite each service against `Operation` directly, which is
   service work, not deletion, and belongs to a follow-up per service.
6. **Inline log text becomes a file.** Legacy `logs` columns (and restore's
   database-only logs) are written to `operation_<id>.log` under
   `data_dir/logs` during the copy; a `Logs saved to: X` marker resolves to
   the existing file. Alternative: drop inline logs, which loses every
   pre-phase-7 restore log.
7. **`reconcile_orphaned_maintenance_jobs` is deleted**, not ported. It
   reaped legacy `pending` rows whose agent job was never queued. An
   operation is `queued` while it waits for its lane, and its agent job is
   created by the executor at dispatch, so "queued with no agent job" is
   the normal state, not an orphan; a dispatch failure fails the operation
   through `_fail_orphaned_maintenance_job`. The stale scheduled check
   cleanup goes for the same reason.
8. **`BorgRouter.update_stats` callers enqueue** `stats` and `archive_sync`
   rather than running inline. The settings refresh route keeps its
   response shape; its counts now mean "chains enqueued". Alternative: keep
   `update_stats` as a thin inline call into the stats executor, which A.1
   marked for removal here.
9. **`borg_backup_orphaned_jobs_total` stays as an empty family.**
   Alternative: drop it and note the removal in `docs/METRICS.md`.
10. **Pre-Alembic transfers land on `PRE_COLLAPSE_REVISION`** and then
    continue to head. Alternative: teach `_transfer` to fold legacy rows
    itself, duplicating the copy.
