# Agent upgrades phase 1: version model and visibility

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show which managed agents are running an out-of-date agent version,
and add the endpoint that pins one to a specific version. The pin UI ships in
phase 3, alongside the upgrade action it modifies.

**Architecture:** A pure comparison helper turns three inputs (the version an
agent reported, the version it is pinned to, the version this server serves)
into one status string. The API exposes that status per agent plus a new pin
endpoint. The UI renders the status as a chip on each agent card and counts
out-of-date agents in an informational banner.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic-style numbered migrations, React,
MUI, i18next, Storybook, pytest, vitest.

**Spec:** `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`

## Global Constraints

- No em dashes in UI copy, i18n strings, code comments, or commit messages.
- Every new i18n key must be added to all four locales:
  `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`. The
  `frontend-locale-check` pre-push hook fails otherwise.
- No heavy left accent borders on cards, panels, alerts, or status surfaces
  (`AGENTS.md`, UI Preferences).
- New or changed UI ships a Storybook story demonstrating the changed state.
- Do not commit generated PNGs under `frontend/storybook-snapshots/` or
  `frontend/argos-screenshots/`.
- New UI components go in `frontend/src/pages/managed-agents/`, not inline in
  `ManagedAgents.tsx`, which is already over 2200 lines.
- **Phase 1 adds no upgrade action.** The banner is informational. Do not add
  an "Upgrade all" button; that is phase 4 and a dead button is worse than no
  button.

---

### Task 1: Version comparison helper

Pure functions, no database, no FastAPI. This is the whole decision table from
spec section 4 in one testable place.

**Files:**
- Create: `app/core/agent_versions.py`
- Test: `tests/unit/test_agent_version_status.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `parse_agent_version(value: str | None) -> tuple[int, ...] | None`
  - `compute_agent_upgrade_status(*, reported: str | None, desired: str | None, available: str | None) -> str`
  - `UPGRADE_STATUSES: frozenset[str]` containing
    `{"up_to_date", "outdated", "ahead", "pinned", "unknown"}`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_agent_version_status.py`:

```python
import pytest

from app.core.agent_versions import (
    UPGRADE_STATUSES,
    compute_agent_upgrade_status,
    parse_agent_version,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0.1.3", (0, 1, 3)),
        ("1.0", (1, 0)),
        ("2", (2,)),
        ("0.1.3a1", None),
        ("", None),
        (None, None),
        ("1.-2.3", None),
        ("1..3", None),
    ],
)
def test_parse_agent_version(value, expected):
    assert parse_agent_version(value) == expected


@pytest.mark.parametrize(
    "reported,desired,available,expected",
    [
        # Tracking the server.
        ("0.1.3", None, "0.1.3", "up_to_date"),
        ("0.1.2", None, "0.1.3", "outdated"),
        ("0.2.0", None, "0.1.3", "ahead"),
        # Pinned.
        ("0.1.2", "0.1.2", "0.1.3", "pinned"),
        ("0.1.1", "0.1.2", "0.1.3", "outdated"),
        ("0.1.3", "0.1.2", "0.1.3", "ahead"),
        # Unknown inputs.
        (None, None, "0.1.3", "unknown"),
        ("0.1.3", None, None, "unknown"),
        (None, None, None, "unknown"),
        ("0.1.3a1", None, "0.1.3", "unknown"),
        ("0.1.3", None, "0.1.3a1", "unknown"),
        # Equal after padding but written differently: not the served string,
        # so it is not current. Reinstalling is harmless.
        ("0.1", None, "0.1.0", "outdated"),
    ],
)
def test_compute_agent_upgrade_status(reported, desired, available, expected):
    assert (
        compute_agent_upgrade_status(
            reported=reported, desired=desired, available=available
        )
        == expected
    )
    assert expected in UPGRADE_STATUSES


def test_exact_string_match_wins_over_parsing():
    """An unparseable version that exactly matches its target is current, not
    unknown. The endpoint is demonstrably running the wheel we serve."""
    assert (
        compute_agent_upgrade_status(
            reported="0.1.3a1", desired=None, available="0.1.3a1"
        )
        == "up_to_date"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_agent_version_status.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.agent_versions'`

- [ ] **Step 3: Write minimal implementation**

Create `app/core/agent_versions.py`:

