# Operations Phase 10: Per-repository Index Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents, per the
> spec's Appendix B). Use superpowers:test-driven-development inside every
> task, and `ui-ux-pro-max` for the UI tasks. Steps use checkbox (`- [ ]`)
> syntax for tracking. Do not commit at the end of a task; the phase has one
> commit gate (G2) at the end, per section 19.4 of the spec and
> `.claude/instructions.md`.

**Goal:** Make "how much of this repository do we index" a per-repository
choice (spec 6.8): a `full` / `archives` / `off` mode that the follow-up
chain and the reconcile tick honour, that manual work can still override
once, and that every surface reads as a deliberate setting rather than as a
repository that is stale or broken. The same phase puts the 6.7 exclude list
into the UI, since neither control exists there today.

**Architecture:** One new module, `app/services/operations/index_mode.py`,
owns the mode vocabulary and the single filter that drops kinds a mode says
no to. Two callers apply it: `followups.chain_for()` and
`reconcile.reconcile_kinds()`, exactly as 6.8 requires, reached from the six
existing `chain_for` call sites through one new helper
(`chain_for_repository`) so no call site grows a lookup of its own. Nothing
is created and then skipped: a stage a mode excludes never becomes a row,
which is the Community rule from 11.2 applied to a second reason. The mode
change itself is a side effect of `PUT /repositories/{id}`: leaving `full`
cancels the repository's queued index operations through the runner (7.7),
returning to `full` enqueues one catch-up reconcile run. Manual work
(`/rebuild`, `/resync`) is never blocked by the mode; it drops only the
history stages a non-`full` mode excludes and tells the caller the run will
not repeat. The frontend reads `index_mode` off the repository payloads it
already fetches, so no new query is added anywhere.

**Tech Stack:** FastAPI, SQLAlchemy declarative models, Alembic with
`batch_alter_table` for SQLite, pytest with the in-memory `db` fixture
pattern from `tests/unit/test_operations_reconcile.py` and the
`test_client` / `admin_headers` fixtures from `tests/fixtures/api.py`;
React with MUI, `react-i18next`, `RichSelect`, `PlanGate`, TanStack Query,
Vitest and Storybook on the frontend. No new dependencies.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`,
sections 6.7, 6.8, 7.4, 7.5, 7.7, 9.2, 10.1, 10.2, 11.2, 11.3, 13 (phase 10
row), 18, Appendix B. Review focus (19.3) for this phase is not listed
separately, so the reviewer reads 6.8 in full plus Appendix B, and 10.1 and
10.2 for the surfaces.

## Model

Section 13 splits phase 10: Sonnet 5 for the column, chain filter, routes,
and settings control; Opus 5 for the hub and card states; Opus 5 to review.
This plan was drafted on Opus 5 at gate G0 on 2026-09-11, which is one of the
two implement models the row names and the model 19.5 calls sufficient for
plan writing. An implementing session may follow the split or stay on one
model; record the choice in the 19.1 Notes.

## Global Constraints

- No em dashes anywhere: not in code comments, not in i18n strings, not in
  documentation. Use periods, commas or parentheses.
- Every user-visible string goes through `react-i18next` with the key added
  to all four of `frontend/src/locales/{en,de,es,it}.json`. German, Spanish
  and Italian are translated, never left as English.
- Every new or changed component ships or updates a Storybook story
  (`AGENTS.md` lines 18 and 21), and components stay small and composed.
- No left accent borders; dialogs use `ResponsiveDialog`; rich option rows
  use `RichSelect` (spec section 10 preamble).
- `index_mode` is `String`, not null, server default `'full'`. A repository
  that predates the column reads `full`, so nothing about an existing
  install changes until someone sets a mode.
- The mode is applied in exactly two functions, `chain_for` and
  `reconcile_kinds` (spec 6.8). No executor, service or route grows its own
  mode branch. Manual entry points (`/rebuild`, `/resync`) are the single
  documented exception and go through the same module's filter.
- Backend tests come before the code in every task; frontend tests are
  Vitest under the component's `__tests__` directory, following the
  neighbouring test files' style.
- Nothing is committed until gate G2.

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `app/services/operations/index_mode.py` | The mode vocabulary, the mode-to-kinds table from 6.8, `filter_kinds`, and `mode_for_repository`. The one place the table lives. |
| `app/database/alembic/versions/<rev>_add_repository_index_mode.py` | Adds `repositories.index_mode` with a `'full'` backfill. |
| `tests/unit/test_operations_index_mode.py` | The filter and the vocabulary. |
| `tests/unit/test_index_mode_chains.py` | `chain_for_repository` and `reconcile_kinds` under each mode, and the reconcile tick skipping `off`. |
| `tests/unit/test_api_repository_index_mode.py` | The `PUT` validation, the cancel-on-leave and catch-up-on-return side effects, and the payload fields. |
| `frontend/src/components/repositories/IndexModeSettings.tsx` | The mode `RichSelect` and the 6.7 exclude list editor. |
| `frontend/src/components/repositories/IndexModeSettings.stories.tsx` | Its three modes. |
| `frontend/src/components/repositories/__tests__/IndexModeSettings.test.tsx` | Its behaviour. |
| `frontend/src/components/archives/IndexModeGate.tsx` | The 6.8 panel that replaces history content when the mode excludes it. |
| `frontend/src/components/archives/IndexModeGate.stories.tsx` | Its two reasons. |
| `frontend/src/hooks/useIndexMode.ts` | Reads one repository's mode off the shared `['repositories']` query, so no surface adds a fetch. |

**Modified**

| File | Change |
| --- | --- |
| `app/database/models.py` | The `index_mode` column beside `history_index_excludes` (line 385). |
| `app/services/operations/followups.py` | `chain_for` gains `mode`; new `chain_for_repository`. |
| `app/services/operations/reconcile.py` | `reconcile_kinds` gains the mode; `enqueue_reconcile_run` gains `manual`; the tick skips `off`. |
| `app/services/operations/runner.py:475`, `executors/wipe.py:58`, `executors/backup.py:102`, `enqueue.py:145`, `maintenance_start.py:314`, `followups.py:128` | Each switches to `chain_for_repository`. |
| `app/api/repositories.py` | `RepositoryUpdate.index_mode`, its validation and side effects, and `index_mode` in the list and detail payloads. |
| `app/api/archive_index.py` | `/rebuild` and `/resync` filter history stages by the mode and report `repeats`. |
| `app/services/operations/repository_status.py` | The `index` cell is omitted for `off`. |
| `app/api/operations.py` | `HubRepository.index_mode`. |
| `frontend/src/types/operations.ts`, `types/index.ts`, `pages/repositories-page/types.ts` | The `IndexMode` type and the fields. |
| `frontend/src/components/background-work/hubRows.ts`, `RepositoryHubRow.tsx`, `storyFixtures.ts` | The muted hub states and the attention counts. |
| `frontend/src/components/RepositoryCard.tsx` | The `off` message on both last-run entries. |
| `frontend/src/components/wizard/WizardStepRepositoryAdvanced.tsx`, `frontend/src/components/RepositoryWizard.tsx` | The settings control and its payload field. |
| `frontend/src/components/archives/ArchiveChangesTab.tsx`, `ArchiveFileDetailsPane.tsx` | The mode gate inside the plan gate. |
| `frontend/src/locales/{en,de,es,it}.json` | The new keys. |
| `docs/api.md`, `docs/navigation.md`, `docs/architecture/job-system.md` | The mode, its routes, and where it is set. |
| The spec's 19.1 row | Status transitions. |

---

## Task 1: The column, the vocabulary, and the payloads

Nothing behavioural yet: the mode can be stored and read back, and the
module that owns the 6.8 table exists with its filter tested. Later tasks
call the filter.

**Files:**
- Create: `app/services/operations/index_mode.py`
- Create: `app/database/alembic/versions/<rev>_add_repository_index_mode.py`
- Create: `tests/unit/test_operations_index_mode.py`
- Create: `tests/unit/test_api_repository_index_mode.py`
- Modify: `app/database/models.py` (beside `history_index_excludes`, line 385)
- Modify: `app/api/repositories.py` (`RepositoryUpdate` at line 1300, the
  list payload at line 3037, the detail payload at line 4103, the update
  handler at line 4883)

**Interfaces:**
- Produces: `INDEX_MODES: tuple[str, ...]`, `DEFAULT_INDEX_MODE: str`,
  `INDEX_KINDS: frozenset[str]`, `MODE_KINDS: dict[str, frozenset[str]]`,
  `mode_of(repository) -> str`, `mode_for_repository(db, repository_id) -> str`,
  `filter_kinds(mode, kinds) -> list[str]`, `indexes_history(mode) -> bool`.
  Every later task consumes them.

- [ ] **Step 1: Write the failing filter tests**

```python
# tests/unit/test_operations_index_mode.py
import pytest

