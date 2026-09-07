# Centralized agent upgrades

**Date:** 2026-09-07
**Status:** Approved for implementation
**Owner:** karanhudia
**Issue:** [#940](https://github.com/karanhudia/borg-ui/issues/940)
**Related docs:** `docs/managed-agents.md`, `docs/managed-agent-spec.md`,
`docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`

> **For agentic workers:** this spec is the single source of truth for the
> feature. Each phase in section 13 names its scope and its gate. Do not start
> a phase without the previous phase merged. Use `superpowers:writing-plans` to
> turn one phase into a task-level plan under `docs/engineering/plans/` before
> coding it. Use `superpowers:test-driven-development` inside every phase and
> `superpowers:verification-before-completion` before claiming a phase done.
> All UI work goes through the `ui-ux-pro-max` skill and ships Storybook
> stories, per `AGENTS.md`.
>
> Appendix A lists the existing code each phase touches, with file paths.
> Appendix B records decisions already made and the alternatives rejected. Do
> not re-open a decision in Appendix B; if you believe one is wrong, stop and
> ask the owner rather than implementing something different.

---

## 1. Problem

Keeping a fleet of managed agents current is entirely manual. The server
already knows everything it needs to know, and does nothing with it.

**The server knows the answer and does not show it.** Every agent reports
`agent_version` on register and on every heartbeat
(`app/api/agents.py:1186`), and the server knows the exact agent wheel it
serves (`agent_package_version()`, `app/api/agent_installer.py:797`). The two
are never compared. There is no way to answer "which of my endpoints are
behind?" short of reading a version string off each row and remembering what
the server ships.

**Upgrading is copy-paste, once per machine.** The Managed Agents page has a
"reinstall" action, but it only opens a dialog that renders a shell command
(`AgentReinstallDialog`, `frontend/src/pages/ManagedAgents.tsx:1468`). The
operator then has to reach each protected machine, get a root shell, and paste
it. For a fleet of any size this is the whole cost of the feature.

**The agent cannot upgrade itself, by design.** The recommended install runs
the agent as an unprivileged service user with `NoNewPrivileges=true`
(`app/api/agent_installer.py:741`). It cannot re-run the root installer, write
its own venv, or touch its own systemd unit. This is a good property and the
feature must not simply discard it.

**There is no notion of an intended version.** An endpoint's version is
whatever was installed on it. Nothing records what it *should* be running, so
there is nothing to reconcile against and no way to pin one endpoint while the
rest of the fleet moves.

## 2. User outcome

- An operator opens Managed Agents and sees, per endpoint, the agent version it
  runs and whether that is current. A banner names how many endpoints are
  behind.
- The operator selects out-of-date endpoints, clicks Upgrade, confirms a dialog
  that names exactly which machines will briefly disconnect, and watches each
  row move through upgrading to up to date without touching a single machine.
- An endpoint that must stay on an older agent is pinned, and it stops being
  counted as out of date.
- An endpoint whose install predates this feature is clearly labelled as
  needing a one-time manual reinstall, with the existing command dialog one
  click away. It is never silently skipped.
- The operator chooses which Borg major version an endpoint runs and applies it
  through the same upgrade path.

## 3. Non-goals

- **Server self-upgrade.** Issue #940 lists it as a stretch. It is a different
  problem (the server is a container or a native install managed by the host,
  not a thing the server can restart from inside itself) and is out of scope
  here. If wanted, it gets its own spec.
- **Downgrade.** The upgrade path installs the version the server serves or the
  version an endpoint is pinned to. Rolling an endpoint backwards is done by
  pinning and reinstalling manually.
- **Windows or macOS endpoints.** The privileged helper is systemd-specific,
  matching the current installer, which is Linux-only.
- **Upgrading the agent across a server upgrade in one step.** The server ships
  one agent wheel per image. Getting a newer agent means upgrading the server
  first. That is the existing model and this spec does not change it.

## 4. Version model

The core of the feature is a three-state model. Two-state ("does the reported
version match what the server ships?") is not enough, because section 10 gives
endpoints an intended version of their own.

| State | Source | Meaning |
| --- | --- | --- |
| **reported** | `AgentMachine.agent_version` | What the endpoint last told us it runs. `NULL` until first heartbeat. |
| **desired** | `AgentMachine.desired_agent_version` (new, nullable) | What this endpoint is pinned to. `NULL` means "track the server", which is the default and the normal case. |
| **available** | `agent_package_version()` | The agent wheel this server image serves. `NULL` on a server built without a bundled wheel. |

The **effective target** is `desired ?? available`.

`upgrade_status` is computed per agent on read, never stored:

| Status | Condition |
| --- | --- |
| `up_to_date` | `reported == effective_target` |
| `outdated` | both known, `reported != effective_target`, and `reported` orders below it |
| `ahead` | both known, `reported` orders above `effective_target` (server was rolled back) |
| `pinned` | `desired` is set and `reported == desired`, shown instead of `up_to_date` so the pin is visible |
| `unknown` | `reported` or `effective_target` is `NULL`, or either fails to parse |

Equality is the source of truth for "current"; ordering only separates
`outdated` from `ahead`. Comparison uses a small local parser that splits on
`.` and compares leading integer components, falling back to `unknown` when a
component does not parse. It does not add a `packaging` dependency for this
(see Appendix B, D3).

## 5. Server API surface

All routes live in `app/api/managed_machines.py` alongside the existing agent
routes and inherit its `authorize_request` dependency.

**`GET /api/managed-machines/agents`** — `AgentMachineResponse` gains:

```
desired_agent_version: str | None
available_agent_version: str | None
upgrade_status: Literal["up_to_date","outdated","ahead","pinned","unknown"]
self_upgrade_supported: bool          # "self_upgrade" in capabilities
upgrade_state: Literal["idle","requested","failed"] | None
upgrade_requested_at: datetime | None
upgrade_error: str | None
```

`available_agent_version` is resolved once per request, not per row.

**`POST /api/managed-machines/agents/upgrade`**

```
{ "agent_machine_ids": [int, ...] }
```

Queues one upgrade per named agent. Rejects with `422` and a
`backend.errors.agents.upgradeUnsupported` key if any named agent reports no
`self_upgrade` capability, rather than silently skipping it — a partial success
that looks like a full one is the failure mode to avoid. Returns the created
job ids and, per agent, the resulting state.

**`PUT /api/managed-machines/agents/{id}/desired-version`**

```
{ "desired_agent_version": str | null, "desired_borg_version": "1" | "2" | null }
```

Sets or clears the pin. Setting a `desired_agent_version` the server cannot
serve is rejected: the installer can only install from this server's
wheelhouse, so a pin to an unavailable version would be permanently
unsatisfiable.

## 6. The privileged helper

This is the load-bearing security design. The agent gets exactly one
escalation, and it carries no attacker-controlled input.

`install.sh` writes four root-owned artifacts. They are skipped entirely when
the service user is `root` (that case needs no escalation) and when the operator
passes `--no-remote-upgrade` (section 11.3). A reinstall preserves the existing
choice unless the flag is given explicitly, matching how the installer already
preserves the service user (`app/api/agent_installer.py:279`):

**`/etc/borg-ui-agent/upgrade.conf`** — mode `0644`, owned `root:root`. Records
the parameters a reinstall needs: server URL, borg install mode, service user
mode, service user and group, agent root. Written at install time from the
values the operator gave the installer.

**`/opt/borg-ui-agent/bin/borg-ui-agent-upgrade`** — mode `0755`, owned
`root:root`, in a root-owned directory. It takes **no arguments**. It reads
`upgrade.conf`, fetches `install.sh` from the recorded server, and runs it with
`--reinstall` and the recorded flags. Because every parameter comes from a
root-owned file rather than the caller, a compromised agent process cannot
redirect the install source, change the service user, or inject installer
flags. This is the property that makes the sudoers rule safe.

Before fetching anything it compares the server URL in `upgrade.conf` against
the one in `/etc/borg-ui-agent/config.toml` and aborts if they differ, so a
config left behind by an earlier enrollment cannot point a live agent's upgrade
at a host it no longer talks to.

**`/etc/sudoers.d/borg-ui-agent-upgrade`** — mode `0440`, granting the service
user exactly:

```
<service_user> ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block borg-ui-agent-upgrade.service
```

The `systemctl` path is resolved at install time with `command -v systemctl`
and written into both the sudoers rule and `upgrade.conf`, because sudoers
matches on the absolute path and it differs across distributions. The agent
invokes exactly that path, so the rule matches. Validated with `visudo -cf`
before being moved into place; a validation failure aborts that step with a
warning and leaves the endpoint on the manual path rather than writing a broken
sudoers file.

**`/etc/systemd/system/borg-ui-agent-upgrade.service`** — `Type=oneshot`,
`ExecStart=/opt/borg-ui-agent/bin/borg-ui-agent-upgrade`. It is not enabled;
it only ever runs when started. Running the reinstall inside a separate unit is
what lets the upgrade survive the restart of `borg-ui-agent` that it performs:
the upgrade is not in the agent's own process tree, so systemd killing the
agent does not kill the upgrade.

The agent advertises `self_upgrade` in `DEFAULT_CAPABILITIES`
(`agent/borg_ui_agent/runtime.py:19`) only when it can actually see the helper:
the unit file exists and `sudo -n systemctl start --no-block` for it passes
`sudo -l`. Capability is detected, not assumed, so an agent upgraded from an
older install that lacks the helper reports honestly and the UI routes it to
the manual path.

## 7. The upgrade command

New session command `agent.upgrade`, dispatched through the existing
`_handle_command` chain (`agent/borg_ui_agent/session.py:593`) next to
`diagnostics.run`.

Handler steps:

1. Refuse with `upgrade_busy` if this agent has any other job in flight. An
   upgrade restarts the process; doing it under a running backup would orphan
   that backup's job.
2. Refuse with `upgrade_unsupported` if the helper is not present.
3. Emit a log line, then run
   `sudo -n <systemctl path> start --no-block borg-ui-agent-upgrade.service`,
   using the absolute path recorded in `upgrade.conf` so the sudoers rule matches.
4. Report success and let the process die.

`--no-block` matters: the call returns as soon as systemd has queued the job,
so the agent gets to report "upgrade started" before the restart kills it.

### 7.1 The agent cannot report its own outcome

The agent is killed by the thing it is reporting on. Therefore **the server
owns the outcome**, and this is explicit rather than incidental:

- The `agent_upgrade` job is completed at "upgrade started". It records that
  the upgrade was successfully *requested*, nothing more.
- The server sets `upgrade_state = "requested"`, `upgrade_requested_at = now`,
  and `upgrade_target_version = <effective target>` on the agent machine.
- **Success** is recognised in the register/heartbeat path: an agent that comes
  back reporting `agent_version == upgrade_target_version` has its
  `upgrade_state` cleared to `idle`.
- **Failure** is recognised by timeout. A sweep in `agent_job_reaper` (which
  already runs on a timer for exactly this class of problem, see
  `app/services/agent_job_reaper.py:1`) marks any agent whose
  `upgrade_requested_at` is older than `AGENT_UPGRADE_TIMEOUT_SECONDS`
  (default 600) without a matching re-register as `upgrade_state = "failed"`,
  with a message pointing at the manual reinstall path.
- An agent that comes back reporting the *old* version before the timeout is
  left in `requested`; the reinstall may still be mid-flight. Only the timeout
  resolves it.

## 8. Fleet upgrades

`POST .../agents/upgrade` with many ids queues many jobs, but they are released
in waves of `AGENT_UPGRADE_CONCURRENCY` (default 5). Every upgrading endpoint
is briefly offline, and taking a whole fleet down at once turns a routine
maintenance action into an outage. Waves are advanced by the same reconciler
that resolves outcomes: a slot frees when an agent leaves `requested`, by
success or by timeout.

Jobs are ordinary `agent_jobs` rows with `job_type="agent_upgrade"`, so they
appear in the existing agent job list, logs, and activity views for free.

## 9. UI

All on the Managed Agents page (`frontend/src/pages/ManagedAgents.tsx`),
composed from small components per `AGENTS.md`, no left accent borders.

**Fleet banner** — shown only when at least one endpoint is `outdated`. Names
the count and the target version, with an Upgrade all action. Endpoints without
`self_upgrade_supported` are excluded from the count in the action and called
out separately, so the number in the button is the number that will actually
move.

**Per-agent version cell** — the reported version, with a chip: `Current`,
`Update available`, `Pinned`, `Ahead of server`, or `Unknown`. A pinned agent
shows the pin target next to it.

**Row state while upgrading** — the row shows a progress indicator and
"Upgrading…" with the target version, driven by `upgrade_state`. On timeout the
row shows a failure state with the error and a link to the existing reinstall
dialog.

**Upgrade dialog** — a `ResponsiveDialog` listing the affected endpoints by
name and hostname, stating plainly that each will disconnect for a short period
and that running backups block the upgrade. Confirm queues the jobs.

**Manual-path affordance** — an endpoint with `self_upgrade_supported: false`
gets an explanatory chip and its row action opens the existing
`AgentReinstallDialog` rather than the new one. The copy says this endpoint
needs one manual reinstall to gain remote upgrades, so the dead end is
explained rather than just presented.

**Pin control** — in the agent detail area, a select for the desired agent
version (default "Track server") and the desired Borg major version.

Stories are required for: fleet banner with and without unsupported endpoints,
each version-cell chip state, the row upgrading state, the row failed state,
the upgrade confirmation dialog, and the pin control. Each in default and
mobile viewports, per existing `ManagedAgents.stories.tsx` conventions.

## 10. Per-endpoint Borg version

`AgentMachine.desired_borg_version` (`"1"`, `"2"`, or `NULL` for "leave as
installed") is recorded on the pin endpoint and written into
`upgrade.conf` by the server-side reinstall path, so the next upgrade installs
that Borg major version. Reported Borg versions already arrive in
`borg_versions` and are already displayed, so the comparison surface is the
same pattern as the agent version and reuses the chip component.

This is the last phase because it depends on the upgrade path existing: without
it, setting a desired Borg version does nothing an operator can act on.

## 11. Security

### 11.1 What this actually grants

State the escalation plainly rather than minimising it.

Before this feature, a compromised Borg UI server can already, on every
endpoint: run arbitrary code as the service user (`script.run`,
`agent/borg_ui_agent/runtime.py:52`) and read any file on the machine, because
the unit carries `CAP_DAC_READ_SEARCH` (`app/api/agent_installer.py:722`). It
also already dictates which agent code the endpoint runs, since the endpoint
installs the wheel the server serves.

After this feature, on endpoints that carry the helper, it can additionally
obtain **root** on demand: write access, persistence, and everything the read
capability did not cover.

That is a genuine escalation, not a repackaging of existing trust. It is
accepted because the alternative — restricting upgrades to root-mode installs —
excludes the installer's own default service user mode (`current`,
`app/api/agent_installer.py:51`) and therefore excludes most installs from the
feature. The escalation is bounded to "the server that already controls this
endpoint's agent code can also restart it as root", which is a step up from
that starting position rather than a new party gaining access.

### 11.2 Properties the design must preserve

- The escalation is one command with no caller-supplied input (section 6). A
  compromised **agent** cannot influence what gets installed or from where; only
  a compromised **server** can, and only into the reinstall path.
- `upgrade.conf` is root-owned and not writable by the service user, so the
  agent cannot rewrite the server URL and redirect its own upgrade to an
  attacker-controlled host.
- The sudoers file is validated with `visudo -cf` before installation, names one
  absolute command path, and is never written on a root-mode install or when the
  operator opted out (section 6).
- The helper is refused entirely when `upgrade.conf` names a server URL that is
  not the one the agent is enrolled against, so a stale or tampered config
  cannot silently repoint an upgrade.
- Upgrade endpoints require the same authorization as every other agent
  mutation. Add the new actions to `app/core/authorization.py` alongside the
  existing agent actions.

### 11.3 Operator control

Remote upgrade is installed by default, because a fleet feature that is off by
default is not a fleet feature. `install.sh` accepts `--no-remote-upgrade` to
skip all four artifacts; such an endpoint reports no `self_upgrade` capability
and lands on the manual path described in section 9, which is the same path an
endpoint installed before this feature takes. Document the flag and its trade in
`docs/managed-agents.md` in the same phase that adds it.

## 12. Testing

- **Version comparison** — table-driven unit tests over the `upgrade_status`
  matrix in section 4, including unparseable versions, `NULL` on either side,
  and a pinned agent matching and not matching its pin.
- **Installer packaging** — extend `tests/unit/test_native_install_packaging.py`
  style guard tests: the served script writes all four artifacts, skips them in
  root mode and under `--no-remote-upgrade`, preserves the choice across a
  reinstall that does not pass the flag, and emits a sudoers line naming exactly
  one absolute command path.
- **Session command** — the agent refuses when busy and when unsupported, and
  invokes the expected `sudo` argv (mocked) otherwise.
- **Reconciliation** — an agent re-registering with the target version clears
  `requested`; one re-registering with the old version does not; the reaper
  marks a stale request `failed`.
- **Fleet waves** — queuing more agents than the concurrency cap releases them
  in waves.
- **Frontend** — tests for the banner counts (particularly the unsupported
  exclusion), each chip state, and that the manual path opens the existing
  dialog. Stories per section 9.

## 13. Phases

### 13.1 Progress

Agents update this table and nothing else as work advances. Statuses:
`not started`, `plan drafted`, `plan approved`, `in progress`, `in review`,
`done`, `blocked`.

| Phase | Status | Plan file | Branch | Notes |
| --- | --- | --- | --- | --- |
| 1. Version model and visibility | not started | | | |
| 2. Privileged helper and capability | not started | | | |
| 3. Single-agent remote upgrade | not started | | | |
| 4. Fleet upgrade | not started | | | |
| 5. Per-endpoint Borg version | not started | | | |

### 13.2 Phase 1 — version model and visibility

Migration adding `desired_agent_version`, `desired_borg_version`,
`upgrade_state`, `upgrade_requested_at`, `upgrade_target_version`, and
`upgrade_error` to `agent_machines`. The comparison helper and `upgrade_status`
on `AgentMachineResponse`. The version cell, its chips, the fleet banner, and
the pin control with its `PUT` endpoint. Stories for every chip state and the
banner.

Gate: an operator can see which endpoints are behind and pin one, with no
change to how upgrades are performed.

### 13.3 Phase 2 — privileged helper and capability

The four installer artifacts, the root-mode skip, the `--no-remote-upgrade`
opt-out, `visudo` validation, and capability detection in the agent. Update
`docs/managed-agents.md` with what the helper grants (section 11.1) and how to
decline it. No server behavior change beyond `self_upgrade_supported` appearing
in the response and the manual-path affordance in the UI becoming meaningful.

Gate: a freshly installed endpoint reports `self_upgrade`; an endpoint
installed before this phase does not, and the UI says so.

### 13.4 Phase 3 — single-agent remote upgrade

The `agent.upgrade` session command, the `agent_upgrade` job type, the
single-agent upgrade action and dialog, and the full reconciliation path
including the reaper timeout.

Gate: one endpoint upgrades from the UI and the row resolves to up to date
without anyone touching that machine.

### 13.5 Phase 4 — fleet upgrade

Multi-select, the bulk endpoint, the wave scheduler, and the banner's
Upgrade all action.

Gate: a fleet of endpoints upgrades in waves, and no more than the cap are
offline at once.

### 13.6 Phase 5 — per-endpoint Borg version

`desired_borg_version` written through to `upgrade.conf`, the Borg version
chip, and the selector.

Gate: an operator moves an endpoint from Borg 1 to Borg 2 from the UI.

---

## Appendix A — existing code this touches

| Area | File | Note |
| --- | --- | --- |
| Agent model |  `app/database/models.py:105` | `AgentMachine`; new columns land here |
| Agent jobs | `app/database/models.py:152` | `AgentJob`; `agent_upgrade` is a new `job_type` |
| Version reporting | `app/api/agents.py:1186` | heartbeat sets `agent_version`; success reconciliation hooks here |
| Register | `app/api/agents.py:1138` | same, for the post-restart re-register |
| Agent responses | `app/api/managed_machines.py:100` | `AgentMachineResponse` gains the new fields |
| Agent routes | `app/api/managed_machines.py:470` | new upgrade and pin routes sit alongside |
| Served installer | `app/api/agent_installer.py:29` | `INSTALLER_SCRIPT`; the four new artifacts |
| Served version | `app/api/agent_installer.py:797` | `agent_package_version()` is `available` |
| Systemd unit | `app/api/agent_installer.py:726` | unprivileged service user, the constraint |
| Session dispatch | `agent/borg_ui_agent/session.py:593` | `agent.upgrade` slots in here |
| Capabilities | `agent/borg_ui_agent/runtime.py:19` | `self_upgrade` added by detection |
| Reaper | `app/services/agent_job_reaper.py` | hosts the upgrade timeout sweep |
| Agents page | `frontend/src/pages/ManagedAgents.tsx` | version cell, banner, dialogs |
| Reinstall dialog | `frontend/src/pages/ManagedAgents.tsx:1468` | the manual fallback, kept |
| Stories | `frontend/src/pages/ManagedAgents.stories.tsx` | new states added here |

## Appendix B — decisions made

**D1. Escalation is a dedicated oneshot unit plus a narrow sudoers rule.**
The decisive argument is that the installer's default service user mode is
`current` — an unprivileged user (`app/api/agent_installer.py:51`). Rejected:
only upgrading root-mode installs, which would ship a fleet feature that does
not work on the installer's own default and would leave most endpoints on the
copy-paste path permanently. Rejected: an agent-writable venv, which weakens the
agent's own code path and still cannot update the systemd unit or the bundled
Borg binary. Section 11.1 states what the accepted option grants.

**D2. The helper takes no arguments; all parameters come from a root-owned
config file.** The alternative — the agent passing a server URL or flags
through sudo — would make a compromised agent able to install arbitrary code as
root. The sudoers rule is only safe because the escalated command has no input
surface.

**D3. Version comparison uses equality plus a local integer-tuple ordering, not
`packaging`.** `packaging` is not a direct dependency and the only ordering
question is `outdated` versus `ahead`, which a few lines answer. Adding a
dependency for a cosmetic distinction is not worth it.

**D4. Outcome is owned by the server, not reported by the agent.** The agent is
killed by the upgrade it is performing, so it structurally cannot report
completion. Making this explicit — request, then reconcile on re-register, then
time out — avoids a design where the terminal state depends on a message that
can never arrive.

**D5. Upgrades run in waves, not all at once.** Every upgrading endpoint is
briefly offline. An uncapped fleet upgrade is an outage.

**D6. The bulk endpoint rejects unsupported agents rather than skipping them.**
A partial success that reports as a full one is worse than a clear rejection
naming the endpoints that need a manual reinstall first.

**D7. Server self-upgrade is out of scope.** It is a different problem with a
different failure model and belongs in its own spec.

**D8. The helper is installed by default, with `--no-remote-upgrade` to opt
out.** Rejected: opt-in by default, which reintroduces the problem D1 rejects —
the feature would not work on a normal install until someone knew to ask for it.
An operator with one sensitive host opts that host out and keeps the manual
path.

**D9. Upgrades are pulled by the agent, not pushed by the server over SSH.**
A server that could SSH into each endpoint could push upgrades directly, and at
least one comparable product appears to be built that way. Borg UI's managed
agents deliberately dial out, which is what lets them sit behind NAT with no
inbound access and no server-held credentials for the endpoint. Adding
server-to-endpoint SSH to enable upgrades would undo that property for the sake
of one feature.
