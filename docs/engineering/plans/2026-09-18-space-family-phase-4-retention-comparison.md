# Space Family Phase 4: Retention Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents). Use
> superpowers:test-driven-development inside every task, and `ui-ux-pro-max`
> for the UI tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Do not
> commit at the end of a task; the phase has one commit gate (G2) at the end,
> per section 5.4 of the spec and `.claude/instructions.md`.

**Goal:** Run a fixed set of retention policies through the prune preview in
the background, store the results per repository, show them side by side on
the prune preview page, and surface the biggest saving on the dashboard
(spec 4.5).

**Architecture:** One new service module, `app/services/prune_compare.py`,
owns the candidate list (current policy plus three presets), the run that
stores one `prune_comparisons` row per candidate, the staleness rule and
the dashboard summary. It reuses the prune preview builder's steps 1 to 4,
which Task 3 extracts from `build_preview` into `run_candidate` so the page
and the comparison share one code path. A new operation kind
`prune_compare` (category maintenance, exclusive) runs as a follow-up of
`archive_sync` when the listing changed the archive set; the follow-up
filter lives in `enqueue_followups`. Two routes in
`app/api/archive_index.py` read and refresh the stored rows; the dashboard
overview gains `space_savings`. The frontend adds a `PruneComparedPolicies`
table under the preview, a `SpaceSavingsPanel` on the dashboard, and the
`?candidate=` query parameter on the preview page.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest with the
`db` / `repo` fixtures of `tests/unit/test_operations_index_executors.py`
and the `_repo` / `_archive` helpers and `test_client` / `admin_headers`
fixtures of `tests/unit/test_api_archive_index.py`; React 19, MUI, React
Router, `react-i18next`, TanStack Query, Vitest with `renderWithProviders`,
Storybook. No new dependencies. One migration.

**Spec:** `docs/engineering/specs/2026-09-16-pro-roadmap-search-space-source-guard.md`,
sections 4.4 (the builder this reuses), 4.5, 4.6, 4.7, 4.8 (phase 4 row),
5, Appendix B.

## Model

Section 4.8 names Sonnet 5 to implement phase 4 and Fable 5.1 to review
it. This plan was drafted on Fable 5.1 on 2026-09-18, so G0 passed for the
plan step. The implement step must check G0 against Sonnet 5 and record
any deviation in the 5.1 Notes column.

## Global Constraints

- Wording is fixed: "Compared policies" and "would free at least". Never
  "recommended" or "suggested" anywhere (UI copy, i18n, comments, API).
- The dashboard headline reads "frees the most of the compared policies".
- No em dashes anywhere: UI copy, i18n strings, comments, commit messages.
- No new feature key. Everything in this phase is Community (spec 4.6).
- Presets are fixed in code: `standard` (7 daily, 4 weekly, 6 monthly,
  1 yearly), `longer` (14 daily, 8 weekly, 12 monthly, 2 yearly), `wide`
  (30 daily, 12 monthly, 3 yearly). A preset equal to the current policy is
  dropped.
- Freed space is a lower bound (Appendix B): the sum of the candidates'
  fresh `deduplicated_size`. No chunk-level math.
- Every i18n key is added to all four locales (`en`, `de`, `es`, `it`);
  `npm run check:locales` must pass.
- Branch `feat/space-family-phase-4` from `main`, in a worktree
  (`~/Documents/Projects/borg-ui-space-family` may be reused: check out the
  new branch from `origin/main` there). Node 20.19.4 via fnm for `npm ci`.
- Backend tests run with `.venv/bin/python -m pytest` from the main
  checkout's venv (`../borg-ui/.venv/bin/python` from a sibling worktree).
- Do not commit until gate G2.

---

## File map

Backend:
- Modify `app/services/operations/vocab.py`: add the kind.
- Modify `app/services/operations/followups.py`: chain entry and the
  result-conditional filter.
- Modify `app/services/prune_preview.py`: extract `run_candidate`; let
  `run_prune_dry_run` nest under a parent operation.
- Create `app/services/prune_compare.py`: presets, candidates, the run,
  staleness, dashboard summary.
- Create `app/services/operations/executors/prune_compare.py`: the
  executor with its guards; register it in `executors/__init__.py`.
- Modify `app/database/models.py`: `PruneComparison`.
- Create `app/database/alembic/versions/b4c5d6e7f8a9_add_prune_comparisons.py`.
- Modify `app/api/archive_index.py`: the two routes.
- Modify `app/api/dashboard.py`: `space_savings` in the overview.

Frontend:
- Modify `frontend/src/types/operations.ts`, `frontend/src/types/archives.ts`,
  `frontend/src/pages/dashboard-v3/types.ts`, `frontend/src/services/api.ts`.
- Create `frontend/src/components/prune/formatRetention.ts`.
- Create `frontend/src/components/prune/PruneComparedPolicies.tsx` (+ story
  + test).
- Modify `frontend/src/pages/PrunePreview.tsx`.
- Create `frontend/src/pages/dashboard-v3/SpaceSavingsPanel.tsx` (+ story +
  test); modify `frontend/src/pages/DashboardV3.tsx`.
- Modify the four locale files.

---

### Task 1: The kind and its conditional follow-up

**Files:**
- Modify: `app/services/operations/vocab.py:14-30`
- Modify: `app/services/operations/followups.py:14-30` and `:163-195`
- Modify: `frontend/src/types/operations.ts:10-25`
- Test: `tests/unit/test_operations_vocab.py`, `tests/unit/test_operations_followups.py`

**Interfaces:**
- Produces: kind `"prune_compare"` with `KindSpec("maintenance", True)`;
  `FOLLOWUPS["archive_sync"] == ("prune_compare",)`;
  `followup_wanted(kind: str, operation) -> bool` in `followups.py`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_operations_vocab.py`, add to `EXPECTED_KINDS`:

```python
    "prune_compare": ("maintenance", True),
```

In `tests/unit/test_operations_followups.py`, change the
`test_chain_table_matches_spec_7_4` entry to
`"archive_sync": ("prune_compare",),` and add `"prune_compare": (),`.
Then add:

```python
@pytest.mark.unit
def test_prune_compare_follows_a_listing_that_changed_the_archive_set(
    db, repo, monkeypatch
):
    """Spec 4.5: the comparison hangs off archive_sync only when rows were
    added or removed, so an unchanged listing does not spend four dry runs."""
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    sync = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    sync.status = "completed"
    sync.result = {"listed": 3, "new": 0, "removed_archive_ids": []}
    db.commit()
    assert enqueue_followups(db, sync, depends_on_id=sync.id, available={"prune_compare"}) == []

    sync.result = {"listed": 4, "new": 1, "removed_archive_ids": []}
    db.commit()
    ops = enqueue_followups(db, sync, depends_on_id=sync.id, available={"prune_compare"})
    assert [o.kind for o in ops] == ["prune_compare"]
    assert ops[0].depends_on_id == sync.id
    assert ops[0].trigger == "followup"