from app.services.operations import index_mode as im


def test_full_keeps_every_index_kind():
    assert im.filter_kinds("full", ["archive_sync", "history_merge", "history_index", "stats"]) == [
        "archive_sync",
        "history_merge",
        "history_index",
        "stats",
    ]


def test_archives_drops_only_the_history_kinds():
    assert im.filter_kinds(
        "archives", ["archive_sync", "history_merge", "history_index", "stats"]
    ) == ["archive_sync", "stats"]


def test_off_drops_every_index_kind():
    assert im.filter_kinds("off", ["archive_sync", "history_merge", "history_index", "stats"]) == []


def test_kinds_outside_the_index_category_are_never_dropped():
    # The mode governs derived data, not the work a user asked for. A chain
    # that ever carries a non-index kind keeps it in every mode.
    assert im.filter_kinds("off", ["backup", "stats"]) == ["backup"]


def test_an_unknown_mode_reads_as_the_default():
    # A row written by a newer version, or hand-edited. Indexing everything
    # is the safe reading: the repository keeps working.
    assert im.filter_kinds("nonsense", ["history_index"]) == ["history_index"]


def test_indexes_history():
    assert im.indexes_history("full") is True
    assert im.indexes_history("archives") is False
    assert im.indexes_history("off") is False


def test_mode_of_a_repository_without_the_column_set():
    class Repo:
        index_mode = None

    assert im.mode_of(Repo()) == "full"


@pytest.mark.parametrize("mode", im.INDEX_MODES)
def test_every_mode_has_a_kind_set(mode):
    assert mode in im.MODE_KINDS
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/unit/test_operations_index_mode.py -q`
Expected: FAIL, `ModuleNotFoundError: app.services.operations.index_mode`

- [ ] **Step 3: Write the module**

```python
# app/services/operations/index_mode.py
"""Per-repository index mode (spec section 6.8).

The mode says how much derived data a repository keeps up to date. It is
applied in exactly two places, `followups.chain_for` and
`reconcile.reconcile_kinds`, so a stage a mode excludes is never created and
then skipped (the Community rule in spec 11.2, Appendix B). This module owns
the table from 6.8 and nothing else.
"""

from typing import Iterable, Optional

DEFAULT_INDEX_MODE = "full"
INDEX_MODES: tuple[str, ...] = ("full", "archives", "off")

# The four kinds the mode governs. Anything else in a chain is work someone
# asked for and is never dropped here.
INDEX_KINDS: frozenset[str] = frozenset(
    {"stats", "archive_sync", "history_index", "history_merge"}
)

# Spec 6.8: what each mode keeps refreshing.
MODE_KINDS: dict[str, frozenset[str]] = {
    "full": frozenset({"stats", "archive_sync", "history_index", "history_merge"}),
    "archives": frozenset({"stats", "archive_sync"}),
    "off": frozenset(),
}


def normalize(mode: Optional[str]) -> str:
    """A mode this version understands. A null column (a row that predates
    the column) and an unrecognised value both read as `full`: indexing
    everything is the reading that keeps the repository working."""
    return mode if mode in MODE_KINDS else DEFAULT_INDEX_MODE


def mode_of(repository) -> str:
    return normalize(getattr(repository, "index_mode", None))


def mode_for_repository(db, repository_id: Optional[int]) -> str:
    """The mode of one repository, by id, for the follow-up chain. Work with
    no repository (a package install) is never index work, so it reads as
    the default."""
    if repository_id is None:
        return DEFAULT_INDEX_MODE
    from app.database.models import Repository

    value = (
        db.query(Repository.index_mode).filter(Repository.id == repository_id).scalar()
    )
    return normalize(value)


def allows(mode: str, kind: str) -> bool:
    if kind not in INDEX_KINDS:
        return True
    return kind in MODE_KINDS[normalize(mode)]


def filter_kinds(mode: str, kinds: Iterable[str]) -> list[str]:
    """`kinds` minus the index kinds this mode does not refresh."""
    resolved = normalize(mode)
    return [k for k in kinds if allows(resolved, k)]


def indexes_history(mode: str) -> bool:
    """True when the mode keeps file history (spec 6.5) up to date."""
    return "history_index" in MODE_KINDS[normalize(mode)]
```

- [ ] **Step 4: Run the filter tests and watch them pass**

Run: `pytest tests/unit/test_operations_index_mode.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 5: Write the failing API tests for the column and the payloads**

```python
# tests/unit/test_api_repository_index_mode.py
def test_a_new_repository_reads_as_full(test_client, admin_headers, repository):
    response = test_client.get("/api/repositories/", headers=admin_headers)
    assert response.status_code == 200
    row = next(
        r for r in response.json()["repositories"] if r["id"] == repository.id
    )
    assert row["index_mode"] == "full"


def test_the_detail_payload_carries_the_mode(test_client, admin_headers, repository):
    response = test_client.get(
        f"/api/repositories/{repository.id}", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["repository"]["index_mode"] == "full"


def test_the_mode_can_be_set(test_client, admin_headers, repository, test_db):
    response = test_client.put(
        f"/api/repositories/{repository.id}",
        json={"index_mode": "archives"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    test_db.refresh(repository)
    assert repository.index_mode == "archives"


def test_an_unknown_mode_is_refused(test_client, admin_headers, repository):
    response = test_client.put(
        f"/api/repositories/{repository.id}",
        json={"index_mode": "sometimes"},
        headers=admin_headers,
    )
    assert response.status_code == 422
```

Read `tests/fixtures/api.py` first and use the repository fixture that file
actually provides (the neighbouring `tests/unit/test_api_archive_index.py`
shows the current names); adapt the four tests to it rather than inventing a
fixture.

- [ ] **Step 6: Run them and watch them fail**

Run: `pytest tests/unit/test_api_repository_index_mode.py -q`
Expected: FAIL, `KeyError: 'index_mode'` on the first two and 200 on the
fourth.

- [ ] **Step 7: Add the column to the model**

In `app/database/models.py`, directly under `history_index_excludes`:

```python
    # How much derived data this repository keeps refreshed (spec 6.8).
    # "full", "archives" or "off"; see app/services/operations/index_mode.py.
    index_mode = Column(String(20), nullable=False, server_default="full")
```

- [ ] **Step 8: Write the migration**

`down_revision` is the current head. Confirm it first:

```bash
python3 - <<'PY'
import ast, os, re
d = "app/database/alembic/versions"
revs, downs = {}, set()
for f in sorted(os.listdir(d)):
    if not f.endswith(".py"):
        continue
    t = open(os.path.join(d, f)).read()
    r = re.search(r"^revision(?::.*?)?\s*=\s*(.+)$", t, re.M)
    dn = re.search(r"^down_revision(?::.*?)?\s*=\s*(.+)$", t, re.M)
    if r:
        revs[ast.literal_eval(r.group(1).strip())] = f
    if dn:
        v = ast.literal_eval(dn.group(1).strip())
        downs.update(v if isinstance(v, (tuple, list)) else ([v] if v else []))
print([(r, f) for r, f in revs.items() if r not in downs])
PY
```

