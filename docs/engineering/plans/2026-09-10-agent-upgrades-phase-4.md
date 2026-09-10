# Agent upgrades phase 4: fleet upgrade

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade a whole fleet from the Managed Agents page, in waves of at
most `AGENT_UPGRADE_CONCURRENCY` endpoints in flight at a time.

**Architecture:** Phase 3 dispatches every id in the request immediately. This
phase splits accept from dispatch: `POST .../agents/upgrade` validates the
whole request, marks every accepted endpoint `queued`, and then releases as
many as the free-slot count allows. The same release function runs on every
agent-job-reaper tick, so a slot freed by a success or a timeout starts the
next endpoint with no further operator action. On the page, the banner gains
an Upgrade all action, cards gain selection checkboxes with a bulk action bar,
and the existing single-agent upgrade dialog is generalised to a list.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, TypeScript, MUI, i18next,
Vitest, Storybook.

**Spec:** `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`
(sections 5, 8, 9, 12; phase 13.5)

## Global Constraints

- No em dashes in UI copy, i18n strings, code comments, or commit messages.
- Every new i18n key must be added to all four locales:
  `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`. The
  `frontend-locale-check` pre-push hook fails otherwise.
- No heavy left accent borders on cards, panels, alerts, or status surfaces
  (`AGENTS.md`, UI Preferences).
- New UI components go in `frontend/src/pages/managed-agents/`, not inline in
  `ManagedAgents.tsx`, which is over 2400 lines.
- New or changed UI ships a Storybook story for the changed state, in default
  and mobile viewports, matching `ManagedAgents.stories.tsx` conventions.
- Do not register `managed-machines` routes in `ENDPOINT_POLICIES`
  (`app/core/authorization.py`); that router authorizes through its route
  signatures (spec section 11.2).
- Do not re-open a decision in the spec's Appendix B.

## Decisions this plan makes that the spec leaves open

Called out at the phase gate rather than buried here.

1. **`upgrade_requested_at` stays NULL while an endpoint is `queued`.** The
   reaper times an endpoint out `AGENT_UPGRADE_TIMEOUT_SECONDS` after
   `upgrade_requested_at`, so stamping it at accept time would fail endpoints
   for the time they spent waiting in line behind other waves. It is stamped
   when the endpoint is actually dispatched.
2. **Waves are released in id order.** The spec says waves, not fairness. Id
   order is stable, reproducible in tests, and needs no extra column.
3. **A `queued` endpoint that fails to dispatch is marked `failed` and does
   not hold a slot.** This is already what phase 3 does on a dispatch error;
   the wave release inherits it unchanged.

---

### Task 1: Wave release service

**Files:**
- Modify: `app/core/agent_constants.py`
- Create: `app/services/agent_upgrades.py`
- Modify: `app/api/managed_machines.py`
- Test: `tests/unit/test_agent_upgrade_waves.py`

**Interfaces:**
- Produces: `AGENT_UPGRADE_CONCURRENCY: int` in `app/core/agent_constants.py`.
- Produces: `async def release_agent_upgrade_waves(db: Session) -> int` in
  `app/services/agent_upgrades.py`, returning how many endpoints it
  dispatched.
- Produces: `async def request_agent_upgrade(db, agent, *, target) -> dict`,
  the phase 3 `_request_agent_upgrade` moved out of the API module unchanged
  in behaviour, so both the endpoint and the wave release call one dispatcher.
- Consumes: `AgentMachine.upgrade_state`, `upgrade_requested_at`,
  `upgrade_target_version`, `upgrade_error` (phase 1 columns).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_agent_upgrade_waves.py`. Model the existing agent
tests: look at `tests/unit/test_agent_job_reaper.py` for the session/factory
helpers already in use and reuse them rather than inventing new fixtures.

```python
import pytest

from app.services.agent_upgrades import release_agent_upgrade_waves


