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
  row move through upgrading to up-to-date without touching a single machine.
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

```text
desired_agent_version: str | None
desired_borg_version: "1" | "2" | None
available_agent_version: str | None
upgrade_status: Literal["up_to_date","outdated","ahead","pinned","unknown"]
self_upgrade_supported: bool          # "self_upgrade" in capabilities
upgrade_state: Literal["idle","queued","requested","failed"] | None
upgrade_requested_at: datetime | None
upgrade_error: str | None
```

`available_agent_version` is resolved once per request, not per row.

`desired_borg_version` is returned as well as accepted, so the pin control can
restore what an operator selected rather than resetting on reload, and so the
UI can compare the intended Borg major version against the ones the endpoint
actually reports in `borg_versions`.

`upgrade_state` distinguishes an endpoint accepted into a fleet upgrade but
still waiting for a wave (`queued`) from one whose upgrade has actually been
dispatched (`requested`). Without that split, every endpoint in a large bulk
request would read as idle until its wave started, and the operator would think
the request had been dropped.

**`POST /api/managed-machines/agents/upgrade`**

```json
{ "agent_machine_ids": [1, 2, 3] }
```

Queues one upgrade per named agent. Returns the created job ids and, per agent,
the resulting state.

Validation runs over the whole request before any job is created, and any
failure rejects the entire request rather than partially applying it. A partial
success that reports as a full one is the failure mode to avoid. Three checks,
each with its own error key:

| Condition | Key |
| --- | --- |
| An agent reports no `self_upgrade` capability | `backend.errors.agents.upgradeUnsupported` |
| An agent has no effective target, because it is unpinned and this server serves no agent wheel | `backend.errors.agents.upgradeTargetUnavailable` |

`agent_machine_ids` is deduplicated before validation, and an agent that
already has an `agent_upgrade` job in a non-terminal state returns that job
rather than queueing a second one. An upgrade restarts the endpoint, so
queueing two for one machine could restart it twice or race two reinstalls
against each other. This makes the endpoint idempotent under a double-click or
a client retry.

**`PUT /api/managed-machines/agents/{id}/desired-version`**

```json
{ "desired_agent_version": "0.1.3", "desired_borg_version": "2" }
```

Sets or clears the pin. Setting a `desired_agent_version` the server cannot
serve is rejected: the installer can only install from this server's
wheelhouse, so a pin to an unavailable version would be permanently
unsatisfiable.

## 6. The privileged helper

This is the load-bearing security design. The agent gets exactly one
escalation, and it carries no attacker-controlled input.

`install.sh` writes four root-owned artifacts, skipped only when the operator
passes `--no-remote-upgrade` (section 11.3). A reinstall preserves the existing
choice unless the flag is given explicitly, matching how the installer already
preserves the service user (`app/api/agent_installer.py:279`).

**A root-mode install gets three of the four.** The unit, the helper script and
`upgrade.conf` are installed exactly as for an unprivileged agent; only the
sudoers file is skipped, because a root agent can already start the unit. An
earlier draft skipped the whole set for root, which left root endpoints with
nothing to trigger and therefore no upgrade path at all: strictly worse than
the unprivileged case the escalation exists to serve. The escalation is what
root does not need; the mechanism it escalates to is needed either way.

**`/etc/borg-ui-agent-upgrade.conf`** — mode `0644`, owned `root:root`, and
deliberately outside `/etc/borg-ui-agent`, which the service user owns and could
otherwise replace a file in. Records
the parameters a reinstall needs: server URL, borg install mode, service user
mode, service user and group, agent root. Written at install time from the
values the operator gave the installer.

**`/opt/borg-ui-agent/bin/borg-ui-agent-upgrade`** — mode `0755`, owned
`root:root`, in a root-owned directory. It takes **no arguments**. It reads
`upgrade.conf`, fetches `install.sh` from the recorded server, verifies it
(below), and runs it with `--reinstall` and the recorded flags. Because every
parameter comes from a root-owned file rather than the caller, a compromised
agent process cannot redirect the install source, change the service user, or
inject installer flags. This is the property that makes the sudoers rule safe.

