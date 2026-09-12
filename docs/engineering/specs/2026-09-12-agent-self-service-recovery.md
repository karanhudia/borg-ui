# Agent self-service recovery: server URL and uninstall

**Date:** 2026-09-12
**Status:** Approved 2026-09-12
**Owner:** karanhudia
**Related docs:** `docs/managed-agents.md`, `docs/managed-agent-spec.md`,
`docs/engineering/specs/2026-09-07-centralized-agent-upgrades.md`

> **For agentic workers:** this spec is the single source of truth for the
> feature. Each phase in section 10 names its scope and its gate. Do not start
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

Two routine endpoint lifecycle events have no supported path today.

**The server address changes.** An operator's Borg UI server moves: DHCP hands
it a new address, it goes behind a reverse proxy, it moves to a tunnel. Every
enrolled agent still holds the old `server_url` in
`/etc/borg-ui-agent/config.toml` and fails with `No route to host` forever.
`--reinstall` deliberately preserves that file and accepts no `--server`
(`app/api/agent_installer.py:255`), and `register` demands a fresh enrollment
token. The only route is editing a root-owned TOML file by hand, which is
documented nowhere. This was hit in practice on 2026-09-12: an agent stranded
on `192.168.1.81:8083` after the host moved to `.82`, recovered only by a
manual `sed`.

**Removing an agent leaves the machine dirty.** `borg-ui-agent unregister`
(`agent/borg_ui_agent/cli.py:126`) notifies the server and deletes the config,
but leaves the systemd units, the venv at `/opt/borg-ui-agent`, the upgrade
helper and its path unit, `/etc/borg-ui-agent/`, a possible dedicated service
user, and the `/usr/local/bin/borg` symlinks. `install.sh` has no
`--uninstall`. The docs say "unregister it on the client" without giving a
command.

Underneath both is a discoverability failure. `borg-ui-agent status` already
prints the configured server URL and would have diagnosed the first problem in
one command, but nothing in the UI or the docs points at it. The Managed Agents
page shows exactly one command, the enrollment one-liner, so a stuck operator
has no thread to pull.

## 2. User outcome

An operator whose server address changed opens Managed Agents, clicks **Change
server URL** on the affected card, types the new URL, and is handed one command
to run on that machine. The agent reconnects to the new address, keeping its
identity, its credential, and its history. No new enrollment token, no second
card in the fleet list.

An operator retiring a machine clicks **Uninstall** on its card, runs the one
command it hands them, and the machine is left with no trace of Borg UI: no
service, no venv, no config, no dedicated user. Their own Borg installation,
and their backup repositories, are untouched. The card reflects the removal
without further clicks.

## 3. Non-goals

- **Server-initiated push of either action.** Both features stay copy-paste
  commands. See Appendix B.1.
- **Removing distro-packaged Borg.** Out of scope permanently, not deferred.
  See section 6.2.
- **Checksum verification of the pasted installer command.** The existing
  `install.sh` copy-paste path is unverified today and `uninstall.sh` inherits
  that. Tightening both is real work and belongs in its own change.
- **A general remote-command console.** Nothing here adds a new way for the
  server to run arbitrary work on an endpoint.

## 4. Shape

Neither feature touches the agent to server protocol. No new session command,
no new capability, no new server to agent push, and no change to how the
privileged upgrade helper is triggered. The entire feature is:

1. One new agent CLI subcommand, `set-server`.
2. One new endpoint, `GET /agent/uninstall.sh`, and the script it serves.
3. Two card dialogs that render a copy-paste command.
4. Documentation.

This is deliberate. An agent pointed at the wrong server is offline by
definition, so the server cannot reach it to fix it. A push-based design would
be unable to serve the case that motivates the feature.

## 5. Changing the server URL

### 5.1 The agent subcommand

`borg-ui-agent set-server URL` joins `status`, `register`, `unregister`, `once`,
`run`, and `service-check` in `build_parser` (`agent/borg_ui_agent/cli.py:27`).
It loads the config, replaces `server_url`, and writes it back through the
existing `save_config`, which already restores `0600` on the file and `0700` on
its directory (`agent/borg_ui_agent/config.py:51`). `agent_id`, `agent_token`,
and `name` are preserved untouched.

