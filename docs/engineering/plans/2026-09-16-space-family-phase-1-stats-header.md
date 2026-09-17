# Space Family Phase 1: Stats Freshness and Archive Header Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents). Use
> superpowers:test-driven-development inside every task, and `ui-ux-pro-max`
> for the UI tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Do not
> commit at the end of a task; the phase has one commit gate (G2) at the end,
> per section 5.4 of the spec and `.claude/instructions.md`.

**Goal:** Give every archive's stored Borg figures a measurement date that
goes stale when the repository loses archives and is refreshed by the
existing info loop (spec 4.1), and replace the archive detail header's chip
row with a stats header that leads with what the archive added to the
repository and shows deltas against its predecessor (spec 4.2).

**Architecture:** One new nullable column, `archives.stats_measured_at`,
written by `fill_archive_info` and cleared for every surviving archive by
`run_archive_sync` when a listing observes removed archives. The selector
`archives_needing_info` switches from "no sizes" to "no measurement date",
which covers never-measured and stale rows with the same bounded loop. The
detail route adds a `predecessor_stats` object so the header draws deltas
from the single request the page already makes. On the frontend one new
component, `ArchiveStatsHeader`, owns the tiles; `ArchiveDetail.tsx` only
swaps the chip row for it.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic (plain `add_column` and
`drop_column`: a batch rebuild of `archives` on SQLite cascades into
`archive_changes`), pytest with the `db` / `repo` fixtures of
`tests/unit/test_operations_index_executors.py` and the `test_client` /
`admin_headers` fixtures of `tests/unit/test_api_archive_index.py`; React,
MUI, `react-i18next`, TanStack Query, Vitest with `renderWithProviders`,
Storybook. No new dependencies.

**Spec:** `docs/engineering/specs/2026-09-16-pro-roadmap-search-space-source-guard.md`,
sections 4.1, 4.2, 4.6, 4.7, 4.8 (phase 1 row), 5, Appendix B.

## Model

Section 4.8 names Fable 5.1 to implement and review phase 1. This plan was
drafted on Fable 5.1 on 2026-09-16, so G0 passed without a deviation.
Record any implement-model deviation in the 5.1 Notes column.

## Global Constraints

- No em dashes anywhere: not in code comments, not in i18n strings, not in
  documentation. Use periods, commas or parentheses.
- Every user-visible string goes through `react-i18next`, with the key added
  to all four locale files (`frontend/src/locales/{en,de,es,it}.json`); the
  pre-push `check:locales` script enforces parity.
- All work happens in the worktree `../borg-ui-space-family` on branch
  `feat/space-family-phase-1`, never in the main checkout.
- Every task adds or updates a test. The full backend suite and the frontend
  `typecheck`, `lint`, `test` and `check:locales` run before G2.
- UI changes are verified visually in Storybook, light and dark, before push
  (repository rule). Storybook needs Node 20.19+ via `fnm use 24`.

---

### Task 1: Column and migration

**Files:**
- Modify: `app/database/models.py` (class `Archive`, after `deduplicated_size`)
- Create: `app/database/alembic/versions/a3b4c5d6e7f8_add_archive_stats_measured_at.py`
- Test: `tests/unit/test_archive_stats_measured_at_migration.py`

**Interfaces:**
- Produces: `Archive.stats_measured_at: Optional[datetime]` (naive UTC, like
  every other datetime on the row).

- [x] **Step 1: Write the failing migration test**

```python
"""Tests for revision a3b4c5d6e7f8 (archives.stats_measured_at, spec 4.1)."""

from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "a3b4c5d6e7f8"
PREVIOUS = "f2a3b4c5d6e7"


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _columns(url):
    engine = _engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("archives")}
    finally:
        engine.dispose()


@pytest.mark.unit
def test_upgrade_adds_and_downgrade_drops_the_column(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    assert "stats_measured_at" not in _columns(url)
    _migrate(url, REVISION)
    assert "stats_measured_at" in _columns(url)
    _migrate(url, PREVIOUS, down=True)
    assert "stats_measured_at" not in _columns(url)


@pytest.mark.unit
def test_measured_rows_are_backfilled_from_first_seen_at(tmp_path):
    """A row that already carries sizes was measured in the listing run
    that created it, so first_seen_at is the honest date. A row without
    sizes stays NULL and is picked up by the info loop as before."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    engine = _engine(url)
    seen = datetime(2026, 9, 1, 2, 0, 0)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO repositories (name, path) VALUES ('r', '/tmp/r')"
            )
        )
        for borg_id, size in (("sized", 10), ("bare", None)):
            conn.execute(
                text(
                    "INSERT INTO archives (repository_id, borg_id, name, series, "
                    "start, original_size, history_state, history_truncated, "
                    "history_attempts, first_seen_at, last_seen_at) "
                    "VALUES (1, :bid, :bid, 'default', :seen, :size, 'pending', 0, 0, "
                    ":seen, :seen)"
                ),
                {"bid": borg_id, "seen": seen, "size": size},
            )
    engine.dispose()
    _migrate(url, REVISION)
    engine = _engine(url)
    with engine.connect() as conn:
        rows = dict(
            conn.execute(
                text("SELECT borg_id, stats_measured_at FROM archives")
            ).all()
        )
    engine.dispose()
    assert rows["sized"] is not None and rows["sized"].startswith("2026-09-01")
    assert rows["bare"] is None
```

