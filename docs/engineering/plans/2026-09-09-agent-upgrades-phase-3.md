# Agent upgrades phase 3: single-agent remote upgrade

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** An operator clicks Upgrade on one managed agent row and that endpoint
reinstalls itself, with the server owning the outcome, so the row resolves to
up to date without anyone touching the machine.

**Architecture:** Phase 2 shipped the mechanism on the endpoint: a root helper,
a `oneshot` unit, and a systemd `.path` unit watching
`/etc/borg-ui-agent/upgrade-requested`. Phase 3 pulls the trigger. A new
`agent.upgrade` session command makes the agent create that one empty file
after re-checking the same readiness predicate the capability probe uses. A new
`POST /api/managed-machines/agents/upgrade` endpoint validates the whole
request, creates one `agent_upgrade` job per agent, dispatches the command, and
records `upgrade_state="requested"` with the target version. The agent is
killed by the thing it is reporting on, so the server resolves the outcome:
success when the endpoint re-registers on the target version, failure by
timeout in the existing agent job reaper.

**Tech Stack:** FastAPI, SQLAlchemy, systemd, React, MUI, i18next, Storybook,
pytest, vitest.

**Spec:** `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`
(sections 5, 7, 7.1, 9, 13.4)

## Global Constraints

- **The spec's section 7 is partly stale.** It describes the agent running
  `sudo -n systemctl start --no-block borg-ui-agent-upgrade.service`. Phase 2
  review replaced that with the `.path` unit (see the amendment box in spec
  section 6): the agent unit sets `NoNewPrivileges=true`, under which `sudo`
  refuses to run. **The shipped trigger is creating the file
  `/etc/borg-ui-agent/upgrade-requested`.** No sudo, no systemctl, no argv.
  Read section 7's steps 1, 2 and 4 as current, and step 3 as "create the
  trigger file".
- No em dashes in UI copy, i18n strings, code comments, or commit messages.
- Every new i18n key goes into all four locales:
  `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`. The
  `frontend-locale-check` pre-push hook fails otherwise.
- No heavy left accent borders on cards, panels, alerts, or status surfaces
  (`AGENTS.md`, UI Preferences).
- New or changed UI ships a Storybook story for the changed state, in default
  and mobile viewports, following `ManagedAgents.stories.tsx` conventions.
- New UI components go in `frontend/src/pages/managed-agents/`, not inline in
  `ManagedAgents.tsx`, which is over 2000 lines.
- Do not register `managed-machines` routes in `ENDPOINT_POLICIES`
  (`app/core/authorization.py`); that router authorizes through
  `get_current_admin_user` / `require_managed_agents_admin_user` in each route
  signature (spec section 11.2).
- **Phase 3 is one agent at a time.** The endpoint accepts a list because the
  spec defines it that way and phase 4 reuses it, but no wave scheduler, no
  multi-select, and no Upgrade all action land here. `AgentUpgradeBanner` stays
  informational.
- Do not re-open a decision in the spec's Appendix B.

---

## File structure

| File | Responsibility |
| --- | --- |
| `agent/borg_ui_agent/session.py` | Dispatch `agent.upgrade` and handle it: busy check, readiness re-check, create the trigger. |
| `app/core/agent_constants.py` | `AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS`, `AGENT_UPGRADE_TIMEOUT_SECONDS`. |
| `app/api/managed_machines.py` | `POST /agents/upgrade`: validation, dedup, idempotency, job creation, dispatch, state write. |
| `app/api/agents.py` | Clear `upgrade_state` when an endpoint re-registers on its target version (register and hello paths). |
| `app/services/agent_job_reaper.py` | Sweep stale `requested` upgrades to `failed`. |
| `frontend/src/services/api.ts` | `upgradeAgents`, `setAgentDesiredVersion`. |
| `frontend/src/pages/managed-agents/AgentUpgradeDialog.tsx` | Confirmation dialog for one endpoint. |
| `frontend/src/pages/managed-agents/AgentUpgradeStateChip.tsx` | Row state for `requested` and `failed`. |
| `frontend/src/pages/managed-agents/AgentPinControl.tsx` | Desired agent version and desired Borg major version. |
| `frontend/src/pages/ManagedAgents.tsx` | Row action wiring, dialog state, manual path routing. |

---

### Task 1: The `agent.upgrade` session command

**Files:**
- Modify: `agent/borg_ui_agent/session.py` (dispatch block around line 593, new
  handler next to `_handle_diagnostics` around line 738, and the non-job command
  list in `_job_id_for_dispatch` around line 530)
- Test: `tests/unit/test_agent_upgrade_command.py` (create)

**Interfaces:**
- Consumes: `check_self_upgrade()` and `UpgradeReadiness` from
  `agent/borg_ui_agent/self_upgrade.py` (phase 2). `UpgradeReadiness` carries
  `supported: bool`, `reason: str`, `trigger: Optional[Path]`.