The URL is validated before writing: it must parse, carry an `http` or `https`
scheme, and carry a host. An invalid URL exits non-zero with a readable message
and leaves the file unchanged. A trailing slash is stripped, matching
`load_config`.

The command does not restart the service. The operator's pasted command does
that explicitly, so the restart is visible rather than implied.

### 5.2 The emitted command

The dialog renders exactly one command. The server chooses which form based on
the `agent_version` already stored on the machine record, compared using the
existing `parse_agent_version` (`app/core/agent_versions.py:31`).

For an agent new enough to have the subcommand:

```
sudo borg-ui-agent set-server "URL" && sudo systemctl restart borg-ui-agent
```

For an older agent, or one whose version is unknown:

```
sudo sed -i 's|^server_url = .*|server_url = "URL"|' /etc/borg-ui-agent/config.toml && sudo systemctl restart borg-ui-agent
```

The fallback matches the exact line shape `save_config` writes, so it is
reliable against any config this project has ever produced. It is anchored at
line start and replaces the whole line, so a URL containing `=` is safe. The
URL is shell-quoted in both forms.

The operator never chooses between the two and the dialog never explains a
fork. The fallback naturally stops being emitted as the fleet updates.

### 5.3 What the dialog shows

The current `server_url` is not stored on the server, so the dialog cannot
prefill it from the record. It prefills with the server's own public base URL,
which is the value the operator almost always wants, and is the same value the
enrollment command already uses. Below the field, the dialog notes that
`borg-ui-agent status` prints the URL the endpoint currently holds, which is
the discoverability fix for the diagnostic that already exists.

## 6. Uninstall

### 6.1 The endpoint

`GET /agent/uninstall.sh` is added to the same prefixless router as
`install.sh` (`app/api/agent_installer.py:1242`), served as
`text/x-shellscript`. Unlike `install.sh` it takes no query parameters and
renders no per-agent pins, so it is a static string constant with no database
access.

The command on the card is:

```
curl -fsSL {server}/agent/uninstall.sh | sudo bash
```

### 6.2 What it removes

Full removal is the default, per the owner's requirement that nothing remain.

Always removed:

- The `borg-ui-agent` service, stopped and disabled, and
  `/etc/systemd/system/borg-ui-agent.service`
- The upgrade artifacts, by calling the existing `remove_upgrade_artifacts()`
  logic (`app/api/agent_installer.py:1050`): the `.path` and `.service` units,
  the helper, `/etc/borg-ui-agent-upgrade.conf`, the trigger file, and the
  legacy `/etc/sudoers.d/borg-ui-agent-upgrade`
- `/opt/borg-ui-agent`, which is the venv, the agent package, and any Borg the
  installer placed
- `/etc/borg-ui-agent/`, including `config.toml`
- `/etc/borg-ui-agent-no-remote-upgrade`
- `/var/lib/borg-ui-agent`
- A `systemctl daemon-reload` at the end

Two removals are conditional, and the conditions are load-bearing safety rules
rather than preferences.

**Borg symlinks.** `/usr/local/bin/borg` and `/usr/local/bin/borg2` are removed
only when the link resolves to a path under `/opt/borg-ui-agent`. This is the
same test `_classify_install_source` uses to label a binary `borg-ui-installer`
in the UI (`agent/borg_ui_agent/borg.py:49`), so the uninstaller and the card
agree by construction. A distro Borg at `/usr/bin/borg` is never touched, and
neither is a symlink an operator pointed somewhere else. Removing a
system-package Borg would break Borg for everything else on that machine,
including backups run outside Borg UI.

**The service user.** The account is deleted only when it is literally
`borg-ui-agent`, the dedicated account the installer creates. An install run
with `--service-user current` binds the service to the operator's own login
account, and deleting that would be catastrophic. The script reads `User=` from
the unit before removing it and deletes the account only on an exact match with
`borg-ui-agent`.

Backup repositories are never touched under any flag.

### 6.3 Flags

Mirroring the install flags, as opt-outs from the full sweep:

- `--keep-borg` leaves `/opt/borg-ui-agent/bin` Borg binaries and their
  symlinks in place
- `--keep-user` leaves the dedicated service user and `/var/lib/borg-ui-agent`
- `--keep-config` leaves `/etc/borg-ui-agent/config.toml`, for an operator who
  intends to reinstall against the same registration
- `--help` prints usage, matching `install.sh`

