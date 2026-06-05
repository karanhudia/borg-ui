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
