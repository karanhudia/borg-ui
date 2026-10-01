# Borg UI Agent

`borg-ui-agent` is the lightweight runtime for machines managed by a central
Borg UI server. It registers with Borg UI, stores an agent credential locally,
keeps one authenticated outbound WebSocket session open to Borg UI, runs Borg on
the local machine, and streams logs and progress back to the server. The
`once` command still uses the polling path for compatibility.

## One-Command Linux Install

In Borg UI, open Managed Agents and choose **Add Agent**. The wizard creates a
temporary enrollment token and shows a command like:

```bash
curl -fsSL http://borg-ui-host:8083/agent/install.sh | sudo bash -s -- \
  --server http://borg-ui-host:8083 \
  --token borgui_enroll_example \
  --name media-node \
  --borg-repo "<BORG_REPO_URL>" \
  --no-prompt
```

Run it on the Linux machine that owns the files Borg should back up. The
installer:

- installs `python3`, `python3-venv`, `python3-pip`, `git`, `curl`, and
  `borgbackup`
- runs the service as the user who invoked `sudo` by default
- installs the agent into `/opt/borg-ui-agent/.venv`
- registers `/etc/borg-ui-agent/config.toml`
- validates the service configuration
- enables and starts `borg-ui-agent` with systemd

Repository and source paths must be readable or writable by the selected service
user. The default `current` mode uses the sudo-invoking user's normal Linux
permissions, so paths under that user's home directory work as expected. Use
`--service-user borg-ui-agent` for the older dedicated service account model,
`--service-user root` only when the agent must back up root-owned paths, or
`--service-user USERNAME` to run as another existing local user.

The agent owns the URL of the repository it backs up to: it reports
`BORG_REPO` (and `BORG_REMOTE_PATH`, the Borg executable on a host that
offers several) from its environment, and Borg UI pre-fills the repository
form with them. The command the dialog shows carries `--borg-repo
"<BORG_REPO_URL>"`: replace the placeholder with the repository (the installer
refuses it left in place), or remove the flag when there is none yet. Pass
`--borg-remote-path P` as well if needed. The values are recorded in the
service's environment and in `agent.env` beside the config, and a reinstall
keeps them; a flag given on a reinstall replaces that one value, an empty one
clears it. A Linux install never asks for them: it is scripted over `ssh -t`
or by configuration management as often as it is typed, and a question would
hang it. A first-time macOS install run from a terminal without these flags
asks, and for an `ssh://` or `rest://` repository offers to open one SSH
connection as the user, so the host key and the login are confirmed while
someone is there to answer; a service cannot do that later. `--no-prompt`
skips the questions. That check covers the one repository given
there. For the command the dialog shows (which passes `--no-prompt`), for a
Linux install and for every SSH repository added later, accept the host key
once as the user the agent runs as before the first job, for example
`ssh -p 23 user@host exit` (on Linux through `sudo -u <service user>`). The
passphrase is never asked for or stored on the machine: Borg UI keeps it and
sends it with each job.

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

Poll once through the compatibility job-polling path:

```bash
borg-ui-agent once
```

Run continuously with the live WebSocket session and reconnect backoff:

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

### macOS

On macOS the agent runs as the user whose data it backs up, under launchd, and
only while that user is logged in. Nothing is installed system-wide: no service
user, no root-owned file, no `/usr/local/bin` symlink. The Add Agent dialog
prints the install command for macOS; it is the Linux one without `sudo` and
without `--service-user`:

```bash
curl -fsSL https://SERVER/agent/install.sh | bash -s -- \
  --server https://SERVER --token TOKEN --name AGENT_NAME --borg-version 1 \
  --borg-repo "<BORG_REPO_URL>" --no-prompt
```

"Logged in" means a login session at the Mac, at its screen or through Screen
Sharing: launchd keeps the user's `gui/<uid>` domain only for that. An ssh
session alone has none, so the installer stops before installing anything when
it finds no such session, and after a restart the agent (and with it remote
upgrade) is offline until the user logs in. With FileVault that happens anyway,
since unlocking the disk at boot logs the user in; without it, automatic login
does the same for a Mac nobody sits at.

