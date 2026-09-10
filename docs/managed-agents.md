---
title: Managed Agents
nav_order: 7
description: "Install and run Borg UI Agent on client machines"
---

# Managed Agents

Managed Agents let one Borg UI server coordinate backups on client machines.
The client runs `borg-ui-agent`, connects outbound to Borg UI, runs Borg
locally, and streams progress and logs back to the server.

Open Managed Agents from the Infrastructure navigation group.

## Add a Linux Agent

In Managed Agents, choose **Add Agent**. The wizard asks for:

- platform: Linux
- agent name
- enrollment token expiry: 1 hour, 24 hours, 7 days, 30 days, or Never
- service user: Installing user, dedicated `borg-ui-agent` user, or Root
- server URL reachable by the client machine

The final step shows a one-line installer command:

```bash
curl -fsSL http://borg-ui-host:8083/agent/install.sh | sudo bash -s -- \
  --server http://borg-ui-host:8083 \
  --token borgui_enroll_example \
  --name laptop
```

Run it on the machine that owns the files you want Borg to back up. The
installer requires root or sudo, installs system dependencies, registers
`/etc/borg-ui-agent/config.toml`, runs `service-check`, and enables the systemd
service with `systemctl enable --now borg-ui-agent`.

By default the installer fetches the exact Borg versions the server runs, as
the static Linux binaries borgbackup publishes for x86_64 and aarch64. Those
binaries need a minimum glibc; when the machine's glibc is too old, the
installer says which version it needs and stops. Borg 1 can then be taken from
the distribution instead (`--borg-source distro`). No distribution ships
Borg 2 yet: install the server's version yourself and expose it as `borg2` on
PATH, then re-run the installer with `--skip-borg-install`. The installer's
message prints the commands for that, pinned to the server's version — a
virtualenv with `borgbackup` and `borgstore`, and a `borg2` symlink in
`/usr/local/bin` (a plain pip install provides only `borg`, which the agent
does not use for Borg 2). That install builds Borg from source, so the machine
needs a C toolchain, Borg's build dependencies and, from 2.0.0b24 on, OpenSSL
3.2 or newer.

By default, the service runs as the user who invoked `sudo`. That means the
agent can read and write the same paths that user can access, matching the
permission model used by SSH remote machines. Repository paths must be writable
by that service user.

Advanced service-user modes are available:

- `--service-user current` uses the sudo-invoking user. This is the default.
- `--service-user borg-ui-agent` uses a dedicated low-privilege system user and
  creates it if needed.
- `--service-user root` runs root-level Borg operations. Use it only when the
  agent must back up root-owned paths.
- `--service-user USERNAME` runs as another existing local user.

The machine appears in Managed Agents after registration and its first live
session. The wizard waits for that connection while the command is displayed.

## Reinstall or Update an Existing Agent

Use the **Reinstall agent** action on an existing agent card when you want to
update the installed `borg-ui-agent` package on a machine that is already
enrolled. Borg UI shows a tokenless command:

```bash
curl -fsSL http://borg-ui-host:8083/agent/install.sh | sudo bash -s -- --reinstall
```

Run it on that enrolled machine. Reinstall mode requires the existing
`/etc/borg-ui-agent/config.toml`, preserves the stored agent credential, skips
the registration step, refreshes the installed package and systemd unit, and
restarts `borg-ui-agent`. You do not need a new enrollment token unless you are
enrolling a different machine or recreating a missing local agent config.

## Remote Upgrade and What It Grants

New installs place four root-owned files on the endpoint so a future Borg UI
release can reinstall the agent from the server instead of you visiting the
machine. The agent asks for an upgrade by creating one empty file, which is the
entire privilege it is given. It passes no arguments and runs no privileged
command itself, so nothing here needs `sudo`, which the agent's own unit would
refuse anyway under `NoNewPrivileges=true`.

| File | Purpose |
| --- | --- |
| `/etc/borg-ui-agent-upgrade.conf` | The reinstall parameters. Root-owned, and outside the agent-owned config directory so the agent cannot replace it. |
| `/opt/borg-ui-agent/bin/borg-ui-agent-upgrade` | The helper. Takes no arguments and reads only `upgrade.conf`. |
| `/etc/systemd/system/borg-ui-agent-upgrade.service` | A oneshot unit that runs the helper. Never enabled. |
| `/etc/systemd/system/borg-ui-agent-upgrade.path` | Watches for `/etc/borg-ui-agent/upgrade-requested` and starts that one unit when it appears. |

