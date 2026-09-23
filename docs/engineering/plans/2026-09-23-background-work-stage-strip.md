# Background work stage strip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Background work board's three stage columns with a strip of per-stage blocks (live counts, click to filter, per-stage pause), and a single Current stage cell per row.

**Architecture:** The backend gets one stage map in `vocab.py` and a `paused_stages` setting that replaces `background_paused`; admission (`can_start`) checks the operation's stage. The frontend stage model gains `retention` and a `currentStage` helper that both the new `StageStrip` and the row's `CurrentStage` cell read.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic (SQLite), pytest; React, MUI, TanStack Query, i18next, Vitest, Storybook.

**Spec:** `docs/engineering/specs/2026-09-23-background-work-stage-strip.md`

## Global Constraints

- No em dashes in UI copy, i18n strings, code comments or docs.
- Every new i18n key lands in `en`, `de`, `es`, `it` in the same commit.
- No heavy left accent borders; the selected block uses a full outline.
- Stage, pause and worker controls are admin-only; operators read them.
- `history_merge` stays mapped to the `archives` stage (backend and frontend) so this change does not depend on PR #1168; after #1168 it is only legacy rows.
- Alembic: the new revision's `down_revision` is the current head, recomputed against fetched `origin/main` right before writing it (today `b2c3d4e5f6a7`).
- Run backend tests with `../borg-ui/.venv/bin/pytest`; frontend with `cd frontend && npx vitest run <path>`.

---

### Task 1: Stage map, `paused_stages`, admission

**Files:**
- Modify: `app/services/operations/vocab.py`
- Modify: `app/database/models.py:1537`
- Create: `app/database/alembic/versions/c3d4e5f6a7b8_paused_stages.py`
- Modify: `app/services/operations/lanes.py:23-30,165-170`
- Test: `tests/unit/test_operations_lanes.py`, `tests/unit/test_paused_stages_migration.py`

**Interfaces:**
- Produces: `vocab.STAGES: dict[str, tuple[str, ...]]`, `vocab.STAGE_FOR_KIND: dict[str, str]`, `SystemSettings.paused_stages` (JSON list of stage keys).

- [ ] **Step 1: Failing tests.** Replace `test_pause_only_affects_followup_and_reconcile` in `test_operations_lanes.py` with:

```python
@pytest.mark.unit
def test_a_paused_stage_holds_its_followup_and_reconcile_work(db, repo, settings):
    settings.paused_stages = ["stats"]
    db.commit()
    followup = enqueue(db, "stats", repository_id=repo.id, trigger="followup")
    reconcile = enqueue(db, "stats", repository_id=repo.id, trigger="reconcile")
    manual = enqueue(db, "stats", repository_id=repo.id, trigger="manual")
    assert lanes.can_start(db, followup, settings) is False
    assert lanes.can_start(db, reconcile, settings) is False
    assert lanes.can_start(db, manual, settings) is True


@pytest.mark.unit
def test_pausing_one_stage_leaves_the_others_running(db, repo, settings):
    settings.paused_stages = ["history"]
    db.commit()
    stats = enqueue(db, "stats", repository_id=repo.id, trigger="followup")
    assert lanes.can_start(db, stats, settings) is True


@pytest.mark.unit
def test_history_merge_pauses_with_the_archive_list(db, repo, settings):
    settings.paused_stages = ["archives"]
    db.commit()
    merge = enqueue(db, "history_merge", repository_id=repo.id, trigger="followup")
    assert lanes.can_start(db, merge, settings) is False


@pytest.mark.unit
def test_every_followup_kind_has_a_stage():
    from app.services.operations.followups import FOLLOWUPS
    from app.services.operations.vocab import STAGE_FOR_KIND

    queued_by_chains = {k for chain in FOLLOWUPS.values() for k in chain}
    assert queued_by_chains <= set(STAGE_FOR_KIND)
```

The last test is the guarantee that "all stages paused" blocks exactly what `background_paused` did.

Create `tests/unit/test_paused_stages_migration.py`:

