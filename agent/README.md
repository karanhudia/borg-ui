# Borg UI Agent

`borg-ui-agent` is the lightweight runtime for machines managed by a central
Borg UI server. It registers with Borg UI, stores an agent credential locally,
polls for queued work, runs Borg on the local machine, and streams logs and
progress back to the server.

## Install From This Repository

On a fresh client machine, clone Borg UI and install the agent package into a
virtual environment:

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

## Register

Create an enrollment token in Borg UI, then run:

```bash
borg-ui-agent register \
  --server http://borg-ui-host:7879 \
  --token borgui_enroll_example \
  --name laptop
```

Use the Borg UI URL that the client machine can reach. `localhost:7879` is only
correct when the agent runs on the same machine as Borg UI. For a remote client,
use the Borg UI server's host name, IP address, or HTTPS URL.

The agent writes a protected config file containing the server URL, agent ID,
and agent token.

Default config paths:

| Platform | Path |
| --- | --- |
| Linux | `~/.config/borg-ui-agent/config.toml` |
| macOS | `~/Library/Application Support/borg-ui-agent/config.toml` |
| Windows | `%ProgramData%\borg-ui-agent\config.toml` |

## Run

Poll once:

```bash
borg-ui-agent once
```

Run continuously:

```bash
borg-ui-agent run
```

For a quick manual proof, start with `borg-ui-agent once` to poll for one job,
then use `borg-ui-agent run` for continuous polling.

Use a custom config path:

```bash
borg-ui-agent --config /etc/borg-ui-agent/config.toml run
```

Unregister the agent and remove local credentials:

```bash
borg-ui-agent unregister
```

## Service Templates

Linux systemd and macOS launchd templates are available under `agent/install/`.
Adjust paths to match the virtual environment and config location used on the
target machine.

Linux systemd example:

```bash
sudo cp agent/install/systemd/borg-ui-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now borg-ui-agent
```

macOS launchd example:

```bash
sudo cp agent/install/launchd/com.borg-ui.agent.plist /Library/LaunchDaemons/
sudo launchctl bootstrap system /Library/LaunchDaemons/com.borg-ui.agent.plist
```

Review the template before enabling it. The default service assumes the agent is
installed under `/opt/borg-ui-agent/.venv` and uses
`/etc/borg-ui-agent/config.toml`.

## Current Job Support

The first implementation supports:

- enrollment and heartbeat
- polling and claiming jobs
- `backup.create` using Borg 1 or Borg 2
- `filesystem.browse` for source path selection from the central Borg UI
- `repository.info`, `repository.list_archives`, `repository.check`,
  `repository.prune`, and `repository.compact` for agent-owned local
  repositories
- log and progress upload
- cancellation through heartbeat
