---
title: Managed Agents
nav_order: 7
description: "Install and run Borg UI Agent on client machines"
---

# Managed Agents

Managed Agents let one Borg UI server coordinate backups on client machines.
The client runs `borg-ui-agent`, polls Borg UI for work, runs Borg locally, and
streams progress and logs back to the server.

This feature is currently behind the Managed CLI Agents beta switch.

## Enable the UI

1. Open Settings > Advanced > Beta.
2. Enable Managed CLI Agents.
3. Open Managed Agents from the Backup navigation group.

## Install on a Client Machine

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

## Register the Client

In Borg UI, create an enrollment token from Managed Agents. Tokens are shown
once, so copy the token or generated command before closing the dialog.

Run the registration command on the client:

```bash
borg-ui-agent register \
  --server http://borg-ui-host:7879 \
  --token borgui_enroll_example \
  --name laptop
```

The `--server` value must be reachable from the client machine. If Borg UI is
running on the same machine as the agent, `http://localhost:7879` is valid. If
the agent runs on another machine, `localhost` points at that client machine, so
use the Borg UI server host name, IP address, reverse-proxy URL, or HTTPS URL.

## Run the Agent

Poll once:

```bash
borg-ui-agent once
```

Run continuously:

```bash
borg-ui-agent run
```

The machine appears in Managed Agents after registration and its first
heartbeat.

## Run on Startup

Linux systemd and macOS launchd templates are included in the repository under
`agent/install/`.

### Linux systemd

The default Linux unit expects a system user and group named `borg-ui-agent`:

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