```python
"""Compare the agent version an endpoint reports against the version it should
be running.

Three inputs decide the answer, and two are not enough (see the spec at
docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md section 4):

- reported:  what the endpoint last told us it runs
- desired:   what this endpoint is pinned to, or None to track the server
- available: the agent wheel this server image serves

Exact string equality is the source of truth for "current": the question is
whether the endpoint runs the wheel we serve, not whether its version number
sorts high enough. Ordering is used only to separate "behind" from "ahead of
the server", which happens when a server is rolled back. Anything that does
not parse as dotted integers is reported as unknown rather than guessed at.
"""

from __future__ import annotations

from typing import Optional

UP_TO_DATE = "up_to_date"
OUTDATED = "outdated"
AHEAD = "ahead"
PINNED = "pinned"
UNKNOWN = "unknown"

UPGRADE_STATUSES = frozenset({UP_TO_DATE, OUTDATED, AHEAD, PINNED, UNKNOWN})


def parse_agent_version(value: Optional[str]) -> Optional[tuple[int, ...]]:
    """Dotted integer components of ``value``, or None if any component is not
    a plain non-negative integer. Deliberately strict: a pre-release such as
    "0.1.3a1" returns None so the caller reports unknown instead of ordering it
    wrongly."""
    if not value:
        return None
    parts = value.split(".")
    components: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        components.append(int(part))
    return tuple(components)


def _padded(
    left: tuple[int, ...], right: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    width = max(len(left), len(right))
    return (
        left + (0,) * (width - len(left)),
        right + (0,) * (width - len(right)),
    )


def compute_agent_upgrade_status(
    *,
    reported: Optional[str],
    desired: Optional[str],
    available: Optional[str],
) -> str:
    """One of UPGRADE_STATUSES for a single agent."""
    target = desired or available
    if not reported or not target:
        return UNKNOWN

    if reported == target:
        # Surface the pin so an operator can see why this endpoint is not
        # moving with the fleet.
        return PINNED if desired else UP_TO_DATE

    reported_parts = parse_agent_version(reported)
    target_parts = parse_agent_version(target)
    if reported_parts is None or target_parts is None:
        return UNKNOWN

    left, right = _padded(reported_parts, target_parts)
    if left > right:
        return AHEAD
    # Equal tuples with different strings (for example "0.1" against "0.1.0")
    # land here: the endpoint is not running the string we serve, so it is
    # treated as behind. Reinstalling it is harmless.
    return OUTDATED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_agent_version_status.py -v`
Expected: PASS, 20 passed

- [ ] **Step 5: Commit**

```bash
git add app/core/agent_versions.py tests/unit/test_agent_version_status.py
git commit -m "feat(agents): add agent version comparison helper"
```

---

### Task 2: Database columns

**Files:**
- Create: `app/database/migrations/129_add_agent_upgrade_tracking.py`
- Modify: `app/database/models.py` (`AgentMachine`, after `agent_version`)
- Test: `tests/unit/test_agent_upgrade_columns.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `AgentMachine.desired_agent_version`, `.desired_borg_version`,
  `.upgrade_state`, `.upgrade_requested_at`, `.upgrade_target_version`,
  `.upgrade_error`. Later phases write `upgrade_state` and friends; phase 1
  only reads them.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_agent_upgrade_columns.py`:

```python
from app.database.models import AgentMachine


def test_agent_machine_has_upgrade_tracking_columns(test_db):
    agent = AgentMachine(
        name="node-1",
        agent_id="agt_test_upgrade_columns",
        token_hash="x",
        token_prefix="agt_test",
        status="online",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    assert agent.desired_agent_version is None
    assert agent.desired_borg_version is None
    assert agent.upgrade_state is None
    assert agent.upgrade_requested_at is None
    assert agent.upgrade_target_version is None
    assert agent.upgrade_error is None

    agent.desired_agent_version = "0.1.2"
    agent.desired_borg_version = "2"
    test_db.commit()
    test_db.refresh(agent)
    assert agent.desired_agent_version == "0.1.2"
    assert agent.desired_borg_version == "2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_agent_upgrade_columns.py -v`
Expected: FAIL with `AttributeError` on `desired_agent_version`

- [ ] **Step 3: Write minimal implementation**

In `app/database/models.py`, inside `class AgentMachine`, immediately after the
`agent_version` column, add:

```python
    # Version an operator pinned this endpoint to. NULL means "track whatever
    # this server serves", which is the default and the normal case.
    desired_agent_version = Column(String, nullable=True)
    # Borg major version this endpoint should run ("1" or "2"). NULL means
    # leave whatever is installed alone.
    desired_borg_version = Column(String, nullable=True)
    # Set while a remote upgrade is in flight. The agent is killed by the
    # upgrade it performs, so the server owns the outcome (spec section 7.1).
    upgrade_state = Column(String, nullable=True)
    upgrade_requested_at = Column(DateTime, nullable=True)
    upgrade_target_version = Column(String, nullable=True)
    upgrade_error = Column(Text, nullable=True)
```