- Produces: session command `agent.upgrade`, taking an empty payload, replying
  `{"success": True, "trigger": "<path>"}` on success and `command_error` with
  code `upgrade_busy` or `upgrade_unsupported` otherwise.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_upgrade_command.py`:

```python
"""The agent's side of a remote upgrade: create one empty file.

The trigger is a systemd .path unit, so the agent needs no sudo and passes no
arguments. It re-checks readiness rather than trusting the capability it last
reported, because the endpoint may have changed since.
"""

import json
import queue
from pathlib import Path

import pytest

from agent.borg_ui_agent.config import AgentConfig
from agent.borg_ui_agent.session import AgentSessionRuntime
from agent.borg_ui_agent.self_upgrade import UpgradeReadiness


def _drain(outbox):
    frames = []
    while not outbox.empty():
        frames.append(json.loads(outbox.get_nowait()))
    return frames


@pytest.fixture
def session(monkeypatch):
    return AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: None,
        http_client=_HttpClient(),
    )


def _run(session, outbox, monkeypatch, readiness, running_ids=()):
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.check_self_upgrade", lambda: readiness
    )
    monkeypatch.setattr(
        AgentSessionRuntime, "_running_job_ids", lambda self: list(running_ids)
    )
    session._handle_command(
        outbox, {"command_id": "c1", "command": "agent.upgrade", "payload": {}}
    )


def test_upgrade_creates_the_trigger_file(session, tmp_path, monkeypatch):
    trigger = tmp_path / "upgrade-requested"
    outbox: "queue.Queue[str]" = queue.Queue()

    _run(
        session,
        outbox,
        monkeypatch,
        UpgradeReadiness(supported=True, trigger=trigger),
    )

    assert trigger.is_file()
    results = [f for f in _drain(outbox) if f["type"] == "command_result"]
    assert results[0]["result"] == {"success": True, "trigger": str(trigger)}


def test_upgrade_refuses_while_a_job_is_running(session, tmp_path, monkeypatch):
    trigger = tmp_path / "upgrade-requested"
    outbox: "queue.Queue[str]" = queue.Queue()

    _run(
        session,
        outbox,
        monkeypatch,
        UpgradeReadiness(supported=True, trigger=trigger),
        running_ids=(7,),
    )

    assert not trigger.exists()
    errors = [f for f in _drain(outbox) if f["type"] == "command_error"]
    assert errors[0]["error"]["code"] == "upgrade_busy"


@pytest.mark.parametrize(
    "reason",
    ["unit_missing", "helper_missing", "conf_missing", "path_unit_missing"],
)
def test_upgrade_refuses_when_unsupported(session, tmp_path, monkeypatch, reason):
    outbox: "queue.Queue[str]" = queue.Queue()

    _run(
        session,
        outbox,
        monkeypatch,
        UpgradeReadiness(supported=False, reason=reason),
    )

    errors = [f for f in _drain(outbox) if f["type"] == "command_error"]
    assert errors[0]["error"]["code"] == "upgrade_unsupported"
    assert reason in errors[0]["error"]["message"]


def test_upgrade_reports_an_unwritable_trigger_rather_than_dying(
    session, tmp_path, monkeypatch
):
    trigger = tmp_path / "missing-dir" / "upgrade-requested"
    outbox: "queue.Queue[str]" = queue.Queue()

    _run(
        session,
        outbox,
        monkeypatch,
        UpgradeReadiness(supported=True, trigger=trigger),
    )

    errors = [f for f in _drain(outbox) if f["type"] == "command_error"]
    assert errors[0]["error"]["code"] == "upgrade_failed"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_upgrade_command.py -v`
Expected: FAIL, `check_self_upgrade` is not an attribute of
`agent.borg_ui_agent.session`.

- [ ] **Step 3: Implement the handler**

In `agent/borg_ui_agent/session.py`, import the predicate next to the other
agent imports:

```python
from agent.borg_ui_agent.self_upgrade import check_self_upgrade
```

Add `"agent.upgrade"` to the tuple of non-job commands in
`_job_id_for_dispatch` (it carries no `job_id`, so it must not be registered
for cancellation):

```python
        if command in (
            "filesystem.browse",
            "diagnostics.run",
            "agent.repository_defaults",
            "agent.list_scripts",
            "agent.upgrade",
            "cancel",
        ):
            return None
```

Dispatch it in `_handle_command`, next to `diagnostics.run`:

```python
        if command == "agent.upgrade":
            self._handle_upgrade(client)
            return
```

Add the handler next to `_handle_diagnostics`:

```python
    def _handle_upgrade(self, client: SessionCommandClient) -> None:
        """Ask this endpoint to reinstall itself.

        The whole action is creating one empty file that nothing reads: a
        systemd .path unit watches it and starts the root helper, which takes
        no arguments and reads every parameter from a root-owned config. The
        agent therefore names no version and passes no argv.

        Readiness is re-checked rather than trusted. The capability was
        reported at connect time and the endpoint may have been changed since.
        """
        running = self._running_job_ids()
        if running:
            # An upgrade restarts this process, which would orphan whatever
            # job is running under it.
            client.send_error(
                f"Agent is running jobs {running}", code="upgrade_busy"
            )
            return

        readiness = check_self_upgrade()
        if not readiness.supported or readiness.trigger is None:
            client.send_error(
                f"Endpoint cannot upgrade itself: {readiness.reason}",
                code="upgrade_unsupported",
            )
            return

        try:
            readiness.trigger.touch()
        except OSError as exc:
            client.send_error(f"Could not request upgrade: {exc}", code="upgrade_failed")
            return

        logger.info("Upgrade requested", trigger=str(readiness.trigger))
        client.send_result({"success": True, "trigger": str(readiness.trigger)})