```python
"""Tests for revision c3d4e5f6a7b8 (system_settings.paused_stages)."""

import json

import pytest
from alembic import command
from sqlalchemy import inspect, text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "c3d4e5f6a7b8"
PREVIOUS = "b2c3d4e5f6a7"
ALL = ["archives", "retention", "history", "stats"]


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _run(url, sql):
    engine = _engine(url)
    try:
        with engine.begin() as c:
            return c.execute(text(sql)).fetchall()
    finally:
        engine.dispose()


def _columns(url):
    engine = _engine(url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("system_settings")}
    finally:
        engine.dispose()


@pytest.mark.unit
@pytest.mark.parametrize("paused,expected", [(1, ALL), (0, [])])
def test_upgrade_carries_the_global_pause_over(tmp_path, paused, expected):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, PREVIOUS)
    _run(url, "DELETE FROM system_settings")
    _run(url, f"INSERT INTO system_settings (id, background_paused) VALUES (1, {paused})")
    _migrate(url, REVISION)
    assert "background_paused" not in _columns(url)
    assert json.loads(_run(url, "SELECT paused_stages FROM system_settings")[0][0]) == expected


@pytest.mark.unit
@pytest.mark.parametrize("stages,expected", [(ALL, 1), (["history"], 0), ([], 0)])
def test_downgrade_is_paused_only_when_every_stage_was(tmp_path, stages, expected):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, REVISION)
    _run(url, "DELETE FROM system_settings")
    _run(url, f"INSERT INTO system_settings (id, paused_stages) VALUES (1, '{json.dumps(stages)}')")
    _migrate(url, PREVIOUS, down=True)
    assert "paused_stages" not in _columns(url)
    assert _run(url, "SELECT background_paused FROM system_settings")[0][0] == expected
```

If the `INSERT` fails on another NOT NULL column without a server default, add that column to the insert with its model default.

- [ ] **Step 2: Run, expect failures.** `../borg-ui/.venv/bin/pytest tests/unit/test_operations_lanes.py tests/unit/test_paused_stages_migration.py -q`: fails on `paused_stages` / missing revision.

- [ ] **Step 3: Implement.**

`vocab.py`, after `INDEX_KINDS`:

```python
# The board's pausable stages (spec 2026-09-23 section 1), in run order.
# Every kind a follow-up or reconcile can queue belongs to one, so pausing
# them all holds exactly the work the old global pause held.
# history_merge left every chain with #1168; its legacy rows still pause
# with the listing that replaced it.
STAGES: dict[str, tuple[str, ...]] = {
    "archives": ("archive_sync", "history_merge"),
    "retention": ("prune_compare",),
    "history": ("history_index",),
    "stats": ("stats",),
}
STAGE_FOR_KIND: dict[str, str] = {
    kind: stage for stage, kinds in STAGES.items() for kind in kinds
}
```

`models.py:1537`: replace `background_paused = Column(Boolean, ...)` with

```python
    # Stage keys from vocab.STAGES whose follow-up and reconcile work waits.
    paused_stages = Column(JSON, default=list, nullable=False)
```

Migration `c3d4e5f6a7b8_paused_stages.py`:

```python
"""pause background work per stage

The global background_paused flag becomes the list of paused stages; a
paused install comes out with every stage paused.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-23
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

# Frozen copy of vocab.STAGES keys: a migration must not follow later edits.
ALL_STAGES = ["archives", "retention", "history", "stats"]


def upgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column("paused_stages", sa.JSON(), nullable=False, server_default="[]")
        )
    op.execute(
        sa.text(
            "UPDATE system_settings SET paused_stages = :all WHERE background_paused"
        ).bindparams(all=json.dumps(ALL_STAGES))
    )
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("background_paused")


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "background_paused", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    bind = op.get_bind()
    for row_id, stages in bind.execute(
        sa.text("SELECT id, paused_stages FROM system_settings")
    ):
        paused = set(json.loads(stages or "[]")) >= set(ALL_STAGES)
        bind.execute(
            sa.text("UPDATE system_settings SET background_paused = :p WHERE id = :id"),
            {"p": paused, "id": row_id},
        )
    with op.batch_alter_table("system_settings") as batch_op:
        batch_op.drop_column("paused_stages")
```

`lanes.py`: in `_DEFAULTS` replace `"background_paused": False` with `"paused_stages": []`; import `STAGE_FOR_KIND` from vocab; replace the pause check at the top of `can_start`:

```python
    if STAGE_FOR_KIND.get(op.kind) in (_setting(settings, "paused_stages") or []) and (
        op.trigger in ("followup", "reconcile")
    ):
        return False
```

- [ ] **Step 4: Run, expect pass.** Same command, then `grep -rn background_paused app tests` to catch leftovers (the old migration `b1e2f3a4c5d6` keeps its own references; leave those).
- [ ] **Step 5: Commit.** `feat(operations): pause background work per stage`

### Task 2: Stage pause API and queue response

**Files:**
- Modify: `app/api/operations.py` (`QueueResponse`, queue handler ~550, pause/resume ~700)
- Test: `tests/unit/test_api_operations.py` (`TestPauseAndLimits`, queue body test ~266)

**Interfaces:**
- Consumes: `vocab.STAGES`, `SystemSettings.paused_stages`.
- Produces: `POST /api/operations/stages/{stage}/pause|resume` returning `{"paused_stages": [...]}`; `/pause` and `/resume` still return `{"paused": bool}`; `QueueResponse.paused_stages: list[str]`, `QueueResponse.paused: bool` (every stage paused).