Create `app/database/migrations/129_add_agent_upgrade_tracking.py`:

```python
"""Track the agent version each endpoint should run, and in-flight upgrades.

Purely additive and idempotent: every column is nullable, NULL for every
existing row, and added only if missing. Mirrors migration 127.
"""

from sqlalchemy import text

_COLUMNS = (
    ("desired_agent_version", "VARCHAR"),
    ("desired_borg_version", "VARCHAR"),
    ("upgrade_state", "VARCHAR"),
    ("upgrade_requested_at", "DATETIME"),
    ("upgrade_target_version", "VARCHAR"),
    ("upgrade_error", "TEXT"),
)


def _columns(connection, table):
    return connection.execute(text(f"PRAGMA table_info({table})")).fetchall()


def _has_table(connection, table):
    return bool(_columns(connection, table))


def _add_column_if_missing(connection, table, column, ddl_type):
    names = {row[1] for row in _columns(connection, table)}
    if column not in names:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def upgrade(connection):
    if not _has_table(connection, "agent_machines"):
        return
    for column, ddl_type in _COLUMNS:
        _add_column_if_missing(connection, "agent_machines", column, ddl_type)


def downgrade(connection):
    # No downgrade: every column is nullable and additive.
    print("✓ Downgrade skipped for migration 129 (additive, non-destructive)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_agent_upgrade_columns.py -v`
Expected: PASS

Then confirm nothing else broke:
Run: `python -m pytest tests/unit/test_api_managed_machines.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/database/models.py app/database/migrations/129_add_agent_upgrade_tracking.py tests/unit/test_agent_upgrade_columns.py
git commit -m "feat(agents): add agent upgrade tracking columns"
```

---

### Task 3: Expose upgrade status on the agents API

**Files:**
- Modify: `app/api/managed_machines.py` (`AgentMachineResponse` at line 100,
  `list_agent_machines` at line 470)
- Test: `tests/unit/test_api_managed_machines.py`

**Interfaces:**
- Consumes: `compute_agent_upgrade_status` from Task 1; the columns from
  Task 2; `agent_package_version()` from `app.api.agent_installer`.