@pytest.mark.unit
def test_prune_compare_follows_a_listing_that_removed_archives(db, repo, monkeypatch):
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    sync = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    sync.status = "completed"
    sync.result = {"listed": 2, "new": 0, "removed_archive_ids": [7]}
    db.commit()
    ops = enqueue_followups(db, sync, depends_on_id=sync.id, available={"prune_compare"})
    assert [o.kind for o in ops] == ["prune_compare"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_operations_vocab.py tests/unit/test_operations_followups.py -q`
Expected: FAIL (unknown kind; chain table mismatch; `ops == []`).

- [ ] **Step 3: Implement**

`vocab.py`, in `KINDS` after `"wipe"`:

```python
    "prune_compare": KindSpec("maintenance", True),
```

`followups.py`: set `"archive_sync": ("prune_compare",),` and add
`"prune_compare": (),` to `FOLLOWUPS`. Below `PLAN_GATED_KINDS` add:

```python
def followup_wanted(kind: str, operation) -> bool:
    """Spec 4.5: a retention comparison is worth four dry runs only when the
    listing that finished changed the archive set. Every other follow-up is
    unconditional."""
    if kind != "prune_compare":
        return True
    result = operation.result or {}
    return bool(result.get("new")) or bool(result.get("removed_archive_ids"))
```

In `enqueue_followups`, right after `kinds = chain_for_repository(...)`:

```python
    kinds = [k for k in kinds if followup_wanted(k, operation)]
```

`frontend/src/types/operations.ts`: add `| 'prune_compare'` after
`| 'wipe'` in the kind union.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/test_operations_vocab.py tests/unit/test_operations_followups.py tests/unit/test_operations_index_mode.py -q`
Expected: PASS. Then run `.venv/bin/python -m pytest tests/unit -q -k "followup or vocab or chain"` and make sure nothing else pinned the chain table.

---

### Task 2: The `prune_comparisons` table

**Files:**
- Modify: `app/database/models.py` (after `RepositoryStorage`, around line 660)
- Create: `app/database/alembic/versions/b4c5d6e7f8a9_add_prune_comparisons.py`
- Test: `tests/unit/test_prune_comparisons_migration.py`

**Interfaces:**
- Produces: model `PruneComparison` with columns `id`, `repository_id`,
  `candidate`, `label`, `retention` (JSON, nullable), `kept_count`,
  `deleted_count`, `freed_at_least` (BigInteger), `partial_measure`
  (Boolean), `operation_id` (nullable FK, SET NULL), `archive_count_at`,
  `computed_at`; unique on `(repository_id, candidate)`.

- [ ] **Step 1: Write the failing migration test**

Copy the structure of `tests/unit/test_archive_stats_measured_at_migration.py`
(its `_migrate` helper) into the new file with:

```python
"""Tests for revision b4c5d6e7f8a9 (prune_comparisons, spec 4.5)."""

import pytest
from alembic import command
from sqlalchemy import inspect

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "b4c5d6e7f8a9"
PREVIOUS = "a3b4c5d6e7f8"


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


@pytest.mark.unit
def test_upgrade_creates_and_downgrade_drops_the_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "prune_comparisons" not in _tables(url)
    _migrate(url, REVISION)
    assert "prune_comparisons" in _tables(url)
    engine = _engine(url)
    columns = {c["name"] for c in inspect(engine).get_columns("prune_comparisons")}
    engine.dispose()
    assert {
        "repository_id", "candidate", "label", "retention", "kept_count",
        "deleted_count", "freed_at_least", "partial_measure", "operation_id",
        "archive_count_at", "computed_at",
    } <= columns
    _migrate(url, PREVIOUS, down=True)
    assert "prune_comparisons" not in _tables(url)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_prune_comparisons_migration.py -q`
Expected: FAIL (revision not found).

- [ ] **Step 3: Model and migration**

`models.py`, after `RepositoryStorage`:

```python
class PruneComparison(Base):
    """Spec 4.5: one row per repository and candidate policy, replaced
    wholesale by each prune_compare run."""

    __tablename__ = "prune_comparisons"
    __table_args__ = (
        UniqueConstraint("repository_id", "candidate", name="uq_prune_comparison"),
    )

    id = Column(Integer, primary_key=True)
    repository_id = Column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate = Column(String, nullable=False)
    label = Column(String, nullable=False)
    retention = Column(JSON, nullable=True)
    kept_count = Column(Integer, nullable=False, default=0)
    deleted_count = Column(Integer, nullable=False, default=0)
    freed_at_least = Column(BigInteger, nullable=False, default=0)
    partial_measure = Column(Boolean, nullable=False, default=False)
    operation_id = Column(
        Integer, ForeignKey("operations.id", ondelete="SET NULL"), nullable=True
    )
    archive_count_at = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime, nullable=False, default=utc_now)
```

Check `UniqueConstraint`, `Boolean`, `BigInteger` and `JSON` are already
imported at the top of `models.py`; add any that is missing.

Migration file:

```python
"""add prune_comparisons

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-18
"""

from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prune_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Integer(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("candidate", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("retention", sa.JSON(), nullable=True),
        sa.Column("kept_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("freed_at_least", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("partial_measure", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "operation_id",
            sa.Integer(),
            sa.ForeignKey("operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("archive_count_at", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("repository_id", "candidate", name="uq_prune_comparison"),
    )
    op.create_index(
        "ix_prune_comparisons_repository_id", "prune_comparisons", ["repository_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_prune_comparisons_repository_id", table_name="prune_comparisons")
    op.drop_table("prune_comparisons")
```

- [ ] **Step 4: Run the migration test and the model import**

Run: `.venv/bin/python -m pytest tests/unit/test_prune_comparisons_migration.py tests/unit/test_archive_stats_measured_at_migration.py -q`
Expected: PASS. Also `.venv/bin/python -c "from app.database.models import PruneComparison"`.

---

### Task 3: Share the builder's steps 1 to 4

**Files:**
- Modify: `app/services/prune_preview.py:92-165` (`run_prune_dry_run`) and `:432-500` (`build_preview`)
- Test: `tests/unit/test_api_archive_index.py::TestPrunePreview` (existing, must stay green), `tests/unit/test_prune_preview.py`

**Interfaces:**
- Produces:

```python
@dataclass
class CandidateResult:
    operation: Operation
    log: str
    joined: list[PreviewArchive]
    candidates: list[Archive]      # deletion candidates, re-measured
    partial_measure: bool
    freed_at_least: int
    kept_count: int
    deleted_count: int

async def run_candidate(
    db, repository, retention, *, user_id, run_id=None, depends_on_id=None
) -> CandidateResult   # raises DryRunFailed
```

  and `run_prune_dry_run(..., run_id=None, depends_on_id=None)`.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_api_archive_index.py`, inside `TestPrunePreview`, add:

```python
    @pytest.mark.asyncio
    async def test_run_candidate_returns_counts_and_freed(self, test_db):
        from app.services import prune_preview as pp

        repo = _repo(test_db)
        kept = _archive(test_db, repo, name="a1", borg_id="a" * 64, deduplicated_size=10)
        gone = _archive(test_db, repo, name="a2", borg_id="b" * 64, deduplicated_size=30)
        log = (
            f"Keeping archive (rule: daily #1):            a1  Thu, 2026-09-17 15:07:55 [{kept.borg_id}]\n"
            f"Would prune:                                 a2  Thu, 2026-09-17 15:07:55 [{gone.borg_id}]\n"
        )
        with (
            patch.object(pp, "run_prune_dry_run", new=_fake_dry_run(log=log)),
            patch.object(pp, "remeasure_candidates", new=AsyncMock(return_value=False)),
        ):
            result = await pp.run_candidate(
                test_db, repo, pp.Retention(keep_daily=1), user_id=None
            )
        assert (result.kept_count, result.deleted_count) == (1, 1)
        assert result.freed_at_least == 30
        assert [a.id for a in result.candidates] == [gone.id]
        assert result.partial_measure is False
```

Match `_archive`'s real keyword names (read its signature at line 31) and
add `from unittest.mock import AsyncMock, patch` if missing.

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_api_archive_index.py -q -k run_candidate`
Expected: FAIL (`run_candidate` missing).

- [ ] **Step 3: Extract**

In `run_prune_dry_run`, add `run_id: Optional[str] = None,
depends_on_id: Optional[int] = None` keyword parameters and pass them to
`start_inline_maintenance(..., run_id=run_id, depends_on_id=depends_on_id)`.

Add the dataclass and function above `build_preview`:

```python
@dataclass
class CandidateResult:
    operation: Operation
    log: str
    joined: list[PreviewArchive]
    candidates: list[Archive]
    partial_measure: bool
    freed_at_least: int
    kept_count: int
    deleted_count: int


async def run_candidate(
    db: Session,
    repository: Repository,
    retention: Retention,
    *,
    user_id: Optional[int],
    run_id: Optional[str] = None,
    depends_on_id: Optional[int] = None,
) -> CandidateResult:
    """Spec 4.4 steps 1 to 4: dry run, verdict join, candidate re-measure,
    freed lower bound. Shared by the preview page and the comparison
    (spec 4.5). Raises DryRunFailed when Borg's dry run did not complete."""
    operation, log = await run_prune_dry_run(
        db, repository, retention, user_id=user_id, run_id=run_id, depends_on_id=depends_on_id
    )
    if operation.status not in ("completed", "completed_with_warnings"):
        raise DryRunFailed(log)
    joined = join_verdicts(db, repository, parse_prune_verdicts(log))
    by_id = {a.id: a for rows in archives_by_series(db, repository).values() for a in rows}
    candidates = [by_id[p.id] for p in joined if p.verdict == "deleted" and p.id in by_id]
    partial = await remeasure_candidates(db, repository, candidates)
    for p in joined:
        row = by_id.get(p.id) if p.id is not None else None
        if row is not None:
            p.deduplicated_size = row.deduplicated_size
            p.stats_measured_at = row.stats_measured_at
    return CandidateResult(
        operation=operation,
        log=log,
        joined=joined,
        candidates=candidates,
        partial_measure=partial,
        freed_at_least=freed_at_least(candidates),
        kept_count=sum(1 for p in joined if p.verdict == "kept"),
        deleted_count=sum(1 for p in joined if p.verdict == "deleted"),
    )
```

Rewrite `build_preview` to call it: keep the `pro = history_enabled(db)`
line first, then `r = await run_candidate(db, repository, retention,
user_id=user_id)`, and use `r.operation`, `r.log`, `r.joined`,
`r.candidates`, `r.partial_measure`, `r.freed_at_least`, `r.kept_count`,
`r.deleted_count` where the old locals were. The response dict must not
change.

- [ ] **Step 4: Run the preview tests**

Run: `.venv/bin/python -m pytest tests/unit/test_api_archive_index.py tests/unit/test_prune_preview.py -q`
Expected: PASS, same count as before plus one.

---

### Task 4: The comparison service

**Files:**
- Create: `app/services/prune_compare.py`
- Test: `tests/unit/test_prune_compare.py`

**Interfaces:**
- Consumes: `run_candidate`, `Retention`, `retention_defaults`,
  `DryRunFailed` from `app.services.prune_preview`; `pending_removed_ids`
  from `app.services.operations.repository_status`; `PruneComparison`.
- Produces:

```python
PRESETS: list[tuple[str, str, Retention]]   # (key, label, retention)
def candidates(db, repository) -> list[tuple[str, str, Optional[Retention]]]
def current_archive_count(db, repository) -> int
async def run_comparison(db, repository, *, run_id, depends_on_id) -> list[PruneComparison]
def stored(db, repository) -> dict          # the GET payload
def space_savings(db, repositories) -> list[dict]   # the dashboard list
```

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_prune_compare.py`, using the `db` and `repo` fixtures
copied from `tests/unit/test_operations_index_executors.py:16-40`:

```python
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, Base, PruneComparison, Repository, SystemSettings
from app.services import prune_compare as pc
from app.services.prune_preview import CandidateResult, DryRunFailed, Retention


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


def _archives(db, repo, n):
    rows = []
    for i in range(n):
        a = Archive(
            repository_id=repo.id,
            name=f"a{i}",
            borg_id=f"{i:064x}",
            start=datetime(2026, 9, 1) + timedelta(days=i),
            deduplicated_size=10 * (i + 1),
            first_seen_at=datetime(2026, 9, 1),
            last_seen_at=datetime(2026, 9, 1),
        )
        db.add(a)
        rows.append(a)
    db.commit()
    return rows


def _result(kept, deleted, freed, partial=False):
    op = type("Op", (), {"id": 99})()
    return CandidateResult(
        operation=op, log="", joined=[], candidates=[], partial_measure=partial,
        freed_at_least=freed, kept_count=kept, deleted_count=deleted,
    )


@pytest.mark.unit
def test_candidates_start_with_current_and_drop_an_equal_preset(db, repo, monkeypatch):
    monkeypatch.setattr(
        pc, "retention_defaults",
        lambda db, r: {"source": "plan", "plan_name": "p", "keep_hourly": 0, "keep_daily": 7,
                       "keep_weekly": 4, "keep_monthly": 6, "keep_quarterly": 0,
                       "keep_yearly": 1, "keep_within": None},
    )
    keys = [k for k, _, _ in pc.candidates(db, repo)]
    assert keys == ["current", "longer", "wide"]


@pytest.mark.unit
def test_candidates_without_a_policy_carry_a_none_retention(db, repo, monkeypatch):
    monkeypatch.setattr(pc, "retention_defaults", lambda db, r: {"source": "default",
        "keep_hourly": 0, "keep_daily": 0, "keep_weekly": 0, "keep_monthly": 0,
        "keep_quarterly": 0, "keep_yearly": 0, "keep_within": None})
    rows = pc.candidates(db, repo)
    assert rows[0][0] == "current" and rows[0][2] is None
    assert [k for k, _, _ in rows[1:]] == ["standard", "longer", "wide"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_comparison_stores_one_row_per_candidate(db, repo, monkeypatch):
    _archives(db, repo, 3)
    monkeypatch.setattr(pc, "retention_defaults", lambda db, r: {"source": "default",
        "keep_hourly": 0, "keep_daily": 0, "keep_weekly": 0, "keep_monthly": 0,
        "keep_quarterly": 0, "keep_yearly": 0, "keep_within": None})
    fake = AsyncMock(side_effect=[_result(2, 1, 30), _result(3, 0, 0), _result(1, 2, 50, True)])
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=5)
    by_key = {r.candidate: r for r in rows}
    assert set(by_key) == {"current", "standard", "longer", "wide"}
    assert by_key["current"].retention is None
    assert (by_key["current"].kept_count, by_key["current"].deleted_count) == (3, 0)
    assert by_key["current"].operation_id is None
    assert by_key["standard"].freed_at_least == 30
    assert by_key["wide"].partial_measure is True
    assert by_key["wide"].operation_id == 99
    assert all(r.archive_count_at == 3 for r in rows)
    assert fake.call_args_list[0].kwargs == {"user_id": None, "run_id": "run", "depends_on_id": 5}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_comparison_replaces_old_rows_and_skips_a_failed_dry_run(db, repo, monkeypatch):
    _archives(db, repo, 2)
    db.add(PruneComparison(repository_id=repo.id, candidate="stale_key", label="x",
                           kept_count=0, deleted_count=0, freed_at_least=0,
                           archive_count_at=1, computed_at=datetime(2026, 1, 1)))
    db.commit()
    monkeypatch.setattr(pc, "retention_defaults", lambda db, r: {"source": "default",
        "keep_hourly": 0, "keep_daily": 0, "keep_weekly": 0, "keep_monthly": 0,
        "keep_quarterly": 0, "keep_yearly": 0, "keep_within": None})
    fake = AsyncMock(side_effect=[DryRunFailed("boom"), _result(2, 0, 0), _result(1, 1, 5)])
    with patch.object(pc, "run_candidate", new=fake):
        rows = await pc.run_comparison(db, repo, run_id="run", depends_on_id=None)
    keys = {r.candidate for r in db.query(PruneComparison).filter_by(repository_id=repo.id)}
    assert keys == {"current", "longer", "wide"}
    assert "stale_key" not in keys


@pytest.mark.unit
def test_stored_reports_stale_when_the_archive_count_moved(db, repo):
    assert pc.stored(db, repo) == {"computed_at": None, "archive_count_at": None,
                                   "stale": True, "candidates": []}
    _archives(db, repo, 2)
    db.add(PruneComparison(repository_id=repo.id, candidate="standard", label="Standard",
                           retention=Retention().as_params(), kept_count=1, deleted_count=1,
                           freed_at_least=20, archive_count_at=2,
                           computed_at=datetime(2026, 9, 18, 1, 0)))
    db.commit()
    payload = pc.stored(db, repo)
    assert payload["stale"] is False
    assert payload["candidates"][0]["key"] == "standard"
    assert payload["candidates"][0]["freed_at_least"] == 20
    _archives(db, repo, 1)
    assert pc.stored(db, repo)["stale"] is True


@pytest.mark.unit
def test_space_savings_picks_the_best_row_per_repository_and_drops_zero(db, repo):
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4", borg_version=1)
    empty = Repository(name="e", path="/tmp/e", encryption="none", compression="lz4", borg_version=1)
    db.add_all([other, empty])
    db.commit()
    now = datetime(2026, 9, 18)
    db.add_all([
        PruneComparison(repository_id=repo.id, candidate="standard", label="Standard",
                        retention={}, kept_count=1, deleted_count=1, freed_at_least=20,
                        archive_count_at=0, computed_at=now),
        PruneComparison(repository_id=repo.id, candidate="wide", label="Wide",
                        retention={}, kept_count=1, deleted_count=1, freed_at_least=50,
                        archive_count_at=0, computed_at=now),
        PruneComparison(repository_id=other.id, candidate="wide", label="Wide",
                        retention={}, kept_count=1, deleted_count=1, freed_at_least=70,
                        archive_count_at=0, computed_at=now),
        PruneComparison(repository_id=empty.id, candidate="wide", label="Wide",
                        retention={}, kept_count=1, deleted_count=0, freed_at_least=0,
                        archive_count_at=0, computed_at=now),
    ])
    db.commit()
    rows = pc.space_savings(db, [repo, other, empty])
    assert [(r["repository_id"], r["candidate"], r["freed_at_least"]) for r in rows] == [
        (other.id, "wide", 70), (repo.id, "wide", 50)]
    assert rows[0]["repository_name"] == "o" and rows[0]["stale"] is False  # count 0 == archive_count_at 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_prune_compare.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `app/services/prune_compare.py`**

```python
"""Retention comparison (spec 4.5): a fixed set of policies run through the
prune preview's dry run and stored per repository. Wording is fixed:
compared policies, would free at least. Nothing here picks a policy for the user."""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import Archive, PruneComparison, Repository
from app.services.operations.repository_status import pending_removed_ids
from app.services.prune_preview import (
    DryRunFailed,
    Retention,
    retention_defaults,
    run_candidate,
)
from app.utils.datetime_utils import utc_now

PRESETS: list[tuple[str, str, Retention]] = [
    ("standard", "Standard", Retention(keep_daily=7, keep_weekly=4, keep_monthly=6, keep_yearly=1)),
    ("longer", "Longer", Retention(keep_daily=14, keep_weekly=8, keep_monthly=12, keep_yearly=2)),
    ("wide", "Wide", Retention(keep_daily=30, keep_weekly=0, keep_monthly=12, keep_yearly=3)),
]

_KEEP_FIELDS = (
    "keep_hourly", "keep_daily", "keep_weekly", "keep_monthly",
    "keep_quarterly", "keep_yearly", "keep_within",
)


def _current(db: Session, repository: Repository) -> Optional[Retention]:
    defaults = retention_defaults(db, repository)
    retention = Retention(**{k: defaults.get(k) or (None if k == "keep_within" else 0) for k in _KEEP_FIELDS})
    return retention if retention.has_rule else None


def candidates(db: Session, repository: Repository) -> list[tuple[str, str, Optional[Retention]]]:
    """The current policy first (None when there is none), then the presets
    that differ from it."""
    current = _current(db, repository)
    rows: list[tuple[str, str, Optional[Retention]]] = [("current", "Current", current)]
    for key, label, preset in PRESETS:
        if current is not None and preset.as_params() == current.as_params():
            continue
        rows.append((key, label, preset))
    return rows


def current_archive_count(db: Session, repository: Repository) -> int:
    removed = pending_removed_ids(db, repository.id)
    q = db.query(Archive.id).filter(Archive.repository_id == repository.id)
    if removed:
        q = q.filter(Archive.id.notin_(removed))
    return q.count()


async def run_comparison(
    db: Session, repository: Repository, *, run_id: Optional[str], depends_on_id: Optional[int]
) -> list[PruneComparison]:
    """Run every candidate, then replace the repository's rows wholesale. A
    candidate whose dry run failed is left out; the others still land."""
    count = current_archive_count(db, repository)
    computed_at = utc_now()
    rows: list[PruneComparison] = []
    for key, label, retention in candidates(db, repository):
        if retention is None:
            rows.append(PruneComparison(
                repository_id=repository.id, candidate=key, label=label, retention=None,
                kept_count=count, deleted_count=0, freed_at_least=0, partial_measure=False,
                operation_id=None, archive_count_at=count, computed_at=computed_at))
            continue
        try:
            result = await run_candidate(
                db, repository, retention, user_id=None, run_id=run_id, depends_on_id=depends_on_id
            )
        except DryRunFailed:
            continue
        rows.append(PruneComparison(
            repository_id=repository.id, candidate=key, label=label,
            retention=retention.as_params(), kept_count=result.kept_count,
            deleted_count=result.deleted_count, freed_at_least=result.freed_at_least,
            partial_measure=result.partial_measure, operation_id=result.operation.id,
            archive_count_at=count, computed_at=computed_at))
    db.query(PruneComparison).filter(PruneComparison.repository_id == repository.id).delete(
        synchronize_session=False
    )
    db.add_all(rows)
    db.commit()
    return rows


def _row_payload(row: PruneComparison) -> dict:
    return {
        "key": row.candidate,
        "label": row.label,
        "retention": row.retention,
        "kept_count": row.kept_count,
        "deleted_count": row.deleted_count,
        "freed_at_least": row.freed_at_least,
        "partial_measure": row.partial_measure,
        "operation_id": row.operation_id,
    }


def stored(db: Session, repository: Repository) -> dict:
    rows = (
        db.query(PruneComparison)
        .filter(PruneComparison.repository_id == repository.id)
        .order_by(PruneComparison.id)
        .all()
    )
    if not rows:
        return {"computed_at": None, "archive_count_at": None, "stale": True, "candidates": []}
    count_at = rows[0].archive_count_at
    return {
        "computed_at": rows[0].computed_at,
        "archive_count_at": count_at,
        "stale": current_archive_count(db, repository) != count_at,
        "candidates": [_row_payload(r) for r in rows],
    }


def space_savings(db: Session, repositories: list[Repository]) -> list[dict]:
    """Dashboard: the row that frees the most per repository, top three,
    repositories with nothing computed or nothing to free left out."""
    by_id = {r.id: r for r in repositories}
    rows = (
        db.query(PruneComparison)
        .filter(PruneComparison.repository_id.in_(list(by_id)), PruneComparison.freed_at_least > 0)
        .all()
    )
    best: dict[int, PruneComparison] = {}
    for row in rows:
        if row.repository_id not in best or row.freed_at_least > best[row.repository_id].freed_at_least:
            best[row.repository_id] = row
    out = []
    for repo_id, row in best.items():
        repository = by_id[repo_id]
        out.append({
            "repository_id": repo_id,
            "repository_name": repository.name,
            "candidate": row.candidate,
            "label": row.label,
            "retention": row.retention,
            "freed_at_least": row.freed_at_least,
            "computed_at": row.computed_at,
            "stale": current_archive_count(db, repository) != row.archive_count_at,
        })
    out.sort(key=lambda r: r["freed_at_least"], reverse=True)
    return out[:3]
```

`utc_now` comes from `app.utils.datetime_utils`, as in `models.py`.
`Retention(**{...})` must pass ints for the keep counts and `None` or a
string for `keep_within`; adjust the comprehension if `Retention`'s
fields disagree.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/test_prune_compare.py -q`
Expected: PASS (6 tests).

---

### Task 5: The executor and its guards

**Files:**
- Create: `app/services/operations/executors/prune_compare.py`
- Modify: `app/services/operations/executors/__init__.py:load_default_executors`
- Test: `tests/unit/test_operations_prune_compare_executor.py`

**Interfaces:**
- Consumes: `run_comparison`, `current_archive_count` (Task 4);
  `write_maintenance_running` from `app.services.operations.lanes`;
  `Outcome` from `app.services.operations.runner`; `ctx.operation`
  (the `Operation` row, with `run_id` and `id`).
- Produces: registered executor for kind `prune_compare`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Archive, Base, Operation, Repository, SystemSettings
from app.services.operations.executors import prune_compare as executor


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


def _op(db, repo):
    op = Operation(repository_id=repo.id, kind="prune_compare", category="maintenance",
                   status="running", trigger="followup", priority=10, run_id="run-1")
    db.add(op)
    db.commit()
    return op


def _ctx(db, repo, op):
    return SimpleNamespace(db=db, repository_id=repo.id, operation_id=op.id, operation=op,
                           kind="prune_compare", params={}, progress=AsyncMock(),
                           log=lambda line: None, cancelled=lambda: False)


def _archives(db, repo, n):
    for i in range(n):
        db.add(Archive(repository_id=repo.id, name=f"a{i}", borg_id=f"{i:064x}",
                       start=datetime(2026, 9, 1) + timedelta(days=i),
                       first_seen_at=datetime(2026, 9, 1), last_seen_at=datetime(2026, 9, 1)))
    db.commit()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_an_observe_only_repository(db, repo):
    repo.mode = "observe"
    db.commit()
    out = await executor.run_prune_compare(_ctx(db, repo, _op(db, repo)))
    assert (out.status, out.skip_reason) == ("skipped", "observe_only")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_with_fewer_than_two_archives(db, repo):
    _archives(db, repo, 1)
    out = await executor.run_prune_compare(_ctx(db, repo, _op(db, repo)))
    assert (out.status, out.skip_reason) == ("skipped", "too_few_archives")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_while_write_maintenance_is_pending(db, repo):
    _archives(db, repo, 3)
    db.add(Operation(repository_id=repo.id, kind="prune", category="maintenance",
                     status="queued", trigger="manual", priority=0, run_id="x"))
    db.commit()
    out = await executor.run_prune_compare(_ctx(db, repo, _op(db, repo)))
    assert (out.status, out.skip_reason) == ("skipped", "maintenance_pending")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runs_the_comparison_under_its_own_run(db, repo):
    _archives(db, repo, 3)
    op = _op(db, repo)
    fake = AsyncMock(return_value=[SimpleNamespace(candidate="standard")] * 2)
    with patch.object(executor, "run_comparison", new=fake):
        out = await executor.run_prune_compare(_ctx(db, repo, op))
    assert out.status == "completed"
    assert out.result == {"candidates": 2}
    assert fake.call_args.kwargs == {"run_id": "run-1", "depends_on_id": op.id}


@pytest.mark.unit
def test_executor_is_registered():
    from app.services.operations.executors import get_executor, load_default_executors

    load_default_executors()
    assert get_executor("prune_compare") is executor.run_prune_compare
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_operations_prune_compare_executor.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`app/services/operations/executors/prune_compare.py`:

```python
"""prune_compare executor (spec 4.5): the retention comparison, run as a
follow-up of a listing that changed the archive set."""

from app.database.models import Repository
from app.services.operations import executors
from app.services.operations.lanes import write_maintenance_running
from app.services.operations.runner import Outcome
from app.services.prune_compare import current_archive_count, run_comparison


async def run_prune_compare(ctx) -> Outcome:
    db = ctx.db
    repository = db.get(Repository, ctx.repository_id) if ctx.repository_id else None
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    if repository.mode == "observe":
        return Outcome(status="skipped", skip_reason="observe_only")
    if current_archive_count(db, repository) < 2:
        return Outcome(status="skipped", skip_reason="too_few_archives")
    if write_maintenance_running(db, repository.id):
        # A real prune, compact, delete or wipe is about to change the
        # answer; the listing it triggers brings the comparison back.
        return Outcome(status="skipped", skip_reason="maintenance_pending")
    rows = await run_comparison(
        db, repository, run_id=ctx.operation.run_id, depends_on_id=ctx.operation.id
    )
    ctx.log(f"compared {len(rows)} policies")
    return Outcome(result={"candidates": len(rows)})


executors.register("prune_compare", run_prune_compare)
```

Check that the `OperationContext` in `runner.py` exposes `operation` (it
does, `self.operation = operation` at line 129). If importing `Outcome`
from `runner` creates a circular import at module load, import it inside
the function as `executors/index.py` may do; copy that module's import
style.

In `executors/__init__.py`, add `prune_compare,` to the import list in
`load_default_executors` (alphabetical, after `package`).

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/test_operations_prune_compare_executor.py tests/unit/test_operations_index_executors.py -q`
Expected: PASS.

- [ ] **Step 5: Check the kind shows up correctly elsewhere**

Run: `.venv/bin/python -m pytest tests/unit -q -k "operations or activity or timeline or anomal or lanes"` and fix any test that enumerates kinds (add `prune_compare` where a list is asserted against `KINDS`). `OVERDUE_THRESHOLD_DAYS` is read with `.get`, so no entry is needed.

---

### Task 6: The two routes and the dashboard field

**Files:**
- Modify: `app/api/archive_index.py` (after `prune_retention_defaults`, line 450)
- Modify: `app/api/dashboard.py:1166` (the overview return dict)
- Test: `tests/unit/test_api_archive_index.py`, `tests/unit/test_api_dashboard.py`

**Interfaces:**
- Consumes: `stored`, `space_savings` (Task 4); `enqueue` from
  `app.services.operations.enqueue`.
- Produces: `GET /api/repositories/{id}/prune/comparison`,
  `POST /api/repositories/{id}/prune/comparison/refresh` returning
  `{"operation_id": int}`; overview key `space_savings`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_api_archive_index.py`, a new class after
`TestPrunePreview`:

```python
class TestPruneComparison:
    def test_get_returns_empty_and_stale_before_a_run(self, test_client, admin_headers, test_db):
        repo = _repo(test_db)
        res = test_client.get(f"/api/repositories/{repo.id}/prune/comparison", headers=admin_headers)
        assert res.status_code == 200
        assert res.json() == {"computed_at": None, "archive_count_at": None, "stale": True, "candidates": []}

    def test_get_returns_stored_rows(self, test_client, admin_headers, test_db):
        from datetime import datetime
        from app.database.models import PruneComparison

        repo = _repo(test_db)
        test_db.add(PruneComparison(repository_id=repo.id, candidate="standard", label="Standard",
                                    retention={"keep_daily": 7}, kept_count=2, deleted_count=1,
                                    freed_at_least=40, archive_count_at=0,
                                    computed_at=datetime(2026, 9, 18, 1)))
        test_db.commit()
        body = test_client.get(f"/api/repositories/{repo.id}/prune/comparison", headers=admin_headers).json()
        assert body["stale"] is False
        assert body["candidates"][0]["key"] == "standard"
        assert body["candidates"][0]["freed_at_least"] == 40

    def test_refresh_enqueues_one_operation_and_refuses_a_second(self, test_client, admin_headers, test_db, monkeypatch):
        from app.database.models import Operation

        monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
        repo = _repo(test_db)
        res = test_client.post(f"/api/repositories/{repo.id}/prune/comparison/refresh", headers=admin_headers)
        assert res.status_code == 200
        op = test_db.get(Operation, res.json()["operation_id"])
        assert (op.kind, op.status, op.trigger) == ("prune_compare", "queued", "manual")
        again = test_client.post(f"/api/repositories/{repo.id}/prune/comparison/refresh", headers=admin_headers)
        assert again.status_code == 409
```

In `tests/unit/test_api_dashboard.py`, find the class holding
`test_dashboard_overview_aggregates_real_database_state` and add a test
that seeds one `PruneComparison` row with `freed_at_least=40` for a
repository the test creates, calls `/api/dashboard/overview` the way that
test does, and asserts:

```python
        savings = res.json()["space_savings"]
        assert len(savings) == 1
        assert savings[0]["candidate"] == "standard"
        assert savings[0]["freed_at_least"] == 40
        assert set(savings[0]) >= {"repository_id", "repository_name", "label", "retention", "computed_at", "stale"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/test_api_archive_index.py -q -k Comparison` and `.venv/bin/python -m pytest tests/unit/test_api_dashboard.py -q -k space_savings`
Expected: FAIL (404 / KeyError).

- [ ] **Step 3: Implement**

`archive_index.py`, after `prune_retention_defaults`:

```python
@router.get("/{repo_id}/prune/comparison")
async def prune_comparison(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spec 4.5: the stored retention comparison, with `stale` when the
    archive count moved since it was computed."""
    from app.services.prune_compare import stored

    return stored(db, _repo(db, current_user, repo_id))


@router.post("/{repo_id}/prune/comparison/refresh")
async def prune_comparison_refresh(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.operations.enqueue import enqueue

    repository = _repo(db, current_user, repo_id, role="operator")
    pending = (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == repository.id,
            Operation.kind == "prune_compare",
            Operation.status.in_(("queued", "running")),
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(
            status_code=409, detail={"key": "backend.errors.prune.comparisonRunning"}
        )
    op = enqueue(
        db,
        "prune_compare",
        repository_id=repository.id,
        trigger="manual",
        triggered_by_user_id=current_user.id,
    )
    return {"operation_id": op.id}
```

Make sure `Operation` is imported in `archive_index.py` (it is used by
`retention_defaults` in the service, check the API module's imports).
Add the key `backend.errors.prune.comparisonRunning` to the four locale
files next to `backend.errors.prune.noKeepRule` (en: "A retention
comparison is already running for this repository."; de: "Für dieses
Repository läuft bereits ein Vergleich der Aufbewahrungsregeln."; es: "Ya
se está ejecutando una comparación de retención para este repositorio.";
it: "È già in corso un confronto delle regole di conservazione per questo
repository.").

`dashboard.py`: in `get_dashboard_overview`, before the `return {` at
line 1166 add:

```python
        from app.services.prune_compare import space_savings

        savings = space_savings(db, full_mode_repos)
```

and add `"space_savings": savings,` to the returned dict next to
`"upcoming_tasks"`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/unit/test_api_archive_index.py tests/unit/test_api_dashboard.py -q`
Expected: PASS.

---

### Task 7: Frontend API, types, kind label and retention formatter

**Files:**
- Modify: `frontend/src/types/archives.ts` (after `PruneRetentionDefaults`)
- Modify: `frontend/src/pages/dashboard-v3/types.ts` (after `upcoming_tasks`)
- Modify: `frontend/src/services/api.ts:988-991`
- Create: `frontend/src/components/prune/formatRetention.ts`
- Modify: the four locale files
- Test: `frontend/src/components/prune/__tests__/formatRetention.test.ts`

**Interfaces:**
- Produces:

```ts
export interface PruneComparisonRow {
  key: string
  label: string
  retention: PruneRetention | null   // keep_within null when unset
  kept_count: number
  deleted_count: number
  freed_at_least: number
  partial_measure: boolean
  operation_id: number | null
}
export interface PruneComparison {
  computed_at: string | null
  archive_count_at: number | null
  stale: boolean
  candidates: PruneComparisonRow[]
}
export interface SpaceSaving {
  repository_id: number
  repository_name: string
  candidate: string
  label: string
  retention: PruneRetention | null
  freed_at_least: number
  computed_at: string
  stale: boolean
}
repositoriesAPI.pruneComparison(id): Promise<AxiosResponse<PruneComparison>>
repositoriesAPI.pruneComparisonRefresh(id): Promise<AxiosResponse<{ operation_id: number }>>
formatRetention(r: PruneRetention | null): string   // "7d 4w 6m 1y", "within 2d 7d", "" for null
```

- [ ] **Step 1: Write the failing test**

`frontend/src/components/prune/__tests__/formatRetention.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatRetention } from '../formatRetention'

describe('formatRetention', () => {
  it('lists the non-zero keep rules in period order', () => {
    expect(
      formatRetention({
        keep_hourly: 0, keep_daily: 7, keep_weekly: 4, keep_monthly: 6,
        keep_quarterly: 0, keep_yearly: 1, keep_within: '',
      })
    ).toBe('7d 4w 6m 1y')
  })
  it('puts keep_within first and skips a null policy', () => {
    expect(
      formatRetention({
        keep_hourly: 2, keep_daily: 0, keep_weekly: 0, keep_monthly: 12,
        keep_quarterly: 1, keep_yearly: 3, keep_within: '2d',
      })
    ).toBe('within 2d 2h 12m 1q 3y')
    expect(formatRetention(null)).toBe('')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/prune/__tests__/formatRetention.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

`formatRetention.ts`:

```ts
import type { PruneRetention } from '../../types/archives'

const UNITS: Array<[keyof PruneRetention, string]> = [
  ['keep_hourly', 'h'],
  ['keep_daily', 'd'],
  ['keep_weekly', 'w'],
  ['keep_monthly', 'm'],
  ['keep_quarterly', 'q'],
  ['keep_yearly', 'y'],
]

/** One-line retention, e.g. "7d 4w 6m 1y". Empty for a missing policy. */
export function formatRetention(r: PruneRetention | null | undefined): string {
  if (!r) return ''
  const parts: string[] = []
  if (r.keep_within) parts.push(`within ${r.keep_within}`)
  for (const [field, unit] of UNITS) {
    const n = Number(r[field] ?? 0)
    if (n > 0) parts.push(`${n}${unit}`)
  }
  return parts.join(' ')
}
```

Add the three interfaces to `types/archives.ts` and `SpaceSaving` plus
`space_savings: SpaceSaving[]` to `dashboard-v3/types.ts` (import
`PruneRetention` from `../../types/archives`). In `api.ts` after
`pruneRetentionDefaults`:

```ts
  pruneComparison: (id: number) =>
    api.get<PruneComparison>(`/repositories/${id}/prune/comparison`),
  pruneComparisonRefresh: (id: number) =>
    api.post<{ operation_id: number }>(`/repositories/${id}/prune/comparison/refresh`),
```

and add `PruneComparison` to the `types/archives` import at the top.

Locales, `operations.kind` block (the object holding
`"history_merge": "Fold removed history"`, en.json line 3854): add
`"prune_compare": "Compare retention"` (de: "Aufbewahrung vergleichen",
es: "Comparar retención", it: "Confronta conservazione").

- [ ] **Step 4: Run**

Run: `cd frontend && npx vitest run src/components/prune && npm run typecheck && npm run check:locales`
Expected: PASS.

---

### Task 8: `PruneComparedPolicies` table

**Files:**
- Create: `frontend/src/components/prune/PruneComparedPolicies.tsx`
- Create: `frontend/src/components/prune/PruneComparedPolicies.stories.tsx`
- Test: `frontend/src/components/prune/__tests__/PruneComparedPolicies.test.tsx`
- Modify: the four locale files (`prunePreview.compare.*`)

**Interfaces:**
- Consumes: `PruneComparisonRow`, `formatRetention`, `formatBytes` from
  `../../utils/dateUtils` (the import `PrunePreviewNumbers.tsx` uses).
- Produces:

```ts
export interface EditingRow { retention: PruneRetention; kept_count: number; deleted_count: number; freed_at_least: number }
export function PruneComparedPolicies(props: {
  comparison: PruneComparison | null
  editing: EditingRow | null          // shown only when it differs from every stored row
  selectedKey: string | null          // row whose retention is in the editor
  pending: boolean                    // a refresh was requested and has not landed
  refreshDisabled: boolean
  onSelect: (row: PruneComparisonRow) => void
  onRefresh: () => void
}): JSX.Element
```

- [ ] **Step 1: i18n keys**

Add under `prunePreview` a `compare` object in all four locales. English:

```json
"compare": {
  "title": "Compared policies",
  "intro": "The same archives under other retention rules. Pick a row to preview it in full.",
  "computedOn": "Compared on {{date}}",
  "stale": "Numbers may have changed since the last comparison.",
  "notYet": "Not compared yet.",
  "compareNow": "Compare now",
  "comparing": "Comparing, this runs one dry run per policy.",
  "colPolicy": "Policy",
  "colRetention": "Retention",
  "colKept": "Kept",
  "colDeleted": "Deleted",
  "colFree": "Would free at least",
  "current": "Current",
  "currentNoPolicy": "No policy",
  "editing": "Editing",
  "presets": { "standard": "Standard", "longer": "Longer", "wide": "Wide" },
  "partial": "Some sizes are stored values, not re-measured."
}
```

German, Spanish and Italian translations of each string (keep the
`{{date}}` placeholder). No em dashes.

- [ ] **Step 2: Write the failing test**

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import { PruneComparedPolicies } from '../PruneComparedPolicies'
import type { PruneComparison } from '../../../types/archives'

const retention = (keep_daily: number) => ({
  keep_hourly: 0, keep_daily, keep_weekly: 4, keep_monthly: 6, keep_quarterly: 0, keep_yearly: 1, keep_within: null,
})

const comparison: PruneComparison = {
  computed_at: '2026-09-18T01:00:00Z',
  archive_count_at: 12,
  stale: false,
  candidates: [
    { key: 'current', label: 'Current', retention: retention(30), kept_count: 12, deleted_count: 0, freed_at_least: 0, partial_measure: false, operation_id: 1 },
    { key: 'standard', label: 'Standard', retention: retention(7), kept_count: 8, deleted_count: 4, freed_at_least: 40 * 1024 ** 3, partial_measure: true, operation_id: 2 },
  ],
}

describe('PruneComparedPolicies', () => {
  it('renders one row per candidate, marks the current one, and selects on click', () => {
    const onSelect = vi.fn()
    renderWithProviders(
      <PruneComparedPolicies comparison={comparison} editing={null} selectedKey="current"
        pending={false} refreshDisabled={false} onSelect={onSelect} onRefresh={() => {}} />
    )
    expect(screen.getByText('Compared policies')).toBeInTheDocument()
    expect(screen.getByText('7d 4w 6m 1y')).toBeInTheDocument()
    expect(screen.getByText('30d 4w 6m 1y')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Standard'))
    expect(onSelect).toHaveBeenCalledWith(comparison.candidates[1])
  })

  it('shows the editing row and the stale note', () => {
    renderWithProviders(
      <PruneComparedPolicies comparison={{ ...comparison, stale: true }}
        editing={{ retention: { ...retention(3), keep_within: '' }, kept_count: 4, deleted_count: 8, freed_at_least: 1024 }}
        selectedKey={null} pending={false} refreshDisabled={false} onSelect={() => {}} onRefresh={() => {}} />
    )
    expect(screen.getByText('Editing')).toBeInTheDocument()
    expect(screen.getByText('3d 4w 6m 1y')).toBeInTheDocument()
    expect(screen.getByText('Numbers may have changed since the last comparison.')).toBeInTheDocument()
  })

  it('offers compare now when nothing is stored, and says comparing while pending', () => {
    const onRefresh = vi.fn()
    const { rerender } = renderWithProviders(
      <PruneComparedPolicies comparison={{ computed_at: null, archive_count_at: null, stale: true, candidates: [] }}
        editing={null} selectedKey={null} pending={false} refreshDisabled={false} onSelect={() => {}} onRefresh={onRefresh} />
    )
    expect(screen.getByText('Not compared yet.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Compare now' }))
    expect(onRefresh).toHaveBeenCalled()
    rerender(
      <PruneComparedPolicies comparison={null} editing={null} selectedKey={null}
        pending={true} refreshDisabled={true} onSelect={() => {}} onRefresh={onRefresh} />
    )
    expect(screen.getByText('Comparing, this runs one dry run per policy.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Compare now' })).toBeDisabled()
  })
})
```

Check how `renderWithProviders` returns `rerender` (it wraps RTL's
`render`; if it does not expose `rerender`, render twice instead).

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/prune/__tests__/PruneComparedPolicies.test.tsx`
Expected: FAIL (module missing).

- [ ] **Step 4: Implement**

Follow the `Paper variant="outlined" sx={{ p: 2 }}` pattern the preview
page uses, and the `ButtonBase` row pattern of `PruneCandidatesRanked.tsx`
for clickable rows:

```tsx
import { useTranslation } from 'react-i18next'
import {
  Alert, Box, Button, ButtonBase, Chip, Paper, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, Typography,
} from '@mui/material'
import { formatBytes, formatDateTimeFull } from '../../utils/dateUtils'
import { formatRetention } from './formatRetention'
import type { PruneComparison, PruneComparisonRow, PruneRetention } from '../../types/archives'

export interface EditingRow {
  retention: PruneRetention
  kept_count: number
  deleted_count: number
  freed_at_least: number
}

interface Props {
  comparison: PruneComparison | null
  editing: EditingRow | null
  selectedKey: string | null
  pending: boolean
  refreshDisabled: boolean
  onSelect: (row: PruneComparisonRow) => void
  onRefresh: () => void
}

export function PruneComparedPolicies({
  comparison, editing, selectedKey, pending, refreshDisabled, onSelect, onRefresh,
}: Props) {
  const { t } = useTranslation()
  const rows = comparison?.candidates ?? []
  const label = (row: PruneComparisonRow) =>
    row.key === 'current'
      ? row.retention ? t('prunePreview.compare.current') : t('prunePreview.compare.currentNoPolicy')
      : t(`prunePreview.compare.presets.${row.key}`, { defaultValue: row.label })
  const partial = rows.some((r) => r.partial_measure)

  return (
    <Paper variant="outlined" sx={{ p: 2, mt: 3 }}>
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            {t('prunePreview.compare.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {pending
              ? t('prunePreview.compare.comparing')
              : comparison?.computed_at
                ? t('prunePreview.compare.computedOn', { date: formatDateTimeFull(comparison.computed_at) })
                : t('prunePreview.compare.notYet')}
          </Typography>
        </Box>
        <Button size="small" variant="outlined" onClick={onRefresh} disabled={refreshDisabled || pending}>
          {t('prunePreview.compare.compareNow')}
        </Button>
      </Stack>
      {comparison?.stale && rows.length > 0 && !pending && (
        <Alert severity="info" sx={{ mb: 1 }}>{t('prunePreview.compare.stale')}</Alert>
      )}
      {(rows.length > 0 || editing) && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('prunePreview.compare.colPolicy')}</TableCell>
              <TableCell>{t('prunePreview.compare.colRetention')}</TableCell>
              <TableCell align="right">{t('prunePreview.compare.colKept')}</TableCell>
              <TableCell align="right">{t('prunePreview.compare.colDeleted')}</TableCell>
              <TableCell align="right">{t('prunePreview.compare.colFree')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.key} selected={row.key === selectedKey} hover>
                <TableCell>
                  <ButtonBase onClick={() => onSelect(row)} sx={{ fontWeight: 600, textAlign: 'left' }}>
                    {label(row)}
                  </ButtonBase>
                </TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{formatRetention(row.retention)}</TableCell>
                <TableCell align="right">{row.kept_count}</TableCell>
                <TableCell align="right">{row.deleted_count}</TableCell>
                <TableCell align="right">{formatBytes(row.freed_at_least)}</TableCell>
              </TableRow>
            ))}
            {editing && (
              <TableRow selected>
                <TableCell><Chip size="small" label={t('prunePreview.compare.editing')} /></TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{formatRetention(editing.retention)}</TableCell>
                <TableCell align="right">{editing.kept_count}</TableCell>
                <TableCell align="right">{editing.deleted_count}</TableCell>
                <TableCell align="right">{formatBytes(editing.freed_at_least)}</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
      {partial && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {t('prunePreview.compare.partial')}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
        {t('prunePreview.compare.intro')}
      </Typography>
    </Paper>
  )
}
```

Check `formatDateTimeFull` exists in `utils/dateUtils` (it is imported by
`UpcomingBackupsPanel.tsx`) and that a row without an operation id still
renders (no link is drawn from `operation_id`; it is kept for the API).

Story `PruneComparedPolicies.stories.tsx`: three stories, `Stored`,
`WithEditingRowStale`, `Empty`, using the same fixture data as the test,
following `PruneCandidatesRanked.stories.tsx` for the meta shape.

- [ ] **Step 5: Run**

Run: `cd frontend && npx vitest run src/components/prune && npm run typecheck && npm run lint && npm run check:locales`
Expected: PASS.

---

### Task 9: Preview page integration and `?candidate=`

**Files:**
- Modify: `frontend/src/pages/PrunePreview.tsx`
- Test: `frontend/src/pages/__tests__/PrunePreview.test.tsx`

**Interfaces:**
- Consumes: `PruneComparedPolicies`, `repositoriesAPI.pruneComparison`,
  `repositoriesAPI.pruneComparisonRefresh`.

- [ ] **Step 1: Write the failing tests**

Extend the `vi.mock('../../services/api', ...)` block so
`repositoriesAPI.pruneComparison` and `pruneComparisonRefresh` are
`vi.fn()`s, then add:

```tsx
  const storedComparison = {
        computed_at: '2026-09-18T01:00:00Z', archive_count_at: 2, stale: false,
        candidates: [
          { key: 'current', label: 'Current', retention: { keep_hourly: 0, keep_daily: 30, keep_weekly: 0, keep_monthly: 0, keep_quarterly: 0, keep_yearly: 0, keep_within: null }, kept_count: 2, deleted_count: 0, freed_at_least: 0, partial_measure: false, operation_id: 1 },
          { key: 'standard', label: 'Standard', retention: { keep_hourly: 0, keep_daily: 7, keep_weekly: 4, keep_monthly: 6, keep_quarterly: 0, keep_yearly: 1, keep_within: null }, kept_count: 1, deleted_count: 1, freed_at_least: 100, partial_measure: false, operation_id: 2 },
        ],
  }

  it('lists compared policies and previews a row on click', async () => {
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({ data: storedComparison } as never)
    renderPage()   // the file's existing render helper with defaults resolved
    await waitFor(() => expect(screen.getByText('Compared policies')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Standard'))
    await waitFor(() =>
      expect(repositoriesAPI.prunePreview).toHaveBeenLastCalledWith(
        1,
        expect.objectContaining({ keep_daily: 7, keep_weekly: 4, keep_monthly: 6, keep_yearly: 1, keep_within: '' })
      )
    )
  })

  it('starts from the candidate named in the query string', async () => {
    // Mock useSearchParams (or render at '?candidate=standard' if the
    // helper takes a route) so the page opens with candidate=standard.
    vi.mocked(repositoriesAPI.pruneComparison).mockResolvedValue({ data: storedComparison } as never)
    renderPage({ search: '?candidate=standard' })
    await waitFor(() =>
      expect(repositoriesAPI.prunePreview).toHaveBeenCalledWith(1, expect.objectContaining({ keep_daily: 7 }))
    )
    expect(repositoriesAPI.prunePreview).toHaveBeenCalledTimes(1)
  })

  it('compare now posts a refresh and polls until a newer comparison lands', async () => {
    vi.mocked(repositoriesAPI.pruneComparison)
      .mockResolvedValueOnce({ data: { computed_at: null, archive_count_at: null, stale: true, candidates: [] } } as never)
      .mockResolvedValue({ data: { computed_at: '2026-09-18T02:00:00Z', archive_count_at: 2, stale: false, candidates: [] } } as never)
    vi.mocked(repositoriesAPI.pruneComparisonRefresh).mockResolvedValue({ data: { operation_id: 9 } } as never)
    renderPage()
    await waitFor(() => expect(screen.getByText('Not compared yet.')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Compare now' }))
    await waitFor(() => expect(repositoriesAPI.pruneComparisonRefresh).toHaveBeenCalledWith(1))
    expect(screen.getByText('Comparing, this runs one dry run per policy.')).toBeInTheDocument()
  })
```

Read the existing test file's render helper and router mock first and
adapt `renderPage` and the `?candidate=` setup to what it provides (the
file mocks `react-router-dom`; add `useSearchParams` to that mock
returning `[new URLSearchParams(search), vi.fn()]`).

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/pages/__tests__/PrunePreview.test.tsx`
Expected: the three new tests FAIL.

- [ ] **Step 3: Implement in `PrunePreview.tsx`**

Additions, in order:

```tsx
import { useSearchParams } from 'react-router-dom'   // add to the existing import
import { PruneComparedPolicies } from '../components/prune/PruneComparedPolicies'
import type { PruneComparisonRow } from '../types/archives'

const toForm = (r: PruneComparisonRow['retention']): PruneRetention | null =>
  r ? { ...r, keep_within: r.keep_within ?? '' } : null
```

Inside the component, after the defaults query:

```tsx
  const [searchParams] = useSearchParams()
  const candidateKey = searchParams.get('candidate')
  const [pendingSince, setPendingSince] = useState<string | null>(null)
  const comparisonQuery = useQuery({
    queryKey: ['prune-comparison', repositoryId],
    queryFn: () => repositoriesAPI.pruneComparison(repositoryId).then((res) => res.data),
    enabled: Number.isFinite(repositoryId),
    refetchInterval: pendingSince ? 5000 : false,
  })
  const comparison = comparisonQuery.data ?? null
  useEffect(() => {
    if (pendingSince && comparison?.computed_at && comparison.computed_at > pendingSince) {
      setPendingSince(null)
    }
  }, [comparison, pendingSince])
  const refreshMutation = useMutation({
    mutationFn: () => repositoriesAPI.pruneComparisonRefresh(repositoryId),
    onSuccess: () => setPendingSince(new Date().toISOString()),
    onError: () => toast.error(t('prunePreview.compare.refreshFailed')),
  })
  const candidateRetention = useMemo(
    () => (candidateKey && comparison ? toForm(comparison.candidates.find((c) => c.key === candidateKey)?.retention ?? null) : null),
    [candidateKey, comparison]
  )
```

Add the i18n key `prunePreview.compare.refreshFailed` ("Could not start
the comparison." and translations) to the four locales.

Change the first-preview effect so a `?candidate=` waits for the
comparison and wins over the defaults:

```tsx
    if (candidateKey && comparisonQuery.isPending) return
    const initial = stateRetention ?? candidateRetention ?? defaultRetention
```

and add `candidateRetention, comparisonQuery.isPending, candidateKey` to
its dependency array. Note the string comparison of ISO timestamps only
works when both carry the same zone; the backend serialises
`computed_at` as naive UTC, so compare `new Date(x).getTime()` instead if
the test shows a mismatch.

Selected row and editing row:

```tsx
  const selectedKey = useMemo(() => {
    if (!previewedRetention || !comparison) return null
    return comparison.candidates.find(
      (c) => JSON.stringify(toForm(c.retention)) === JSON.stringify(previewedRetention)
    )?.key ?? null
  }, [comparison, previewedRetention])
  const editing =
    preview && previewedRetention && selectedKey === null
      ? { retention: previewedRetention, kept_count: preview.kept_count, deleted_count: preview.deleted_count, freed_at_least: preview.freed_at_least }
      : null
```

Render, after the warnings `Paper` (line 316 block) and before the log
disclosure:

```tsx
          <PruneComparedPolicies
            comparison={comparison}
            editing={editing}
            selectedKey={selectedKey}
            pending={pendingSince !== null}
            refreshDisabled={!ready || previewMutation.isPending}
            onSelect={(row) => {
              const form = toForm(row.retention)
              if (!form) return
              setRetention(form)
              previewMutation.mutate(form)
            }}
            onRefresh={() => refreshMutation.mutate()}
          />
```

Place it so it renders whether or not a preview has loaded (outside the
`preview &&` block), since an empty comparison must still offer "Compare
now".

- [ ] **Step 4: Run**

Run: `cd frontend && npx vitest run src/pages/__tests__/PrunePreview.test.tsx && npm run typecheck && npm run lint`
Expected: PASS.

---

### Task 10: Dashboard card

**Files:**
- Create: `frontend/src/pages/dashboard-v3/SpaceSavingsPanel.tsx`
- Create: `frontend/src/pages/dashboard-v3/SpaceSavingsPanel.stories.tsx`
- Test: `frontend/src/pages/dashboard-v3/__tests__/SpaceSavingsPanel.test.tsx` (create the directory if the folder has no `__tests__`; check where `ActivityTimeline.test.tsx` sits and follow it)
- Modify: `frontend/src/pages/DashboardV3.tsx:516` (after `UpcomingBackupsPanel`)
- Modify: the four locale files (`dashboard.spaceSavings.*`)

**Interfaces:**
- Consumes: `SpaceSaving`, `formatBytes`, `formatRetention`, `useT` from
  `./tokens`.
- Produces: `SpaceSavingsPanel({ rows, onNavigate }: { rows: SpaceSaving[]; onNavigate: (route: string) => void })`.

- [ ] **Step 1: i18n keys**

Under `dashboard` in all four locales:

```json
"spaceSavings": {
  "title": "Space you could free",
  "line": "at least {{size}} with {{retention}}",
  "hint": "Frees the most of the compared policies. Open to preview it.",
  "stale": "may have changed"
}
```

- [ ] **Step 2: Write the failing test**

```tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import { SpaceSavingsPanel } from '../SpaceSavingsPanel'

const row = {
  repository_id: 3, repository_name: 'nas', candidate: 'standard', label: 'Standard',
  retention: { keep_hourly: 0, keep_daily: 7, keep_weekly: 4, keep_monthly: 6, keep_quarterly: 0, keep_yearly: 1, keep_within: null },
  freed_at_least: 40 * 1024 ** 3, computed_at: '2026-09-18T01:00:00Z', stale: true,
}

describe('SpaceSavingsPanel', () => {
  it('renders nothing without rows', () => {
    const { container } = renderWithProviders(<SpaceSavingsPanel rows={[]} onNavigate={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })
  it('links each line to the preview with the candidate preselected', () => {
    const onNavigate = vi.fn()
    renderWithProviders(<SpaceSavingsPanel rows={[row]} onNavigate={onNavigate} />)
    expect(screen.getByText('Space you could free')).toBeInTheDocument()
    expect(screen.getByText('nas')).toBeInTheDocument()
    expect(screen.getByText(/7d 4w 6m 1y/)).toBeInTheDocument()
    expect(screen.getByText('may have changed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /nas/ }))
    expect(onNavigate).toHaveBeenCalledWith('/repositories/3/prune-preview?candidate=standard')
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npx vitest run src/pages/dashboard-v3`
Expected: FAIL (module missing).

- [ ] **Step 4: Implement**

Model the card on `UpcomingBackupsPanel.tsx` (same outer `Box` with
`T.bgCard`, `T.border`, `T.radius`, the icon row with a lucide icon, here
`HardDrive`):

```tsx
import { Box, ButtonBase, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { HardDrive } from 'lucide-react'
import { formatBytes } from '../../utils/dateUtils'
import { formatRetention } from '../../components/prune/formatRetention'
import { useT } from './tokens'
import type { SpaceSaving } from './types'

export function SpaceSavingsPanel({
  rows, onNavigate,
}: { rows: SpaceSaving[]; onNavigate: (route: string) => void }) {
  const T = useT()
  const { t } = useTranslation()
  if (rows.length === 0) return null
  return (
    <Box sx={{ bgcolor: T.bgCard, border: `1px solid ${T.border}`, borderRadius: T.radius, p: 2.5, transition: 'border-color 0.2s', '&:hover': { borderColor: T.borderHover } }}>
      <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', mb: 0.5 }}>
        <HardDrive size={14} color={T.textMuted} />
        <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary }}>
          {t('dashboard.spaceSavings.title')}
        </Typography>
      </Stack>
      <Typography sx={{ fontSize: '0.75rem', color: T.textMuted, mb: 1.5 }}>
        {t('dashboard.spaceSavings.hint')}
      </Typography>
      <Stack spacing={1}>
        {rows.map((row) => (
          <ButtonBase
            key={row.repository_id}
            onClick={() => onNavigate(`/repositories/${row.repository_id}/prune-preview?candidate=${row.candidate}`)}
            sx={{ display: 'block', textAlign: 'left', width: '100%', border: `1px solid ${T.border}`, borderRadius: '8px', p: 1.25 }}
          >
            <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary }}>
              {row.repository_name}
            </Typography>
            <Typography sx={{ fontSize: '0.75rem', color: T.textMuted }}>
              {t('dashboard.spaceSavings.line', { size: formatBytes(row.freed_at_least), retention: formatRetention(row.retention) })}
              {row.stale ? ' ' : ''}
              {row.stale && <Box component="span" sx={{ fontStyle: 'italic' }}>{t('dashboard.spaceSavings.stale')}</Box>}
            </Typography>
          </ButtonBase>
        ))}
      </Stack>
    </Box>
  )
}
```

The `getByText('may have changed')` assertion needs the stale note in its
own element, which the `Box component="span"` gives it.

In `DashboardV3.tsx`, after `<UpcomingBackupsPanel tasks={ov.upcoming_tasks} />`:

```tsx
            <SpaceSavingsPanel
              rows={ov.space_savings ?? []}
              onNavigate={(route) => {
                trackNavigation(EventAction.VIEW, { section: 'dashboard', destination: route.substring(1), source: 'space_savings' })
                navigate(route)
              }}
            />
```

with the import next to `UpcomingBackupsPanel`'s. Check the
`trackNavigation` call shape against the `CapabilityLaunchpad` one at
line 505 and match it. Any dashboard fixture or mock overview object in
tests or stories that is typed as `DashboardOverview` needs
`space_savings: []`; run the typecheck to find them.

Story `SpaceSavingsPanel.stories.tsx`: `ThreeRows` and `OneStale`,
following `UpcomingBackupsPanel`'s neighbour `ActivityTimeline.stories.tsx`
for the meta shape.

- [ ] **Step 5: Run**

Run: `cd frontend && npx vitest run src/pages/dashboard-v3 src/pages/__tests__/DashboardV3.test.tsx && npm run typecheck && npm run lint && npm run check:locales`
Expected: PASS (adjust the DashboardV3 test path to whatever exists).

---

### Task 11: Visual check and full verification

**Files:** none new.

- [ ] **Step 1: Storybook, light and dark**

Start Storybook (fnm Node 24 per the memory note, `nohup npm run
storybook &`), open `PruneComparedPolicies` (`Stored`,
`WithEditingRowStale`, `Empty`) and `SpaceSavingsPanel` (`ThreeRows`,
`OneStale`) in light and dark, and at 400px width. Screenshot each. Fix
any overflow: the table goes in a `Box sx={{ overflowX: 'auto' }}` if the
five columns do not fit at 400px.

- [ ] **Step 2: Backend suite**

Run: `.venv/bin/python -m pytest tests/unit -q -x`
Expected: all pass. Then `.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests`.

- [ ] **Step 3: Frontend suite**

Run: `cd frontend && npm run typecheck && npm run lint && npx vitest run && npm run check:locales && npm run format:check`
Expected: all pass.

- [ ] **Step 4: Live smoke (optional but preferred)**

With the dev container (`borg-live-debug`), trigger a listing on a
repository with three or more archives, confirm a `prune_compare`
operation appears under it in the activity view with its dry-run children,
then open the preview page and the dashboard. Wording check: grep the diff
for "recommend" and "suggest"; there must be none.

- [ ] **Step 5: Gate G2**

Report: tests run and their counts, screenshots taken, any deviation from
this plan or the spec. Do not commit until the user answers G2. Update the
spec's 5.1 row for phase 4 with the outcome.