If the `repositories` insert fails on NOT NULL columns, build the insert
from `inspect(engine).get_columns("repositories")` exactly as
`tests/unit/test_repository_index_mode_migration.py::test_an_existing_repository_is_backfilled_to_full`
does, and copy that helper rather than naming columns.

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_archive_stats_measured_at_migration.py -v`
Expected: FAIL, alembic cannot find revision `a3b4c5d6e7f8`.

- [x] **Step 3: Add the column to the model**

In `app/database/models.py`, class `Archive`, directly after
`deduplicated_size`:

```python
    # When fill_archive_info last wrote the four Borg figures above. NULL is
    # "never measured" or "stale": a listing that observed removed archives
    # clears it on every survivor, because deduplicated_size is relative to
    # the archives that exist (spec 4.1). Values stay in place while stale.
    stats_measured_at = Column(DateTime, nullable=True)
```

- [x] **Step 4: Write the migration**

```python
"""add archives.stats_measured_at

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain ALTER like f2a3b4c5d6e7: a batch rebuild of `archives` on SQLite
    # would cascade-delete every archive_changes row.
    op.add_column("archives", sa.Column("stats_measured_at", sa.DateTime(), nullable=True))
    # A row with sizes was measured in the listing run that created it
    # (spec 4.1); first_seen_at is the honest date. Rows without sizes stay
    # NULL and the info loop picks them up as before.
    op.execute(
        "UPDATE archives SET stats_measured_at = first_seen_at "
        "WHERE original_size IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("archives", "stats_measured_at")
```

- [x] **Step 5: Run the test to verify it passes**

Run: `pytest tests/unit/test_archive_stats_measured_at_migration.py -v`
Expected: PASS (2 tests).

- [x] **Step 6: Run the other migration tests to check the chain**

Run: `pytest tests/unit -k migration -q`
Expected: PASS. If a test pins the old head `f2a3b4c5d6e7` as "the head",
update it to `a3b4c5d6e7f8`.

### Task 2: The info fill writes the date, the selector reads it

**Files:**
- Modify: `app/services/operations/executors/index.py:286-322` (`archives_needing_info`) and `:412-478` (`fill_archive_info`)
- Test: `tests/unit/test_operations_index_executors.py`

**Interfaces:**
- Consumes: `Archive.stats_measured_at` from Task 1.
- Produces: `archives_needing_info(db, repository, *, limit, include_missing_end=False)`
  now returns rows with `stats_measured_at IS NULL` (signature unchanged);
  `fill_archive_info` sets `stats_measured_at = utc_now()` on every row it
  fills.

- [x] **Step 1: Write the failing tests**

Add to `tests/unit/test_operations_index_executors.py`, next to
`test_archives_needing_info_backfills_across_runs`:

```python
@pytest.mark.unit
def test_archives_needing_info_picks_stale_rows_with_sizes(db, repo):
    """Spec 4.1: NULL stats_measured_at means never measured or stale, so a
    row that has sizes but no date comes back, and a dated row does not."""
    for borg_id, size, measured in (
        ("stale", 10, None),
        ("fresh", 10, datetime(2026, 9, 1, 3)),
        ("never", None, None),
    ):
        db.add(
            Archive(
                repository_id=repo.id,
                borg_id=borg_id,
                name=borg_id,
                series="default",
                start=datetime(2026, 9, 1),
                original_size=size,
                stats_measured_at=measured,
            )
        )
    db.commit()
    picked = {a.borg_id for a in index_exec.archives_needing_info(db, repo, limit=5)}
    assert picked == {"stale", "never"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_archive_info_stamps_stats_measured_at(db, repo, monkeypatch):
    row = Archive(
        repository_id=repo.id,
        borg_id="x",
        name="x",
        series="default",
        start=datetime(2026, 9, 1),
    )
    db.add(row)
    db.commit()
    payload = json.dumps(
        {
            "archives": [
                {
                    "end": "2026-09-01T00:10:00",
                    "duration": 600,
                    "stats": {
                        "nfiles": 1,
                        "original_size": 10,
                        "compressed_size": 8,
                        "deduplicated_size": 4,
                    },
                }
            ]
        }
    )
    monkeypatch.setattr(
        index_exec,
        "_server_archive_info",
        AsyncMock(return_value={"success": True, "stdout": payload}),
    )
    assert await index_exec.fill_archive_info(db, repo, [row], {}, limit=1) == 1
    db.refresh(row)
    assert row.deduplicated_size == 4
    assert row.stats_measured_at is not None
```

Then update the existing `test_archives_needing_info_backfills_across_runs`
and `test_archives_needing_info_revisits_withheld_end`: every row those
tests create with `original_size=10` and expect to be skipped must also set
`stats_measured_at=datetime(2026, 9, 1)`, since "has sizes" no longer means
"measured".

- [x] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_operations_index_executors.py -k "needing_info or stamps_stats" -v`
Expected: `picks_stale_rows_with_sizes` FAILS (stale row not picked),
`stamps_stats_measured_at` FAILS (`stats_measured_at` is None).

- [x] **Step 3: Change the selector**

In `archives_needing_info`, replace

```python
    rows = _select(Archive.original_size.is_(None), set(), limit)
```

with

```python
    # NULL is "never measured" and "stale" alike (spec 4.1): a listing that
    # saw archives removed cleared it on every survivor, and the same
    # bounded loop re-measures them, oldest first.
    rows = _select(Archive.stats_measured_at.is_(None), set(), limit)
```

and update the docstring's first line to "Archives whose `borg info` stats
are missing or stale, oldest first."

- [x] **Step 4: Stamp the date in the fill**

In `fill_archive_info`, directly after `archive.deduplicated_size = info["deduplicated_size"]`:

```python
        archive.stats_measured_at = utc_now()
```

`utc_now` is already imported from `app.database.models` at the top of the
module.

- [x] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_operations_index_executors.py -v`
Expected: PASS, including the two updated tests.

### Task 3: A listing that loses archives stales the survivors

**Files:**
- Modify: `app/services/operations/executors/index.py:606-612` (`run_archive_sync`, right after `apply_listing` returns)
- Test: `tests/unit/test_operations_index_executors.py`

**Interfaces:**
- Consumes: `apply_listing(...) -> (new_rows, removed_ids)` (existing).
- Produces: nothing new; behaviour only.

- [x] **Step 1: Write the failing test**

Add next to `test_run_archive_sync_updates_repository_columns`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_archive_sync_stales_survivors_when_archives_were_removed(
    db, repo, monkeypatch
):
    """Spec 4.1: deduplicated_size is relative to the archives that exist,
    so once a listing sees archives gone (prune, delete, wipe, inside or
    outside Borg UI) every surviving row's measurement is stale. A listing
    that removed nothing leaves the dates alone."""
    measured = datetime(2026, 9, 1, 3)
    survivor = Archive(
        repository_id=repo.id,
        borg_id="aa11",
        name="nas-2026-09-02T02:00:00",
        series="nas",
        start=datetime(2026, 9, 2, 2),
        original_size=10,
        stats_measured_at=measured,
    )
    gone = Archive(
        repository_id=repo.id,
        borg_id="gone",
        name="nas-2026-09-01T02:00:00",
        series="nas",
        start=datetime(2026, 9, 1, 2),
        original_size=10,
        stats_measured_at=measured,
    )
    db.add_all([survivor, gone])
    db.commit()
    monkeypatch.setattr(
        index_exec,
        "list_archives_for_repository",
        AsyncMock(return_value=(True, [BORG1_ENTRY], "UTC")),
    )
    monkeypatch.setattr(index_exec, "fill_archive_info", AsyncMock(return_value=0))
    monkeypatch.setattr(
        index_exec, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )

    await index_exec.run_archive_sync(_ctx(db, repo))
    db.refresh(survivor)
    assert survivor.stats_measured_at is None

    # Second listing, nothing removed: a freshly measured date survives.
    survivor.stats_measured_at = measured
    db.commit()
    await index_exec.run_archive_sync(_ctx(db, repo))
    db.refresh(survivor)
    assert survivor.stats_measured_at == measured
```

`BORG1_ENTRY` lists only `aa11`, so `gone` is the removed row on the first
run and nothing is removed on the second.

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_operations_index_executors.py -k stales_survivors -v`
Expected: FAIL on the first assertion (`stats_measured_at` still set).

- [x] **Step 3: Clear the dates when the listing removed archives**

In `run_archive_sync`, immediately after the `removed_last_seen_at = {...}`
dict is built and before the `if is_agent_executor(repository):` block:

```python
        if removed_ids:
            # deduplicated_size is relative to the archives that exist (spec
            # 4.1): the survivors' figures are now stale, whoever removed the
            # archives. Clearing the date hands them to archives_needing_info
            # below, under the same per-run cap as a first fill.
            db.query(Archive).filter(Archive.repository_id == repository.id).update(
                {Archive.stats_measured_at: None}, synchronize_session=False
            )
            db.commit()
```

`apply_listing` has already deleted the removed rows, so "every row of the
repository" is exactly the survivors.

- [x] **Step 4: Run the test to verify it passes**

Run: `pytest tests/unit/test_operations_index_executors.py -v`
Expected: PASS.

- [x] **Step 5: Run the wider index and follow-up suites**

Run: `pytest tests/unit/test_operations_index_executors.py tests/unit/test_operations_index_mode.py tests/unit/test_operations_followups.py -q`
Expected: PASS.

### Task 4: The detail route carries the date and the predecessor's figures

**Files:**
- Modify: `app/api/archive_index.py:64-89` (`serialize_archive`) and `:328-347` (`get_archive`)
- Test: `tests/unit/test_api_archive_index.py` (class `TestArchiveList` or wherever `test_detail_has_neighbours_and_history_state` lives)

**Interfaces:**
- Produces: every archive payload gains `stats_measured_at: str | null`.
  The detail payload gains
  `predecessor_stats: {id, nfiles, original_size, deduplicated_size, duration_seconds} | null`.

- [x] **Step 1: Write the failing test**

Add after `test_detail_has_neighbours_and_history_state`:

```python
    def test_detail_carries_measurement_date_and_predecessor_stats(
        self, test_client, test_db, admin_headers
    ):
        """Spec 4.2: the header draws its deltas from one request."""
        repo = _repo(test_db)
        a1 = _archive(test_db, repo, "a1", 1, size=100, dur=10.0, nfiles=10)
        a2 = _archive(test_db, repo, "a2", 2, size=150, dur=12.0, nfiles=11)
        a2.stats_measured_at = datetime(2026, 9, 2, 2, 30)
        test_db.commit()

        body = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a2.id}", headers=admin_headers
        ).json()
        assert body["stats_measured_at"].startswith("2026-09-02T02:30")
        assert body["predecessor_stats"] == {
            "id": a1.id,
            "nfiles": 10,
            "original_size": 100,
            "deduplicated_size": 100,
            "duration_seconds": 10.0,
        }

        first = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a1.id}", headers=admin_headers
        ).json()
        assert first["predecessor_stats"] is None
        assert first["stats_measured_at"] is None
```

- [x] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_api_archive_index.py -k predecessor_stats -v`
Expected: FAIL with `KeyError: 'stats_measured_at'`.

- [x] **Step 3: Serialize the date and the predecessor's figures**

In `serialize_archive`, after `"deduplicated_size": a.deduplicated_size,`:

```python
        "stats_measured_at": a.stats_measured_at,
```

In `get_archive`, replace the `return {...}` with:

```python
    return {
        **serialize_archive(archive),
        "predecessor_id": predecessor.id if predecessor else None,
        "successor_id": successor.id if successor else None,
        # The header's deltas (spec 4.2) come from here rather than a second
        # request for the predecessor.
        "predecessor_stats": (
            {
                "id": predecessor.id,
                "nfiles": predecessor.nfiles,
                "original_size": predecessor.original_size,
                "deduplicated_size": predecessor.deduplicated_size,
                "duration_seconds": predecessor.duration_seconds,
            }
            if predecessor
            else None
        ),
        "history_available": history,
        "history_capability": history_capability(db, repository, history=history),
    }
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_archive_index.py tests/unit/test_api_archive_index_modes.py -q`
Expected: PASS. If a test compares a serialized archive to an exact dict,
add `"stats_measured_at": None` to the expectation.

### Task 5: `ArchiveStatsHeader` component, story, test, strings

**Files:**
- Modify: `frontend/src/types/archives.ts` (`ArchiveRow`, `ArchiveDetailResponse`)
- Create: `frontend/src/components/archives/ArchiveStatsHeader.tsx`
- Create: `frontend/src/components/archives/ArchiveStatsHeader.stories.tsx`
- Create: `frontend/src/components/archives/__tests__/ArchiveStatsHeader.test.tsx`
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json` (under `archives.detail`)

**Interfaces:**
- Consumes: `ArchiveDetailResponse` with the two new fields from Task 4;
  `formatBytes`, `formatDurationSeconds`, `formatRelativeTime` from
  `utils/dateUtils`; `changeColor` from `components/archives/changeStyle`.
- Produces:

```ts
export interface ArchiveStatsHeaderProps {
  archive: ArchiveDetailResponse
  // The changes totals the page already fetches; undefined while loading,
  // on Community, or in a non-full index mode.
  totals?: { added: number; removed: number; modified: number }
  // Why the totals are absent, so the tile can say so instead of showing 0.
  totalsState: 'ready' | 'loading' | 'plan_locked' | 'not_indexed' | 'unavailable'
}
export default function ArchiveStatsHeader(props: ArchiveStatsHeaderProps)
```

- [x] **Step 1: Extend the types**

In `frontend/src/types/archives.ts`, add to `ArchiveRow` after
`deduplicated_size`:

```ts
  // When the four Borg figures above were last measured. null is never
  // measured (sizes null too) or stale (sizes set, being re-measured).
  stats_measured_at: string | null
```

and to `ArchiveDetailResponse`:

```ts
  predecessor_stats: {
    id: number
    nfiles: number | null
    original_size: number | null
    deduplicated_size: number | null
    duration_seconds: number | null
  } | null
```

Run `cd frontend && npx tsc --noEmit -p tsconfig.json` and fix every
fixture that builds an `ArchiveRow` literal (stories and tests) by adding
`stats_measured_at: null` and, for detail responses, `predecessor_stats: null`.

- [x] **Step 2: Add the strings**

In `frontend/src/locales/en.json` under `archives.detail`, add:

```json
      "stats": {
        "addedToRepository": "Added to the repository",
        "addedHint": "Data unique to this archive. Deleting it frees at least this much.",
        "filesChanged": "Files changed",
        "filesChangedLocked": "Pro: file changes per archive",
        "filesChangedNotIndexed": "Not indexed yet",
        "filesChangedUnavailable": "Not available for this repository",
        "dataBackedUp": "Data backed up",
        "files": "Files",
        "duration": "Duration",
        "compression": "Compression",
        "compressionNotReported": "Not reported by this Borg version",
        "measuredAt": "Measured {{when}}",
        "remeasuring": "Re-measuring after archives were removed",
        "notMeasured": "Not measured yet",
        "vsPrevious": "vs previous"
      }
```

Add the same keys with translations to `de.json`, `es.json` and `it.json`
(the parity check only needs the keys to exist; translate them properly).

- [x] **Step 3: Write the failing component test**

`frontend/src/components/archives/__tests__/ArchiveStatsHeader.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveStatsHeader from '../ArchiveStatsHeader'
import type { ArchiveDetailResponse } from '../../../types/archives'

const base: ArchiveDetailResponse = {
  id: 12,
  repository_id: 7,
  borg_id: 'abc',
  name: 'nas-2026-09-02',
  series: 'nas',
  start: '2026-09-02T02:00:00Z',
  end: '2026-09-02T02:14:00Z',
  duration_seconds: 840,
  nfiles: 12000,
  original_size: 90_000_000_000,
  compressed_size: 60_000_000_000,
  deduplicated_size: 41_200_000_000,
  stats_measured_at: '2026-09-02T02:20:00Z',
  hostname: 'nas',
  username: 'root',
  comment: null,
  backup_operation_id: 55,
  history_state: 'indexed',
  history_indexed_at: null,
  history_rows: 0,
  history_truncated: false,
  first_seen_at: null,
  last_seen_at: null,
  predecessor_id: 11,
  successor_id: null,
  predecessor_stats: {
    id: 11,
    nfiles: 11000,
    original_size: 80_000_000_000,
    deduplicated_size: 30_000_000_000,
    duration_seconds: 900,
  },
  history_available: true,
}

describe('ArchiveStatsHeader', () => {
  it('leads with what the archive added and shows deltas against the predecessor', () => {
    renderWithProviders(
      <ArchiveStatsHeader
        archive={base}
        totals={{ added: 5, removed: 2, modified: 9 }}
        totalsState="ready"
      />
    )
    expect(screen.getByText('Added to the repository')).toBeInTheDocument()
    expect(screen.getByText('38.37 GB')).toBeInTheDocument()
    expect(screen.getByText('+5')).toBeInTheDocument()
    expect(screen.getByText('−2')).toBeInTheDocument()
    expect(screen.getByText('~9')).toBeInTheDocument()
    // 12000 files vs 11000
    expect(screen.getByText('+1,000 vs previous')).toBeInTheDocument()
    // 90 GB vs 80 GB (formatBytes is binary, two decimals)
    expect(screen.getByText('+9.31 GB vs previous')).toBeInTheDocument()
    // 840 s vs 900 s
    expect(screen.getByText('−1 min vs previous')).toBeInTheDocument()
    expect(screen.getByText(/1\.5:1/)).toBeInTheDocument()
    expect(screen.getByText(/Measured/)).toBeInTheDocument()
  })

  it('says why the file changes are absent instead of showing zeros', () => {
    renderWithProviders(<ArchiveStatsHeader archive={base} totalsState="plan_locked" />)
    expect(screen.getByText('Pro: file changes per archive')).toBeInTheDocument()
    expect(screen.queryByText('+0')).not.toBeInTheDocument()
  })

  it('names the stale and never-measured states', () => {
    renderWithProviders(
      <ArchiveStatsHeader
        archive={{ ...base, stats_measured_at: null }}
        totalsState="ready"
        totals={{ added: 0, removed: 0, modified: 0 }}
      />
    )
    expect(screen.getByText('Re-measuring after archives were removed')).toBeInTheDocument()
    renderWithProviders(
      <ArchiveStatsHeader
        archive={{
          ...base,
          stats_measured_at: null,
          original_size: null,
          deduplicated_size: null,
          compressed_size: null,
          nfiles: null,
        }}
        totalsState="ready"
      />
    )
    expect(screen.getByText('Not measured yet')).toBeInTheDocument()
  })

  it('shows no delta when the predecessor lacks the figure, and no ratio on Borg 2', () => {
    renderWithProviders(
      <ArchiveStatsHeader
        archive={{ ...base, compressed_size: null, predecessor_stats: null }}
        totalsState="ready"
      />
    )
    expect(screen.queryByText(/vs previous/)).not.toBeInTheDocument()
    expect(screen.getByText('Not reported by this Borg version')).toBeInTheDocument()
  })
})
```

The literals follow `utils/dateUtils.ts`: `formatBytes` is binary with two
decimals (41.2e9 bytes is `38.37 GB`, a 10e9 delta is `9.31 GB`) and
`formatDurationSeconds(60)` is `1 min`. The minus sign in the delta and in `−2` is U+2212, the same glyph
the changes tab uses.

- [x] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/archives/__tests__/ArchiveStatsHeader.test.tsx`
Expected: FAIL, module not found.

- [x] **Step 5: Write the component**

`frontend/src/components/archives/ArchiveStatsHeader.tsx`:

```tsx
import type { ReactNode } from 'react'
import { Box, Tooltip, Typography, useTheme, alpha } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDurationSeconds, formatRelativeTime } from '../../utils/dateUtils'
import { changeColor } from './changeStyle'
import type { ArchiveDetailResponse } from '../../types/archives'

export interface ArchiveStatsHeaderProps {
  archive: ArchiveDetailResponse
  totals?: { added: number; removed: number; modified: number }
  totalsState: 'ready' | 'loading' | 'plan_locked' | 'not_indexed' | 'unavailable'
}

const MINUS = '−'

// A signed difference rendered with the same formatter as the value, or
// null when either side is missing (spec 4.2: a delta needs both figures).
function delta(
  current: number | null | undefined,
  previous: number | null | undefined,
  format: (n: number) => string
): string | null {
  if (current == null || previous == null) return null
  const diff = current - previous
  if (diff === 0) return '±0'
  return diff > 0 ? `+${format(diff)}` : `${MINUS}${format(-diff)}`
}

interface Tile {
  key: string
  label: string
  value: ReactNode
  sub?: ReactNode
  headline?: boolean
}

export default function ArchiveStatsHeader({ archive, totals, totalsState }: ArchiveStatsHeaderProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const prev = archive.predecessor_stats
  const measured = archive.original_size != null
  const stale = measured && archive.stats_measured_at == null

  const measuredLine = !measured
    ? t('archives.detail.stats.notMeasured')
    : stale
      ? t('archives.detail.stats.remeasuring')
      : t('archives.detail.stats.measuredAt', {
          when: formatRelativeTime(archive.stats_measured_at),
        })

  const withPrevious = (d: string | null) =>
    d ? `${d} ${t('archives.detail.stats.vsPrevious')}` : undefined

  const ratio =
    archive.compressed_size != null && archive.original_size
      ? `${(archive.original_size / archive.compressed_size).toFixed(1)}:1`
      : null

  const filesChanged: ReactNode =
    totalsState === 'ready' && totals ? (
      <Box
        component="span"
        sx={{
          display: 'inline-flex',
          gap: 1,
          fontVariantNumeric: 'tabular-nums',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        }}
      >
        <Box component="span" sx={{ color: changeColor(theme, 'added') }}>+{totals.added}</Box>
        <Box component="span" sx={{ color: changeColor(theme, 'removed') }}>{MINUS}{totals.removed}</Box>
        <Box component="span" sx={{ color: changeColor(theme, 'modified') }}>~{totals.modified}</Box>
      </Box>
    ) : (
      <Typography component="span" variant="body2" sx={{ color: 'text.secondary' }}>
        {totalsState === 'plan_locked'
          ? t('archives.detail.stats.filesChangedLocked')
          : totalsState === 'not_indexed'
            ? t('archives.detail.stats.filesChangedNotIndexed')
            : totalsState === 'unavailable'
              ? t('archives.detail.stats.filesChangedUnavailable')
              : '…'}
      </Typography>
    )

  const tiles: Tile[] = [
    {
      key: 'added',
      label: t('archives.detail.stats.addedToRepository'),
      value: measured ? formatBytes(archive.deduplicated_size) : MINUS,
      sub: measuredLine,
      headline: true,
    },
    { key: 'changed', label: t('archives.detail.stats.filesChanged'), value: filesChanged },
    {
      key: 'original',
      label: t('archives.detail.stats.dataBackedUp'),
      value: measured ? formatBytes(archive.original_size) : MINUS,
      sub: withPrevious(delta(archive.original_size, prev?.original_size, formatBytes)),
    },
    {
      key: 'files',
      label: t('archives.detail.stats.files'),
      value: archive.nfiles != null ? archive.nfiles.toLocaleString() : MINUS,
      sub: withPrevious(delta(archive.nfiles, prev?.nfiles, (n) => n.toLocaleString())),
    },
    {
      key: 'duration',
      label: t('archives.detail.stats.duration'),
      value: archive.duration_seconds != null ? formatDurationSeconds(archive.duration_seconds) : MINUS,
      sub: withPrevious(
        delta(archive.duration_seconds, prev?.duration_seconds, formatDurationSeconds)
      ),
    },
    {
      key: 'compression',
      label: t('archives.detail.stats.compression'),
      value: ratio ?? (
        <Typography component="span" variant="body2" sx={{ color: 'text.secondary' }}>
          {t('archives.detail.stats.compressionNotReported')}
        </Typography>
      ),
    },
  ]

  return (
    <Box
      component="dl"
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr 1fr', md: '1.6fr repeat(5, 1fr)' },
        gap: 1.5,
        m: 0,
        mt: 2,
      }}
    >
      {tiles.map((tile) => (
        <Tooltip
          key={tile.key}
          title={tile.headline ? t('archives.detail.stats.addedHint') : ''}
          disableHoverListener={!tile.headline}
        >
          <Box
            sx={{
              p: 1.5,
              borderRadius: 2,
              bgcolor: tile.headline
                ? alpha(theme.palette.info.main, theme.palette.mode === 'dark' ? 0.16 : 0.09)
                : alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.04 : 0.03),
              gridColumn: tile.headline ? { xs: '1 / -1', md: 'auto' } : 'auto',
            }}
          >
            <Typography component="dt" variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
              {tile.label}
            </Typography>
            <Typography
              component="dd"
              variant={tile.headline ? 'h5' : 'subtitle1'}
              sx={{ m: 0, fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1.3 }}
            >
              {tile.value}
            </Typography>
            {tile.sub && (
              <Typography variant="caption" sx={{ color: stale && tile.headline ? 'warning.main' : 'text.secondary' }}>
                {tile.sub}
              </Typography>
            )}
          </Box>
        </Tooltip>
      ))}
    </Box>
  )
}
```

The zero-delta branch renders `±0`; keep it, it says "same as before"
without a sign. `formatRelativeTime` accepts a nullable string and is called
only when `stats_measured_at` is set.

- [x] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/archives/__tests__/ArchiveStatsHeader.test.tsx`
Expected: PASS (4 tests). Adjust the literal expectations to the formatter
output if a formatter changed, never the formatter.

- [x] **Step 7: Write the story**

`frontend/src/components/archives/ArchiveStatsHeader.stories.tsx`:

```tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import ArchiveStatsHeader from './ArchiveStatsHeader'
import type { ArchiveDetailResponse } from '../../types/archives'

const archive: ArchiveDetailResponse = {
  id: 12,
  repository_id: 7,
  borg_id: 'abc123',
  name: 'nas-2026-09-02T02:00',
  series: 'nightly',
  start: '2026-09-02T02:00:00Z',
  end: '2026-09-02T02:14:00Z',
  duration_seconds: 840,
  nfiles: 12000,
  original_size: 90_000_000_000,
  compressed_size: 60_000_000_000,
  deduplicated_size: 41_200_000_000,
  stats_measured_at: '2026-09-02T02:20:00Z',
  hostname: 'nas',
  username: 'root',
  comment: null,
  backup_operation_id: 55,
  history_state: 'indexed',
  history_indexed_at: '2026-09-02T02:20:00Z',
  history_rows: 40,
  history_truncated: false,
  first_seen_at: '2026-09-02T02:00:00Z',
  last_seen_at: '2026-09-02T02:00:00Z',
  predecessor_id: 11,
  successor_id: null,
  predecessor_stats: {
    id: 11,
    nfiles: 11000,
    original_size: 80_000_000_000,
    deduplicated_size: 30_000_000_000,
    duration_seconds: 900,
  },
  history_available: true,
}

const meta = {
  title: 'Components/Archives/ArchiveStatsHeader',
  component: ArchiveStatsHeader,
} satisfies Meta<typeof ArchiveStatsHeader>

export default meta
type Story = StoryObj<typeof meta>

export const Pro: Story = {
  args: { archive, totals: { added: 5, removed: 2, modified: 9 }, totalsState: 'ready' },
}
export const Community: Story = { args: { archive, totalsState: 'plan_locked' } }
export const Stale: Story = {
  args: { archive: { ...archive, stats_measured_at: null }, totalsState: 'ready', totals: { added: 0, removed: 0, modified: 0 } },
}
export const NeverMeasured: Story = {
  args: {
    archive: { ...archive, stats_measured_at: null, original_size: null, compressed_size: null, deduplicated_size: null, nfiles: null, duration_seconds: null },
    totalsState: 'not_indexed',
  },
}
export const Borg2FirstOfSeries: Story = {
  args: { archive: { ...archive, compressed_size: null, predecessor_stats: null, predecessor_id: null }, totalsState: 'ready', totals: { added: 12000, removed: 0, modified: 0 } },
}
```

- [x] **Step 8: Lint, types, locales**

Run: `cd frontend && npm run typecheck && npm run lint && npm run check:locales`
Expected: all pass.

### Task 6: Wire the header into the detail page

**Files:**
- Modify: `frontend/src/pages/ArchiveDetail.tsx:242-300` (totals derivation) and `:380-440` (the chip row)
- Test: `frontend/src/pages/__tests__/ArchiveDetail.test.tsx`

**Interfaces:**
- Consumes: `ArchiveStatsHeader` from Task 5; the page's existing
  `changesForLabel` query, `indexMode`, `usePlan`, and `archive.history_capability`.

- [x] **Step 1: Write the failing page test**

Add to `frontend/src/pages/__tests__/ArchiveDetail.test.tsx`, using the
file's existing `archive` fixture and `renderRoute` helper (extend the
fixture with `stats_measured_at: '2026-09-02T02:20:00Z'` and
`predecessor_stats: { id: 11, nfiles: 11000, original_size: 80_000_000_000, deduplicated_size: 30_000_000_000, duration_seconds: 900 }`
if it lacks them after Task 5's type fix):

```tsx
  it('shows the stats header with deltas and the changes totals', async () => {
    vi.mocked(archivesAPI.getArchive).mockResolvedValue({ data: archive } as never)
    vi.mocked(archivesAPI.getChanges).mockResolvedValue({
      data: {
        archive_id: 12,
        compare_to_id: 11,
        changes: [],
        totals: { added: 5, removed: 2, modified: 9, summary: 0 },
        next_cursor: null,
        incomplete: false,
        unindexed_archive_ids: [],
        history_state: 'indexed',
        history_truncated: false,
      },
    } as never)
    renderRoute('/archives/7/12?tab=files')
    expect(await screen.findByText('Added to the repository')).toBeInTheDocument()
    expect(await screen.findByText('+5')).toBeInTheDocument()
    expect(screen.getByText(/^\+1,000 vs previous$/)).toBeInTheDocument()
    expect(screen.queryByText('Deduplicated size')).not.toBeInTheDocument()
  })
```

If the file's `usePlan` mock (or `repositoriesAPI.getRepositories`) reports
Community by default, set it to Pro for this test the way the file's other
Pro tests do; on Community the tile shows the locked line instead of `+5`.

- [x] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/__tests__/ArchiveDetail.test.tsx`
Expected: the new test FAILS (header text absent).

- [x] **Step 3: Derive the totals state and swap the chip row**

In `ArchiveDetail.tsx`, next to the existing `const totals = ...` line:

```tsx
  const capability = archive?.history_capability ?? 'available'
  const totalsState: ArchiveStatsHeaderProps['totalsState'] =
    capability === 'plan_locked'
      ? 'plan_locked'
      : capability !== 'available' || indexMode !== 'full'
        ? 'unavailable'
        : archive?.history_state !== 'indexed'
          ? 'not_indexed'
          : totals
            ? 'ready'
            : 'loading'
```

Import `ArchiveStatsHeader, { type ArchiveStatsHeaderProps }` from
`../components/archives/ArchiveStatsHeader`.

Then replace the `<Stack direction="row" spacing={1} useFlexGap ...>` chip
block (the array of `series`, `files`, `originalSize`, `deduplicatedSize`,
`duration` pills and its `.map`) with the series chip alone followed by the
header, keeping the header inside the same `<Box sx={{ minWidth: 0 }}>`:

```tsx
            <Chip
              size="small"
              label={`${t('archives.detail.series')}: ${archive.series}`}
              sx={{ mt: 1.5 }}
            />
```

and, as the last child of the outer bordered `Box` (after the action
buttons `Stack`, so it spans the full card width), render:

```tsx
        <Box sx={{ flexBasis: '100%' }}>
          <ArchiveStatsHeader archive={archive} totals={totals} totalsState={totalsState} />
        </Box>
```

The outer card is `display: flex` with `flexDirection` `row` on `md`; add
`flexWrap: 'wrap'` to its `sx` so the full-width child wraps under the
title and the buttons.

Remove the now-unused imports (`alpha` stays if the icon tile uses it;
`formatBytes` and `formatDurationSeconds` go if nothing else on the page
uses them; run the linter to be sure).

- [x] **Step 4: Run the page tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/__tests__/ArchiveDetail.test.tsx`
Expected: PASS, including the older tests (they never asserted on the
chips).

- [x] **Step 5: Visual check in Storybook, light and dark**

Run (worktree, Node via fnm):

```bash
cd frontend && fnm use 24 && npm run storybook -- --ci --port 6007
```

Open `Components/Archives/ArchiveStatsHeader` in both themes and take one
screenshot each of `Pro`, `Stale` and `Borg2FirstOfSeries` (the repository
rule: verify UI visually before push). Check that the headline tile spans
the row on a 400px-wide viewport and that the six tiles sit in one row at
`md`. Fix spacing in the component, not in the page.

### Task 7: Verification before G2

- [x] **Step 1: Backend suite**

Run: `pytest tests/unit -q -x`
Expected: PASS. If `tests/unit/test_api_auth.py` fails on
`PUBLIC_BASE_URL`, that is the main checkout's `.env` leaking (known); rerun
with `env -u PUBLIC_BASE_URL`.

- [x] **Step 2: Frontend suite**

Run: `cd frontend && npm run typecheck && npm run lint && npm run test -- --run && npm run check:locales && npm run format:check`
Expected: all pass.

- [x] **Step 3: Update the spec's progress table**

Set phase 1 to `in review` in section 5.1 of the spec with the verification
output summarised in Notes, then stop at gate G2 and ask whether to commit.
Commit message convention: `feat(archives): stats measurement date and archive stats header (space family phase 1)`.

## Open questions

- `formatRelativeTime` output ("2 hours ago") is what "Measured {{when}}"
  interpolates. If the reader wants the absolute time on hover, add a
  `Tooltip` with `formatDateTimeFull` in Task 5; not planned unless asked.
- The migration backfills `first_seen_at` for rows with sizes. A row that
  was re-listed many times before its info fill (a large import over
  several runs) gets a date a few runs early. Accepted in spec 4.1.
- Whether `ArchiveInfoTab` should also drop its duplicate size rows now that
  the header carries them. Out of scope for this phase; raise at G3 if the
  duplication reads badly.