*Which version it installs.* `upgrade.conf` records the endpoint's `agent_id`,
not a version. The helper requests the installer as that agent, and **the
server** resolves which versions to pin into the script it serves, from the
endpoint's stored `desired_agent_version` and `desired_borg_version` (falling
back to the served wheel and the installed Borg when unpinned). The mechanism
already exists: the served script carries `PINNED_AGENT_VERSION` and the Borg
pinning block, rewritten per request (`app/api/agent_installer.py:829`).

This is the only propagation path, and it is deliberate. A pin set in the UI
after install time has to reach the endpoint somehow, and every alternative is
worse: writing the version into `upgrade.conf` needs a root-writable channel
from the agent, and passing it through sudo would hand the agent the argument
surface section 11.2 exists to deny. Resolving it server-side means the agent
never names a version, so it can neither install one of its own choosing nor
escape a pin, and the pin survives a server upgrade because it lives in the
database rather than on the endpoint.

*Transport and integrity.* The helper runs the fetched script as root, so:

- The recorded server URL must be `https`, with certificate and hostname
  verification on. An `http` URL is refused rather than downgraded, and a
  redirect that changes scheme or host aborts the upgrade. `curl` is invoked
  with `--proto '=https'`, which holds across redirects, so an https URL that
  redirects to http fails instead of downloading in cleartext. `--insecure` and
  `--location-trusted` are both omitted.
- The server publishes a SHA256 for the script it serves, and the helper
  verifies the download against it before executing. This mirrors what the
  native installer already does for its own artifacts, where checksums are
  published alongside the release rather than fetched from a mutable branch.
- Verification failure aborts without executing anything, leaves the agent
  running, and reports through the upgrade's timeout path (section 7.1).

Pinning versions is not integrity: `PINNED_AGENT_VERSION` says which wheel to
install, not that the script asking for it is the script we published. Both are
needed.

Before fetching anything it compares the server URL in `upgrade.conf` against
the one in `/etc/borg-ui-agent/config.toml` and aborts if they differ, so a
config left behind by an earlier enrollment cannot point a live agent's upgrade
at a host it no longer talks to.

**`/etc/sudoers.d/borg-ui-agent-upgrade`** — mode `0440`, granting the service
user exactly:

