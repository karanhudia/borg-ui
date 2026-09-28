# macOS Agent Platform Spec

Status: target picture for #1151. Extends
`2026-07-19-managed-agent-install-layout.md` (where a node's software comes
from) and `2026-09-07-centralized-agent-upgrades.md` (remote upgrade) to a
second platform. The implementation plan is
`../plans/2026-09-28-macos-agent-platform.md`.

## Goal

A Mac enrols as a managed agent through the same install command flow as a
Linux machine, runs the Borg version its server runs, receives jobs, and takes
remote upgrades. The agent runs as the user whose data it backs up, under
launchd, with nothing installed system-wide and no package manager involved.

## Problem

The managed agent targets Linux: the installer is Debian-family only, the
service templates are systemd units, and the paths it assumes
(`/etc/borg-ui-agent`, `/opt/borg-ui-agent`) are Linux paths. A full trial on
macOS (#1151) showed that the agent itself already carries most of what it
needs — `config.py` has a Darwin config path, `borg.py` reports `os: darwin`,
and Borg runs — and that a small set of platform assumptions stands in the way:

1. **The WebSocket session has no CA bundle.** `session._default_connect`
   passes no `sslopt`, so websocket-client falls back to OpenSSL's default
   verify paths. On a python.org framework build those are empty and every
   handshake ends in `CERTIFICATE_VERIFY_FAILED`, while `register` (requests,
   certifi) succeeds. The agent enrols, is listed as online, and never receives
   a job.
2. **`du -sb` is GNU-only.** BSD `du` has no `-b`, exits 64, and the size of a
   local-path repository becomes Unknown.
3. **launchd hands a job `PATH=/usr/bin:/bin:/usr/sbin:/sbin`.** The job payload
   never names a Borg binary, so the command falls back to a bare `borg`
   resolved through the agent's own `PATH`, which under launchd contains no
   Borg at all.
4. **The shipped plist is a root LaunchDaemon** pointing at
   `/Library/Application Support/...`, while the agent's Darwin default is the
   per-user `~/Library/Application Support/borg-ui-agent/config.toml`.
5. **Two Linux defaults:** the scripts allow-list at `/etc/borg-ui-agent/scripts.d`
   and an `install_source` classifier that reports Homebrew as `custom-path`.
6. **Mounting is offered for agent-executed repositories** but runs on the
   server, which has neither the repository nor the agent's filesystem.
7. **The UI prints the Linux install command** to a Mac, and the installer
   stops at its `/etc/os-release` guard.

## Where things come from

The rule of the install layout spec holds: the enrolling server provides what
only it can provide, and the rest comes from where the site already gets its
software. macOS has no distribution channel for that rest — the system Python
is a Command Line Tools stub at 3.9, which the agent cannot use, and Borg is
not shipped at all — so on macOS everything comes as published, checksummed
release artifacts, selected by a manifest the server serves, exactly the way
Borg already reaches a Linux node.

| Component | Source | Notes |
| --- | --- | --- |
| Agent package and dependencies | the enrolling server | Unchanged: `pip install --no-index --find-links <server>/agent/dist/`. The wheels are `py3-none-any`. |
| Borg | Borg's published macOS binaries, pinned in `app/api/borg_binaries.json` | Borg publishes `borg-macos-<N>-{arm64,x86_64}-gh` for every release the server pins (1.4.5 and 2.0.0b24 both do). The manifest gains a platform dimension. |
| Python | python-build-standalone, pinned in `app/api/python_runtimes.json` | A relocatable CPython (`*-apple-darwin-install_only.tar.gz`, ~23 MB) unpacked under the agent root. The version follows `PYTHON_VERSION` in `docker/runtime-base.env`. |
| curl, tar, shasum, launchctl | the base system | Nothing to solve. |

A Mac then needs to reach the enrolling server and GitHub's release downloads,
the same two hosts a Linux node needs for a server-pinned Borg. Homebrew and
MacPorts are never consulted. Their prefixes appear in the service `PATH` only
so that `--skip-borg-install` keeps working for a Mac that already has Borg.

Both artifacts are ad-hoc signed by their publishers. `curl` sets no quarantine
attribute, and launchd does not run Gatekeeper on the jobs it starts, so they
run as downloaded. Signing the agent itself is a separate concern (see Out of
scope).

## Layout

Everything lives under the user's own directories, matching the config path the
agent already defaults to on Darwin:

| Path | Purpose |
| --- | --- |
| `~/Library/Application Support/borg-ui-agent/` | `AGENT_ROOT` and the config directory in one: `config.toml`, `scripts.d/`, `python/`, `.venv/`, `borg1/<version>/borg`, `borg2/<version>/borg`, `bin/` (forwarders and the upgrade helper), `upgrade.conf`, `upgrade-requested`, `no-remote-upgrade` |
| `~/Library/LaunchAgents/com.borg-ui.agent.plist` | the agent job |
| `~/Library/LaunchAgents/com.borg-ui.agent-upgrade.plist` | the upgrade job |
| `~/Library/Logs/borg-ui-agent/` | `agent.log`, `agent.err`, `upgrade.log` |

There is no service user, no `/usr/local/bin` symlink and no root-owned file.
The Linux separation of an agent-owned config directory from root-owned install
and upgrade files exists to bound a privilege escalation; per user there is no
escalation to bound, so the separation is not reproduced.

## Installer contract

`GET /agent/install.sh` stays one script. It detects the platform after parsing
its arguments and before touching anything, and the Linux flow is unchanged in
what it does. On Darwin:

- The command runs **without sudo**, as the user whose data is backed up. Root
  is refused, since a root job would need its own Full Disk Access grant and
  still could not read the user's data without it.
- `--service-user` and `--borg-source distro` are refused as Linux-only.
  `--borg-version`, `--skip-borg-install`, `--reinstall`, `--no-remote-upgrade`,
  `--remote-upgrade`, `--agent-source` and `--version` keep their meaning.
- The Python runtime is selected by architecture from the pinned manifest,
  downloaded, verified against its SHA-256 and unpacked to
  `AGENT_ROOT/python`. A reinstall keeps a runtime whose recorded version
  matches the pin and replaces one that does not. The virtualenv is created
  from it.
- Borg is selected by platform, architecture and the macOS floor the binary was
  built on (`sw_vers -productVersion` against the manifest's `min_macos`, the
  same comparison the glibc floor uses on Linux), downloaded, verified and
  installed under `AGENT_ROOT/borg<major>/<version>/borg` with a forwarder in
  `AGENT_ROOT/bin`. The forwarder directory is the first entry of the service
  `PATH`, which is what makes the agent use the pinned binary.
- Registration runs as the current user against the per-user config path.
- The repository the agent reports (`agent.repository_defaults`, which the
  server asks for to pre-fill the repository form) comes from the agent's
  environment, so the installer takes `--borg-repo` and `--borg-remote-path`
  on both platforms, records them in `agent.env` beside the config and in the
  service definition (an `EnvironmentFile=` line pointing at that file, so a
  login inside the URL never reaches the world-readable unit; the plist's
  `EnvironmentVariables`), and reads them back on a reinstall, each value only
  when no flag gave it. The dialog's command passes `--borg-repo` with a
  `<BORG_REPO_URL>` placeholder (refused if left in place) and `--no-prompt`.
  A first-time macOS install with a terminal and without these flags asks for
  them instead, reading `/dev/tty` because its stdin is the piped script, and
  for an `ssh://` repository offers one SSH connection as the user: the first
  contact with a host is where the host key gets confirmed, which the service
  cannot do later. A Linux install never asks, since a question would hang a
  scripted `ssh -t` run; the upgrade helper's reinstall never sees a terminal.
  The passphrase stays with the server and travels with each job.
- The agent plist is rendered with absolute paths (launchd expands no `~`) and
  an `EnvironmentVariables` block, then bootstrapped into the user's domain:
  `launchctl bootstrap gui/$UID <plist>`; a reinstall boots the job out and
  bootstraps it again, since launchd reads a changed plist only then. The rendered
  plist is what `agent/install/launchd/com.borg-ui.agent.plist` shows as a
  template for a manual install.
- Remote upgrade is set up unless declined, see below.

The uninstaller (`GET /agent/uninstall.sh`) mirrors this: it boots both jobs
out, removes the plists, the agent root (keeping `config.toml`, `agent.env` and
`scripts.d` with `--keep-config`, as Linux keeps its config directory) and the
logs, and unregisters the endpoint as it does on Linux.

## launchd service

```xml
<key>Label</key>              <string>com.borg-ui.agent</string>
<key>ProgramArguments</key>   <array>
  <string>/Users/alex/Library/Application Support/borg-ui-agent/.venv/bin/borg-ui-agent</string>
  <string>--config</string>
  <string>/Users/alex/Library/Application Support/borg-ui-agent/config.toml</string>
  <string>run</string>
</array>
<key>RunAtLoad</key>          <true/>
<key>KeepAlive</key>          <true/>
<key>ThrottleInterval</key>   <integer>10</integer>
<key>EnvironmentVariables</key> <dict>
  <key>PATH</key>
  <string>/Users/alex/Library/Application Support/borg-ui-agent/bin:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
</dict>
<key>StandardOutPath</key>    <string>/Users/alex/Library/Logs/borg-ui-agent/agent.log</string>
<key>StandardErrorPath</key>  <string>/Users/alex/Library/Logs/borg-ui-agent/agent.err</string>
```

`KeepAlive` with `ThrottleInterval` is `Restart=always` / `RestartSec=10`. No
secret goes into the plist: `BORG_PASSPHRASE` arrives per job from the server,
and the SSH key of a per-user job is the user's own `~/.ssh`. A LaunchAgent runs
only while the user is logged in; that is the platform's model for user data
and is stated in the documentation rather than worked around.

## Remote upgrade

The Linux mechanism is: the agent creates a trigger file, a systemd path unit
notices and runs a oneshot unit as root, which runs an argument-less helper
that fetches `install.sh` and its checksum from the enrolled server, verifies,
and runs `install.sh --reinstall`. On macOS the same three pieces exist per
user:

- **Trigger:** `AGENT_ROOT/upgrade-requested`.
- **Watcher:** the `com.borg-ui.agent-upgrade` job with
  `KeepAlive` → `PathState` → `{<trigger>: true}`, launchd's equivalent of
  `PathExists=`: the job is started while the trigger exists.
- **Helper:** the same script, reading `AGENT_ROOT/upgrade.conf`. It removes
  the trigger first, as today. It also exits without doing anything when no
  trigger exists, so a job that launchd starts speculatively at bootstrap
  (which `KeepAlive` permits) does not reinstall on top of the install that just
  bootstrapped it. That guard is new on Linux too, where the path unit only
  ever starts the helper for an existing trigger, so nothing changes there.

After the reinstall, `install.sh` boots the agent job out and bootstraps it again.
The agent's `check_self_upgrade` reads the plist instead of the unit file on
Darwin (`ProgramArguments[0]` in place of `ExecStart=`) and the per-user paths;
the capability and the `agent.upgrade` handler are otherwise unchanged. The
server side needs nothing: it decides by the reported `self_upgrade` capability,
not by the platform.

The trust anchor is unchanged: an https server URL, the checksum served by the
same server, and the check that the conf names the server the agent is enrolled
against.

## Agent changes

- `session.py`: no change. The agent injects `truststore` at its CLI entry
  (0.1.13, #1278), so websocket-client's `ssl.SSLContext` verifies through the
  macOS keychain and the empty OpenSSL verify paths of a python.org framework
  build no longer matter. Measured on such a build: a `wss://` handshake fails
  without `truststore` and succeeds with it, with no `sslopt`.
- `storage_usage.py`: `du_storage_used` runs `du -A -sk` on Darwin and scales
  by 1024. `-A` keeps the measure comparable — apparent size, what `-b` reports
  on Linux — where a plain `-k` would report allocated blocks on one platform
  only. The per-file rounding to 512-byte units is below one percent on a
  repository of segment files. Only local-path repositories reach `du`.
- A small `paths` module answers `default_agent_root()` and
  `default_config_dir()` per platform; `config.py`, `scripts.py`, `borg.py` and
  `self_upgrade.py` read their Darwin defaults from it. The scripts allow-list
  defaults to `AGENT_ROOT/scripts.d`; `BORG_UI_AGENT_SCRIPTS_DIR` still
  overrides.
- `borg.py`: `_classify_install_source` knows the per-user agent root
  (`borg-ui-installer`), a Homebrew cellar in the resolved path (`homebrew`)
  and the MacPorts prefix (`macports`). `/usr/local/bin` without a cellar stays
  `custom-path`, which on Linux is exactly the hand-placed binary it names.
- `self_upgrade.py`: Darwin defaults and plist reading, as above.
- Agent version 0.1.14.

## Server changes

- `POST /api/mounts/borg` refuses a repository whose `executor_type` is
  `agent` with 400 and `backend.errors.mounts.agentRepository`. The mount
  service mounts under the server's data directory and never consulted the
  executor; for an agent endpoint that is either the wrong host or, when the
  repository path exists only on the agent, not reachable at all. Dispatching a
  mount to the agent is a separate feature (macFUSE, a mount point under the
  user's home) and not part of this.
- `app/api/borg_binaries.json` gains `platform` on every entry (`linux` /
  `darwin`) and `min_macos` on Darwin entries; `binary_table` renders
  `major platform arch floor sha256 url`. `scripts/refresh_borg_binary_manifest.py`
  recognises `borg-macos-<N>-(arm64|x86_64)-gh` next to the Linux pattern. A
  release stays adoptable on its Linux pair alone; a macOS pair that
  disappears is reported as a coverage regression in the adoption PR, so
  macOS never holds the Linux pin back.
- `app/api/python_runtimes.json` and `scripts/refresh_python_runtime_manifest.py`
  record the python-build-standalone build for the `PYTHON_VERSION` minor in
  `docker/runtime-base.env`, one entry per Darwin architecture. The installer
  receives it as `PINNED_PYTHON_RUNTIMES` next to `PINNED_BORG_BINARIES`.

## UI behavior

- The Add Agent dialog offers the platform (Linux, macOS). The macOS command
  omits `sudo` and the service-user flag; the service-user choice is hidden
  for it. The reinstall and uninstall commands take the platform from the
  agent's reported `os`.
- Archives and archive detail hide the mount action for an agent-executed
  repository. The backend refusal is what holds when the action is reached
  another way.

## Documentation

- `agent/README.md`: the macOS section describes the per-user layout, the
  install command, the LaunchAgent template and its manual bootstrap, remote
  upgrade, and the logged-in-user model.
- `docs/managed-agents.md`: the upgrade file table gains the macOS column.

## Testing

- Agent unit tests with a faked Darwin for each change: `du` runs
  `-A -sk` and scales; the scripts default; the install-source labels; the
  Darwin `check_self_upgrade` against a plist.
- Manifest tests: every pinned Borg version covers both Darwin architectures
  as it covers both Linux ones; the Python runtime matches the pinned minor and
  covers both architectures; the table renders the platform column; the
  native server installer skips Darwin rows.
- Installer tests: the served script parses under `bash -n` and shellcheck as
  today; the Darwin branch refuses root and the Linux-only flags, renders the
  plist with the agent root first on `PATH`, arms the upgrade job with
  `PathState`, and the helper exits without a trigger. A dry run of the Darwin
  branch with stubbed `uname`, `sw_vers`, `curl`, `launchctl` and a stub Python
  runtime walks the whole flow up to bootstrap.
- Route test: mounting an agent-executed repository answers 400.
- Frontend: command builder tests for both platforms, a story for the macOS
  install command.

The end-to-end trial (a fresh macOS without Command Line Tools, a real server,
a real enrolment and upgrade) is a manual step on a virtual machine; the trial
behind #1151 covered the agent's job path, and the installer's artifacts were
exercised by hand: both downloads verify against their published digests, the
relocatable Python runs with `tomllib` and a working certificate store, the
agent package installs into a virtualenv made from it, and Borg 1.4.5 creates,
lists, prunes and checks a repository under launchd's environment.

## Out of scope

- **Sleep.** A laptop sleeps during a long backup; an IOKit power assertion
  from the agent process would hold it awake and release with the process.
  Whether platform-specific power handling belongs in the agent is a design
  call, and the failure has not been measured yet.
- **TCC / Full Disk Access.** Measured on the trial Mac with the agent as a
  launchd user agent: `~/Desktop` was read without a prompt or a grant, and
  `~/Library/Containers` was not, Borg reporting each path as a warning so
  the run completed with warnings and the paths are in its log. macOS shows
  no dialog and adds nothing to its lists for a background job; the grant is
  made by hand, Full Disk Access → "+" → the interpreter the job runs,
  `AGENT_ROOT/python/bin/python3.12`, after which the same run completed
  clean. The grant binds to the code
  identity of the agent's executable, so a stable signed binary is the
  prerequisite for a grant that survives upgrades. That is a packaging and
  signing decision (an ad-hoc signature changes with every build).
- **A Python-free agent binary** (a PyInstaller build like Borg's own) would
  remove the runtime download; it depends on the signing decision above.
- **Mounting through the agent.**