```

If `session.py` has no `logger` in scope, drop the `logger.info` line rather
than adding a logging dependency for one line.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_agent_upgrade_command.py -v`
Expected: PASS, all six cases.

- [ ] **Step 5: Run the neighbouring agent suites**

Run: `pytest tests/unit/test_agent_runtime.py tests/unit/test_agent_self_upgrade.py -q`
Expected: PASS, no regressions in the session dispatch tests.

- [ ] **Step 6: Commit**

```bash
git add agent/borg_ui_agent/session.py tests/unit/test_agent_upgrade_command.py
git commit -m "feat(agents): add the agent.upgrade session command"
```

---

### Task 2: The upgrade endpoint and the `agent_upgrade` job

**Files:**
- Modify: `app/core/agent_constants.py`
- Modify: `app/api/managed_machines.py` (request model near the other Pydantic
  models around line 110, route after `set_agent_desired_version` around line
  580)
- Modify: `frontend/src/locales/{en,de,es,it}.json` (the two new
  `backend.errors.agents.*` keys)
- Test: `tests/unit/test_api_agent_upgrade.py` (create)

**Interfaces:**
- Consumes: `agent.upgrade` from Task 1; `compute_agent_upgrade_status` and
  `agent_package_version` from `app/core/agent_versions.py`;
  `agent_connection_manager.send_command` and the `AgentConnectionUnavailable`
  / `AgentCommandTimeout` / `AgentCommandError` exceptions already imported in
  `managed_machines.py`.
