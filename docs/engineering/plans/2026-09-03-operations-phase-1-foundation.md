# Operations Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit at the
> end of a task; the phase has one commit gate (G2) at the end, per section
> 19.4 of the spec and `.claude/instructions.md`.

**Goal:** Give Borg UI one `operations` table and one in-process runner with
per-repository lanes, then move the first two derived-data jobs (`stats`,
`archive_sync`) and the hourly stats refresh onto it, so that importing a
repository returns immediately and the Activity API can already read the new
rows.

**Architecture:** A new package `app/services/operations/` owns vocabulary,
enqueueing, follow-up chains, lane rules, the runner loop, crash recovery,
and SSE events. Executors are plain coroutines registered by kind. New
tables `operations`, `archives`, `archive_changes` are created by one
Alembic revision. The legacy job tables are untouched; `/api/activity/recent`
unions them with `operations`. A new `/api/operations` router exposes the
list, queue, cancel, pause, and limits routes. `stats_refresh_scheduler` is
replaced by a reconcile loop that enqueues runs instead of calling Borg.

**Tech Stack:** FastAPI, SQLAlchemy 1.x declarative models, Alembic with
`render_as_batch=True` (SQLite), asyncio, structlog, pytest with the
`test_db` / `test_client` / `admin_headers` fixtures from `tests/fixtures/api.py`
and the in-memory `db` pattern from `tests/unit/test_job_history_retention.py`.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
(sections 6.1, 6.3, 6.4, 6.5, 7, 8.1, 8.2, 9.1, 9.3, 9.4, 12, 14, 18, Appendix A, Appendix B).

## Global Constraints

- Phase 1 is backend only. No frontend files change. Frontend types for the
  vocabulary land in phase 3 (`frontend/src/types/operations.ts`).
- Spec 6.1 column list for `operations` is verbatim. Do not add or rename
  columns. Timestamps are naive UTC via `app.database.models.utc_now`.
- Spec 6.3 vocabularies are the only allowed string values for `kind`,
  `category`, `status`, `trigger`. Validate in Python, store as `String`.
- Priorities: manual and plan `0`, schedule `5`, followup `10`, reconcile
  and manual rebuild `20`.