- Produces: `_agent_machine_response(agent, *, available) -> AgentMachineResponse`,
  used by `list_agent_machines` and by the pin endpoint in Task 4.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_api_managed_machines.py`:

```python
def test_list_agents_reports_upgrade_status(client, test_db, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    behind = AgentMachine(
        name="behind",
        agent_id="agt_behind",
        token_hash="x",
        token_prefix="agt_b",
        status="online",
        agent_version="0.1.2",
        capabilities=["backup.create"],
    )
    current = AgentMachine(
        name="current",
        agent_id="agt_current",
        token_hash="x",
        token_prefix="agt_c",
        status="online",
        agent_version="0.1.3",
        capabilities=["backup.create", "self_upgrade"],
    )
    test_db.add_all([behind, current])
    test_db.commit()

    response = client.get("/api/managed-machines/agents", headers=admin_headers)
    assert response.status_code == 200
    by_name = {row["name"]: row for row in response.json()}

    assert by_name["behind"]["upgrade_status"] == "outdated"
    assert by_name["behind"]["available_agent_version"] == "0.1.3"
    assert by_name["behind"]["self_upgrade_supported"] is False

    assert by_name["current"]["upgrade_status"] == "up_to_date"
    assert by_name["current"]["self_upgrade_supported"] is True


def test_list_agents_respects_pin(client, test_db, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    agent = AgentMachine(
        name="pinned",
        agent_id="agt_pinned",
        token_hash="x",
        token_prefix="agt_p",
        status="online",
        agent_version="0.1.2",
        desired_agent_version="0.1.2",
    )
    test_db.add(agent)
    test_db.commit()

    response = client.get("/api/managed-machines/agents", headers=admin_headers)
    assert response.status_code == 200
    row = next(r for r in response.json() if r["name"] == "pinned")
    assert row["upgrade_status"] == "pinned"
    assert row["desired_agent_version"] == "0.1.2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_api_managed_machines.py -k upgrade_status -v`
Expected: FAIL with `KeyError: 'upgrade_status'`

- [ ] **Step 3: Write minimal implementation**

In `app/api/managed_machines.py`, add imports near the existing ones:

```python
from app.api.agent_installer import agent_package_version
from app.core.agent_versions import compute_agent_upgrade_status
```

Add these fields to `AgentMachineResponse`, after `agent_version`:

```python
    desired_agent_version: Optional[str] = None
    desired_borg_version: Optional[str] = None
    available_agent_version: Optional[str] = None
    upgrade_status: str = "unknown"
    self_upgrade_supported: bool = False
    upgrade_state: Optional[str] = None
    upgrade_requested_at: Optional[datetime] = None
    upgrade_error: Optional[str] = None
```

Add this helper immediately above `list_agent_machines`:

```python
def _agent_machine_response(
    agent: AgentMachine, *, available: Optional[str]
) -> AgentMachineResponse:
    """Serialize one agent with its computed upgrade status.

    ``available`` is passed in rather than resolved here so a list response
    reads the served wheel version once instead of once per agent.
    """
    response = AgentMachineResponse.model_validate(agent)
    response.available_agent_version = available
    response.upgrade_status = compute_agent_upgrade_status(
        reported=agent.agent_version,
        desired=agent.desired_agent_version,
        available=available,
    )
    response.self_upgrade_supported = "self_upgrade" in (agent.capabilities or [])
    return response
```

Change the end of `list_agent_machines` from `return agents` to:

```python
    available = agent_package_version()
    return [_agent_machine_response(agent, available=available) for agent in agents]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_api_managed_machines.py -v`
Expected: PASS, including the pre-existing tests

- [ ] **Step 5: Commit**

```bash
git add app/api/managed_machines.py tests/unit/test_api_managed_machines.py
git commit -m "feat(agents): report agent upgrade status from the agents API"
```

---

### Task 4: Pin endpoint

**Files:**
- Modify: `app/api/managed_machines.py` (new route after
  `list_agent_machines`)
- Test: `tests/unit/test_api_managed_machines.py`

Admin gating comes from the `get_current_admin_user` dependency in the route
signature, exactly as the sibling agent routes do. Do not add an entry to
`ENDPOINT_POLICIES` in `app/core/authorization.py`: no `managed-machines` route
is registered there, and adding one would introduce a second, divergent
authorization path for this router.

**Interfaces:**
- Consumes: `_agent_machine_response` from Task 3.
- Produces: `PUT /api/managed-machines/agents/{agent_machine_id}/desired-version`
  taking `{"desired_agent_version": str | null, "desired_borg_version": "1" | "2" | null}`
  and returning the updated `AgentMachineResponse`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_api_managed_machines.py`:

```python
def test_set_desired_version_pins_agent(client, test_db, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    agent = AgentMachine(
        name="pin-me",
        agent_id="agt_pin_me",
        token_hash="x",
        token_prefix="agt_pm",
        status="online",
        agent_version="0.1.3",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    response = client.put(
        f"/api/managed-machines/agents/{agent.id}/desired-version",
        json={"desired_agent_version": "0.1.3", "desired_borg_version": "2"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["desired_agent_version"] == "0.1.3"
    assert response.json()["desired_borg_version"] == "2"
    assert response.json()["upgrade_status"] == "pinned"


def test_clearing_desired_version_returns_to_tracking_server(
    client, test_db, admin_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    agent = AgentMachine(
        name="unpin-me",
        agent_id="agt_unpin_me",
        token_hash="x",
        token_prefix="agt_um",
        status="online",
        agent_version="0.1.3",
        desired_agent_version="0.1.2",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    response = client.put(
        f"/api/managed-machines/agents/{agent.id}/desired-version",
        json={"desired_agent_version": None, "desired_borg_version": None},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["desired_agent_version"] is None
    assert response.json()["upgrade_status"] == "up_to_date"


def test_cannot_pin_a_version_the_server_cannot_serve(
    client, test_db, admin_headers, monkeypatch
):
    """The installer only installs from this server's wheelhouse, so a pin to
    anything else is permanently unsatisfiable."""
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    agent = AgentMachine(
        name="bad-pin",
        agent_id="agt_bad_pin",
        token_hash="x",
        token_prefix="agt_bp",
        status="online",
        agent_version="0.1.3",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    response = client.put(
        f"/api/managed-machines/agents/{agent.id}/desired-version",
        json={"desired_agent_version": "9.9.9", "desired_borg_version": None},
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.agents.desiredVersionUnavailable"
    )


def test_desired_borg_version_must_be_1_or_2(
    client, test_db, admin_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    agent = AgentMachine(
        name="bad-borg",
        agent_id="agt_bad_borg",
        token_hash="x",
        token_prefix="agt_bb",
        status="online",
        agent_version="0.1.3",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    response = client.put(
        f"/api/managed-machines/agents/{agent.id}/desired-version",
        json={"desired_agent_version": None, "desired_borg_version": "3"},
        headers=admin_headers,
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_api_managed_machines.py -k desired_version -v`
Expected: FAIL with 405 or 404 (route does not exist)

- [ ] **Step 3: Write minimal implementation**

In `app/api/managed_machines.py`, add the request model next to the other
Pydantic models:

```python
class AgentDesiredVersionRequest(BaseModel):
    """Pin an endpoint to a version, or clear the pin with nulls."""

    desired_agent_version: Optional[str] = None
    desired_borg_version: Optional[Literal["1", "2"]] = None
```

Add `Literal` to the `typing` import if it is not already there.

Add the route immediately after `list_agent_machines`:

```python
@router.put(
    "/agents/{agent_machine_id}/desired-version",
    response_model=AgentMachineResponse,
)
async def set_agent_desired_version(
    agent_machine_id: int,
    payload: AgentDesiredVersionRequest,
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Pin this endpoint to an agent version, or clear the pin to track the
    server again."""
    agent = (
        db.query(AgentMachine)
        .filter(
            AgentMachine.id == agent_machine_id,
            AgentMachine.status != "deleted",
        )
        .first()
    )
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.notFound"},
        )

    available = agent_package_version()
    if (
        payload.desired_agent_version is not None
        and payload.desired_agent_version != available
    ):
        # The installer installs from this server's wheelhouse and nowhere
        # else, so a pin to any other version could never be satisfied.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"key": "backend.errors.agents.desiredVersionUnavailable"},
        )

    agent.desired_agent_version = payload.desired_agent_version
    agent.desired_borg_version = payload.desired_borg_version
    agent.updated_at = _now_utc()
    db.commit()
    db.refresh(agent)
    return _agent_machine_response(agent, available=available)
```

Add the i18n keys to all four locale files under
`backend.errors.agents`: `desiredVersionUnavailable`. English copy:
`"That version is not available on this server."`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_api_managed_machines.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/managed_machines.py frontend/src/locales tests/unit/test_api_managed_machines.py
git commit -m "feat(agents): add an endpoint to pin an agent version"
```

---

### Task 5: Frontend types and the version chip

**Files:**
- Modify: `frontend/src/services/api.ts:1187` (`AgentMachineResponse`)
- Create: `frontend/src/pages/managed-agents/AgentUpgradeChip.tsx`
- Create: `frontend/src/pages/managed-agents/AgentUpgradeChip.stories.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

**Interfaces:**
- Consumes: the API fields from Task 3.
- Produces: `AgentUpgradeStatus` type
  (`'up_to_date' | 'outdated' | 'ahead' | 'pinned' | 'unknown'`) and
  `<AgentUpgradeChip status={...} targetVersion={...} />`.

- [ ] **Step 1: Extend the API type**

In `frontend/src/services/api.ts`, add to `AgentMachineResponse` after
`agent_version`:

```typescript
  desired_agent_version?: string | null
  desired_borg_version?: string | null
  available_agent_version?: string | null
  upgrade_status?: AgentUpgradeStatus
  self_upgrade_supported?: boolean
  upgrade_state?: string | null
  upgrade_requested_at?: string | null
  upgrade_error?: string | null
```

And above the interface:

```typescript
export type AgentUpgradeStatus =
  | 'up_to_date'
  | 'outdated'
  | 'ahead'
  | 'pinned'
  | 'unknown'
```

- [ ] **Step 2: Add the i18n keys**

Under `managedAgents.page`, add an `upgrade` object to all four locales.
English:

```json
"upgrade": {
  "upToDate": "Current",
  "outdated": "Update available",
  "ahead": "Ahead of server",
  "pinned": "Pinned",
  "unknown": "Version unknown",
  "targetTooltip": "This server serves agent version {{version}}",
  "pinnedTooltip": "Pinned to version {{version}} and will not track the server",
  "unknownTooltip": "This endpoint has not reported a version we can compare",
  "outdatedCount_one": "{{count}} endpoint is running an older agent",
  "outdatedCount_other": "{{count}} endpoints are running an older agent",
  "bannerBody": "Upgrade these endpoints to agent version {{version}}.",
  "bannerManual": "Reinstall each one from its card to bring it up to date."
}
```

Translate the same keys into `de.json`, `es.json`, and `it.json`. Keep
`{{count}}` and `{{version}}` placeholders exactly as written, and keep the
`_one` / `_other` plural suffixes, which i18next requires.

- [ ] **Step 3: Write the component**

Create `frontend/src/pages/managed-agents/AgentUpgradeChip.tsx`:

```tsx
import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { AgentUpgradeStatus } from '../../services/api'

const STATUS_COLOR: Record<
  AgentUpgradeStatus,
  'success' | 'warning' | 'info' | 'default'
> = {
  up_to_date: 'success',
  outdated: 'warning',
  ahead: 'info',
  pinned: 'info',
  unknown: 'default',
}

const STATUS_LABEL: Record<AgentUpgradeStatus, string> = {
  up_to_date: 'managedAgents.page.upgrade.upToDate',
  outdated: 'managedAgents.page.upgrade.outdated',
  ahead: 'managedAgents.page.upgrade.ahead',
  pinned: 'managedAgents.page.upgrade.pinned',
  unknown: 'managedAgents.page.upgrade.unknown',
}

export default function AgentUpgradeChip({
  status,
  targetVersion,
  pinnedVersion,
}: {
  status: AgentUpgradeStatus
  targetVersion?: string | null
  pinnedVersion?: string | null
}) {
  const { t } = useTranslation()

  const tooltip = () => {
    if (status === 'pinned' && pinnedVersion) {
      return t('managedAgents.page.upgrade.pinnedTooltip', { version: pinnedVersion })
    }
    if (status === 'unknown') {
      return t('managedAgents.page.upgrade.unknownTooltip')
    }
    if (targetVersion) {
      return t('managedAgents.page.upgrade.targetTooltip', { version: targetVersion })
    }
    return ''
  }

  const chip = (
    <Chip
      size="small"
      variant="outlined"
      color={STATUS_COLOR[status]}
      label={t(STATUS_LABEL[status])}
      sx={{ height: 20, fontSize: '0.6rem', fontWeight: 600 }}
    />
  )

  const title = tooltip()
  return title ? (
    <Tooltip title={title} arrow>
      <span>{chip}</span>
    </Tooltip>
  ) : (
    chip
  )
}
```

- [ ] **Step 4: Write the story**

Create `frontend/src/pages/managed-agents/AgentUpgradeChip.stories.tsx`:

```tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import AgentUpgradeChip from './AgentUpgradeChip'

const meta: Meta<typeof AgentUpgradeChip> = {
  title: 'Managed Agents/AgentUpgradeChip',
  component: AgentUpgradeChip,
}
export default meta

type Story = StoryObj<typeof AgentUpgradeChip>

export const AllStates: Story = {
  render: () => (
    <Stack direction="row" spacing={1} alignItems="center">
      <AgentUpgradeChip status="up_to_date" targetVersion="0.1.3" />
      <AgentUpgradeChip status="outdated" targetVersion="0.1.3" />
      <AgentUpgradeChip status="ahead" targetVersion="0.1.3" />
      <AgentUpgradeChip status="pinned" pinnedVersion="0.1.2" />
      <AgentUpgradeChip status="unknown" />
    </Stack>
  ),
}

export const UpToDate: Story = { args: { status: 'up_to_date', targetVersion: '0.1.3' } }
export const Outdated: Story = { args: { status: 'outdated', targetVersion: '0.1.3' } }
export const Ahead: Story = { args: { status: 'ahead', targetVersion: '0.1.3' } }
export const Pinned: Story = { args: { status: 'pinned', pinnedVersion: '0.1.2' } }
export const Unknown: Story = { args: { status: 'unknown' } }
```

- [ ] **Step 5: Verify and commit**

Run: `cd frontend && npx tsc --noEmit && npx prettier --check src/pages/managed-agents/AgentUpgradeChip.tsx src/pages/managed-agents/AgentUpgradeChip.stories.tsx`
Expected: no type errors, formatting clean

```bash
git add frontend/src/services/api.ts frontend/src/pages/managed-agents/AgentUpgradeChip.tsx frontend/src/pages/managed-agents/AgentUpgradeChip.stories.tsx frontend/src/locales
git commit -m "feat(agents): add an agent version status chip"
```

---

### Task 6: Out-of-date banner

Informational only. No action button in phase 1.

**Files:**
- Create: `frontend/src/pages/managed-agents/AgentUpgradeBanner.tsx`
- Create: `frontend/src/pages/managed-agents/AgentUpgradeBanner.stories.tsx`

**Interfaces:**
- Consumes: `AgentMachineResponse[]` and the i18n keys from Task 5.
- Produces: `<AgentUpgradeBanner agents={agents} />`, which renders nothing
  when no agent is `outdated`.

- [ ] **Step 1: Write the component**

Create `frontend/src/pages/managed-agents/AgentUpgradeBanner.tsx`:

```tsx
import { Alert, AlertTitle, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { AgentMachineResponse } from '../../services/api'

export default function AgentUpgradeBanner({
  agents,
}: {
  agents: AgentMachineResponse[]
}) {
  const { t } = useTranslation()
  const outdated = agents.filter((agent) => agent.upgrade_status === 'outdated')
  if (outdated.length === 0) {
    return null
  }

  // Every outdated agent compares against the same served version, so reading
  // it off the first one is enough.
  const target =
    outdated[0].available_agent_version ?? outdated[0].desired_agent_version ?? ''

  return (
    <Alert severity="warning" variant="outlined" sx={{ mb: 2 }}>
      <AlertTitle sx={{ fontWeight: 700 }}>
        {t('managedAgents.page.upgrade.outdatedCount', { count: outdated.length })}
      </AlertTitle>
      <Typography variant="body2">
        {target
          ? t('managedAgents.page.upgrade.bannerBody', { version: target })
          : null}{' '}
        {t('managedAgents.page.upgrade.bannerManual')}
      </Typography>
    </Alert>
  )
}
```

- [ ] **Step 2: Write the story**

Create `frontend/src/pages/managed-agents/AgentUpgradeBanner.stories.tsx`:

```tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import AgentUpgradeBanner from './AgentUpgradeBanner'
import type { AgentMachineResponse } from '../../services/api'

const base: AgentMachineResponse = {
  id: 1,
  name: 'Production NAS',
  agent_id: 'agt_prod_nas_01',
  status: 'online',
  agent_version: '0.1.2',
  available_agent_version: '0.1.3',
  upgrade_status: 'outdated',
  created_at: '2026-05-10T08:00:00.000Z',
  updated_at: '2026-09-07T08:00:00.000Z',
}

const meta: Meta<typeof AgentUpgradeBanner> = {
  title: 'Managed Agents/AgentUpgradeBanner',
  component: AgentUpgradeBanner,
}
export default meta

type Story = StoryObj<typeof AgentUpgradeBanner>

export const OneOutdated: Story = { args: { agents: [base] } }

export const SeveralOutdated: Story = {
  args: {
    agents: [
      base,
      { ...base, id: 2, name: 'Finance Workstation', agent_id: 'agt_fin_07' },
      { ...base, id: 3, name: 'Build Server', agent_id: 'agt_build_02' },
    ],
  },
}

export const NoneOutdated: Story = {
  args: {
    agents: [{ ...base, upgrade_status: 'up_to_date', agent_version: '0.1.3' }],
  },
}
```

- [ ] **Step 3: Verify and commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: no type errors

```bash
git add frontend/src/pages/managed-agents/AgentUpgradeBanner.tsx frontend/src/pages/managed-agents/AgentUpgradeBanner.stories.tsx
git commit -m "feat(agents): add an out-of-date agents banner"
```

---

### Task 7: Wire the chip and banner into the page

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.tsx` (`AgentList` at line 1556,
  the version display at line 1701)
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`
- Test: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

**Interfaces:**
- Consumes: `AgentUpgradeChip` (Task 5), `AgentUpgradeBanner` (Task 6).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/__tests__/ManagedAgents.test.tsx`, following the
render helpers already in that file:

```tsx
it('shows an update chip on an out-of-date agent', () => {
  renderAgentList([
    makeAgent({
      id: 1,
      name: 'Behind',
      agent_version: '0.1.2',
      available_agent_version: '0.1.3',
      upgrade_status: 'outdated',
    }),
  ])
  expect(screen.getByText('Update available')).toBeInTheDocument()
})

it('does not show an update chip on a current agent', () => {
  renderAgentList([
    makeAgent({
      id: 1,
      name: 'Current',
      agent_version: '0.1.3',
      available_agent_version: '0.1.3',
      upgrade_status: 'up_to_date',
    }),
  ])
  expect(screen.queryByText('Update available')).not.toBeInTheDocument()
})
```

If `renderAgentList` and `makeAgent` do not exist in that file, write them from
the existing render setup rather than inventing a new pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/__tests__/ManagedAgents.test.tsx`
Expected: FAIL, "Update available" not found

- [ ] **Step 3: Render the chip next to the version**

In `frontend/src/pages/ManagedAgents.tsx`, import the components:

```tsx
import AgentUpgradeChip from './managed-agents/AgentUpgradeChip'
import AgentUpgradeBanner from './managed-agents/AgentUpgradeBanner'
```

Replace the version block at line 1701 (the `agent.agent_version && (...)`
`Typography`) with a `Box` holding the same `Typography` plus the chip:

```tsx
<Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
  {agent.agent_version && (
    <Typography
      sx={{
        fontSize: '0.58rem',
        fontWeight: 500,
        color: 'text.disabled',
        letterSpacing: '0.02em',
      }}
    >
      v{agent.agent_version}
    </Typography>
  )}
  {agent.upgrade_status && agent.upgrade_status !== 'up_to_date' && (
    <AgentUpgradeChip
      status={agent.upgrade_status}
      targetVersion={agent.available_agent_version}
      pinnedVersion={agent.desired_agent_version}
    />
  )}
</Box>
```

The chip is hidden for `up_to_date` so the common case stays quiet and only
endpoints needing attention draw the eye.

- [ ] **Step 4: Render the banner above the agent list**

In `AgentList`, immediately inside the returned fragment and before the grid of
agent cards, add:

```tsx
<AgentUpgradeBanner agents={agents} />
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/__tests__/ManagedAgents.test.tsx`
Expected: PASS

- [ ] **Step 6: Add page-level stories**

In `frontend/src/pages/ManagedAgents.stories.tsx`, add `upgrade_status` and
`available_agent_version` to the existing `agents` fixture so the default story
shows a mixed fleet, then add:

```tsx
export const AgentListWithOutdatedAgents: Story = {
  render: () => (
    <AgentList
      agents={[
        { ...agents[0], agent_version: '0.1.2', available_agent_version: '0.1.3', upgrade_status: 'outdated' },
        { ...agents[1], agent_version: '0.1.3', available_agent_version: '0.1.3', upgrade_status: 'up_to_date' },
      ]}
      serverUrl="https://borg.example.com"
      onCopy={() => {}}
      onRevoke={() => {}}
      onDelete={() => {}}
      onViewLogs={() => {}}
      isRevoking={false}
      isDeleting={false}
    />
  ),
}
```

Match the prop list to `AgentList`'s actual signature at the time of writing;
do not guess if it has changed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ManagedAgents.tsx frontend/src/pages/ManagedAgents.stories.tsx frontend/src/pages/__tests__/ManagedAgents.test.tsx
git commit -m "feat(agents): show agent version status on the agents page"
```

---

### Task 8: Documentation and full verification

**Files:**
- Modify: `docs/managed-agents.md`
- Modify: `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`
  (progress table only)

- [ ] **Step 1: Document the version states**

Add a "Keeping agents up to date" section to `docs/managed-agents.md` covering
what each chip means, that the server compares against the agent wheel it
serves, that pinning stops an endpoint tracking the server, and that upgrading
is still a manual reinstall in this release.

- [ ] **Step 2: Update the spec progress table**

Set phase 1 to `done` in section 13.1 and record the branch.

- [ ] **Step 3: Run the full verification**

```bash
python -m pytest tests/unit -q
cd frontend && npm run typecheck && npm run lint && npm run test -- --run
```

Expected: all pass. Do not claim completion until you have seen the output.

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs(agents): document agent version status and pinning"
```

---

## Self-Review

**Spec coverage for phase 1 (section 13.2):**

| Spec requirement | Task |
| --- | --- |
| Migration adding the six columns | 2 |
| Comparison helper and `upgrade_status` | 1, 3 |
| `upgrade_status` on `AgentMachineResponse` | 3 |
| Version cell and chips | 5, 7 |
| Fleet banner | 6, 7 |
| Pin control with its `PUT` endpoint | 4 |
| Stories for every chip state and the banner | 5, 6, 7 |

**Known gap, deliberately deferred:** the spec's phase 1 text says "the pin
control", meaning UI. Task 4 ships the endpoint and Task 5 ships the chip that
displays a pin, but no UI control sets one. Setting a pin is only useful once
upgrades are automatic, since today an operator controls the version by
choosing what to paste. The pin UI moves to phase 3, where the upgrade action
it modifies exists. Update the spec's section 13.2 and 13.4 text to match when
executing Task 8.