- Produces: `POST /api/managed-machines/agents/upgrade` taking
  `{"agent_machine_ids": [int, ...]}` and returning
  `{"results": [{"agent_machine_id": int, "job_id": int, "state": str}]}`.
  `state` is one of `requested`, `failed`. Also
  `AGENT_UPGRADE_TIMEOUT_SECONDS = 600` and
  `AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS = 15.0`, consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_api_agent_upgrade.py`. Follow the client and admin
fixtures already used in `tests/unit/test_api_managed_machines.py`; copy that
file's fixture setup verbatim rather than inventing new ones.

```python
"""POST /managed-machines/agents/upgrade.

Validation runs over the whole request before any job is created: a partial
success that reports as a full one is the failure mode to avoid.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import AgentJob, AgentMachine


def _agent(db, **overrides):
    now = datetime.now(timezone.utc)
    agent = AgentMachine(
        name=overrides.pop("name", "endpoint"),
        agent_id=overrides.pop("agent_id", "agt_test"),
        token_hash="x",
        token_prefix="borgui_a",
        status="online",
        agent_version="0.1.2",
        capabilities=["self_upgrade"],
        created_at=now,
        updated_at=now,
        **overrides,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def test_upgrade_queues_a_job_and_marks_the_agent_requested(
    client, db, admin_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    sent = []

    async def fake_send_command(agent_id, **kwargs):
        sent.append((agent_id, kwargs["command"]))
        return {"success": True}

    monkeypatch.setattr(
        "app.api.managed_machines.agent_connection_manager.send_command",
        fake_send_command,
    )
    agent = _agent(db)

    response = client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["state"] == "requested"
    job = db.query(AgentJob).filter(AgentJob.id == result["job_id"]).one()
    assert job.job_type == "agent_upgrade"
    assert job.status == "completed"
    db.refresh(agent)
    assert agent.upgrade_state == "requested"
    assert agent.upgrade_target_version == "0.1.3"
    assert sent == [(agent.id, "agent.upgrade")]


def test_upgrade_rejects_the_whole_request_when_one_agent_is_unsupported(
    client, db, admin_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    ok = _agent(db, agent_id="agt_ok")
    bad = _agent(db, agent_id="agt_bad", name="old", capabilities=["jobs.poll"])

    response = client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [ok.id, bad.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.agents.upgradeUnsupported"
    )
    assert db.query(AgentJob).count() == 0


def test_upgrade_rejects_an_unpinned_agent_when_the_server_serves_no_wheel(
    client, db, admin_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: None
    )
    agent = _agent(db)

    response = client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.agents.upgradeTargetUnavailable"
    )
    assert db.query(AgentJob).count() == 0


def test_duplicate_ids_create_one_job(client, db, admin_headers, monkeypatch):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )

    async def fake_send_command(agent_id, **kwargs):
        return {"success": True}

    monkeypatch.setattr(
        "app.api.managed_machines.agent_connection_manager.send_command",
        fake_send_command,
    )
    agent = _agent(db)

    response = client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id, agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert db.query(AgentJob).count() == 1


def test_a_second_request_returns_the_in_flight_upgrade(
    client, db, admin_headers, monkeypatch
):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )
    calls = []

    async def fake_send_command(agent_id, **kwargs):
        calls.append(agent_id)
        return {"success": True}

    monkeypatch.setattr(
        "app.api.managed_machines.agent_connection_manager.send_command",
        fake_send_command,
    )
    agent = _agent(db)
    body = {"agent_machine_ids": [agent.id]}

    first = client.post(
        "/api/managed-machines/agents/upgrade", json=body, headers=admin_headers
    )
    second = client.post(
        "/api/managed-machines/agents/upgrade", json=body, headers=admin_headers
    )

    assert first.json()["results"][0]["job_id"] == second.json()["results"][0]["job_id"]
    assert db.query(AgentJob).count() == 1
    assert calls == [agent.id]


def test_an_offline_agent_fails_its_job_and_stays_idle(
    client, db, admin_headers, monkeypatch
):
    from app.services.agent_connection_manager import AgentConnectionUnavailable

    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )

    async def fake_send_command(agent_id, **kwargs):
        raise AgentConnectionUnavailable("offline")

    monkeypatch.setattr(
        "app.api.managed_machines.agent_connection_manager.send_command",
        fake_send_command,
    )
    agent = _agent(db)

    response = client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["state"] == "failed"
    db.refresh(agent)
    assert agent.upgrade_state == "failed"
    assert agent.upgrade_error
    job = db.query(AgentJob).one()
    assert job.status == "failed"
```

Check the import path of `AgentConnectionUnavailable` against the one
`app/api/managed_machines.py` already uses and match it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_api_agent_upgrade.py -v`
Expected: FAIL with 404 on every request, the route does not exist.

- [ ] **Step 3: Add the constants**

In `app/core/agent_constants.py`:

```python
# How long the server waits for an endpoint to acknowledge agent.upgrade. The
# agent only creates a file, so this bounds the round trip, not the reinstall.
AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS = 15.0

# How long an endpoint has to come back on its target version before the
# upgrade is called failed. Generous on purpose: an endpoint that hits this is
# far more likely broken than slow.
AGENT_UPGRADE_TIMEOUT_SECONDS = 600
```

- [ ] **Step 4: Implement the route**

In `app/api/managed_machines.py`, add the request model next to the other
Pydantic models:

```python
class AgentUpgradeRequest(BaseModel):
    agent_machine_ids: list[int]
```

Add the route after `set_agent_desired_version`:

```python
UPGRADE_IN_FLIGHT_STATUSES = ("queued", "claimed", "running", "cancel_requested")


@router.post("/agents/upgrade")
async def upgrade_agent_machines(
    payload: AgentUpgradeRequest,
    current_user: User = Depends(require_managed_agents_admin_user),
    db: Session = Depends(get_db),
):
    """Ask each named endpoint to reinstall itself.

    Validation runs over the whole request before anything is created: a
    partial success that reports as a full one is the failure mode to avoid.
    The agent is killed by the thing it is reporting on, so the job records
    only that the upgrade was requested; the outcome is resolved by the
    register path and the reaper (spec section 7.1).
    """
    # Deduplicated first: an upgrade restarts the endpoint, so two jobs for one
    # machine could restart it twice or race two reinstalls.
    wanted = list(dict.fromkeys(payload.agent_machine_ids))
    agents = (
        db.query(AgentMachine)
        .filter(AgentMachine.id.in_(wanted), AgentMachine.status != "deleted")
        .all()
        if wanted
        else []
    )
    found = {agent.id: agent for agent in agents}
    if len(found) != len(wanted):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"key": "backend.errors.agents.agentNotFound"},
        )

    available = agent_package_version()
    for agent_id in wanted:
        agent = found[agent_id]
        if not (agent.capabilities and "self_upgrade" in agent.capabilities):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.agents.upgradeUnsupported"},
            )
        if not (agent.desired_agent_version or available):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"key": "backend.errors.agents.upgradeTargetUnavailable"},
            )

    results = []
    for agent_id in wanted:
        agent = found[agent_id]
        existing = (
            db.query(AgentJob)
            .filter(
                AgentJob.agent_machine_id == agent.id,
                AgentJob.job_type == "agent_upgrade",
                AgentJob.status.in_(UPGRADE_IN_FLIGHT_STATUSES),
            )
            .first()
        )
        if existing is not None or agent.upgrade_state == "requested":
            # Idempotent under a double click or a client retry.
            results.append(
                {
                    "agent_machine_id": agent.id,
                    "job_id": existing.id if existing else None,
                    "state": agent.upgrade_state or "requested",
                }
            )
            continue

        results.append(
            await _request_agent_upgrade(
                db, agent, target=agent.desired_agent_version or available
            )
        )

    logger.info(
        "Agent upgrades requested",
        user=current_user.username,
        agent_machine_ids=wanted,
    )
    return {"results": results}


async def _request_agent_upgrade(db: Session, agent: AgentMachine, *, target: str):
    """Create the job, dispatch the command, and record the outcome for one
    endpoint. The job is completed at "upgrade started": it records that the
    upgrade was successfully requested, nothing more."""
    now = _now_utc()
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="agent_upgrade",
        status="running",
        payload={"target_version": target},
        created_at=now,
        updated_at=now,
        started_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        await agent_connection_manager.send_command(
            agent.id,
            command="agent.upgrade",
            payload={},
            timeout_seconds=AGENT_UPGRADE_COMMAND_TIMEOUT_SECONDS,
            wait_for_result=True,
        )
    except (
        AgentConnectionUnavailable,
        AgentCommandTimeout,
        AgentCommandError,
    ) as exc:
        finished = _now_utc()
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = finished
        job.updated_at = finished
        agent.upgrade_state = "failed"
        agent.upgrade_error = str(exc)
        agent.upgrade_target_version = target
        agent.updated_at = finished
        db.commit()
        return {
            "agent_machine_id": agent.id,
            "job_id": job.id,
            "state": "failed",
        }

    finished = _now_utc()
    job.status = "completed"
    job.completed_at = finished
    job.updated_at = finished
    agent.upgrade_state = "requested"
    agent.upgrade_requested_at = finished
    agent.upgrade_target_version = target
    agent.upgrade_error = None
    agent.updated_at = finished
    db.commit()
    return {"agent_machine_id": agent.id, "job_id": job.id, "state": "requested"}
```

Import the two new constants from `app.core.agent_constants` at the top of the
file, alongside the existing agent constant imports.

- [ ] **Step 5: Add the error copy to all four locales**

Under `backend.errors.agents` in `frontend/src/locales/en.json`, keeping the
block's alphabetical neighbours intact:

```json
"upgradeUnsupported": "This endpoint cannot upgrade itself yet. Reinstall it once from the command shown in the reinstall dialog.",
"upgradeTargetUnavailable": "This server does not ship an agent version to upgrade to."
```

Translate both into `de.json`, `es.json` and `it.json`, matching the tone of
the surrounding keys in each file.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_agent_upgrade.py tests/unit/test_api_managed_machines.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/core/agent_constants.py app/api/managed_machines.py \
  tests/unit/test_api_agent_upgrade.py frontend/src/locales
git commit -m "feat(agents): add the agent upgrade endpoint and job type"
```

---

### Task 3: Reconciliation, success and timeout

**Files:**
- Modify: `app/api/agents.py` (the register path around line 1239 and the
  session hello path around line 1307)
- Modify: `app/services/agent_job_reaper.py`
- Test: `tests/unit/test_agent_upgrade_reconciliation.py` (create)

**Interfaces:**
- Consumes: `AGENT_UPGRADE_TIMEOUT_SECONDS` from Task 2; the
  `upgrade_state` / `upgrade_requested_at` / `upgrade_target_version` /
  `upgrade_error` columns from phase 1.
- Produces: `resolve_agent_upgrade(agent)` in `app/api/agents.py`, called from
  both re-entry paths; `reap_stale_agent_upgrades(db, *, now=None,
  timeout=AGENT_UPGRADE_TIMEOUT_SECONDS)` in `app/services/agent_job_reaper.py`,
  returning the number of agents marked failed.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_agent_upgrade_reconciliation.py`:

```python
"""The agent is killed by the thing it is reporting on, so the server owns the
outcome: success on re-entry with the target version, failure by timeout."""

from datetime import datetime, timedelta, timezone

from app.api.agents import resolve_agent_upgrade
from app.database.models import AgentMachine
from app.services.agent_job_reaper import reap_stale_agent_upgrades


def _requested(db, *, reported, requested_at):
    now = datetime.now(timezone.utc)
    agent = AgentMachine(
        name="endpoint",
        agent_id="agt_recon",
        token_hash="x",
        token_prefix="borgui_a",
        status="online",
        agent_version=reported,
        upgrade_state="requested",
        upgrade_requested_at=requested_at,
        upgrade_target_version="0.1.3",
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def test_re_registering_on_the_target_version_clears_the_upgrade(db):
    agent = _requested(
        db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )
    agent.agent_version = "0.1.3"

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "idle"
    assert agent.upgrade_error is None


def test_re_registering_on_the_old_version_leaves_it_requested(db):
    agent = _requested(
        db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )

    resolve_agent_upgrade(agent)

    # The reinstall may still be mid flight. Only the timeout resolves it.
    assert agent.upgrade_state == "requested"


def test_the_reaper_fails_a_stale_upgrade(db):
    agent = _requested(
        db,
        reported="0.1.2",
        requested_at=datetime.now(timezone.utc) - timedelta(seconds=1200),
    )

    assert reap_stale_agent_upgrades(db) == 1

    db.refresh(agent)
    assert agent.upgrade_state == "failed"
    assert agent.upgrade_error


def test_the_reaper_leaves_a_fresh_upgrade_alone(db):
    agent = _requested(
        db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )

    assert reap_stale_agent_upgrades(db) == 0

    db.refresh(agent)
    assert agent.upgrade_state == "requested"
```

Use whatever `db` session fixture `tests/unit/test_api_managed_machines.py`
uses; do not add a new one.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_agent_upgrade_reconciliation.py -v`
Expected: FAIL, `resolve_agent_upgrade` and `reap_stale_agent_upgrades` do not
exist.

- [ ] **Step 3: Implement the success path**

In `app/api/agents.py`, add next to the other module-level helpers:

```python
def resolve_agent_upgrade(agent: AgentMachine) -> None:
    """Clear a requested upgrade when the endpoint comes back on its target.

    An endpoint that comes back on the old version is left in `requested`: the
    reinstall may still be mid flight, and only the timeout resolves it.
    """
    if agent.upgrade_state != "requested":
        return
    if agent.upgrade_target_version and agent.agent_version == (
        agent.upgrade_target_version
    ):
        agent.upgrade_state = "idle"
        agent.upgrade_error = None
        agent.upgrade_requested_at = None
```

Call it in both re-entry paths, immediately after `agent_version` is assigned:
once in the register handler (around line 1239) and once in the session hello
handler (around line 1307).

- [ ] **Step 4: Implement the timeout path**

In `app/services/agent_job_reaper.py`:

```python
def reap_stale_agent_upgrades(
    db: Session,
    *,
    now: Optional[datetime] = None,
    timeout_seconds: int = AGENT_UPGRADE_TIMEOUT_SECONDS,
) -> int:
    """Mark upgrades whose endpoint never came back as failed.

    The cap in a fleet upgrade bounds upgrades in flight, not endpoints
    offline, so this frees the slot even though the endpoint may still be mid
    reinstall. Holding the slot instead would let one machine that never comes
    back stall every remaining upgrade in the fleet.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=timeout_seconds)
    stale = (
        db.query(AgentMachine)
        .filter(
            AgentMachine.upgrade_state == "requested",
            AgentMachine.upgrade_requested_at.isnot(None),
            AgentMachine.upgrade_requested_at < cutoff,
        )
        .all()
    )
    for agent in stale:
        agent.upgrade_state = "failed"
        agent.upgrade_error = (
            "The endpoint did not come back on the target version in time. "
            "Reinstall it manually from the reinstall dialog."
        )
        agent.updated_at = now
    if stale:
        db.commit()
        logger.info("Reaped stale agent upgrades", count=len(stale))
    return len(stale)