- Spec 7.4 follow-up chains are verbatim. In phase 1 no `history_index` or
  `history_merge` executor exists, so `chain_for()` must drop kinds that
  have no registered executor rather than creating rows that can never run
  (Appendix B: "Community installs never create history stages, rather than
  creating and skipping them" applies the same way to missing executors).
- Runtime-mutable settings `index_workers` (default `2`) and
  `background_paused` (default `False`) are columns on `SystemSettings`,
  because `PUT /operations/limits` and pause/resume change them at runtime.
  `INDEX_ARCHIVE_INFO_PER_RUN` (default `20`) is an environment setting in
  `app/config.py`. This reading of spec section 14 is recorded under Open
  questions at the end of this plan.
- Never commit or push without the user's answer at gate G2. Do not use
  em dashes anywhere: not in code comments, docstrings, log messages, or
  docs. Use commas, periods, or parentheses.
- Every new module gets unit tests under `tests/unit/`. Every route gets a
  test through `test_client`. Run `python -m pytest tests/unit -q -x
  -p no:cacheprovider` before claiming a task done. Run `ruff check app
  tests` as well.
- Series inference (spec 6.6) is phase 2. Phase 1 stores `series` as the
  Borg 2 archive `name`, or the literal `"default"` for Borg 1. Document this
  in the executor docstring so phase 2 knows to replace it.
- Managed-agent repositories (`is_agent_executor(repository)` is true):
  `archive_sync` lists through the agent job path already used by
  `_update_agent_repository_stats`; `stats` completes without touching
  `total_size` and records `result = {"unique_csize": None,
  "reason": "agent_size_unsupported"}`.
- Log files for operations live next to the other job logs:
  `Path(settings.data_dir) / "logs" / f"operation_{id}.log"`, matching the
  `self.log_dir` convention in `app/services/check_service.py`.

## File Structure

Created:

- `app/services/operations/__init__.py` (empty, package marker)
- `app/services/operations/vocab.py` kinds, categories, statuses, triggers, priorities, legacy status map
- `app/services/operations/models.py` `serialize_operation()` and status helpers over `Operation` rows
- `app/services/operations/enqueue.py` `enqueue()`, `enqueue_chain()`, `new_run_id()`
- `app/services/operations/followups.py` `FOLLOWUPS`, `chain_for()`
- `app/services/operations/lanes.py` `legacy_running_exclusive()`, `lane_free()`, `can_start()`, `global_slot_available()`
- `app/services/operations/runner.py` `Outcome`, `OperationContext`, `OperationRunner`, `operation_runner`
- `app/services/operations/events.py` `broadcast_operation_updated()`, `broadcast_operation_progress()`
- `app/services/operations/reconcile.py` `enqueue_reconcile_runs()`, `ReconcileScheduler`, `reconcile_scheduler`
- `app/services/operations/executors/__init__.py` `REGISTRY`, `get_executor()`, `registered_kinds()`
- `app/services/operations/executors/index.py` `run_stats()`, `run_archive_sync()`, listing helpers
- `app/api/operations.py` router for `/api/operations`
- `app/database/alembic/versions/b1e2f3a4c5d6_add_operations_and_archives.py`
- `tests/unit/test_operations_vocab.py`
- `tests/unit/test_operations_enqueue.py`
- `tests/unit/test_operations_followups.py`
- `tests/unit/test_operations_lanes.py`
- `tests/unit/test_operations_runner.py`
- `tests/unit/test_operations_events.py`
- `tests/unit/test_operations_index_executors.py`
- `tests/unit/test_operations_reconcile.py`
- `tests/unit/test_api_operations.py`
- `tests/unit/test_activity_union.py`

Modified:

- `app/database/models.py` add `Operation`, `Archive`, `ArchiveChange`; add `index_workers`, `background_paused` to `SystemSettings`
- `app/config.py` add `index_archive_info_per_run: int = 20`
- `app/main.py` register router, run recovery, start runner and reconcile, stop starting `stats_refresh_scheduler`
- `app/api/activity.py` union `operations` rows into `/recent`, resolve operation kinds in logs and delete routes
- `app/api/repositories.py` `import_repository` records `import_connect` and enqueues follow-ups instead of calling `update_stats`
- `app/services/job_history_retention.py` add `Operation` to `_JOB_TABLES`
- `tests/unit/test_schedulers.py` remove `StatsRefreshScheduler` tests (replaced by `test_operations_reconcile.py`)
- `docs/architecture/job-system.md` add an "Operations runner" section
- `docs/configuration.md` add `INDEX_ARCHIVE_INFO_PER_RUN`

Deleted:

- `app/services/stats_refresh_scheduler.py` (its only caller is `app/main.py`; its tests move)

---

### Task 1: Vocabulary module

**Files:**
- Create: `app/services/operations/__init__.py`
- Create: `app/services/operations/vocab.py`
- Test: `tests/unit/test_operations_vocab.py`

**Interfaces:**
- Produces:
  - `KindSpec` dataclass with `category: str`, `exclusive: bool`
  - `KINDS: dict[str, KindSpec]` with exactly the 15 kinds of spec 6.3
  - `CATEGORIES: tuple[str, ...]`, `STATUSES: tuple[str, ...]`, `TRIGGERS: tuple[str, ...]`
  - `TERMINAL_STATUSES: frozenset[str]` = completed, completed_with_warnings, failed, cancelled, skipped
  - `SUCCESS_STATUSES: frozenset[str]` = completed, completed_with_warnings
  - `INDEX_KINDS: frozenset[str]` = stats, archive_sync, history_index, history_merge
  - `PRIORITY_MANUAL = 0`, `PRIORITY_SCHEDULE = 5`, `PRIORITY_FOLLOWUP = 10`, `PRIORITY_RECONCILE = 20`
  - `LEGACY_STATUS_MAP: dict[str, str]` = `{"pending": "queued", "needs_backup": "skipped", "running_prune": "running", "running_compact": "running", "prune_failed": "failed", "compact_failed": "failed"}`
  - `category_for(kind: str) -> str`, `is_exclusive(kind: str) -> bool`, `validate_kind(kind: str) -> str` (raises `ValueError`), `validate_status(status: str) -> str`, `validate_trigger(trigger: str) -> str`, `priority_for_trigger(trigger: str) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_vocab.py
import pytest

from app.services.operations import vocab


EXPECTED_KINDS = {
    "import_connect": ("import", False),
    "backup": ("backup", True),
    "restore": ("restore", False),
    "restore_check": ("restore", False),
    "check": ("maintenance", True),
    "prune": ("maintenance", True),
    "compact": ("maintenance", True),
    "delete_archive": ("maintenance", True),
    "wipe": ("maintenance", True),
    "rclone_sync": ("mirror", False),
    "package_install": ("system", False),
    "stats": ("index", False),
    "archive_sync": ("index", False),
    "history_index": ("index", True),
    "history_merge": ("index", False),
}


@pytest.mark.unit
def test_every_kind_has_category_and_exclusivity():
    assert set(vocab.KINDS) == set(EXPECTED_KINDS)
    for kind, (category, exclusive) in EXPECTED_KINDS.items():
        assert vocab.category_for(kind) == category
        assert vocab.is_exclusive(kind) is exclusive
        assert category in vocab.CATEGORIES


@pytest.mark.unit
def test_vocabularies_match_spec():
    assert vocab.CATEGORIES == (
        "import", "backup", "restore", "maintenance", "index", "mirror", "system",
    )
    assert vocab.STATUSES == (
        "queued", "running", "completed", "completed_with_warnings",
        "failed", "cancelled", "skipped",
    )
    assert vocab.TRIGGERS == (
        "manual", "schedule", "plan", "import", "followup", "reconcile", "retry",
    )
    assert vocab.TERMINAL_STATUSES == frozenset(
        {"completed", "completed_with_warnings", "failed", "cancelled", "skipped"}
    )
    assert vocab.SUCCESS_STATUSES == frozenset({"completed", "completed_with_warnings"})
    assert vocab.INDEX_KINDS == frozenset(
        {"stats", "archive_sync", "history_index", "history_merge"}
    )


@pytest.mark.unit
def test_priorities_by_trigger():
    assert vocab.priority_for_trigger("manual") == 0
    assert vocab.priority_for_trigger("plan") == 0
    assert vocab.priority_for_trigger("import") == 0
    assert vocab.priority_for_trigger("retry") == 0
    assert vocab.priority_for_trigger("schedule") == 5
    assert vocab.priority_for_trigger("followup") == 10
    assert vocab.priority_for_trigger("reconcile") == 20


@pytest.mark.unit
def test_legacy_status_map():
    assert vocab.LEGACY_STATUS_MAP == {
        "pending": "queued",
        "needs_backup": "skipped",
        "running_prune": "running",
        "running_compact": "running",
        "prune_failed": "failed",
        "compact_failed": "failed",
    }


@pytest.mark.unit
def test_validators_reject_unknown_values():
    assert vocab.validate_kind("stats") == "stats"
    with pytest.raises(ValueError):
        vocab.validate_kind("nope")
    with pytest.raises(ValueError):
        vocab.validate_status("pending")
    with pytest.raises(ValueError):
        vocab.validate_trigger("cron")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_vocab.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.operations'`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/__init__.py
"""Unified repository operations: vocabulary, runner, executors."""
```

```python
# app/services/operations/vocab.py
"""Operation vocabulary. Single source of truth for kinds, categories,
statuses, triggers, and priorities (spec section 6.3). The frontend mirror
lands in phase 3 at frontend/src/types/operations.ts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KindSpec:
    category: str
    exclusive: bool


KINDS: dict[str, KindSpec] = {
    "import_connect": KindSpec("import", False),
    "backup": KindSpec("backup", True),
    "restore": KindSpec("restore", False),
    "restore_check": KindSpec("restore", False),
    "check": KindSpec("maintenance", True),
    "prune": KindSpec("maintenance", True),
    "compact": KindSpec("maintenance", True),
    "delete_archive": KindSpec("maintenance", True),
    "wipe": KindSpec("maintenance", True),
    "rclone_sync": KindSpec("mirror", False),
    "package_install": KindSpec("system", False),
    "stats": KindSpec("index", False),
    "archive_sync": KindSpec("index", False),
    "history_index": KindSpec("index", True),
    "history_merge": KindSpec("index", False),
}

CATEGORIES: tuple[str, ...] = (
    "import", "backup", "restore", "maintenance", "index", "mirror", "system",
)

STATUSES: tuple[str, ...] = (
    "queued", "running", "completed", "completed_with_warnings",
    "failed", "cancelled", "skipped",
)

TRIGGERS: tuple[str, ...] = (
    "manual", "schedule", "plan", "import", "followup", "reconcile", "retry",
)

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "completed_with_warnings", "failed", "cancelled", "skipped"}
)
SUCCESS_STATUSES: frozenset[str] = frozenset({"completed", "completed_with_warnings"})
INDEX_KINDS: frozenset[str] = frozenset(
    {"stats", "archive_sync", "history_index", "history_merge"}
)

PRIORITY_MANUAL = 0
PRIORITY_SCHEDULE = 5
PRIORITY_FOLLOWUP = 10
PRIORITY_RECONCILE = 20

_PRIORITY_BY_TRIGGER = {
    "manual": PRIORITY_MANUAL,
    "plan": PRIORITY_MANUAL,
    "import": PRIORITY_MANUAL,
    "retry": PRIORITY_MANUAL,
    "schedule": PRIORITY_SCHEDULE,
    "followup": PRIORITY_FOLLOWUP,
    "reconcile": PRIORITY_RECONCILE,
}

LEGACY_STATUS_MAP: dict[str, str] = {
    "pending": "queued",
    "needs_backup": "skipped",
    "running_prune": "running",
    "running_compact": "running",
    "prune_failed": "failed",
    "compact_failed": "failed",
}


def validate_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"Unknown operation kind: {kind!r}")
    return kind


def validate_status(status: str) -> str:
    if status not in STATUSES:
        raise ValueError(f"Unknown operation status: {status!r}")
    return status


def validate_trigger(trigger: str) -> str:
    if trigger not in TRIGGERS:
        raise ValueError(f"Unknown operation trigger: {trigger!r}")
    return trigger


def category_for(kind: str) -> str:
    return KINDS[validate_kind(kind)].category


def is_exclusive(kind: str) -> bool:
    return KINDS[validate_kind(kind)].exclusive


def priority_for_trigger(trigger: str) -> int:
    return _PRIORITY_BY_TRIGGER[validate_trigger(trigger)]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_vocab.py -q -p no:cacheprovider`
Expected: 5 passed

---

### Task 2: Models, settings columns, config, and migration

**Files:**
- Modify: `app/database/models.py` (after `class RepositoryWipeJob`, before `class SystemSettings`; and inside `SystemSettings`)
- Modify: `app/config.py` (inside `class Settings`, near `cache_max_size_mb`)
- Create: `app/database/alembic/versions/b1e2f3a4c5d6_add_operations_and_archives.py`
- Test: `tests/unit/test_operations_models.py`

**Interfaces:**
- Produces: `Operation`, `Archive`, `ArchiveChange` SQLAlchemy models with the exact columns of spec 6.1, 6.4, 6.5; `SystemSettings.index_workers` (Integer, default 2), `SystemSettings.background_paused` (Boolean, default False); `settings.index_archive_info_per_run` (int, default 20).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_models.py
import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Archive,
    ArchiveChange,
    Base,
    Operation,
    Repository,
    SystemSettings,
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


def _repo(db):
    repo = Repository(name="r1", path="/tmp/r1", encryption="none", compression="lz4")
    db.add(repo)
    db.commit()
    return repo


@pytest.mark.unit
def test_operation_defaults(db):
    repo = _repo(db)
    op = Operation(repository_id=repo.id, kind="stats", category="index", run_id="run-1")
    db.add(op)
    db.commit()
    db.refresh(op)
    assert op.status == "queued"
    assert op.trigger == "manual"
    assert op.priority == 10
    assert op.created_at is not None
    assert op.started_at is None


@pytest.mark.unit
def test_operation_columns_match_spec():
    cols = {c.name for c in Operation.__table__.columns}
    assert cols == {
        "id", "repository_id", "kind", "category", "status", "trigger", "priority",
        "run_id", "depends_on_id", "triggered_by_user_id", "scheduled_job_id",
        "backup_plan_run_id", "execution_mode", "process_pid", "process_start_time",
        "progress_percent", "progress_current", "progress_total", "progress_message",
        "error_message", "skip_reason", "log_file_path", "params", "result",
        "created_at", "started_at", "completed_at",
    }
    index_columns = {tuple(c.name for c in ix.columns) for ix in Operation.__table__.indexes}
    assert ("repository_id", "status") in index_columns
    assert ("status", "priority", "created_at") in index_columns
    assert ("category", "created_at") in index_columns


@pytest.mark.unit
def test_archive_unique_per_repository_and_cascade(db):
    repo = _repo(db)
    a = Archive(repository_id=repo.id, borg_id="abc", name="n", series="default",
                start=__import__("datetime").datetime(2026, 9, 1))
    db.add(a)
    db.commit()
    db.add(ArchiveChange(archive_id=a.id, path="/x", change="added", size_after=1))
    db.commit()
    assert a.history_state == "pending"
    assert a.history_truncated is False
    dup = Archive(repository_id=repo.id, borg_id="abc", name="n2", series="default",
                  start=__import__("datetime").datetime(2026, 9, 2))
    db.add(dup)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()
    db.delete(db.get(Repository, repo.id))
    db.commit()
    assert db.query(Archive).count() == 0
    assert db.query(ArchiveChange).count() == 0


@pytest.mark.unit
def test_system_settings_new_columns(db):
    s = SystemSettings()
    db.add(s)
    db.commit()
    db.refresh(s)
    assert s.index_workers == 2
    assert s.background_paused is False


@pytest.mark.unit
def test_config_has_index_archive_info_per_run():
    from app.config import settings
    assert settings.index_archive_info_per_run == 20
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_models.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'Operation'`

- [ ] **Step 3: Add the models**

In `app/database/models.py`, confirm the `from sqlalchemy import (...)` block at the top includes `BigInteger`, `Boolean`, `Column`, `DateTime`, `Float`, `ForeignKey`, `Index`, `Integer`, `JSON`, `String`, `Text`, `UniqueConstraint`; add any that are missing. Then insert directly before `class SystemSettings(Base):`:

```python
class Operation(Base):
    """One unit of work on (usually) one repository. Spec section 6.1."""

    __tablename__ = "operations"

    id = Column(Integer, primary_key=True)
    repository_id = Column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    trigger = Column(String, nullable=False, default="manual")
    priority = Column(Integer, nullable=False, default=10)
    run_id = Column(String(36), nullable=False, index=True)
    depends_on_id = Column(
        Integer, ForeignKey("operations.id", ondelete="SET NULL"), nullable=True
    )
    triggered_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_job_id = Column(
        Integer, ForeignKey("scheduled_jobs.id", ondelete="SET NULL"), nullable=True
    )
    backup_plan_run_id = Column(
        Integer, ForeignKey("backup_plan_runs.id", ondelete="SET NULL"), nullable=True
    )
    execution_mode = Column(String, nullable=True)  # server | remote_ssh | agent | rclone
    process_pid = Column(Integer, nullable=True)
    process_start_time = Column(Float, nullable=True)
    progress_percent = Column(Float, nullable=True)
    progress_current = Column(Integer, nullable=True)
    progress_total = Column(Integer, nullable=True)
    progress_message = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    skip_reason = Column(String, nullable=True)
    log_file_path = Column(String, nullable=True)
    params = Column(JSON, nullable=True)  # kind-specific input, small
    result = Column(JSON, nullable=True)  # kind-specific output summary, small
    created_at = Column(DateTime, default=utc_now, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_operations_repository_status", "repository_id", "status"),
        Index("ix_operations_status_priority_created", "status", "priority", "created_at"),
        Index("ix_operations_category_created", "category", "created_at"),
    )


class Archive(Base):
    """Persisted archive list per repository. Spec section 6.4."""

    __tablename__ = "archives"

    id = Column(Integer, primary_key=True)
    repository_id = Column(
        Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    borg_id = Column(String(64), nullable=False)
    name = Column(String, nullable=False)
    series = Column(String, nullable=False, index=True)
    start = Column(DateTime, nullable=False, index=True)
    end = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    nfiles = Column(Integer, nullable=True)
    original_size = Column(BigInteger, nullable=True)
    compressed_size = Column(BigInteger, nullable=True)
    deduplicated_size = Column(BigInteger, nullable=True)
    hostname = Column(String, nullable=True)
    username = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    backup_operation_id = Column(
        Integer, ForeignKey("operations.id", ondelete="SET NULL"), nullable=True
    )
    history_state = Column(String, nullable=False, default="pending")
    history_indexed_at = Column(DateTime, nullable=True)
    history_rows = Column(Integer, nullable=True)
    history_truncated = Column(Boolean, nullable=False, default=False)
    first_seen_at = Column(DateTime, default=utc_now, nullable=False)
    last_seen_at = Column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (UniqueConstraint("repository_id", "borg_id"),)


class ArchiveChange(Base):
    """One changed path per archive relative to its predecessor. Spec 6.5."""

    __tablename__ = "archive_changes"

    id = Column(Integer, primary_key=True)
    archive_id = Column(
        Integer, ForeignKey("archives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path = Column(Text, nullable=False)
    change = Column(String(8), nullable=False)  # added | removed | modified | summary
    size_before = Column(BigInteger, nullable=True)
    size_after = Column(BigInteger, nullable=True)
    mode_changed = Column(Boolean, nullable=False, default=False)
    owner_changed = Column(Boolean, nullable=False, default=False)
    summary_count = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_archive_changes_archive_path", "archive_id", "path"),
        Index("ix_archive_changes_path", "path"),
    )
```

Inside `class SystemSettings(Base)`, directly after the `stats_refresh_interval_minutes` and `last_stats_refresh` columns, add:

```python
    # Operations runner (spec section 7.3)
    index_workers = Column(Integer, default=2, nullable=False)
    background_paused = Column(Boolean, default=False, nullable=False)
```

In `app/config.py`, inside `class Settings(BaseSettings)` next to `cache_max_size_mb`, add:

```python
    # Operations index: per-archive `borg info` calls per archive_sync run
    index_archive_info_per_run: int = 20
```

- [ ] **Step 4: Write the migration**

```python
# app/database/alembic/versions/b1e2f3a4c5d6_add_operations_and_archives.py
"""add operations, archives, archive_changes tables and runner settings

Revision ID: b1e2f3a4c5d6
Revises: c7e4f8a1d2b3
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa

revision = "b1e2f3a4c5d6"
down_revision = "c7e4f8a1d2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("trigger", sa.String(), nullable=False, server_default="manual"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("depends_on_id", sa.Integer(), sa.ForeignKey("operations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("triggered_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scheduled_job_id", sa.Integer(), sa.ForeignKey("scheduled_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("backup_plan_run_id", sa.Integer(), sa.ForeignKey("backup_plan_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("execution_mode", sa.String(), nullable=True),
        sa.Column("process_pid", sa.Integer(), nullable=True),
        sa.Column("process_start_time", sa.Float(), nullable=True),
        sa.Column("progress_percent", sa.Float(), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("progress_message", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("log_file_path", sa.String(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_operations_repository_id", "operations", ["repository_id"])
    op.create_index("ix_operations_kind", "operations", ["kind"])
    op.create_index("ix_operations_category", "operations", ["category"])
    op.create_index("ix_operations_status", "operations", ["status"])
    op.create_index("ix_operations_run_id", "operations", ["run_id"])
    op.create_index("ix_operations_created_at", "operations", ["created_at"])
    op.create_index("ix_operations_repository_status", "operations", ["repository_id", "status"])
    op.create_index("ix_operations_status_priority_created", "operations", ["status", "priority", "created_at"])
    op.create_index("ix_operations_category_created", "operations", ["category", "created_at"])

    op.create_table(
        "archives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("borg_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("series", sa.String(), nullable=False),
        sa.Column("start", sa.DateTime(), nullable=False),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("nfiles", sa.Integer(), nullable=True),
        sa.Column("original_size", sa.BigInteger(), nullable=True),
        sa.Column("compressed_size", sa.BigInteger(), nullable=True),
        sa.Column("deduplicated_size", sa.BigInteger(), nullable=True),
        sa.Column("hostname", sa.String(), nullable=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("backup_operation_id", sa.Integer(), sa.ForeignKey("operations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("history_state", sa.String(), nullable=False, server_default="pending"),
        sa.Column("history_indexed_at", sa.DateTime(), nullable=True),
        sa.Column("history_rows", sa.Integer(), nullable=True),
        sa.Column("history_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("repository_id", "borg_id", name="uq_archives_repository_id_borg_id"),
    )
    op.create_index("ix_archives_repository_id", "archives", ["repository_id"])
    op.create_index("ix_archives_series", "archives", ["series"])
    op.create_index("ix_archives_start", "archives", ["start"])

    op.create_table(
        "archive_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("archive_id", sa.Integer(), sa.ForeignKey("archives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("change", sa.String(8), nullable=False),
        sa.Column("size_before", sa.BigInteger(), nullable=True),
        sa.Column("size_after", sa.BigInteger(), nullable=True),
        sa.Column("mode_changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("owner_changed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary_count", sa.Integer(), nullable=True),
    )
    op.create_index("ix_archive_changes_archive_id", "archive_changes", ["archive_id"])
    op.create_index("ix_archive_changes_archive_path", "archive_changes", ["archive_id", "path"])
    op.create_index("ix_archive_changes_path", "archive_changes", ["path"])

    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column("index_workers", sa.Integer(), nullable=False, server_default="2")
        )
        batch_op.add_column(
            sa.Column("background_paused", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("background_paused")
        batch_op.drop_column("index_workers")
    op.drop_index("ix_archive_changes_path", table_name="archive_changes")
    op.drop_index("ix_archive_changes_archive_path", table_name="archive_changes")
    op.drop_index("ix_archive_changes_archive_id", table_name="archive_changes")
    op.drop_table("archive_changes")
    op.drop_index("ix_archives_start", table_name="archives")
    op.drop_index("ix_archives_series", table_name="archives")
    op.drop_index("ix_archives_repository_id", table_name="archives")
    op.drop_table("archives")
    for name in (
        "ix_operations_category_created",
        "ix_operations_status_priority_created",
        "ix_operations_repository_status",
        "ix_operations_created_at",
        "ix_operations_run_id",
        "ix_operations_status",
        "ix_operations_category",
        "ix_operations_kind",
        "ix_operations_repository_id",
    ):
        op.drop_index(name, table_name="operations")
    op.drop_table("operations")
```

Before writing, confirm the head with `grep -rh "^down_revision" app/database/alembic/versions/*.py | sort | uniq -c` and `grep -rh "^revision" app/database/alembic/versions/*.py`; `c7e4f8a1d2b3` must be the only revision no other file revises. If a newer head exists, use it as `down_revision`.

- [ ] **Step 5: Run the tests and the migration check**

Run: `python -m pytest tests/unit/test_operations_models.py -q -p no:cacheprovider`
Expected: 5 passed

Run: `DATA_DIR=$(mktemp -d) alembic upgrade head && DATA_DIR=$(mktemp -d) alembic downgrade -1`
Expected: both complete without error. If the repository has a dedicated migration test (search `tests/unit` for `alembic`), run it too.

---

### Task 3: Serialization helpers

**Files:**
- Create: `app/services/operations/models.py`
- Test: `tests/unit/test_operations_models.py` (append)

**Interfaces:**
- Produces:
  - `serialize_operation(op: Operation, *, repository_name: str | None = None, repository_path: str | None = None, has_logs: bool = False, followups: list[dict] | None = None) -> dict` returning every key of the `OperationItem` model defined in Task 11: `activity_key`, `id`, `type` (= kind), `kind`, `category`, `status`, `trigger`, `priority`, `run_id`, `depends_on_id`, `repository_id`, `repository`, `repository_path`, `started_at`, `completed_at`, `created_at`, `error_message`, `skip_reason`, `log_file_path`, `triggered_by` (= `"schedule"` when trigger is schedule, else `"manual"`), `schedule_id`, `schedule_name` (None), `backup_plan_id` (None), `backup_plan_run_id`, `backup_plan_name` (None), `archive_name` (from `params.get("archive_name")`), `package_name` (None), `has_logs`, `progress_percent`, `progress_current`, `progress_total`, `progress_message`, `execution_mode`, `params`, `result`, `followups`.
  - `is_terminal(op) -> bool`, `is_success(op) -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_operations_models.py`:

```python
@pytest.mark.unit
def test_serialize_operation_shape(db):
    from app.services.operations.models import is_success, is_terminal, serialize_operation

    repo = _repo(db)
    op = Operation(
        repository_id=repo.id, kind="archive_sync", category="index", run_id="run-9",
        trigger="schedule", priority=5, params={"archive_name": "a1"},
        status="completed", result={"count": 3},
    )
    db.add(op)
    db.commit()
    item = serialize_operation(op, repository_name=repo.name, repository_path=repo.path)
    assert item["id"] == op.id
    assert item["type"] == "archive_sync"
    assert item["kind"] == "archive_sync"
    assert item["category"] == "index"
    assert item["triggered_by"] == "schedule"
    assert item["trigger"] == "schedule"
    assert item["repository"] == "r1"
    assert item["repository_path"] == "/tmp/r1"
    assert item["archive_name"] == "a1"
    assert item["activity_key"] == f"operation:{op.id}"
    assert item["followups"] == []
    assert item["has_logs"] is False
    assert is_terminal(op) and is_success(op)
    op.status = "running"
    assert not is_terminal(op)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_operations_models.py::test_serialize_operation_shape -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/models.py
"""Typed helpers over Operation rows."""

from typing import Optional

from app.database.models import Operation
from app.services.operations.vocab import SUCCESS_STATUSES, TERMINAL_STATUSES


def is_terminal(op: Operation) -> bool:
    return op.status in TERMINAL_STATUSES


def is_success(op: Operation) -> bool:
    return op.status in SUCCESS_STATUSES


def serialize_operation(
    op: Operation,
    *,
    repository_name: Optional[str] = None,
    repository_path: Optional[str] = None,
    has_logs: bool = False,
    followups: Optional[list[dict]] = None,
) -> dict:
    """Return the OperationItem dict (a superset of ActivityItem, spec 9.1)."""
    params = op.params or {}
    return {
        "activity_key": f"operation:{op.id}",
        "id": op.id,
        "type": op.kind,
        "kind": op.kind,
        "category": op.category,
        "status": op.status,
        "trigger": op.trigger,
        "priority": op.priority,
        "run_id": op.run_id,
        "depends_on_id": op.depends_on_id,
        "repository_id": op.repository_id,
        "repository": repository_name,
        "repository_path": repository_path,
        "started_at": op.started_at,
        "completed_at": op.completed_at,
        "created_at": op.created_at,
        "error_message": op.error_message,
        "skip_reason": op.skip_reason,
        "log_file_path": op.log_file_path,
        "triggered_by": "schedule" if op.trigger == "schedule" else "manual",
        "schedule_id": op.scheduled_job_id,
        "schedule_name": None,
        "backup_plan_id": None,
        "backup_plan_run_id": op.backup_plan_run_id,
        "backup_plan_name": None,
        "archive_name": params.get("archive_name"),
        "package_name": None,
        "has_logs": has_logs,
        "progress_percent": op.progress_percent,
        "progress_current": op.progress_current,
        "progress_total": op.progress_total,
        "progress_message": op.progress_message,
        "execution_mode": op.execution_mode,
        "params": op.params,
        "result": op.result,
        "followups": list(followups or []),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/unit/test_operations_models.py -q -p no:cacheprovider`
Expected: 6 passed

---

### Task 4: Enqueue

**Files:**
- Create: `app/services/operations/enqueue.py`
- Test: `tests/unit/test_operations_enqueue.py`

**Interfaces:**
- Consumes: `vocab.validate_kind`, `vocab.validate_trigger`, `vocab.category_for`, `vocab.priority_for_trigger`; `Operation` model.
- Produces:
  - `new_run_id() -> str` (uuid4 string)
  - `enqueue(db, kind, *, repository_id=None, trigger="manual", priority=None, run_id=None, depends_on_id=None, triggered_by_user_id=None, scheduled_job_id=None, backup_plan_run_id=None, params=None, execution_mode=None, commit=True) -> Operation`. Sets `category` from the kind, `priority` from the trigger when not given, generates `run_id` when not given, commits when `commit=True`, then calls `wake_runner()`.
  - `enqueue_chain(db, kinds, *, repository_id, trigger, priority=None, run_id=None, depends_on_id=None, triggered_by_user_id=None, scheduled_job_id=None, backup_plan_run_id=None, commit=True) -> list[Operation]`: each operation depends on the previous one; the first depends on `depends_on_id`.
  - `wake_runner() -> None`: imports `operation_runner` from `runner.py` lazily and calls `operation_runner.wake()`; swallows `ImportError` and `RuntimeError` so enqueue works outside an event loop (tests, CLI).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_enqueue.py
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.enqueue import enqueue, enqueue_chain, new_run_id


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
def repo(db):
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.commit()
    return r


@pytest.mark.unit
def test_enqueue_fills_category_priority_and_run_id(db, repo):
    op = enqueue(db, "stats", repository_id=repo.id, trigger="reconcile")
    assert op.id is not None
    assert op.category == "index"
    assert op.priority == 20
    assert op.status == "queued"
    assert len(op.run_id) == 36
    assert db.query(Operation).count() == 1


@pytest.mark.unit
def test_enqueue_explicit_priority_wins(db, repo):
    op = enqueue(db, "stats", repository_id=repo.id, trigger="reconcile", priority=3)
    assert op.priority == 3


@pytest.mark.unit
def test_enqueue_rejects_unknown_kind_and_trigger(db, repo):
    with pytest.raises(ValueError):
        enqueue(db, "bogus", repository_id=repo.id)
    with pytest.raises(ValueError):
        enqueue(db, "stats", repository_id=repo.id, trigger="cron")


@pytest.mark.unit
def test_enqueue_chain_links_dependencies(db, repo):
    parent = enqueue(db, "import_connect", repository_id=repo.id, trigger="import")
    chain = enqueue_chain(
        db, ["stats", "archive_sync"], repository_id=repo.id,
        trigger="followup", run_id=parent.run_id, depends_on_id=parent.id,
    )
    assert [c.kind for c in chain] == ["stats", "archive_sync"]
    assert chain[0].depends_on_id == parent.id
    assert chain[1].depends_on_id == chain[0].id
    assert {c.run_id for c in chain} == {parent.run_id}
    assert all(c.priority == 10 for c in chain)


@pytest.mark.unit
def test_enqueue_wakes_runner(db, repo, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: calls.append(1))
    enqueue(db, "stats", repository_id=repo.id)
    assert calls == [1]


@pytest.mark.unit
def test_new_run_id_is_unique():
    assert new_run_id() != new_run_id()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_enqueue.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/enqueue.py
"""Create operations rows. The only writer of new queued operations."""

import uuid
from typing import Iterable, Optional

import structlog
from sqlalchemy.orm import Session

from app.database.models import Operation
from app.services.operations import vocab

logger = structlog.get_logger()


def new_run_id() -> str:
    return str(uuid.uuid4())


def wake_runner() -> None:
    """Nudge the runner loop. Safe to call without a running loop."""
    try:
        from app.services.operations.runner import operation_runner

        operation_runner.wake()
    except (ImportError, RuntimeError):
        # No runner in this process (tests, scripts). The runner polls anyway.
        pass


def enqueue(
    db: Session,
    kind: str,
    *,
    repository_id: Optional[int] = None,
    trigger: str = "manual",
    priority: Optional[int] = None,
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
    triggered_by_user_id: Optional[int] = None,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    params: Optional[dict] = None,
    execution_mode: Optional[str] = None,
    commit: bool = True,
) -> Operation:
    vocab.validate_kind(kind)
    vocab.validate_trigger(trigger)
    op = Operation(
        repository_id=repository_id,
        kind=kind,
        category=vocab.category_for(kind),
        status="queued",
        trigger=trigger,
        priority=vocab.priority_for_trigger(trigger) if priority is None else priority,
        run_id=run_id or new_run_id(),
        depends_on_id=depends_on_id,
        triggered_by_user_id=triggered_by_user_id,
        scheduled_job_id=scheduled_job_id,
        backup_plan_run_id=backup_plan_run_id,
        params=params,
        execution_mode=execution_mode,
    )
    db.add(op)
    if commit:
        db.commit()
        db.refresh(op)
    else:
        db.flush()
    logger.debug("Enqueued operation", operation_id=op.id, kind=kind,
                 repository_id=repository_id, trigger=trigger)
    wake_runner()
    return op


def enqueue_chain(
    db: Session,
    kinds: Iterable[str],
    *,
    repository_id: Optional[int],
    trigger: str,
    priority: Optional[int] = None,
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
    triggered_by_user_id: Optional[int] = None,
    scheduled_job_id: Optional[int] = None,
    backup_plan_run_id: Optional[int] = None,
    commit: bool = True,
) -> list[Operation]:
    """Enqueue kinds in order, each depending on the previous one."""
    run_id = run_id or new_run_id()
    created: list[Operation] = []
    previous_id = depends_on_id
    for kind in kinds:
        op = enqueue(
            db, kind,
            repository_id=repository_id, trigger=trigger, priority=priority,
            run_id=run_id, depends_on_id=previous_id,
            triggered_by_user_id=triggered_by_user_id,
            scheduled_job_id=scheduled_job_id, backup_plan_run_id=backup_plan_run_id,
            commit=False,
        )
        previous_id = op.id
        created.append(op)
    if commit:
        db.commit()
        for op in created:
            db.refresh(op)
    return created
```

Note: `enqueue(..., commit=False)` uses `db.flush()` so `op.id` is available for the next link. Because `wake_runner()` is called inside `enqueue`, `enqueue_chain` wakes the runner once per link; that is harmless since `wake()` only sets an event.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_enqueue.py -q -p no:cacheprovider`
Expected: 6 passed

---

### Task 5: Follow-up chains

**Files:**
- Create: `app/services/operations/followups.py`
- Test: `tests/unit/test_operations_followups.py`

**Interfaces:**
- Produces:
  - `FOLLOWUPS: dict[str, tuple[str, ...]]` exactly as spec 7.4.
  - `chain_for(kind: str, *, available: Optional[set[str]] = None) -> list[str]`: the chain for `kind`, filtered to kinds present in `available` when given. Unknown kind raises `ValueError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_followups.py
import pytest

from app.services.operations.followups import FOLLOWUPS, chain_for


@pytest.mark.unit
def test_chain_table_matches_spec_7_4():
    assert FOLLOWUPS == {
        "import_connect": ("stats", "archive_sync", "history_index"),
        "backup": ("archive_sync", "history_index", "stats"),
        "prune": ("archive_sync", "history_merge", "stats"),
        "delete_archive": ("archive_sync", "history_merge", "stats"),
        "compact": ("stats",),
        "check": (),
        "wipe": ("archive_sync", "history_merge", "stats"),
        "restore": (),
        "restore_check": (),
        "rclone_sync": (),
        "package_install": (),
        "stats": (),
        "archive_sync": (),
        "history_index": (),
        "history_merge": (),
    }


@pytest.mark.unit
def test_chain_for_filters_to_available_executors():
    assert chain_for("import_connect") == ["stats", "archive_sync", "history_index"]
    assert chain_for("import_connect", available={"stats", "archive_sync"}) == [
        "stats", "archive_sync",
    ]
    assert chain_for("prune", available={"stats", "archive_sync"}) == [
        "archive_sync", "stats",
    ]
    assert chain_for("check") == []


@pytest.mark.unit
def test_chain_for_rejects_unknown_kind():
    with pytest.raises(ValueError):
        chain_for("bogus")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_followups.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/followups.py
"""Follow-up chains (spec section 7.4). Created by the runner when a parent
operation reaches a success state. Phase 2 adds plan awareness here
(spec 11.2): history kinds are dropped for Community installs."""

from typing import Optional

from app.services.operations.vocab import validate_kind

FOLLOWUPS: dict[str, tuple[str, ...]] = {
    "import_connect": ("stats", "archive_sync", "history_index"),
    "backup": ("archive_sync", "history_index", "stats"),
    "prune": ("archive_sync", "history_merge", "stats"),
    "delete_archive": ("archive_sync", "history_merge", "stats"),
    "compact": ("stats",),
    "check": (),
    "wipe": ("archive_sync", "history_merge", "stats"),
    "restore": (),
    "restore_check": (),
    "rclone_sync": (),
    "package_install": (),
    "stats": (),
    "archive_sync": (),
    "history_index": (),
    "history_merge": (),
}


def chain_for(kind: str, *, available: Optional[set[str]] = None) -> list[str]:
    """Return the follow-up kinds for `kind`, in order.

    When `available` is given (the runner passes its registered executor
    kinds), kinds without an executor are dropped so no row is created that
    can never run.
    """
    validate_kind(kind)
    chain = list(FOLLOWUPS[kind])
    if available is not None:
        chain = [k for k in chain if k in available]
    return chain
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_followups.py -q -p no:cacheprovider`
Expected: 3 passed

---

### Task 6: Lane rules and global limits

**Files:**
- Create: `app/services/operations/lanes.py`
- Test: `tests/unit/test_operations_lanes.py`

**Interfaces:**
- Consumes: `vocab.is_exclusive`, `vocab.INDEX_KINDS`; models `Operation`, `Repository`, `SystemSettings`, `BackupJob`, `CheckJob`, `PruneJob`, `CompactJob`, `RepositoryWipeJob`, `DeleteArchiveJob`.
- Produces:
  - `LEGACY_RUNNING_STATUSES = ("running", "running_prune", "running_compact")`
  - `legacy_running_exclusive(db, repository_id) -> bool`: true if any legacy exclusive job table has a row for the repository in a running status. `BackupJob` matches on `repository_id` and status in `LEGACY_RUNNING_STATUSES`; the others match on `repository_id` and `status == "running"`. Deleted in phase 9.
  - `running_exclusive_operation(db, repository_id, *, exclude_id=None) -> bool`: any `operations` row for the repository with `status == "running"` and an exclusive kind.
  - `lane_free(db, repository_id, *, exclude_id=None) -> bool` = not `running_exclusive_operation` and not `legacy_running_exclusive`.
  - `running_count(db, *, kind=None, kinds=None, trigger=None, triggers=None, category=None) -> int` over `operations` with `status == "running"`.
  - `global_slot_available(db, op, settings) -> bool` per spec 7.3, where `settings` is a `SystemSettings` row or `None` (defaults: `max_concurrent_backups=1`, `max_concurrent_scheduled_backups=2`, `max_concurrent_scheduled_checks=4`, `index_workers=2`, `background_paused=False`).
  - `can_start(db, op, settings) -> bool` per spec 7.2 combined with `global_slot_available`.

Lane rules in `can_start`:

1. If `settings.background_paused` and `op.trigger in ("followup", "reconcile")`: False.
2. If `not global_slot_available(db, op, settings)`: False.
3. If `op.repository_id is None`: True (system kinds have no lane).
4. If `is_exclusive(op.kind)`: return `lane_free(db, op.repository_id, exclude_id=op.id)`.
5. If `op.kind in INDEX_KINDS` (non-exclusive index kinds): if the lane is free return True; else return `bool(repository.bypass_lock or (settings and settings.bypass_lock_on_list))` where `repository = db.get(Repository, op.repository_id)`.
6. Otherwise (non-exclusive, non-index kinds such as restore or rclone_sync): True.

Global limits in `global_slot_available`:

- `op.kind == "backup"` and `op.trigger == "schedule"`: `running_count(db, kind="backup", trigger="schedule") < settings.max_concurrent_scheduled_backups`.
- `op.kind == "backup"` and other triggers: `running_count(db, kind="backup", triggers=("manual", "plan", "import", "retry", "followup", "reconcile")) < settings.max_concurrent_backups`.
- `op.kind == "check"` and `op.trigger == "schedule"`: `running_count(db, kind="check", trigger="schedule") < settings.max_concurrent_scheduled_checks`.
- `op.kind in INDEX_KINDS`: `running_count(db, kinds=INDEX_KINDS) < settings.index_workers`.
- Anything else: True.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_lanes.py
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupJob, Base, CheckJob, Operation, Repository, SystemSettings,
)
from app.services.operations import lanes
from app.services.operations.enqueue import enqueue


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
def repo(db):
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.commit()
    return r


@pytest.fixture()
def settings(db):
    s = SystemSettings()
    db.add(s)
    db.commit()
    return s


def _running(db, kind, repo, trigger="manual"):
    op = enqueue(db, kind, repository_id=repo.id, trigger=trigger)
    op.status = "running"
    db.commit()
    return op


@pytest.mark.unit
def test_lane_free_without_running_work(db, repo, settings):
    op = enqueue(db, "history_index", repository_id=repo.id)
    assert lanes.lane_free(db, repo.id) is True
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_exclusive_blocks_second_exclusive_on_same_repo(db, repo, settings):
    _running(db, "history_index", repo)
    second = enqueue(db, "history_index", repository_id=repo.id)
    assert lanes.can_start(db, second, settings) is False


@pytest.mark.unit
def test_exclusive_does_not_block_other_repo(db, repo, settings):
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add(other)
    db.commit()
    _running(db, "history_index", repo)
    op = enqueue(db, "history_index", repository_id=other.id)
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_legacy_running_backup_blocks_lane(db, repo, settings):
    db.add(BackupJob(repository=repo.path, repository_id=repo.id, status="running_prune"))
    db.commit()
    assert lanes.legacy_running_exclusive(db, repo.id) is True
    op = enqueue(db, "history_index", repository_id=repo.id)
    assert lanes.can_start(db, op, settings) is False


@pytest.mark.unit
def test_legacy_completed_check_does_not_block(db, repo, settings):
    db.add(CheckJob(repository_id=repo.id, repository_path=repo.path, status="completed"))
    db.commit()
    assert lanes.legacy_running_exclusive(db, repo.id) is False


@pytest.mark.unit
def test_index_kind_waits_without_bypass_and_runs_with_bypass(db, repo, settings):
    _running(db, "history_index", repo)
    op = enqueue(db, "stats", repository_id=repo.id)
    assert lanes.can_start(db, op, settings) is False
    settings.bypass_lock_on_list = True
    db.commit()
    assert lanes.can_start(db, op, settings) is True
    settings.bypass_lock_on_list = False
    repo.bypass_lock = True
    db.commit()
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_index_workers_limit(db, repo, settings):
    settings.index_workers = 1
    db.commit()
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add(other)
    db.commit()
    _running(db, "stats", repo)
    op = enqueue(db, "stats", repository_id=other.id)
    assert lanes.global_slot_available(db, op, settings) is False
    settings.index_workers = 2
    db.commit()
    assert lanes.global_slot_available(db, op, settings) is True


@pytest.mark.unit
def test_pause_only_affects_followup_and_reconcile(db, repo, settings):
    settings.background_paused = True
    db.commit()
    followup = enqueue(db, "stats", repository_id=repo.id, trigger="followup")
    reconcile = enqueue(db, "stats", repository_id=repo.id, trigger="reconcile")
    manual = enqueue(db, "stats", repository_id=repo.id, trigger="manual")
    assert lanes.can_start(db, followup, settings) is False
    assert lanes.can_start(db, reconcile, settings) is False
    assert lanes.can_start(db, manual, settings) is True


@pytest.mark.unit
def test_backup_limits_by_trigger(db, repo, settings):
    settings.max_concurrent_backups = 1
    settings.max_concurrent_scheduled_backups = 1
    db.commit()
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add(other)
    db.commit()
    _running(db, "backup", repo, trigger="manual")
    manual = enqueue(db, "backup", repository_id=other.id, trigger="manual")
    scheduled = enqueue(db, "backup", repository_id=other.id, trigger="schedule")
    assert lanes.global_slot_available(db, manual, settings) is False
    assert lanes.global_slot_available(db, scheduled, settings) is True


@pytest.mark.unit
def test_system_kind_has_no_lane(db, settings):
    op = enqueue(db, "package_install", repository_id=None)
    assert lanes.can_start(db, op, settings) is True


@pytest.mark.unit
def test_defaults_when_settings_row_missing(db, repo):
    op = enqueue(db, "stats", repository_id=repo.id)
    assert lanes.can_start(db, op, None) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_lanes.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/lanes.py
"""Per-repository lanes and global limits (spec sections 7.2 and 7.3)."""

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.database.models import (
    BackupJob,
    CheckJob,
    CompactJob,
    DeleteArchiveJob,
    Operation,
    PruneJob,
    Repository,
    RepositoryWipeJob,
    SystemSettings,
)
from app.services.operations.vocab import INDEX_KINDS, KINDS, is_exclusive

LEGACY_RUNNING_STATUSES = ("running", "running_prune", "running_compact")

_EXCLUSIVE_KINDS = tuple(k for k, spec in KINDS.items() if spec.exclusive)

_DEFAULTS = {
    "max_concurrent_backups": 1,
    "max_concurrent_scheduled_backups": 2,
    "max_concurrent_scheduled_checks": 4,
    "index_workers": 2,
    "background_paused": False,
    "bypass_lock_on_list": False,
}


def _setting(settings: Optional[SystemSettings], name: str):
    value = getattr(settings, name, None) if settings is not None else None
    return _DEFAULTS[name] if value is None else value


def legacy_running_exclusive(db: Session, repository_id: int) -> bool:
    """True while a legacy job table shows exclusive work running on the
    repository. Deleted in phase 9 once every kind lives in operations."""
    if (
        db.query(BackupJob.id)
        .filter(BackupJob.repository_id == repository_id,
                BackupJob.status.in_(LEGACY_RUNNING_STATUSES))
        .first()
    ):
        return True
    for model in (CheckJob, PruneJob, CompactJob, DeleteArchiveJob, RepositoryWipeJob):
        if (
            db.query(model.id)
            .filter(model.repository_id == repository_id, model.status == "running")
            .first()
        ):
            return True
    return False


def running_exclusive_operation(
    db: Session, repository_id: int, *, exclude_id: Optional[int] = None
) -> bool:
    q = db.query(Operation.id).filter(
        Operation.repository_id == repository_id,
        Operation.status == "running",
        Operation.kind.in_(_EXCLUSIVE_KINDS),
    )
    if exclude_id is not None:
        q = q.filter(Operation.id != exclude_id)
    return q.first() is not None


def lane_free(db: Session, repository_id: int, *, exclude_id: Optional[int] = None) -> bool:
    if running_exclusive_operation(db, repository_id, exclude_id=exclude_id):
        return False
    return not legacy_running_exclusive(db, repository_id)


def running_count(
    db: Session,
    *,
    kind: Optional[str] = None,
    kinds: Optional[Iterable[str]] = None,
    trigger: Optional[str] = None,
    triggers: Optional[Iterable[str]] = None,
    category: Optional[str] = None,
) -> int:
    q = db.query(Operation.id).filter(Operation.status == "running")
    if kind is not None:
        q = q.filter(Operation.kind == kind)
    if kinds is not None:
        q = q.filter(Operation.kind.in_(tuple(kinds)))
    if trigger is not None:
        q = q.filter(Operation.trigger == trigger)
    if triggers is not None:
        q = q.filter(Operation.trigger.in_(tuple(triggers)))
    if category is not None:
        q = q.filter(Operation.category == category)
    return q.count()


def global_slot_available(db: Session, op: Operation, settings: Optional[SystemSettings]) -> bool:
    if op.kind == "backup":
        if op.trigger == "schedule":
            limit = _setting(settings, "max_concurrent_scheduled_backups")
            return running_count(db, kind="backup", trigger="schedule") < limit
        limit = _setting(settings, "max_concurrent_backups")
        non_scheduled = ("manual", "plan", "import", "retry", "followup", "reconcile")
        return running_count(db, kind="backup", triggers=non_scheduled) < limit
    if op.kind == "check" and op.trigger == "schedule":
        limit = _setting(settings, "max_concurrent_scheduled_checks")
        return running_count(db, kind="check", trigger="schedule") < limit
    if op.kind in INDEX_KINDS:
        return running_count(db, kinds=INDEX_KINDS) < _setting(settings, "index_workers")
    return True


def can_start(db: Session, op: Operation, settings: Optional[SystemSettings]) -> bool:
    if _setting(settings, "background_paused") and op.trigger in ("followup", "reconcile"):
        return False
    if not global_slot_available(db, op, settings):
        return False
    if op.repository_id is None:
        return True
    if is_exclusive(op.kind):
        return lane_free(db, op.repository_id, exclude_id=op.id)
    if op.kind in INDEX_KINDS:
        if lane_free(db, op.repository_id, exclude_id=op.id):
            return True
        repository = db.get(Repository, op.repository_id)
        repo_bypass = bool(repository.bypass_lock) if repository is not None else False
        return repo_bypass or bool(_setting(settings, "bypass_lock_on_list"))
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_lanes.py -q -p no:cacheprovider`
Expected: 11 passed

---

### Task 7: Runner, context, dispatch, follow-ups, cancellation, recovery

**Files:**
- Create: `app/services/operations/executors/__init__.py`
- Create: `app/services/operations/runner.py`
- Test: `tests/unit/test_operations_runner.py`

**Interfaces:**
- Consumes: `lanes.can_start`, `followups.chain_for`, `enqueue.enqueue_chain`, `vocab`, `models.serialize_operation`, `app.utils.process_utils.is_process_alive`, `app.config.settings.data_dir`.
- Produces in `executors/__init__.py`:
  - `Executor = Callable[["OperationContext"], Awaitable[Optional["Outcome"]]]`
  - `REGISTRY: dict[str, Executor]` (empty here; Task 9 registers the index executors)
  - `register(kind: str, executor: Executor) -> None`, `get_executor(kind) -> Executor | None`, `registered_kinds() -> set[str]`
- Produces in `runner.py`:
  - `@dataclass Outcome(status: str = "completed", result: Optional[dict] = None, skip_reason: Optional[str] = None, error_message: Optional[str] = None)`; `status` must be one of completed, completed_with_warnings, skipped, failed.
  - `class OperationContext`: attributes `operation_id: int`, `repository_id: Optional[int]`, `kind: str`, `params: dict`, `db: Session` (a session the executor may use and must not close); methods `async progress(*, percent=None, current=None, total=None, message=None) -> None` (writes to the row at most once per second per operation, always writes when `current == total`, then broadcasts `operation.progress`), `log(line: str) -> None` (appends `line + "\n"` to `log_file_path`, creating the file and parent directory on first call, and sets `operation.log_file_path` the first time), `cancelled() -> bool`.
  - `class OperationRunner`:
    - `__init__(self, *, session_factory=None, registry=None, poll_interval: float = 5.0)`; `session_factory` defaults to `app.database.database.SessionLocal` (import lazily inside `__init__`), `registry` defaults to `executors.REGISTRY`.
    - `wake()`: sets the internal `asyncio.Event` if a loop is running, else no-op.
    - `async tick() -> int`: one scheduling pass; returns the number of operations dispatched.
    - `async run_operation(operation_id: int) -> None`: executes one operation to completion (used by `tick` via `asyncio.create_task`, and directly by tests).
    - `async start()`: loop until `stop()`; each iteration awaits `wake` or the poll timeout, then `tick()`.
    - `stop()`.
    - `async request_cancel(operation_id: int) -> bool`: queued rows become `cancelled` immediately; running rows get a cancel flag and their task is cancelled after the executor observes the flag or immediately if it never checks (use `task.cancel()` after setting the flag; the `CancelledError` handler marks the row `cancelled`). Returns False for terminal rows.
    - `recover_on_startup(db) -> dict`: spec 7.6; returns `{"requeued": n, "failed": n, "kept": n}`.
    - `running_tasks: dict[int, asyncio.Task]`, `cancel_requested: set[int]`.
  - `operation_runner = OperationRunner()` module singleton.

Tick algorithm (spec 7.1), inside one session:

1. `settings = db.query(SystemSettings).first()`.
2. `queued = db.query(Operation).filter(Operation.status == "queued").order_by(Operation.priority.asc(), Operation.created_at.asc(), Operation.id.asc()).all()`.
3. For each `op`: if `op.id in self.running_tasks` skip. If `op.depends_on_id` is set, load the dependency. If it is missing or its status is in `("failed", "cancelled", "skipped")`, set `op.status = "skipped"`, `op.skip_reason = "dependency_failed"`, `op.completed_at = utc_now()`, commit, broadcast `operation.updated`, and continue. If the dependency is not in `SUCCESS_STATUSES`, continue (not eligible yet). If `get_executor(op.kind)` is None, set `op.status = "skipped"`, `op.skip_reason = "executor_unavailable"`, `op.completed_at = utc_now()`, commit, broadcast, continue.
4. If `can_start(db, op, settings)`: set `status = "running"`, `started_at = utc_now()`, commit, broadcast, `self.running_tasks[op.id] = asyncio.create_task(self.run_operation(op.id))`, increment dispatched. Do not stop after the first dispatch; keep evaluating the remaining candidates, because `can_start` reads the row just committed and will see the new running state.
5. Return dispatched.

`run_operation(operation_id)`:

1. Open a new session, load the row; return if missing or not running.
2. Build `OperationContext`. Call the executor inside `try`.
3. Outcome handling: `None` or `Outcome()` means completed. `Outcome(status="skipped")` sets `skip_reason`. `Outcome(status="failed")` sets `error_message`. An exception sets `failed` with `error_message = str(exc)` and logs the traceback with `logger.exception`. `asyncio.CancelledError` sets `cancelled` and re-raises after committing. In every case set `completed_at`, store `result`, commit, broadcast `operation.updated`.
4. On success (`SUCCESS_STATUSES`) and `op.trigger != "followup"` or any trigger: create follow-ups with `enqueue_chain(db, chain_for(op.kind, available=registered_kinds()), repository_id=op.repository_id, trigger="followup", run_id=op.run_id, depends_on_id=op.id, triggered_by_user_id=op.triggered_by_user_id, scheduled_job_id=op.scheduled_job_id, backup_plan_run_id=op.backup_plan_run_id)`. Follow-ups of follow-ups are fine because index kinds have empty chains.
5. `finally`: remove from `running_tasks` and `cancel_requested`, close the session, `self.wake()`.

`recover_on_startup(db)`:

- For each `running` row: if `op.kind in INDEX_KINDS`: set `queued`, clear `started_at`, `process_pid`, `process_start_time`, `progress_*`; count `requeued`. Else if `op.process_pid` and `is_process_alive(op.process_pid, int(op.process_start_time or 0))`: leave it, count `kept`. Else set `failed`, `error_message = "interrupted by restart"`, `completed_at = utc_now()`; count `failed`. Commit once at the end. The lock-break step for local repositories is not needed in phase 1 because no exclusive Borg kind has an executor yet; phase 5 adds it when maintenance kinds migrate.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_runner.py
import asyncio
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, SystemSettings
from app.services.operations import executors
from app.services.operations.enqueue import enqueue, enqueue_chain
from app.services.operations.runner import OperationContext, OperationRunner, Outcome


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def repo(db):
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


@pytest.fixture()
def registry():
    return {}


@pytest.fixture()
def runner(session_factory, registry, monkeypatch, tmp_path):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return OperationRunner(session_factory=session_factory, registry=registry, poll_interval=0.01)


async def _drain(runner, rounds=20):
    for _ in range(rounds):
        await runner.tick()
        if runner.running_tasks:
            await asyncio.gather(*list(runner.running_tasks.values()), return_exceptions=True)
        await asyncio.sleep(0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dispatch_order_priority_then_age(db, repo, runner, registry):
    order = []

    async def record(ctx: OperationContext):
        order.append(ctx.operation_id)
        return Outcome()

    registry["stats"] = record
    late_high = enqueue(db, "stats", repository_id=repo.id, priority=20)
    early_low = enqueue(db, "stats", repository_id=repo.id, priority=0)
    await _drain(runner)
    assert order == [early_low.id, late_high.id]
    db.expire_all()
    assert {o.status for o in db.query(Operation)} == {"completed"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependency_gating_and_failure_skips_chain(db, repo, runner, registry):
    async def fail(ctx):
        raise RuntimeError("boom")

    async def ok(ctx):
        return Outcome()

    registry["stats"] = fail
    registry["archive_sync"] = ok
    chain = enqueue_chain(db, ["stats", "archive_sync"], repository_id=repo.id, trigger="manual")
    await _drain(runner)
    db.expire_all()
    first, second = (db.get(Operation, c.id) for c in chain)
    assert first.status == "failed"
    assert first.error_message == "boom"
    assert second.status == "skipped"
    assert second.skip_reason == "dependency_failed"
    assert second.completed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependency_waits_for_success(db, repo, runner, registry):
    seen = []

    async def ok(ctx):
        seen.append(ctx.kind)
        return Outcome()

    registry["stats"] = ok
    registry["archive_sync"] = ok
    enqueue_chain(db, ["stats", "archive_sync"], repository_id=repo.id, trigger="manual")
    dispatched = await runner.tick()
    assert dispatched == 1
    await asyncio.gather(*runner.running_tasks.values())
    await runner.tick()
    await asyncio.gather(*runner.running_tasks.values())
    assert seen == ["stats", "archive_sync"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_executor_is_skipped(db, repo, runner, registry):
    op = enqueue(db, "history_index", repository_id=repo.id)
    await runner.tick()
    db.expire_all()
    op = db.get(Operation, op.id)
    assert op.status == "skipped"
    assert op.skip_reason == "executor_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_followups_created_on_success_only_for_registered_kinds(db, repo, runner, registry):
    async def ok(ctx):
        return Outcome()

    registry["import_connect"] = ok
    registry["stats"] = ok
    registry["archive_sync"] = ok
    parent = enqueue(db, "import_connect", repository_id=repo.id, trigger="import")
    await _drain(runner)
    db.expire_all()
    rows = db.query(Operation).order_by(Operation.id).all()
    assert [r.kind for r in rows] == ["import_connect", "stats", "archive_sync"]
    assert rows[1].depends_on_id == parent.id
    assert rows[2].depends_on_id == rows[1].id
    assert {r.run_id for r in rows} == {parent.run_id}
    assert rows[1].trigger == "followup" and rows[1].priority == 10
    assert {r.status for r in rows} == {"completed"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_followups_on_failure(db, repo, runner, registry):
    async def fail(ctx):
        return Outcome(status="failed", error_message="nope")

    registry["import_connect"] = fail
    enqueue(db, "import_connect", repository_id=repo.id, trigger="import")
    await _drain(runner)
    db.expire_all()
    assert db.query(Operation).count() == 1
    assert db.query(Operation).first().error_message == "nope"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_lane_blocks_second_exclusive_until_first_finishes(db, repo, runner, registry):
    gate = asyncio.Event()

    async def wait(ctx):
        await gate.wait()
        return Outcome()

    registry["history_index"] = wait
    enqueue(db, "history_index", repository_id=repo.id)
    enqueue(db, "history_index", repository_id=repo.id)
    assert await runner.tick() == 1
    assert await runner.tick() == 0
    gate.set()
    await asyncio.gather(*runner.running_tasks.values())
    assert await runner.tick() == 1
    await asyncio.gather(*runner.running_tasks.values())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_queued_and_running(db, repo, runner, registry):
    started = asyncio.Event()

    async def slow(ctx):
        started.set()
        while not ctx.cancelled():
            await asyncio.sleep(0.01)
        return Outcome(status="skipped", skip_reason="cancelled_by_user")

    registry["stats"] = slow
    queued = enqueue(db, "stats", repository_id=repo.id, priority=5)
    running = enqueue(db, "stats", repository_id=repo.id, priority=0)
    await runner.tick()
    await started.wait()
    assert await runner.request_cancel(queued.id) is True
    assert await runner.request_cancel(running.id) is True
    await asyncio.gather(*runner.running_tasks.values(), return_exceptions=True)
    db.expire_all()
    assert db.get(Operation, queued.id).status == "cancelled"
    assert db.get(Operation, running.id).status == "cancelled"
    assert await runner.request_cancel(queued.id) is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_progress_and_log(db, repo, runner, registry, tmp_path):
    async def work(ctx):
        ctx.log("hello")
        await ctx.progress(current=1, total=2, message="half")
        await ctx.progress(current=2, total=2, message="done")
        return Outcome(result={"n": 2})

    registry["stats"] = work
    op = enqueue(db, "stats", repository_id=repo.id)
    await _drain(runner)
    db.expire_all()
    op = db.get(Operation, op.id)
    assert op.result == {"n": 2}
    assert op.progress_current == 2 and op.progress_total == 2
    assert op.progress_message == "done"
    assert op.log_file_path and op.log_file_path.endswith(f"operation_{op.id}.log")
    assert open(op.log_file_path).read() == "hello\n"


@pytest.mark.unit
def test_recover_on_startup(db, repo, runner, monkeypatch):
    idx = enqueue(db, "stats", repository_id=repo.id)
    idx.status = "running"
    idx.started_at = datetime(2026, 9, 1)
    idx.progress_current = 3
    dead = enqueue(db, "check", repository_id=repo.id)
    dead.status = "running"
    dead.process_pid = 4242
    dead.process_start_time = 1.0
    alive = enqueue(db, "compact", repository_id=repo.id)
    alive.status = "running"
    alive.process_pid = 4343
    alive.process_start_time = 2.0
    queued = enqueue(db, "stats", repository_id=repo.id)
    db.commit()
    monkeypatch.setattr(
        "app.services.operations.runner.is_process_alive",
        lambda pid, start: pid == 4343,
    )
    counts = runner.recover_on_startup(db)
    assert counts == {"requeued": 1, "failed": 1, "kept": 1}
    db.expire_all()
    assert db.get(Operation, idx.id).status == "queued"
    assert db.get(Operation, idx.id).started_at is None
    assert db.get(Operation, idx.id).progress_current is None
    assert db.get(Operation, dead.id).status == "failed"
    assert db.get(Operation, dead.id).error_message == "interrupted by restart"
    assert db.get(Operation, alive.id).status == "running"
    assert db.get(Operation, queued.id).status == "queued"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_loop_dispatches_and_stops(db, repo, runner, registry):
    done = asyncio.Event()

    async def ok(ctx):
        done.set()
        return Outcome()

    registry["stats"] = ok
    enqueue(db, "stats", repository_id=repo.id)
    task = asyncio.create_task(runner.start())
    await asyncio.wait_for(done.wait(), timeout=2)
    runner.stop()
    runner.wake()
    await asyncio.wait_for(task, timeout=2)
```

Check `pytest.ini` for `asyncio_mode`; if it is not `auto`, the `@pytest.mark.asyncio` markers above are required and `pytest-asyncio` must already be in `requirements.txt` (search `tests/unit` for `pytest.mark.asyncio` to confirm the convention).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_runner.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the registry**

```python
# app/services/operations/executors/__init__.py
"""Executor registry: kind -> coroutine taking an OperationContext."""

from typing import TYPE_CHECKING, Awaitable, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover
    from app.services.operations.runner import OperationContext, Outcome

Executor = Callable[["OperationContext"], Awaitable[Optional["Outcome"]]]

REGISTRY: dict[str, Executor] = {}


def register(kind: str, executor: Executor) -> None:
    REGISTRY[kind] = executor


def get_executor(kind: str) -> Optional[Executor]:
    return REGISTRY.get(kind)


def registered_kinds() -> set[str]:
    return set(REGISTRY)
```

- [ ] **Step 4: Write the runner**

```python
# app/services/operations/runner.py
"""The operations runner (spec section 7): loop, lanes, dispatch, follow-ups,
cancellation, and crash recovery. One instance per process."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.database.models import Operation, SystemSettings, utc_now
from app.services.operations import executors as executor_registry
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.events import (
    broadcast_operation_progress,
    broadcast_operation_updated,
)
from app.services.operations.followups import chain_for
from app.services.operations.lanes import can_start
from app.services.operations.vocab import INDEX_KINDS, SUCCESS_STATUSES
from app.utils.process_utils import is_process_alive

logger = structlog.get_logger()

_FAILED_DEPENDENCY_STATUSES = ("failed", "cancelled", "skipped")
_OUTCOME_STATUSES = ("completed", "completed_with_warnings", "skipped", "failed")


@dataclass
class Outcome:
    status: str = "completed"
    result: Optional[dict] = None
    skip_reason: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.status not in _OUTCOME_STATUSES:
            raise ValueError(f"Invalid outcome status: {self.status!r}")


def operation_log_path(operation_id: int) -> Path:
    return Path(app_settings.data_dir) / "logs" / f"operation_{operation_id}.log"


class OperationContext:
    """What an executor gets: the row's identity, a session, progress, logs,
    and a cancellation check."""

    def __init__(self, runner: "OperationRunner", db: Session, operation: Operation):
        self._runner = runner
        self.db = db
        self.operation = operation
        self.operation_id = operation.id
        self.repository_id = operation.repository_id
        self.kind = operation.kind
        self.params = dict(operation.params or {})
        self._last_progress_write = 0.0
        self._log_handle = None

    def cancelled(self) -> bool:
        return self.operation_id in self._runner.cancel_requested

    async def progress(
        self,
        *,
        percent: Optional[float] = None,
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        now = time.monotonic()
        final = current is not None and total is not None and current >= total
        if not final and now - self._last_progress_write < 1.0:
            return
        self._last_progress_write = now
        op = self.operation
        if percent is not None:
            op.progress_percent = percent
        if current is not None:
            op.progress_current = current
        if total is not None:
            op.progress_total = total
        if message is not None:
            op.progress_message = message
        self.db.commit()
        await broadcast_operation_progress(op)

    def log(self, line: str) -> None:
        if self._log_handle is None:
            path = operation_log_path(self.operation_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = path.open("a", encoding="utf-8")
            if self.operation.log_file_path != str(path):
                self.operation.log_file_path = str(path)
                self.db.commit()
        self._log_handle.write(line + "\n")
        self._log_handle.flush()

    def close(self) -> None:
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None


class OperationRunner:
    def __init__(self, *, session_factory=None, registry=None, poll_interval: float = 5.0):
        if session_factory is None:
            from app.database.database import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory
        self._registry = registry if registry is not None else executor_registry.REGISTRY
        self._poll_interval = poll_interval
        self._wake: Optional[asyncio.Event] = None
        self._stopped = False
        self.running_tasks: dict[int, asyncio.Task] = {}
        self.cancel_requested: set[int] = set()

    # -- registry helpers (respect an injected registry in tests) ------------

    def _get_executor(self, kind: str):
        return self._registry.get(kind)

    def _registered_kinds(self) -> set[str]:
        return set(self._registry)

    # -- loop ------------------------------------------------------------------

    def _event(self) -> asyncio.Event:
        if self._wake is None:
            self._wake = asyncio.Event()
        return self._wake

    def wake(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        self._event().set()

    def stop(self) -> None:
        self._stopped = True

    async def start(self) -> None:
        self._stopped = False
        logger.info("Operations runner started", poll_interval=self._poll_interval)
        while not self._stopped:
            try:
                await self.tick()
            except Exception as exc:  # keep the loop alive
                logger.error("Operations runner tick failed", error=str(exc))
            try:
                await asyncio.wait_for(self._event().wait(), timeout=self._poll_interval)
            except asyncio.TimeoutError:
                pass
            self._event().clear()
        logger.info("Operations runner stopped")

    # -- scheduling ------------------------------------------------------------

    async def tick(self) -> int:
        dispatched = 0
        db: Session = self._session_factory()
        try:
            system_settings = db.query(SystemSettings).first()
            queued = (
                db.query(Operation)
                .filter(Operation.status == "queued")
                .order_by(Operation.priority.asc(), Operation.created_at.asc(), Operation.id.asc())
                .all()
            )
            for op in queued:
                if op.id in self.running_tasks:
                    continue
                if op.depends_on_id is not None:
                    dependency = db.get(Operation, op.depends_on_id)
                    if dependency is None or dependency.status in _FAILED_DEPENDENCY_STATUSES:
                        await self._skip(db, op, "dependency_failed")
                        continue
                    if dependency.status not in SUCCESS_STATUSES:
                        continue
                if self._get_executor(op.kind) is None:
                    await self._skip(db, op, "executor_unavailable")
                    continue
                if not can_start(db, op, system_settings):
                    continue
                op.status = "running"
                op.started_at = utc_now()
                db.commit()
                await broadcast_operation_updated(op, db)
                self.running_tasks[op.id] = asyncio.create_task(self.run_operation(op.id))
                dispatched += 1
        finally:
            db.close()
        return dispatched

    async def _skip(self, db: Session, op: Operation, reason: str) -> None:
        op.status = "skipped"
        op.skip_reason = reason
        op.completed_at = utc_now()
        db.commit()
        await broadcast_operation_updated(op, db)

    # -- execution -------------------------------------------------------------

    async def run_operation(self, operation_id: int) -> None:
        db: Session = self._session_factory()
        ctx: Optional[OperationContext] = None
        try:
            op = db.get(Operation, operation_id)
            if op is None or op.status != "running":
                return
            executor = self._get_executor(op.kind)
            ctx = OperationContext(self, db, op)
            outcome: Optional[Outcome]
            try:
                outcome = await executor(ctx)
            except asyncio.CancelledError:
                op.status = "cancelled"
                op.completed_at = utc_now()
                db.commit()
                await broadcast_operation_updated(op, db)
                raise
            except Exception as exc:
                logger.exception("Operation failed", operation_id=op.id, kind=op.kind)
                outcome = Outcome(status="failed", error_message=str(exc) or exc.__class__.__name__)
            if outcome is None:
                outcome = Outcome()
            if operation_id in self.cancel_requested and outcome.status != "failed":
                op.status = "cancelled"
            else:
                op.status = outcome.status
            op.result = outcome.result
            op.skip_reason = outcome.skip_reason
            op.error_message = outcome.error_message
            op.completed_at = utc_now()
            db.commit()
            await broadcast_operation_updated(op, db)
            if op.status in SUCCESS_STATUSES:
                kinds = chain_for(op.kind, available=self._registered_kinds())
                if kinds:
                    enqueue_chain(
                        db, kinds,
                        repository_id=op.repository_id, trigger="followup",
                        run_id=op.run_id, depends_on_id=op.id,
                        triggered_by_user_id=op.triggered_by_user_id,
                        scheduled_job_id=op.scheduled_job_id,
                        backup_plan_run_id=op.backup_plan_run_id,
                    )
        finally:
            if ctx is not None:
                ctx.close()
            db.close()
            self.running_tasks.pop(operation_id, None)
            self.cancel_requested.discard(operation_id)
            self.wake()

    # -- cancellation ----------------------------------------------------------

    async def request_cancel(self, operation_id: int) -> bool:
        db: Session = self._session_factory()
        try:
            op = db.get(Operation, operation_id)
            if op is None:
                return False
            if op.status == "queued":
                op.status = "cancelled"
                op.completed_at = utc_now()
                db.commit()
                await broadcast_operation_updated(op, db)
                return True
            if op.status == "running":
                self.cancel_requested.add(operation_id)
                return True
            return False
        finally:
            db.close()

    # -- recovery --------------------------------------------------------------

    def recover_on_startup(self, db: Session) -> dict:
        counts = {"requeued": 0, "failed": 0, "kept": 0}
        for op in db.query(Operation).filter(Operation.status == "running").all():
            if op.kind in INDEX_KINDS:
                op.status = "queued"
                op.started_at = None
                op.process_pid = None
                op.process_start_time = None
                op.progress_percent = None
                op.progress_current = None
                op.progress_total = None
                op.progress_message = None
                counts["requeued"] += 1
            elif op.process_pid and is_process_alive(op.process_pid, int(op.process_start_time or 0)):
                counts["kept"] += 1
            else:
                op.status = "failed"
                op.error_message = "interrupted by restart"
                op.completed_at = utc_now()
                counts["failed"] += 1
        db.commit()
        logger.info("Operations recovery completed", **counts)
        return counts


operation_runner = OperationRunner()
```

Two notes for the implementer. First, the runner imports `events.py`, which Task 8 creates; write Task 8's module before running this task's tests, or temporarily stub the two broadcast coroutines as no-ops and replace them in Task 8. Second, the running-cancel test relies on the executor polling `ctx.cancelled()`; `request_cancel` deliberately does not call `task.cancel()` so that Borg-backed executors in later phases can terminate their child process cleanly before returning. Executors that never poll are documented as not cancellable while running.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_runner.py -q -p no:cacheprovider`
Expected: 12 passed

---

### Task 8: SSE events

**Files:**
- Create: `app/services/operations/events.py`
- Test: `tests/unit/test_operations_events.py`

**Interfaces:**
- Consumes: `app.api.events.event_manager.broadcast_event(event_type, data)`, `models.serialize_operation`, `app.utils.datetime_utils.serialize_datetime`.
- Produces:
  - `async broadcast_operation_updated(op: Operation, db: Optional[Session] = None) -> None`: event type `operation.updated`, data is `serialize_operation(op, repository_name=..., repository_path=...)` with datetimes serialized via `serialize_datetime`; repository name and path are looked up with `db.get(Repository, op.repository_id)` when `db` is given.
  - `async broadcast_operation_progress(op: Operation) -> None`: event type `operation.progress`, data `{"id", "progress_percent", "progress_current", "progress_total", "progress_message"}`.
  - Both swallow and log exceptions from the event manager so a broken SSE client never fails an operation.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_events.py
from datetime import datetime

import pytest

from app.database.models import Operation
from app.services.operations import events as op_events


class _Manager:
    def __init__(self):
        self.calls = []

    async def broadcast_event(self, event_type, data, user_id=None):
        self.calls.append((event_type, data))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_updated_serializes_datetimes(monkeypatch):
    manager = _Manager()
    monkeypatch.setattr(op_events, "event_manager", manager)
    op = Operation(id=7, repository_id=None, kind="stats", category="index", run_id="r",
                   status="completed", started_at=datetime(2026, 9, 3, 12, 0, 0),
                   created_at=datetime(2026, 9, 3, 11, 59, 0))
    await op_events.broadcast_operation_updated(op)
    event_type, data = manager.calls[0]
    assert event_type == "operation.updated"
    assert data["id"] == 7
    assert data["kind"] == "stats"
    assert isinstance(data["started_at"], str)
    assert data["completed_at"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_progress_payload(monkeypatch):
    manager = _Manager()
    monkeypatch.setattr(op_events, "event_manager", manager)
    op = Operation(id=3, kind="archive_sync", category="index", run_id="r",
                   progress_current=2, progress_total=5, progress_message="x")
    await op_events.broadcast_operation_progress(op)
    assert manager.calls == [(
        "operation.progress",
        {"id": 3, "progress_percent": None, "progress_current": 2,
         "progress_total": 5, "progress_message": "x"},
    )]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_broadcast_errors_are_swallowed(monkeypatch):
    class Broken:
        async def broadcast_event(self, *a, **k):
            raise RuntimeError("no clients")

    monkeypatch.setattr(op_events, "event_manager", Broken())
    op = Operation(id=1, kind="stats", category="index", run_id="r")
    await op_events.broadcast_operation_updated(op)
    await op_events.broadcast_operation_progress(op)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_events.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/events.py
"""Server-sent events for operations (spec section 9.4)."""

from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.api.events import event_manager
from app.database.models import Operation, Repository
from app.services.operations.models import serialize_operation
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()


def _jsonable(data: dict) -> dict:
    return {
        key: serialize_datetime(value) if isinstance(value, datetime) else value
        for key, value in data.items()
    }


async def broadcast_operation_updated(op: Operation, db: Optional[Session] = None) -> None:
    repository_name = None
    repository_path = None
    if db is not None and op.repository_id is not None:
        repository = db.get(Repository, op.repository_id)
        if repository is not None:
            repository_name = repository.name
            repository_path = repository.path
    data = _jsonable(
        serialize_operation(op, repository_name=repository_name, repository_path=repository_path)
    )
    try:
        await event_manager.broadcast_event("operation.updated", data)
    except Exception as exc:
        logger.warning("Failed to broadcast operation.updated", operation_id=op.id, error=str(exc))


async def broadcast_operation_progress(op: Operation) -> None:
    data = {
        "id": op.id,
        "progress_percent": op.progress_percent,
        "progress_current": op.progress_current,
        "progress_total": op.progress_total,
        "progress_message": op.progress_message,
    }
    try:
        await event_manager.broadcast_event("operation.progress", data)
    except Exception as exc:
        logger.warning("Failed to broadcast operation.progress", operation_id=op.id, error=str(exc))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_events.py tests/unit/test_operations_runner.py -q -p no:cacheprovider`
Expected: all passed

---

### Task 9: Index executors `stats` and `archive_sync`

**Files:**
- Create: `app/services/operations/executors/index.py`
- Modify: `app/services/operations/executors/__init__.py` (register at import time, see step 3)
- Test: `tests/unit/test_operations_index_executors.py`

**Interfaces:**
- Consumes: `BorgRouter(repository).list_archives(env=...)`, `BorgRouter(repository).calculate_total_size_bytes(env=, info_timeout=, use_bypass_lock=, temp_key_file=)`, `app.api.repositories._prepare_repository_borg_env`, `_repository_stats_borg_env`, `_parse_borg_archive_time`, `get_operation_timeouts`, `format_bytes`, `_agent_result_archives`; `app.utils.borg_env.cleanup_temp_key_file`; `app.services.repository_executor.is_agent_executor`, `queue_agent_repository_operation_job`, `wait_for_agent_repository_operation_job`; `app.services.agent_job_dispatcher.dispatch_agent_job_best_effort`; `app.services.repository_command_lock.run_serialized_repository_command`; `app.config.settings.index_archive_info_per_run`.
- Produces:
  - `async run_stats(ctx) -> Outcome`
  - `async run_archive_sync(ctx) -> Outcome`
  - `archive_fields_from_listing(entry: dict, borg_version: int) -> Optional[dict]`: pure; returns `{"borg_id", "name", "series", "start", "end", "hostname", "username", "comment"}` or `None` when `id` or `name`/`archive` or a parseable time is missing. Borg 1 `borg list --json` entries carry `archive`, `name`, `id`, `start`, `time`; Borg 2 `repo-list --json` entries carry `name`, `id`, `time`, and may carry `hostname`, `username`, `comment`. `start = start or time`. `series = name` for Borg 2, `"default"` for Borg 1 (phase 2 replaces this with spec 6.6).
  - `apply_listing(db, repository, entries: list[dict]) -> tuple[list[Archive], list[int]]`: upserts by `(repository_id, borg_id)`, updates `last_seen_at`, `name`, `series`, `start`, `end`, `hostname`, `username`, `comment` on existing rows, returns `(new_rows, removed_archive_ids)` where removed ids are `archives` rows for the repository whose `borg_id` is not in the listing. Does not delete anything.
  - `async list_archives_for_repository(db, repository, env) -> list[dict]`: agent path or `BorgRouter.list_archives`.
  - `async fill_archive_info(db, repository, archives: list[Archive], env, *, limit: int) -> int`: per-archive `borg info` for up to `limit` archives, oldest `start` first, filling `nfiles`, `original_size`, `compressed_size`, `deduplicated_size`, `end`, `duration_seconds` from `archives[0]["stats"]` and `archives[0]["end"]`/`duration` in the info JSON. Uses `BorgRouter(repository)` helpers: Borg 1 `borg.info_archive(repository.path, name, ...)`, Borg 2 `borg2.info_archive(repository.path, f"aid:{borg_id}", ...)`. Returns the number filled. Any per-archive failure is logged through `ctx.log` and skipped. Skipped entirely for agent repositories.

Executor behaviour:

`run_stats(ctx)`:
1. Load the repository; if missing return `Outcome(status="skipped", skip_reason="repository_missing")`.
2. If `is_agent_executor(repository)`: return `Outcome(result={"unique_csize": None, "reason": "agent_size_unsupported"})` without touching `total_size`.
3. Build env with `_prepare_repository_borg_env`, compute `use_bypass_lock` exactly as `update_repository_stats` does, call `calculate_total_size_bytes` inside `run_serialized_repository_command(repository.id, ..., scope="metadata")`, write `repository.total_size = format_bytes(n)` when `n > 0`, commit, `cleanup_temp_key_file` in `finally`.
4. Return `Outcome(result={"unique_csize": n})`.

`run_archive_sync(ctx)`:
1. Load the repository; skip as above if missing.
2. Build env; `entries = await list_archives_for_repository(...)` inside the metadata lock (agent path does not take the lock).
3. `new_rows, removed_ids = apply_listing(db, repository, entries)`.
4. `filled = await fill_archive_info(db, repository, new_rows, env, limit=settings.index_archive_info_per_run)` (agent repos: 0).
5. `repository.archive_count = count of archives rows for the repository`; `repository.last_backup = max(start)` over rows or unchanged when there are none; commit.
6. `ctx.progress(current=len(entries), total=len(entries), message=f"{len(entries)} archives")`.
7. Return `Outcome(result={"listed": len(entries), "new": len(new_rows), "info_filled": filled, "removed_archive_ids": removed_ids})`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_index_executors.py
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, Base, Repository, SystemSettings
from app.services.operations.executors import index as index_exec
from app.services.operations.runner import Outcome


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
def repo(db):
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4", borg_version=1)
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


def _ctx(db, repo, kind="archive_sync"):
    progress = AsyncMock()
    return SimpleNamespace(
        db=db, repository_id=repo.id, operation_id=1, kind=kind, params={},
        progress=progress, log=lambda line: None, cancelled=lambda: False,
    )


BORG1_ENTRY = {
    "archive": "nas-2026-09-02T02:00:00", "name": "nas-2026-09-02T02:00:00",
    "id": "aa11", "start": "2026-09-02T02:00:00.000000", "time": "2026-09-02T02:00:00.000000",
}
BORG2_ENTRY = {
    "name": "nas", "id": "bb22", "time": "2026-09-02T02:00:00.000000",
    "hostname": "nas", "username": "root", "comment": "",
}


@pytest.mark.unit
def test_archive_fields_from_listing_borg1_and_borg2():
    f1 = index_exec.archive_fields_from_listing(BORG1_ENTRY, 1)
    assert f1["borg_id"] == "aa11"
    assert f1["name"] == "nas-2026-09-02T02:00:00"
    assert f1["series"] == "default"
    assert f1["start"] == datetime(2026, 9, 2, 2, 0, 0)
    f2 = index_exec.archive_fields_from_listing(BORG2_ENTRY, 2)
    assert f2["series"] == "nas"
    assert f2["hostname"] == "nas" and f2["username"] == "root"
    assert index_exec.archive_fields_from_listing({"name": "x"}, 1) is None
    assert index_exec.archive_fields_from_listing({"id": "x", "name": "n"}, 2) is None


@pytest.mark.unit
def test_apply_listing_upserts_and_reports_removed(db, repo):
    gone = Archive(repository_id=repo.id, borg_id="old", name="old", series="default",
                   start=datetime(2026, 8, 1))
    db.add(gone)
    db.commit()
    new_rows, removed = index_exec.apply_listing(db, repo, [BORG1_ENTRY])
    assert [a.borg_id for a in new_rows] == ["aa11"]
    assert removed == [gone.id]
    assert db.query(Archive).count() == 2
    again_new, again_removed = index_exec.apply_listing(db, repo, [BORG1_ENTRY])
    assert again_new == [] and again_removed == [gone.id]
    row = db.query(Archive).filter_by(borg_id="aa11").one()
    assert row.last_seen_at >= row.first_seen_at


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_updates_repository_columns(db, repo, monkeypatch):
    monkeypatch.setattr(index_exec, "list_archives_for_repository", AsyncMock(return_value=[BORG1_ENTRY]))
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=1))
    monkeypatch.setattr(index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None))
    ctx = _ctx(db, repo)
    outcome = await index_exec.run_archive_sync(ctx)
    assert isinstance(outcome, Outcome)
    assert outcome.result == {"listed": 1, "new": 1, "info_filled": 1, "removed_archive_ids": []}
    db.refresh(repo)
    assert repo.archive_count == 1
    assert repo.last_backup == datetime(2026, 9, 2, 2, 0, 0)
    ctx.progress.assert_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_skips_missing_repository(db, repo):
    ctx = _ctx(db, repo)
    ctx.repository_id = 9999
    outcome = await index_exec.run_archive_sync(ctx)
    assert outcome.status == "skipped" and outcome.skip_reason == "repository_missing"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_writes_total_size(db, repo, monkeypatch):
    monkeypatch.setattr(index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None))
    with patch("app.core.borg_router.BorgRouter.calculate_total_size_bytes",
               new=AsyncMock(return_value=2048)):
        outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.result == {"unique_csize": 2048}
    db.refresh(repo)
    assert repo.total_size == "2.00 KB"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_stats_agent_repository_leaves_size_alone(db, repo, monkeypatch):
    repo.total_size = "keep"
    db.commit()
    monkeypatch.setattr(index_exec, "is_agent_executor", lambda repository: True)
    outcome = await index_exec.run_stats(_ctx(db, repo, kind="stats"))
    assert outcome.result == {"unique_csize": None, "reason": "agent_size_unsupported"}
    db.refresh(repo)
    assert repo.total_size == "keep"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_limits_and_orders_oldest_first(db, repo, monkeypatch):
    rows = []
    for i, day in enumerate((3, 1, 2)):
        a = Archive(repository_id=repo.id, borg_id=f"id{i}", name=f"n{i}", series="default",
                    start=datetime(2026, 9, day))
        db.add(a)
        rows.append(a)
    db.commit()
    seen = []

    async def fake_info(repository, archive_name, **kwargs):
        seen.append(archive_name)
        return {"success": True, "stdout": __import__("json").dumps({
            "archives": [{"stats": {"nfiles": 5, "original_size": 10,
                                     "compressed_size": 8, "deduplicated_size": 4},
                          "end": "2026-09-01T02:10:00.000000",
                          "duration": 600.0}]})}

    monkeypatch.setattr("app.core.borg.borg.info_archive", fake_info)
    filled = await index_exec.fill_archive_info(db, repo, rows, {}, limit=2)
    assert filled == 2
    assert seen == ["n1", "n2"]
    db.expire_all()
    oldest = db.query(Archive).filter_by(borg_id="id1").one()
    assert oldest.nfiles == 5 and oldest.deduplicated_size == 4
    assert oldest.duration_seconds == 600.0
    newest = db.query(Archive).filter_by(borg_id="id0").one()
    assert newest.nfiles is None


@pytest.mark.unit
def test_registry_has_index_kinds():
    from app.services.operations import executors
    import app.services.operations.executors.index  # noqa: F401  (registers on import)

    assert {"stats", "archive_sync"} <= executors.registered_kinds()
```

The `format_bytes` expectation `"2.00 KB"` must match `app.api.repositories.format_bytes(2048)`; run `python -c "from app.api.repositories import format_bytes; print(format_bytes(2048))"` and adjust the assertion to the real output before writing code.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_index_executors.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError` on `index`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/executors/index.py
"""Index executors: stats and archive_sync (spec sections 8.1 and 8.2).

Series inference here is the phase 1 placeholder: Borg 2 uses the archive
name (Borg 2 defines series that way); Borg 1 uses "default". Phase 2
replaces `series_for` with the full inference of spec section 6.6.
"""

import json
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.api.repositories import (
    _agent_result_archives,
    _parse_borg_archive_time,
    _prepare_repository_borg_env,
    _repository_stats_borg_env,
    format_bytes,
    get_operation_timeouts,
)
from app.config import settings
from app.core.borg_router import BorgRouter
from app.database.models import Archive, Repository, SystemSettings, utc_now
from app.services.operations import executors
from app.services.operations.runner import Outcome
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.repository_executor import is_agent_executor
from app.utils.borg_env import cleanup_temp_key_file, effective_repository_remote_path

logger = structlog.get_logger()


# -- pure helpers ---------------------------------------------------------------

def series_for(name: str, borg_version: int) -> str:
    return name if borg_version == 2 else "default"


def archive_fields_from_listing(entry: dict, borg_version: int) -> Optional[dict]:
    borg_id = entry.get("id")
    name = entry.get("name") or entry.get("archive")
    raw_time = entry.get("start") or entry.get("time")
    if not borg_id or not name or not raw_time:
        return None
    try:
        start = _parse_borg_archive_time(raw_time)
    except ValueError:
        return None
    if start is None:
        return None
    end = None
    if entry.get("end"):
        try:
            end = _parse_borg_archive_time(entry["end"])
        except ValueError:
            end = None
    return {
        "borg_id": str(borg_id),
        "name": name,
        "series": series_for(name, borg_version),
        "start": start,
        "end": end,
        "hostname": entry.get("hostname"),
        "username": entry.get("username"),
        "comment": entry.get("comment") or None,
    }


def apply_listing(db: Session, repository: Repository, entries: list[dict]) -> tuple[list[Archive], list[int]]:
    existing = {
        a.borg_id: a
        for a in db.query(Archive).filter(Archive.repository_id == repository.id).all()
    }
    seen: set[str] = set()
    new_rows: list[Archive] = []
    now = utc_now()
    for entry in entries:
        fields = archive_fields_from_listing(entry, repository.borg_version or 1)
        if fields is None:
            continue
        seen.add(fields["borg_id"])
        row = existing.get(fields["borg_id"])
        if row is None:
            row = Archive(repository_id=repository.id, first_seen_at=now, **fields)
            db.add(row)
            new_rows.append(row)
        else:
            for key, value in fields.items():
                if key == "borg_id":
                    continue
                if key == "series" and value != row.series:
                    row.history_state = "pending"
                setattr(row, key, value)
        row.last_seen_at = now
    removed = [a.id for borg_id, a in existing.items() if borg_id not in seen]
    db.commit()
    for row in new_rows:
        db.refresh(row)
    return new_rows, removed


# -- Borg access ------------------------------------------------------------------

async def list_archives_for_repository(db: Session, repository: Repository, env: dict) -> list[dict]:
    if is_agent_executor(repository):
        from app.services.agent_job_dispatcher import dispatch_agent_job_best_effort
        from app.services.repository_executor import (
            queue_agent_repository_operation_job,
            wait_for_agent_repository_operation_job,
        )

        timeouts = get_operation_timeouts(db)
        job = queue_agent_repository_operation_job(db, repository, job_kind="repository.list_archives")
        await dispatch_agent_job_best_effort(db, job, repository_id=repository.id)
        result = await wait_for_agent_repository_operation_job(
            db, job.id, timeout_seconds=timeouts["list_timeout"]
        )
        return _agent_result_archives(result)

    router = BorgRouter(repository)
    stats_env = _repository_stats_borg_env(env)
    return await run_serialized_repository_command(
        repository.id, lambda: router.list_archives(env=stats_env), scope="metadata"
    )


def _info_stats(payload: str) -> Optional[dict]:
    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError:
        return None
    archives = data.get("archives") or []
    if not archives:
        return None
    entry = archives[0]
    stats = entry.get("stats") or {}
    return {
        "nfiles": stats.get("nfiles"),
        "original_size": stats.get("original_size"),
        "compressed_size": stats.get("compressed_size"),
        "deduplicated_size": stats.get("deduplicated_size"),
        "end": entry.get("end"),
        "duration": entry.get("duration"),
    }


async def fill_archive_info(
    db: Session, repository: Repository, archives: list[Archive], env: dict, *, limit: int
) -> int:
    if is_agent_executor(repository) or limit <= 0:
        return 0
    filled = 0
    remote_path = effective_repository_remote_path(repository)
    for archive in sorted(archives, key=lambda a: a.start)[:limit]:
        try:
            if (repository.borg_version or 1) == 2:
                from app.core.borg2 import borg2

                result = await borg2.info_archive(
                    repository.path, f"aid:{archive.borg_id}",
                    passphrase=repository.passphrase, remote_path=remote_path,
                    bypass_lock=repository.bypass_lock, env=env or None,
                )
            else:
                from app.core.borg import borg

                result = await borg.info_archive(
                    repository.path, archive.name,
                    passphrase=repository.passphrase, remote_path=remote_path,
                    bypass_lock=repository.bypass_lock, env=env or None,
                )
        except Exception as exc:
            logger.warning("archive info failed", archive=archive.name, error=str(exc))
            continue
        if not result or not result.get("success"):
            continue
        info = _info_stats(result.get("stdout", ""))
        if info is None:
            continue
        archive.nfiles = info["nfiles"]
        archive.original_size = info["original_size"]
        archive.compressed_size = info["compressed_size"]
        archive.deduplicated_size = info["deduplicated_size"]
        if info["end"]:
            try:
                archive.end = _parse_borg_archive_time(info["end"])
            except ValueError:
                pass
        if info["duration"] is not None:
            archive.duration_seconds = float(info["duration"])
        filled += 1
    db.commit()
    return filled


# -- executors -------------------------------------------------------------------

def _load_repository(ctx) -> Optional[Repository]:
    if ctx.repository_id is None:
        return None
    return ctx.db.get(Repository, ctx.repository_id)


async def run_stats(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    if is_agent_executor(repository):
        return Outcome(result={"unique_csize": None, "reason": "agent_size_unsupported"})
    db = ctx.db
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        system_settings = db.query(SystemSettings).first()
        use_bypass_lock = bool(
            repository.bypass_lock or (system_settings and system_settings.bypass_lock_on_list)
        )
        timeouts = get_operation_timeouts(db)
        router = BorgRouter(repository)
        total = await run_serialized_repository_command(
            repository.id,
            lambda: router.calculate_total_size_bytes(
                env=env, info_timeout=timeouts["info_timeout"],
                use_bypass_lock=use_bypass_lock, temp_key_file=temp_key_file,
            ),
            scope="metadata",
        )
        if total and total > 0:
            repository.total_size = format_bytes(total)
            db.commit()
        ctx.log(f"repository size {total} bytes")
        return Outcome(result={"unique_csize": total})
    finally:
        cleanup_temp_key_file(temp_key_file)


async def run_archive_sync(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        entries = await list_archives_for_repository(db, repository, env)
        new_rows, removed_ids = apply_listing(db, repository, entries)
        filled = await fill_archive_info(
            db, repository, new_rows, env, limit=settings.index_archive_info_per_run
        )
        rows = db.query(Archive).filter(Archive.repository_id == repository.id).all()
        repository.archive_count = len(rows)
        if rows:
            repository.last_backup = max(a.start for a in rows)
        db.commit()
        ctx.log(f"listed {len(entries)} archives, {len(new_rows)} new, {filled} info fetched")
        await ctx.progress(current=len(entries), total=len(entries),
                           message=f"{len(entries)} archives")
        return Outcome(result={
            "listed": len(entries), "new": len(new_rows),
            "info_filled": filled, "removed_archive_ids": removed_ids,
        })
    finally:
        cleanup_temp_key_file(temp_key_file)


executors.register("stats", run_stats)
executors.register("archive_sync", run_archive_sync)
```

Then make the registry import the executors so the production runner sees them. Append to `app/services/operations/executors/__init__.py`:

```python
def load_default_executors() -> None:
    """Import executor modules for their registration side effect."""
    from app.services.operations.executors import index  # noqa: F401
```

Circular import note: `index.py` imports `app.api.repositories`, which imports a lot of the app. Keep this import inside `index.py` only, never in `runner.py` or `enqueue.py`. `load_default_executors()` is called from `app/main.py` in Task 10, not at package import time.

Also confirm `_prepare_repository_borg_env` returns `(env, temp_key_file)` and that the `datetime` returned by `_parse_borg_archive_time` is naive UTC, matching the test expectations; adjust the test's expected `start` value if the helper applies a timezone shift.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_index_executors.py -q -p no:cacheprovider`
Expected: 8 passed

---

### Task 10: Reconcile loop and application startup wiring

**Files:**
- Create: `app/services/operations/reconcile.py`
- Modify: `app/main.py` (startup event around the `stats_refresh_scheduler` block, and the router registration block)
- Delete: `app/services/stats_refresh_scheduler.py`
- Modify: `tests/unit/test_schedulers.py` (remove the `StatsRefreshScheduler` import and its tests)
- Test: `tests/unit/test_operations_reconcile.py`

**Interfaces:**
- Consumes: `enqueue.enqueue_chain`, `followups`, `executors.registered_kinds`, `SystemSettings.stats_refresh_interval_minutes`, `SystemSettings.last_stats_refresh`.
- Produces:
  - `RECONCILE_CHAIN = ("archive_sync", "history_merge", "history_index", "stats")`
  - `has_active_index_work(db, repository_id) -> bool`: any `operations` row for the repository with `category == "index"` and status in `("queued", "running")`.
  - `enqueue_reconcile_runs(db) -> int`: for every repository without active index work, `enqueue_chain(db, [k for k in RECONCILE_CHAIN if k in registered_kinds()], repository_id=..., trigger="reconcile", priority=20)`; sets `SystemSettings.last_stats_refresh = utc_now()`; returns the number of repositories enqueued.
  - `class ReconcileScheduler` with `start()` and `stop()` mirroring `StatsRefreshScheduler.start()`: reads `stats_refresh_interval_minutes` each loop, `0` disables, sleeps `interval * 60` seconds between runs, first run happens after one interval (same as the old scheduler). Loop body calls `enqueue_reconcile_runs` in a fresh `SessionLocal()`.
  - `reconcile_scheduler = ReconcileScheduler()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_operations_reconcile.py
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, SystemSettings
from app.services.operations import reconcile
from app.services.operations.enqueue import enqueue


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
def repos(db):
    a = Repository(name="a", path="/tmp/a", encryption="none", compression="lz4")
    b = Repository(name="b", path="/tmp/b", encryption="none", compression="lz4")
    db.add_all([a, b, SystemSettings()])
    db.commit()
    return a, b


@pytest.mark.unit
def test_enqueue_reconcile_runs_skips_repos_with_active_index_work(db, repos, monkeypatch):
    monkeypatch.setattr(reconcile, "registered_kinds", lambda: {"stats", "archive_sync"})
    a, b = repos
    enqueue(db, "stats", repository_id=a.id)  # queued index work on a
    count = reconcile.enqueue_reconcile_runs(db)
    assert count == 1
    rows = db.query(Operation).filter(Operation.repository_id == b.id).order_by(Operation.id).all()
    assert [r.kind for r in rows] == ["archive_sync", "stats"]
    assert all(r.trigger == "reconcile" and r.priority == 20 for r in rows)
    assert rows[1].depends_on_id == rows[0].id
    assert db.query(SystemSettings).first().last_stats_refresh is not None


@pytest.mark.unit
def test_enqueue_reconcile_runs_includes_history_kinds_when_registered(db, repos, monkeypatch):
    monkeypatch.setattr(
        reconcile, "registered_kinds",
        lambda: {"stats", "archive_sync", "history_merge", "history_index"},
    )
    a, _ = repos
    reconcile.enqueue_reconcile_runs(db)
    kinds = [r.kind for r in db.query(Operation).filter(Operation.repository_id == a.id).order_by(Operation.id)]
    assert kinds == ["archive_sync", "history_merge", "history_index", "stats"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_disabled_when_interval_zero(db, repos, monkeypatch):
    settings = db.query(SystemSettings).first()
    settings.stats_refresh_interval_minutes = 0
    db.commit()
    monkeypatch.setattr(reconcile, "SessionLocal", lambda: db)
    scheduler = reconcile.ReconcileScheduler()
    await scheduler.start()
    assert scheduler.running is False
    assert db.query(Operation).count() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_reconcile.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/reconcile.py
"""Reconcile loop (spec section 7.5). Replaces stats_refresh_scheduler:
instead of calling Borg for every repository in a loop, it enqueues one
index run per repository and lets the runner pace the work."""

import asyncio

import structlog
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import Operation, Repository, SystemSettings, utc_now
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.executors import registered_kinds
from app.services.operations.vocab import PRIORITY_RECONCILE

logger = structlog.get_logger()

RECONCILE_CHAIN = ("archive_sync", "history_merge", "history_index", "stats")
DEFAULT_INTERVAL_MINUTES = 60


def has_active_index_work(db: Session, repository_id: int) -> bool:
    return (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == repository_id,
            Operation.category == "index",
            Operation.status.in_(("queued", "running")),
        )
        .first()
        is not None
    )


def enqueue_reconcile_runs(db: Session) -> int:
    available = registered_kinds()
    kinds = [k for k in RECONCILE_CHAIN if k in available]
    if not kinds:
        return 0
    count = 0
    for repo in db.query(Repository).all():
        if has_active_index_work(db, repo.id):
            continue
        enqueue_chain(
            db, kinds, repository_id=repo.id, trigger="reconcile",
            priority=PRIORITY_RECONCILE, commit=False,
        )
        count += 1
    settings = db.query(SystemSettings).first()
    if settings is not None:
        settings.last_stats_refresh = utc_now()
    db.commit()
    logger.info("Reconcile runs enqueued", repositories=count, kinds=kinds)
    return count


class ReconcileScheduler:
    def __init__(self):
        self.running = False

    def _interval_minutes(self) -> int:
        db = SessionLocal()
        try:
            settings = db.query(SystemSettings).first()
            if settings and settings.stats_refresh_interval_minutes is not None:
                return settings.stats_refresh_interval_minutes
            return DEFAULT_INTERVAL_MINUTES
        except Exception as exc:
            logger.warning("Failed to read reconcile interval", error=str(exc))
            return DEFAULT_INTERVAL_MINUTES
        finally:
            db.close()

    def stop(self) -> None:
        self.running = False

    async def start(self) -> None:
        interval = self._interval_minutes()
        if interval <= 0:
            logger.info("Reconcile scheduler disabled (interval=0)")
            self.running = False
            return
        self.running = True
        logger.info("Reconcile scheduler started", interval_minutes=interval)
        while self.running:
            await asyncio.sleep(interval * 60)
            if not self.running:
                break
            interval = self._interval_minutes()
            if interval <= 0:
                logger.info("Reconcile disabled, stopping scheduler")
                self.running = False
                break
            db = SessionLocal()
            try:
                enqueue_reconcile_runs(db)
            except Exception as exc:
                logger.error("Reconcile run failed", error=str(exc))
            finally:
                db.close()


reconcile_scheduler = ReconcileScheduler()
```

- [ ] **Step 4: Wire startup in `app/main.py`**

Replace the block

```python
    # Start stats refresh scheduler (background task)
    from app.services.stats_refresh_scheduler import stats_refresh_scheduler

    task2 = asyncio.create_task(stats_refresh_scheduler.start())
    app.state.background_tasks.append(task2)
    logger.info("Stats refresh scheduler started")
```

with

```python
    # Operations runner: recover interrupted rows, register executors, start
    # the loop, then start the reconcile scheduler that replaces the old
    # stats refresh loop (spec sections 7.1, 7.5, 7.6).
    from app.services.operations.executors import load_default_executors
    from app.services.operations.reconcile import reconcile_scheduler
    from app.services.operations.runner import operation_runner

    load_default_executors()
    try:
        db = SessionLocal()
        try:
            operation_runner.recover_on_startup(db)
        finally:
            db.close()
    except Exception as e:
        logger.error("Operations recovery failed", error=str(e))
    task2 = asyncio.create_task(operation_runner.start())
    app.state.background_tasks.append(task2)
    task2b = asyncio.create_task(reconcile_scheduler.start())
    app.state.background_tasks.append(task2b)
    logger.info("Operations runner and reconcile scheduler started")
```

`SessionLocal` is already imported near the orphaned-jobs cleanup earlier in the startup handler; reuse that import. In the shutdown handler, after the existing task cancellation, add `operation_runner.stop()` and `reconcile_scheduler.stop()` (import them at the top of the handler the same way).

Then delete `app/services/stats_refresh_scheduler.py` and, in `tests/unit/test_schedulers.py`, remove `from app.services.stats_refresh_scheduler import StatsRefreshScheduler` and every test function that references `StatsRefreshScheduler` (search the file; they will be named with `stats_refresh`). Search the whole repo for other references: `grep -rn stats_refresh_scheduler app tests docs` must return nothing except this plan and the spec.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_operations_reconcile.py tests/unit/test_schedulers.py -q -p no:cacheprovider`
Expected: all passed, no `ImportError`

Run: `python -c "import app.main"`
Expected: imports without error

---

### Task 11: Operations API

**Files:**
- Create: `app/api/operations.py`
- Modify: `app/main.py` (import `operations` in the `from app.api import (...)` block; add `app.include_router(operations.router, prefix="/api/operations", tags=["Operations"])` next to the activity router)
- Test: `tests/unit/test_api_operations.py`

**Interfaces:**
- Consumes: `models.serialize_operation`, `runner.operation_runner.request_cancel`, `lanes.lane_free`, `lanes.running_count`, `app.core.security.get_current_admin_user`, `check_repo_access`, `app.api.auth.get_current_user`, `app.core.security.get_current_download_user`, `app.api.activity._paginate_log_text`, `app.services.log_policy.get_log_save_policy`, `job_has_logs_by_policy`.
- Produces: pydantic `OperationItem` (every key returned by `serialize_operation`, all optional except `id`, `type`, `kind`, `category`, `status`, `trigger`, `priority`, `run_id`), `OperationListResponse { items: list[OperationItem], next_cursor: Optional[int] }`, `QueueResponse { repositories: list[QueueRepository], limits: QueueLimits, paused: bool }` where `QueueRepository { repository_id, repository_name, lane_busy: bool, operations: list[OperationItem] }` and `QueueLimits { index_workers: int, index_running: int, max_concurrent_backups: int, max_concurrent_scheduled_backups: int, max_concurrent_scheduled_checks: int }`.

Routes (all under `/api/operations`):

| Route | Auth | Behaviour |
| --- | --- | --- |
| `GET /` | any user | Filters `repository_id`, `category` (repeatable), `kind` (repeatable), `status` (repeatable), `trigger` (repeatable), `run_id`, `since` (ISO datetime, on `created_at`), `limit` (default 100, max 500), `cursor` (an operation id; returns rows with `id < cursor`). Ordered by `id desc`. `next_cursor` is the last returned id when exactly `limit` rows were returned, else null. |
| `GET /queue` | any user | Rows with status in (queued, running) plus rows with `completed_at >= now - 60s`, grouped by repository (null repository grouped under `repository_id = null`, name `"System"`), each group with `lane_busy = not lane_free(db, repository_id)`. `limits` from `SystemSettings` (defaults as in Task 6) and `index_running = running_count(db, kinds=INDEX_KINDS)`. `paused = settings.background_paused`. |
| `GET /{id}` | any user | One item plus `run: list[OperationItem]` (every row sharing `run_id`, ordered by id). 404 when missing. |
| `POST /{id}/cancel` | operator on the repository, admin when no repository | Calls `operation_runner.request_cancel(id)`. 404 when missing, 409 when terminal (returns `{"key": "backend.errors.operations.alreadyFinished"}`), else `{"status": "cancel_requested"}`. |
| `POST /pause`, `POST /resume` | admin | Set `SystemSettings.background_paused` true or false, creating the settings row if missing; returns `{"paused": bool}`. `resume` calls `operation_runner.wake()`. |
| `PUT /limits` | admin | Body `{"index_workers": int}` with `1 <= index_workers <= 32`; returns `QueueLimits`. Calls `operation_runner.wake()`. |
| `GET /{id}/logs` | any user with viewer access to the repository | `offset`, `limit` (default 500). Reads `log_file_path` when present, else returns `_paginate_log_text("", ...)`. Same response shape as `/api/activity/{job_type}/{job_id}/logs`. |
| `GET /{id}/logs/download` | `get_current_download_user` | `FileResponse` of the log file, `media_type="text/plain"`, filename `operation_{id}.log`; 404 when no file. |

Every route that takes an id resolves the row with a shared helper `_get_operation_with_access(db, user, operation_id, required_role)` that loads the row, loads its repository when present, and calls `check_repo_access(db, user, repository, required_role)`; rows without a repository require admin for `operator` access and allow any user for `viewer` access. Error payloads follow the existing `{"key": "backend.errors.…"}` convention; add the keys `backend.errors.operations.notFound` and `backend.errors.operations.alreadyFinished` (no frontend translation is needed in phase 1; phase 3 adds them to the locale files).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_api_operations.py
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.database.models import Operation, Repository, SystemSettings, utc_now
from app.services.operations.enqueue import enqueue


def _repo(test_db, name="r"):
    repo = Repository(name=name, path=f"/tmp/{name}", encryption="none", compression="lz4")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _settings(test_db):
    s = test_db.query(SystemSettings).first()
    if s is None:
        s = SystemSettings()
        test_db.add(s)
        test_db.commit()
    return s


@pytest.mark.unit
class TestOperationsList:
    def test_list_filters_and_cursor(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a = enqueue(test_db, "stats", repository_id=repo.id, trigger="manual")
        b = enqueue(test_db, "archive_sync", repository_id=repo.id, trigger="reconcile")
        c = enqueue(test_db, "backup", repository_id=repo.id, trigger="schedule")
        r = test_client.get("/api/operations/?category=index", headers=admin_headers)
        assert r.status_code == 200
        assert [i["id"] for i in r.json()["items"]] == [b.id, a.id]
        r = test_client.get("/api/operations/?trigger=schedule", headers=admin_headers)
        assert [i["kind"] for i in r.json()["items"]] == ["backup"]
        r = test_client.get("/api/operations/?limit=2", headers=admin_headers)
        body = r.json()
        assert [i["id"] for i in body["items"]] == [c.id, b.id]
        assert body["next_cursor"] == b.id
        r = test_client.get(f"/api/operations/?limit=2&cursor={b.id}", headers=admin_headers)
        assert [i["id"] for i in r.json()["items"]] == [a.id]
        assert r.json()["next_cursor"] is None

    def test_list_item_shape_is_activity_superset(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        enqueue(test_db, "stats", repository_id=repo.id)
        item = test_client.get("/api/operations/", headers=admin_headers).json()["items"][0]
        for key in ("id", "type", "status", "started_at", "completed_at", "error_message",
                    "repository", "triggered_by", "has_logs", "kind", "category", "trigger",
                    "priority", "run_id", "progress_message", "skip_reason", "followups"):
            assert key in item
        assert item["repository"] == "r"
        assert item["type"] == "stats"

    def test_requires_auth(self, test_client):
        assert test_client.get("/api/operations/").status_code == 401


@pytest.mark.unit
class TestOperationsQueue:
    def test_queue_groups_and_limits(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        settings = _settings(test_db)
        settings.index_workers = 3
        test_db.commit()
        running = enqueue(test_db, "history_index", repository_id=repo.id)
        running.status = "running"
        old = enqueue(test_db, "stats", repository_id=repo.id)
        old.status = "completed"
        old.completed_at = utc_now() - timedelta(minutes=5)
        recent = enqueue(test_db, "stats", repository_id=repo.id)
        recent.status = "completed"
        recent.completed_at = utc_now()
        test_db.commit()
        body = test_client.get("/api/operations/queue", headers=admin_headers).json()
        group = body["repositories"][0]
        assert group["repository_id"] == repo.id
        assert group["lane_busy"] is True
        assert {o["id"] for o in group["operations"]} == {running.id, recent.id}
        assert body["limits"]["index_workers"] == 3
        assert body["limits"]["index_running"] == 1
        assert body["paused"] is False


@pytest.mark.unit
class TestOperationsDetailAndCancel:
    def test_detail_includes_run(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a = enqueue(test_db, "stats", repository_id=repo.id)
        b = enqueue(test_db, "archive_sync", repository_id=repo.id, run_id=a.run_id, depends_on_id=a.id)
        body = test_client.get(f"/api/operations/{a.id}", headers=admin_headers).json()
        assert body["id"] == a.id
        assert [o["id"] for o in body["run"]] == [a.id, b.id]

    def test_detail_404(self, test_client, admin_headers):
        assert test_client.get("/api/operations/999", headers=admin_headers).status_code == 404

    def test_cancel_queued(self, test_client, test_db, admin_headers, monkeypatch):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        r = test_client.post(f"/api/operations/{op.id}/cancel", headers=admin_headers)
        assert r.status_code == 200
        test_db.expire_all()
        assert test_db.get(Operation, op.id).status == "cancelled"

    def test_cancel_terminal_is_409(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        op.status = "completed"
        test_db.commit()
        r = test_client.post(f"/api/operations/{op.id}/cancel", headers=admin_headers)
        assert r.status_code == 409

    def test_cancel_requires_operator(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        r = test_client.post(f"/api/operations/{op.id}/cancel", headers=auth_headers)
        assert r.status_code == 403


@pytest.mark.unit
class TestPauseAndLimits:
    def test_pause_resume(self, test_client, test_db, admin_headers):
        assert test_client.post("/api/operations/pause", headers=admin_headers).json() == {"paused": True}
        assert test_db.query(SystemSettings).first().background_paused is True
        assert test_client.post("/api/operations/resume", headers=admin_headers).json() == {"paused": False}

    def test_limits_validation_and_update(self, test_client, test_db, admin_headers):
        r = test_client.put("/api/operations/limits", json={"index_workers": 0}, headers=admin_headers)
        assert r.status_code == 422
        r = test_client.put("/api/operations/limits", json={"index_workers": 4}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["index_workers"] == 4
        assert test_db.query(SystemSettings).first().index_workers == 4

    def test_pause_requires_admin(self, test_client, auth_headers):
        assert test_client.post("/api/operations/pause", headers=auth_headers).status_code == 403


@pytest.mark.unit
class TestLogs:
    def test_logs_and_download(self, test_client, test_db, admin_headers, tmp_path):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        log = tmp_path / f"operation_{op.id}.log"
        log.write_text("line1\nline2\n")
        op.log_file_path = str(log)
        test_db.commit()
        body = test_client.get(f"/api/operations/{op.id}/logs?limit=1", headers=admin_headers).json()
        assert body["lines"][0] == "line1"
        r = test_client.get(f"/api/operations/{op.id}/logs/download", headers=admin_headers)
        assert r.status_code == 200
        assert b"line2" in r.content

    def test_logs_without_file(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        r = test_client.get(f"/api/operations/{op.id}/logs", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["lines"] == []
```

Check the exact response keys of `_paginate_log_text` in `app/api/activity.py` (it returns a dict with a lines list and totals) and adjust `body["lines"]` in the test to the real key name before writing code.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_api_operations.py -q -p no:cacheprovider`
Expected: FAIL with 404 responses (router not registered)

- [ ] **Step 3: Write the router**

```python
# app/api/operations.py
"""Operations API (spec section 9.1)."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.activity import _paginate_log_text
from app.api.auth import get_current_user
from app.core.security import (
    check_repo_access,
    get_current_admin_user,
    get_current_download_user,
    require_any_role,
)
from app.database.database import get_db
from app.database.models import Operation, Repository, SystemSettings, User, utc_now
from app.services.log_policy import get_log_save_policy, job_has_logs_by_policy
from app.services.operations.lanes import lane_free, running_count
from app.services.operations.models import is_terminal, serialize_operation
from app.services.operations.runner import operation_runner
from app.services.operations.vocab import INDEX_KINDS
from app.utils.datetime_utils import serialize_datetime

router = APIRouter()

MAX_LIMIT = 500
RECENT_WINDOW = timedelta(seconds=60)


class OperationItem(BaseModel):
    activity_key: Optional[str] = None
    id: int
    type: str
    kind: str
    category: str
    status: str
    trigger: str
    priority: int
    run_id: str
    depends_on_id: Optional[int] = None
    repository_id: Optional[int] = None
    repository: Optional[str] = None
    repository_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    error_message: Optional[str] = None
    skip_reason: Optional[str] = None
    log_file_path: Optional[str] = None
    triggered_by: str = "manual"
    schedule_id: Optional[int] = None
    schedule_name: Optional[str] = None
    backup_plan_id: Optional[int] = None
    backup_plan_run_id: Optional[int] = None
    backup_plan_name: Optional[str] = None
    archive_name: Optional[str] = None
    package_name: Optional[str] = None
    has_logs: bool = False
    progress_percent: Optional[float] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    progress_message: Optional[str] = None
    execution_mode: Optional[str] = None
    params: Optional[dict] = None
    result: Optional[dict] = None
    followups: list["OperationItem"] = Field(default_factory=list)

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


OperationItem.model_rebuild()


class OperationDetail(OperationItem):
    run: list[OperationItem] = Field(default_factory=list)


class OperationListResponse(BaseModel):
    items: list[OperationItem]
    next_cursor: Optional[int] = None


class QueueLimits(BaseModel):
    index_workers: int
    index_running: int
    max_concurrent_backups: int
    max_concurrent_scheduled_backups: int
    max_concurrent_scheduled_checks: int


class QueueRepository(BaseModel):
    repository_id: Optional[int]
    repository_name: str
    lane_busy: bool
    operations: list[OperationItem]


class QueueResponse(BaseModel):
    repositories: list[QueueRepository]
    limits: QueueLimits
    paused: bool


class LimitsUpdate(BaseModel):
    index_workers: int = Field(ge=1, le=32)


# -- helpers ---------------------------------------------------------------------

def _repositories_by_id(db: Session, ops: list[Operation]) -> dict[int, Repository]:
    ids = {op.repository_id for op in ops if op.repository_id is not None}
    if not ids:
        return {}
    return {r.id: r for r in db.query(Repository).filter(Repository.id.in_(ids)).all()}


def _item(db: Session, op: Operation, repos: dict[int, Repository], policy: str) -> dict:
    repo = repos.get(op.repository_id) if op.repository_id is not None else None
    has_logs = job_has_logs_by_policy(
        op, policy, output_text=[op.error_message], file_path=op.log_file_path
    )
    return serialize_operation(
        op,
        repository_name=repo.name if repo else None,
        repository_path=repo.path if repo else None,
        has_logs=has_logs,
    )


def _get_or_404(db: Session, operation_id: int) -> Operation:
    op = db.get(Operation, operation_id)
    if op is None:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.operations.notFound"})
    return op


def _get_operation_with_access(
    db: Session, user: User, operation_id: int, required_role: str
) -> Operation:
    op = _get_or_404(db, operation_id)
    if op.repository_id is not None:
        repo = db.get(Repository, op.repository_id)
        if repo is not None:
            check_repo_access(db, user, repo, required_role)
    elif required_role != "viewer":
        require_any_role(user, "admin")
    return op


def _settings_row(db: Session) -> SystemSettings:
    settings = db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _limits(db: Session, settings: SystemSettings) -> QueueLimits:
    return QueueLimits(
        index_workers=settings.index_workers if settings.index_workers is not None else 2,
        index_running=running_count(db, kinds=INDEX_KINDS),
        max_concurrent_backups=settings.max_concurrent_backups or 1,
        max_concurrent_scheduled_backups=settings.max_concurrent_scheduled_backups or 2,
        max_concurrent_scheduled_checks=settings.max_concurrent_scheduled_checks or 4,
    )


# -- routes ------------------------------------------------------------------------

@router.get("/", response_model=OperationListResponse)
async def list_operations(
    repository_id: Optional[int] = None,
    category: Optional[list[str]] = Query(default=None),
    kind: Optional[list[str]] = Query(default=None),
    status: Optional[list[str]] = Query(default=None),
    trigger: Optional[list[str]] = Query(default=None),
    run_id: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    cursor: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Operation)
    if repository_id is not None:
        q = q.filter(Operation.repository_id == repository_id)
    if category:
        q = q.filter(Operation.category.in_(category))
    if kind:
        q = q.filter(Operation.kind.in_(kind))
    if status:
        q = q.filter(Operation.status.in_(status))
    if trigger:
        q = q.filter(Operation.trigger.in_(trigger))
    if run_id:
        q = q.filter(Operation.run_id == run_id)
    if since is not None:
        q = q.filter(Operation.created_at >= since)
    if cursor is not None:
        q = q.filter(Operation.id < cursor)
    ops = q.order_by(Operation.id.desc()).limit(limit).all()
    repos = _repositories_by_id(db, ops)
    policy = get_log_save_policy(db)
    items = [_item(db, op, repos, policy) for op in ops]
    next_cursor = ops[-1].id if len(ops) == limit else None
    return OperationListResponse(items=items, next_cursor=next_cursor)


@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = utc_now() - RECENT_WINDOW
    ops = (
        db.query(Operation)
        .filter(
            (Operation.status.in_(("queued", "running")))
            | (Operation.completed_at >= cutoff)
        )
        .order_by(Operation.priority.asc(), Operation.id.asc())
        .all()
    )
    repos = _repositories_by_id(db, ops)
    policy = get_log_save_policy(db)
    groups: dict[Optional[int], list[dict]] = {}
    for op in ops:
        groups.setdefault(op.repository_id, []).append(_item(db, op, repos, policy))
    repositories = []
    for repository_id, items in groups.items():
        repo = repos.get(repository_id) if repository_id is not None else None
        repositories.append(
            QueueRepository(
                repository_id=repository_id,
                repository_name=repo.name if repo else "System",
                lane_busy=(not lane_free(db, repository_id)) if repository_id is not None else False,
                operations=items,
            )
        )
    settings = _settings_row(db)
    return QueueResponse(
        repositories=repositories,
        limits=_limits(db, settings),
        paused=bool(settings.background_paused),
    )


@router.post("/pause")
async def pause_background(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    settings = _settings_row(db)
    settings.background_paused = True
    db.commit()
    return {"paused": True}


@router.post("/resume")
async def resume_background(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    settings = _settings_row(db)
    settings.background_paused = False
    db.commit()
    operation_runner.wake()
    return {"paused": False}


@router.put("/limits", response_model=QueueLimits)
async def update_limits(
    body: LimitsUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    settings = _settings_row(db)
    settings.index_workers = body.index_workers
    db.commit()
    operation_runner.wake()
    return _limits(db, settings)


@router.get("/{operation_id}", response_model=OperationDetail)
async def get_operation(
    operation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "viewer")
    run_ops = db.query(Operation).filter(Operation.run_id == op.run_id).order_by(Operation.id).all()
    repos = _repositories_by_id(db, run_ops + [op])
    policy = get_log_save_policy(db)
    data = _item(db, op, repos, policy)
    data["run"] = [_item(db, r, repos, policy) for r in run_ops]
    return data


@router.post("/{operation_id}/cancel")
async def cancel_operation(
    operation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "operator")
    if is_terminal(op):
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.operations.alreadyFinished"}
        )
    accepted = await operation_runner.request_cancel(op.id)
    if not accepted:
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.operations.alreadyFinished"}
        )
    return {"status": "cancel_requested"}


@router.get("/{operation_id}/logs")
async def get_operation_logs(
    operation_id: int,
    offset: int = 0,
    limit: int = 500,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "viewer")
    text = ""
    if op.log_file_path:
        try:
            with open(op.log_file_path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            text = ""
    return _paginate_log_text(text, offset, limit)


@router.get("/{operation_id}/logs/download")
async def download_operation_logs(
    operation_id: int,
    current_user: User = Depends(get_current_download_user),
    db: Session = Depends(get_db),
):
    op = _get_operation_with_access(db, current_user, operation_id, "viewer")
    if not op.log_file_path:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.operations.notFound"})
    import os

    if not os.path.exists(op.log_file_path):
        raise HTTPException(status_code=404, detail={"key": "backend.errors.operations.notFound"})
    return FileResponse(
        op.log_file_path, media_type="text/plain", filename=f"operation_{op.id}.log"
    )
```

Route ordering matters: `/queue`, `/pause`, `/resume`, `/limits` are declared before `/{operation_id}` so FastAPI does not try to parse them as ids. `job_has_logs_by_policy` is called with the `Operation` row; confirm its signature in `app/services/log_policy.py` accepts any object with a `status` attribute, and adapt the call if it needs specific attributes.

The `require_any_role` import is used by `_get_operation_with_access` for repository-less rows. The cancel test expects the runner singleton to cancel a queued row without a running loop; `request_cancel` on a queued row only touches the database, so it works under `TestClient`.

In `app/main.py`, add `operations` to the `from app.api import (...)` list and register:

```python
app.include_router(operations.router, prefix="/api/operations", tags=["Operations"])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_api_operations.py -q -p no:cacheprovider`
Expected: 14 passed

---

### Task 12: Activity union

**Files:**
- Modify: `app/api/activity.py` (`ActivityItem`, `list_recent_activity`, `get_job_logs`, the download route at the `/{job_type}/{job_id}/logs/download` decorator, and the delete route)
- Test: `tests/unit/test_activity_union.py`

**Interfaces:**
- Consumes: `serialize_operation`, `vocab.KINDS`, `vocab.INDEX_KINDS`.
- Produces:
  - `ActivityItem` gains optional fields `kind`, `category`, `trigger`, `priority`, `run_id`, `depends_on_id`, `repository_id`, `progress_percent`, `progress_current`, `progress_total`, `progress_message`, `execution_mode`, `followups: list["ActivityItem"]` (default empty), `created_at`. All optional so legacy rows validate unchanged.
  - `list_recent_activity` gains query params `category: Optional[list[str]] = Query(default=None)`, `trigger: Optional[list[str]] = Query(default=None)`, `collapse_runs: bool = True`.
  - `_operation_activity_items(db, *, limit, job_type, status, category, trigger, collapse_runs, log_save_policy) -> list[dict]`: reads `operations`, applies filters, nests follow-ups under their parent when `collapse_runs`, returns dicts with `_sort_at = started_at or created_at` so the existing sort works.

Rules (spec 9.3):

- Index-category rows are excluded unless `category` contains `"index"`.
- `job_type` matches `Operation.kind` when the value is a known kind (so `job_type=stats` works and `job_type=backup` continues to match legacy backup jobs and, later, backup operations).
- `status` filter maps through `vocab.LEGACY_STATUS_MAP` first, so `status=pending` also matches `queued` rows.
- When `collapse_runs` is true: a row with `trigger == "followup"` is not emitted at top level; it is attached to the `followups` list of the row whose id equals its `depends_on_id`, walking up until the top-level parent of the run. Follow-ups are still subject to the index filter only through their parent: when the parent is shown, its follow-ups are shown regardless of category. When the parent is not in the result (already filtered or older than the limit window), the follow-up is dropped.
- When `collapse_runs` is false: every row is a top-level item and `followups` is empty.
- Legacy rows get `category` and `trigger` derived so the new filters apply to them too: `category` from `vocab.category_for(type)` when `type` is a known kind, else `"system"` for `package`, `"mirror"` for rclone types, `"system"` for `script_execution`; `trigger` = the legacy `triggered_by`, mapping `"schedule"` to `"schedule"` and everything else to `"manual"`, except rows with `backup_plan_run_id` which become `"plan"`. Apply `category` and `trigger` filters to legacy rows using those derived values.

Logs and delete routes: when `job_type in vocab.KINDS` and no legacy model is mapped for it (in phase 1 that is every kind except `backup`, `restore`, `check`, `restore_check`, `compact`, `prune`, `package`), resolve `Operation` by id and serve `log_file_path` through `_paginate_log_text` (logs), `FileResponse` (download), and delete the row plus its log file (delete, admin only as today, refusing `running` rows with the existing 409 payload). For the seven kinds that still have legacy tables, keep resolving the legacy model; the Operations API in Task 11 serves operations rows of those kinds by id.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_activity_union.py
from datetime import timedelta

import pytest

from app.database.models import Operation, PruneJob, Repository, utc_now
from app.services.operations.enqueue import enqueue, enqueue_chain


def _repo(test_db):
    repo = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestActivityUnion:
    def test_index_rows_hidden_by_default_and_shown_with_filter(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        enqueue(test_db, "stats", repository_id=repo.id)
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert body == []
        body = test_client.get("/api/activity/recent?category=index", headers=admin_headers).json()
        assert [i["type"] for i in body] == ["stats"]
        assert body[0]["category"] == "index"
        assert body[0]["status"] == "queued"

    def test_legacy_and_operations_merge_ordered_by_time(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        old = PruneJob(repository_id=repo.id, repository_path=repo.path, status="completed",
                       started_at=utc_now() - timedelta(hours=2))
        test_db.add(old)
        test_db.commit()
        op = enqueue(test_db, "import_connect", repository_id=repo.id, trigger="import")
        op.status = "completed"
        op.started_at = utc_now() - timedelta(hours=1)
        test_db.commit()
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert [i["type"] for i in body] == ["import_connect", "prune"]
        assert body[1]["category"] == "maintenance"
        assert body[1]["trigger"] == "manual"

    def test_collapse_runs_nests_followups(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        parent = enqueue(test_db, "import_connect", repository_id=repo.id, trigger="import")
        parent.status = "completed"
        parent.started_at = utc_now()
        test_db.commit()
        chain = enqueue_chain(test_db, ["stats", "archive_sync"], repository_id=repo.id,
                              trigger="followup", run_id=parent.run_id, depends_on_id=parent.id)
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert [i["id"] for i in body] == [parent.id]
        assert [f["kind"] for f in body[0]["followups"]] == ["stats", "archive_sync"]
        flat = test_client.get("/api/activity/recent?collapse_runs=false&category=index&category=import",
                               headers=admin_headers).json()
        assert {i["id"] for i in flat} == {parent.id, chain[0].id, chain[1].id}
        assert all(i["followups"] == [] for i in flat)

    def test_status_filter_maps_pending_to_queued(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        enqueue(test_db, "import_connect", repository_id=repo.id, trigger="import")
        body = test_client.get("/api/activity/recent?status=pending", headers=admin_headers).json()
        assert [i["type"] for i in body] == ["import_connect"]

    def test_trigger_filter_applies_to_legacy_rows(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        test_db.add(PruneJob(repository_id=repo.id, repository_path=repo.path, status="completed",
                             started_at=utc_now(), scheduled_prune=True))
        test_db.add(PruneJob(repository_id=repo.id, repository_path=repo.path, status="completed",
                             started_at=utc_now()))
        test_db.commit()
        body = test_client.get("/api/activity/recent?trigger=schedule", headers=admin_headers).json()
        assert len(body) == 1 and body[0]["trigger"] == "schedule"

    def test_logs_resolve_operation_kinds(self, test_client, test_db, admin_headers, tmp_path):
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        log = tmp_path / "op.log"
        log.write_text("a\nb\n")
        op.log_file_path = str(log)
        test_db.commit()
        r = test_client.get(f"/api/activity/archive_sync/{op.id}/logs", headers=admin_headers)
        assert r.status_code == 200

    def test_delete_operation_row_via_activity(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        op.status = "completed"
        test_db.commit()
        r = test_client.delete(f"/api/activity/archive_sync/{op.id}", headers=admin_headers)
        assert r.status_code == 200
        assert test_db.get(Operation, op.id) is None

    def test_delete_running_operation_refused(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        op.status = "running"
        test_db.commit()
        r = test_client.delete(f"/api/activity/archive_sync/{op.id}", headers=admin_headers)
        assert r.status_code in (400, 409)
```

Check `PruneJob` for a `scheduled_prune` column (the activity code reads it with `getattr`) and the delete route's exact refusal status for running jobs; align the last assertion with it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_activity_union.py -q -p no:cacheprovider`
Expected: FAIL (index rows appear or 404 on kinds)

- [ ] **Step 3: Implement the union**

In `app/api/activity.py`:

1. Add imports:

```python
from fastapi import Query
from app.database.models import Operation
from app.services.operations import vocab as op_vocab
from app.services.operations.models import serialize_operation
```

2. Extend `ActivityItem` with the optional fields listed in Interfaces (place them after `repository_path`), and add `ActivityItem.model_rebuild()` after the class for the self-referencing `followups` list.

3. Add the helper before `list_recent_activity`:

```python
_LEGACY_CATEGORY_BY_TYPE = {
    "package": "system",
    "script_execution": "system",
}


def _legacy_category(item_type: str) -> str:
    if item_type in op_vocab.KINDS:
        return op_vocab.category_for(item_type)
    if item_type in RCLONE_ACTIVITY_OPERATIONS:
        return "mirror"
    return _LEGACY_CATEGORY_BY_TYPE.get(item_type, "system")


def _legacy_trigger(item: dict) -> str:
    if item.get("backup_plan_run_id"):
        return "plan"
    return "schedule" if item.get("triggered_by") == "schedule" else "manual"


def _operation_activity_items(
    db: Session,
    *,
    limit: int,
    job_type: Optional[str],
    status: Optional[str],
    category: Optional[list[str]],
    trigger: Optional[list[str]],
    collapse_runs: bool,
    log_save_policy: str,
) -> list[dict]:
    q = db.query(Operation)
    if job_type:
        if job_type not in op_vocab.KINDS:
            return []
        q = q.filter(Operation.kind == job_type)
    if status:
        wanted = {status, op_vocab.LEGACY_STATUS_MAP.get(status, status)}
        q = q.filter(Operation.status.in_(tuple(wanted)))
    ops = q.order_by(Operation.id.desc()).limit(limit * 4).all()
    if not ops:
        return []
    repo_ids = {op.repository_id for op in ops if op.repository_id is not None}
    repos = {
        r.id: r for r in db.query(Repository).filter(Repository.id.in_(repo_ids)).all()
    } if repo_ids else {}
    by_id: dict[int, dict] = {}
    for op in ops:
        repo = repos.get(op.repository_id) if op.repository_id is not None else None
        item = serialize_operation(
            op,
            repository_name=repo.name if repo else None,
            repository_path=repo.path if repo else None,
            has_logs=job_has_logs_by_policy(
                op, log_save_policy, output_text=[op.error_message], file_path=op.log_file_path
            ),
        )
        item["_sort_at"] = op.started_at or op.created_at
        item["_depends_on_id"] = op.depends_on_id
        item["_trigger"] = op.trigger
        by_id[op.id] = item

    def _visible(item: dict) -> bool:
        if category:
            if item["category"] not in category:
                return False
        elif item["category"] == "index":
            return False
        if trigger and item["trigger"] not in trigger:
            return False
        return True

    top_level: list[dict] = []
    if collapse_runs:
        for item in by_id.values():
            if item["_trigger"] != "followup":
                if _visible(item):
                    top_level.append(item)
        for item in sorted(by_id.values(), key=lambda i: i["id"]):
            if item["_trigger"] != "followup":
                continue
            parent_id = item["_depends_on_id"]
            while parent_id in by_id and by_id[parent_id]["_trigger"] == "followup":
                parent_id = by_id[parent_id]["_depends_on_id"]
            parent = by_id.get(parent_id)
            if parent is not None and parent in top_level:
                parent["followups"].append(item)
    else:
        top_level = [item for item in by_id.values() if _visible(item)]
    for item in by_id.values():
        item.pop("_depends_on_id", None)
        item.pop("_trigger", None)
        for followup in item["followups"]:
            followup.pop("_sort_at", None)
            followup.pop("_depends_on_id", None)
            followup.pop("_trigger", None)
    return top_level
```

4. In `list_recent_activity`, add the parameters:

```python
    category: Optional[list[str]] = Query(default=None),
    trigger: Optional[list[str]] = Query(default=None),
    collapse_runs: bool = True,
```

After the last legacy block and before the sort, derive `category` and `trigger` for every legacy dict and apply the new filters, then extend with operation items:

```python
    for activity in activities:
        activity.setdefault("category", _legacy_category(activity["type"]))
        activity.setdefault("trigger", _legacy_trigger(activity))
        activity.setdefault("followups", [])
    if category:
        activities = [a for a in activities if a["category"] in category]
    if trigger:
        activities = [a for a in activities if a["trigger"] in trigger]
    activities.extend(
        _operation_activity_items(
            db, limit=limit, job_type=job_type, status=status, category=category,
            trigger=trigger, collapse_runs=collapse_runs, log_save_policy=log_save_policy,
        )
    )
```

Keep the existing sort, limit, and `_sort_at` pop after that. Because every dict now carries `followups` lists that also contain `_sort_at`, the pop loop above already strips them for follow-ups.

5. In `get_job_logs`, the download route, and the delete route, add at the top, before the legacy `job_models` lookup:

```python
    if job_type in op_vocab.KINDS and job_type not in job_models:
        op = db.query(Operation).filter(Operation.id == job_id, Operation.kind == job_type).first()
        if not op:
            raise HTTPException(
                status_code=404,
                detail={"key": "backend.errors.activity.jobNotFound", "params": {"jobType": job_type}},
            )
        ...
```

For logs: read `op.log_file_path` if present and return `_paginate_log_text(text, offset, limit)`. For download: `FileResponse(op.log_file_path, media_type="text/plain", filename=f"operation_{op.id}.log")` or 404 when missing. For delete: refuse when `op.status == "running"` with the same status code and payload the route already uses for running legacy jobs, otherwise delete the log file if present, `db.delete(op)`, commit, and return the route's usual success payload. Define `job_models` before that check in each route (it already exists in logs and delete; add the same dict in the download route if it is built inline there).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_activity_union.py tests/unit/test_api_activity.py -q -p no:cacheprovider`
Expected: all passed

---

### Task 13: Import records `import_connect` and enqueues follow-ups

**Files:**
- Modify: `app/api/repositories.py` (`import_repository`, the block that calls `BorgRouter(repository).update_stats(db)` after the repository row is committed)
- Test: `tests/unit/test_api_repositories_import_operations.py`

**Interfaces:**
- Consumes: `enqueue`, `enqueue_chain`, `chain_for`, `executors.registered_kinds`.
- Produces: `record_import_connect(db, repository, *, user_id) -> Operation`: creates a `completed` `import_connect` row (`trigger="import"`, `started_at = completed_at = utc_now()`, `result = {"verified": True}`) and then `enqueue_chain(db, chain_for("import_connect", available=registered_kinds()), repository_id=repository.id, trigger="followup", run_id=op.run_id, depends_on_id=op.id, triggered_by_user_id=user_id)`. Lives in `app/services/operations/enqueue.py` so the v2 import route can reuse it in phase 2.

The import route already verified the repository with `verify_existing_repository` before the row was created, so `import_connect` is recorded as already completed; the runner never executes it (there is no executor for it, and it is never queued).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_api_repositories_import_operations.py
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import Operation, Repository


@pytest.mark.unit
def test_record_import_connect_creates_completed_row_and_followups(test_db):
    from app.services.operations.enqueue import record_import_connect
    import app.services.operations.executors.index  # noqa: F401

    repo = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    test_db.add(repo)
    test_db.commit()
    op = record_import_connect(test_db, repo, user_id=None)
    rows = test_db.query(Operation).order_by(Operation.id).all()
    assert rows[0].id == op.id
    assert rows[0].kind == "import_connect" and rows[0].status == "completed"
    assert rows[0].trigger == "import" and rows[0].completed_at is not None
    assert [r.kind for r in rows[1:]] == ["stats", "archive_sync"]
    assert rows[1].depends_on_id == op.id
    assert all(r.run_id == op.run_id and r.trigger == "followup" for r in rows[1:])


@pytest.mark.unit
def test_import_repository_records_operation_and_skips_inline_stats(
    test_client, test_db, admin_headers, tmp_path
):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    with (
        patch(
            "app.api.repositories.verify_existing_repository",
            new=AsyncMock(return_value={"success": True, "encryption": "none"}),
        ),
        patch("app.core.borg_router.BorgRouter.update_stats", new=AsyncMock()) as update_stats,
    ):
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "imported", "path": str(repo_path), "passphrase": "", "compression": "lz4"},
            headers=admin_headers,
        )
    assert response.status_code in (200, 201), response.text
    update_stats.assert_not_awaited()
    repo = test_db.query(Repository).filter_by(name="imported").one()
    kinds = [o.kind for o in test_db.query(Operation).filter_by(repository_id=repo.id).order_by(Operation.id)]
    assert kinds[0] == "import_connect"
    assert "archive_sync" in kinds and "stats" in kinds
```

Read `import_repository` and its `RepositoryImport` schema before writing the second test: the JSON body above must satisfy the schema's required fields and any validation that runs before `verify_existing_repository` (for example `_validate_upload_ratelimit_kib`, rclone and Borg 2 payload checks). Find an existing import test in `tests/unit/test_api_repositories.py` (search for `"/api/repositories/import"`) and copy its body and patches instead of guessing. The return value of `verify_existing_repository` must match what the route reads from it (search the route for `verify_result[`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_api_repositories_import_operations.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'record_import_connect'`

- [ ] **Step 3: Implement**

Append to `app/services/operations/enqueue.py`:

```python
def record_import_connect(db: Session, repository, *, user_id: Optional[int]) -> Operation:
    """Record a completed import_connect for an already verified repository
    and enqueue its follow-up chain (spec sections 7.4 and A.1)."""
    from app.database.models import utc_now
    from app.services.operations.executors import registered_kinds
    from app.services.operations.followups import chain_for

    now = utc_now()
    op = Operation(
        repository_id=repository.id,
        kind="import_connect",
        category=vocab.category_for("import_connect"),
        status="completed",
        trigger="import",
        priority=vocab.priority_for_trigger("import"),
        run_id=new_run_id(),
        triggered_by_user_id=user_id,
        result={"verified": True},
        started_at=now,
        completed_at=now,
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    kinds = chain_for("import_connect", available=registered_kinds())
    if kinds:
        enqueue_chain(
            db, kinds, repository_id=repository.id, trigger="followup",
            run_id=op.run_id, depends_on_id=op.id, triggered_by_user_id=user_id,
        )
    return op
```

In `app/api/repositories.py`, replace

```python
        # Update archive count by listing archives (non-blocking - don't fail import)
        try:
            from app.core.borg_router import BorgRouter

            await BorgRouter(repository).update_stats(db)
        except Exception as e:
            # Log but don't fail the import - stats can be updated later
            logger.warning(
                "Failed to update repository stats after import",
                repository=repository.name,
                error=str(e),
            )
```

with

```python
        # Record the verified connect step and hand stats and archive listing
        # to the operations runner (spec section 7.4). The request no longer
        # waits on Borg for derived data.
        try:
            from app.services.operations.enqueue import record_import_connect

            record_import_connect(db, repository, user_id=current_user.id)
        except Exception as e:
            logger.warning(
                "Failed to enqueue post-import operations",
                repository=repository.name,
                error=str(e),
            )
```

The Borg 2 import path (`import_repository_v2` in `app/api/v2/repositories.py`) and the agent and rclone import paths keep their current behaviour in phase 1; they are listed under Open questions for phase 2.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_api_repositories_import_operations.py tests/unit/test_api_repositories.py -q -p no:cacheprovider`
Expected: all passed. If an existing import test asserted that `update_stats` is awaited, update it to assert the `import_connect` row instead.

---

### Task 14: Retention, documentation

**Files:**
- Modify: `app/services/job_history_retention.py` (`_JOB_TABLES`)
- Modify: `docs/architecture/job-system.md`
- Modify: `docs/configuration.md`
- Test: `tests/unit/test_job_history_retention.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_job_history_retention.py`:

```python
@pytest.mark.unit
def test_operations_rows_fall_with_cleanup_retention(db):
    from app.database.models import Operation
    from app.services.operations.enqueue import enqueue

    _settings(db)
    repo = Repository(name="ops", path="/tmp/ops", encryption="none", compression="lz4")
    db.add(repo)
    db.commit()
    old = enqueue(db, "stats", repository_id=repo.id)
    old.status = "completed"
    old.created_at = utc_now() - timedelta(days=200)
    old.completed_at = utc_now() - timedelta(days=200)
    fresh = enqueue(db, "stats", repository_id=repo.id)
    fresh.status = "completed"
    fresh.completed_at = utc_now()
    db.commit()
    run_retention(db)
    ids = {o.id for o in db.query(Operation)}
    assert fresh.id in ids and old.id not in ids
```

Match the `_settings(db)` helper and `run_retention` call signature used by the neighbouring tests in that file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_job_history_retention.py -q -p no:cacheprovider -k operations_rows`
Expected: FAIL (old row still present)

- [ ] **Step 3: Implement**

In `app/services/job_history_retention.py`, import `Operation` from `app.database.models` and add `(Operation, ()),` to `_JOB_TABLES` after `(AvailabilityScheduleSkip, ()),`. Operations have no inline log column; log files on disk follow the existing file-based `log_retention_days` sweep if that sweep reads `log_file_path` from the models it iterates. Check `job_history_retention.py` for how it treats `log_file_path` on other tables and confirm `Operation` gets the same treatment.

Add to `docs/architecture/job-system.md`, after the "Concurrency" section:

```markdown
## Operations runner

Derived-data work (repository stats, archive listing, and in later phases
history indexing) runs through a single in-process runner backed by the
`operations` table. Each row has a kind, a category, a trigger, a priority,
and an optional dependency on another row. Rows that share a `run_id` form
a run, for example an import followed by its stats and archive listing.

Rules:

- One exclusive operation per repository at a time (the repository lane).
  While a backup, check, prune, compact, wipe, or archive delete is running,
  exclusive operations wait. Index operations wait too unless
  `bypass_lock_on_list` or the repository's bypass setting allows them to
  run alongside.
- Lower priority number runs first: manual and plan work at 0, scheduled at
  5, follow-ups at 10, reconcile at 20.
- A failed, cancelled, or skipped operation skips everything that depends on
  it with `skip_reason = dependency_failed`.
- Follow-ups are created automatically when an operation succeeds. An
  import enqueues stats and archive listing.
- The reconcile scheduler replaces the old stats refresh loop. Every
  `stats_refresh_interval_minutes` it enqueues an index run for each
  repository that has none queued or running. `0` disables it.
- On startup, running index operations are requeued; other running
  operations are marked failed unless their recorded process is still
  alive.

The `/api/operations` routes expose the list, a live queue view, cancel,
pause and resume of background triggers, and the `index_workers` limit.
Activity includes operations rows; index-category rows are hidden unless
the Index category filter is on.
```

Add to the settings table in `docs/configuration.md`:

```markdown
| `INDEX_ARCHIVE_INFO_PER_RUN` | `20` | Per-archive `borg info` calls one archive listing run may make for newly seen archives; the rest are picked up by later runs |
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_job_history_retention.py -q -p no:cacheprovider`
Expected: all passed

---

### Task 15: Phase verification and gate G2

**Files:** none new.

- [ ] **Step 1: Full backend test suite**

Run: `python -m pytest tests/unit -q -p no:cacheprovider`
Expected: all passed, zero skipped tests introduced by this phase.

- [ ] **Step 2: Lint and format**

Run: `ruff check app tests && ruff format --check app tests`
Expected: no findings. Fix and rerun if needed.

- [ ] **Step 3: Migration round trip on a fresh database**

Run: `DATA_DIR=$(mktemp -d) alembic upgrade head`
Expected: completes; `operations`, `archives`, `archive_changes` exist.

- [ ] **Step 4: Import smoke check**

Run: `python -c "import app.main; from app.services.operations.executors import load_default_executors, registered_kinds; load_default_executors(); print(sorted(registered_kinds()))"`
Expected: `['archive_sync', 'stats']`

- [ ] **Step 5: Live check with the borg-live-debug skill (optional but recommended)**

Start the dev stack, import a small local repository through the UI, and confirm with `sqlite3` or the `/api/operations/queue` route that `import_connect` is completed and `stats` and `archive_sync` reach `completed`, that `archives` has one row per archive, and that `repository.archive_count` matches. Confirm that `GET /api/activity/recent` shows the import row with two nested follow-ups.

- [ ] **Step 6: Reference checks**

Run: `grep -rn "stats_refresh_scheduler" app tests` (expect no results) and `grep -rn $'\xe2\x80\x94' app/services/operations app/api/operations.py docs/architecture/job-system.md` (expect no results; the escape is the em dash byte sequence).

- [ ] **Step 7: Verification before completion**

Invoke `superpowers:verification-before-completion`, paste the command outputs from steps 1 to 6 verbatim into the report, update the progress table in the spec (section 19.1) to `in review`, and stop at gate G2: ask the user whether to commit. Do not commit before the answer.

---

## Open questions

Answers are recorded in the spec's Appendix B by the orchestrator once given.

1. **Where `index_workers` and `background_paused` live.** Spec section 14 lists them next to `app/config.py` settings, but section 9.1 mutates them at runtime through `PUT /operations/limits` and pause/resume. This plan stores them as `SystemSettings` columns and keeps only `INDEX_ARCHIVE_INFO_PER_RUN` in `config.py`. Confirm or redirect.
2. **Import paths other than the Borg 1 server route.** `import_repository_v2` (Borg 2), the agent path (`_create_agent_repository_record`), and the rclone paths still call their existing stats logic. This plan leaves them for phase 2 so phase 1 changes one route. Confirm.
3. **Activity visibility.** `/api/activity/recent` shows every repository's rows to any authenticated user today. The new operations rows follow the same rule for parity. If per-repository RBAC filtering is wanted in Activity, it is a separate change for both legacy and new rows.
4. **`BorgRouter.update_stats` callers.** Backup, wipe, and the info-dialog sync still call it in phase 1; the spec assigns their replacement to phases 5, 6, and 2. Confirm that phase 1 leaves `update_repository_stats` untouched apart from the import route.
5. **Running-operation cancellation.** `request_cancel` sets a flag and relies on the executor polling `ctx.cancelled()`; it does not hard-cancel the asyncio task, so a Borg-backed executor in later phases can terminate its child process first. Confirm this is the intended contract, or ask for a hard cancel after a grace period.