The installer downloads a relocatable Python build and the Borg version the
server runs from their published releases, verifies both against the digests
the server pins, and lays everything out under
`~/Library/Application Support/borg-ui-agent/`: `config.toml`, `scripts.d/`,
`python/`, `.venv/`, `borg1/<version>/borg`, `bin/` (forwarders and the
upgrade helper), `upgrade.conf`. Logs go to `~/Library/Logs/borg-ui-agent/`.
The job `com.borg-ui.agent` is bootstrapped into the user's launchd domain
with an `EnvironmentVariables` `PATH` that leads with `bin/`, which is how the
agent resolves the pinned Borg: launchd sources no shell profile. `BORG_REPO`
and `BORG_REMOTE_PATH` go into the same block when given or answered. SSH
needs nothing of its own: the job runs as the user, so `~/.ssh` applies, and
the host key has to be in `known_hosts` before the first job: the
interactive install's SSH check adds it for the repository given there, and
any other repository needs one connection as the user first (see
One-Command Linux Install above). Of the ssh-agents, the job sees macOS's
own (`com.openssh.ssh-agent`), whose socket launchd hands to every job in the
login session as `SSH_AUTH_SOCK`, and one named by `IdentityAgent` in
`~/.ssh/config`. An agent started in a terminal (`eval $(ssh-agent)`) is not
visible to it: use a key without a passphrase, the macOS agent, or
`IdentityAgent`.

Protected user data (`~/Library/Mail`, `Messages`, `Containers` and the rest
of TCC's list; `~/Desktop` is not among them in practice) is refused to the
job until it has Full Disk Access, and Borg then reports each such path as
a warning. macOS shows no dialog for a background job and adds nothing to
its lists: grant it by hand under Privacy & Security → Full Disk Access →
"+" (Cmd+Shift+G) for the interpreter the job runs,
`~/Library/Application Support/borg-ui-agent/python/bin/python3.12`. The
grant is bound to that file, so a Python change on upgrade needs it again.
A warning of the form `[Errno 13] Permission denied` is ordinary file
permissions, not TCC, and no grant changes it.

The job reads what its user reads: the user's own home directory (macOS keeps
`Desktop`, `Documents`, `Downloads`, `Library`, `Movies`, `Music` and
`Pictures` readable by their owner alone) and what is world-readable on the
machine, never another user's private folders, `/var/root` or root-only
state. Admin-group membership changes nothing there, since the job runs as
the user; it is needed only to grant Full Disk Access, so a user without it
backs up the home directory except what TCC protects. Several users on one
machine each install their own agent in their own session; the layout, the
jobs and the config are per user, and each agent is a separate endpoint with
the same hostname. A root-level, whole-machine backup is deliberately not
offered: the job executes code the user can write.