```

Import `AgentMachine` and `AGENT_UPGRADE_TIMEOUT_SECONDS` at the top of the
file, and call it from `_reap_once` next to the other reconcilers:

```python
        reaped += reap_stale_agent_upgrades(db)
```

Note the timestamp comparison: `upgrade_requested_at` is stored naive in
SQLite. If the query returns nothing in the test, compare with
`_as_utc(agent.upgrade_requested_at)` in Python over the `requested` rows
rather than in the `WHERE` clause, matching how `_job_activity_at` already
sidesteps this.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_agent_upgrade_reconciliation.py tests/unit/test_api_agents.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/agents.py app/services/agent_job_reaper.py \
  tests/unit/test_agent_upgrade_reconciliation.py
git commit -m "feat(agents): resolve upgrade outcomes on re-entry and by timeout"
```

---

### Task 4: The upgrade action, dialog, and row state

**Files:**
- Modify: `frontend/src/services/api.ts` (agents block around line 1367)
- Create: `frontend/src/pages/managed-agents/AgentUpgradeDialog.tsx`
- Create: `frontend/src/pages/managed-agents/AgentUpgradeDialog.stories.tsx`
- Create: `frontend/src/pages/managed-agents/AgentUpgradeStateChip.tsx`
- Create: `frontend/src/pages/managed-agents/AgentUpgradeStateChip.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx` (version cell around line 1725,
  row actions around line 1929, dialog mount around line 2018)