`--keep-config` implies the config directory survives; everything else in it,
including the upgrade trigger, is still removed.

### 6.4 Unregistering first

Before removing anything, the script reads `server_url` and `agent_token` from
`config.toml` and calls `POST /api/agents/unregister` with the
`X-Borg-Agent-Authorization` header, the same call `borg-ui-agent unregister`
makes through `AgentClient` (`agent/borg_ui_agent/cli.py:126`). The server
marks the machine `revoked` (`app/api/agents.py:1509`), so the card reflects
reality without the operator clicking Delete.

This is best effort with a short timeout. A stranded agent, which is a likely
reason to be uninstalling in the first place, cannot reach its server, and that
must not block local cleanup. The script prints whether the server was notified
and continues either way. `--keep-config` still unregisters; the operator asked
to keep the file, not to stay enrolled.

If `config.toml` is absent or unreadable, the script skips this step and
proceeds, so it is safe to run on a partially installed or already-unregistered
machine.

### 6.5 Idempotence

Every removal tolerates a missing target. Running the script twice, or on a
machine that was never fully installed, exits zero and reports what it found.
The script does not use `set -e` around removals for this reason; it collects
failures and reports them at the end rather than aborting halfway and leaving a
half-removed machine.

## 7. UI

Both actions are added to the existing card action row in
`ManagedAgents.tsx`, alongside diagnostics, pin, upgrade, revoke, and delete.
Per `AGENTS.md` and the phase 5 constraint, the new dialogs go in
`frontend/src/pages/managed-agents/`, not inline in `ManagedAgents.tsx`, which
is already over 2400 lines.

**Change server URL** is available whether the agent is online or offline.
Offline is the state in which it matters most, which is the point of the
copy-paste design.

**Uninstall** is likewise available in both states, and is styled as a
destructive action consistent with the existing delete control. Its dialog
states plainly what will be removed and, in one line each, that the operator's
own Borg installation and their backup repositories are not touched. It does
not require a typed confirmation; the command still has to be pasted into a
root shell on the target machine, which is confirmation enough.

Both dialogs use the copy-to-clipboard treatment the enrollment command box
already uses on the same page, so there is one visual language for "run this on
the endpoint".

The offline card gains one line of text pointing at `borg-ui-agent status` as
the way to see what the endpoint currently believes. This closes the dead end
described in section 1 at near zero cost, since the server cannot receive a
`last_error` from an agent that cannot connect.

## 8. Security

The uninstall endpoint is unauthenticated, matching `install.sh` beside it.
This is acceptable because the script is static, identical for every caller,
carries no credentials, no pins, and no per-agent data, and does nothing unless
an operator with root on a machine chooses to run it there. It reveals only
that a Borg UI server is present, which `install.sh` already reveals.

The script reads `agent_token` from `config.toml` to unregister. It sends that
token only to the `server_url` recorded in the same file, never to a URL passed
on the command line, so a pasted script cannot be steered into exfiltrating the
credential. The token is never echoed.

`set-server` writes only to the config file and only through `save_config`,
which restores the restrictive modes. It cannot alter the token, the agent id,
or any unit file, so it grants nothing beyond redirecting the agent this
operator already controls as root.

Nothing here adds a new escalation path. The upgrade helper and its `.path`
trigger (`app/api/agent_installer.py:1020`) are untouched; uninstall removes
them rather than using them.

## 9. Testing

- `agent/`: unit tests for `set-server`, covering a valid URL written and
  reread through `load_config`, preservation of `agent_id`/`agent_token`/`name`,
  trailing-slash stripping, rejection of a missing scheme and of a missing host,
  and that a rejected URL leaves the file byte-identical.
- `app/`: a test that `GET /agent/uninstall.sh` returns the shellscript media
  type, and that the body is byte-identical across two calls with different
  query strings, which pins the "static, no per-agent data" property in
  section 8.
- Command rendering: tests that the emitted `set-server` command is chosen by
  version, covering an agent above the threshold, one below, and one with
  `agent_version` null, plus shell quoting of a URL containing a shell
  metacharacter.