def _queued_agent(db, name, *, version="0.1.3"):
    """An endpoint accepted into a fleet upgrade but not yet dispatched."""
    agent = AgentMachine(
        name=name,
        agent_id=name,
        status="online",
        capabilities=["self_upgrade"],
        agent_version="0.1.2",
        upgrade_state="queued",
        upgrade_target_version=version,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@pytest.mark.asyncio
async def test_release_dispatches_at_most_the_concurrency_cap(db, monkeypatch):
    sent = []

    async def fake_send_command(agent_id, **kwargs):
        sent.append(agent_id)

    monkeypatch.setattr(
        "app.services.agent_upgrades.agent_connection_manager.send_command",
        fake_send_command,
    )
    monkeypatch.setattr(
        "app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 2
    )
    agents = [_queued_agent(db, f"a{i}") for i in range(5)]

    dispatched = await release_agent_upgrade_waves(db)

    assert dispatched == 2
    assert len(sent) == 2
    states = [db.query(AgentMachine).get(a.id).upgrade_state for a in agents]
    assert states == ["requested", "requested", "queued", "queued", "queued"]


@pytest.mark.asyncio
async def test_release_counts_in_flight_endpoints_against_the_cap(db, monkeypatch):
    """A slot held by an endpoint already upgrading is not handed out twice."""
    sent = []

    async def fake_send_command(agent_id, **kwargs):
        sent.append(agent_id)

    monkeypatch.setattr(
        "app.services.agent_upgrades.agent_connection_manager.send_command",
        fake_send_command,
    )
    monkeypatch.setattr(
        "app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 2
    )
    in_flight = _queued_agent(db, "busy")
    in_flight.upgrade_state = "requested"
    in_flight.upgrade_requested_at = datetime.now(timezone.utc)
    db.commit()
    _queued_agent(db, "waiting-1")
    _queued_agent(db, "waiting-2")

    assert await release_agent_upgrade_waves(db) == 1
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_release_stamps_requested_at_only_on_dispatch(db, monkeypatch):
    """A queued endpoint must not age towards the reaper's timeout."""

    async def fake_send_command(agent_id, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_upgrades.agent_connection_manager.send_command",
        fake_send_command,
    )
    monkeypatch.setattr(
        "app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 1
    )
    first = _queued_agent(db, "first")
    waiting = _queued_agent(db, "waiting")

    await release_agent_upgrade_waves(db)

    assert db.query(AgentMachine).get(first.id).upgrade_requested_at is not None
    assert db.query(AgentMachine).get(waiting.id).upgrade_requested_at is None


@pytest.mark.asyncio
async def test_release_marks_a_failed_dispatch_failed_and_frees_its_slot(
    db, monkeypatch
):
    async def fake_send_command(agent_id, **kwargs):
        raise AgentConnectionUnavailable("offline")

    monkeypatch.setattr(
        "app.services.agent_upgrades.agent_connection_manager.send_command",
        fake_send_command,
    )
    monkeypatch.setattr(
        "app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 1
    )
    agent = _queued_agent(db, "offline-endpoint")

    await release_agent_upgrade_waves(db)

    row = db.query(AgentMachine).get(agent.id)
    assert row.upgrade_state == "failed"
    assert row.upgrade_requested_at is None
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```bash
pytest tests/unit/test_agent_upgrade_waves.py -q
```

Expected: collection error, `No module named 'app.services.agent_upgrades'`.

- [ ] **Step 3: Add the concurrency constant**

In `app/core/agent_constants.py`, below `AGENT_UPGRADE_TIMEOUT_SECONDS`:

```python
# How many endpoints may be upgrading at once. Every upgrading endpoint is
# briefly offline, so a fleet-wide request is released in waves rather than
# taking the whole fleet down together. The cap bounds upgrades in flight, not
# endpoints offline: a timeout frees its slot while that endpoint may still be
# mid-reinstall (spec section 8).
AGENT_UPGRADE_CONCURRENCY = 5
```

- [ ] **Step 4: Move the dispatcher into a service module**

Create `app/services/agent_upgrades.py`. Move `_request_agent_upgrade` from
`app/api/managed_machines.py` verbatim, renamed `request_agent_upgrade`, with
its imports (`AgentJob`, `AgentMachine`, `agent_connection_manager`, the three
agent command exceptions, `AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS`) and its
`_now_utc` helper. In `managed_machines.py`, delete the moved function and
import `request_agent_upgrade` from the new module; every existing call site
keeps working because the signature is unchanged.

- [ ] **Step 5: Implement the wave release**

Append to `app/services/agent_upgrades.py`:

```python
async def release_agent_upgrade_waves(db: Session) -> int:
    """Dispatch as many queued upgrades as there are free slots.

    Called both by the upgrade endpoint (so a small request starts at once)
    and by the agent job reaper on every tick (so a slot freed by a success or
    a timeout starts the next endpoint with nobody watching). Returns the
    number dispatched.
    """
    in_flight = (
        db.query(AgentMachine)
        .filter(AgentMachine.upgrade_state == "requested")
        .count()
    )
    free = AGENT_UPGRADE_CONCURRENCY - in_flight
    if free <= 0:
        return 0

    waiting = (
        db.query(AgentMachine)
        .filter(AgentMachine.upgrade_state == "queued")
        .order_by(AgentMachine.id)
        .limit(free)
        .all()
    )
    dispatched = 0
    for agent in waiting:
        # Conditional claim, matching the endpoint's: two releases racing (an
        # operator request landing on a reaper tick) must not dispatch one
        # endpoint twice. The loser updates no row and skips it.
        claimed = (
            db.query(AgentMachine)
            .filter(
                AgentMachine.id == agent.id,
                AgentMachine.upgrade_state == "queued",
            )
            .update(
                {
                    AgentMachine.upgrade_state: "requested",
                    AgentMachine.upgrade_requested_at: _now_utc(),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if not claimed:
            continue
        db.refresh(agent)
        await request_agent_upgrade(
            db, agent, target=agent.upgrade_target_version
        )
        dispatched += 1
    return dispatched
```

- [ ] **Step 6: Run the tests and confirm they pass**

Run:

```bash
pytest tests/unit/test_agent_upgrade_waves.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/core/agent_constants.py app/services/agent_upgrades.py \
  app/api/managed_machines.py tests/unit/test_agent_upgrade_waves.py
git commit -m "feat(agents): release fleet upgrades in waves"
```

### Task 2: The endpoint queues, then releases

**Files:**
- Modify: `app/api/managed_machines.py:599-710`
- Test: `tests/unit/test_managed_machines_upgrade.py`

**Interfaces:**
- Consumes: `release_agent_upgrade_waves`, `request_agent_upgrade` (Task 1).
- Produces: `POST /api/managed-machines/agents/upgrade` returning
  `{"results": [{"agent_machine_id": int, "job_id": int | None,
  "state": "queued" | "requested" | "failed"}]}`.

- [ ] **Step 1: Write the failing tests**

Add to the existing upgrade endpoint test module (find it with
`grep -rl "agents/upgrade" tests/unit`; phase 3 added it):

```python
def test_upgrade_beyond_the_cap_leaves_the_rest_queued(client, db, monkeypatch):
    monkeypatch.setattr("app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 2)
    agents = [_upgradable_agent(db, f"a{i}") for i in range(4)]

    response = client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [a.id for a in agents]},
    )

    assert response.status_code == 200
    states = [r["state"] for r in response.json()["results"]]
    assert states == ["requested", "requested", "queued", "queued"]
    # A queued endpoint has no job yet: the job is created at dispatch.
    assert [r["job_id"] for r in response.json()["results"]][2:] == [None, None]


def test_a_queued_endpoint_is_not_queued_twice(client, db, monkeypatch):
    """Idempotent under a double click, exactly as an in-flight one is."""
    monkeypatch.setattr("app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 0)
    agent = _upgradable_agent(db, "solo")
    body = {"agent_machine_ids": [agent.id]}

    client.post("/api/managed-machines/agents/upgrade", json=body)
    response = client.post("/api/managed-machines/agents/upgrade", json=body)

    assert response.status_code == 200
    assert response.json()["results"][0]["state"] == "queued"
    assert (
        db.query(AgentJob)
        .filter(AgentJob.agent_machine_id == agent.id)
        .count()
        == 0
    )


def test_validation_still_rejects_the_whole_request(client, db):
    """Unchanged from phase 3: nothing is queued if any endpoint is invalid."""
    good = _upgradable_agent(db, "good")
    bad = _upgradable_agent(db, "bad")
    bad.capabilities = []
    db.commit()

    response = client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [good.id, bad.id]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["key"] == (
        "backend.errors.agents.upgradeUnsupported"
    )
    assert db.query(AgentMachine).get(good.id).upgrade_state is None
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
pytest tests/unit/test_managed_machines_upgrade.py -q
```

Expected: the first two fail because every id is dispatched immediately and
`state` is never `queued`.

- [ ] **Step 3: Rewrite the results loop**

Keep the validation block above it exactly as it is: dedup, 404 on a missing
agent, `upgradeUnsupported`, `upgradeTargetUnavailable`, all before anything
is written. Replace only the results loop (the `for agent_id in wanted:` block
that claims and calls `_request_agent_upgrade`) with an accept pass followed by
one release:

```python
    for agent_id in wanted:
        agent = found[agent_id]
        # Accept, do not dispatch. An endpoint already queued or already
        # upgrading keeps the state it has: an upgrade restarts the machine,
        # so a double click must not restart it twice.
        db.query(AgentMachine).filter(
            AgentMachine.id == agent.id,
            or_(
                AgentMachine.upgrade_state.is_(None),
                AgentMachine.upgrade_state.notin_(("queued", "requested")),
            ),
        ).update(
            {
                AgentMachine.upgrade_state: "queued",
                # Deliberately not stamping upgrade_requested_at: the reaper
                # times out from it, and time spent waiting for a wave is not
                # time the endpoint has failed to come back (spec section 8).
                AgentMachine.upgrade_requested_at: None,
                AgentMachine.upgrade_target_version: (
                    agent.desired_agent_version or available
                ),
                AgentMachine.upgrade_error: None,
            },
            synchronize_session=False,
        )
    db.commit()

    # Release the first wave inline so a request under the cap starts at once
    # rather than waiting up to a reaper interval.
    await release_agent_upgrade_waves(db)

    results = []
    for agent_id in wanted:
        agent = db.query(AgentMachine).filter(AgentMachine.id == agent_id).first()
        results.append(
            {
                "agent_machine_id": agent_id,
                "job_id": _last_upgrade_job_id(db, agent),
                "state": agent.upgrade_state,
            }
        )
```

`_last_upgrade_job_id` already returns `None` when an endpoint has no upgrade
job, which is exactly the queued case.

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
pytest tests/unit/test_managed_machines_upgrade.py tests/unit/test_agent_upgrade_waves.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/managed_machines.py tests/unit/test_managed_machines_upgrade.py
git commit -m "feat(agents): queue fleet upgrades and release the first wave"
```

### Task 3: The reaper advances the waves

**Files:**
- Modify: `app/services/agent_job_reaper.py:254-276`
- Test: `tests/unit/test_agent_job_reaper.py`

**Interfaces:**
- Consumes: `release_agent_upgrade_waves` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_agent_job_reaper.py`:

```python
@pytest.mark.asyncio
async def test_reaper_tick_releases_the_next_upgrade_wave(monkeypatch):
    """A slot freed by a timeout starts the next endpoint with no operator."""
    released = []

    async def fake_release(db):
        released.append(True)
        return 0

    monkeypatch.setattr(
        "app.services.agent_job_reaper.release_agent_upgrade_waves", fake_release
    )
    monkeypatch.setattr(
        "app.services.agent_job_reaper._reap_once", lambda ids=None: 0
    )

    task = asyncio.create_task(start_agent_job_reaper(interval_seconds=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert released
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```bash
pytest tests/unit/test_agent_job_reaper.py -q -k wave
```

Expected: `AttributeError` on the missing `release_agent_upgrade_waves`
attribute in the reaper module.

- [ ] **Step 3: Call the release from the loop**

The release is async and dispatches over the agent WebSocket, so it runs on
the event loop, not inside the `asyncio.to_thread` reap. In
`app/services/agent_job_reaper.py`, import at module level:

```python
from app.services.agent_upgrades import release_agent_upgrade_waves
```

and in `start_agent_job_reaper`, after the notify block:

```python
            if failed_backup_job_ids:
                await _notify_reaped_backup_jobs(failed_backup_job_ids)
            # A slot frees when an endpoint leaves "requested", by success or
            # by the timeout reaped just above, so the next wave starts here
            # (spec section 8).
            await _release_upgrade_waves()
```

with the session-owning helper next to `_notify_reaped_backup_jobs`:

```python
async def _release_upgrade_waves() -> None:
    """Advance the fleet upgrade waves with a session of our own."""
    db = SessionLocal()
    try:
        await release_agent_upgrade_waves(db)
    finally:
        db.close()
```

If the module-level import trips a circular import (the API module imports
the reaper), move it inside `_release_upgrade_waves`, matching how
`_reap_once` already imports `app.utils.process_utils` locally.

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
pytest tests/unit/test_agent_job_reaper.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/agent_job_reaper.py tests/unit/test_agent_job_reaper.py
git commit -m "feat(agents): advance upgrade waves on every reaper tick"
```

### Task 4: The queued row state

**Files:**
- Modify: `frontend/src/pages/managed-agents/AgentUpgradeStateChip.tsx`
- Modify: `frontend/src/pages/managed-agents/AgentUpgradeStateChip.stories.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`
- Test: `frontend/src/pages/managed-agents/__tests__/AgentUpgradeStateChip.test.tsx`

**Interfaces:**
- Consumes: `upgrade_state: "queued"` from Task 2's endpoint.
- Produces: no prop changes; the existing `state` prop gains a value.

- [ ] **Step 1: Write the failing test**

Add to the chip's test file (create it if phase 3 did not, following the
sibling tests in `frontend/src/pages/managed-agents/__tests__/`):

