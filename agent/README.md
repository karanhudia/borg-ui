# Borg UI Agent

`borg-ui-agent` is the lightweight runtime for machines managed by a central
Borg UI server. It registers with Borg UI, stores an agent credential locally,
polls for queued work, runs Borg on the local machine, and streams logs and
progress back to the server.

## Install From This Repository

```bash
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
  --server https://borg-ui.example.com \
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

## Run

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

Unregister the agent and remove local credentials:

```bash
borg-ui-agent unregister
```

## Service Templates

Linux systemd and macOS launchd templates are available under `agent/install/`.
Adjust paths to match the virtual environment and config location used on the
target machine.

## Current Job Support

The first implementation supports:

- enrollment and heartbeat
- polling and claiming jobs
- `backup.create` using Borg 1 or Borg 2
- log and progress upload
- cancellation through heartbeat