- The script itself is tested by running it, matching how `install.sh` is
  tested today. Cases: a full install removed cleanly; a second run exits zero;
  each `--keep-*` flag; a `/usr/local/bin/borg` symlink pointing at
  `/usr/bin/borg` left in place while one pointing into `/opt/borg-ui-agent` is
  removed; a unit with `User=someoperator` leaving that account alone while
  `User=borg-ui-agent` is removed; an unreachable server still cleaning up.
- Frontend: Vitest for both dialogs, and Storybook stories for the online and
  offline card states in default and mobile viewports, matching
  `ManagedAgents.stories.tsx`.

The two safety rules in section 6.2 each get a test that fails loudly if the
condition is inverted. They are the tests that matter most in this change.

## 10. Phases

### 10.1 Progress

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | `set-server` and the URL dialog | Plan written, awaiting implementation ([plan](../plans/2026-09-12-agent-self-service-recovery-phase-1.md)) |
| 2 | `uninstall.sh` and the uninstall dialog | Not started |

### 10.2 Phase 1 - change the server URL

The `set-server` subcommand, the version-selected command rendering, the card
dialog, the `borg-ui-agent status` hint on offline cards, and the docs section
on recovering an endpoint after the server moves.

**Gate:** an operator can move a real endpoint to a new URL from the card, on
both a current agent and one old enough to need the `sed` fallback, and it
reconnects with the same identity.

### 10.3 Phase 2 - uninstall

The endpoint, the script, its flags, the unregister call, the card dialog, and
the docs section on removing an endpoint.

**Gate:** a real endpoint is removed with no trace, verified against the
section 6.2 inventory, with a system-package Borg and the operator's own login
account both demonstrably intact afterwards.

## Appendix A - existing code this touches

| Path | What |
| --- | --- |
| `agent/borg_ui_agent/cli.py:27` | `build_parser`, where `set-server` is added |
| `agent/borg_ui_agent/config.py:51` | `save_config`, reused unchanged |
| `agent/borg_ui_agent/borg.py:49` | `_classify_install_source`, the rule the Borg symlink test mirrors |
| `app/api/agent_installer.py:1242` | The `install.sh` route, where `uninstall.sh` is added beside it |
| `app/api/agent_installer.py:1050` | `remove_upgrade_artifacts`, reused by the uninstaller |
| `app/core/agent_versions.py:31` | `parse_agent_version`, for choosing the command form |
| `app/api/agents.py:1509` | `POST /agents/unregister`, called by the uninstaller |
| `frontend/src/pages/ManagedAgents.tsx` | Card action row; new dialogs live in `managed-agents/` |
| `docs/managed-agents.md:244` | "Server URL and Localhost", which covers install time only |

## Appendix B - decisions made

**B.1 Copy-paste commands, not server-initiated push.** Considered pushing both
actions down the agent websocket as capability-gated session commands, which
would have made the card buttons act directly. Rejected because an agent with a
wrong `server_url` is offline by definition, so the motivating case is exactly
the one a push cannot reach. A push design would also have required a new root
escalation path for uninstall, since the agent may run as an unprivileged
service user and cannot remove its own systemd unit. The copy-paste design
needs neither, and works identically online and offline.

**B.2 Both the subcommand and the `sed` fallback.** Considered shipping only
`set-server`, which is the command that ought to exist, and only the `sed`,
which works on every deployed agent. Rejected both. Subcommand-only ships a
recovery feature that cannot recover anything until the whole fleet has been
reinstalled, and a stranded agent cannot be upgraded to obtain it.
`sed`-only leaves the CLI permanently missing the command that fixes the most
common failure, and teaches operators to regex-edit a root-owned config. The
objection to shipping both was a dialog that makes the operator choose; that is
avoided by selecting the form server-side from the `agent_version` already on
the record, so only one command is ever shown.

**B.3 Full removal by default.** Considered an agent-only default with an
explicit `--purge`. Rejected on the owner's call: an operator removing an agent
wants it gone, and a default that quietly leaves a service user and a data
directory behind is the wrong surprise. The safety rules in section 6.2 are not
part of this trade; they hold under every flag.

**B.4 No checksum on the pasted command.** `install.sh` is served alongside a
`.sha256` that only the self-upgrade helper verifies, so the copy-paste path
humans use pipes an unverified script into `sudo bash`. That is a real weakness
and `uninstall.sh` inherits it. Deliberately out of scope here: fixing it means
changing the enrollment command every operator has already learned, and it
should be decided on its own merits rather than smuggled in.