```tsx
it('shows a waiting label for an endpoint queued behind a wave', () => {
  render(<AgentUpgradeStateChip state="queued" targetVersion="0.1.3" />)
  expect(screen.getByText('Waiting to upgrade')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run it and confirm it fails**

Run:

```bash
cd frontend && npm run test -- src/pages/managed-agents/__tests__/AgentUpgradeStateChip.test.tsx --run
```

Expected: FAIL, the chip renders `null` for an unknown state.

- [ ] **Step 3: Add the queued branch**

Above the `requested` branch in `AgentUpgradeStateChip.tsx`:

```tsx
  if (state === 'queued') {
    return (
      <Tooltip title={t('managedAgents.page.upgradeState.queuedTooltip')} arrow>
        <Chip
          size="small"
          variant="outlined"
          color="default"
          label={t('managedAgents.page.upgradeState.queued')}
          sx={agentChipSx}
        />
      </Tooltip>
    )
  }
```

No spinner: nothing is happening on that machine yet, and a spinner would say
otherwise.

Add to `managedAgents.page.upgradeState` in all four locale files:

```json
"queued": "Waiting to upgrade",
"queuedTooltip": "Queued behind other endpoints. It starts when a slot frees, with no further action."
```

Translate the German, Spanish and Italian values; do not copy the English.

- [ ] **Step 4: Add the story and run the tests**

Add a `Queued` story to `AgentUpgradeStateChip.stories.tsx` mirroring the
existing `Requested` story, then run:

```bash
cd frontend && npm run test -- src/pages/managed-agents/__tests__/AgentUpgradeStateChip.test.tsx --run
cd frontend && npm run check:locales
```

Expected: PASS, and the locale check reports no missing keys.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/managed-agents/AgentUpgradeStateChip.tsx \
  frontend/src/pages/managed-agents/AgentUpgradeStateChip.stories.tsx \
  frontend/src/pages/managed-agents/__tests__/AgentUpgradeStateChip.test.tsx \
  frontend/src/locales
git commit -m "feat(agents): show the queued upgrade state on the row"
```