- [ ] **Step 1: Failing tests.** In `TestPauseAndLimits` replace `test_pause_resume` and add:

```python
    def test_pause_resume_all(self, test_client, test_db, admin_headers):
        assert test_client.post("/api/operations/pause", headers=admin_headers).json() == {"paused": True}
        assert test_db.query(SystemSettings).first().paused_stages == list(STAGES)
        assert test_client.post("/api/operations/resume", headers=admin_headers).json() == {"paused": False}
        assert test_db.query(SystemSettings).first().paused_stages == []

    def test_pause_one_stage(self, test_client, test_db, admin_headers):
        r = test_client.post("/api/operations/stages/history/pause", headers=admin_headers)
        assert r.json() == {"paused_stages": ["history"]}
        queue = test_client.get("/api/operations/queue", headers=admin_headers).json()
        assert queue["paused_stages"] == ["history"]
        assert queue["paused"] is False
        r = test_client.post("/api/operations/stages/history/resume", headers=admin_headers)
        assert r.json() == {"paused_stages": []}

    def test_pausing_every_stage_reads_as_paused(self, test_client, admin_headers):
        for stage in STAGES:
            test_client.post(f"/api/operations/stages/{stage}/pause", headers=admin_headers)
        assert test_client.get("/api/operations/queue", headers=admin_headers).json()["paused"] is True

    def test_unknown_stage_is_404(self, test_client, admin_headers):
        for stage in ("connect", "nope"):
            r = test_client.post(f"/api/operations/stages/{stage}/pause", headers=admin_headers)
            assert r.status_code == 404

    def test_stage_pause_requires_admin(self, test_client, auth_headers):
        r = test_client.post("/api/operations/stages/stats/pause", headers=auth_headers)
        assert r.status_code == 403
```

Import `from app.services.operations.vocab import STAGES` at the top. In the queue body test near line 266, add `assert body["paused_stages"] == []`.

- [ ] **Step 2: Run, expect failures.** `../borg-ui/.venv/bin/pytest tests/unit/test_api_operations.py -q`
- [ ] **Step 3: Implement.**

```python
class QueueResponse(BaseModel):
    repositories: list[QueueRepository]
    limits: QueueLimits
    # Every stage paused: what the tab's banner and "Resume all" read.
    paused: bool
    paused_stages: list[str]


def _paused_stages(settings) -> list[str]:
    # Stored order is click order; answer in run order.
    stored = set(settings.paused_stages or [])
    return [stage for stage in STAGES if stage in stored]
```

Queue handler return:

```python
    paused_stages = _paused_stages(settings)
    return QueueResponse(
        repositories=repositories,
        limits=_limits(db, settings),
        paused=len(paused_stages) == len(STAGES),
        paused_stages=paused_stages,
    )
```

Routes (replace the bodies of `/pause`, `/resume`; add two):

```python
@router.post("/pause")
async def pause_background(current_user=Depends(get_current_admin_user), db=Depends(get_db)):
    settings = _settings_row(db)
    settings.paused_stages = list(STAGES)
    db.commit()
    return {"paused": True}


@router.post("/resume")
async def resume_background(current_user=Depends(get_current_admin_user), db=Depends(get_db)):
    settings = _settings_row(db)
    settings.paused_stages = []
    db.commit()
    operation_runner.wake()
    return {"paused": False}


def _set_stage_paused(db, stage: str, paused: bool) -> dict:
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail={"key": "backend.errors.operations.unknownStage"})
    settings = _settings_row(db)
    stored = set(settings.paused_stages or [])
    stored = stored | {stage} if paused else stored - {stage}
    # A new list, so SQLAlchemy sees the JSON column change.
    settings.paused_stages = [s for s in STAGES if s in stored]
    db.commit()
    if not paused:
        operation_runner.wake()
    return {"paused_stages": settings.paused_stages}


@router.post("/stages/{stage}/pause")
async def pause_stage(stage: str, current_user=Depends(get_current_admin_user), db=Depends(get_db)):
    return _set_stage_paused(db, stage, True)


@router.post("/stages/{stage}/resume")
async def resume_stage(stage: str, current_user=Depends(get_current_admin_user), db=Depends(get_db)):
    return _set_stage_paused(db, stage, False)
```

Keep the file's existing annotation style (`current_user: User = Depends(...)`, `db: Session = Depends(...)`). Declare the `/stages/...` routes before `@router.get("/{operation_id}")`. Add `backend.errors.operations.unknownStage` to the four locale files ("Unknown background stage.").

- [ ] **Step 4: Run, expect pass**, plus `../borg-ui/.venv/bin/pytest tests/unit -q -k "operations or lanes or reconcile"`.
- [ ] **Step 5: Commit.** `feat(operations): stage pause routes and paused_stages on the queue`

