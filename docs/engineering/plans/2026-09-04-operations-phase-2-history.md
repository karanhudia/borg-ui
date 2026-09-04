# Operations Phase 2: History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not commit at the
> end of a task; the phase has one commit gate (G2) at the end, per section
> 19.4 of the spec and `.claude/instructions.md`.

**Goal:** Store what each backup changed, so that diff, file history, search,
heatmap, and status strip become database reads, and gate that history layer
behind the Pro feature key `archive_history`.

**Architecture:** Two new executors in `app/services/operations/executors/`
fill and maintain `archive_changes`: `history_index` streams `borg diff`
(or a full `borg list` for a series' first archive) into batched rows with
excludes and a row cap, and `history_merge` folds a pruned archive's rows into
its successor with one pure fold function that the changes route reuses for
`compare_to`. A new router `app/api/archive_index.py` under
`/api/repositories/{id}` serves the archive list, heatmap, status strip,
rebuild, changes, history, and search from the database. Series inference,
anomaly rules, and the fold are pure modules with unit tests. The follow-up
chain, reconcile, and the licensing service become plan aware.

**Tech Stack:** FastAPI, SQLAlchemy 1.x declarative models, Alembic with
`batch_alter_table` (SQLite), asyncio subprocess streaming, croniter (already
a dependency), pytest with the `test_db` / `test_client` / `admin_headers`
fixtures from `tests/fixtures/api.py`, the in-memory `db` fixture pattern from
`tests/unit/test_operations_index_executors.py`, and `db_session` from
`tests/fixtures/database.py`. Real Borg output for fixtures is captured with
the `borg-live-debug` skill.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
(sections 6.4 to 6.7, 7.4, 7.5, 8.3, 8.4, 9.2, 9.5, 11, 12, 14, 18, Appendix A,
Appendix B).

## Model per task

Spec section 13 splits phase 2 between two models. Run `/continue-spec` on
the model of the first unchecked task; gate G0 compares against this table,
not against a single phase model.

| Tasks | Model | Why |
| --- | --- | --- |
| 1 to 3 | Sonnet 5 | Settings, feature key, series inference, Borg wrappers, fixtures: pattern work |
| 4 to 6 | Fable 5.1 | Fold table, `history_index`, `history_merge`: correctness is the feature |
| 7 to 12 | Sonnet 5 | Plan-aware chain, info sync, anomaly rules, routes, docs: pattern work against fixed interfaces |

Task 3 precedes the executors because they are written against its
`ChangeRecord` and stream interfaces; the spec's "once the first executor
exists" ordering is satisfied by the routes and anomaly rules (tasks 9 to 11),
which do come after the executors.

## Global Constraints

- Phase 2 is backend plus four small frontend edits: the `archive_history`
  key in `frontend/src/core/features.ts`, its Vitest test, the copied
  `frontend/src/data/plan-content.json`, and one URL in
  `frontend/src/services/api.ts` (Task 10, see Open questions 1). No
  components, stories, or i18n keys change in this phase.
- Spec 6.5 columns for `archive_changes` are verbatim and already exist from
  phase 1. Do not add columns. `size_delta` lives only on the in-memory
  `ChangeRecord`, never in the table.
- Spec 6.7 defaults are verbatim: excludes
  `["**/.cache/**", "**/Library/Caches/**", "**/node_modules/**", "**/__pycache__/**", "**/.git/objects/**"]`,
  `INDEX_HISTORY_MAX_ROWS` default `200000`, insert batches of `5000`, one
  transaction per archive.
- Spec 7.4 chain table is unchanged. Plan awareness only removes
  `history_index` and `history_merge` from a chain; it never reorders.
- Spec 9.2 paths are verbatim. The Pro routes use
  `require_feature("archive_history")` and return the same 403 payload as
  every other gated route (`app/core/features.py`).
- Every Borg call in an executor goes through
  `run_serialized_repository_command(repository.id, ..., scope="metadata")`.
- Paths in `archive_changes.path` are stored exactly as Borg prints them
  (no leading slash). Directories are not stored (Open questions 3).
- Never commit or push without the user's answer at gate G2. Do not use em
  dashes anywhere: not in code, comments, docstrings, log messages, JSON
  copy, or docs. Use commas, periods, or parentheses.
- Every new module gets unit tests under `tests/unit/`. Every route gets a
  test through `test_client`. Run `python -m pytest tests/unit -q -x
  -p no:cacheprovider` and `ruff check app tests` before claiming a task
  done. For frontend edits run `cd frontend && npx vitest run src/core
  src/services/planContent.test.ts`.
- Fixtures under `tests/fixtures/borg_output/` must be real Borg output
  captured with `borg-live-debug` (spec 8.3 and 12). Hand-written JSON is
  not acceptable; if the container is unavailable, stop at gate G4.

## File Structure

Created:

- `app/services/operations/series.py` `strip_timestamp()`, `template_prefix()`, `series_prefixes_for_repository()`, `cron_for_repository()`, `infer_series()`
- `app/core/borg_stream.py` `CommandLineStream`
- `app/core/borg_diff.py` `ChangeRecord`, `parse_diff_line()`, `parse_list_line()`
- `app/services/operations/history_fold.py` `Change`, `fold_pair()`, `fold_sequence()`, `change_from_row()`, `rows_to_changes()`
- `app/services/operations/executors/history.py` `run_history_index()`, `run_history_merge()`, excludes, cap, size resolution, merge orchestration
- `app/services/operations/anomalies.py` `size_outlier()`, `duration_outlier()`, `median_gap()`, `missed_run_days()`, `overdue()`, `series_flags()`, `OVERDUE_THRESHOLD_DAYS`
- `app/services/operations/legacy_status.py` `latest_legacy_terminal()` (deleted in phase 9)
- `app/api/archive_index.py` router for the spec 9.2 routes
- `app/database/alembic/versions/c2d3e4f5a6b7_add_history_index_excludes.py`
- `tests/fixtures/borg_output/{borg1_diff,borg2_diff,borg1_list,borg2_list}.jsonl` and `README.md`
- `tests/unit/test_series_inference.py`
- `tests/unit/test_borg_stream.py`
- `tests/unit/test_borg_diff_parsing.py`
- `tests/unit/test_changes_fold.py`
- `tests/unit/test_history_index.py`
- `tests/unit/test_history_merge.py`
- `tests/unit/test_anomalies.py`
- `tests/unit/test_api_archive_index.py`
- `frontend/src/core/__tests__/features.test.ts`

Modified:

- `app/config.py` add `index_history_max_rows: int = 200000`
- `app/database/models.py` add `DEFAULT_HISTORY_INDEX_EXCLUDES`, `Repository.history_index_excludes`, `SystemSettings.history_bootstrap_at`
- `app/core/features.py`, `frontend/src/core/features.ts` add `archive_history`
- `docs/plan-content.json`, `frontend/src/data/plan-content.json` add the `archive_history` entry
- `app/core/borg.py` extract `_build_exec_env()`, add `diff_archives()`, `list_archive_lines()`
- `app/core/borg2.py` add `diff_archives()`, `list_archive_lines()`
- `app/core/borg_router.py` add `diff_archives()`, `list_archive_lines()`
- `app/services/operations/executors/index.py` series inference, `write_repository_archive_columns()`
- `app/services/operations/executors/__init__.py` load the history module
- `app/services/operations/followups.py` `HISTORY_KINDS`, `history_enabled()`, `chain_for(history=...)`
- `app/services/operations/runner.py`, `enqueue.py`, `reconcile.py` pass the plan flag; `bootstrap_history_once()`
- `app/services/licensing_service.py` `_on_plan_changed()` enqueues reconcile on Pro activation
- `app/services/repository_info_sync.py` writes into `archives`
- `app/api/repositories.py` live listing moves to `/{repo_id}/archives/live`; `history_index_excludes` in `RepositoryUpdate`, the PUT route, and the serializer
- `app/api/archives.py` `/list` gains deprecation headers
- `app/main.py` include the new router, call `bootstrap_history_once()`
- `frontend/src/services/api.ts` `listRepositoryArchives` URL
- `tests/unit/test_operations_index_executors.py`, `test_operations_followups.py`, `test_operations_reconcile.py`, `test_core_features.py`, `test_licensing_service.py`, `test_repository_info_sync.py`
- `docs/configuration.md`, `docs/architecture/job-system.md`, `docs/cache.md`, `docs/api.md`, `Borg_UI_API.postman_collection.json`

---

### Task 1: Settings, feature key, plan content, migration

**Files:**
- Modify: `app/config.py:192-193`
- Modify: `app/database/models.py` (`Repository` near line 322, `SystemSettings` near line 1621)
- Modify: `app/core/features.py:20-33`
- Modify: `frontend/src/core/features.ts:10-24`
- Modify: `docs/plan-content.json`, `frontend/src/data/plan-content.json` (identical copies; keep them identical)
- Modify: `docs/configuration.md:159`
- Create: `app/database/alembic/versions/c2d3e4f5a6b7_add_history_index_excludes.py`
- Create: `frontend/src/core/__tests__/features.test.ts`
- Test: `tests/unit/test_core_features.py`, `tests/unit/test_config.py`

**Interfaces:**
- Produces:
  - `settings.index_history_max_rows: int` (default 200000)
  - `app.database.models.DEFAULT_HISTORY_INDEX_EXCLUDES: tuple[str, ...]`
  - `Repository.history_index_excludes: Optional[list[str]]` (JSON column, Python default = the tuple as a list)
  - `SystemSettings.history_bootstrap_at: Optional[datetime]`
  - `FEATURES["archive_history"] == Plan.PRO` on both sides

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_core_features.py` inside `TestPlanIncludes`:

```python
    def test_archive_history_is_a_pro_feature(self):
        assert FEATURES["archive_history"] == Plan.PRO
        assert plan_includes(Plan.COMMUNITY, FEATURES["archive_history"]) is False
        assert plan_includes(Plan.PRO, FEATURES["archive_history"]) is True
```

Append to `tests/unit/test_config.py` (create the file if it does not exist, following the module's existing style):

```python
@pytest.mark.unit
def test_index_history_max_rows_default():
    from app.config import Settings

    assert Settings().index_history_max_rows == 200000
```

Create `tests/unit/test_history_defaults.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    DEFAULT_HISTORY_INDEX_EXCLUDES,
    Base,
    Repository,
    SystemSettings,
)


@pytest.mark.unit
def test_default_history_excludes_match_spec_6_7():
    assert DEFAULT_HISTORY_INDEX_EXCLUDES == (
        "**/.cache/**",
        "**/Library/Caches/**",
        "**/node_modules/**",
        "**/__pycache__/**",
        "**/.git/objects/**",
    )


@pytest.mark.unit
def test_new_repository_is_seeded_with_default_excludes():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    repo = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(repo)
    db.add(SystemSettings())
    db.commit()
    db.refresh(repo)
    assert repo.history_index_excludes == list(DEFAULT_HISTORY_INDEX_EXCLUDES)
    assert db.query(SystemSettings).first().history_bootstrap_at is None
```

Create `frontend/src/core/__tests__/features.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { FEATURES, canAccess } from '../features'