### Task 5: One dialog for one or many endpoints

**Files:**
- Modify: `frontend/src/pages/managed-agents/AgentUpgradeDialog.tsx`
- Modify: `frontend/src/pages/managed-agents/AgentUpgradeDialog.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx:2144-2152`
- Modify: `frontend/src/locales/{en,de,es,it}.json`
- Test: `frontend/src/pages/managed-agents/__tests__/AgentUpgradeDialog.test.tsx`

**Interfaces:**
- Produces: `AgentUpgradeDialog` props change from `agent: AgentMachineResponse
  | null` to `agents: AgentMachineResponse[]`, and `onConfirm:
  (agents: AgentMachineResponse[]) => void`. Tasks 6 and 7 use this shape.

- [ ] **Step 1: Write the failing tests**

```tsx
const agents = [
  { id: 1, name: 'alpha', hostname: 'alpha.local', available_agent_version: '0.1.3' },
  { id: 2, name: 'beta', hostname: 'beta.local', available_agent_version: '0.1.3' },
] as AgentMachineResponse[]

it('lists every affected endpoint by name and hostname', () => {
  render(
    <AgentUpgradeDialog open agents={agents} onConfirm={vi.fn()} onCancel={vi.fn()} />
  )
  expect(screen.getByText(/alpha/)).toBeInTheDocument()
  expect(screen.getByText(/beta.local/)).toBeInTheDocument()
})

it('confirms with every endpoint it listed', async () => {
  const onConfirm = vi.fn()
  render(
    <AgentUpgradeDialog open agents={agents} onConfirm={onConfirm} onCancel={vi.fn()} />
  )
  await userEvent.click(screen.getByRole('button', { name: /upgrade/i }))
  expect(onConfirm).toHaveBeenCalledWith(agents)
})

it('names one shared target version when the endpoints agree', () => {
  render(
    <AgentUpgradeDialog open agents={agents} onConfirm={vi.fn()} onCancel={vi.fn()} />
  )
  expect(screen.getByText(/0\.1\.3/)).toBeInTheDocument()
})

it('does not name a version when the endpoints target different ones', () => {
  const mixed = [
    agents[0],
    { ...agents[1], desired_agent_version: '0.1.2' },
  ] as AgentMachineResponse[]
  render(
    <AgentUpgradeDialog open agents={mixed} onConfirm={vi.fn()} onCancel={vi.fn()} />
  )
  expect(screen.getByText(/its own configured version/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run them and confirm they fail**

Run:

```bash
cd frontend && npm run test -- src/pages/managed-agents/__tests__/AgentUpgradeDialog.test.tsx --run
```

Expected: FAIL, the component takes a single `agent`.

- [ ] **Step 3: Generalise the dialog**

Replace the `agent` prop with `agents: AgentMachineResponse[]`, keep every
existing warning about disconnection and blocked-by-backup unchanged, and:

```tsx
// A pin decides the target whatever the server serves, mirroring
// `desired or available` in app/core/agent_versions.py. Endpoints in one
// request do not have to agree, so a single version is named only when they
// do; naming one otherwise would promise an upgrade a pin forbids.
const targets = new Set(
  agents.map((a) => a.desired_agent_version || a.available_agent_version).filter(Boolean)
)
const sharedTarget = targets.size === 1 ? [...targets][0] : null
```

List the endpoints as a plain `Stack` of `Typography` rows, `name` with
`hostname` in `text.secondary`. No table, no per-row icons: the dialog is a
confirmation, not a view.

The confirm handler calls `onConfirm(agents)`.

Update the single-agent call site in `ManagedAgents.tsx` to pass
`agents={upgradeTarget ? [upgradeTarget] : []}` and
`onConfirm={(list) => { list.forEach((a) => onUpgrade?.(a)); setUpgradeTarget(null) }}`.
Task 6 replaces that handler with the bulk mutation; this step only keeps the
build green.

Add to `managedAgents.page.upgradeDialog` in all four locales:

```json
"bodyMany_one": "This endpoint will disconnect briefly while it reinstalls itself.",
"bodyMany_other": "These {{count}} endpoints will disconnect briefly while they reinstall themselves. They are upgraded a few at a time, so some wait before they start.",
"mixedTargets": "Each endpoint upgrades to its own configured version."
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
cd frontend && npm run test -- src/pages/managed-agents/__tests__/AgentUpgradeDialog.test.tsx --run
cd frontend && npm run check:locales
```

Expected: PASS.

- [ ] **Step 5: Add the stories**

In `AgentUpgradeDialog.stories.tsx`, keep the existing single-endpoint story
(update its prop to a one-element array) and add `ManyEndpoints` and
`MixedTargets`, each in default and mobile viewports.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/managed-agents/AgentUpgradeDialog.tsx \
  frontend/src/pages/managed-agents/AgentUpgradeDialog.stories.tsx \
  frontend/src/pages/managed-agents/__tests__/AgentUpgradeDialog.test.tsx \
  frontend/src/pages/ManagedAgents.tsx frontend/src/locales
git commit -m "feat(agents): confirm an upgrade for one or many endpoints"
```

