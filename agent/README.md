# Borg UI Agent

`borg-ui-agent` is the lightweight runtime for machines managed by a central
Borg UI server. It registers with Borg UI, stores an agent credential locally,
polls for queued work, runs Borg on the local machine, and streams logs and
progress back to the server.

## One-Command Linux Install

In Borg UI, open Managed Agents and choose **Add Agent**. The wizard creates a
temporary enrollment token and shows a command like:

```bash
curl -fsSL http://borg-ui-host:8083/agent/install.sh | sudo bash -s -- \
  --server http://borg-ui-host:8083 \
  --token borgui_enroll_example \
  --name media-node
```

Run it on the Linux machine that owns the files Borg should back up. The
installer:

- installs `python3`, `python3-venv`, `python3-pip`, `git`, `curl`, and
  `borgbackup`
- creates the `borg-ui-agent` system user
- installs the agent into `/opt/borg-ui-agent/.venv`
- registers `/etc/borg-ui-agent/config.toml`
- validates the service configuration
- enables and starts `borg-ui-agent` with systemd

Use the Borg UI URL that the client machine can reach. `localhost` is only
correct when the agent runs on the same machine as Borg UI. For a remote client,
use the Borg UI server's host name, IP address, reverse-proxy URL, or HTTPS URL.

Enrollment tokens are temporary setup credentials. After registration, the agent
stores its own credential and keeps working until access is revoked or the agent
is deleted from Borg UI.

## Revoke, Delete, and Unregister

- **Revoke access** blocks the agent credential but keeps the machine visible for
  history and troubleshooting.
- **Delete agent** removes the machine from the active fleet list. The local
  systemd service may still exist on the client until you remove or unregister
  it there.
- `borg-ui-agent unregister` removes local credentials from the client machine.

## Advanced Manual Install

Manual setup is useful for development or troubleshooting. On a fresh client
machine, clone Borg UI and install the agent package into a virtual environment:

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

Create an enrollment token in Borg UI, then register manually:

```bash
borg-ui-agent register \
  --server http://borg-ui-host:8083 \
  --token borgui_enroll_example \
  --name laptop
```

The agent writes a protected config file containing the server URL, agent ID,
and agent token.

Default config paths:

| Platform | Path |
| --- | --- |
| Linux | `~/.config/borg-ui-agent/config.toml` |
| macOS | `~/Library/Application Support/borg-ui-agent/config.toml` |
| Windows | `%ProgramData%\borg-ui-agent\config.toml` |

Poll once:

```bash
borg-ui-agent once
```

Run continuously:

```bash
borg-ui-agent run
```

Use a custom config path:

```bash
borg-ui-agent --config /etc/borg-ui-agent/config.toml run
```

### Linux systemd Manual Service

The one-command installer handles systemd automatically. If you are repairing a
manual install, the default Linux unit runs as a dedicated system user and group
named `borg-ui-agent`. Create that account before installing or enabling the
unit:

```bash
sudo useradd --system --user-group --home-dir /var/lib/borg-ui-agent \
  --create-home --shell /usr/sbin/nologin borg-ui-agent
sudo install -d -o borg-ui-agent -g borg-ui-agent -m 0750 /etc/borg-ui-agent
```

Install the agent into the path used by the template:

```bash
sudo install -d -m 0755 /opt/borg-ui-agent
sudo python3.11 -m venv /opt/borg-ui-agent/.venv
sudo /opt/borg-ui-agent/.venv/bin/pip install .
```

Register the agent config at the service path:

```bash
sudo -u borg-ui-agent /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml \
  register \
  --server http://borg-ui-host:7879 \
  --token borgui_enroll_example \
  --name laptop
```

Validate the service account, executable, and config path before enabling the
unit:

```bash
sudo /opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check \
  --user borg-ui-agent \
  --group borg-ui-agent \
  --exec /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml
```

Install and start the unit:

```bash
sudo cp agent/install/systemd/borg-ui-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now borg-ui-agent
```

If you choose a different service user, group, virtual environment, or config
path, update both `agent/install/systemd/borg-ui-agent.service` and the
`service-check` arguments before enabling the unit.

### Troubleshooting Linux service startup

`status=217/USER` or `Failed at step USER` means systemd could not use the
configured `User=` or `Group=`. Check the account and run the service setup
validator:

```bash
getent passwd borg-ui-agent
getent group borg-ui-agent
sudo /opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check \
  --user borg-ui-agent \
  --group borg-ui-agent \
  --exec /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml
```

For a missing default user, `service-check` exits before `systemctl enable` with
a message like:

```text
borg-ui-agent: Service user 'borg-ui-agent' does not exist. Create it with: sudo useradd --system --user-group --home-dir /var/lib/borg-ui-agent --create-home --shell /usr/sbin/nologin borg-ui-agent
```

### macOS launchd

macOS launchd example:

```bash
sudo cp agent/install/launchd/com.borg-ui.agent.plist /Library/LaunchDaemons/
sudo launchctl bootstrap system /Library/LaunchDaemons/com.borg-ui.agent.plist
```

Review the template before enabling it. The current one-command installer is
Linux only; macOS and Windows installers are not included in this phase.

## Current Job Support

The first implementation supports:

- enrollment and heartbeat
- polling and claiming jobs
- `backup.create` using Borg 1 or Borg 2
- `filesystem.browse` for source path selection from the central Borg UI
- `repository.init`, `repository.info`, `repository.list_archives`,
  `repository.check`, `repository.prune`, `repository.compact`, and
  `repository.rclone_sync` for agent-owned repositories
- log and progress upload
- cancellation through heartbeat