```text
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
it only ever runs when started. Running the reinstall inside a separate one-shot unit is
what lets the upgrade survive the restart of `borg-ui-agent` that it performs:
the upgrade is not in the agent's own process tree, so systemd killing the
agent does not kill the upgrade.

The agent advertises `self_upgrade` in `DEFAULT_CAPABILITIES`
(`agent/borg_ui_agent/runtime.py:19`) only when it can actually see the helper.
Capability is detected, not assumed, so an agent upgraded from an older install
that lacks the helper reports honestly and the UI routes it to the manual path.

**The upgrade preconditions.** One predicate, evaluated in one place, decides
both whether the agent advertises `self_upgrade` and whether `agent.upgrade`
will run. A partial or half-removed install can leave any one of these pieces
behind without the others, and each missing piece fails at a different point
after the operator has already been told the endpoint can upgrade itself:

1. `/etc/systemd/system/borg-ui-agent-upgrade.service` exists. Without it there
   is nothing to start.
2. The helper its `ExecStart` names is present and executable. Without it the
   unit starts and fails at exec time.
3. `/etc/borg-ui-agent/upgrade.conf` is readable and carries its required
   fields. The helper takes no arguments and reads every parameter from this
   file, so without it the root helper runs and fails having done nothing. The
   agent needs the file for the recorded `systemctl` path in any case.

Splitting the predicate between the probe and the command is what would let
those diverge, so both call it and the failure is reported once, honestly, as
"cannot upgrade itself" rather than as an upgrade that starts and dies.

On top of the preconditions the probe branches on how the agent runs, because
the escalation only exists for the unprivileged case:

- **Running as root.** The preconditions are the whole probe. There is no
  sudoers file to consult and the installer does not install `sudo`, so a probe
  that shelled out to `sudo -l` would report no capability on exactly the
  endpoints that need none.
- **Running unprivileged.** Additionally,
  `sudo -n <systemctl path> start --no-block borg-ui-agent-upgrade.service`
  is listed by `sudo -l`.

## 7. The upgrade command

New session command `agent.upgrade`, dispatched through the existing
`_handle_command` chain (`agent/borg_ui_agent/session.py:593`) next to
`diagnostics.run`.

Handler steps:

1. Refuse with `upgrade_busy` if this agent has any other job in flight. An
   upgrade restarts the process; doing it under a running backup would orphan
   that backup's job.
2. Refuse with `upgrade_unsupported` if the upgrade preconditions above do not
   hold. This is the same predicate the capability probe uses, re-evaluated
   rather than trusted, because the endpoint may have been changed since it
   last reported capabilities.
3. Emit a log line, then start the unit, using the absolute `systemctl` path
   recorded in `upgrade.conf`. A root agent invokes
   `<systemctl path> start --no-block borg-ui-agent-upgrade.service` directly;
   an unprivileged one prefixes `sudo -n` to that same argv. The argv must match
   the sudoers rule exactly, recorded path and unit name included, or the
   unprivileged form is refused.
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

**The cap bounds upgrades in flight, not endpoints offline.** A timeout frees
its slot even though that endpoint may still be mid-reinstall, so in the worst
case more than `AGENT_UPGRADE_CONCURRENCY` endpoints are briefly down at once.
This is deliberate. The alternative, holding a slot until the endpoint
reconnects, lets one machine that never comes back stall every remaining
upgrade in the fleet indefinitely, which is a worse failure than a transient
overshoot. The timeout is set generously (600s, far longer than a reinstall
takes) so an endpoint that hits it is far more likely broken than slow, and a
timed-out endpoint is marked `failed` and excluded from further automatic waves
until an operator acts on it, so the overshoot cannot compound.

Jobs are ordinary `agent_jobs` rows with `job_type="agent_upgrade"`, so they
appear in the existing agent job list, logs, and activity views for free.

## 9. UI

All on the Managed Agents page (`frontend/src/pages/ManagedAgents.tsx`),
composed from small components per `AGENTS.md`, no left accent borders.

**Fleet banner** — shown only when at least one endpoint is `outdated`. Names
the count, with an Upgrade all action. Endpoints without
`self_upgrade_supported` are excluded from the count in the action and called
out separately, so the number in the button is the number that will actually
move.

The banner names a target version only when every outdated endpoint agrees on
one. They do not always: an endpoint pinned below the served version is
outdated against its pin, not against what the server serves, so its effective
target is its own. When targets differ the banner says each endpoint targets
its configured version rather than naming one, and Upgrade all upgrades each to
its own effective target rather than to a single shared version.

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
  mutation, which for this router means the `get_current_admin_user` dependency
  in the route signature. `managed-machines` routes are deliberately not
  registered in `ENDPOINT_POLICIES` (`app/core/authorization.py`); do not add
  them there, or the router gains a second divergent authorization path.

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
  style guard tests: the served script writes all four artifacts, writes the
  unit, helper and `upgrade.conf` but not the sudoers file in root mode, skips
  all four under `--no-remote-upgrade`, preserves the choice across a reinstall
  that does not pass the flag, and emits a sudoers line naming exactly one
  absolute command path.
- **Helper transport and integrity** — the helper refuses an `http` server URL,
  refuses a redirect that changes scheme or host, refuses a script whose SHA256
  does not match the published one, and executes nothing in each case.
- **Version resolution** — the installer served to a pinned endpoint carries
  that endpoint's pinned versions, and the one served to an unpinned endpoint
  carries the wheel this server ships.
- **Bulk validation** — a request naming one unsupported agent creates no jobs
  at all; duplicate ids create one job; a second request for an agent with an
  in-flight upgrade returns the existing job rather than a new one; an unpinned
  agent on a server serving no wheel is rejected.
- **Session command** — the agent refuses when busy and when unsupported, and
  otherwise invokes the complete expected argv (mocked), asserted in full
  including the unit name:
  `<systemctl path> start --no-block borg-ui-agent-upgrade.service` as root,
  and that same argv behind `sudo -n` unprivileged. Capability detection and
  the upgrade are both covered for a root endpoint with no `sudo` on `PATH`,
  and the probe reports no capability, and `agent.upgrade` refuses with
  `upgrade_unsupported`, for each precondition failing on its own: unit
  missing, `ExecStart` helper missing or not executable, and `upgrade.conf`
  missing or short a required field.
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
| 1. Version model and visibility | done | `docs/engineering/plans/2026-09-07-agent-upgrades-phase-1.md` | `feat/agent-upgrades` | Pin UI moved to phase 3 |
| 2. Privileged helper and capability | in review | `docs/engineering/plans/2026-09-09-agent-upgrades-phase-2.md` | `feat/agent-upgrades-phase-2` | https is a precondition; opt-out uses a marker file |
| 3. Single-agent remote upgrade | not started | | | |
| 4. Fleet upgrade | not started | | | |
| 5. Per-endpoint Borg version | not started | | | |

### 13.2 Phase 1 — version model and visibility

Migration adding `desired_agent_version`, `desired_borg_version`,
`upgrade_state`, `upgrade_requested_at`, `upgrade_target_version`, and
`upgrade_error` to `agent_machines`. The comparison helper and `upgrade_status`
on `AgentMachineResponse`. The version cell, its chips, the informational
out-of-date banner, and the pin `PUT` endpoint. Stories for every chip state
and the banner.

The banner carries no action in this phase. An "Upgrade all" button belongs to
phase 4, and a button that does nothing is worse than no button.

The **UI** for setting a pin ships in phase 3, not here. Only the endpoint and
the chip that displays an existing pin land in phase 1: until upgrades are
automatic, an operator already controls an endpoint's version by choosing what
to paste, so a pin control would be a setting with no effect.

Gate: an operator can see which endpoints are behind, and the pin endpoint is
callable, with no change to how upgrades are performed.

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
single-agent upgrade action and dialog, the pin control UI deferred from
phase 1, and the full reconciliation path including the reaper timeout.

Gate: one endpoint upgrades from the UI and the row resolves to up-to-date
without anyone touching that machine.

### 13.5 Phase 4 — fleet upgrade

Multi-select, the bulk endpoint, the wave scheduler, and the banner's
Upgrade all action.

Gate: a fleet of endpoints upgrades in waves, and no more than the cap are
in flight at once. The gate is on upgrades in flight, not endpoints offline,
because a timed-out endpoint releases its slot while possibly still down
(section 8).

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

**D9. The server resolves which version an endpoint installs, not the endpoint.**
`upgrade.conf` records the endpoint's identity, and the server pins versions
into the installer it serves for that identity. Rejected: recording the version
on the endpoint, which needs a root-writable channel from the agent to change a
pin set later; and passing it through sudo, which would hand the agent exactly
the argument surface D2 exists to deny.

**D10. Root-mode endpoints get the helper and the unit, only the sudoers file
is skipped.** Skipping the whole set for root left those endpoints with no
upgrade path at all, which is worse than the unprivileged case the escalation
exists to serve. Root does not need the escalation; it still needs the thing
being escalated to.

**D11. The concurrency cap bounds upgrades in flight, not endpoints offline.**
A timeout frees its slot even though that endpoint may still be reinstalling.
Rejected: holding the slot until the endpoint reconnects, which lets a single
machine that never returns stall every remaining upgrade indefinitely.

**D12. Upgrades are pulled by the agent, not pushed by the server over SSH.**
A server that could SSH into each endpoint could push upgrades directly, and at
least one comparable product appears to be built that way. Borg UI's managed
agents deliberately dial out, which is what lets them sit behind NAT with no
inbound access and no server-held credentials for the endpoint. Adding
server-to-endpoint SSH to enable upgrades would undo that property for the sake
of one feature.