### Task 6: Selection and the bulk action bar

**Files:**
- Create: `frontend/src/pages/managed-agents/AgentBulkUpgradeBar.tsx`
- Create: `frontend/src/pages/managed-agents/AgentBulkUpgradeBar.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx` (`AgentList`, the page's
  mutation)
- Modify: `frontend/src/locales/{en,de,es,it}.json`
- Test: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

**Interfaces:**
- Consumes: `AgentUpgradeDialog` with `agents` (Task 5),
  `managedAgentsAPI.upgradeAgents(agentIds: number[])` (already exists).
- Produces: `AgentBulkUpgradeBar({ count, busy, onUpgrade, onClear })`.
- Produces: `AgentList` gains `onUpgradeMany?: (agents:
  AgentMachineResponse[]) => void`. `onUpgrade` stays for the single-row
  action.

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/pages/__tests__/ManagedAgents.test.tsx`:

```tsx
it('offers selection only on endpoints that can upgrade themselves', () => {
  renderAgentList([
    upgradableAgent({ id: 1, name: 'alpha' }),
    upgradableAgent({ id: 2, name: 'manual', self_upgrade_supported: false }),
  ])
  expect(screen.getAllByRole('checkbox', { name: /select alpha/i })).toHaveLength(1)
  expect(screen.queryByRole('checkbox', { name: /select manual/i })).toBeNull()
})