Remote upgrade works the same way as on Linux: the agent creates
`upgrade-requested`, the job `com.borg-ui.agent-upgrade` (kept alive by
launchd's `PathState` while the file exists) runs the helper, which fetches
the installer from the enrolled server, verifies its checksum and reinstalls.
`borg-ui-agent service-check` and `--service-user` are Linux-only.

For a manual install, `agent/install/launchd/com.borg-ui.agent.plist` is the
job the installer renders, so the manual layout has to be the installer's:
the virtualenv at `~/Library/Application Support/borg-ui-agent/.venv`, the
config at the default path in that directory, logs under
`~/Library/Logs/borg-ui-agent/`. From a checkout of this repository:

```bash
AGENT_ROOT="$HOME/Library/Application Support/borg-ui-agent"
mkdir -p "$AGENT_ROOT" ~/Library/Logs/borg-ui-agent ~/Library/LaunchAgents
python3.11 -m venv "$AGENT_ROOT/.venv"
"$AGENT_ROOT/.venv/bin/pip" install .
"$AGENT_ROOT/.venv/bin/borg-ui-agent" register \
  --server http://borg-ui-host:8083 \
  --token borgui_enroll_example \
  --name laptop
sed "s#/Users/alex/#${HOME}/#g" agent/install/launchd/com.borg-ui.agent.plist \
  > ~/Library/LaunchAgents/com.borg-ui.agent.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.borg-ui.agent.plist
```

The `sed` puts the real home directory in place of `/Users/alex`, since launchd
expands no `~`. Borg has to be on the `PATH` the template sets (Homebrew,
MacPorts and `/usr/local/bin` are on it; the `bin/` forwarders exist only
after the installer ran).

This loads the agent job only. The remote-upgrade job
(`com.borg-ui.agent-upgrade`) and its `upgrade.conf` are rendered by the
installer and have no template, so an agent set up by hand takes no remote
upgrades until the install command has been run once.

Windows is not supported yet.

## Current Job Support

The first implementation supports:

- enrollment and heartbeat
- polling and claiming jobs
- `backup.create` using Borg 1 or Borg 2
- `filesystem.browse` for source path selection from the central Borg UI
- `repository.init`, `repository.info`, `repository.list_archives`,
  `repository.list_archive_contents`, `repository.extract_archive_file`,
  `repository.check`, `repository.prune`, `repository.compact`,
  `repository.rclone_sync`, and `repository.diff` (the change listing the
  server's archive history is built from) for agent-owned repositories
- log and progress upload; from 0.1.8 a line whose progress report says
  all it did (`progress_percent`, `archive_progress`) is not stored as a
  log line too, while a `file_status` line of `create --list` is reported
  and stored, being the listing that was asked for; `repository.info`,
  `repository.rinfo`, `repository.archive_info` and
  `repository.list_archives` log a one-line summary instead of their JSON
  output (a failed run keeps the output); from 0.1.9 the steps Borg's
  progress indicators print (such as the cache transaction, as
  `progress_message` or as a `log_message` of `borg.output.progress`)
  are neither stored nor reported, and a backup's completion carries the
  archive's final counters (`archive_stats`, from `archive.stats` of
  `borg create --json`), which the server keeps over the last progress
  report
- from 0.1.10 a failure report carries the last lines Borg wrote
  (`stderr_tail`, at most 40 lines / 4 KiB) and a `failure_kind`
  (`lock_contention` when Borg gave up on a lock another process holds -
  exit codes 70, 71 and 73, or the `(timeout)` lock line of a Borg 1 on
  legacy exit codes; not 72, a lock file Borg could not create -
  else `other`), so the server does not depend on the log lines, which
  can land after the report
- from 0.1.11 the Borg 1 command lines carry `--lock-wait` with the
  value of `BORG_LOCK_WAIT` (the one the server sends with the job, else
  the agent's default of 180 s), because Borg 1.4 never reads the
  variable and gives up on a lock another process holds after 1 second
  (#1216); Borg 2 keeps reading the variable
- from 0.1.12 custom `borg create` flags and extra `borg check` flags in a
  job are checked against an allowlist of safe options before Borg runs;
  a job carrying any other option or a positional argument fails
- from 0.1.13 TLS is verified against the machine's trust store (via
  `truststore`) as well as certifi's bundle, so a self-signed server
  certificate installed with `update-ca-certificates` (or the platform
  equivalent) is accepted (#1272)
- from 0.1.14 the agent runs on macOS: `du` measures a local repository with `-A -sk` where
  there is no GNU `-b`, the scripts allow-list and the installer root sit in
  the user's Application Support directory, a Homebrew or MacPorts Borg
  reports its install source, and the self-upgrade readiness reads the
  launchd job instead of the systemd units
- from 0.1.15 the agent speaks Borg 2.0.0b25: the remote Borg command
  travels in `BORG_REMOTE_PATH` instead of `--remote-path` (an option Borg 2
  removed in 2.0.0b22), the repository size is read with the repository
  key (2.0.0b25 seals the chunk index with it), a Borg 2 job on a `rest://`
  repository is refused where the machine's Borg 2 is 2.0.0b25 or later
  (it would read the URL as a local directory; the scheme is `ssh://` now;
  an older Borg 2 keeps its `rest://` repositories) and so is creating a
  Borg 2 repository with the encryption mode `none`, which 2.0.0b25 removed;
  a Borg 2 restore into a directory that holds anything is refused with a
  message before Borg runs, where the machine's Borg 2 is 2.0.0b25 or later
  (which does not extract into one)
- cancellation through heartbeat; from 0.1.7 (`jobs.cancel`) a running
  backup, check, prune, compact, restore or archive delete stops as well,
  even while Borg prints nothing