Be clear about the trade. Before this, a compromised Borg UI server could
already run code as the agent's service user on every endpoint and read any
file on it, and it already decided which agent code the endpoint runs. With the
helper it can additionally obtain root on that endpoint: write access and
persistence. That is a real escalation, not a repackaging of existing trust. It
is bounded to the server that already controls the endpoint's agent code, and
it is what makes upgrades possible on the installer's default service user mode
rather than only on root installs.

Remote upgrade needs an `https` server URL, because the helper runs what it
downloads as root and will not fetch it over cleartext. An endpoint enrolled
against an `http` server reports no remote upgrade support and stays on the
manual path.

To decline it on a sensitive host:

```bash
curl -fsSL https://borg-ui-host:8083/agent/install.sh | sudo bash -s -- \
  --server https://borg-ui-host:8083 --token TOKEN --name NAME \
  --no-remote-upgrade
```

That endpoint keeps the manual reinstall path and reports no remote upgrade
support. A later reinstall remembers the choice; pass `--remote-upgrade` to
undo it.

Endpoints enrolled before this release have none of these files and are shown
as manual only. One reinstall gives them remote upgrade:

```bash
curl -fsSL https://borg-ui-host:8083/agent/install.sh | sudo bash -s -- \
  --server https://borg-ui-host:8083 --reinstall
```

## Knowing Which Agents Are Out of Date

Every agent reports the version it runs each time it checks in. Borg UI compares
that against the agent package the server itself ships, and shows the result as
a chip on the agent card:

| Chip | Meaning |
| --- | --- |
| No chip | The agent runs the version this server serves. Nothing to do. |
| **Update available** | The agent is older than the version this server serves. Use the Upgrade action on the row, or reinstall it with the plain `--reinstall` command above. |
| **Ahead of server** | The agent is newer than the version this server serves, which happens after a server rollback. Upgrade the server rather than downgrading the agent. |
| **Pinned** | The agent is held at a specific version and will not follow the server. |
| **Version unknown** | The agent has not reported a version yet, or the version cannot be compared. A freshly enrolled agent shows this until its first check-in. |

A banner above the fleet counts how many endpoints are running an older agent.

## Upgrading an Endpoint from the UI

An endpoint that carries the helper described above shows an Upgrade action on
its row when it is out of date. Confirming it asks that endpoint to reinstall
itself from this server.

What to expect:

- The endpoint disconnects for a short period while it reinstalls, and
  reconnects on its own.
- An endpoint that is running a backup refuses the upgrade, because the restart
  would orphan that backup. Try again once it is idle.
- The row shows **Upgrading** with the target version until the endpoint comes
  back. Nothing to do while it does.
- When the endpoint reconnects on the target version, the row clears itself.
- If it does not come back within 10 minutes, the row shows **Upgrade failed**.
  That endpoint needs the manual reinstall command above; nothing is retried
  automatically.

Upgrading several endpoints at once is a later release. Endpoints shown as
manual only, and endpoints enrolled before the helper existed, keep the manual
reinstall path.

### Pinning an Agent Version

An endpoint can be held at a specific agent version so it stops tracking the
server. The pin action on the agent row opens the version pin, with the agent
version (default "Track server") and the Borg major version. You can only pin
to a version this server can actually serve, because the installer installs
from this server and nowhere else. A pinned endpoint upgrades to its pin rather
than to the version the server serves.

The Borg choice is recorded now and takes effect in a later release, once an
upgrade can change the installed Borg version.

The same pin is available through the API:

```bash
curl -X PUT "$BASE_URL/api/managed-machines/agents/<id>/desired-version" \
  -H "X-Borg-Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"desired_agent_version": "0.1.3", "desired_borg_version": null}'
```

This is an admin endpoint. `$TOKEN` is an API token for an admin account; see
[the API guide](api.md) for how to obtain one. Send `null` for
`desired_agent_version` to clear the pin and track the server
again. You can only pin to a version this server can actually serve, because
the installer installs from this server and nowhere else.

## Server URL and Localhost

The `--server` value must be reachable from the client machine. If Borg UI and
the agent run on the same machine, `localhost` is valid. If the agent runs on
another machine, `localhost` points at that client machine, so use the Borg UI
server host name, IP address, reverse-proxy URL, or HTTPS URL.