it('upgrades every selected endpoint in one request', async () => {
  const onUpgradeMany = vi.fn()
  renderAgentList(
    [upgradableAgent({ id: 1, name: 'alpha' }), upgradableAgent({ id: 2, name: 'beta' })],
    { onUpgradeMany }
  )
  await userEvent.click(screen.getByRole('checkbox', { name: /select alpha/i }))
  await userEvent.click(screen.getByRole('checkbox', { name: /select beta/i }))
  await userEvent.click(screen.getByRole('button', { name: /upgrade 2 endpoints/i }))
  await userEvent.click(screen.getByRole('button', { name: /^upgrade$/i }))
  expect(onUpgradeMany).toHaveBeenCalledWith(
    expect.arrayContaining([expect.objectContaining({ id: 1 }), expect.objectContaining({ id: 2 })])
  )
})

it('clears the selection after a bulk upgrade is confirmed', async () => {
  renderAgentList([upgradableAgent({ id: 1, name: 'alpha' })], { onUpgradeMany: vi.fn() })
  await userEvent.click(screen.getByRole('checkbox', { name: /select alpha/i }))
  await userEvent.click(screen.getByRole('button', { name: /upgrade 1 endpoint/i }))
  await userEvent.click(screen.getByRole('button', { name: /^upgrade$/i }))
  expect(screen.queryByRole('button', { name: /upgrade 1 endpoint/i })).toBeNull()
})
```

- [ ] **Step 2: Run them and confirm they fail**

Run:

```bash
cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run -t upgrade
```

Expected: FAIL, no checkboxes are rendered.

- [ ] **Step 3: Build the bar**

`frontend/src/pages/managed-agents/AgentBulkUpgradeBar.tsx`:

```tsx
import { Button, Paper, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

/**
 * Appears only while endpoints are selected. Flat surface, no accent border,
 * matching the page's other inline action surfaces.
 */
export default function AgentBulkUpgradeBar({
  count,
  busy = false,
  onUpgrade,
  onClear,
}: {
  count: number
  busy?: boolean
  onUpgrade: () => void
  onClear: () => void
}) {
  const { t } = useTranslation()
  if (count === 0) {
    return null
  }
  return (
    <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <Typography variant="body2" sx={{ flexGrow: 1 }}>
          {t('managedAgents.page.upgrade.selectedCount', { count })}
        </Typography>
        <Button size="small" onClick={onClear} disabled={busy}>
          {t('common.clear')}
        </Button>
        <Button size="small" variant="contained" onClick={onUpgrade} disabled={busy}>
          {t('managedAgents.page.upgrade.upgradeSelected', { count })}
        </Button>
      </Stack>
    </Paper>
  )
}
```

Locale keys (all four files, under `managedAgents.page.upgrade`):

```json
"selectedCount_one": "{{count}} endpoint selected",
"selectedCount_other": "{{count}} endpoints selected",
"upgradeSelected_one": "Upgrade {{count}} endpoint",
"upgradeSelected_other": "Upgrade {{count}} endpoints",
"selectAgent": "Select {{name}}"
```

Reuse `common.clear` if it exists; add it if it does not.

- [ ] **Step 4: Wire selection into AgentList**

In `AgentList`, hold `const [selectedIds, setSelectedIds] = useState<number[]>([])`.
Render a `Checkbox` in each card's header with
`inputProps={{ 'aria-label': t('managedAgents.page.upgrade.selectAgent', { name: agent.name }) }}`,
only when `onUpgradeMany && agent.self_upgrade_supported === true &&
agent.upgrade_status === 'outdated' && agent.upgrade_state !== 'requested' &&
agent.upgrade_state !== 'queued'`. That is the same eligibility the existing
single-row upgrade button uses, so extract it once:

```tsx
/** The endpoints a server-driven upgrade can actually move. */
const canUpgradeNow = (agent: AgentMachineResponse): boolean =>
  agent.self_upgrade_supported === true &&
  agent.upgrade_status === 'outdated' &&
  agent.upgrade_state !== 'requested' &&
  agent.upgrade_state !== 'queued'
```

Put it in `frontend/src/pages/managed-agents/agentUpgradeEligibility.ts` and
use it from the row action, the bar, and the banner (Task 7), so the count in
the button is always the number that will actually move.

Render `<AgentBulkUpgradeBar ... />` above the list, and reuse the existing
`upgradeTarget` dialog state by widening it to
`const [upgradeTargets, setUpgradeTargets] = useState<AgentMachineResponse[]>([])`.
The bar's Upgrade sets it to the selected agents; the row action sets it to
one. On confirm, call `onUpgradeMany?.(list)` and clear both the dialog and
the selection.

Drop the row-level `onUpgrade` prop if `onUpgradeMany` fully covers it, so
there is one path rather than two.

In the page component, replace `upgradeAgentMutation`'s single-id mutation
with `mutationFn: (ids: number[]) => managedAgentsAPI.upgradeAgents(ids)` and
pass `onUpgradeMany={(list) => upgradeAgentMutation.mutate(list.map((a) => a.id))}`.
Keep the existing activity tracking and toasts; make the success toast count
aware with a plural key.

- [ ] **Step 5: Run the tests and confirm they pass**

Run:

```bash
cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run
cd frontend && npm run check:locales
```

Expected: PASS.

- [ ] **Step 6: Add the story**

`AgentBulkUpgradeBar.stories.tsx` with a selected state and a busy state, plus
a `FleetSelection` story in `ManagedAgents.stories.tsx` showing the list with
two endpoints selected, in default and mobile viewports.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/managed-agents frontend/src/pages/ManagedAgents.tsx \
  frontend/src/pages/ManagedAgents.stories.tsx \
  frontend/src/pages/__tests__/ManagedAgents.test.tsx frontend/src/locales
git commit -m "feat(agents): select endpoints and upgrade them together"
```

### Task 7: Upgrade all from the banner

**Files:**
- Modify: `frontend/src/pages/managed-agents/AgentUpgradeBanner.tsx`
- Modify: `frontend/src/pages/managed-agents/AgentUpgradeBanner.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx` (`AgentList` passes the
  handler)
- Modify: `frontend/src/locales/{en,de,es,it}.json`
- Test: `frontend/src/pages/managed-agents/__tests__/AgentUpgradeBanner.test.tsx`

**Interfaces:**
- Consumes: `canUpgradeNow` (Task 6), `AgentUpgradeDialog` with `agents`
  (Task 5).
- Produces: `AgentUpgradeBanner` gains
  `onUpgradeAll?: (agents: AgentMachineResponse[]) => void` and `busy?: boolean`.

- [ ] **Step 1: Write the failing tests**

```tsx
it('counts only the endpoints the action will actually move', () => {
  render(
    <AgentUpgradeBanner
      agents={[
        outdated({ id: 1, self_upgrade_supported: true }),
        outdated({ id: 2, self_upgrade_supported: false }),
      ]}
      onUpgradeAll={vi.fn()}
    />
  )
  expect(screen.getByRole('button', { name: /upgrade 1 endpoint/i })).toBeInTheDocument()
})

it('calls out the endpoints that need a manual reinstall', () => {
  render(
    <AgentUpgradeBanner
      agents={[outdated({ id: 1, self_upgrade_supported: false })]}
      onUpgradeAll={vi.fn()}
    />
  )
  expect(screen.getByText(/1 endpoint needs a manual reinstall/i)).toBeInTheDocument()
})

it('shows no action when nothing can be upgraded remotely', () => {
  render(
    <AgentUpgradeBanner
      agents={[outdated({ id: 1, self_upgrade_supported: false })]}
      onUpgradeAll={vi.fn()}
    />
  )
  expect(screen.queryByRole('button', { name: /upgrade/i })).toBeNull()
})

it('hands every upgradable endpoint to the handler', async () => {
  const onUpgradeAll = vi.fn()
  const agents = [outdated({ id: 1, self_upgrade_supported: true })]
  render(<AgentUpgradeBanner agents={agents} onUpgradeAll={onUpgradeAll} />)
  await userEvent.click(screen.getByRole('button', { name: /upgrade 1 endpoint/i }))
  expect(onUpgradeAll).toHaveBeenCalledWith(agents)
})
```

- [ ] **Step 2: Run them and confirm they fail**

Run:

```bash
cd frontend && npm run test -- src/pages/managed-agents/__tests__/AgentUpgradeBanner.test.tsx --run
```

Expected: FAIL, the banner renders no button.

- [ ] **Step 3: Add the action**

In `AgentUpgradeBanner.tsx`, keep the existing count, shared-target and
mixed-target copy exactly as it is. Add:

```tsx
  const upgradable = outdated.filter(canUpgradeNow)
  const manualOnly = outdated.length - upgradable.length
```

Render the manual-only sentence when `manualOnly > 0`, and an `Alert`
`action` button labelled
`t('managedAgents.page.upgrade.upgradeSelected', { count: upgradable.length })`
only when `onUpgradeAll && upgradable.length > 0`. The button count is
`upgradable.length`, never `outdated.length`: the number in the button is the
number that will move.

Replace the now-wrong `bannerManual` sentence, which tells the operator to
reinstall each one from its card, with copy that fits a fleet that can upgrade
itself. Keep the old string as the value of a new
`bannerManualOnly` key used for the endpoints that genuinely cannot.

Locale keys (all four files, under `managedAgents.page.upgrade`):

```json
"bannerManualOnly_one": "{{count}} endpoint needs a manual reinstall from its card before it can be upgraded from here.",
"bannerManualOnly_other": "{{count}} endpoints need a manual reinstall from their cards before they can be upgraded from here."
```

- [ ] **Step 4: Wire it through**

In `AgentList`, pass `onUpgradeAll={(list) => setUpgradeTargets(list)}` so
Upgrade all opens the same confirmation dialog the bulk bar opens, and
`busy={isUpgrading}`.

- [ ] **Step 5: Run the tests and confirm they pass**

Run:

```bash
cd frontend && npm run test -- src/pages/managed-agents --run
cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run
cd frontend && npm run check:locales
```

Expected: PASS.

- [ ] **Step 6: Update the stories**

`AgentUpgradeBanner.stories.tsx`: stories for the banner with an action, with
mixed targets, and with unsupported endpoints called out, in default and
mobile viewports.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/managed-agents frontend/src/pages/ManagedAgents.tsx \
  frontend/src/locales
git commit -m "feat(agents): upgrade the whole fleet from the banner"
```

### Task 8: Docs and phase verification

**Files:**
- Modify: `docs/managed-agents.md`
- Modify: `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md:553`

- [ ] **Step 1: Document the fleet upgrade**

Extend the remote upgrade section of `docs/managed-agents.md` (phase 3 added
it) with how a fleet upgrade behaves: select endpoints or use Upgrade all,
endpoints are upgraded at most `AGENT_UPGRADE_CONCURRENCY` (5) at a time, a
waiting endpoint shows "Waiting to upgrade" and starts on its own, an endpoint
that does not come back within 600 seconds is marked failed and skipped by
later waves until an operator acts on it, and endpoints without the
self-upgrade helper still need one manual reinstall.

- [ ] **Step 2: Run the full required checks**

```bash
ruff check app tests
ruff format --check app tests
pytest tests/unit -q
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run test -- --run
cd frontend && npm run build
```

Storybook needs Node 20.19+ via fnm before `npm run snapshots`.

- [ ] **Step 3: Verify the phase gate by hand**

The gate is: a fleet of endpoints upgrades in waves, and no more than the cap
are in flight at once. With the local stack running and more than five agents
registered (or `AGENT_UPGRADE_CONCURRENCY` temporarily lowered), press Upgrade
all and confirm that at most the cap show "Upgrading", the rest show "Waiting
to upgrade", and waiting endpoints start on their own as slots free.

- [ ] **Step 4: Update the spec progress table**

Set phase 4's row to `done` with this plan's path and the branch
`feat/agent-upgrades-phase-4`. Note the three decisions from the top of this
plan in the Notes column, condensed.

- [ ] **Step 5: Commit**

```bash
git add docs
git commit -m "docs(agents): document fleet upgrades and mark phase 4 done"
```