### Task 3: Frontend stage model

**Files:**
- Modify: `frontend/src/types/operations.ts` (`QueueResponse`), `frontend/src/services/api.ts:799-800`
- Modify: `frontend/src/components/background-work/repositoryTrack.ts`
- Modify: `frontend/src/components/background-work/storyFixtures.ts` (queues gain `paused_stages: []`)
- Test: `frontend/src/components/background-work/__tests__/repositoryTrack.test.ts`

**Interfaces:**
- Produces:
  - `type PausableStage = 'archives' | 'retention' | 'history' | 'stats'` and `PAUSABLE_STAGES: PausableStage[]` in `types/operations.ts`; `QueueResponse.paused_stages: PausableStage[]`.
  - `operationsAPI.pauseStage(stage)`, `operationsAPI.resumeStage(stage)`.
  - `StageKey = 'connect' | PausableStage`, `STAGE_ORDER` in run order.
  - `WaitReason` adds `'upstream_paused'`.
  - `deriveTrack(repository, limits, pausedStages: PausableStage[])` (third argument was `paused: boolean`).
  - `currentStage(track: RepositoryTrack | null): StageState | null`.

- [ ] **Step 1: Failing tests** in `repositoryTrack.test.ts` (reuse the file's existing `op`/repository helpers; call sites that passed `false`/`true` become `[]`/`PAUSABLE_STAGES`):

```ts
it('places prune_compare in the retention stage, not the foreground', () => {
  const track = deriveTrack(repo([op({ id: 1, kind: 'prune_compare', category: 'maintenance', status: 'running' })]), limits, [])
  expect(track.foreground).toBeNull()
  expect(track.stages.find((s) => s.key === 'retention')?.status).toBe('running')
})

it('counts a legacy history_merge as part of the archive list', () => {
  const track = deriveTrack(repo([op({ id: 1, kind: 'history_merge', status: 'failed' })]), limits, [])
  expect(track.stages.find((s) => s.key === 'archives')?.status).toBe('failed')
  expect(track.stages.find((s) => s.key === 'history')?.status).toBe('idle')
})

it('says paused only for a stage that is paused', () => {
  const track = deriveTrack(repo([op({ id: 1, kind: 'stats', status: 'queued' })]), limits, ['history'])
  expect(track.stages.find((s) => s.key === 'stats')?.reason).toBe('queued')
})

it('says a stage waits on a paused one it depends on', () => {
  const track = deriveTrack(
    repo([
      op({ id: 1, kind: 'archive_sync', status: 'queued' }),
      op({ id: 2, kind: 'stats', status: 'queued', depends_on_id: 1 }),
    ]),
    limits,
    ['archives']
  )
  expect(track.stages.find((s) => s.key === 'archives')?.reason).toBe('paused')
  expect(track.stages.find((s) => s.key === 'stats')?.reason).toBe('upstream_paused')
})

describe('currentStage', () => {
  it('prefers running, then the first waiting, then failed', () => {
    const running = deriveTrack(repo([
      op({ id: 1, kind: 'archive_sync', status: 'completed' }),
      op({ id: 2, kind: 'history_index', status: 'running' }),
      op({ id: 3, kind: 'stats', status: 'queued', depends_on_id: 2 }),
    ]), limits, [])
    expect(currentStage(running)?.key).toBe('history')
    const waiting = deriveTrack(repo([
      op({ id: 1, kind: 'archive_sync', status: 'failed' }),
      op({ id: 2, kind: 'stats', status: 'queued' }),
    ]), limits, [])
    expect(currentStage(waiting)?.key).toBe('stats')
    const failed = deriveTrack(repo([op({ id: 1, kind: 'archive_sync', status: 'failed' })]), limits, [])
    expect(currentStage(failed)?.key).toBe('archives')
  })

  it('is null at rest', () => {
    expect(currentStage(null)).toBeNull()
    const done = deriveTrack(repo([op({ id: 1, kind: 'stats', status: 'completed' })]), limits, [])
    expect(currentStage(done)).toBeNull()
  })
})
```

Delete the old test `treats history_merge as the history stage and failed as retryable` (its premise is gone).

- [ ] **Step 2: Run, expect failures.** `cd frontend && npx vitest run src/components/background-work/__tests__/repositoryTrack.test.ts`
- [ ] **Step 3: Implement** in `repositoryTrack.ts`:

```ts
export type StageKey = 'connect' | PausableStage
export const STAGE_ORDER: StageKey[] = ['connect', 'archives', 'retention', 'history', 'stats']

// Mirrors vocab.STAGES, plus the import's connect step, which never queues.
const STAGE_FOR_KIND: Partial<Record<OperationKind, StageKey>> = {
  import_connect: 'connect',
  archive_sync: 'archives',
  // Left every chain with #1168; legacy rows still belong to the listing.
  history_merge: 'archives',
  prune_compare: 'retention',
  history_index: 'history',
  stats: 'stats',
}

export type WaitReason = 'paused' | 'upstream_paused' | 'lane_busy' | 'index_busy' | 'workers' | 'queued'
```

- `FOREGROUND_CATEGORIES` check: add `&& !STAGE_FOR_KIND[operation.kind]`.
- Signature: `deriveTrack(repository, limits, pausedStages: PausableStage[])`. In the waiting branch, after the `predecessors` walk:

```ts
      const isPaused = (k: StageKey | undefined) =>
        k != null && k !== 'connect' && pausedStages.includes(k)
      const upstreamPaused = [...predecessors].some((id) => {
        const dep = operationsById.get(id)
        return dep?.status === 'queued' && isPaused(STAGE_FOR_KIND[dep.kind])
      })
      if (isPaused(key)) reason = 'paused'
      else if (upstreamPaused) reason = 'upstream_paused'
      else if (holderRunning) { ... unchanged ... }
```

- Remove `HUB_STAGE_COLUMN_WIDTH`; `HUB_GRID_COLUMNS.md` becomes
  `'minmax(160px, 1.3fr) minmax(170px, 1.3fr) minmax(150px, 1fr) minmax(170px, 1.2fr) minmax(120px, 0.9fr) 40px'`
  (name, current stage, archives, history, stats, menu). Update the comment above it.
- Add:

```ts
// The one stage a repository is "in" for the strip and the row: the
// running one, else the first waiting one in run order, else a failed one
// from the run, else none (at rest).
export function currentStage(track: RepositoryTrack | null): StageState | null {
  if (!track) return null
  return (
    track.stages.find((s) => s.status === 'running') ??
    track.stages.find((s) => s.status === 'waiting') ??
    track.stages.find((s) => s.status === 'failed') ??
    null
  )
}
```

`types/operations.ts`:

```ts
export type PausableStage = 'archives' | 'retention' | 'history' | 'stats'
// Run order; mirrors app/services/operations/vocab.py STAGES.
export const PAUSABLE_STAGES: PausableStage[] = ['archives', 'retention', 'history', 'stats']
```

and `paused_stages: PausableStage[]` on `QueueResponse` (keep `paused`). `api.ts`:

```ts
  pauseStage: (stage: PausableStage) => api.post(`/operations/stages/${stage}/pause`),
  resumeStage: (stage: PausableStage) => api.post(`/operations/stages/${stage}/resume`),
```

Update callers of `deriveTrack` (`PipelineBoard.tsx:242`, `RepositoryHubRow.stories.tsx`) to pass `queue.paused_stages`, and every `QueueResponse` literal in `storyFixtures.ts` and tests to include `paused_stages: []`. Add `operations.background.stage.retention: "Retention preview"` and `operations.background.reason.upstream_paused: "Waiting on a paused stage"` in all four locales.

- [ ] **Step 4: Run, expect pass**, plus `npx tsc --noEmit -p .` in `frontend`.
- [ ] **Step 5: Commit.** `feat(background-work): retention stage, per-stage pause reasons, currentStage`

### Task 4: Stage filter and counts

**Files:**
- Modify: `frontend/src/components/background-work/hubRows.ts`
- Test: `frontend/src/components/background-work/__tests__/hubRows.test.ts`

**Interfaces:**
- Consumes: `currentStage`, `StageKey`.
- Produces: `HubToolbarState.stage: StageKey | null` (default `null`); `StageCounts = Record<StageKey, { total: number; running: number; waiting: number; failed: number }>`; `stageCounts(rows: HubRow[]): StageCounts`.

- [ ] **Step 1: Failing tests** (build rows with the file's existing helpers):

```ts
it('filters rows to the stage they are in', () => {
  const rows = [rowIn('archives', 'running'), rowIn('stats', 'waiting'), atRestRow()]
  expect(applyToolbar(rows, { ...DEFAULT_TOOLBAR, stage: 'stats' })).toHaveLength(1)
})

it('counts each repository once, in its current stage, without the system lane', () => {
  const counts = stageCounts([rowIn('archives', 'running'), rowIn('archives', 'waiting'), rowIn('history', 'failed'), systemRow('stats')])
  expect(counts.archives).toEqual({ total: 2, running: 1, waiting: 1, failed: 0 })
  expect(counts.history).toEqual({ total: 1, running: 0, waiting: 0, failed: 1 })
  expect(counts.stats.total).toBe(0)
})
```

`rowIn(stage, status)` builds a `HubRow` whose track has that one stage in that status (add it next to the existing row helpers in the test file).

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** `DEFAULT_TOOLBAR` gains `stage: null`. In `applyToolbar`'s repository filter add `&& (state.stage === null || currentStage(row.track)?.key === state.stage)`; the system lane is shown only when `state.stage === null`. Add:

```ts
export function stageCounts(rows: HubRow[]): StageCounts {
  const counts = Object.fromEntries(
    STAGE_ORDER.map((key) => [key, { total: 0, running: 0, waiting: 0, failed: 0 }])
  ) as StageCounts
  for (const row of rows) {
    if (!row.repository) continue
    const stage = currentStage(row.track)
    if (!stage) continue
    const bucket = counts[stage.key]
    bucket.total += 1
    if (stage.status === 'running') bucket.running += 1
    else if (stage.status === 'waiting') bucket.waiting += 1
    else if (stage.status === 'failed') bucket.failed += 1
  }
  return counts
}
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit.** `feat(background-work): filter and count repositories by current stage`

### Task 5: `StageStrip` component

**Files:**
- Create: `frontend/src/components/background-work/StageStrip.tsx`, `StageStrip.stories.tsx`
- Test: `frontend/src/components/background-work/__tests__/StageStrip.test.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

**Interfaces:**
- Consumes: `StageCounts`, `StageKey`, `STAGE_ORDER`, `PausableStage`.
- Produces:

```ts
interface StageStripProps {
  counts: StageCounts
  selected: StageKey | null
  onSelect: (stage: StageKey | null) => void
  pausedStages: PausableStage[]
  canManage: boolean
  onTogglePause: (stage: PausableStage, paused: boolean) => void
  // Rendered inside the File history block (the index worker stepper).
  historyExtra?: React.ReactNode
}
```

- [ ] **Step 1: Failing test** `StageStrip.test.tsx`:

```tsx
const counts = (over: Partial<StageCounts> = {}) => ({ ...emptyCounts(), ...over })

it('shows every stage, idle ones included', () => {
  render(<StageStrip counts={counts()} selected={null} onSelect={vi.fn()} pausedStages={[]} canManage onTogglePause={vi.fn()} />)
  for (const label of ['Connect', 'Archive list', 'Retention preview', 'File history', 'Stats'])
    expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument()
  expect(screen.getAllByText('Idle')).toHaveLength(5)
})

it('toggles the filter', () => {
  const onSelect = vi.fn()
  const { rerender } = render(<StageStrip counts={counts({ archives: { total: 3, running: 2, waiting: 1, failed: 0 } })} selected={null} onSelect={onSelect} pausedStages={[]} canManage onTogglePause={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: /Archive list/ }))
  expect(onSelect).toHaveBeenCalledWith('archives')
  rerender(<StageStrip counts={counts()} selected="archives" onSelect={onSelect} pausedStages={[]} canManage onTogglePause={vi.fn()} />)
  expect(screen.getByRole('button', { name: /Archive list/ })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: /Archive list/ }))
  expect(onSelect).toHaveBeenLastCalledWith(null)
})

it('pauses and resumes a stage, admins only, never connect', () => {
  const onTogglePause = vi.fn()
  const { rerender } = render(<StageStrip counts={counts()} selected={null} onSelect={vi.fn()} pausedStages={['history']} canManage onTogglePause={onTogglePause} />)
  expect(screen.queryByRole('button', { name: 'Pause Connect' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Resume File history' }))
  expect(onTogglePause).toHaveBeenCalledWith('history', false)
  fireEvent.click(screen.getByRole('button', { name: 'Pause Stats' }))
  expect(onTogglePause).toHaveBeenCalledWith('stats', true)
  rerender(<StageStrip counts={counts()} selected={null} onSelect={vi.fn()} pausedStages={['history']} canManage={false} onTogglePause={onTogglePause} />)
  expect(screen.queryByRole('button', { name: /^(Pause|Resume) / })).toBeNull()
  expect(screen.getByText('Paused')).toBeInTheDocument()
})
```

Export `emptyCounts()` from `hubRows.ts` (the zeroed object `stageCounts` starts from) so tests and stories share it.

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** Layout per spec 3.2: `Box` grid `repeat(auto-fit, minmax(128px, 1fr))`, gap 1. Each block is a `Box` with `border: 1px solid divider`, radius 2, `bgcolor: background.paper`, padding 1.5; selected block uses `borderColor: primary.main` and `boxShadow: inset 0 0 0 1px primary.main` (full outline, no left accent). The clickable area is a `ButtonBase` with `aria-pressed` and an accessible name of the stage label, containing: caption label (`operations.background.stage.<key>`), count (`h5`, tabular numbers, `text.disabled` when 0), and a caption line: when `total === 0` `operations.background.strip.idle`; otherwise the non-zero parts of `strip.running`, `strip.waiting`, `strip.failed` (pluralised counts) joined with ` · `, failed in `error.main`. Top-right corner, outside the `ButtonBase` (so it does not trigger the filter): a `Chip` `strip.paused` (size small, warning tint) when paused, and for admins on pausable stages an `IconButton` (`Pause`/`Play` lucide, 14px) with `aria-label` `strip.pauseStage`/`strip.resumeStage` (`{{stage}}`) and a matching `Tooltip`. `historyExtra` renders under the caption in the `history` block.

Locale keys under `operations.background.strip` (all four files; translate de/es/it):

```json
"strip": {
  "idle": "Idle",
  "running_one": "{{count}} running", "running_other": "{{count}} running",
  "waiting_one": "{{count}} waiting", "waiting_other": "{{count}} waiting",
  "failed_one": "{{count}} failed", "failed_other": "{{count}} failed",
  "paused": "Paused",
  "pauseStage": "Pause {{stage}}",
  "resumeStage": "Resume {{stage}}",
  "label": "Background stages"
}
```

Stories in `StageStrip.stories.tsx`: `BackupWave` (archives 6 = 4 running 2 waiting, retention 1, history 2 = 1 running 1 failed, stats 1), `AllIdle`, `OneStagePaused` (history paused, 3 waiting), `AllPaused`, `ReadOnly` (`canManage: false`), `Selected` (archives).

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit.** `feat(background-work): stage strip with counts, filter and per-stage pause`

### Task 6: Current stage cell, board wiring, Pause all

**Files:**
- Create: `frontend/src/components/background-work/CurrentStage.tsx` (from `StageTrack.tsx`'s `StageSegment`)
- Delete: `frontend/src/components/background-work/StageTrack.tsx`
- Modify: `RepositoryHubRow.tsx`, `RepositoryHubRow.stories.tsx`, `PipelineBoard.tsx`, `PipelineBoard.stories.tsx`, `frontend/src/components/BackgroundWorkTab.tsx`, locales
- Test: `__tests__/RepositoryHubRow.test.tsx`, `__tests__/PipelineBoard.test.tsx`

**Interfaces:**
- Consumes: `currentStage`, `stageCounts`, `StageStrip`, `operationsAPI.pauseStage/resumeStage`.
- Produces: `CurrentStage({ stage: StageState | null, now: number, onRetry })`.

- [ ] **Step 1: Failing tests.**

`RepositoryHubRow.test.tsx`: replace assertions on `stage-track` / `stage-cell-*` with the cell:

```tsx
it('shows the stage the repository is in, with its wait reason', () => {
  renderRow({ track: trackWith([{ key: 'stats', status: 'waiting', reason: 'upstream_paused' }]) })
  const cell = screen.getByTestId('current-stage')
  expect(within(cell).getByText('Stats')).toBeInTheDocument()
  expect(within(cell).getByText('Waiting on a paused stage')).toBeInTheDocument()
})

it('offers retry on a failed stage', () => {
  const onRetry = vi.fn()
  renderRow({ onRetry, track: trackWith([{ key: 'archives', status: 'failed' }]) })
  fireEvent.click(within(screen.getByTestId('current-stage')).getByRole('button', { name: 'Retry' }))
  expect(onRetry).toHaveBeenCalledWith(expect.objectContaining({ key: 'archives' }))
})

it('leaves the cell empty at rest', () => {
  renderRow({ track: null })
  expect(screen.getByTestId('current-stage')).toBeEmptyDOMElement()
})
```

`PipelineBoard.test.tsx` (queue mocks gain `paused_stages`; add `pauseStage`/`resumeStage` to the `operationsAPI` mock):

```tsx
it('counts repositories per stage and filters the table by a block', async () => {
  // queue: repo 1 archive_sync running; repo 2 stats queued; hub has repos 1, 2, 3
  renderBoard()
  const strip = await screen.findByRole('group', { name: 'Background stages' })
  expect(within(strip).getByRole('button', { name: /Archive list/ })).toHaveTextContent('1')
  fireEvent.click(within(strip).getByRole('button', { name: /Stats/ }))
  expect(screen.getAllByTestId('repository-row')).toHaveLength(1)
})

it('pauses a single stage', async () => {
  renderBoard()
  fireEvent.click(await screen.findByRole('button', { name: 'Pause File history' }))
  await waitFor(() => expect(operationsAPI.pauseStage).toHaveBeenCalledWith('history'))
})

it('shows the worker stepper on the file history block', async () => {
  renderBoard()
  const strip = await screen.findByRole('group', { name: 'Background stages' })
  expect(within(strip).getByRole('button', { name: 'More index workers' })).toBeInTheDocument()
})
```

In the `withParent` tests: the header button reads "Pause all"; the banner appears only when `paused` is true and its action reads "Resume all".

Remove tests that exercised the history-without-capability resync retry (see step 3).

- [ ] **Step 2: Run, expect failures.** `npx vitest run src/components/background-work src/components/BackgroundWorkTab`
- [ ] **Step 3: Implement.**

`CurrentStage.tsx`: move `StageSegment` from `StageTrack.tsx` unchanged except: always render the stage label (drop the `display: { md: 'none' }`), caption also handles `upstream_paused` through the existing `reason.*` lookup (no change needed), and wrap as

```tsx
export default function CurrentStage({ stage, now, onRetry }: { stage: StageState | null; now: number; onRetry: (stage: StageState) => void }) {
  return (
    <Box data-testid="current-stage" sx={{ minWidth: 0, gridColumn: { xs: '1 / -1', md: 'auto' } }}>
      {stage && <StageSegment stage={stage} now={now} onRetry={onRetry} />}
    </Box>
  )
}
```

Delete `StageTrack.tsx`.

`RepositoryHubRow.tsx`: render `<CurrentStage stage={currentStage(track)} now={now} onRetry={onRetry} />` as the second grid cell; remove the shaded `StageTrack` band. Keep the `trackOff` caption for `off` repositories with no live stage. The system lane's placeholder spans 3 data columns after the Current stage cell (unchanged `span 3`).

`PipelineBoard.tsx`:
- `deriveTrack(repo, queue.data.limits, queue.data.paused_stages)`.
- `const counts = useMemo(() => stageCounts(rows), [rows])`.
- A `stageMutation` calling `pauseStage`/`resumeStage`, invalidating `QUEUE_KEY`; its error shows `operations.background.pauseFailed`.
- Render `<StageStrip counts={counts} selected={toolbar.stage} onSelect={(stage) => setToolbar({ ...toolbar, stage })} pausedStages={queue.data.paused_stages} canManage={canManage} onTogglePause={(stage, paused) => stageMutation.mutate({ stage, paused })} historyExtra={<WorkerStepper ... />} />` between `HubSummary` and `{messages}`, wrapped in `role="group"` `aria-label={t('operations.background.strip.label')}` (put the role on StageStrip's root).
- Header row: columns `repositoryColumn`, `currentStageColumn`, `archivesColumn`, `historyColumn`, `statsColumn`, empty; no stepper.
- `handleRetry`: drop the `history_capability` resync branch and `resyncMutation`/`resyncDeferred`/`retryDeferred` (the history stage now only ever holds `history_index`, which exists only where history can be built). Retry is `rebuildMutation.mutate({ repositoryId, stage: REBUILD_STAGE_FOR[stage.key] })`; `REBUILD_STAGE_FOR` has no `retention` or `connect`, so those stages show no Retry button (StageSegment already checks it).

`BackgroundWorkTab.tsx`: button label `operations.background.pauseAll`, banner action `operations.background.resumeAll`, banner text unchanged.

Locale keys (four files): `pauseAll: "Pause all"`, `resumeAll: "Resume all"`, `currentStageColumn: "Current stage"`, `archivesColumn: "Archives"`, `historyColumn: "File history"`, `statsColumn: "Stats"`. Remove now-unused `retryDeferred`, `pause`, `resume` only if nothing references them (`grep -rn "background.pause'" src`).

Update `RepositoryHubRow.stories.tsx` (stories for running, waiting with reason, upstream paused, failed) and `PipelineBoard.stories.tsx` (the board with the strip; one story with a paused stage).

- [ ] **Step 4: Run, expect pass.** Full frontend: `npx vitest run`, `npx tsc --noEmit -p .`, `npm run lint`.
- [ ] **Step 5: Commit.** `feat(background-work): current stage column and stage strip on the board`

### Task 7: Docs, visual check, PR

**Files:**
- Modify: `docs/navigation.md:64`, `docs/configuration.md:163-165`

- [ ] **Step 1: Docs.** `navigation.md` Background work row: "See how many repositories are in each background stage (connect, archive list, retention preview, file history, stats), filter the table by a stage, pause or resume a single stage or all of them, adjust index workers, and rebuild derived data. Visible to admins and operators." `configuration.md`: `background_paused` becomes `paused_stages`.
- [ ] **Step 2: Backend suite.** `../borg-ui/.venv/bin/pytest tests/unit -q` (14 `test_api_auth` failures from a local `.env` are known and unrelated; confirm with `git stash` if any other fails).
- [ ] **Step 3: Visual check.** Storybook with Node from fnm v24 (copy the darwin-arm64 native bindings into the worktree's `node_modules` if needed); screenshot `StageStrip` and `PipelineBoard` stories in light and dark.
- [ ] **Step 4: Commit docs, push, open PR** against `main` with summary, the dependency note on #1168, and the test plan.