describe('features', () => {
  it('archive_history is a Pro feature', () => {
    expect(FEATURES.archive_history).toBe('pro')
    expect(canAccess('community', 'archive_history')).toBe(false)
    expect(canAccess('pro', 'archive_history')).toBe(true)
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_core_features.py tests/unit/test_history_defaults.py tests/unit/test_config.py -q -p no:cacheprovider`
Expected: FAIL with `KeyError: 'archive_history'`, `ImportError` for `DEFAULT_HISTORY_INDEX_EXCLUDES`, `AttributeError` for `index_history_max_rows`.

Run: `cd frontend && npx vitest run src/core`
Expected: FAIL, `archive_history` is not a key of `FEATURES`.

- [ ] **Step 3: Add the settings, columns, and keys**

`app/config.py`, after `index_archive_info_per_run`:

```python
    # Operations index: change rows stored per archive before the rest is
    # collapsed into per-subtree summary rows (spec 6.7)
    index_history_max_rows: int = 200000
```

`app/database/models.py`, above `class Repository(Base)`:

```python
# Default history index excludes (spec 6.7). Seeded on every repository
# creation path through the column default and backfilled by migration
# c2d3e4f5a6b7 for rows that predate it.
DEFAULT_HISTORY_INDEX_EXCLUDES: tuple[str, ...] = (
    "**/.cache/**",
    "**/Library/Caches/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.git/objects/**",
)
```

Inside `Repository`, after `borg_version`:

```python
    # Glob patterns the history index drops from borg diff output (spec 6.7)
    history_index_excludes = Column(
        JSON, nullable=True, default=lambda: list(DEFAULT_HISTORY_INDEX_EXCLUDES)
    )
```

Inside `SystemSettings`, after `background_paused`:

```python
    # Set once the first post-phase-2 startup has enqueued a reconcile run
    # for every repository (spec 14)
    history_bootstrap_at = Column(DateTime, nullable=True)
```

`app/core/features.py`, in `FEATURES` after `"alerting_monitoring"`:

```python
    "archive_history": Plan.PRO,  # change deltas, file history, search, outlier flags
```

`frontend/src/core/features.ts`, in `FEATURES` after `alerting_monitoring`:

```ts
  archive_history: 'pro',
```

`docs/plan-content.json` and `frontend/src/data/plan-content.json`: insert this object after the `container_backups` entry (before `rbac`):

```json
    {
      "id": "archive_history",
      "plan": "pro",
      "label": "Archive history and change tracking",
      "label_localized": {
        "es": "Historial de archivos y seguimiento de cambios",
        "de": "Archivverlauf und Änderungsverfolgung",
        "it": "Cronologia degli archivi e tracciamento delle modifiche"
      },
      "description": "See what each backup added, removed, or modified, follow a file across archives, and search for files that only exist in old backups.",
      "description_localized": {
        "es": "Consulta qué añadió, eliminó o modificó cada copia, sigue un archivo a través de los archivos y busca archivos que solo existen en copias antiguas.",
        "de": "Sehen Sie, was jedes Backup hinzugefügt, entfernt oder geändert hat, verfolgen Sie eine Datei über Archive hinweg und suchen Sie nach Dateien, die nur in alten Backups existieren.",
        "it": "Scopri cosa ha aggiunto, rimosso o modificato ogni backup, segui un file attraverso gli archivi e cerca file che esistono solo nei backup precedenti."
      },
      "availability": "included"
    },
```

After editing, run `diff -q docs/plan-content.json frontend/src/data/plan-content.json` and expect no output.

`docs/configuration.md`, after the `INDEX_ARCHIVE_INFO_PER_RUN` row:

```markdown
| `INDEX_HISTORY_MAX_ROWS` | `200000` | Change rows stored per archive by the history index; changes past the cap collapse into per-subtree summary rows and the archive is marked truncated |
```

- [ ] **Step 4: Write the migration**

Create `app/database/alembic/versions/c2d3e4f5a6b7_add_history_index_excludes.py`:

```python
"""add repository history index excludes and history bootstrap flag

Revision ID: c2d3e4f5a6b7
Revises: b1e2f3a4c5d6
Create Date: 2026-09-04
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1e2f3a4c5d6"
branch_labels = None
depends_on = None

# Mirrors app.database.models.DEFAULT_HISTORY_INDEX_EXCLUDES. Copied so the
# migration does not import application code.
DEFAULT_EXCLUDES = [
    "**/.cache/**",
    "**/Library/Caches/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.git/objects/**",
]


def upgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(
            sa.Column("history_index_excludes", sa.JSON(), nullable=True)
        )
    with op.batch_alter_table("system_settings") as batch:
        batch.add_column(sa.Column("history_bootstrap_at", sa.DateTime(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE repositories SET history_index_excludes = :value "
            "WHERE history_index_excludes IS NULL"
        ).bindparams(value=json.dumps(DEFAULT_EXCLUDES))
    )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("history_bootstrap_at")
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("history_index_excludes")
```

- [ ] **Step 5: Run the tests and the migration**

Run: `python -m pytest tests/unit/test_core_features.py tests/unit/test_history_defaults.py tests/unit/test_config.py -q -p no:cacheprovider`
Expected: PASS.

Run: `cd frontend && npx vitest run src/core src/services/planContent.test.ts`
Expected: PASS.

Run: `DATA_DIR=$(mktemp -d) alembic upgrade head && DATA_DIR=$(mktemp -d) alembic downgrade -1`
Expected: both complete without error. If `tests/unit` has a migration test (search for `alembic`), run it too.

Run: `ruff check app tests`
Expected: no findings.

---

### Task 2: Series inference

**Files:**
- Create: `app/services/operations/series.py`
- Modify: `app/services/operations/executors/index.py:36-38` (`series_for`), `:41-45` (`archive_fields_from_listing`), `:91-133` (`apply_listing`)
- Test: `tests/unit/test_series_inference.py`
- Test: `tests/unit/test_operations_index_executors.py` (update the Borg 1 series assertion)

**Interfaces:**
- Consumes: `app.utils.archive_names.build_archive_name(job_name, repo_name, template, timestamp, stable_series=True)`
- Produces:
  - `strip_timestamp(name: str) -> Optional[str]`
  - `template_prefix(template: Optional[str], *, job_name: str, repo_name: Optional[str]) -> Optional[str]`
  - `series_prefixes_for_repository(db, repository) -> list[str]` (longest first)
  - `cron_for_repository(db, repository) -> tuple[Optional[str], Optional[str]]` (cron expression, timezone) used by Task 9
  - `infer_series(name: str, borg_version: int, prefixes: Sequence[str] = ()) -> str`
  - `index.archive_fields_from_listing(entry, borg_version, *, timezone_name, series_prefixes=())`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_series_inference.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    Base,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
)
from app.services.operations.series import (
    cron_for_repository,
    infer_series,
    series_prefixes_for_repository,
    strip_timestamp,
    template_prefix,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("nas-2026-09-02T02:00:00", "nas"),
        ("nas-2026-09-02T02:00:00.123456", "nas"),
        ("nas-2026-09-02_02-00-00", "nas"),
        ("nas-2026-09-02 02:00:00", "nas"),
        ("nas-20260902T020000", "nas"),
        ("nas-20260902_020000", "nas"),
        ("nas-2026-09-02", "nas"),
        ("nas-1756778400", "nas"),
        ("docs-laptop-2026-09-02T02:00:00+02:00", "docs-laptop"),
        ("2026-09-02T02:00:00", None),
        ("nas", None),
    ],
)
def test_strip_timestamp(name, expected):
    assert strip_timestamp(name) == expected


@pytest.mark.unit
def test_template_prefix_drops_time_placeholders():
    assert template_prefix("{job_name}-{now}", job_name="nightly", repo_name="nas") == "nightly"
    assert (
        template_prefix("{repo_name}-{job_name}-{now:%Y%m%d}", job_name="n", repo_name="nas")
        == "nas-n"
    )
    assert template_prefix(None, job_name="nightly", repo_name="nas") == "nightly-nas"
    assert template_prefix("{now}", job_name="x", repo_name=None) == "x"


@pytest.mark.unit
def test_infer_series_prefers_longest_prefix_then_timestamp_then_default():
    prefixes = ["nas", "nas-docs"]
    assert infer_series("nas-docs-2026-09-02T02:00:00", 1, prefixes) == "nas-docs"
    assert infer_series("nas-2026-09-02T02:00:00", 1, prefixes) == "nas"
    assert infer_series("nas", 1, prefixes) == "nas"
    assert infer_series("photos-2026-09-02T02:00:00", 1, prefixes) == "photos"
    assert infer_series("manual", 1, prefixes) == "default"
    assert infer_series("nas-2026-09-02T02:00:00", 2, prefixes) == "nas-2026-09-02T02:00:00"


@pytest.mark.unit
def test_series_prefixes_come_from_schedules_and_plans(db):
    repo = Repository(name="nas", path="/tmp/nas", encryption="none", compression="lz4")
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add_all([repo, other])
    db.commit()
    direct = ScheduledJob(
        name="nightly", cron_expression="0 2 * * *", repository_id=repo.id,
        archive_name_template="{job_name}-{now}",
    )
    linked = ScheduledJob(name="weekly", cron_expression="0 3 * * 0")
    unrelated = ScheduledJob(name="other", cron_expression="0 4 * * *", repository_id=other.id)
    db.add_all([direct, linked, unrelated])
    db.commit()
    db.add(ScheduledJobRepository(scheduled_job_id=linked.id, repository_id=repo.id))
    plan = BackupPlan(name="photos plan", archive_name_template="{plan_name}-{repo_name}-{now}")
    db.add(plan)
    db.commit()
    db.add(BackupPlanRepository(backup_plan_id=plan.id, repository_id=repo.id))
    db.commit()

    prefixes = series_prefixes_for_repository(db, repo)
    assert prefixes == sorted(
        {"nightly", "weekly-nas", "photos-plan-nas"}, key=len, reverse=True
    )
    assert cron_for_repository(db, repo)[0] == "0 2 * * *"
    assert series_prefixes_for_repository(db, other) == ["other-o"]
```

If `ScheduledJob`, `ScheduledJobRepository`, `BackupPlan`, or
`BackupPlanRepository` need more non-null columns than shown, add the
minimal values the model requires; do not change the assertions.

In `tests/unit/test_operations_index_executors.py::test_archive_fields_from_listing_borg1_and_borg2`
change `assert f1["series"] == "default"` to `assert f1["series"] == "nas"`
and add:

```python
    f1p = index_exec.archive_fields_from_listing(
        BORG1_ENTRY, 1, timezone_name="UTC", series_prefixes=["nas"]
    )
    assert f1p["series"] == "nas"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_series_inference.py tests/unit/test_operations_index_executors.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: app.services.operations.series` and the series assertion.

- [ ] **Step 3: Write the series module**

Create `app/services/operations/series.py`:

```python
"""Series inference (spec section 6.6).

Borg 2 names a series directly. For Borg 1 the series is the literal prefix
of a schedule or plan archive name template that targets the repository,
else the archive name with a trailing timestamp stripped, else "default".
"""

import re
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
)
from app.utils.archive_names import build_archive_name

DEFAULT_SERIES = "default"

_TIMESTAMP_SUFFIXES = (
    # 2026-09-02T02:00:00, 2026-09-02_02-00-00, 2026-09-02 02:00:00,
    # optional fraction and zone offset
    re.compile(
        r"[-_.]?\d{4}-\d{2}-\d{2}[T_ -]\d{2}[:\-.]?\d{2}[:\-.]?\d{2}"
        r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
    ),
    # 20260902T020000, 20260902_020000, 20260902-020000
    re.compile(r"[-_.]?\d{8}[T_-]?\d{6}$"),
    # 2026-09-02
    re.compile(r"[-_.]?\d{4}-\d{2}-\d{2}$"),
    # unix epoch seconds
    re.compile(r"[-_.]?\d{10}$"),
)


def strip_timestamp(name: str) -> Optional[str]:
    """Return the name without its trailing timestamp, or None when there is
    no timestamp or nothing would remain."""
    for pattern in _TIMESTAMP_SUFFIXES:
        stripped = pattern.sub("", name, count=1)
        if stripped != name:
            return stripped.rstrip("-_.") or None
    return None


def template_prefix(
    template: Optional[str], *, job_name: str, repo_name: Optional[str]
) -> Optional[str]:
    """The literal prefix backups from this template share: the template
    rendered with its time placeholders removed. Without a template the
    default name builder applies, so the prefix is job (and repo) name."""
    prefix = build_archive_name(
        job_name, repo_name, template, timestamp="", stable_series=True
    )
    return prefix or None


def _schedules_for(db: Session, repository: Repository) -> list[ScheduledJob]:
    direct = (
        db.query(ScheduledJob).filter(ScheduledJob.repository_id == repository.id).all()
    )
    linked_ids = [
        row.scheduled_job_id
        for row in db.query(ScheduledJobRepository.scheduled_job_id)
        .filter(ScheduledJobRepository.repository_id == repository.id)
        .all()
    ]
    linked = (
        db.query(ScheduledJob).filter(ScheduledJob.id.in_(linked_ids)).all()
        if linked_ids
        else []
    )
    seen: set[int] = set()
    result = []
    for job in direct + linked:
        if job.id not in seen:
            seen.add(job.id)
            result.append(job)
    return result


def _plans_for(db: Session, repository: Repository) -> list[BackupPlan]:
    plan_ids = [
        row.backup_plan_id
        for row in db.query(BackupPlanRepository.backup_plan_id)
        .filter(BackupPlanRepository.repository_id == repository.id)
        .all()
    ]
    if not plan_ids:
        return []
    return db.query(BackupPlan).filter(BackupPlan.id.in_(plan_ids)).all()


def series_prefixes_for_repository(db: Session, repository: Repository) -> list[str]:
    """Template prefixes of every schedule and plan targeting the repository,
    longest first so "nas-docs" wins over "nas"."""
    prefixes: set[str] = set()
    for job in _schedules_for(db, repository):
        prefix = template_prefix(
            job.archive_name_template, job_name=job.name, repo_name=repository.name
        )
        if prefix:
            prefixes.add(prefix)
    for plan in _plans_for(db, repository):
        prefix = template_prefix(
            plan.archive_name_template, job_name=plan.name, repo_name=repository.name
        )
        if prefix:
            prefixes.add(prefix)
    return sorted(prefixes, key=len, reverse=True)


def cron_for_repository(
    db: Session, repository: Repository
) -> tuple[Optional[str], Optional[str]]:
    """Cron expression and timezone of the first enabled cron schedule that
    targets the repository, for the missed-run rule (spec 9.5)."""
    for job in _schedules_for(db, repository):
        if job.enabled and job.schedule_mode == "cron" and job.cron_expression:
            return job.cron_expression, getattr(job, "timezone", None)
    return None, None


def infer_series(name: str, borg_version: int, prefixes: Sequence[str] = ()) -> str:
    if borg_version == 2:
        return name
    for prefix in prefixes:
        if name == prefix or name.startswith(prefix + "-"):
            return prefix
    stripped = strip_timestamp(name)
    if stripped:
        return stripped
    return DEFAULT_SERIES
```

Check the timezone attribute name on `ScheduledJob` (the column comment
near `app/database/models.py:789` says "IANA timezone used to interpret
cron_expression"); use that column name instead of `getattr` once known.

- [ ] **Step 4: Wire it into the index executor**

In `app/services/operations/executors/index.py`:

Replace the module docstring's placeholder paragraph with:

```python
"""Index executors: stats and archive_sync (spec sections 8.1 and 8.2).
Series inference follows spec 6.6 through `app.services.operations.series`.
"""
```

Replace `series_for` and the signature of `archive_fields_from_listing`:

```python
from app.services.operations.series import (
    infer_series,
    series_prefixes_for_repository,
)


def series_for(name: str, borg_version: int, prefixes: Sequence[str] = ()) -> str:
    return infer_series(name, borg_version, prefixes)


def archive_fields_from_listing(
    entry: dict,
    borg_version: int,
    *,
    timezone_name: Optional[str],
    series_prefixes: Sequence[str] = (),
) -> Optional[dict]:
```

and inside it `"series": series_for(name, borg_version, series_prefixes),`.
Add `Sequence` to the `typing` import.

In `apply_listing`, before the loop:

```python
    prefixes = series_prefixes_for_repository(db, repository)
```

and pass `series_prefixes=prefixes` to `archive_fields_from_listing`.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/unit/test_series_inference.py tests/unit/test_operations_index_executors.py -q -p no:cacheprovider`
Expected: PASS.

Run: `ruff check app tests`
Expected: no findings.

---

### Task 3: Borg diff wrappers, line streaming, parser, real fixtures

**Files:**
- Create: `app/core/borg_stream.py`
- Create: `app/core/borg_diff.py`
- Modify: `app/core/borg.py:66-150` (extract `_build_exec_env`), add methods after `list_archive_contents` (line 602)
- Modify: `app/core/borg2.py` add methods after `list_archive_contents` (line 506)
- Modify: `app/core/borg_router.py` add methods after `list_archive_contents` (line 434)
- Create: `tests/fixtures/borg_output/README.md`, `borg1_diff.jsonl`, `borg2_diff.jsonl`, `borg1_list.jsonl`, `borg2_list.jsonl`
- Test: `tests/unit/test_borg_stream.py`, `tests/unit/test_borg_diff_parsing.py`

**Interfaces:**
- Produces:
  - `CommandLineStream(cmd: list[str], *, env: Optional[dict] = None, timeout: int = 3600)` async-iterable of `str` lines; after iteration `return_code: Optional[int]`, `stderr: str`; `async close()`
  - `ChangeRecord(path, change, size_before=None, size_after=None, mode_changed=False, owner_changed=False, size_delta=None, is_directory=False)` frozen dataclass; `change` in `added | removed | modified`
  - `parse_diff_line(line: str) -> Optional[ChangeRecord]`, `parse_list_line(line: str) -> Optional[ChangeRecord]`
  - `Borg.diff_archives(repository, archive_a, archive_b, *, remote_path=None, passphrase=None, bypass_lock=False, env=None, timeout=3600) -> CommandLineStream`
  - `Borg.list_archive_lines(repository, archive, *, remote_path=None, passphrase=None, bypass_lock=False, env=None, timeout=3600) -> CommandLineStream`
  - `Borg2.diff_archives(repository, archive_a, archive_b, *, passphrase=None, remote_path=None, env=None, timeout=3600)`, `Borg2.list_archive_lines(repository, archive, *, ...)`
  - `BorgRouter.diff_archives(archive_a: str, archive_b: str, *, env=None, timeout=3600) -> CommandLineStream`, `BorgRouter.list_archive_lines(archive: str, *, env=None, timeout=3600) -> CommandLineStream`. Callers pass `aid:<borg_id>` for Borg 2 and the archive name for Borg 1.

- [ ] **Step 1: Capture fixtures with `borg-live-debug`**

Invoke the `borg-live-debug` skill. Inside the container, for each Borg
version (the container ships both binaries; the skill documents which
command runs which), create a repository and two archives from this tree,
then capture four files. The recipe is fixed so tests can assert on it:

```bash
set -e
export BORG_PASSPHRASE=fixture
W=/tmp/fx; rm -rf $W; mkdir -p $W/src/dir_a $W/src/.cache
printf 'keep\n' > $W/src/keep.txt
printf 'grow\n' > $W/src/grow.txt
printf 'gone\n' > $W/src/gone.txt
printf 'x\n' > $W/src/dir_a/inner.txt
printf 'cached\n' > $W/src/.cache/blob
printf '#!/bin/sh\n' > $W/src/mode.sh
ln -s keep.txt $W/src/link
cd $W
# Borg 1
borg init -e repokey repo1
borg create repo1::first src
borg list --json-lines repo1::first > borg1_list.jsonl
printf 'grow more\n' >> src/grow.txt
rm src/gone.txt
printf 'new\n' > src/new.txt
mkdir src/dir_new; printf 'y\n' > src/dir_new/f.txt
chmod +x src/mode.sh
chown 1000:1000 src/keep.txt
rm src/link; ln -s grow.txt src/link
borg create repo1::second src
borg diff --json-lines repo1::first second > borg1_diff.jsonl
```

Repeat with the Borg 2 binary (`borg2 -r repo2 repo-create -e repokey-aes-ocb`,
`borg2 -r repo2 create first src`, `borg2 -r repo2 list --json-lines first`,
`borg2 -r repo2 diff --json-lines first second`) after resetting `src` to the
first state, writing `borg2_list.jsonl` and `borg2_diff.jsonl`. Copy the four
files into `tests/fixtures/borg_output/` with `docker cp`. Write
`tests/fixtures/borg_output/README.md` recording the Borg versions
(`borg --version`, `borg2 --version`), the date, and the recipe above.

Expected fixture facts, which the tests assert: `borg1_diff.jsonl` and
`borg2_diff.jsonl` each contain lines for `src/grow.txt` (modified),
`src/gone.txt` (removed), `src/new.txt` (added), `src/dir_new` (added
directory), `src/dir_new/f.txt` (added), `src/mode.sh` (mode change),
`src/keep.txt` (owner change), `src/link` (changed link), and no line for
`src/dir_a/inner.txt`. The list fixtures contain `src/keep.txt` with type
`-` and a numeric `size`, `src/dir_a` with type `d`, and `src/link` with
type `l`.

- [ ] **Step 2: Write the failing parser tests**

Create `tests/unit/test_borg_diff_parsing.py`:

```python
import json
from pathlib import Path

import pytest

from app.core.borg_diff import ChangeRecord, parse_diff_line, parse_list_line

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "borg_output"


def _records(name, parser):
    out = {}
    for line in (FIXTURES / name).read_text().splitlines():
        rec = parser(line)
        if rec is not None:
            out[rec.path] = rec
    return out


@pytest.mark.unit
@pytest.mark.parametrize("fixture", ["borg1_diff.jsonl", "borg2_diff.jsonl"])
def test_diff_fixture_maps_every_change_kind(fixture):
    recs = _records(fixture, parse_diff_line)
    grow = recs["src/grow.txt"]
    assert grow.change == "modified"
    assert grow.size_delta == len(b"grow more\n")
    assert grow.size_before is None and grow.size_after is None
    gone = recs["src/gone.txt"]
    assert gone.change == "removed" and gone.size_before == len(b"gone\n")
    new = recs["src/new.txt"]
    assert new.change == "added" and new.size_after == len(b"new\n")
    assert recs["src/dir_new"].change == "added"
    assert recs["src/dir_new"].is_directory is True
    assert recs["src/dir_new/f.txt"].change == "added"
    mode = recs["src/mode.sh"]
    assert mode.change == "modified" and mode.mode_changed is True
    assert mode.size_delta == 0
    keep = recs["src/keep.txt"]
    assert keep.change == "modified" and keep.owner_changed is True
    link = recs["src/link"]
    assert link.change == "modified" and link.size_delta is None
    assert "src/dir_a/inner.txt" not in recs


@pytest.mark.unit
@pytest.mark.parametrize("fixture", ["borg1_list.jsonl", "borg2_list.jsonl"])
def test_list_fixture_maps_entries_to_added_records(fixture):
    recs = _records(fixture, parse_list_line)
    keep = recs["src/keep.txt"]
    assert keep == ChangeRecord("src/keep.txt", "added", size_after=len(b"keep\n"))
    assert recs["src/dir_a"].is_directory is True
    assert recs["src/dir_a"].change == "added"
    link = recs["src/link"]
    assert link.change == "added" and link.size_after is None


@pytest.mark.unit
def test_parse_diff_line_rejects_junk():
    assert parse_diff_line("") is None
    assert parse_diff_line("not json") is None
    assert parse_diff_line(json.dumps({"changes": []})) is None
    assert parse_diff_line(json.dumps({"path": "p", "changes": []})) is None


@pytest.mark.unit
def test_parse_diff_line_prefers_presence_over_modification():
    line = json.dumps(
        {
            "path": "a",
            "changes": [{"type": "mode", "item1": "-rw", "item2": "-rwx"}, {"type": "added", "size": 3}],
        }
    )
    rec = parse_diff_line(line)
    assert rec.change == "added" and rec.size_after == 3 and rec.mode_changed is True


@pytest.mark.unit
def test_parse_diff_line_mtime_only_is_modified_with_zero_delta():
    rec = parse_diff_line(json.dumps({"path": "a", "changes": [{"type": "mtime"}]}))
    assert rec.change == "modified" and rec.size_delta == 0
```

Create `tests/unit/test_borg_stream.py`:

```python
import sys

import pytest

from app.core.borg_stream import CommandLineStream


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_yields_lines_then_exposes_exit_and_stderr():
    stream = CommandLineStream(
        [sys.executable, "-c", "import sys; print('a'); print('b'); sys.stderr.write('warn'); sys.exit(1)"]
    )
    lines = [line async for line in stream]
    assert lines == ["a", "b"]
    assert stream.return_code == 1
    assert stream.stderr == "warn"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_close_terminates_a_running_process():
    stream = CommandLineStream(
        [sys.executable, "-c", "import time; print('a', flush=True); time.sleep(30)"]
    )
    first = None
    async for line in stream:
        first = line
        await stream.close()
        break
    assert first == "a"
    assert stream.return_code is not None and stream.return_code != 0
```

Wrapper tests, appended to `tests/unit/test_borg_diff_parsing.py`:

```python
@pytest.mark.unit
def test_borg1_diff_command_shape(monkeypatch):
    from app.core import borg as borg_module

    captured = {}

    class FakeStream:
        def __init__(self, cmd, *, env=None, timeout=3600):
            captured["cmd"] = cmd
            captured["env"] = env

    monkeypatch.setattr(borg_module, "CommandLineStream", FakeStream)
    b = borg_module.Borg.__new__(borg_module.Borg)
    b.borg_cmd = "borg"
    b.diff_archives("/r", "a1", "a2", remote_path="/opt/borg", passphrase="pw", bypass_lock=True)
    assert captured["cmd"] == [
        "borg", "diff", "--remote-path", "/opt/borg", "--bypass-lock", "--json-lines", "/r::a1", "a2"
    ]
    assert captured["env"]["BORG_PASSPHRASE"] == "pw"
    assert captured["env"]["BORG_LOCK_WAIT"] == "20"
    b.list_archive_lines("/r", "a1")
    assert captured["cmd"] == ["borg", "list", "--json-lines", "/r::a1"]


@pytest.mark.unit
def test_borg2_diff_command_shape(monkeypatch):
    from app.core import borg2 as borg2_module

    captured = {}

    class FakeStream:
        def __init__(self, cmd, *, env=None, timeout=3600):
            captured["cmd"] = cmd
            captured["env"] = env

    monkeypatch.setattr(borg2_module, "CommandLineStream", FakeStream)
    b = borg2_module.Borg2.__new__(borg2_module.Borg2)
    b.borg_cmd = "borg2"
    b.diff_archives("/r", "aid:1", "aid:2", passphrase="pw", remote_path="/opt/borg2")
    assert captured["cmd"] == [
        "borg2", "-r", "/r", "diff", "--json-lines", "--remote-path", "/opt/borg2", "aid:1", "aid:2"
    ]
    assert captured["env"]["BORG_PASSPHRASE"] == "pw"
    b.list_archive_lines("/r", "aid:1")
    assert captured["cmd"] == ["borg2", "-r", "/r", "list", "--json-lines", "aid:1"]
```

If `Borg.__new__` leaves attributes the methods need unset (check
`Borg.__init__` at `app/core/borg.py:21`), set them on the instance in the
test the same way `borg_cmd` is set.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_borg_diff_parsing.py tests/unit/test_borg_stream.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError` for `app.core.borg_diff` and `app.core.borg_stream`.

- [ ] **Step 4: Write the stream runner**

Create `app/core/borg_stream.py`:

```python
"""Line-streaming subprocess runner for Borg commands whose output must not
be buffered whole: `borg diff --json-lines` and `borg list --json-lines` on
large archives (spec 6.7, "diff output is streamed line by line")."""

import asyncio
from typing import AsyncIterator, Optional

# Longest accepted output line. Paths are unbounded in theory; 4 MiB is far
# past anything a filesystem allows.
LINE_LIMIT = 4 * 1024 * 1024


class CommandLineStream:
    """Async iterator over a command's stdout lines.

    After iteration finishes (or `close()` is awaited) `return_code` and
    `stderr` are populated. Iterating twice is not supported.
    """

    def __init__(self, cmd: list[str], *, env: Optional[dict] = None, timeout: int = 3600):
        self.cmd = cmd
        self.env = env
        self.timeout = timeout
        self.return_code: Optional[int] = None
        self.stderr: str = ""
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None

    async def _start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
            limit=LINE_LIMIT,
        )
        # Drain stderr concurrently so a chatty command cannot deadlock on a
        # full pipe while we read stdout.
        self._stderr_task = asyncio.create_task(self._process.stderr.read())

    async def __aiter__(self) -> AsyncIterator[str]:
        await self._start()
        try:
            while True:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=self.timeout
                )
                if not line:
                    break
                yield line.decode("utf-8", errors="replace").rstrip("\r\n")
        finally:
            await self._finish()

    async def _finish(self) -> None:
        if self._process is None:
            return
        if self._process.returncode is None:
            try:
                await asyncio.wait_for(self._process.wait(), timeout=30)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self.return_code = self._process.returncode
        if self._stderr_task is not None:
            self.stderr = (await self._stderr_task).decode("utf-8", errors="replace")

    async def close(self) -> None:
        """Terminate early. Safe to call more than once."""
        if self._process is not None and self._process.returncode is None:
            self._process.kill()
        await self._finish()
```

- [ ] **Step 5: Write the parser**

Create `app/core/borg_diff.py`:

```python
"""Normalise `borg diff --json-lines` and `borg list --json-lines` output
into ChangeRecord values (spec 8.3). Handles Borg 1.2 and Borg 2 shapes,
which differ only in the mode and owner change payload keys that this
parser does not read."""

import json
from dataclasses import dataclass
from typing import Optional

PRESENCE_TYPES = {
    "added": "added",
    "removed": "removed",
    "added directory": "added",
    "removed directory": "removed",
    "added link": "added",
    "removed link": "removed",
}
DIRECTORY_TYPES = {"added directory", "removed directory"}
LINK_TYPES = {"added link", "removed link", "changed link"}


@dataclass(frozen=True)
class ChangeRecord:
    path: str
    change: str  # added | removed | modified
    size_before: Optional[int] = None
    size_after: Optional[int] = None
    mode_changed: bool = False
    owner_changed: bool = False
    # modified regular files only: bytes added minus bytes removed, from
    # borg diff. Absolute sizes are resolved by the executor from the last
    # known size of the path in the series.
    size_delta: Optional[int] = None
    is_directory: bool = False


def _int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_diff_line(line: str) -> Optional[ChangeRecord]:
    data = _load(line)
    if data is None:
        return None
    path = data.get("path")
    changes = data.get("changes")
    if not path or not isinstance(changes, list) or not changes:
        return None
    changes = [c for c in changes if isinstance(c, dict)]
    types = [c.get("type", "") for c in changes]
    flags = {
        "mode_changed": "mode" in types,
        "owner_changed": "owner" in types,
    }
    for c in changes:
        kind = c.get("type", "")
        if kind in PRESENCE_TYPES:
            change = PRESENCE_TYPES[kind]
            size = _int(c.get("size")) if kind in ("added", "removed") else None
            return ChangeRecord(
                path,
                change,
                size_before=size if change == "removed" else None,
                size_after=size if change == "added" else None,
                is_directory=kind in DIRECTORY_TYPES,
                **flags,
            )
    for c in changes:
        if c.get("type") == "modified":
            added = _int(c.get("added")) or 0
            removed = _int(c.get("removed")) or 0
            return ChangeRecord(path, "modified", size_delta=added - removed, **flags)
    if "changed link" in types:
        return ChangeRecord(path, "modified", **flags)
    # Only metadata changed (mode, owner, mtime, ctime): content is the same
    return ChangeRecord(path, "modified", size_delta=0, **flags)


def parse_list_line(line: str) -> Optional[ChangeRecord]:
    """A full listing entry becomes an `added` record (first archive in a
    series, spec 6.5). Only regular files carry a size."""
    data = _load(line)
    if data is None:
        return None
    path = data.get("path")
    if not path:
        return None
    entry_type = data.get("type", "-")
    return ChangeRecord(
        path,
        "added",
        size_after=_int(data.get("size")) if entry_type == "-" else None,
        is_directory=entry_type == "d",
    )
```

If the captured Borg 2 fixture spells a change type differently from the
`PRESENCE_TYPES` keys above (for example a link change reported under
another label), add that spelling to the tables; do not weaken the tests.

- [ ] **Step 6: Add the wrappers**

`app/core/borg.py`: move the environment construction at the top of
`_execute_command` (from `exec_env = os.environ.copy()` through the last
`exec_env[...] = ...` assignment that precedes `asyncio.create_subprocess_exec`,
including the merge of the caller's `env`) into:

```python
    def _build_exec_env(self, env: dict = None) -> dict:
        """Process environment for a borg invocation: the inherited environment,
        the lock and hostname settings every call needs, and the caller's
        overrides on top."""
```

and call `exec_env = self._build_exec_env(env)` from `_execute_command`
(and from `_execute_command_streaming` if it duplicates the same block).
Run the existing borg tests after the extraction:
`python -m pytest tests/unit -q -k "borg and not integration" -p no:cacheprovider`.

Then add, after `list_archive_contents`:

```python
    def diff_archives(
        self,
        repository: str,
        archive_a: str,
        archive_b: str,
        *,
        remote_path: str = None,
        passphrase: str = None,
        bypass_lock: bool = False,
        env: dict = None,
        timeout: int = 3600,
    ) -> CommandLineStream:
        """Stream `borg diff --json-lines` between two archives (spec 8.3)."""
        cmd = [self.borg_cmd, "diff"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if bypass_lock:
            cmd.append("--bypass-lock")
        cmd.extend(["--json-lines", f"{repository}::{archive_a}", archive_b])
        exec_env = self._build_exec_env(env)
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return CommandLineStream(cmd, env=exec_env, timeout=timeout)

    def list_archive_lines(
        self,
        repository: str,
        archive: str,
        *,
        remote_path: str = None,
        passphrase: str = None,
        bypass_lock: bool = False,
        env: dict = None,
        timeout: int = 3600,
    ) -> CommandLineStream:
        """Stream `borg list --json-lines` for one archive (first archive of a
        series, spec 8.3)."""
        cmd = [self.borg_cmd, "list"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if bypass_lock:
            cmd.append("--bypass-lock")
        cmd.extend(["--json-lines", f"{repository}::{archive}"])
        exec_env = self._build_exec_env(env)
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return CommandLineStream(cmd, env=exec_env, timeout=timeout)
```

with `from app.core.borg_stream import CommandLineStream` at the top.

`app/core/borg2.py`, after `list_archive_contents` (Borg 2 has no
`--bypass-lock`, see its `list_archives`):

```python
    def diff_archives(
        self,
        repository: str,
        archive_a: str,
        archive_b: str,
        *,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
        timeout: int = 3600,
    ) -> CommandLineStream:
        cmd = [self.borg_cmd, "-r", repository, "diff", "--json-lines"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend([archive_a, archive_b])
        exec_env = self._base_env(env)
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return CommandLineStream(cmd, env=exec_env, timeout=timeout)

    def list_archive_lines(
        self,
        repository: str,
        archive: str,
        *,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
        timeout: int = 3600,
    ) -> CommandLineStream:
        cmd = [self.borg_cmd, "-r", repository, "list", "--json-lines"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.append(archive)
        exec_env = self._base_env(env)
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return CommandLineStream(cmd, env=exec_env, timeout=timeout)
```

`app/core/borg_router.py`, after `list_archive_contents`:

```python
    def diff_archives(
        self, archive_a: str, archive_b: str, *, env: dict = None, timeout: int = 3600
    ):
        """Stream diff lines. Pass `aid:<id>` references for Borg 2 and
        archive names for Borg 1."""
        if self.is_v2:
            from app.core.borg2 import borg2

            return borg2.diff_archives(
                self.repo.path,
                archive_a,
                archive_b,
                passphrase=self.repo.passphrase,
                remote_path=effective_repository_remote_path(self.repo),
                env=env,
                timeout=timeout,
            )
        from app.core.borg import borg

        return borg.diff_archives(
            self.repo.path,
            archive_a,
            archive_b,
            remote_path=effective_repository_remote_path(self.repo),
            passphrase=self.repo.passphrase,
            bypass_lock=self.repo.bypass_lock,
            env=env,
            timeout=timeout,
        )

    def list_archive_lines(self, archive: str, *, env: dict = None, timeout: int = 3600):
        if self.is_v2:
            from app.core.borg2 import borg2

            return borg2.list_archive_lines(
                self.repo.path,
                archive,
                passphrase=self.repo.passphrase,
                remote_path=effective_repository_remote_path(self.repo),
                env=env,
                timeout=timeout,
            )
        from app.core.borg import borg

        return borg.list_archive_lines(
            self.repo.path,
            archive,
            remote_path=effective_repository_remote_path(self.repo),
            passphrase=self.repo.passphrase,
            bypass_lock=self.repo.bypass_lock,
            env=env,
            timeout=timeout,
        )
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/unit/test_borg_diff_parsing.py tests/unit/test_borg_stream.py -q -p no:cacheprovider`
Expected: PASS.

Run: `python -m pytest tests/unit -q -x -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings.

---

### Task 4: The fold (spec 8.4 table) and fold-across-archives

**Files:**
- Create: `app/services/operations/history_fold.py`
- Test: `tests/unit/test_changes_fold.py`

**Interfaces:**
- Produces:
  - `Change(path, change, size_before=None, size_after=None, mode_changed=False, owner_changed=False, summary_count=None)` dataclass; `change` in `added | removed | modified | summary`
  - `fold_pair(older: dict[str, Change], newer: dict[str, Change]) -> dict[str, Change]`
  - `fold_sequence(deltas: Iterable[dict[str, Change]]) -> dict[str, Change]`
  - `change_from_row(row: ArchiveChange) -> Change`, `rows_to_changes(rows: Iterable[ArchiveChange]) -> dict[str, Change]`, `change_to_row_dict(change: Change, archive_id: int) -> dict`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_changes_fold.py`:

```python
import pytest

from app.services.operations.history_fold import Change, fold_pair, fold_sequence


def _d(*changes):
    return {c.path: c for c in changes}


@pytest.mark.unit
class TestFoldTable:
    """One test per row of the spec 8.4 table."""

    def test_added_then_nothing_copies(self):
        r = Change("a", "added", size_after=3)
        assert fold_pair(_d(r), {}) == _d(r)

    def test_added_then_modified_is_added_with_new_size(self):
        out = fold_pair(
            _d(Change("a", "added", size_after=3)),
            _d(Change("a", "modified", size_before=3, size_after=5, mode_changed=True)),
        )
        assert out["a"] == Change("a", "added", size_before=None, size_after=5, mode_changed=True)

    def test_added_then_removed_disappears(self):
        out = fold_pair(
            _d(Change("a", "added", size_after=3)),
            _d(Change("a", "removed", size_before=3)),
        )
        assert "a" not in out

    def test_modified_then_nothing_copies(self):
        r = Change("a", "modified", size_before=1, size_after=2)
        assert fold_pair(_d(r), {}) == _d(r)

    def test_modified_then_modified_keeps_first_size_before(self):
        out = fold_pair(
            _d(Change("a", "modified", size_before=1, size_after=2)),
            _d(Change("a", "modified", size_before=2, size_after=9, owner_changed=True)),
        )
        assert out["a"] == Change("a", "modified", size_before=1, size_after=9, owner_changed=True)

    def test_modified_then_removed_keeps_first_size_before(self):
        out = fold_pair(
            _d(Change("a", "modified", size_before=1, size_after=2)),
            _d(Change("a", "removed", size_before=2)),
        )
        assert out["a"] == Change("a", "removed", size_before=1)

    def test_removed_then_nothing_copies(self):
        r = Change("a", "removed", size_before=4)
        assert fold_pair(_d(r), {}) == _d(r)

    def test_removed_then_added_is_modified(self):
        out = fold_pair(
            _d(Change("a", "removed", size_before=4)),
            _d(Change("a", "added", size_after=7)),
        )
        assert out["a"] == Change("a", "modified", size_before=4, size_after=7)

    def test_summary_then_any_keeps_newer_and_adds_count(self):
        out = fold_pair(
            _d(Change("x/y/z", "summary", summary_count=10)),
            _d(Change("x/y/z", "summary", summary_count=5)),
        )
        assert out["x/y/z"] == Change("x/y/z", "summary", summary_count=15)
        out = fold_pair(_d(Change("x/y/z", "summary", summary_count=10)), {})
        assert out["x/y/z"].summary_count == 10

    def test_flags_are_ored(self):
        out = fold_pair(
            _d(Change("a", "modified", mode_changed=True)),
            _d(Change("a", "modified", owner_changed=True)),
        )
        assert out["a"].mode_changed and out["a"].owner_changed

    def test_untouched_newer_rows_survive(self):
        newer = _d(Change("b", "added", size_after=1))
        assert fold_pair({}, newer) == newer


@pytest.mark.unit
def test_fold_sequence_equals_direct_diff_of_endpoints():
    """Three archives: A1 full listing, A2 and A3 deltas. Folding A2 into A3
    must equal a direct A1 to A3 diff; folding all three must equal a full
    listing of A3 (spec 12, test_changes_fold)."""
    a1 = _d(
        Change("a", "added", size_after=10),
        Change("b", "added", size_after=3),
        Change("c", "added", size_after=8),
    )
    a2 = _d(
        Change("a", "modified", size_before=10, size_after=12),
        Change("b", "removed", size_before=3),
        Change("d", "added", size_after=5),
    )
    a3 = _d(
        Change("a", "modified", size_before=12, size_after=20),
        Change("b", "added", size_after=7),
        Change("d", "removed", size_before=5),
        Change("c", "modified", size_before=8, size_after=8, mode_changed=True),
    )
    direct_a1_a3 = _d(
        Change("a", "modified", size_before=10, size_after=20),
        Change("b", "modified", size_before=3, size_after=7),
        Change("c", "modified", size_before=8, size_after=8, mode_changed=True),
    )
    assert fold_sequence([a2, a3]) == direct_a1_a3
    full_a3 = _d(
        Change("a", "added", size_after=20),
        Change("b", "added", size_after=7),
        Change("c", "added", size_after=8, mode_changed=True),
    )
    assert fold_sequence([a1, a2, a3]) == full_a3
    assert fold_sequence([]) == {}
    assert fold_sequence([a1]) == a1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_changes_fold.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: app.services.operations.history_fold`.

- [ ] **Step 3: Write the fold module**

Create `app/services/operations/history_fold.py`:

```python
"""Fold one archive's change delta into the delta that follows it
(spec section 8.4). Used by history_merge when a pruned archive's rows move
to its successor, and by the changes route when `compare_to` is older than
the predecessor (spec 9.2). Pure functions over plain values."""

from dataclasses import dataclass, replace
from typing import Iterable, Optional

from app.database.models import ArchiveChange


@dataclass(frozen=True)
class Change:
    path: str
    change: str  # added | removed | modified | summary
    size_before: Optional[int] = None
    size_after: Optional[int] = None
    mode_changed: bool = False
    owner_changed: bool = False
    summary_count: Optional[int] = None


def _flags(older: Change, newer: Change) -> dict:
    return {
        "mode_changed": older.mode_changed or newer.mode_changed,
        "owner_changed": older.owner_changed or newer.owner_changed,
    }


def fold_pair(older: dict[str, Change], newer: dict[str, Change]) -> dict[str, Change]:
    """Return the delta from older's base to newer's target.

    Rows follow the spec 8.4 table. Pairs the table does not list cannot
    occur in a consistent sequence (added after added, removed after
    removed, added after modified, modified after removed); newer wins for
    those so a corrupt history never raises.
    """
    result: dict[str, Change] = dict(newer)
    for path, r in older.items():
        s = newer.get(path)
        if r.change == "summary":
            if s is None:
                result[path] = r
            else:
                result[path] = replace(
                    s, summary_count=(s.summary_count or 0) + (r.summary_count or 0)
                )
            continue
        if s is None:
            result[path] = r
            continue
        if s.change == "summary":
            continue
        flags = _flags(r, s)
        if r.change == "added":
            if s.change == "modified":
                result[path] = replace(s, change="added", size_before=None, **flags)
            elif s.change == "removed":
                del result[path]
        elif r.change == "modified":
            if s.change in ("modified", "removed"):
                result[path] = replace(s, size_before=r.size_before, **flags)
        elif r.change == "removed":
            if s.change == "added":
                result[path] = replace(
                    s,
                    change="modified",
                    size_before=r.size_before,
                    size_after=s.size_after,
                    **flags,
                )
    return result


def fold_sequence(deltas: Iterable[dict[str, Change]]) -> dict[str, Change]:
    result: Optional[dict[str, Change]] = None
    for delta in deltas:
        result = delta if result is None else fold_pair(result, delta)
    return result if result is not None else {}


def change_from_row(row: ArchiveChange) -> Change:
    return Change(
        path=row.path,
        change=row.change,
        size_before=row.size_before,
        size_after=row.size_after,
        mode_changed=bool(row.mode_changed),
        owner_changed=bool(row.owner_changed),
        summary_count=row.summary_count,
    )


def rows_to_changes(rows: Iterable[ArchiveChange]) -> dict[str, Change]:
    return {row.path: change_from_row(row) for row in rows}


def change_to_row_dict(change: Change, archive_id: int) -> dict:
    """Mapping for `Session.bulk_insert_mappings(ArchiveChange, ...)`."""
    return {
        "archive_id": archive_id,
        "path": change.path,
        "change": change.change,
        "size_before": change.size_before,
        "size_after": change.size_after,
        "mode_changed": change.mode_changed,
        "owner_changed": change.owner_changed,
        "summary_count": change.summary_count,
    }
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_changes_fold.py -q -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings.

---

### Task 5: `history_index` executor

**Files:**
- Create: `app/services/operations/executors/history.py`
- Modify: `app/services/operations/executors/__init__.py:24-27` (`load_default_executors`)
- Test: `tests/unit/test_history_index.py`

**Interfaces:**
- Consumes: `ChangeRecord`, `parse_diff_line`, `parse_list_line` (Task 3); `BorgRouter.diff_archives` / `list_archive_lines` (Task 3); `change_to_row_dict` (Task 4); `settings.index_history_max_rows` (Task 1); `Repository.history_index_excludes` (Task 1); `_prepare_repository_borg_env`, `run_serialized_repository_command`, `is_agent_executor`, `Outcome` as used in `executors/index.py`
- Produces:
  - `glob_to_regex(pattern: str) -> re.Pattern`, `compile_excludes(patterns: Optional[list[str]]) -> list[re.Pattern]`, `is_excluded(path: str, compiled: list[re.Pattern]) -> bool`
  - `summary_prefix(path: str) -> str` (first three segments)
  - `RowCollector(archive_id: int, max_rows: int)` with `add(record, size_before, size_after)`, `detail: list[dict]`, `summary_rows() -> list[dict]`, `truncated: bool`, `count: int`
  - `known_sizes(db, repository_id, series, before_start, paths: Iterable[str]) -> dict[str, int]`
  - `predecessor_of(db, archive) -> Optional[Archive]`, `successor_of(db, archive) -> Optional[Archive]`
  - `archive_ref(repository, archive) -> str`
  - `collect_changes(ctx, db, repository, archive, predecessor, env, excludes, max_rows) -> RowCollector`
  - `write_archive_rows(db, archive, collector: RowCollector) -> None` (one transaction)
  - `run_history_index(ctx) -> Outcome` registered as `history_index`
  - `OperationCancelled` exception

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_history_index.py`:

```python
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, ArchiveChange, Base, Repository, SystemSettings
from app.services.operations.executors import history


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


def _archive(db, repo, name, day, series="nas", state="pending"):
    a = Archive(
        repository_id=repo.id, borg_id=f"id-{name}", name=name, series=series,
        start=datetime(2026, 9, day, 2, 0, 0), history_state=state,
    )
    db.add(a)
    db.commit()
    return a


def _ctx(db, repo, cancelled=False):
    return SimpleNamespace(
        db=db, repository_id=repo.id, operation_id=1, kind="history_index",
        params={}, operation=SimpleNamespace(depends_on_id=None),
        progress=AsyncMock(), log=lambda line: None, cancelled=lambda: cancelled,
    )


class FakeStream:
    def __init__(self, lines, return_code=0, stderr=""):
        self._lines = lines
        self.return_code = None
        self.stderr = ""
        self._rc = return_code
        self._stderr = stderr
        self.closed = False

    async def __aiter__(self):
        for line in self._lines:
            yield line
        self.return_code = self._rc
        self.stderr = self._stderr

    async def close(self):
        self.closed = True
        self.return_code = -9


class FakeRouter:
    """Maps (a, b) diff refs and list refs to canned lines."""

    lists: dict = {}
    diffs: dict = {}

    def __init__(self, repository):
        self.repository = repository

    def list_archive_lines(self, archive, *, env=None, timeout=3600):
        return FakeStream(self.lists[archive])

    def diff_archives(self, a, b, *, env=None, timeout=3600):
        value = self.diffs[(a, b)]
        return value if isinstance(value, FakeStream) else FakeStream(value)


L = lambda path, size=None, t="-": f'{{"type": "{t}", "path": "{path}", "size": {size if size is not None else "null"}}}'
D_MOD = lambda path, added, removed: f'{{"path": "{path}", "changes": [{{"type": "modified", "added": {added}, "removed": {removed}}}]}}'
D_ADD = lambda path, size: f'{{"path": "{path}", "changes": [{{"type": "added", "size": {size}}}]}}'
D_RM = lambda path, size: f'{{"path": "{path}", "changes": [{{"type": "removed", "size": {size}}}]}}'


@pytest.fixture(autouse=True)
def _patches():
    with patch.object(history, "_prepare_repository_borg_env", return_value=({}, None)), patch.object(
        history, "BorgRouter", FakeRouter
    ), patch.object(history, "history_enabled", return_value=True):
        FakeRouter.lists = {}
        FakeRouter.diffs = {}
        yield


@pytest.mark.unit
def test_glob_excludes():
    compiled = history.compile_excludes(["**/node_modules/**", "*.log", "home/*/tmp/**"])
    assert history.is_excluded("app/node_modules/x/y.js", compiled)
    assert history.is_excluded("node_modules/y.js", compiled)
    assert history.is_excluded("a.log", compiled)
    assert not history.is_excluded("dir/a.log", compiled)
    assert history.is_excluded("home/k/tmp/f", compiled)
    assert not history.is_excluded("home/k/tmp", compiled)
    assert history.compile_excludes(None) == []


@pytest.mark.unit
def test_summary_prefix():
    assert history.summary_prefix("a/b/c/d/e") == "a/b/c"
    assert history.summary_prefix("a") == "a"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_first_archive_gets_full_listing_without_directories_or_excludes(db, repo):
    a1 = _archive(db, repo, "first", 1)
    FakeRouter.lists["first"] = [L("src", t="d"), L("src/a.txt", 5), L("src/.cache/x", 1), L("src/link", t="l")]
    out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "completed" and out.result == {"indexed": 1, "failed": 0, "left_pending": 0}
    db.refresh(a1)
    assert a1.history_state == "indexed" and a1.history_rows == 2 and a1.history_truncated is False
    rows = {r.path: r for r in db.query(ArchiveChange).filter_by(archive_id=a1.id)}
    assert set(rows) == {"src/a.txt", "src/link"}
    assert rows["src/a.txt"].change == "added" and rows["src/a.txt"].size_after == 5
    assert rows["src/link"].size_after is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pair_diff_resolves_sizes_from_last_known(db, repo):
    a1 = _archive(db, repo, "first", 1, state="indexed")
    db.add(ArchiveChange(archive_id=a1.id, path="src/a.txt", change="added", size_after=10))
    db.commit()
    a2 = _archive(db, repo, "second", 2)
    FakeRouter.diffs[("first", "second")] = [D_MOD("src/a.txt", 7, 2), D_ADD("src/n.txt", 3), D_RM("src/g.txt", 4), D_MOD("src/unknown.txt", 1, 0)]
    out = await history.run_history_index(_ctx(db, repo))
    assert out.result["indexed"] == 1
    rows = {r.path: r for r in db.query(ArchiveChange).filter_by(archive_id=a2.id)}
    assert (rows["src/a.txt"].size_before, rows["src/a.txt"].size_after) == (10, 15)
    assert rows["src/n.txt"].size_after == 3 and rows["src/g.txt"].size_before == 4
    assert (rows["src/unknown.txt"].size_before, rows["src/unknown.txt"].size_after) == (None, None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_predecessor_not_indexed_leaves_archive_pending(db, repo):
    _archive(db, repo, "first", 1, state="failed")
    a2 = _archive(db, repo, "second", 2)
    out = await history.run_history_index(_ctx(db, repo))
    assert out.result == {"indexed": 0, "failed": 0, "left_pending": 1}
    db.refresh(a2)
    assert a2.history_state == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cap_collapses_overflow_into_summary_rows(db, repo, monkeypatch):
    monkeypatch.setattr(history.settings, "index_history_max_rows", 2)
    a1 = _archive(db, repo, "first", 1)
    FakeRouter.lists["first"] = [L("a/b/c/1", 1), L("a/b/c/2", 1), L("a/b/c/3", 1), L("a/b/d/4", 1), L("x", 1)]
    await history.run_history_index(_ctx(db, repo))
    db.refresh(a1)
    assert a1.history_truncated is True and a1.history_rows == 5
    summaries = {r.path: r.summary_count for r in db.query(ArchiveChange).filter_by(archive_id=a1.id, change="summary")}
    assert summaries == {"a/b/c": 1, "a/b/d": 1, "x": 1}
    assert db.query(ArchiveChange).filter_by(archive_id=a1.id).filter(ArchiveChange.change != "summary").count() == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_repository_skips_all_pending(db, repo):
    a1 = _archive(db, repo, "first", 1)
    with patch.object(history, "is_agent_executor", return_value=True):
        out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "skipped" and out.skip_reason == "agent_diff_unsupported"
    db.refresh(a1)
    assert a1.history_state == "skipped"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg_failure_marks_archive_failed_and_warns(db, repo):
    a1 = _archive(db, repo, "first", 1, state="indexed")
    a2 = _archive(db, repo, "second", 2)
    FakeRouter.diffs[("first", "second")] = FakeStream([D_ADD("x", 1)], return_code=2, stderr="lock held")
    out = await history.run_history_index(_ctx(db, repo))
    assert out.status == "completed_with_warnings" and out.result["failed"] == 1
    db.refresh(a2)
    assert a2.history_state == "failed"
    assert db.query(ArchiveChange).filter_by(archive_id=a2.id).count() == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_stops_between_archives(db, repo):
    _archive(db, repo, "first", 1)
    FakeRouter.lists["first"] = [L("a", 1)]
    out = await history.run_history_index(_ctx(db, repo, cancelled=True))
    assert out.result["indexed"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg2_uses_aid_references(db, repo):
    repo.borg_version = 2
    db.commit()
    a1 = _archive(db, repo, "nas", 1, state="indexed")
    a2 = _archive(db, repo, "nas", 2)
    FakeRouter.diffs[(f"aid:{a1.borg_id}", f"aid:{a2.borg_id}")] = [D_ADD("x", 1)]
    out = await history.run_history_index(_ctx(db, repo))
    assert out.result["indexed"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_progress_reports_pair_label(db, repo):
    _archive(db, repo, "first", 1, state="indexed")
    _archive(db, repo, "second", 2)
    FakeRouter.diffs[("first", "second")] = []
    ctx = _ctx(db, repo)
    await history.run_history_index(ctx)
    messages = [c.kwargs.get("message") for c in ctx.progress.await_args_list]
    assert "first → second" in messages


@pytest.mark.unit
def test_registered():
    from app.services.operations.executors import load_default_executors, registered_kinds

    load_default_executors()
    assert {"history_index", "history_merge"} <= registered_kinds()
```

`test_registered` also covers Task 6; it fails until both executors exist.
The `progress` label uses the arrow character per spec 8.3.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_history_index.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError` for `app.services.operations.executors.history`.

- [ ] **Step 3: Write the executor module (index half)**

Create `app/services/operations/executors/history.py`:

```python
"""History executors: history_index and history_merge (spec 8.3, 8.4, 6.7).

history_index streams `borg diff` per (predecessor, archive) pair, or a
full `borg list` for the first archive of a series, drops excluded paths,
resolves absolute sizes for modified files from the last known size in the
series, caps rows per archive, and writes each archive in one transaction.
history_merge folds a removed archive's rows into its successor.
"""

import asyncio
import re
from collections import Counter
from typing import Iterable, Optional

import structlog
from sqlalchemy.orm import Session

from app.api.repositories import _prepare_repository_borg_env
from app.config import settings
from app.core.borg_diff import ChangeRecord, parse_diff_line, parse_list_line
from app.core.borg_router import BorgRouter
from app.database.models import Archive, ArchiveChange, Operation, Repository, utc_now
from app.services.operations import executors
from app.services.operations.followups import history_enabled
from app.services.operations.history_fold import (
    change_to_row_dict,
    fold_pair,
    rows_to_changes,
)
from app.services.operations.runner import Outcome
from app.services.repository_command_lock import run_serialized_repository_command
from app.services.repository_executor import is_agent_executor
from app.utils.borg_env import cleanup_temp_key_file

logger = structlog.get_logger()

BATCH_SIZE = 5000
SUMMARY_DEPTH = 3
SIZE_LOOKUP_CHUNK = 500
# borg exits 1 for warnings; the diff is still complete
BORG_OK_EXIT_CODES = (0, 1)


class OperationCancelled(Exception):
    pass


# -- excludes -------------------------------------------------------------------


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a glob with `**` (any depth), `*` (one segment), `?` into a
    regex anchored to the whole path. A leading `**/` matches zero or more
    directories so `**/.cache/**` covers `.cache/x` at the root too."""
    out = ""
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile(f"^{out}$")


def compile_excludes(patterns: Optional[list[str]]) -> list[re.Pattern]:
    return [glob_to_regex(p) for p in (patterns or []) if p]


def is_excluded(path: str, compiled: list[re.Pattern]) -> bool:
    return any(rx.match(path) for rx in compiled)


def summary_prefix(path: str) -> str:
    return "/".join(path.split("/")[:SUMMARY_DEPTH])


# -- row collection -------------------------------------------------------------


class RowCollector:
    """Rows for one archive with the spec 6.7 cap applied on the fly."""

    def __init__(self, archive_id: int, max_rows: int):
        self.archive_id = archive_id
        self.max_rows = max_rows
        self.detail: list[dict] = []
        self.overflow: Counter = Counter()
        self.count = 0

    def add(self, record: ChangeRecord, size_before: Optional[int], size_after: Optional[int]) -> None:
        self.count += 1
        if len(self.detail) < self.max_rows:
            self.detail.append(
                {
                    "archive_id": self.archive_id,
                    "path": record.path,
                    "change": record.change,
                    "size_before": size_before,
                    "size_after": size_after,
                    "mode_changed": record.mode_changed,
                    "owner_changed": record.owner_changed,
                    "summary_count": None,
                }
            )
        else:
            self.overflow[summary_prefix(record.path)] += 1

    @property
    def truncated(self) -> bool:
        return bool(self.overflow)

    def summary_rows(self) -> list[dict]:
        return [
            {
                "archive_id": self.archive_id,
                "path": prefix,
                "change": "summary",
                "size_before": None,
                "size_after": None,
                "mode_changed": False,
                "owner_changed": False,
                "summary_count": n,
            }
            for prefix, n in sorted(self.overflow.items())
        ]


def known_sizes(
    db: Session, repository_id: int, series: str, before_start, paths: Iterable[str]
) -> dict[str, int]:
    """Last known size of each path in earlier archives of the series."""
    paths = list(dict.fromkeys(paths))
    result: dict[str, int] = {}
    for i in range(0, len(paths), SIZE_LOOKUP_CHUNK):
        chunk = paths[i : i + SIZE_LOOKUP_CHUNK]
        rows = (
            db.query(ArchiveChange.path, ArchiveChange.size_after)
            .join(Archive, Archive.id == ArchiveChange.archive_id)
            .filter(
                Archive.repository_id == repository_id,
                Archive.series == series,
                Archive.start < before_start,
                ArchiveChange.path.in_(chunk),
                ArchiveChange.change.in_(("added", "modified")),
                ArchiveChange.size_after.isnot(None),
            )
            .order_by(Archive.start.desc())
            .all()
        )
        for path, size in rows:
            result.setdefault(path, size)
    return result


# -- archive neighbours ---------------------------------------------------------


def predecessor_of(db: Session, archive: Archive) -> Optional[Archive]:
    return (
        db.query(Archive)
        .filter(
            Archive.repository_id == archive.repository_id,
            Archive.series == archive.series,
            Archive.start < archive.start,
        )
        .order_by(Archive.start.desc(), Archive.id.desc())
        .first()
    )


def successor_of(db: Session, archive: Archive) -> Optional[Archive]:
    return (
        db.query(Archive)
        .filter(
            Archive.repository_id == archive.repository_id,
            Archive.series == archive.series,
            Archive.start > archive.start,
        )
        .order_by(Archive.start.asc(), Archive.id.asc())
        .first()
    )


def archive_ref(repository: Repository, archive: Archive) -> str:
    return f"aid:{archive.borg_id}" if (repository.borg_version or 1) == 2 else archive.name


# -- collecting one archive -----------------------------------------------------


async def collect_changes(
    ctx,
    db: Session,
    repository: Repository,
    archive: Archive,
    predecessor: Optional[Archive],
    env: dict,
    excludes: list[re.Pattern],
    max_rows: int,
) -> RowCollector:
    router = BorgRouter(repository)
    if predecessor is None:
        stream = router.list_archive_lines(archive_ref(repository, archive), env=env)
        parser = parse_list_line
    else:
        stream = router.diff_archives(
            archive_ref(repository, predecessor), archive_ref(repository, archive), env=env
        )
        parser = parse_diff_line
    collector = RowCollector(archive.id, max_rows)
    pending_modified: list[ChangeRecord] = []

    def flush_modified() -> None:
        if not pending_modified:
            return
        sizes = known_sizes(
            db, repository.id, archive.series, archive.start, (r.path for r in pending_modified)
        )
        for rec in pending_modified:
            before = sizes.get(rec.path)
            after = before + rec.size_delta if before is not None else None
            collector.add(rec, before, after)
        pending_modified.clear()

    async for line in stream:
        if ctx.cancelled():
            await stream.close()
            raise OperationCancelled()
        rec = parser(line)
        if rec is None or rec.is_directory or is_excluded(rec.path, excludes):
            continue
        if rec.change == "modified" and rec.size_delta is not None:
            pending_modified.append(rec)
            if len(pending_modified) >= SIZE_LOOKUP_CHUNK:
                flush_modified()
        else:
            collector.add(rec, rec.size_before, rec.size_after)
    flush_modified()
    if stream.return_code not in BORG_OK_EXIT_CODES:
        raise RuntimeError(
            f"borg exited {stream.return_code}: {(stream.stderr or '').strip()[-500:]}"
        )
    return collector


def write_archive_rows(db: Session, archive: Archive, collector: RowCollector) -> None:
    """Replace the archive's rows and mark it indexed, in one transaction."""
    db.query(ArchiveChange).filter(ArchiveChange.archive_id == archive.id).delete(
        synchronize_session=False
    )
    for i in range(0, len(collector.detail), BATCH_SIZE):
        db.bulk_insert_mappings(ArchiveChange, collector.detail[i : i + BATCH_SIZE])
    summaries = collector.summary_rows()
    if summaries:
        db.bulk_insert_mappings(ArchiveChange, summaries)
    archive.history_state = "indexed"
    archive.history_indexed_at = utc_now()
    archive.history_rows = len(collector.detail) + len(summaries)
    archive.history_truncated = collector.truncated
    db.commit()


# -- executor: history_index ----------------------------------------------------


def _load_repository(ctx) -> Optional[Repository]:
    if ctx.repository_id is None:
        return None
    return ctx.db.get(Repository, ctx.repository_id)


async def run_history_index(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    if not history_enabled(db):
        return Outcome(status="skipped", skip_reason="plan_locked")
    pending = (
        db.query(Archive)
        .filter(Archive.repository_id == repository.id, Archive.history_state == "pending")
        .order_by(Archive.series.asc(), Archive.start.asc(), Archive.id.asc())
        .all()
    )
    if is_agent_executor(repository):
        for archive in pending:
            archive.history_state = "skipped"
        db.commit()
        return Outcome(
            status="skipped",
            skip_reason="agent_diff_unsupported",
            result={"archives": len(pending)},
        )
    if not pending:
        return Outcome(result={"indexed": 0, "failed": 0, "left_pending": 0})
    excludes = compile_excludes(repository.history_index_excludes)
    max_rows = settings.index_history_max_rows
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    indexed = failed = left = 0
    total = len(pending)
    try:
        for position, archive in enumerate(pending):
            if ctx.cancelled():
                break
            predecessor = predecessor_of(db, archive)
            if predecessor is not None and predecessor.history_state != "indexed":
                left += 1
                continue
            label = f"{predecessor.name if predecessor else 'full listing'} → {archive.name}"
            await ctx.progress(current=position, total=total, message=label)
            try:
                collector = await run_serialized_repository_command(
                    repository.id,
                    lambda: collect_changes(
                        ctx, db, repository, archive, predecessor, env, excludes, max_rows
                    ),
                    scope="metadata",
                )
                write_archive_rows(db, archive, collector)
                indexed += 1
                ctx.log(f"{label}: {collector.count} changes, truncated={collector.truncated}")
                # Let other coroutines (SSE, API) run between archives
                await asyncio.sleep(0)
            except OperationCancelled:
                db.rollback()
                break
            except Exception as exc:
                db.rollback()
                archive.history_state = "failed"
                db.commit()
                failed += 1
                ctx.log(f"{label}: failed: {exc}")
                logger.warning(
                    "history index failed for archive",
                    repository_id=repository.id,
                    archive=archive.name,
                    error=str(exc),
                )
        await ctx.progress(current=total, total=total, message=f"{indexed} indexed")
        status = "completed_with_warnings" if failed else "completed"
        return Outcome(
            status=status,
            result={"indexed": indexed, "failed": failed, "left_pending": left},
        )
    finally:
        cleanup_temp_key_file(temp_key_file)
```

`executors.register("history_index", run_history_index)` goes at the
bottom of the module together with the merge registration from Task 6.
Until Task 6 exists, register only `history_index` so the module imports.

In `app/services/operations/executors/__init__.py`:

```python
def load_default_executors() -> None:
    """Import executor modules for their registration side effect."""
    from app.services.operations.executors import history, index  # noqa: F401
```

`history_enabled` is added to `followups.py` in Task 7. For this task add
the function now (Task 7 then only adds its callers):

```python
def history_enabled(db) -> bool:
    """True when the current plan includes the archive_history feature
    (spec 11.2). Imported lazily: app.core.features pulls in the licensing
    service, which must not be an import-time dependency of the runner."""
    from app.core.features import Plan, get_current_plan, plan_includes

    return plan_includes(get_current_plan(db), Plan.PRO)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_history_index.py -q -p no:cacheprovider`
Expected: PASS except `test_registered` (needs Task 6).

Run: `python -m pytest tests/unit -q -x -p no:cacheprovider --deselect tests/unit/test_history_index.py::test_registered && ruff check app tests`
Expected: PASS, no findings.

---

### Task 6: `history_merge` executor

**Files:**
- Modify: `app/services/operations/executors/history.py` (append the merge half)
- Test: `tests/unit/test_history_merge.py`

**Interfaces:**
- Consumes: `fold_pair`, `rows_to_changes`, `change_to_row_dict` (Task 4); `successor_of`, `BATCH_SIZE` (Task 5); `Operation.result["removed_archive_ids"]` written by `run_archive_sync` (phase 1)
- Produces:
  - `removed_archive_ids_from_dependency(db, operation) -> list[int]`
  - `merge_removed_archive(db, removed: Archive) -> str` returning `folded | reset | dropped`
  - `run_history_merge(ctx) -> Outcome` registered as `history_merge`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_history_merge.py`:

```python
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, ArchiveChange, Base, Operation, Repository, SystemSettings
from app.services.operations.executors import history


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


def _archive(db, repo, name, day, state="indexed", series="nas", truncated=False):
    a = Archive(
        repository_id=repo.id, borg_id=f"id-{name}", name=name, series=series,
        start=datetime(2026, 9, day, 2), history_state=state, history_truncated=truncated,
    )
    db.add(a)
    db.commit()
    return a


def _row(db, archive, path, change, before=None, after=None, count=None):
    db.add(ArchiveChange(archive_id=archive.id, path=path, change=change, size_before=before, size_after=after, summary_count=count))
    db.commit()


def _ops(db, repo, removed_ids):
    parent = Operation(repository_id=repo.id, kind="archive_sync", category="index", status="completed",
                       trigger="reconcile", priority=20, run_id="run", result={"removed_archive_ids": removed_ids})
    db.add(parent)
    db.commit()
    child = Operation(repository_id=repo.id, kind="history_merge", category="index", status="running",
                      trigger="reconcile", priority=20, run_id="run", depends_on_id=parent.id)
    db.add(child)
    db.commit()
    return child


def _ctx(db, repo, op):
    return SimpleNamespace(db=db, repository_id=repo.id, operation_id=op.id, kind="history_merge", params={},
                           operation=op, progress=AsyncMock(), log=lambda line: None, cancelled=lambda: False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_removed_archive_folds_into_indexed_successor(db, repo):
    r = _archive(db, repo, "r", 2, truncated=True)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "a", "added", after=3)
    _row(db, r, "b", "modified", before=1, after=2)
    _row(db, r, "c", "removed", before=4)
    _row(db, s, "a", "removed", before=3)
    _row(db, s, "b", "modified", before=2, after=9)
    _row(db, s, "c", "added", after=7)
    _row(db, s, "d", "added", after=1)
    op = _ops(db, repo, [r.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.status == "completed" and out.result == {"merged": 1, "folded": 1, "reset": 0, "dropped": 0}
    assert db.get(Archive, r.id) is None
    rows = {x.path: x for x in db.query(ArchiveChange).filter_by(archive_id=s.id)}
    assert set(rows) == {"b", "c", "d"}
    assert (rows["b"].size_before, rows["b"].size_after) == (1, 9)
    assert rows["c"].change == "modified" and (rows["c"].size_before, rows["c"].size_after) == (4, 7)
    db.refresh(s)
    assert s.history_rows == 3 and s.history_truncated is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unindexed_removed_archive_resets_indexed_successor(db, repo):
    r = _archive(db, repo, "r", 2, state="pending")
    s = _archive(db, repo, "s", 3)
    _row(db, s, "a", "added", after=1)
    op = _ops(db, repo, [r.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["reset"] == 1
    db.refresh(s)
    assert s.history_state == "pending" and s.history_rows is None
    assert db.query(ArchiveChange).filter_by(archive_id=s.id).count() == 0
    assert db.get(Archive, r.id) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pending_successor_or_no_successor_just_drops(db, repo):
    r1 = _archive(db, repo, "r1", 1)
    _row(db, r1, "a", "added", after=1)
    s = _archive(db, repo, "s", 2, state="pending")
    r2 = _archive(db, repo, "newest", 5, series="other")
    op = _ops(db, repo, [r1.id, r2.id])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["dropped"] == 2 and out.result["merged"] == 2
    assert db.get(Archive, r1.id) is None and db.get(Archive, r2.id) is None
    assert db.query(ArchiveChange).count() == 0
    db.refresh(s)
    assert s.history_state == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ignores_other_repositories_and_missing_ids(db, repo):
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add(other)
    db.commit()
    foreign = Archive(repository_id=other.id, borg_id="f", name="f", series="d", start=datetime(2026, 9, 1))
    db.add(foreign)
    db.commit()
    op = _ops(db, repo, [foreign.id, 9999])
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["merged"] == 0
    assert db.get(Archive, foreign.id) is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_dependency_result_merges_nothing(db, repo):
    op = Operation(repository_id=repo.id, kind="history_merge", category="index", status="running",
                   trigger="manual", priority=0, run_id="x")
    db.add(op)
    db.commit()
    out = await history.run_history_merge(_ctx(db, repo, op))
    assert out.result["merged"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_merge_is_atomic_per_archive(db, repo):
    r = _archive(db, repo, "r", 2)
    s = _archive(db, repo, "s", 3)
    _row(db, r, "a", "added", after=3)
    _row(db, s, "b", "added", after=1)
    op = _ops(db, repo, [r.id])
    with patch.object(db, "bulk_insert_mappings", side_effect=RuntimeError("disk full")):
        with pytest.raises(RuntimeError):
            history.merge_removed_archive(db, r)
    assert db.get(Archive, r.id) is not None
    assert {x.path for x in db.query(ArchiveChange).filter_by(archive_id=s.id)} == {"b"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_history_merge.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: run_history_merge`.

- [ ] **Step 3: Append the merge half**

Append to `app/services/operations/executors/history.py`:

```python
# -- executor: history_merge ----------------------------------------------------


def removed_archive_ids_from_dependency(db: Session, operation) -> list[int]:
    """archive_sync reports removed archives in its result; history_merge
    always directly depends on it (spec 7.4 and 7.5 chains)."""
    depends_on_id = getattr(operation, "depends_on_id", None)
    if depends_on_id is None:
        return []
    parent = db.get(Operation, depends_on_id)
    if parent is None or parent.kind != "archive_sync":
        return []
    ids = (parent.result or {}).get("removed_archive_ids") or []
    return [int(i) for i in ids]


def merge_removed_archive(db: Session, removed: Archive) -> str:
    """Fold `removed` into its successor and delete it, in one transaction.

    Returns "folded" when both archives were indexed, "reset" when the
    successor was indexed against an archive that never was (its delta is
    now against the wrong base, so it goes back to pending), and "dropped"
    when there is no successor or the successor is not indexed yet (it will
    be diffed against the new predecessor when it is).
    """
    successor = successor_of(db, removed)
    try:
        if successor is None:
            outcome = "dropped"
        elif successor.history_state == "indexed" and removed.history_state == "indexed":
            older = rows_to_changes(
                db.query(ArchiveChange).filter(ArchiveChange.archive_id == removed.id).all()
            )
            newer = rows_to_changes(
                db.query(ArchiveChange).filter(ArchiveChange.archive_id == successor.id).all()
            )
            folded = list(fold_pair(older, newer).values())
            db.query(ArchiveChange).filter(ArchiveChange.archive_id == successor.id).delete(
                synchronize_session=False
            )
            mappings = [change_to_row_dict(c, successor.id) for c in folded]
            for i in range(0, len(mappings), BATCH_SIZE):
                db.bulk_insert_mappings(ArchiveChange, mappings[i : i + BATCH_SIZE])
            successor.history_rows = len(mappings)
            successor.history_truncated = bool(
                successor.history_truncated or removed.history_truncated
            )
            outcome = "folded"
        elif successor.history_state == "indexed":
            db.query(ArchiveChange).filter(ArchiveChange.archive_id == successor.id).delete(
                synchronize_session=False
            )
            successor.history_state = "pending"
            successor.history_indexed_at = None
            successor.history_rows = None
            successor.history_truncated = False
            outcome = "reset"
        else:
            outcome = "dropped"
        # Explicit delete of the rows: SQLite only cascades with
        # foreign_keys=ON, which the app does not guarantee.
        db.query(ArchiveChange).filter(ArchiveChange.archive_id == removed.id).delete(
            synchronize_session=False
        )
        db.delete(removed)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return outcome


async def run_history_merge(ctx) -> Outcome:
    repository = _load_repository(ctx)
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    db = ctx.db
    counts = {"merged": 0, "folded": 0, "reset": 0, "dropped": 0}
    ids = removed_archive_ids_from_dependency(db, ctx.operation)
    for position, archive_id in enumerate(ids):
        if ctx.cancelled():
            break
        removed = db.get(Archive, archive_id)
        if removed is None or removed.repository_id != repository.id:
            continue
        outcome = merge_removed_archive(db, removed)
        counts[outcome] += 1
        counts["merged"] += 1
        ctx.log(f"{removed.name}: {outcome}")
        await ctx.progress(current=position + 1, total=len(ids), message=removed.name)
        await asyncio.sleep(0)
    return Outcome(result=counts)


executors.register("history_index", run_history_index)
executors.register("history_merge", run_history_merge)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_history_merge.py tests/unit/test_history_index.py -q -p no:cacheprovider`
Expected: PASS, including `test_registered`.

Run: `python -m pytest tests/unit -q -x -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings. `tests/unit/test_operations_followups.py::test_chain_for_filters_to_available_executors`
still passes because it passes `available` explicitly.

---

### Task 7: Plan-aware chains, reconcile, licence activation hook, startup bootstrap

**Files:**
- Modify: `app/services/operations/followups.py`
- Modify: `app/services/operations/runner.py:283-296` (follow-up creation)
- Modify: `app/services/operations/enqueue.py:127-171` (`record_import_connect`)
- Modify: `app/services/operations/reconcile.py:39-58` (`enqueue_reconcile_runs`), add `bootstrap_history_once`
- Modify: `app/services/licensing_service.py:234-259` (`_apply_entitlement`)
- Modify: `app/main.py:406-420`
- Test: `tests/unit/test_operations_followups.py`, `tests/unit/test_operations_reconcile.py`, `tests/unit/test_operations_runner.py`, `tests/unit/test_licensing_service.py`

**Interfaces:**
- Produces:
  - `followups.HISTORY_KINDS: frozenset[str]`, `chain_for(kind, *, available=None, history=True)`
  - `reconcile.enqueue_reconcile_runs(db, *, history: Optional[bool] = None) -> int` (None means "ask the plan")
  - `reconcile.bootstrap_history_once(db) -> int`
  - `licensing_service._on_plan_changed(db, before: str, after: str) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_operations_followups.py`:

```python
@pytest.mark.unit
def test_chain_for_drops_history_kinds_for_community():
    from app.services.operations.followups import HISTORY_KINDS

    assert HISTORY_KINDS == {"history_index", "history_merge"}
    assert chain_for("backup", history=False) == ["archive_sync", "stats"]
    assert chain_for("prune", history=False) == ["archive_sync", "stats"]
    assert chain_for("import_connect", history=False) == ["stats", "archive_sync"]
    assert chain_for("backup", history=True) == ["archive_sync", "history_index", "stats"]
    assert chain_for("backup", available={"archive_sync", "history_index"}, history=False) == ["archive_sync"]


@pytest.mark.unit
def test_history_enabled_follows_plan(db_session):
    from app.database.models import LicensingState
    from app.services.operations.followups import history_enabled

    assert history_enabled(db_session) is False
    db_session.add(LicensingState(instance_id="t-followups", plan="pro", status="active"))
    db_session.commit()
    assert history_enabled(db_session) is True
```

Append to `tests/unit/test_operations_reconcile.py` (reuse the file's
existing fixtures for a session with one repository; the names below assume
`db` and `repo` as in `test_operations_index_executors.py`, adapt to the
file's own fixtures):

```python
@pytest.mark.unit
def test_reconcile_omits_history_kinds_for_community(db, repo):
    from app.services.operations.executors import load_default_executors
    from app.services.operations.reconcile import enqueue_reconcile_runs

    load_default_executors()
    assert enqueue_reconcile_runs(db, history=False) == 1
    kinds = [o.kind for o in db.query(Operation).order_by(Operation.id).all()]
    assert kinds == ["archive_sync", "stats"]


@pytest.mark.unit
def test_reconcile_includes_history_kinds_for_pro(db, repo):
    from app.services.operations.executors import load_default_executors
    from app.services.operations.reconcile import enqueue_reconcile_runs

    load_default_executors()
    assert enqueue_reconcile_runs(db, history=True) == 1
    kinds = [o.kind for o in db.query(Operation).order_by(Operation.id).all()]
    assert kinds == ["archive_sync", "history_merge", "history_index", "stats"]


@pytest.mark.unit
def test_bootstrap_history_once_runs_a_single_time(db, repo):
    from app.services.operations.reconcile import bootstrap_history_once

    with patch("app.services.operations.reconcile.enqueue_reconcile_runs", return_value=1) as enq:
        assert bootstrap_history_once(db) == 1
        assert bootstrap_history_once(db) == 0
    assert enq.call_count == 1
    assert db.query(SystemSettings).first().history_bootstrap_at is not None
```

Append to `tests/unit/test_operations_runner.py` a test using the file's
existing runner fixture pattern (an in-memory session factory and a
registry with a stub executor that returns `Outcome()`):

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_followups_skip_history_kinds_on_community(session_factory, registry_with_stub):
    """A successful backup on a Community install enqueues archive_sync and
    stats but no history_index, even though its executor is registered."""
```

with a body that enqueues a `backup` row, registers stub executors for
`backup`, `archive_sync`, `history_index`, `stats`, runs one tick plus the
task, patches `app.services.operations.runner.history_enabled` to return
`False`, and asserts the follow-up kinds are `["archive_sync", "stats"]`.
Then the same with `True` asserting `["archive_sync", "history_index",
"stats"]`. Copy the setup from the file's existing follow-up test rather
than inventing a new one.

Append to `tests/unit/test_licensing_service.py`:

```python
def test_pro_activation_enqueues_reconcile_runs(db_session, activation_keys):
    from app.database.models import Operation, Repository
    from app.services.licensing_service import import_offline_entitlement

    db_session.add(Repository(name="r", path="/tmp/r", encryption="none", compression="lz4"))
    db_session.commit()
    document = _build_document(activation_keys, plan="pro", is_trial=False)
    with patch("app.services.operations.reconcile.registered_kinds", return_value={"archive_sync", "history_merge", "history_index", "stats"}):
        import_offline_entitlement(db_session, document)
    kinds = [o.kind for o in db_session.query(Operation).order_by(Operation.id).all()]
    assert kinds == ["archive_sync", "history_merge", "history_index", "stats"]
    assert all(o.trigger == "reconcile" for o in db_session.query(Operation).all())
    # A second Pro entitlement does not enqueue again
    import_offline_entitlement(db_session, document)
    assert db_session.query(Operation).count() == 4
```

Adjust `_build_document(...)` arguments to the helper's actual signature at
`tests/unit/test_licensing_service.py:23`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_operations_followups.py tests/unit/test_operations_reconcile.py tests/unit/test_operations_runner.py tests/unit/test_licensing_service.py -q -p no:cacheprovider`
Expected: FAIL (`HISTORY_KINDS` missing, unexpected `history` kwarg, no operations enqueued on activation).

- [ ] **Step 3: Make chains, reconcile, and licensing plan aware**

`app/services/operations/followups.py`:

```python
HISTORY_KINDS: frozenset[str] = frozenset({"history_index", "history_merge"})


def chain_for(
    kind: str, *, available: Optional[set[str]] = None, history: bool = True
) -> list[str]:
    """Return the follow-up kinds for `kind`, in order.

    `available` drops kinds without an executor. `history=False` drops the
    history kinds for Community installs (spec 11.2): the stage does not
    exist rather than being created and skipped (Appendix B).
    """
    validate_kind(kind)
    chain = list(FOLLOWUPS[kind])
    if available is not None:
        chain = [k for k in chain if k in available]
    if not history:
        chain = [k for k in chain if k not in HISTORY_KINDS]
    return chain
```

Update the module docstring to say phase 2 added the plan awareness.

`app/services/operations/runner.py`: import `history_enabled` from
`followups` and change the follow-up creation to
`kinds = chain_for(op.kind, available=self._registered_kinds(), history=history_enabled(db))`.

`app/services/operations/enqueue.py` `record_import_connect`: import
`history_enabled` alongside `chain_for` and pass
`history=history_enabled(db)`.

`app/services/operations/reconcile.py`:

```python
from typing import Optional

from app.database.models import Operation, Repository, SystemSettings, utc_now
from app.services.operations.followups import HISTORY_KINDS, history_enabled


def enqueue_reconcile_runs(db: Session, *, history: Optional[bool] = None) -> int:
    available = registered_kinds()
    if history is None:
        history = history_enabled(db)
    kinds = [
        k
        for k in RECONCILE_CHAIN
        if k in available and (history or k not in HISTORY_KINDS)
    ]
    ...  # unchanged body


def bootstrap_history_once(db: Session) -> int:
    """First startup after phase 2: enqueue a reconcile run for every
    repository at priority 20 (spec 14). Recorded on SystemSettings so it
    runs once per install, not once per restart."""
    system_settings = db.query(SystemSettings).first()
    if system_settings is None or system_settings.history_bootstrap_at is not None:
        return 0
    count = enqueue_reconcile_runs(db)
    system_settings.history_bootstrap_at = utc_now()
    db.commit()
    logger.info("History bootstrap enqueued", repositories=count)
    return count
```

`app/services/licensing_service.py`:

```python
def _on_plan_changed(db: Session, before: str, after: str) -> None:
    """Spec 11.2: a Pro activation enqueues a reconcile run for every
    repository so history builds in the background. Lapses do nothing;
    rows stay and the gated routes hide them."""
    from app.core.features import Plan, plan_includes
    from app.services.operations.reconcile import enqueue_reconcile_runs

    try:
        was_pro = plan_includes(Plan(before), Plan.PRO)
        is_pro = plan_includes(Plan(after), Plan.PRO)
    except ValueError:
        return
    if is_pro and not was_pro:
        try:
            enqueue_reconcile_runs(db, history=True)
        except Exception as exc:
            logger.warning("Failed to enqueue reconcile after activation", error=str(exc))
```

In `_apply_entitlement`, first line: `before = get_effective_plan_value(db)`;
after `db.commit()`: `_on_plan_changed(db, before, get_effective_plan_value(db))`.

`app/main.py`, after `reconcile_scheduler.start()` is scheduled:

```python
    try:
        db = SessionLocal()
        try:
            from app.services.operations.reconcile import bootstrap_history_once

            bootstrap_history_once(db)
        finally:
            db.close()
    except Exception as e:
        logger.error("History bootstrap failed", error=str(e))
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_operations_followups.py tests/unit/test_operations_reconcile.py tests/unit/test_operations_runner.py tests/unit/test_licensing_service.py tests/unit/test_api_repositories_import_operations.py -q -p no:cacheprovider`
Expected: PASS. If an import test asserted the `history_index` follow-up
on a Community test database, it now expects `["stats", "archive_sync"]`;
update that assertion and add a Pro variant with a `LicensingState` row.

Run: `python -m pytest tests/unit -q -x -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings.

---

### Task 8: Info-dialog sync writes into `archives`

**Files:**
- Modify: `app/services/operations/executors/index.py:385-402` (extract `write_repository_archive_columns`)
- Modify: `app/services/repository_info_sync.py:56-104`
- Test: `tests/unit/test_repository_info_sync.py`, `tests/unit/test_operations_index_executors.py`

**Interfaces:**
- Produces: `index.write_repository_archive_columns(db, repository, *, exclude_ids: Iterable[int] = ()) -> None` (writes `archive_count` and `last_backup` from the `archives` table and commits)

- [ ] **Step 1: Write the failing tests**

Read `tests/unit/test_repository_info_sync.py` first; keep its existing
tests and change expectations only where they assert the repository row is
the sole target. Append:

```python
@pytest.mark.unit
def test_sync_writes_archive_rows_and_derives_columns(db, repo):
    """Borg 2 info entries carry id, name, and time; they upsert `archives`
    and the repository columns are derived from that table (spec 6.4)."""
    from app.database.models import Archive
    from app.services.repository_info_sync import sync_archive_stats_from_info

    repo.borg_version = 2
    db.commit()
    info = {
        "archives": [
            {"id": "a1", "name": "nas", "time": "2026-09-01T02:00:00.000000"},
            {"id": "a2", "name": "nas", "time": "2026-09-02T02:00:00.000000"},
        ]
    }
    sync_archive_stats_from_info(repo, info, db)
    assert db.query(Archive).filter_by(repository_id=repo.id).count() == 2
    assert repo.archive_count == 2
    assert repo.last_backup == datetime(2026, 9, 2, 2, 0, 0)


@pytest.mark.unit
def test_sync_falls_back_to_columns_when_entries_lack_ids(db, repo):
    from app.database.models import Archive
    from app.services.repository_info_sync import sync_archive_stats_from_info

    repo.borg_version = 2
    db.commit()
    sync_archive_stats_from_info(
        repo, {"archives": [{"name": "nas", "time": "2026-09-02T02:00:00.000000"}]}, db
    )
    assert db.query(Archive).count() == 0
    assert repo.archive_count == 1
```

Use the file's own repository fixture; the `db`/`repo` names above follow
`test_operations_index_executors.py` (Borg 2 repositories need
`borg_version=2`).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_repository_info_sync.py -q -p no:cacheprovider`
Expected: FAIL, no `archives` rows are written.

- [ ] **Step 3: Extract the column writer and switch the sync**

In `app/services/operations/executors/index.py` replace the block in
`run_archive_sync` that computes `rows`, `repository.archive_count`, and
`repository.last_backup` with a call to:

```python
def write_repository_archive_columns(
    db: Session, repository: Repository, *, exclude_ids: Iterable[int] = ()
) -> None:
    """Derive archive_count and last_backup from the archives table (spec
    6.4). `exclude_ids` are rows reported removed that history_merge has
    not deleted yet."""
    excluded = set(exclude_ids)
    rows = [
        a
        for a in db.query(Archive).filter(Archive.repository_id == repository.id).all()
        if a.id not in excluded
    ]
    repository.archive_count = len(rows)
    repository.last_backup = max((a.start for a in rows), default=None)
    db.commit()
```

(`from typing import Iterable`). Call it as
`write_repository_archive_columns(db, repository, exclude_ids=removed_ids)`.

In `app/services/repository_info_sync.py`, inside the `try` after the
timezone import:

```python
        timezone_name = agent_timezone_for_repository(db, repository)
        if archives and all(isinstance(a, dict) and a.get("id") for a in archives):
            # Full entries: keep the archives table in step with what the
            # dialog just showed, then derive the columns from it.
            from app.services.operations.executors.index import (
                apply_listing,
                write_repository_archive_columns,
            )

            _, removed = apply_listing(db, repository, archives, timezone_name=timezone_name)
            write_repository_archive_columns(db, repository, exclude_ids=removed)
            return
        repository.archive_count = len(archives)
        newest = _newest_archive_time(archives, timezone_name=timezone_name)
        ...  # existing column-only path unchanged
```

Update the module docstring: the sync now writes `archives` rows when the
info entries carry ids, and falls back to the columns otherwise. Replace
the em dashes in that docstring with commas while there.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_repository_info_sync.py tests/unit/test_operations_index_executors.py -q -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings.

---

### Task 9: Anomaly rules

**Files:**
- Create: `app/services/operations/anomalies.py`
- Test: `tests/unit/test_anomalies.py`

**Interfaces:**
- Consumes: `croniter`
- Produces:
  - `OVERDUE_THRESHOLD_DAYS = {"backup": 2, "check": 30, "prune": 14, "compact": 30, "index": 2, "mirror": 1}`
  - `median(values: Sequence[float]) -> Optional[float]`
  - `size_outlier(previous: Sequence[Optional[int]], value: Optional[int]) -> bool`
  - `duration_outlier(previous: Sequence[Optional[float]], value: Optional[float]) -> bool`
  - `median_gap(starts: Sequence[datetime]) -> Optional[timedelta]`
  - `expected_days_from_cron(cron_expression, start, until, timezone_name=None) -> set[date]`
  - `expected_days_from_gap(first, until, gap) -> set[date]`
  - `missed_run_days(starts: Sequence[datetime], *, until: datetime, cron_expression=None, timezone_name=None) -> set[date]`
  - `overdue(cell: str, last_completed_at: Optional[datetime], now: datetime) -> bool`
  - `series_flags(archives: Sequence[ArchiveLike]) -> dict[int, list[str]]` where `ArchiveLike` has `id`, `start`, `deduplicated_size`, `nfiles`, `duration_seconds`; returns `size_outlier` / `duration_outlier` per archive id

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_anomalies.py`:

```python
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.operations import anomalies as an


@pytest.mark.unit
def test_median():
    assert an.median([]) is None
    assert an.median([3]) == 3
    assert an.median([1, 5, 3]) == 3
    assert an.median([1, 2, 3, 4]) == 2.5


@pytest.mark.unit
def test_size_outlier_boundaries():
    prev = [100, 100, 100, 100, 100, 100, 100]
    assert an.size_outlier(prev, 59) is True
    assert an.size_outlier(prev, 60) is False
    assert an.size_outlier(prev, None) is False
    assert an.size_outlier([], 1) is False
    assert an.size_outlier([None, None], 1) is False
    # only the last seven count
    assert an.size_outlier([1] * 10 + [100] * 7, 59) is True


@pytest.mark.unit
def test_duration_outlier_boundaries():
    prev = [10.0] * 7
    assert an.duration_outlier(prev, 25.0) is False
    assert an.duration_outlier(prev, 25.1) is True
    assert an.duration_outlier(prev, None) is False


@pytest.mark.unit
def test_median_gap_uses_last_fourteen():
    starts = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(20)]
    assert an.median_gap(starts) == timedelta(days=1)
    assert an.median_gap(starts[:1]) is None
    assert an.median_gap([]) is None


@pytest.mark.unit
def test_expected_days_from_cron_and_gap():
    days = an.expected_days_from_cron("0 2 * * *", datetime(2026, 9, 1), datetime(2026, 9, 4), "UTC")
    assert days == {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)}
    days = an.expected_days_from_gap(datetime(2026, 9, 1, 2), datetime(2026, 9, 8), timedelta(days=2))
    assert days == {date(2026, 9, 1), date(2026, 9, 3), date(2026, 9, 5), date(2026, 9, 7)}
    # sub-daily cadence is capped at one expected day per day
    days = an.expected_days_from_gap(datetime(2026, 9, 1), datetime(2026, 9, 3), timedelta(hours=6))
    assert days == {date(2026, 9, 1), date(2026, 9, 2)}


@pytest.mark.unit
def test_missed_run_days_from_cron_and_from_gap():
    starts = [datetime(2026, 9, d, 2) for d in (1, 2, 4, 5)]
    missed = an.missed_run_days(starts, until=datetime(2026, 9, 6), cron_expression="0 2 * * *")
    assert missed == {date(2026, 9, 3)}
    missed = an.missed_run_days(starts, until=datetime(2026, 9, 6))
    assert missed == {date(2026, 9, 3)}
    assert an.missed_run_days([datetime(2026, 9, 1)], until=datetime(2026, 9, 6)) == set()
    # a day whose expected run is not yet due is not missed
    missed = an.missed_run_days(starts, until=datetime(2026, 9, 6, 1), cron_expression="0 2 * * *")
    assert date(2026, 9, 6) not in missed


@pytest.mark.unit
def test_overdue_thresholds():
    now = datetime(2026, 9, 10)
    assert an.OVERDUE_THRESHOLD_DAYS == {"backup": 2, "check": 30, "prune": 14, "compact": 30, "index": 2, "mirror": 1}
    assert an.overdue("backup", now - timedelta(days=2, seconds=1), now) is True
    assert an.overdue("backup", now - timedelta(days=2), now) is False
    assert an.overdue("check", None, now) is True
    assert an.overdue("unknown", now, now) is False


@pytest.mark.unit
def test_series_flags_per_archive():
    mk = lambda i, size, dur: SimpleNamespace(id=i, start=datetime(2026, 9, i), deduplicated_size=size, nfiles=10, duration_seconds=dur)
    archives = [mk(i, 100, 10.0) for i in range(1, 8)] + [mk(8, 50, 10.0), mk(9, 100, 30.0)]
    flags = an.series_flags(archives)
    assert flags[8] == ["size_outlier"]
    assert flags[9] == ["duration_outlier"]
    assert flags[3] == []
    # nfiles counts too
    archives = [mk(i, 100, 10.0) for i in range(1, 8)] + [SimpleNamespace(id=8, start=datetime(2026, 9, 8), deduplicated_size=100, nfiles=1, duration_seconds=10.0)]
    assert an.series_flags(archives)[8] == ["size_outlier"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_anomalies.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the module**

Create `app/services/operations/anomalies.py`:

```python
"""Anomaly rules (spec section 9.5). Pure functions; the heatmap and
status-strip routes call them and decide which flags the plan may show."""

from datetime import date, datetime, timedelta
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from croniter import croniter

OVERDUE_THRESHOLD_DAYS: dict[str, int] = {
    "backup": 2,
    "check": 30,
    "prune": 14,
    "compact": 30,
    "index": 2,
    "mirror": 1,
}
SIZE_OUTLIER_RATIO = 0.6
DURATION_OUTLIER_RATIO = 2.5
OUTLIER_WINDOW = 7
CADENCE_SAMPLE = 14
MAX_EXPECTED_DAYS = 5000


def median(values: Sequence[float]) -> Optional[float]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _window(previous: Sequence) -> list:
    return [v for v in list(previous)[-OUTLIER_WINDOW:] if v is not None]


def size_outlier(previous: Sequence[Optional[int]], value: Optional[int]) -> bool:
    base = median(_window(previous))
    if value is None or base is None:
        return False
    return value < SIZE_OUTLIER_RATIO * base


def duration_outlier(previous: Sequence[Optional[float]], value: Optional[float]) -> bool:
    base = median(_window(previous))
    if value is None or base is None:
        return False
    return value > DURATION_OUTLIER_RATIO * base


def median_gap(starts: Sequence[datetime]) -> Optional[timedelta]:
    sample = sorted(starts)[-CADENCE_SAMPLE:]
    if len(sample) < 2:
        return None
    gaps = [(b - a).total_seconds() for a, b in zip(sample, sample[1:])]
    return timedelta(seconds=median(gaps))


def expected_days_from_cron(
    cron_expression: str, start: datetime, until: datetime, timezone_name: Optional[str] = None
) -> set[date]:
    tz = ZoneInfo(timezone_name) if timezone_name else None
    base = start.replace(tzinfo=tz) if tz else start
    it = croniter(cron_expression, base)
    days: set[date] = set()
    while len(days) < MAX_EXPECTED_DAYS:
        nxt = it.get_next(datetime)
        naive = nxt.replace(tzinfo=None) if nxt.tzinfo else nxt
        if naive > until:
            break
        days.add(naive.date())
    return days


def expected_days_from_gap(first: datetime, until: datetime, gap: timedelta) -> set[date]:
    step = max(gap, timedelta(days=1))
    days: set[date] = set()
    current = first
    while current <= until and len(days) < MAX_EXPECTED_DAYS:
        days.add(current.date())
        current += step
    return days


def missed_run_days(
    starts: Sequence[datetime],
    *,
    until: datetime,
    cron_expression: Optional[str] = None,
    timezone_name: Optional[str] = None,
) -> set[date]:
    """Days inside the series cadence with no archive. Cadence is the cron
    when known, else the median gap of the last 14 archives. A day is only
    counted once its expected run time has passed."""
    if not starts:
        return set()
    first = min(starts)
    present = {s.date() for s in starts}
    if cron_expression:
        # Start the iteration just before the first archive so its own day
        # counts as expected. Days after `until` are excluded by the helper.
        expected = expected_days_from_cron(
            cron_expression, first - timedelta(seconds=1), until, timezone_name
        )
    else:
        gap = median_gap(starts)
        if gap is None:
            return set()
        expected = expected_days_from_gap(first, until - gap, gap)
    return {d for d in expected if d not in present and d >= first.date()}


def overdue(cell: str, last_completed_at: Optional[datetime], now: datetime) -> bool:
    threshold = OVERDUE_THRESHOLD_DAYS.get(cell)
    if threshold is None:
        return False
    if last_completed_at is None:
        return True
    return now - last_completed_at > timedelta(days=threshold)


def series_flags(archives: Sequence) -> dict[int, list[str]]:
    """Outlier flags per archive id, comparing each archive with the seven
    before it in start order."""
    ordered = sorted(archives, key=lambda a: (a.start, a.id))
    flags: dict[int, list[str]] = {}
    for i, archive in enumerate(ordered):
        previous = ordered[max(0, i - OUTLIER_WINDOW) : i]
        found: list[str] = []
        if size_outlier([p.deduplicated_size for p in previous], archive.deduplicated_size) or size_outlier(
            [p.nfiles for p in previous], archive.nfiles
        ):
            found.append("size_outlier")
        if duration_outlier([p.duration_seconds for p in previous], archive.duration_seconds):
            found.append("duration_outlier")
        flags[archive.id] = found
    return flags
```

If the cron test's "not yet due" case fails because `expected_days_from_cron`
returns the day at 02:00 before `until` 01:00 on the sixth, the helper is
right and the test is right: the run at 02:00 on the sixth is after `until`,
so it is excluded; make sure `naive > until` compares full datetimes, not
dates.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_anomalies.py -q -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings.

---

### Task 10: Community routes: archive list, detail, heatmap, status strip, rebuild, settings field

**Files:**
- Create: `app/api/archive_index.py`
- Create: `app/services/operations/legacy_status.py`
- Modify: `app/api/repositories.py:6028` (route path), `:1298-1341` (`RepositoryUpdate`), `:3087` (serializer), `:4916-4917` (PUT assignment)
- Modify: `app/api/archives.py:215-220` (`/list` deprecation headers)
- Modify: `app/main.py:196-198` (include the router after the repositories router)
- Modify: `frontend/src/services/api.ts:898`
- Test: `tests/unit/test_api_archive_index.py`, `tests/unit/test_api_archives.py`

**Interfaces:**
- Consumes: `series_flags`, `missed_run_days`, `overdue`, `OVERDUE_THRESHOLD_DAYS` (Task 9); `cron_for_repository` (Task 2); `history_enabled`, `HISTORY_KINDS` (Task 7); `enqueue_chain`, `PRIORITY_RECONCILE`; `get_repository_with_access` from `app/api/maintenance_jobs.py:20`; `require_any_role` from `app/core/security.py:580`; `predecessor_of`, `successor_of` (Task 5)
- Produces:
  - `serialize_archive(archive: Archive) -> dict`
  - `sync_state_for(db, repository) -> tuple[str, Optional[datetime]]` (`fresh | syncing | stale | never`)
  - `STRIP_CELLS` and `legacy_status.latest_legacy_terminal(db, repository_id, cell) -> Optional[tuple[str, datetime]]`
  - Routes: `GET /{repo_id}/archives`, `GET /{repo_id}/archives/heatmap`, `GET /{repo_id}/archives/{archive_id}`, `GET /{repo_id}/status-strip`, `POST /{repo_id}/rebuild`
  - The live Borg listing moves to `GET /{repo_id}/archives/live` (Open questions 1)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_api_archive_index.py`:

```python
from datetime import datetime, timedelta

import pytest

from app.database.models import (
    Archive,
    ArchiveChange,
    BackupJob,
    LicensingState,
    Operation,
    Repository,
    SystemSettings,
    utc_now,
)


def _repo(test_db, name="r", **kw):
    repo = Repository(name=name, path=f"/tmp/{name}", encryption="none", compression="lz4", **kw)
    test_db.add(repo)
    if test_db.query(SystemSettings).first() is None:
        test_db.add(SystemSettings())
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _archive(test_db, repo, name, day, series="nas", state="indexed", size=100, dur=10.0, nfiles=10):
    a = Archive(
        repository_id=repo.id, borg_id=f"id-{name}", name=name, series=series,
        start=datetime(2026, 9, day, 2), history_state=state, deduplicated_size=size,
        duration_seconds=dur, nfiles=nfiles,
    )
    test_db.add(a)
    test_db.commit()
    test_db.refresh(a)
    return a


def _op(test_db, repo, kind, status="completed", completed_at=None, category=None, trigger="manual"):
    from app.services.operations.vocab import category_for

    op = Operation(
        repository_id=repo.id, kind=kind, category=category or category_for(kind), status=status,
        trigger=trigger, priority=0, run_id="run", completed_at=completed_at,
    )
    test_db.add(op)
    test_db.commit()
    return op


def _pro(test_db):
    test_db.add(LicensingState(instance_id="t-archive-index", plan="pro", status="active"))
    test_db.commit()


@pytest.mark.unit
class TestArchiveList:
    def test_lists_from_table_with_filters_and_sync_state(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)
        _archive(test_db, repo, "b1", 2, series="docs")
        _archive(test_db, repo, "a2", 3)
        r = test_client.get(f"/api/repositories/{repo.id}/archives", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert [a["name"] for a in body["archives"]] == ["a2", "b1", "a1"]
        assert body["sync_state"] == "never" and body["last_synced_at"] is None
        assert sorted(body["series"]) == ["docs", "nas"]
        assert body["history_available"] is False
        r = test_client.get(f"/api/repositories/{repo.id}/archives?series=nas&since=2026-09-02T00:00:00", headers=admin_headers)
        assert [a["name"] for a in r.json()["archives"]] == ["a2"]

    def test_sync_state_fresh_syncing_stale(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _op(test_db, repo, "archive_sync", completed_at=utc_now())
        assert test_client.get(f"/api/repositories/{repo.id}/archives", headers=admin_headers).json()["sync_state"] == "fresh"
        _op(test_db, repo, "archive_sync", status="queued")
        assert test_client.get(f"/api/repositories/{repo.id}/archives", headers=admin_headers).json()["sync_state"] == "syncing"
        test_db.query(Operation).delete()
        _op(test_db, repo, "archive_sync", completed_at=utc_now() - timedelta(days=3))
        assert test_client.get(f"/api/repositories/{repo.id}/archives", headers=admin_headers).json()["sync_state"] == "stale"

    def test_detail_has_neighbours_and_history_state(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2, state="pending")
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a2.id}", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["history_state"] == "pending"
        assert r.json()["predecessor_id"] == a1.id and r.json()["successor_id"] is None
        assert test_client.get(f"/api/repositories/{repo.id}/archives/999", headers=admin_headers).status_code == 404

    def test_live_listing_moved(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        paths = {route.path for route in test_client.app.routes}
        assert "/api/repositories/{repo_id}/archives/live" in paths

    def test_requires_repository_access(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        assert test_client.get(f"/api/repositories/{repo.id}/archives", headers=auth_headers).status_code in (403, 404)


@pytest.mark.unit
class TestHeatmap:
    def test_counts_sizes_and_missed_days_for_community(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        for d in (1, 2, 4):
            _archive(test_db, repo, f"a{d}", d)
        _archive(test_db, repo, "a5", 5, size=10)
        r = test_client.get(f"/api/repositories/{repo.id}/archives/heatmap?since=2026-09-01T00:00:00&until=2026-09-06T00:00:00", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        series = {s["series"]: s for s in body["series"]}["nas"]
        days = {d["date"]: d for d in series["days"]}
        assert days["2026-09-01"]["count"] == 1 and days["2026-09-01"]["deduplicated_size"] == 100
        assert "2026-09-03" in series["missed_days"]
        assert days["2026-09-05"]["anomalies"] == []
        assert body["flags_available"] == {"missed_run": True, "size_outlier": False, "duration_outlier": False}

    def test_outlier_flags_only_for_pro(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        for d in range(1, 8):
            _archive(test_db, repo, f"a{d}", d)
        _archive(test_db, repo, "a8", 8, size=10)
        _pro(test_db)
        r = test_client.get(f"/api/repositories/{repo.id}/archives/heatmap?since=2026-09-01T00:00:00&until=2026-09-09T00:00:00", headers=admin_headers)
        series = r.json()["series"][0]
        days = {d["date"]: d for d in series["days"]}
        assert days["2026-09-08"]["anomalies"] == ["size_outlier"]
        assert r.json()["flags_available"]["size_outlier"] is True


@pytest.mark.unit
class TestStatusStrip:
    def test_cells_from_operations_and_legacy(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        now = utc_now()
        _op(test_db, repo, "prune", completed_at=now - timedelta(days=20))
        _op(test_db, repo, "archive_sync", completed_at=now - timedelta(hours=1))
        _op(test_db, repo, "check", status="running")
        test_db.add(BackupJob(repository_id=repo.id, status="completed", completed_at=now - timedelta(days=3)))
        test_db.commit()
        r = test_client.get(f"/api/repositories/{repo.id}/status-strip", headers=admin_headers)
        assert r.status_code == 200
        cells = {c["cell"]: c for c in r.json()["cells"]}
        assert set(cells) == {"backup", "check", "prune", "compact", "index"}
        assert cells["backup"]["source"] == "legacy" and cells["backup"]["status"] == "completed"
        assert cells["prune"]["threshold_days"] == 14
        assert cells["prune"]["overdue"] is None
        assert cells["check"]["running"] is True and cells["check"]["completed_at"] is None
        assert cells["index"]["age_seconds"] < 4000
        assert r.json()["overdue_available"] is False

    def test_overdue_flags_for_pro_and_mirror_cell(self, test_client, test_db, admin_headers):
        repo = _repo(test_db, cloud_mirror_enabled=True)
        _pro(test_db)
        _op(test_db, repo, "prune", completed_at=utc_now() - timedelta(days=20))
        r = test_client.get(f"/api/repositories/{repo.id}/status-strip", headers=admin_headers)
        cells = {c["cell"]: c for c in r.json()["cells"]}
        assert "mirror" in cells
        assert cells["prune"]["overdue"] is True and cells["compact"]["overdue"] is True
        assert r.json()["overdue_available"] is True


@pytest.mark.unit
class TestRebuild:
    def test_rebuild_from_stats_and_archives(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "a1", 1)
        a.original_size = 5
        test_db.commit()
        r = test_client.post(f"/api/repositories/{repo.id}/rebuild", json={"from": "stats"}, headers=admin_headers)
        assert r.status_code == 200
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["stats"]
        r = test_client.post(f"/api/repositories/{repo.id}/rebuild", json={"from": "archives"}, headers=admin_headers)
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["archive_sync", "stats"]
        ops = test_db.query(Operation).all()
        assert all(o.trigger == "manual" and o.priority == 20 for o in ops)
        test_db.refresh(a)
        assert a.original_size is None

    def test_rebuild_from_history_is_pro_and_resets_archives(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "a1", 1)
        test_db.add(ArchiveChange(archive_id=a.id, path="x", change="added"))
        test_db.commit()
        r = test_client.post(f"/api/repositories/{repo.id}/rebuild", json={"from": "history"}, headers=admin_headers)
        assert r.status_code == 403 and r.json()["detail"]["feature"] == "archive_history"
        _pro(test_db)
        r = test_client.post(f"/api/repositories/{repo.id}/rebuild", json={"from": "history"}, headers=admin_headers)
        assert r.status_code == 200
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["history_index", "stats"]
        test_db.refresh(a)
        assert a.history_state == "pending" and test_db.query(ArchiveChange).count() == 0

    def test_rebuild_requires_operator(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        r = test_client.post(f"/api/repositories/{repo.id}/rebuild", json={"from": "stats"}, headers=auth_headers)
        assert r.status_code == 403

    def test_rebuild_rejects_unknown_stage(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.post(f"/api/repositories/{repo.id}/rebuild", json={"from": "x"}, headers=admin_headers)
        assert r.status_code == 422


@pytest.mark.unit
class TestRepositorySettings:
    def test_history_excludes_round_trip(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
        assert r.json()["history_index_excludes"][0] == "**/.cache/**"
        r = test_client.put(f"/api/repositories/{repo.id}", json={"history_index_excludes": ["**/tmp/**"]}, headers=admin_headers)
        assert r.status_code == 200
        test_db.refresh(repo)
        assert repo.history_index_excludes == ["**/tmp/**"]
```

Append to `tests/unit/test_api_archives.py` (using its existing mocked
listing test as the template):

```python
@pytest.mark.unit
def test_archives_list_route_sends_deprecation_headers(test_client, test_db, admin_headers, monkeypatch):
    """Spec 9.2: /archives/list stays one release and is marked deprecated."""
```

with a body that patches `app.api.archives.borg.list_archives` with an
`AsyncMock` returning `{"success": True, "stdout": "{}"}`, calls
`/api/archives/list?repository=<path>` for a repository row, and asserts
`r.headers["deprecation"] == "true"` and
`"/archives" in r.headers["link"]`.

`test_requires_repository_access` uses a plain user; if the fixture user has
implicit access to all repositories in this codebase, replace the assertion
with the pattern used by the RBAC tests for a viewer without a permission
row.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_api_archive_index.py tests/unit/test_api_archives.py -q -p no:cacheprovider`
Expected: FAIL with 404 / 405 responses and missing headers.

- [ ] **Step 3: Move the live route, add the settings field, deprecate `/archives/list`**

`app/api/repositories.py:6028`: change `@router.get("/{repo_id}/archives")`
to `@router.get("/{repo_id}/archives/live")` and the docstring to
"List archives straight from borg. The database-backed list is
`GET /{repo_id}/archives` in `app/api/archive_index.py`; this route stays
for the Archives page until phase 4."

`frontend/src/services/api.ts:898`:
`listRepositoryArchives: (id: number) => api.get(`/repositories/${id}/archives/live`),`

`RepositoryUpdate`: add `history_index_excludes: Optional[List[str]] = None`.
PUT route, next to the `bypass_lock` assignment:

```python
        if repo_data.history_index_excludes is not None:
            repository.history_index_excludes = [
                p.strip() for p in repo_data.history_index_excludes if p and p.strip()
            ]
```

Serializer at line 3087, after `"bypass_lock"`:

```python
                "history_index_excludes": repo.history_index_excludes
                or list(DEFAULT_HISTORY_INDEX_EXCLUDES),
```

importing `DEFAULT_HISTORY_INDEX_EXCLUDES` from `app.database.models`.

`app/api/archives.py` `/list`: add `response: Response` to the signature
(`from fastapi import Response`) and before the return:

```python
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = (
            f'</api/repositories/{repo.id}/archives>; rel="successor-version"'
        )
```

- [ ] **Step 4: Write the legacy status helper**

Create `app/services/operations/legacy_status.py`:

```python
"""Latest terminal legacy job per status-strip cell. The strip reads
`operations` first; until phases 5 to 8 migrate backup, check, prune,
compact, and rclone sync, their history lives in the legacy tables. Deleted
in phase 9 together with `legacy_running_exclusive`."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import BackupJob, CheckJob, CompactJob, PruneJob, RcloneSyncJob

_LEGACY_MODELS = {
    "backup": BackupJob,
    "check": CheckJob,
    "prune": PruneJob,
    "compact": CompactJob,
    "mirror": RcloneSyncJob,
}
_TERMINAL = ("completed", "completed_with_warnings", "failed", "cancelled")


def latest_legacy_terminal(
    db: Session, repository_id: int, cell: str
) -> Optional[tuple[str, datetime]]:
    model = _LEGACY_MODELS.get(cell)
    if model is None:
        return None
    row = (
        db.query(model.status, model.completed_at)
        .filter(
            model.repository_id == repository_id,
            model.status.in_(_TERMINAL),
            model.completed_at.isnot(None),
        )
        .order_by(model.completed_at.desc())
        .first()
    )
    return (row.status, row.completed_at) if row else None
```

- [ ] **Step 5: Write the router (community half)**

Create `app/api/archive_index.py`:

```python
"""Database-backed archive routes (spec section 9.2): list, detail,
heatmap, status strip, rebuild, and (Pro) changes, history, search."""

from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.maintenance_jobs import get_repository_with_access
from app.core.features import require_feature, require_feature_access
from app.core.security import get_current_user, require_any_role
from app.database.database import get_db
from app.database.models import (
    Archive,
    ArchiveChange,
    Operation,
    Repository,
    SystemSettings,
    User,
    utc_now,
)
from app.services.operations import anomalies
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.executors.history import predecessor_of, successor_of
from app.services.operations.followups import HISTORY_KINDS, history_enabled
from app.services.operations.history_fold import Change, fold_sequence, rows_to_changes
from app.services.operations.legacy_status import latest_legacy_terminal
from app.services.operations.series import cron_for_repository
from app.services.operations.vocab import PRIORITY_RECONCILE

router = APIRouter()

NOT_FOUND = {"key": "backend.errors.archives.notFound"}
STALE_AFTER_INTERVALS = 2
STRIP_CELLS: tuple[tuple[str, dict], ...] = (
    ("backup", {"kinds": ("backup",)}),
    ("check", {"kinds": ("check",)}),
    ("prune", {"kinds": ("prune",)}),
    ("compact", {"kinds": ("compact",)}),
    ("index", {"category": "index"}),
    ("mirror", {"category": "mirror"}),
)


def _repo(db: Session, user: User, repo_id: int, role: str = "viewer") -> Repository:
    return get_repository_with_access(db, user, repo_id, required_role=role)


def serialize_archive(a: Archive) -> dict:
    return {
        "id": a.id,
        "repository_id": a.repository_id,
        "borg_id": a.borg_id,
        "name": a.name,
        "series": a.series,
        "start": a.start,
        "end": a.end,
        "duration_seconds": a.duration_seconds,
        "nfiles": a.nfiles,
        "original_size": a.original_size,
        "compressed_size": a.compressed_size,
        "deduplicated_size": a.deduplicated_size,
        "hostname": a.hostname,
        "username": a.username,
        "comment": a.comment,
        "backup_operation_id": a.backup_operation_id,
        "history_state": a.history_state,
        "history_indexed_at": a.history_indexed_at,
        "history_rows": a.history_rows,
        "history_truncated": a.history_truncated,
        "first_seen_at": a.first_seen_at,
        "last_seen_at": a.last_seen_at,
    }


def sync_state_for(db: Session, repository: Repository) -> tuple[str, Optional[datetime]]:
    active = (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "archive_sync",
            Operation.status.in_(("queued", "running")),
        )
        .first()
    )
    last = (
        db.query(Operation.completed_at)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "archive_sync",
            Operation.status.in_(("completed", "completed_with_warnings")),
        )
        .order_by(Operation.completed_at.desc())
        .first()
    )
    last_at = last.completed_at if last else None
    if active:
        return "syncing", last_at
    if last_at is None:
        return "never", None
    settings = db.query(SystemSettings).first()
    interval = (settings.stats_refresh_interval_minutes if settings else None) or 60
    if utc_now() - last_at > timedelta(minutes=interval * STALE_AFTER_INTERVALS):
        return "stale", last_at
    return "fresh", last_at


def _archives_query(db: Session, repository: Repository, series, since, until):
    q = db.query(Archive).filter(Archive.repository_id == repository.id)
    if series:
        q = q.filter(Archive.series == series)
    if since:
        q = q.filter(Archive.start >= since)
    if until:
        q = q.filter(Archive.start <= until)
    return q


@router.get("/{repo_id}/archives")
async def list_archives(
    repo_id: int,
    series: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    rows = (
        _archives_query(db, repository, series, since, until)
        .order_by(Archive.start.desc(), Archive.id.desc())
        .all()
    )
    all_series = [
        s for (s,) in db.query(Archive.series)
        .filter(Archive.repository_id == repository.id)
        .distinct()
        .all()
    ]
    state, last_at = sync_state_for(db, repository)
    return {
        "archives": [serialize_archive(a) for a in rows],
        "series": all_series,
        "sync_state": state,
        "last_synced_at": last_at,
        "history_available": history_enabled(db),
    }


@router.get("/{repo_id}/archives/heatmap")
async def archives_heatmap(
    repo_id: int,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    until = until or utc_now()
    since = since or until - timedelta(days=365)
    pro = history_enabled(db)
    rows = (
        _archives_query(db, repository, None, since, until)
        .order_by(Archive.series.asc(), Archive.start.asc())
        .all()
    )
    cron_expression, timezone_name = cron_for_repository(db, repository)
    by_series: dict[str, list[Archive]] = {}
    for a in rows:
        by_series.setdefault(a.series, []).append(a)
    out = []
    for name, archives in by_series.items():
        flags = anomalies.series_flags(archives) if pro else {a.id: [] for a in archives}
        days: dict[str, dict] = {}
        for a in archives:
            key = a.start.date().isoformat()
            day = days.setdefault(
                key,
                {"date": key, "count": 0, "deduplicated_size": 0, "duration_seconds": 0.0,
                 "archive_ids": [], "anomalies": []},
            )
            day["count"] += 1
            day["deduplicated_size"] += a.deduplicated_size or 0
            day["duration_seconds"] += a.duration_seconds or 0.0
            day["archive_ids"].append(a.id)
            for flag in flags.get(a.id, []):
                if flag not in day["anomalies"]:
                    day["anomalies"].append(flag)
        missed = anomalies.missed_run_days(
            [a.start for a in archives], until=until,
            cron_expression=cron_expression, timezone_name=timezone_name,
        )
        out.append({
            "series": name,
            "days": list(days.values()),
            "missed_days": sorted(d.isoformat() for d in missed),
            "first": archives[0].start,
            "last": archives[-1].start,
        })
    return {
        "since": since,
        "until": until,
        "series": out,
        "flags_available": {"missed_run": True, "size_outlier": pro, "duration_outlier": pro},
    }


def _archive_or_404(db: Session, repository: Repository, archive_id: int) -> Archive:
    archive = db.get(Archive, archive_id)
    if archive is None or archive.repository_id != repository.id:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return archive


@router.get("/{repo_id}/archives/{archive_id}")
async def get_archive(
    repo_id: int,
    archive_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    archive = _archive_or_404(db, repository, archive_id)
    predecessor = predecessor_of(db, archive)
    successor = successor_of(db, archive)
    return {
        **serialize_archive(archive),
        "predecessor_id": predecessor.id if predecessor else None,
        "successor_id": successor.id if successor else None,
        "history_available": history_enabled(db),
    }


@router.get("/{repo_id}/status-strip")
async def status_strip(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    pro = history_enabled(db)
    now = utc_now()
    mirror_applies = bool(
        getattr(repository, "cloud_mirror_enabled", False)
        or getattr(repository, "storage_backend", None) == "rclone"
    )
    cells = []
    for cell, spec in STRIP_CELLS:
        if cell == "mirror" and not mirror_applies:
            continue
        q = db.query(Operation).filter(Operation.repository_id == repository.id)
        if "kinds" in spec:
            q = q.filter(Operation.kind.in_(spec["kinds"]))
        else:
            q = q.filter(Operation.category == spec["category"])
        running = q.filter(Operation.status == "running").first() is not None
        latest = (
            q.filter(Operation.status.in_(("completed", "completed_with_warnings", "failed", "cancelled")))
            .order_by(Operation.completed_at.desc())
            .first()
        )
        status, completed_at, source = (
            (latest.status, latest.completed_at, "operations") if latest else (None, None, None)
        )
        legacy = latest_legacy_terminal(db, repository.id, cell)
        if legacy and (completed_at is None or legacy[1] > completed_at):
            status, completed_at, source = legacy[0], legacy[1], "legacy"
        cells.append({
            "cell": cell,
            "status": status,
            "completed_at": completed_at,
            "age_seconds": (now - completed_at).total_seconds() if completed_at else None,
            "threshold_days": anomalies.OVERDUE_THRESHOLD_DAYS[cell],
            "overdue": anomalies.overdue(cell, completed_at, now) if pro else None,
            "running": running,
            "source": source,
        })
    return {"cells": cells, "overdue_available": pro}


class RebuildRequest(BaseModel):
    from_stage: Literal["stats", "archives", "history"] = Field(alias="from")

    model_config = {"populate_by_name": True}


@router.post("/{repo_id}/rebuild")
async def rebuild(
    repo_id: int,
    body: RebuildRequest,
    current_user: User = Depends(require_any_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    """Invalidate a derived-data stage and the stages after it, then enqueue
    a manual run at priority 20 (spec 9.2)."""
    repository = _repo(db, current_user, repo_id, role="operator")
    history = history_enabled(db)
    if body.from_stage == "history":
        require_feature_access(db, "archive_history")
    archives = db.query(Archive).filter(Archive.repository_id == repository.id).all()
    if body.from_stage == "archives":
        for a in archives:
            a.original_size = None
        kinds = ["archive_sync", "history_index", "stats"]
    elif body.from_stage == "history":
        ids = [a.id for a in archives]
        if ids:
            db.query(ArchiveChange).filter(ArchiveChange.archive_id.in_(ids)).delete(synchronize_session=False)
        for a in archives:
            a.history_state = "pending"
            a.history_indexed_at = None
            a.history_rows = None
            a.history_truncated = False
        kinds = ["history_index", "stats"]
    else:
        kinds = ["stats"]
    if not history:
        kinds = [k for k in kinds if k not in HISTORY_KINDS]
    db.commit()
    ops = enqueue_chain(
        db, kinds, repository_id=repository.id, trigger="manual",
        priority=PRIORITY_RECONCILE, triggered_by_user_id=current_user.id,
    )
    return {"run_id": ops[0].run_id if ops else None, "operations": [o.id for o in ops]}
```

Check `require_any_role`'s signature at `app/core/security.py:580` and use
it the way `app/api/operations.py` does for its cancel route. If the
`rebuild_from_history` 403 test fails because `require_feature_access`
runs after the operator check, that order is intended (operator first).

`app/main.py`, right after the `repositories.router` include:

```python
app.include_router(
    archive_index.router, prefix="/api/repositories", tags=["Archive index"]
)
```

with `archive_index` added to the `from app.api import ...` list.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/unit/test_api_archive_index.py tests/unit/test_api_archives.py tests/unit/test_api_repositories.py -q -p no:cacheprovider`
Expected: PASS except the Pro-only classes added in Task 11. Any
repositories test that requested `/{repo_id}/archives` expecting the live
listing now targets `/archives/live`; update those paths.

Run: `cd frontend && npx vitest run src/pages/__tests__/Archives.delete.test.tsx`
Expected: PASS (the mock is on the function, not the URL).

Run: `python -m pytest tests/unit -q -x -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings.

---

### Task 11: Pro routes: changes, history, search

**Files:**
- Modify: `app/api/archive_index.py` (append)
- Test: `tests/unit/test_api_archive_index.py` (append)

**Interfaces:**
- Consumes: `fold_sequence`, `rows_to_changes`, `Change` (Task 4); `require_feature("archive_history")`
- Produces: `GET /{repo_id}/archives/{archive_id}/changes`, `GET /{repo_id}/history`, `GET /{repo_id}/search`; helper `present_ranges(entries) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_api_archive_index.py`:

```python
def _change(test_db, archive, path, change, before=None, after=None, count=None):
    test_db.add(ArchiveChange(archive_id=archive.id, path=path, change=change, size_before=before, size_after=after, summary_count=count))
    test_db.commit()


@pytest.mark.unit
class TestProGate:
    @pytest.mark.parametrize("path", ["/archives/1/changes", "/history?path=x", "/search?q=x"])
    def test_community_gets_403(self, test_client, test_db, admin_headers, path):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)
        r = test_client.get(f"/api/repositories/{repo.id}{path}", headers=admin_headers)
        assert r.status_code == 403
        assert r.json()["detail"] == {
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": "archive_history",
            "required": "pro",
            "current": "community",
        }


@pytest.mark.unit
class TestChanges:
    def _three(self, test_db, repo):
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2)
        a3 = _archive(test_db, repo, "a3", 3)
        _change(test_db, a1, "a", "added", after=10)
        _change(test_db, a1, "b", "added", after=3)
        _change(test_db, a2, "a", "modified", before=10, after=12)
        _change(test_db, a2, "b", "removed", before=3)
        _change(test_db, a2, "d", "added", after=5)
        _change(test_db, a3, "a", "modified", before=12, after=20)
        _change(test_db, a3, "b", "added", after=7)
        _change(test_db, a3, "d", "removed", before=5)
        _change(test_db, a3, "lib/x/y/z", "summary", count=4)
        return a1, a2, a3

    def test_default_compares_with_predecessor(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a3.id}/changes", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["compare_to_id"] == a2.id
        assert {c["path"]: c["change"] for c in body["changes"]} == {"a": "modified", "b": "added", "d": "removed", "lib/x/y/z": "summary"}
        assert body["totals"] == {"added": 1, "removed": 1, "modified": 1, "summary": 1}
        assert body["next_cursor"] is None and body["history_state"] == "indexed"

    def test_compare_to_folds_intermediate_deltas(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a3.id}/changes?compare_to={a1.id}", headers=admin_headers)
        body = r.json()
        by = {c["path"]: c for c in body["changes"]}
        assert by["a"]["change"] == "modified" and (by["a"]["size_before"], by["a"]["size_after"]) == (10, 20)
        assert by["b"]["change"] == "modified" and (by["b"]["size_before"], by["b"]["size_after"]) == (3, 7)
        assert "d" not in by

    def test_filters_and_cursor(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a3.id}/changes?change=added&change=removed", headers=admin_headers)
        assert sorted(c["path"] for c in r.json()["changes"]) == ["b", "d"]
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a3.id}/changes?path_prefix=lib/", headers=admin_headers)
        assert [c["path"] for c in r.json()["changes"]] == ["lib/x/y/z"]
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a3.id}/changes?limit=2", headers=admin_headers)
        first = r.json()
        assert len(first["changes"]) == 2 and first["next_cursor"] is not None
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a3.id}/changes?limit=2&cursor={first['next_cursor']}", headers=admin_headers)
        assert len(r.json()["changes"]) == 2 and r.json()["next_cursor"] is None

    def test_pending_archive_returns_empty_with_state(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a = _archive(test_db, repo, "a1", 1, state="pending")
        r = test_client.get(f"/api/repositories/{repo.id}/archives/{a.id}/changes", headers=admin_headers)
        assert r.status_code == 200 and r.json()["changes"] == [] and r.json()["history_state"] == "pending"

    def test_compare_to_must_be_older_in_same_series(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        other = _archive(test_db, repo, "o", 1, series="other")
        assert test_client.get(f"/api/repositories/{repo.id}/archives/{a1.id}/changes?compare_to={a3.id}", headers=admin_headers).status_code == 400
        assert test_client.get(f"/api/repositories/{repo.id}/archives/{a3.id}/changes?compare_to={other.id}", headers=admin_headers).status_code == 400


@pytest.mark.unit
class TestHistory:
    def test_history_entries_and_present_ranges(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2)
        a3 = _archive(test_db, repo, "a3", 3)
        a4 = _archive(test_db, repo, "a4", 4)
        _change(test_db, a1, "docs/f", "added", after=1)
        _change(test_db, a2, "docs/f", "modified", before=1, after=2)
        _change(test_db, a3, "docs/f", "removed", before=2)
        _change(test_db, a4, "docs/f", "added", after=9)
        r = test_client.get(f"/api/repositories/{repo.id}/history?path=docs/f", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert [e["archive_id"] for e in body["entries"]] == [a4.id, a3.id, a2.id, a1.id]
        assert body["entries"][0]["change"] == "added" and body["entries"][0]["size_after"] == 9
        assert body["present"] == [
            {"series": "nas", "from_archive_id": a1.id, "to_archive_id": a3.id},
            {"series": "nas", "from_archive_id": a4.id, "to_archive_id": None},
        ]
        assert body["present_in_latest"] is True
        r = test_client.get(f"/api/repositories/{repo.id}/history?path=nope", headers=admin_headers)
        assert r.json()["entries"] == [] and r.json()["present_in_latest"] is False


@pytest.mark.unit
class TestSearch:
    def test_search_groups_by_path(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2)
        a3 = _archive(test_db, repo, "a3", 3)
        _change(test_db, a1, "docs/Invoice.xlsx", "added", after=1)
        _change(test_db, a2, "docs/Invoice.xlsx", "modified", before=1, after=2)
        _change(test_db, a1, "old/invoice.txt", "added", after=1)
        _change(test_db, a3, "old/invoice.txt", "removed", before=1)
        _change(test_db, a1, "photo.jpg", "added", after=1)
        r = test_client.get(f"/api/repositories/{repo.id}/search?q=invoice", headers=admin_headers)
        assert r.status_code == 200
        results = {x["path"]: x for x in r.json()["results"]}
        assert set(results) == {"docs/Invoice.xlsx", "old/invoice.txt"}
        inv = results["docs/Invoice.xlsx"]
        assert inv["archive_count"] == 2 and inv["first_seen_archive_id"] == a1.id and inv["last_seen_archive_id"] == a2.id
        assert inv["present_in_latest"] is True
        assert results["old/invoice.txt"]["present_in_latest"] is False
        assert r.json()["truncated"] is False
        r = test_client.get(f"/api/repositories/{repo.id}/search?q=invoice&limit=1", headers=admin_headers)
        assert len(r.json()["results"]) == 1 and r.json()["truncated"] is True
        assert test_client.get(f"/api/repositories/{repo.id}/search?q=", headers=admin_headers).status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/unit/test_api_archive_index.py -q -p no:cacheprovider`
Expected: the new classes FAIL with 404.

- [ ] **Step 3: Append the Pro routes**

Append to `app/api/archive_index.py`:

```python
# -- Pro routes (spec 11.2) -------------------------------------------------------

MAX_LIMIT = 500
ARCHIVE_HISTORY = require_feature("archive_history")


def _serialize_change(c: Change) -> dict:
    return {
        "path": c.path,
        "change": c.change,
        "size_before": c.size_before,
        "size_after": c.size_after,
        "mode_changed": c.mode_changed,
        "owner_changed": c.owner_changed,
        "summary_count": c.summary_count,
    }


def _totals(changes: list[Change]) -> dict:
    totals = {"added": 0, "removed": 0, "modified": 0, "summary": 0}
    for c in changes:
        totals[c.change] = totals.get(c.change, 0) + 1
    return totals


@router.get("/{repo_id}/archives/{archive_id}/changes", dependencies=[ARCHIVE_HISTORY])
async def archive_changes(
    repo_id: int,
    archive_id: int,
    compare_to: Optional[int] = None,
    path_prefix: Optional[str] = None,
    change: Optional[list[str]] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
    cursor: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Changes of one archive against its predecessor, or against an older
    archive of the same series with the intermediate deltas folded (spec
    9.2). `cursor` is an offset into the filtered, path-ordered result."""
    repository = _repo(db, current_user, repo_id)
    target = _archive_or_404(db, repository, archive_id)
    predecessor = predecessor_of(db, target)
    base = {
        "archive_id": target.id,
        "history_state": target.history_state,
        "history_truncated": target.history_truncated,
    }
    if compare_to is None:
        compare = predecessor
    else:
        compare = _archive_or_404(db, repository, compare_to)
        if compare.series != target.series or compare.start >= target.start:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.archives.compareMustBeOlderInSeries"},
            )
    if target.history_state != "indexed":
        return {**base, "compare_to_id": compare.id if compare else None, "changes": [],
                "totals": _totals([]), "next_cursor": None}
    if compare is None or (predecessor is not None and compare.id == predecessor.id):
        changes = list(
            rows_to_changes(
                db.query(ArchiveChange).filter(ArchiveChange.archive_id == target.id).all()
            ).values()
        )
    else:
        between = (
            db.query(Archive)
            .filter(
                Archive.repository_id == repository.id,
                Archive.series == target.series,
                Archive.start > compare.start,
                Archive.start <= target.start,
            )
            .order_by(Archive.start.asc(), Archive.id.asc())
            .all()
        )
        deltas = [
            rows_to_changes(db.query(ArchiveChange).filter(ArchiveChange.archive_id == a.id).all())
            for a in between
        ]
        changes = list(fold_sequence(deltas).values())
    if path_prefix:
        changes = [c for c in changes if c.path.startswith(path_prefix)]
    if change:
        wanted = set(change)
        changes = [c for c in changes if c.change in wanted]
    changes.sort(key=lambda c: c.path)
    page = changes[cursor : cursor + limit]
    next_cursor = cursor + limit if cursor + limit < len(changes) else None
    return {
        **base,
        "compare_to_id": compare.id if compare else None,
        "changes": [_serialize_change(c) for c in page],
        "totals": _totals(changes),
        "next_cursor": next_cursor,
    }


def present_ranges(entries: list[dict]) -> list[dict]:
    """`entries` ascending by start with keys series, archive_id, change.
    A range opens at an added or modified entry and closes at a removed one;
    an open range ends with `to_archive_id` None (still present)."""
    ranges: list[dict] = []
    open_by_series: dict[str, dict] = {}
    for e in entries:
        current = open_by_series.get(e["series"])
        if e["change"] in ("added", "modified"):
            if current is None:
                current = {"series": e["series"], "from_archive_id": e["archive_id"], "to_archive_id": None}
                open_by_series[e["series"]] = current
                ranges.append(current)
        elif e["change"] == "removed" and current is not None:
            current["to_archive_id"] = e["archive_id"]
            del open_by_series[e["series"]]
    return ranges


@router.get("/{repo_id}/history", dependencies=[ARCHIVE_HISTORY])
async def path_history(
    repo_id: int,
    path: str = Query(min_length=1),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repository = _repo(db, current_user, repo_id)
    rows = (
        db.query(ArchiveChange, Archive)
        .join(Archive, Archive.id == ArchiveChange.archive_id)
        .filter(Archive.repository_id == repository.id, ArchiveChange.path == path)
        .order_by(Archive.start.asc(), Archive.id.asc())
        .all()
    )
    ascending = [
        {
            "archive_id": a.id, "archive_name": a.name, "series": a.series, "start": a.start,
            "change": c.change, "size_before": c.size_before, "size_after": c.size_after,
            "mode_changed": c.mode_changed, "owner_changed": c.owner_changed,
        }
        for c, a in rows
    ]
    ranges = present_ranges(ascending)
    newest = (
        db.query(Archive).filter(Archive.repository_id == repository.id)
        .order_by(Archive.start.desc(), Archive.id.desc()).first()
    )
    present_in_latest = bool(
        newest and any(r["series"] == newest.series and r["to_archive_id"] is None for r in ranges)
    )
    return {
        "path": path,
        "entries": list(reversed(ascending)),
        "present": ranges,
        "present_in_latest": present_in_latest,
    }


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/{repo_id}/search", dependencies=[ARCHIVE_HISTORY])
async def search_paths(
    repo_id: int,
    q: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Filename search over archive_changes.path, grouped by path (spec
    9.2). Case-insensitive LIKE; FTS5 is a listed follow-up."""
    repository = _repo(db, current_user, repo_id)
    pattern = f"%{_like_escape(q)}%"
    rows = (
        db.query(ArchiveChange.path, ArchiveChange.change, Archive.id, Archive.start, Archive.series)
        .join(Archive, Archive.id == ArchiveChange.archive_id)
        .filter(
            Archive.repository_id == repository.id,
            ArchiveChange.change != "summary",
            func.lower(ArchiveChange.path).like(pattern.lower(), escape="\\"),
        )
        .order_by(ArchiveChange.path.asc(), Archive.start.asc(), Archive.id.asc())
        .all()
    )
    grouped: dict[str, dict] = {}
    for path, change, archive_id, start, series in rows:
        entry = grouped.setdefault(
            path,
            {"path": path, "first_seen_archive_id": archive_id, "first_seen": start,
             "last_seen_archive_id": archive_id, "last_seen": start, "archive_count": 0,
             "series": series, "last_change": change},
        )
        entry["archive_count"] += 1
        entry["last_seen_archive_id"] = archive_id
        entry["last_seen"] = start
        entry["last_change"] = change
    results = list(grouped.values())
    for entry in results:
        entry["present_in_latest"] = entry.pop("last_change") != "removed"
    truncated = len(results) > limit
    return {"query": q, "results": results[:limit], "truncated": truncated}
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/unit/test_api_archive_index.py -q -p no:cacheprovider`
Expected: PASS.

Run: `python -m pytest tests/unit -q -x -p no:cacheprovider && ruff check app tests`
Expected: PASS, no findings.

---

### Task 12: Documentation, Postman, phase verification, gate G2

**Files:**
- Modify: `docs/architecture/job-system.md:147-186` (Operations runner section)
- Modify: `docs/cache.md` (top of the document)
- Modify: `docs/api.md` (new section at the end)
- Modify: `Borg_UI_API.postman_collection.json` (new folder)
- Test: whole suite

- [ ] **Step 1: Job system doc**

Append to the "Operations runner" section of
`docs/architecture/job-system.md`, before "## Notifications":

```markdown
### History index

Two more index kinds fill and maintain `archive_changes`:

- `history_index` (exclusive, takes the lane) walks every series of a
  repository by archive start. The first archive of a series stores its
  full listing as `added` rows from `borg list --json-lines`; every later
  archive stores the output of `borg diff --json-lines` against its
  predecessor. Paths matching `repository.history_index_excludes` are
  dropped. Modified files get absolute sizes from the last known size of
  the path in the series, since `borg diff` only reports byte deltas. Past
  `INDEX_HISTORY_MAX_ROWS` the rest is collapsed into `summary` rows keyed
  by the first three path segments and the archive is marked truncated.
  Each archive is written in one transaction; a crash leaves it either
  fully indexed or pending. An archive whose predecessor is not indexed
  yet stays pending for the next run. Managed-agent repositories skip the
  stage with `agent_diff_unsupported`.
- `history_merge` consumes `removed_archive_ids` from the `archive_sync`
  it depends on. A removed archive's rows are folded into its successor
  (the table in the spec, section 8.4), or the successor is reset to
  pending when the removed archive was never indexed, or the rows are
  simply dropped when there is no successor. The archive row is deleted
  afterwards.

Both kinds exist only while the plan includes `archive_history`. On
Community installs the follow-up chains and the reconcile run omit them;
activating a Pro licence enqueues a reconcile run for every repository.
`POST /api/repositories/{id}/rebuild` with `from = history` resets the
index; `from = archives` refetches per-archive info; `from = stats`
re-measures the repository.
```

- [ ] **Step 2: Cache doc**

In `docs/cache.md`, after the sentence "There are two separate caches
involved in normal Docker deployments:" and its list, add:

```markdown
Neither cache is the persisted archive index. The `archives` and
`archive_changes` tables (see `docs/architecture/job-system.md`, "History
index") are written by the operations runner and never expire; they back
the archive list, the Changes tab, file history, and search. Folder
browsing keeps going through Borg and the caches above.
```

- [ ] **Step 3: API doc**

Append to `docs/api.md`:

```markdown
## Archive index and history

Database-backed archive routes under `/api/repositories/{id}`. Routes
marked Pro require the `archive_history` feature and return the standard
plan 403 payload otherwise.

| Method | Route | Plan | Purpose |
| --- | --- | --- | --- |
| GET | `/archives` | Community | Archives from the index with `series`, `since`, `until` filters and `sync_state` |
| GET | `/archives/live` | Community | The previous live `borg list` route, kept for the Archives page until it switches to the index |
| GET | `/archives/heatmap` | Community | Per series, per day counts and sizes; `missed_run` days; outlier flags on Pro |
| GET | `/archives/{archive_id}` | Community | One archive with history state and neighbours |
| GET | `/status-strip` | Community | Latest terminal operation per cell; overdue flags on Pro |
| POST | `/rebuild` | Community (`history` stage is Pro) | Body `{"from": "stats" | "archives" | "history"}` |
| GET | `/archives/{archive_id}/changes` | Pro | Changes against the predecessor or `compare_to` |
| GET | `/history?path=` | Pro | Every archive that touched a path, with present ranges |
| GET | `/search?q=` | Pro | Filename search across all archives |

`GET /api/archives/list` is deprecated and sends `Deprecation: true` with a
`Link` header pointing at the index route.
```

- [ ] **Step 4: Postman collection**

Add a folder to `Borg_UI_API.postman_collection.json` next to the other
numbered folders (copy the structure of an existing GET item, keeping the
collection's variable names for base URL and token):

```json
{
  "name": "Archive index and history",
  "item": [
    {"name": "List archives (index)", "request": {"method": "GET", "url": "{{baseUrl}}/api/repositories/1/archives"}},
    {"name": "Archive heatmap", "request": {"method": "GET", "url": "{{baseUrl}}/api/repositories/1/archives/heatmap"}},
    {"name": "Archive detail", "request": {"method": "GET", "url": "{{baseUrl}}/api/repositories/1/archives/1"}},
    {"name": "Archive changes (Pro)", "request": {"method": "GET", "url": "{{baseUrl}}/api/repositories/1/archives/1/changes"}},
    {"name": "Path history (Pro)", "request": {"method": "GET", "url": "{{baseUrl}}/api/repositories/1/history?path=home/user/file.txt"}},
    {"name": "Search paths (Pro)", "request": {"method": "GET", "url": "{{baseUrl}}/api/repositories/1/search?q=invoice"}},
    {"name": "Status strip", "request": {"method": "GET", "url": "{{baseUrl}}/api/repositories/1/status-strip"}},
    {"name": "Rebuild derived data", "request": {"method": "POST", "url": "{{baseUrl}}/api/repositories/1/rebuild", "body": {"mode": "raw", "raw": "{\"from\": \"stats\"}"}}}
  ]
}
```

Match the existing items' `header` and `auth` blocks exactly; validate with
`python -c "import json; json.load(open('Borg_UI_API.postman_collection.json'))"`.

- [ ] **Step 5: Phase verification (superpowers:verification-before-completion)**

Run, and paste the output at gate G2:

```bash
python -m pytest tests/unit -q -p no:cacheprovider
ruff check app tests
ruff format --check app tests
cd frontend && npx vitest run src/core src/services/planContent.test.ts src/pages/__tests__/Archives.delete.test.tsx && npm run lint
cd .. && DATA_DIR=$(mktemp -d) alembic upgrade head
diff -q docs/plan-content.json frontend/src/data/plan-content.json
grep -rnP "\xE2\x80\x94" app/services/operations app/api/archive_index.py app/core/borg_diff.py app/core/borg_stream.py docs/engineering/plans/2026-09-04-operations-phase-2-history.md; test $? -eq 1
```

Expected: tests pass (the 14 pre-existing OIDC failures noted in phase 1
are the only allowed failures, and only if they still fail on `main`),
lint clean, migration applies, plan-content copies identical, no em dashes.

Then, if the live container is reachable, one end-to-end check with
`borg-live-debug`: import a repository with three archives, watch
`/api/operations/queue` reach `history_index` completed, open
`/api/repositories/{id}/archives/{newest}/changes` (with a Pro
`LicensingState` row or on Community expect 403), prune one archive
outside Borg UI, `POST /rebuild {"from": "archives"}`, and confirm the
merge outcome in the next `history_merge` result. Record the result in
the spec's Notes column; if the container is unavailable, record "live
check not run" as phase 1 did.

- [ ] **Step 6: Gate G2**

Set the spec's phase 2 row to `in review`, show the verification output,
and ask whether to commit. Suggested commit message:
`feat(operations): phase 2 history index, merge, and archive routes`.

---

## Open questions

Answers are recorded in the spec's Appendix B once given.

1. **`GET /repositories/{id}/archives` already exists** as a live
   `borg list` route (`app/api/repositories.py:6028`) and is what the
   Archives page calls today (`api.ts:898`), not `/archives/list` as spec
   9.2 assumes. This plan moves the live route to
   `/{repo_id}/archives/live` and updates the one `api.ts` line, so the
   spec path serves the database and phases 3 and 4 build against the
   section 9 contract unchanged. Alternative: give the index route a
   different path and amend spec 9.2. Recommended: move the live route.
2. **Absolute sizes for modified files.** `borg diff` reports only bytes
   added and removed. The executor resolves `size_before` from the last
   known size of the path in the series (the first archive's listing seeds
   it) and derives `size_after`; when nothing is known both are null and
   the delta is not stored. Alternative: add a `size_delta` column, which
   changes spec 6.5. Recommended: resolve from history, no schema change.
3. **Directories are not stored** as change rows; links are, without
   sizes. Directory rows would double the row count for no query the spec
   lists. Confirm.
4. **Status strip before phases 5 to 8.** Backup, check, prune, compact,
   and mirror history lives in legacy tables until they migrate, so the
   strip consults them through `legacy_status.py`, deleted in phase 9 with
   `legacy_running_exclusive`. Alternative: show only `operations` rows,
   which leaves those cells empty for months. Recommended: consult legacy.
5. **`overdue` with no record at all** returns true (a never-checked
   repository is overdue for a check). Confirm or make it null.
6. **Startup bootstrap** (spec 14, "first startup after phase 2") is
   recorded on `SystemSettings.history_bootstrap_at` so it runs once per
   install, not on every restart. Confirm.
7. **`history_index_excludes` editing** ships as a field on
   `PUT /repositories/{id}` and in the repository payload; the settings UI
   for it is left to phase 4 with the other repository-page work. Confirm.
8. **Fixture capture needs the live container.** If `borg-live-debug`
   cannot reach it, Task 3 stops at gate G4 rather than hand-writing JSON.
9. **Model split across sessions:** Sonnet 5 for tasks 1 to 3, Fable 5.1
   for 4 to 6, Sonnet 5 for 7 to 12, with `/continue-spec` checking the
   model of the first unchecked task. Confirm, or run the whole phase on
   Fable 5.1.
10. **Search is case-insensitive** (`lower(path) LIKE`), which cannot use
    the `path` index; spec 6.5 already defers FTS5 to measurements.
    Confirm.