Borg UI proposes a server URL in the Add Agent wizard. You can edit it before
generating the command.

## Enrollment Tokens and Agent Credentials

Enrollment tokens are temporary setup credentials. They can expire after 1 hour,
24 hours, 7 days, 30 days, or never expire. The default UI choice is 7 days.

After enrollment, the agent receives and stores its own credential. Token expiry
does not limit the enrolled agent lifetime. An enrolled agent keeps working until
you revoke access, delete it from the fleet list, or unregister it on the client.

## Revoke and Delete

- **Run diagnostics** opens a focused check for the selected agent. A
  session-only run verifies that Borg UI can reach the agent over its current
  connection and shows troubleshooting details such as online state, last seen
  time, agent version, Borg versions, capabilities, and last error.
- To check whether the agent host can reach another service, open
  **Advanced: test another service** and enter the service host, port, and
  timeout in seconds before running diagnostics. The timeout controls how long
  the agent waits for that TCP connection before reporting a timeout. The agent
  attempts the connection from the agent machine and reports success or failure,
  elapsed time, timeout, and normalized error text. Borg UI validates the target
  input before asking the agent to run the check.
- **Revoke access** blocks the agent credential but keeps the machine visible for
  history and troubleshooting.
- **Delete agent** removes the machine from active fleet lists. Existing job and
  log records remain readable. The local systemd service may still run on the
  client until you stop, remove, or unregister it there.
- **View agent logs** opens recent session-level logs for that machine, including
  connection, dispatch, and live command messages kept by the Borg UI process.

## Advanced Manual Setup

The one-command installer is the default Linux path. Manual setup is useful for
development or troubleshooting.

Run this on the machine that owns the files you want Borg to back up:

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
python3.11 -m venv .venv
. .venv/bin/activate
pip install .
```

Verify the CLI:

```bash
borg-ui-agent status
```

Register manually:

```bash
borg-ui-agent register \
  --server http://borg-ui-host:8083 \
  --token borgui_enroll_example \
  --name laptop
```

Run one manual agent check:

```bash
borg-ui-agent once
```

Run continuously:

```bash
borg-ui-agent run
```

### Linux systemd Manual Service

The installer creates and enables the systemd service automatically. For manual
service setup, the default Linux unit expects a system user and group named
`borg-ui-agent`:

```bash
sudo useradd --system --user-group --home-dir /var/lib/borg-ui-agent \
  --create-home --shell /usr/sbin/nologin borg-ui-agent
sudo install -d -o borg-ui-agent -g borg-ui-agent -m 0750 /etc/borg-ui-agent
```

Install the agent into the path used by
`agent/install/systemd/borg-ui-agent.service`, then register the service config:

```bash
sudo install -d -m 0755 /opt/borg-ui-agent
sudo python3.11 -m venv /opt/borg-ui-agent/.venv
sudo /opt/borg-ui-agent/.venv/bin/pip install .
sudo -u borg-ui-agent /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml \
  register \
  --server http://borg-ui-host:7879 \
  --token borgui_enroll_example \
  --name laptop
```

Validate the service setup before enabling it. This catches a missing or
invalid service user/group before systemd reaches `status=217/USER`:

```bash
sudo /opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check \
  --user borg-ui-agent \
  --group borg-ui-agent \
  --exec /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml
```

Then install and start the unit:

```bash
sudo cp agent/install/systemd/borg-ui-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now borg-ui-agent
```

If you choose a different service user, group, binary path, or config path, edit
the systemd unit and pass the same values to `service-check`.

If `systemctl status borg-ui-agent` shows `status=217/USER` or
`Failed at step USER`, systemd could not use the configured `User=` or `Group=`.
Run:

```bash
getent passwd borg-ui-agent
getent group borg-ui-agent
sudo /opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check \
  --user borg-ui-agent \
  --group borg-ui-agent \
  --exec /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml
```

For macOS, edit `agent/install/launchd/com.borg-ui.agent.plist` so the binary,
config, and log paths match the client machine. Then install it:

```bash
sudo cp agent/install/launchd/com.borg-ui.agent.plist /Library/LaunchDaemons/
sudo launchctl bootstrap system /Library/LaunchDaemons/com.borg-ui.agent.plist
```

Keep the agent config file readable only by the service user or local admin. It
contains the agent credential used to authenticate with Borg UI.

macOS and Windows one-command installers are not available yet.