- Modify: `frontend/src/locales/{en,de,es,it}.json`
- Test: `frontend/src/pages/managed-agents/__tests__/AgentUpgradeDialog.test.tsx`,
  `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

**Interfaces:**
- Consumes: `POST /managed-machines/agents/upgrade` from Task 2; the existing
  `AgentUpgradeChip`, `AgentManualUpgradeChip` and `AgentReinstallDialog`.
- Produces: `agentsApi.upgradeAgents(agentIds: number[])`;
  `<AgentUpgradeDialog open agent onConfirm onCancel busy />`;
  `<AgentUpgradeStateChip state={'requested' | 'failed'} targetVersion error />`.

- [ ] **Step 1: Write the failing tests**

Create
`frontend/src/pages/managed-agents/__tests__/AgentUpgradeDialog.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AgentUpgradeDialog from '../AgentUpgradeDialog'

const agent = {
  id: 1,
  name: 'db-01',
  hostname: 'db-01.internal',
  agent_version: '0.1.2',
  available_agent_version: '0.1.3',
} as never

describe('AgentUpgradeDialog', () => {
  it('names the endpoint and its target version', () => {
    render(
      <AgentUpgradeDialog open agent={agent} onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    expect(screen.getByText(/db-01/)).toBeInTheDocument()
    expect(screen.getByText(/0\.1\.3/)).toBeInTheDocument()
  })

  it('confirms once', () => {
    const onConfirm = vi.fn()
    render(
      <AgentUpgradeDialog open agent={agent} onConfirm={onConfirm} onCancel={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /upgrade/i }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })
})
```

Add to `frontend/src/pages/__tests__/ManagedAgents.test.tsx`, following that
file's existing render helper and API mocks:

```tsx
  it('routes an endpoint without self upgrade support to the reinstall dialog', async () => {
    renderPage([
      { ...baseAgent, id: 1, self_upgrade_supported: false, upgrade_status: 'outdated' },
    ])
    fireEvent.click(await screen.findByRole('button', { name: /reinstall/i }))
    expect(await screen.findByText(/reinstall/i)).toBeInTheDocument()
  })

  it('offers the upgrade action to a supported outdated endpoint', async () => {
    renderPage([
      { ...baseAgent, id: 1, self_upgrade_supported: true, upgrade_status: 'outdated' },
    ])
    expect(await screen.findByRole('button', { name: /upgrade/i })).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/managed-agents/__tests__/AgentUpgradeDialog.test.tsx`
Expected: FAIL, the module does not exist.

- [ ] **Step 3: Add the API client call**

In `frontend/src/services/api.ts`, in the agents block:

```ts
  upgradeAgents: (agentIds: number[]) =>
    api.post<{ results: { agent_machine_id: number; job_id: number | null; state: string }[] }>(
      '/managed-machines/agents/upgrade',
      { agent_machine_ids: agentIds }
    ),
```

- [ ] **Step 4: Build the dialog**

Create `frontend/src/pages/managed-agents/AgentUpgradeDialog.tsx` using
`ResponsiveDialog` the same way `AgentReinstallDialog` in `ManagedAgents.tsx`
does. It states plainly that the endpoint disconnects for a short period and
that a running backup blocks the upgrade, names the endpoint by name and
hostname, and names the target version
(`agent.desired_agent_version ?? agent.available_agent_version`). Confirm calls
`onConfirm`; the confirm button is disabled while `busy`.

New i18n keys under `managedAgents.page.upgradeDialog`, in all four locales:
`title`, `description`, `disconnectWarning`, `busyWarning`, `targetVersion`,
`confirm`, `cancel`.

- [ ] **Step 5: Build the row state chip**

Create `frontend/src/pages/managed-agents/AgentUpgradeStateChip.tsx`. For
`requested` it renders a small `CircularProgress` and "Upgrading to vX.Y.Z";
for `failed` it renders an error chip carrying `upgrade_error`. Reuse
`agentChipSx.ts` so it matches `AgentUpgradeChip`. No left accent borders.

New i18n keys under `managedAgents.page.upgradeState`: `upgrading`, `failed`,
`failedHint`.

- [ ] **Step 6: Wire the page**

In `frontend/src/pages/ManagedAgents.tsx`:

- Render `<AgentUpgradeStateChip>` in the version cell when
  `agent.upgrade_state` is `requested` or `failed`, next to the existing
  `AgentUpgradeChip`.
- Add an Upgrade icon button to the row actions, shown only when
  `agent.self_upgrade_supported === true` and `agent.upgrade_status` is
  `outdated`, disabled while `agent.upgrade_state === 'requested'`. It opens
  `AgentUpgradeDialog`. The existing reinstall button stays as it is, so an
  endpoint with `self_upgrade_supported === false` keeps the manual path
  already wired to `AgentReinstallDialog`.
- Confirm calls `agentsApi.upgradeAgents([agent.id])`, then invalidates the
  agents query the page already uses. On a rejected promise, surface the
  `detail.key` through the page's existing error toast helper.
- Track the action with `trackSystem` following the `open_reinstall_dialog`
  call already in the file, with `operation: 'upgrade_agent'`.

- [ ] **Step 7: Write the stories**

`AgentUpgradeDialog.stories.tsx` and `AgentUpgradeStateChip.stories.tsx`, each
in default and mobile viewports, per `ManagedAgents.stories.tsx` conventions.
`AgentUpgradeStateChip` needs one story per state: upgrading and failed.

- [ ] **Step 8: Run the frontend checks**

```bash
cd frontend && npx vitest run src/pages/managed-agents src/pages/__tests__/ManagedAgents.test.tsx && npm run lint && npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add frontend/src
git commit -m "feat(agents): add the single-agent upgrade action and row state"
```

---

### Task 5: The pin control

**Files:**
- Modify: `frontend/src/services/api.ts`
- Create: `frontend/src/pages/managed-agents/AgentPinControl.tsx`
- Create: `frontend/src/pages/managed-agents/AgentPinControl.stories.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`
- Test: `frontend/src/pages/managed-agents/__tests__/AgentPinControl.test.tsx`

**Interfaces:**
- Consumes: `PUT /managed-machines/agents/{id}/desired-version`, shipped in
  phase 1, which accepts `{desired_agent_version, desired_borg_version}` and
  rejects a version this server cannot serve with
  `backend.errors.agents.desiredVersionUnavailable`.
- Produces: `agentsApi.setAgentDesiredVersion(agentId, body)`;
  `<AgentPinControl agent onSave busy />`.

- [ ] **Step 1: Write the failing test**

`frontend/src/pages/managed-agents/__tests__/AgentPinControl.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AgentPinControl from '../AgentPinControl'

const agent = {
  id: 1,
  desired_agent_version: null,
  desired_borg_version: null,
  available_agent_version: '0.1.3',
} as never

describe('AgentPinControl', () => {
  it('defaults to tracking the server', () => {
    render(<AgentPinControl agent={agent} onSave={vi.fn()} />)
    expect(screen.getByText(/track server/i)).toBeInTheDocument()
  })

  it('saves a cleared pin as null rather than an empty string', () => {
    const onSave = vi.fn()
    render(
      <AgentPinControl
        agent={{ ...agent, desired_agent_version: '0.1.3' } as never}
        onSave={onSave}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /clear pin/i }))
    expect(onSave).toHaveBeenCalledWith({
      desired_agent_version: null,
      desired_borg_version: null,
    })
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/managed-agents/__tests__/AgentPinControl.test.tsx`
Expected: FAIL, the module does not exist.

- [ ] **Step 3: Add the API client call**

```ts
  setAgentDesiredVersion: (
    agentId: number,
    data: { desired_agent_version: string | null; desired_borg_version: '1' | '2' | null }
  ) =>
    api.put<AgentMachineResponse>(
      `/managed-machines/agents/${agentId}/desired-version`,
      data
    ),
```

- [ ] **Step 4: Build the control**

Two MUI selects. The agent version select offers "Track server" (value `null`)
and `agent.available_agent_version`, because a pin to anything else is rejected
by the server: the installer installs from this server's wheelhouse and nowhere
else. The Borg select offers "Leave as installed" (`null`), `1` and `2`. Save
calls `onSave`. New i18n keys under `managedAgents.page.pinControl`:
`title`, `agentVersionLabel`, `trackServer`, `borgVersionLabel`,
`leaveAsInstalled`, `save`, `clearPin`, `hint`.

- [ ] **Step 5: Mount it and write the story**

Mount `AgentPinControl` in the agent detail area of `ManagedAgents.tsx`, wired
to `agentsApi.setAgentDesiredVersion` with the agents query invalidated on
success. Add `AgentPinControl.stories.tsx` with an unpinned and a pinned story,
each in default and mobile viewports.

- [ ] **Step 6: Run the frontend checks**

```bash
cd frontend && npx vitest run src/pages/managed-agents && npm run lint && npx tsc --noEmit
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(agents): add the desired version pin control"
```

---

### Task 6: Documentation and the spec progress table

**Files:**
- Modify: `docs/managed-agents.md`
- Modify: `docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`
  (the progress table, section 13.1)

- [ ] **Step 1: Document the operator-facing flow**

In `docs/managed-agents.md`, next to the remote-upgrade section phase 2 added,
describe: pressing Upgrade on a row, that the endpoint disconnects briefly,
that a running backup blocks the upgrade, that the row resolves itself when the
endpoint comes back, and what the failed state means (the endpoint did not come
back within 10 minutes, so reinstall it manually). Mention the pin control and
that a pin can only name a version this server serves.

- [ ] **Step 2: Run the full backend and frontend suites**

```bash
pytest tests/unit -q
```
```bash
cd frontend && npx vitest run && npm run lint && npx tsc --noEmit
```
Expected: PASS. `tests/unit/test_api_auth.py` failures in the main checkout are
a local `.env` artifact (`PUBLIC_BASE_URL`), not a regression.

- [ ] **Step 3: Update the spec progress table**

Set phase 3 to `in review`, with the plan file and branch filled in, and a note
recording that the trigger is the `.path` file, not the sudoers argv section 7
describes.

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs(agents): document remote upgrades and mark phase 3 in review"
```

---

## Self-review

**Spec coverage.** Section 5's upgrade endpoint: Task 2, including the two
error keys, dedup, and in-flight idempotency. Section 7's command: Task 1, with
the phase 2 amendment applied. Section 7.1's outcome ownership: Task 3, both
halves. Section 9's per-agent action, dialog, row upgrading state, row failed
state, manual-path routing, and pin control: Tasks 4 and 5. Section 12's
session command, bulk validation, reconciliation and frontend test bullets: the
test steps of Tasks 1, 2, 3 and 4.

**Deliberately not covered here**, all phase 4 or 5 by section 13: the wave
scheduler and `AGENT_UPGRADE_CONCURRENCY`, the `queued` upgrade state,
multi-select, the banner's Upgrade all action, and writing
`desired_borg_version` into `upgrade.conf` on the served reinstall (section 10,
phase 5). Phase 5 is what makes the Borg half of the pin control take effect;
until then it records intent only, which the control's hint should say.