At the time of writing that is `d0e1f2a3b4c5` (phase 9's collapse). If main
has moved on, chain onto whatever the command prints, and if it prints more
than one head, stop and raise it at gate G5: the two-heads hazard bit phases
6 and 9 and is not to be guessed at. Pick a revision id no other file uses.

```python
"""add repository index mode

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.add_column(
            sa.Column(
                "index_mode",
                sa.String(length=20),
                nullable=False,
                server_default="full",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("repositories") as batch:
        batch.drop_column("index_mode")
```

- [ ] **Step 9: Add the field to the update schema and the two payloads**

In `RepositoryUpdate` (`app/api/repositories.py:1300`), beside
`history_index_excludes`:

```python
    index_mode: Optional[Literal["full", "archives", "off"]] = None
```

Check the file's existing imports for `Literal`; add it to the `typing`
import if it is not there. The `Literal` is what makes an unknown value a
422 without a hand-written check.

In the list payload (`:3037`) and the detail payload (`:4103`), beside
`history_index_excludes`:

```python
                "index_mode": index_mode_of(repo),
```

with `from app.services.operations.index_mode import mode_of as index_mode_of`
at the top of the file, so a row written before the column still reads
`full` in the payload.

In the update handler (`:4883`), beside the `history_index_excludes` branch,
for now only the assignment (the side effects are Task 3):

```python
        if repo_data.index_mode is not None:
            repository.index_mode = repo_data.index_mode
```

- [ ] **Step 10: Run the API tests and watch them pass**

Run: `pytest tests/unit/test_api_repository_index_mode.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 11: Prove the migration runs both ways**

Run:

```bash
python3 -m pytest tests/unit -q -p no:randomly -k "migration" 2>&1 | tail -5
```

Then a real up and down against a scratch database, following the
`_migrate(url, target)` helper in
`tests/unit/test_backup_job_archive_pruned_at_migration.py`, and confirm
`repositories.index_mode` exists after `upgrade` and is gone after
`downgrade`. Add that as a test in
`tests/unit/test_api_repository_index_mode.py` if the helper makes it cheap;
otherwise record the manual run in the task notes.

---

## Task 2: The chain and the reconcile tick honour the mode

**Files:**
- Modify: `app/services/operations/followups.py`
- Modify: `app/services/operations/reconcile.py`
- Modify: `app/services/operations/runner.py:475`,
  `app/services/operations/executors/wipe.py:58`,
  `app/services/operations/executors/backup.py:102`,
  `app/services/operations/enqueue.py:145`,
  `app/services/operations/maintenance_start.py:314`
- Create: `tests/unit/test_index_mode_chains.py`

**Interfaces:**
- Consumes: `filter_kinds`, `mode_for_repository`, `DEFAULT_INDEX_MODE` from
  Task 1.
- Produces: `chain_for(kind, *, available=None, history=True, mode=DEFAULT_INDEX_MODE) -> list[str]`,
  `chain_for_repository(db, kind, repository_id, *, history=None) -> list[str]`,
  `reconcile_kinds(db, *, history=None, mode=DEFAULT_INDEX_MODE) -> list[str]`,
  `enqueue_reconcile_run(db, repository_id, *, history=None, manual=False, commit=True) -> list`.

- [ ] **Step 1: Write the failing chain tests**

```python
# tests/unit/test_index_mode_chains.py
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, SystemSettings
from app.services.operations import reconcile
from app.services.operations.followups import chain_for, chain_for_repository


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
        engine.dispose()


def _repository(db, mode):
    repo = Repository(name=f"repo-{mode}", path=f"/tmp/{mode}", index_mode=mode)
    db.add(repo)
    db.add(SystemSettings())
    db.commit()
    return repo


def test_chain_for_full_is_unchanged():
    assert chain_for("backup") == ["archive_sync", "history_merge", "history_index", "stats"]


def test_chain_for_archives_keeps_the_listing_and_the_size():
    assert chain_for("backup", mode="archives") == ["archive_sync", "stats"]


def test_chain_for_off_is_empty():
    assert chain_for("backup", mode="off") == []


def test_chain_for_repository_reads_the_repository_mode(db):
    repo = _repository(db, "archives")
    assert chain_for_repository(db, "backup", repo.id, history=True) == [
        "archive_sync",
        "stats",
    ]


def test_chain_for_repository_with_no_repository_is_the_default(db):
    _repository(db, "off")
    # Work with no repository (a package install) is not index work.
    assert chain_for_repository(db, "package_install", None, history=True) == []


def test_reconcile_kinds_drop_history_in_archives_mode(db):
    _repository(db, "archives")
    assert "history_index" not in reconcile.reconcile_kinds(db, history=True, mode="archives")
    assert "archive_sync" in reconcile.reconcile_kinds(db, history=True, mode="archives")


def test_reconcile_kinds_are_empty_for_off(db):
    assert reconcile.reconcile_kinds(db, history=True, mode="off") == []


def test_the_reconcile_tick_enqueues_nothing_for_an_off_repository(db):
    repo = _repository(db, "off")
    assert reconcile.enqueue_reconcile_run(db, repo.id, history=True) == []
    assert db.query(Operation).count() == 0


def test_a_manual_run_still_lists_an_off_repository(db):
    # Spec 6.8: manual work is not gated by the mode, it just does not repeat.
    repo = _repository(db, "off")
    ops = reconcile.enqueue_reconcile_run(db, repo.id, history=True, manual=True)
    assert [op.kind for op in ops] == ["archive_sync", "stats"]


def test_a_manual_run_never_re_enables_history(db):
    repo = _repository(db, "archives")
    ops = reconcile.enqueue_reconcile_run(db, repo.id, history=True, manual=True)
    assert [op.kind for op in ops] == ["archive_sync", "stats"]


def test_the_reconcile_sweep_skips_off_repositories(db):
    _repository(db, "off")
    full = Repository(name="full", path="/tmp/full", index_mode="full")
    db.add(full)
    db.commit()
    assert reconcile.enqueue_reconcile_runs(db, history=True) == 1
    assert {op.repository_id for op in db.query(Operation).all()} == {full.id}
```

The executor registry decides which kinds actually exist, so if
`reconcile_kinds` returns fewer kinds than the assertions expect in a bare
unit environment, register the kinds the way
`tests/unit/test_operations_reconcile.py` does rather than weakening the
assertion.

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/unit/test_index_mode_chains.py -q`
Expected: FAIL, `TypeError: chain_for() got an unexpected keyword argument 'mode'`.

- [ ] **Step 3: Teach `chain_for` the mode and add `chain_for_repository`**

In `app/services/operations/followups.py`:

```python
def chain_for(
    kind: str,
    *,
    available: Optional[set[str]] = None,
    history: bool = True,
    mode: str = DEFAULT_INDEX_MODE,
) -> list[str]:
    """Return the follow-up kinds for `kind`, in order.

    `available` drops kinds without an executor. `history=False` drops the
    plan gated kinds for Community installs (spec 11.2): the stage does not
    exist rather than being created and skipped (Appendix B). history_merge
    is not gated; see PLAN_GATED_KINDS. `mode` drops the kinds the
    repository's index mode does not refresh (spec 6.8), by the same rule:
    a stage that will never run does not exist.
    """
    validate_kind(kind)
    chain = list(FOLLOWUPS[kind])
    if available is not None:
        chain = [k for k in chain if k in available]
    if not history:
        chain = [k for k in chain if k not in PLAN_GATED_KINDS]
    return filter_kinds(mode, chain)


def chain_for_repository(
    db, kind: str, repository_id: Optional[int], *, history: Optional[bool] = None
) -> list[str]:
    """`chain_for` with this install's executors, this install's plan, and
    this repository's index mode. Every follow-up site calls this, so the
    two gates are read in one place rather than six.

    `history` is the plan gate; left None it is read here, which goes
    through the licensing service and commits the session. A caller that
    wraps this call in a savepoint reads it beforehand and passes it in.
    """
    from app.services.operations.executors import registered_kinds

    if history is None:
        history = history_enabled(db)
    return chain_for(
        kind,
        available=registered_kinds(),
        history=history,
        mode=mode_for_repository(db, repository_id),
    )
```

with `from app.services.operations.index_mode import (DEFAULT_INDEX_MODE,
filter_kinds, mode_for_repository)` at the top of the module. `index_mode`
imports nothing from `followups`, so there is no cycle.

- [ ] **Step 4: Move the six call sites onto `chain_for_repository`**

Each becomes one call. `runner.py:475`:

```python
                kinds = chain_for_repository(db, op.kind, op.repository_id)
```

`executors/wipe.py:58`:

```python
        kinds = chain_for_repository(ctx.db, "wipe", operation.repository_id)
```

`executors/backup.py:102`:

```python
    kinds = chain_for_repository(ctx.db, "backup", operation.repository_id)
```

`maintenance_start.py:314`:

```python
    kinds = chain_for_repository(db, operation.kind, operation.repository_id)
```

`enqueue.py:145` keeps its ordering comment and its explicit plan read,
because the comment above it explains why the plan lookup happens before the
row exists:

```python
    kinds = chain_for_repository(
        db, "import_connect", repository.id, history=history_enabled(db)
    )
```

`followups.py:128` inside `enqueue_backup_followups`, which already has
`history` resolved:

```python
    kinds = chain_for_repository(db, "backup", repository_id, history=history)
```

Drop the now unused `registered_kinds` and `chain_for` imports at each site
and let `ruff` confirm it.

- [ ] **Step 5: Teach reconcile the mode**

In `app/services/operations/reconcile.py`:

```python
def reconcile_kinds(
    db: Session, *, history: Optional[bool] = None, mode: str = DEFAULT_INDEX_MODE
) -> list:
    """The reconcile chain, minus kinds this install has no executor for,
    kinds the plan does not include, and kinds the repository's index mode
    does not refresh (spec 6.8)."""
    available = registered_kinds()
    if history is None:
        history = history_enabled(db)
    return filter_kinds(
        mode,
        [
            k
            for k in RECONCILE_CHAIN
            if k in available and (history or k not in PLAN_GATED_KINDS)
        ],
    )
```

```python
def enqueue_reconcile_run(
    db: Session,
    repository_id: int,
    *,
    history: Optional[bool] = None,
    manual: bool = False,
    commit: bool = True,
) -> list:
    """One repository's reconcile run. Returns the operations enqueued, or an
    empty list when index work for the repository is already in flight, so a
    burst of callers (a run of archive deletes, say) queues one run rather
    than one per call.

    `manual=True` is a user asking for this run: an `off` repository is
    listed once anyway (spec 6.8, "manual work is not gated by the mode"),
    but history is never re-enabled behind a mode that excludes it, and
    nothing is scheduled to repeat.
    """
    mode = mode_for_repository(db, repository_id)
    if manual and mode == "off":
        # The one-off look: archive_sync and stats, this once.
        mode = "archives"
    kinds = reconcile_kinds(db, history=history, mode=mode)
    if not kinds or has_active_index_work(db, repository_id):
        return []
    return enqueue_chain(
        db,
        kinds,
        repository_id=repository_id,
        trigger="manual" if manual else "reconcile",
        priority=PRIORITY_RECONCILE,
        commit=commit,
    )
```

and the sweep reads each repository's own mode, which `enqueue_reconcile_run`
already does per repository, so `enqueue_reconcile_runs` only loses its
early return:

```python
def enqueue_reconcile_runs(db: Session, *, history: Optional[bool] = None) -> int:
    if history is None:
        history = history_enabled(db)
    count = 0
    for repo in db.query(Repository).all():
        if enqueue_reconcile_run(db, repo.id, history=history, commit=False):
            count += 1
    db.commit()
    logger.info("Reconcile runs enqueued", repositories=count)
    return count
```

Note the removed `kinds=kinds` log field: the chain now differs per
repository, so one list in the log would be a lie. Add
`from app.services.operations.index_mode import (DEFAULT_INDEX_MODE,
filter_kinds, mode_for_repository)` to the imports.

The `trigger` change on a manual run matters: `resync` (Task 4) is the only
caller that passes `manual=True`, and Activity should show it as manual, not
as the hourly tick.

- [ ] **Step 6: Run the new tests and watch them pass**

Run: `pytest tests/unit/test_index_mode_chains.py -q`
Expected: PASS, 11 tests.

- [ ] **Step 7: Run every test that touches the chain**

Run:

```bash
pytest tests/unit/test_operations_followups.py tests/unit/test_operations_reconcile.py \
  tests/unit/test_operations_runner.py tests/unit/test_operations_enqueue.py -q -p no:randomly
```

(use the module names that actually exist; `ls tests/unit | grep operations`)
Expected: PASS. Any failure here is a call site that still passes the old
keyword arguments; fix it rather than restoring the old signature.

---

## Task 3: Changing the mode cancels and catches up

**Files:**
- Modify: `app/api/repositories.py` (the update handler, at the
  `index_mode` branch Task 1 added)
- Modify: `tests/unit/test_api_repository_index_mode.py`

**Interfaces:**
- Consumes: `mode_of`, `indexes_history` (Task 1),
  `enqueue_reconcile_run` (Task 2), `operation_runner.request_cancel`
  (`app/api/operations.py:673` shows the call).

- [ ] **Step 1: Write the failing side-effect tests**

Append to `tests/unit/test_api_repository_index_mode.py`:

```python
def test_leaving_full_cancels_queued_index_work(
    test_client, admin_headers, repository, test_db
):
    from tests.utils.operations import seed_operation

    queued = seed_operation(
        test_db, "history_index", repository=repository, status="queued"
    )
    other = seed_operation(test_db, "backup", repository=repository, status="queued")
    response = test_client.put(
        f"/api/repositories/{repository.id}",
        json={"index_mode": "archives"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    test_db.refresh(queued)
    test_db.refresh(other)
    assert queued.status == "cancelled"
    # A backup someone asked for is not index work and is left alone.
    assert other.status == "queued"


def test_a_running_index_is_left_to_finish(
    test_client, admin_headers, repository, test_db
):
    from tests.utils.operations import seed_operation

    running = seed_operation(
        test_db, "history_index", repository=repository, status="running"
    )
    test_client.put(
        f"/api/repositories/{repository.id}",
        json={"index_mode": "off"},
        headers=admin_headers,
    )
    test_db.refresh(running)
    assert running.status == "running"


def test_returning_to_full_enqueues_one_catch_up_run(
    test_client, admin_headers, repository, test_db
):
    from app.database.models import Operation

    repository.index_mode = "off"
    test_db.commit()
    response = test_client.put(
        f"/api/repositories/{repository.id}",
        json={"index_mode": "full"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    kinds = [
        op.kind
        for op in test_db.query(Operation)
        .filter(Operation.repository_id == repository.id)
        .all()
    ]
    assert "archive_sync" in kinds


def test_setting_the_same_mode_again_does_nothing(
    test_client, admin_headers, repository, test_db
):
    from app.database.models import Operation

    response = test_client.put(
        f"/api/repositories/{repository.id}",
        json={"index_mode": "full"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert (
        test_db.query(Operation)
        .filter(Operation.repository_id == repository.id)
        .count()
        == 0
    )
```

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/unit/test_api_repository_index_mode.py -q`
Expected: FAIL on the first and third: the queued row is still `queued` and
no catch-up run exists.

- [ ] **Step 3: Implement the side effects**

Replace the Task 1 assignment in the update handler with:

```python
        if repo_data.index_mode is not None:
            previous_mode = index_mode_of(repository)
            repository.index_mode = repo_data.index_mode
            index_mode_changed = repo_data.index_mode != previous_mode
```

and, after the handler's `db.commit()` (the mode has to be stored before the
catch-up run reads it, and a cancelled operation must not be rolled back by
a later failure in the same request), add:

```python
        if index_mode_changed:
            await _apply_index_mode_change(db, repository)
```

with, near the other module-level helpers in the file:

```python
async def _apply_index_mode_change(db: Session, repository: Repository) -> None:
    """Spec 6.8. Leaving `full` cancels the repository's queued index work,
    so a mode set to stop the diffs does not leave hours of them waiting in
    the queue. A running index is left to finish: the lane time is already
    spent, and the rows it writes are kept either way (the mode makes
    history stale, never deleted). Returning to `full` enqueues one
    reconcile run so the repository catches up without waiting for the tick.
    """
    mode = index_mode_of(repository)
    if mode == "full":
        try:
            enqueue_reconcile_run(db, repository.id)
        except Exception as exc:
            # A catch-up run is a convenience; the tick will pick the
            # repository up within the hour. The mode change itself is
            # already stored and must not be undone by this.
            db.rollback()
            logger.warning(
                "Index mode catch-up run failed",
                repo_id=repository.id,
                error=str(exc),
            )
        return
    queued = (
        db.query(Operation)
        .filter(
            Operation.repository_id == repository.id,
            Operation.category == "index",
            Operation.status == "queued",
            Operation.kind.notin_(sorted(MODE_KINDS[mode])),
        )
        .all()
    )
    for operation in queued:
        await operation_runner.request_cancel(operation.id)
```

`Operation.kind.notin_(...)` is what keeps `archives` mode from cancelling a
queued `archive_sync`, which it still wants. For `off` the set is empty, so
every queued index operation goes. Import `MODE_KINDS` and
`mode_of as index_mode_of` from `app.services.operations.index_mode`,
`enqueue_reconcile_run` from `app.services.operations.reconcile`, and
`operation_runner` the way `app/api/operations.py` imports it.

Initialise `index_mode_changed = False` beside the handler's other flags, so
the later branch is safe when the field was absent from the request.

- [ ] **Step 4: Run them and watch them pass**

Run: `pytest tests/unit/test_api_repository_index_mode.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 5: Run the repository API suite**

Run: `pytest tests/unit/test_api_repositories.py -q -p no:randomly`
Expected: PASS, no change in count. This route is long and heavily tested;
a failure here means the new branch moved something it should not have.

---

## Task 4: Manual work runs once and says so

**Files:**
- Modify: `app/api/archive_index.py` (`rebuild` at `:302`, `resync` at `:348`)
- Create: `tests/unit/test_api_archive_index_modes.py`

**Interfaces:**
- Consumes: `filter_kinds`, `mode_of` (Task 1), `enqueue_reconcile_run(..., manual=True)` (Task 2).
- Produces: both routes' responses gain `"index_mode": str` and
  `"repeats": bool`.

- [ ] **Step 1: Write the failing route tests**

```python
# tests/unit/test_api_archive_index_modes.py
def test_rebuild_from_history_drops_the_history_stage_in_archives_mode(
    test_client, admin_headers, repository, test_db, pro_plan
):
    repository.index_mode = "archives"
    test_db.commit()
    response = test_client.post(
        f"/api/repositories/{repository.id}/rebuild",
        json={"from": "history"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["index_mode"] == "archives"
    assert body["repeats"] is False
    from app.database.models import Operation

    kinds = [
        op.kind
        for op in test_db.query(Operation)
        .filter(Operation.id.in_(body["operations"]))
        .all()
    ]
    assert "history_index" not in kinds
    assert "stats" in kinds


def test_rebuild_from_history_still_clears_the_change_rows(
    test_client, admin_headers, repository, test_db, pro_plan
):
    # Spec 6.8: clearing history is an explicit action and stays available.
    ...


def test_rebuild_still_runs_for_an_off_repository(
    test_client, admin_headers, repository, test_db
):
    repository.index_mode = "off"
    test_db.commit()
    response = test_client.post(
        f"/api/repositories/{repository.id}/rebuild",
        json={"from": "stats"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["operations"]
    assert response.json()["repeats"] is False


def test_rebuild_on_a_full_repository_repeats(
    test_client, admin_headers, repository
):
    response = test_client.post(
        f"/api/repositories/{repository.id}/rebuild",
        json={"from": "stats"},
        headers=admin_headers,
    )
    assert response.json()["repeats"] is True


def test_resync_lists_an_off_repository_once(
    test_client, admin_headers, repository, test_db
):
    repository.index_mode = "off"
    test_db.commit()
    response = test_client.post(
        f"/api/repositories/{repository.id}/resync", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["operations"]
    assert response.json()["repeats"] is False
```

Fill in the second test's body by copying the archive and change-row setup
from the existing rebuild tests in `tests/unit/test_api_archive_index.py`
and asserting the `ArchiveChange` rows are gone afterwards. Use whatever
Pro-plan fixture that file already uses in place of `pro_plan`.

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest tests/unit/test_api_archive_index_modes.py -q`
Expected: FAIL, `KeyError: 'index_mode'`.

- [ ] **Step 3: Make `rebuild` mode-aware**

In `rebuild`, replace the plan filter line with both filters and extend the
response. The stage invalidation above it is unchanged: clearing the rows is
the explicit action 6.8 keeps available in every mode.

```python
    mode = index_mode_of(repository)
    if not history:
        kinds = [k for k in kinds if k not in PLAN_GATED_KINDS]
    # Spec 6.8: manual work is not blocked by the mode, but a mode that
    # excludes file history is a standing instruction not to diff this
    # repository, so the history stages go and the listing and the size
    # still run this once.
    kinds = filter_kinds("archives" if mode == "off" else mode, kinds)
    db.commit()
    ops = enqueue_chain(...)
    return {
        "run_id": ops[0].run_id if ops else None,
        "operations": [o.id for o in ops],
        "index_mode": mode,
        # Whether the background chain will keep this stage fresh from now
        # on, or whether this run was the one-off look (spec 6.8).
        "repeats": mode == "full",
    }
```

- [ ] **Step 4: Make `resync` mode-aware**

```python
    repository = _repo(db, current_user, repo_id, role="operator")
    mode = index_mode_of(repository)
    ops = enqueue_reconcile_run(db, repository.id, manual=True)
    return {
        "run_id": ops[0].run_id if ops else None,
        "operations": [o.id for o in ops],
        "index_mode": mode,
        "repeats": mode == "full",
    }
```

and extend the docstring with one sentence: an `off` repository is listed
once here and then goes quiet again.

- [ ] **Step 5: Run them and watch them pass**

Run: `pytest tests/unit/test_api_archive_index_modes.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the archive index suite**

Run: `pytest tests/unit/test_api_archive_index.py -q -p no:randomly`
Expected: PASS. The two response bodies grew two keys; a test that asserts
an exact body needs the two keys added, not the keys removed from the route.

---

## Task 5: The status route and the hub payload carry the mode

**Files:**
- Modify: `app/services/operations/repository_status.py` (`repository_status` at `:524`)
- Modify: `app/api/operations.py` (`HubRepository` at `:137`, the hub route at `:495`)
- Modify: `tests/unit/test_api_archive_index.py` or a new
  `tests/unit/test_repository_status_index_mode.py`, whichever the existing
  status tests live in

**Interfaces:**
- Consumes: `mode_of` (Task 1).
- Produces: `GET /repositories/{id}/status` omits the `index` cell for
  `off`; `HubRepository.index_mode: str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_status_route_omits_the_index_cell_for_an_off_repository(db, repository):
    repository.index_mode = "off"
    payload = repository_status(db, repository, now=utc_now(), pro=True)
    assert "index" not in {cell["cell"] for cell in payload["cells"]}


def test_archives_mode_keeps_the_index_cell(db, repository):
    # The listing and the size still refresh, so the cell still means
    # something (spec 6.8).
    repository.index_mode = "archives"
    payload = repository_status(db, repository, now=utc_now(), pro=True)
    assert "index" in {cell["cell"] for cell in payload["cells"]}


def test_the_hub_row_carries_the_mode(test_client, admin_headers, repository, test_db):
    repository.index_mode = "archives"
    test_db.commit()
    response = test_client.get("/api/operations/repositories", headers=admin_headers)
    row = next(
        r
        for r in response.json()["repositories"]
        if r["repository_id"] == repository.id
    )
    assert row["index_mode"] == "archives"
```

Confirm the hub route's path from `app/api/operations.py` before writing the
third test; the router prefix, not this plan, is the authority.

- [ ] **Step 2: Run them and watch them fail**

Run: `pytest <the two files> -q`
Expected: FAIL on the first and third.

- [ ] **Step 3: Omit the index cell for `off`**

In `repository_status`, beside the mirror rule, which is the same shape of
rule (a category the repository does not have):

```python
    mirror_applies = repository.repository_type == "rclone"
    # Nothing is refreshed for an `off` repository, so an index cell would
    # only ever read as overdue for a state the user chose (spec 6.8).
    index_applies = index_mode_of(repository) != "off"
    cells = []
    for name, spec in CELLS:
        if name == "mirror" and not mirror_applies:
            continue
        if name == "index" and not index_applies:
            continue
```

- [ ] **Step 4: Add the field to the hub payload**

`HubRepository` gains `index_mode: str = "full"`, and the row builder gains
`index_mode=index_mode_of(repo),`. The default keeps a client that is
mid-deploy honest rather than making the field optional.

- [ ] **Step 5: Run them and watch them pass**

Run: `pytest <the two files> -q`
Expected: PASS.

- [ ] **Step 6: Run the status and hub suites**

Run:

```bash
pytest tests/unit/test_repository_last_runs.py tests/unit/test_api_archive_index.py \
  tests/unit/test_api_operations.py -q -p no:randomly
```

Expected: PASS.

---

## Task 6: The hub reads an opted-out repository as a choice

The first of the two UI tasks section 13 gives Opus 5.

**Files:**
- Modify: `frontend/src/types/operations.ts`
- Modify: `frontend/src/components/background-work/hubRows.ts`
- Modify: `frontend/src/components/background-work/RepositoryHubRow.tsx`
- Modify: `frontend/src/components/background-work/storyFixtures.ts`
- Modify: `frontend/src/components/background-work/RepositoryHubRow.stories.tsx`
- Modify: `frontend/src/components/background-work/__tests__/hubRows.test.ts`
- Modify: `frontend/src/components/background-work/__tests__/RepositoryHubRow.test.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

**Interfaces:**
- Consumes: `HubRepository.index_mode` (Task 5).
- Produces: `export type IndexMode = 'full' | 'archives' | 'off'` in
  `types/operations.ts`, imported by Tasks 7, 8 and 9.

- [ ] **Step 1: Write the failing `hubRows` tests**

```ts
// in __tests__/hubRows.test.ts
it('does not count an off repository as stale', () => {
  const rows = [row({ sync_state: 'stale', index_mode: 'off' })]
  expect(attentionCounts(rows).stale).toBe(0)
  expect(attentionCounts(rows).total).toBe(0)
})

it('does not count history failures on a repository that does not index history', () => {
  const rows = [row({ index_mode: 'archives', history: { ...summary, failed: 3 } })]
  expect(attentionCounts(rows).history).toBe(0)
})

it('still counts a stale archives-mode repository', () => {
  // `archives` keeps the listing fresh, so a stale listing is still a problem.
  const rows = [row({ sync_state: 'stale', index_mode: 'archives' })]
  expect(attentionCounts(rows).stale).toBe(1)
})

it('still shows running work on an off repository', () => {
  // A manual one-off run is exactly the case (spec 6.8).
  const rows = [row({ index_mode: 'off' }, activeTrack)]
  expect(attentionCounts(rows).running).toBe(1)
})
```

using the file's existing `row` helper (add the `index_mode` field to it,
defaulting to `'full'`, so no existing case changes).

- [ ] **Step 2: Run them and watch them fail**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/hubRows.test.ts`
Expected: FAIL on the first two.

- [ ] **Step 3: Make `reasonsFor` mode-aware**

```ts
function reasonsFor(row: HubRow): AttentionReason[] {
  const { repository, track } = row
  if (!repository) return []
  const mode = repository.index_mode ?? 'full'
  const reasons: AttentionReason[] = []
  // A repository nobody indexes is not stale, it is opted out (spec 6.8).
  // Its rows are kept and shown, they are simply not counted as a problem.
  if (mode !== 'off') {
    if (repository.sync_state === 'stale') reasons.push('stale')
    if (repository.sync_state === 'never') reasons.push('never')
  }
  if (mode === 'full' && (repository.history.failed > 0 || repository.history.truncated > 0))
    reasons.push('history')
  if (trackIsActive(track)) reasons.push('running')
  return reasons
}
```

- [ ] **Step 4: Run them and watch them pass**

Run: `npx vitest run src/components/background-work/__tests__/hubRows.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing row tests**

```tsx
// in __tests__/RepositoryHubRow.test.tsx
it('reads "Archives only" in place of the history cell', () => {
  render(<RepositoryHubRow {...props({ index_mode: 'archives' })} />)
  expect(screen.getByText('Archives only')).toBeInTheDocument()
})

it('reads "Not indexed" across the track for an off repository', () => {
  render(<RepositoryHubRow {...props({ index_mode: 'off' })} />)
  expect(screen.getByText('Not indexed')).toBeInTheDocument()
  expect(screen.queryByTestId('stage-track')).not.toBeInTheDocument()
})

it('shows the track for an off repository while a manual run is going', () => {
  render(<RepositoryHubRow {...props({ index_mode: 'off' }, activeTrack)} />)
  expect(screen.getByTestId('stage-track')).toBeInTheDocument()
})
```

matching the file's existing render helper and its i18n setup (the other
cases show whether it asserts on English text or on keys).

- [ ] **Step 6: Run them and watch them fail**

Run: `npx vitest run src/components/background-work/__tests__/RepositoryHubRow.test.tsx`
Expected: FAIL, the strings are not rendered.

- [ ] **Step 7: Render the two muted states**

`HistoryCell` takes the mode and answers first, before the plan chip: a
repository that does not index history has no Pro upsell to show, because
the plan is not what is stopping it.

```tsx
function HistoryCell({ repository, historyAvailable, totalHistoryRows }: {...}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const { history, archives } = repository
  const mode = repository.index_mode ?? 'full'

  // Mode before plan: an upgrade would not start indexing this repository,
  // so the Pro chip would be a false promise (spec 6.8).
  if (mode !== 'full') {
    return (
      <Cell
        muted
        primary={t(
          mode === 'archives'
            ? 'operations.background.hub.modeArchives'
            : 'operations.background.hub.modeOff'
        )}
      />
    )
  }
  if (!historyAvailable) {
    ...unchanged
```

and in the row body, the whole track is replaced for `off` when nothing is
running, so the four empty columns do not read as work that failed to start:

```tsx
        {repository && (repository.index_mode ?? 'full') === 'off' && !trackIsActive(track) ? (
          <Box sx={{ gridColumn: '1 / -1' }}>
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              {t('operations.background.hub.trackOff')}
            </Typography>
          </Box>
        ) : (
          ...the existing StageTrack block
        )}
```

Read the existing JSX around `StageTrack` before editing and keep its grid
placement; the snippet above names the condition, not the final markup.

- [ ] **Step 8: Run them and watch them pass**

Run: `npx vitest run src/components/background-work/`
Expected: PASS.

- [ ] **Step 9: Add the keys to all four locales**

`operations.background.hub.modeArchives` ("Archives only"),
`operations.background.hub.modeOff` ("Not indexed"),
`operations.background.hub.trackOff` ("Background work is off for this
repository"). Translate all three into German, Spanish and Italian, matching
the tone of the keys already in that block.

- [ ] **Step 10: Add the stories**

`RepositoryHubRow.stories.tsx` gains an `ArchivesOnly` and a `NotIndexed`
story off the existing fixture with `index_mode` set, and `storyFixtures.ts`
gains `index_mode: 'full'` on its hub repository fixture so the type stays
satisfied.

- [ ] **Step 11: Verify visually**

Follow the `verify-ui-visually` rule: render Storybook (fnm v24, the
darwin-arm64 bindings copied into the worktree if this runs in one) and
screenshot both new stories in light and dark before the task is called
done. A muted state that disappears into the background in dark mode is the
failure to look for.

---

## Task 7: The repository card says why its last runs are empty

**Files:**
- Modify: `frontend/src/components/RepositoryCard.tsx` (`:250` to `:271`)
- Modify: `frontend/src/types/index.ts`, `frontend/src/pages/repositories-page/types.ts`
- Modify: `frontend/src/components/__tests__/RepositoryCard.test.tsx` (or add one)
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

- [ ] **Step 1: Write the failing test**

```tsx
it('says background work is off instead of Never on both entries', () => {
  render(<RepositoryCard {...props({ index_mode: 'off', last_prune: null, last_index: null })} />)
  expect(screen.getAllByText('Background work is off')).toHaveLength(2)
})

it('is unchanged for a full repository', () => {
  render(<RepositoryCard {...props({ index_mode: 'full', last_prune: null, last_index: null })} />)
  expect(screen.getAllByText('Never')).toHaveLength(2)
})
```

- [ ] **Step 2: Run it and watch it fail**

Run: `npx vitest run src/components/__tests__/RepositoryCard.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Add `index_mode` to the two `Repository` types**

```ts
  index_mode?: IndexMode
```

beside `last_prune` and `last_index` in both files, importing `IndexMode`
from `types/operations`.

- [ ] **Step 4: Render the message**

```tsx
  // Neither value can move while background work is off: `Last index` has
  // nothing running, and `Last prune` is read from archive listings that no
  // longer refresh (spec 6.8, 10.2). "Never" would be a wrong answer.
  const backgroundOff = repository.index_mode === 'off'
  const lastRunValue = (value?: string | null) =>
    backgroundOff
      ? t('repositoryCard.backgroundWorkOff')
      : value
        ? formatDateShort(value)
        : t('common.never')
```

used for both entries, with the tooltip suppressed when `backgroundOff`. The
`!== undefined` guard on each entry stays exactly as it is: a backend that
predates the fields still shows no entry at all.

The spec's copy links to the setting. The card's metadata row renders plain
values, so the link belongs in the tooltip rather than in the row: set the
tooltip to `t('repositoryCard.backgroundWorkOffHint')`, which names the
Advanced step of repository settings. Turning a metadata value into a link
is a bigger change to that row than this phase should make; see Open
questions.

- [ ] **Step 5: Run it and watch it pass**

Run: `npx vitest run src/components/__tests__/RepositoryCard.test.tsx`
Expected: PASS.

- [ ] **Step 6: Keys, story, screenshot**

`repositoryCard.backgroundWorkOff` and
`repositoryCard.backgroundWorkOffHint` in all four locales; a
`BackgroundWorkOff` story; light and dark screenshots.

---

## Task 8: The setting itself

**Files:**
- Create: `frontend/src/components/repositories/IndexModeSettings.tsx`
- Create: `frontend/src/components/repositories/IndexModeSettings.stories.tsx`
- Create: `frontend/src/components/repositories/__tests__/IndexModeSettings.test.tsx`
- Modify: `frontend/src/components/wizard/WizardStepRepositoryAdvanced.tsx`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

**Interfaces:**
- Produces:

```ts
export interface IndexModeSettingsProps {
  mode: IndexMode
  excludes: string[]
  onModeChange: (mode: IndexMode) => void
  onExcludesChange: (excludes: string[]) => void
}
```

- [ ] **Step 1: Write the failing component test**

```tsx
it('offers the three modes with their cost line', () => {...})

it('reports a mode change', async () => {
  const onModeChange = vi.fn()
  render(<IndexModeSettings mode="full" excludes={[]} onModeChange={onModeChange} onExcludesChange={vi.fn()} />)
  await userEvent.click(screen.getByLabelText('Background indexing'))
  await userEvent.click(screen.getByText('Archives only'))
  expect(onModeChange).toHaveBeenCalledWith('archives')
})

it('parses one pattern per line', async () => {
  const onExcludesChange = vi.fn()
  render(<IndexModeSettings mode="full" excludes={['**/.cache/**']} onModeChange={vi.fn()} onExcludesChange={onExcludesChange} />)
  const field = screen.getByLabelText('Paths to skip')
  await userEvent.clear(field)
  await userEvent.type(field, '**/a/**\n\n  **/b/**  ')
  expect(onExcludesChange).toHaveBeenLastCalledWith(['**/a/**', '**/b/**'])
})

it('disables the exclude list when the mode does not index history', () => {
  render(<IndexModeSettings mode="archives" excludes={[]} onModeChange={vi.fn()} onExcludesChange={vi.fn()} />)
  expect(screen.getByLabelText('Paths to skip')).toBeDisabled()
})
```

- [ ] **Step 2: Run them and watch them fail**

Run: `npx vitest run src/components/repositories/__tests__/IndexModeSettings.test.tsx`
Expected: FAIL, the module does not exist.

- [ ] **Step 3: Write the component**

A `RichSelect` with the three modes, each with the one line of cost from
6.8, and a multiline `TextField` for the 6.7 patterns, one per line, trimmed
and emptied of blanks on the way out. The exclude list is disabled with a
helper line when the mode does not index history, since the patterns would
have nothing to trim. Keep it small: the two controls and their helper text,
no fetching, no save button. The wizard owns the state and the save, as it
does for every other field on that step.

```tsx
const MODES: IndexMode[] = ['full', 'archives', 'off']

export default function IndexModeSettings({
  mode,
  excludes,
  onModeChange,
  onExcludesChange,
}: IndexModeSettingsProps) {
  const { t } = useTranslation()
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <RichSelect
        label={t('repositoryIndexMode.label')}
        value={mode}
        onChange={(value) => onModeChange(value as IndexMode)}
        options={MODES.map((value) => ({
          value,
          primary: t(`repositoryIndexMode.mode.${value}.title`),
          secondary: t(`repositoryIndexMode.mode.${value}.cost`),
        }))}
      />
      <TextField
        label={t('repositoryIndexMode.excludes')}
        value={excludes.join('\n')}
        onChange={(event) =>
          onExcludesChange(
            event.target.value
              .split('\n')
              .map((line) => line.trim())
              .filter(Boolean)
          )
        }
        multiline
        minRows={3}
        disabled={mode !== 'full'}
        helperText={t(
          mode === 'full'
            ? 'repositoryIndexMode.excludesHelp'
            : 'repositoryIndexMode.excludesInactive'
        )}
      />
    </Box>
  )
}
```

The copy for the three modes comes from 6.8 and says the cost, not the
mechanism: `full` keeps everything current; `archives` keeps the archive
list, heatmap, health and last-backup age current and stops diffing files;
`off` refreshes nothing, and the archive list will no longer refresh.

- [ ] **Step 4: Run them and watch them pass**

Run: `npx vitest run src/components/repositories/`
Expected: PASS, 4 tests.

- [ ] **Step 5: Wire it into the advanced step**

`RepositoryAdvancedStepData` gains `indexMode: IndexMode` and
`historyIndexExcludes: string[]`; `WizardStepRepositoryAdvanced` renders
`IndexModeSettings` above `AdvancedRepositoryOptions`, but only in edit mode
(`repositoryId != null`), because 6.8 makes the mode a setting for a
repository that exists and `PUT` is the only route that accepts it.
`RepositoryWizard` seeds both from `repository.index_mode ?? 'full'` and
`repository.history_index_excludes ?? []` in its edit initialiser (near
`:474`) and sends `index_mode` and `history_index_excludes` in its update
payload (near `:901`).

- [ ] **Step 6: Run the wizard tests**

Run: `npx vitest run src/components/__tests__/RepositoryWizard.test.tsx`
Expected: PASS. If a case asserts the exact update payload, add the two
fields to it.

- [ ] **Step 7: Story, keys, screenshot**

A story per mode; the `repositoryIndexMode.*` keys in all four locales;
light and dark screenshots of the step.

---

## Task 9: The archive route explains itself

**Files:**
- Create: `frontend/src/hooks/useIndexMode.ts`
- Create: `frontend/src/components/archives/IndexModeGate.tsx`
- Create: `frontend/src/components/archives/IndexModeGate.stories.tsx`
- Create: `frontend/src/components/archives/__tests__/IndexModeGate.test.tsx`
- Modify: `frontend/src/components/archives/ArchiveChangesTab.tsx`
- Modify: `frontend/src/components/archives/ArchiveFileDetailsPane.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

- [ ] **Step 1: Write the failing gate tests**

```tsx
it('renders its children when the repository indexes history', () => {...})

it('explains the mode instead of the content', () => {
  render(<IndexModeGate mode="archives"><div>changes</div></IndexModeGate>)
  expect(screen.queryByText('changes')).not.toBeInTheDocument()
  expect(screen.getByText(/not indexed/i)).toBeInTheDocument()
})

it('links to the setting', () => {
  render(<IndexModeGate mode="off"><div>changes</div></IndexModeGate>)
  expect(screen.getByRole('link')).toHaveAttribute('href', expect.stringContaining('/repositories'))
})
```

- [ ] **Step 2: Run them and watch them fail**

Run: `npx vitest run src/components/archives/__tests__/IndexModeGate.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the hook and the gate**

```ts
// frontend/src/hooks/useIndexMode.ts
// The repositories list is already fetched by every page that reaches these
// surfaces, so this reads the mode off the shared query rather than adding a
// request per panel. An unknown repository reads as `full`, which is what
// every install had before spec 6.8.
export function useIndexMode(repositoryId: number): IndexMode {
  const { data } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
    staleTime: 60_000,
  })
  const repositories: Repository[] = data?.data?.repositories ?? []
  return repositories.find((r) => r.id === repositoryId)?.index_mode ?? 'full'
}
```

Copy the `staleTime` and any `select` the other callers of this query key
use (`pages/ArchiveDetail.tsx:105`), so this hook shares their cache entry
rather than fighting it.

The gate renders an `EmptyStateCard`-style panel in the same slot the Pro
upsell uses, saying which mode is set, that the rows already stored are kept
and simply not updated, and linking to the repository's settings.

- [ ] **Step 4: Run them and watch them pass**

Run: `npx vitest run src/components/archives/__tests__/IndexModeGate.test.tsx`
Expected: PASS.

- [ ] **Step 5: Put the gate inside the plan gate**

Spec 6.8: plan first, then mode, never both. `PlanGate` already answers
first when the plan is Community, so nesting is the whole implementation:

```tsx
export default function ArchiveChangesTab(props: ArchiveChangesTabProps) {
  const { can } = usePlan()
  const mode = useIndexMode(props.repositoryId)
  return (
    <PlanGate
      feature="archive_history"
      preview={<ArchiveChangesPreview />}
      surface="archive_detail"
      operation="view_changes"
    >
      {can('archive_history') ? (
        <IndexModeGate mode={mode}>
          <ArchiveChangesTabContent {...props} />
        </IndexModeGate>
      ) : null}
    </PlanGate>
  )
}
```

and the same shape in `ArchiveFileDetailsPane` around `FileHistoryPanel`,
where the panel is already wrapped in a `disabled` `PlanGate`; put the mode
gate around the `FileHistoryPanel` element there so the Files tab keeps its
layout.

- [ ] **Step 6: Run the archives suite**

Run: `npx vitest run src/components/archives/`
Expected: PASS.

- [ ] **Step 7: Keys, story, screenshot**

`archives.indexMode.*` keys in all four locales; a story per mode; light and
dark screenshots of both surfaces.

---

## Task 10: Documentation

**Files:**
- Modify: `docs/api.md` (the "Archive index and history" table at `:263`,
  and the repository payload description)
- Modify: `docs/navigation.md`
- Modify: `docs/architecture/job-system.md`
- Modify: `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md` (19.1)

- [ ] **Step 1: `docs/api.md`**

Add `index_mode` to the repository payload description and a row to the
archive table noting that `/rebuild` and `/resync` answer with `index_mode`
and `repeats`, and that a non-`full` mode drops the history stages from
either run. State the `PUT /api/repositories/{id}` field, its three values,
and the two side effects (queued index work cancelled on leaving `full`, one
catch-up run on returning to it).

- [ ] **Step 2: `docs/architecture/job-system.md`**

One short section under the follow-up chain: the mode is the second gate
next to the plan, applied in `chain_for` and `reconcile_kinds`, and a stage
a mode excludes is never created. Say that manual work overrides `off` once
and never re-enables history.

- [ ] **Step 3: `docs/navigation.md`**

Name where the setting lives: repository settings, Advanced step, beside the
history exclude list.

- [ ] **Step 4: The spec's progress table**

Set phase 10 to `in review` with the plan file, the branch, and Notes
covering the model actually used, the Open questions and how they were
answered at G1, and anything that deviated from this plan.

---

## Verification (before gate G2)

Run `superpowers:verification-before-completion` and paste the real output
of each of these, not a summary:

- [ ] `ruff check app tests && ruff format --check app tests`
- [ ] `python3 -m pytest tests/unit -q -p no:randomly` (expect the phase 9
      baseline of 3969 passed, 14 skipped, plus this phase's new tests; the
      14 skips are pre-existing)
- [ ] `python3 -m pytest tests/integration -q` (one pre-existing failure,
      `test_create_repository_invalid_path`, is expected; confirm it fails
      on a clean checkout too before accepting it)
- [ ] `cd frontend && npm run lint && npx tsc --noEmit && npx vitest run`
- [ ] The alembic head is a single revision: run the head-detecting script
      from Task 1 Step 8 and confirm exactly one entry.
- [ ] A live upgrade and downgrade of the new migration against a scratch
      database.
- [ ] `grep -rn "—" app frontend/src docs/api.md docs/navigation.md` returns
      nothing new (no em dashes).
- [ ] Every new i18n key exists in all four locale files: for each key,
      `grep -c "<key>" frontend/src/locales/*.json` returns 1 in each.
- [ ] Storybook renders, and the new and changed stories are screenshotted
      in light and dark.

## Self-review

Spec coverage, section 6.8 line by line:

| 6.8 requirement | Task |
| --- | --- |
| `index_mode` column, default `full` | 1 |
| The three-mode table | 1 (the table), 2 (applied) |
| Applied in `chain_for` and `reconcile_kinds` only | 2 |
| Reconcile tick skips `off` entirely | 2 |
| Manual rebuild and archive_sync run once | 4 |
| The response notes it will not repeat | 4 |
| Leaving `full` cancels queued index work | 3 |
| A running index is left to finish (implementer's call) | 3 |
| Rows kept, shown as stale, never deleted | 3 (no deletion anywhere), 6 |
| `rebuild from=history` still clears rows in `archives` mode | 4 |
| Returning to `full` enqueues one catch-up run | 3 |
| Agent repositories and `off` | Open question 1 |
| Settings control beside the 6.7 exclude list | 8 |
| Hub row muted states | 6 |
| Hub summary excludes them from stale and failed counts | 6 |
| Status omits the history category for `archives`, `off` message on the card | 5, 7 |
| Changes tab and file history panel panel, plan first then mode | 9 |
| `GET /repositories/{id}` and the hub payload carry `index_mode` | 1, 5 |
| `PUT /repositories/{id}` accepts it with validation | 1 |
| Documentation | 10 |

Type consistency: `IndexMode` is defined once in
`frontend/src/types/operations.ts` and imported by `types/index.ts`,
`pages/repositories-page/types.ts`, `IndexModeSettings`, `IndexModeGate`,
`useIndexMode` and the hub components. On the backend the mode is a plain
`str` everywhere, validated by the `Literal` on `RepositoryUpdate` and
normalised by `index_mode.normalize`. `filter_kinds` and `mode_of` keep
those names in every task that calls them.

Placeholders: two test bodies are deliberately left to be filled from the
existing fixtures they must match
(`test_rebuild_from_history_still_clears_the_change_rows`, and the fixture
names in `tests/unit/test_api_repository_index_mode.py`). Both name the file
to copy from. Everything else carries its code.

## Open questions

Each has a default. Approving the plan at G1 without comment takes every
default.

1. **`off` on a managed-agent repository.** 6.8 says agent repositories
   accept `full` and `archives` only, with `off` a 422, "until the agent
   kinds migrate in phase 5, since the agent's own stats writer would keep
   running regardless". Phase 5 is done and phase 9 deleted
   `update_repository_stats` and `BorgRouter.update_stats`; the agent path
   now runs only inside the `stats` executor
   (`app/services/operations/executors/index.py:495`), which `off` does not
   enqueue. The condition the spec attached to the restriction has been
   met. **Default: accept all three modes for agent repositories, no 422**,
   and record the resolution in the spec's Appendix B. The alternative is to
   implement the 422 as literally written.
2. **A running history index when the mode changes.** 6.8 leaves this to
   the plan. **Default: let it finish.** The lane time is already spent, the
   rows it writes are kept in every mode, and cancelling it would leave a
   half-indexed archive that the next `full` run has to redo. The
   alternative is a cooperative cancel through `request_cancel`.
3. **`rebuild` on a non-`full` repository.** 6.8 says manual work is not
   gated, and separately that `from=history` in `archives` mode "enqueues
   nothing after `archive_sync` and `stats`". **Default: the run happens,
   the invalidation happens, and the history stages are dropped** (Task 4),
   so a mode that says "do not diff this repository" is not overridden by a
   button, while the listing and the size still refresh once. The
   alternative is to run the history stage anyway on an explicit rebuild.
4. **Where the setting lives.** **Default: the repository wizard's Advanced
   step, in edit mode only**, since `PUT` is the only route 6.8 gives the
   field and the mode is a decision about a repository that already exists.
   The alternative is to show it at creation too and add `index_mode` to the
   create schema.
5. **The 6.7 exclude list when the mode is not `full`.** **Default: shown
   but disabled, with a helper line saying it applies to file history**, so
   the patterns a user typed are not silently discarded and the reason is on
   screen. The alternative is to hide it.
6. **The card's link to the setting.** 6.8 wants the `off` message to link
   to the setting. The card's metadata row renders plain label and value
   pairs. **Default: the message is plain text and the tooltip says where the
   setting is** (Task 7), leaving the row's structure alone. The alternative
   is to make metadata values linkable, which is a change to every card.
7. **`archives` mode and the hub's `stale` count.** 6.8 says the summary
   excludes opted-out repositories from its stale and failed counts.
   **Default: `off` is excluded from both; `archives` is excluded from the
   history count only** (Task 6), because `archives` mode still promises a
   fresh archive list, so a stale listing there is a real problem. The
   alternative is to exclude `archives` from everything.
8. **The status route's `index` cell.** **Default: omitted for `off`,
   kept for `archives`** (Task 5), on the same reasoning as 7. The
   alternative is to keep the cell and let it report a null `overdue`.
