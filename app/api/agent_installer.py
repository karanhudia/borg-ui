import asyncio
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.borg_binaries import binary_table
from app.api.python_runtimes import CURRENT_PYTHON_RUNTIME, runtime_table
from app.core.borg import BorgInterface
from app.core.borg2 import Borg2Interface
from app.database.database import get_db
from app.database.models import AgentMachine

logger = structlog.get_logger()

router = APIRouter(tags=["agent-installer"])

# Where the image keeps the agent wheel built during the Docker build.
DEFAULT_AGENT_PACKAGE_DIR = "/opt/borg-ui/agent-dist"

# The served script is pinned to the versions this server actually runs. The
# defaults below keep the raw script valid and runnable on its own (it then
# falls back to distribution packages), and PINNING_MARKERS delimits the block
# the server rewrites.
PINNING_BEGIN = "# BEGIN server-provided pinning"
PINNING_END = "# END server-provided pinning"


INSTALLER_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail

# BEGIN server-provided pinning
# Replaced when this script is served by a Borg UI instance, which fills in the
# Borg versions it runs, the checksums of the matching static binaries, and the
# pins of the endpoint that asked for the script.
PINNED_BORG1_VERSION=""
PINNED_BORG2_VERSION=""
PINNED_BORG_BINARIES=""
# The relocatable Python a macOS endpoint runs the agent with, and where each
# architecture's build comes from. Read by select_python_runtime below.
PINNED_PYTHON_VERSION=""
PINNED_PYTHON_RUNTIMES=""
PINNED_AGENT_VERSION=""
# The Borg major version this endpoint is pinned to in the UI, or empty to
# leave whatever is installed alone. Read by apply_pinned_borg_version below.
PINNED_DESIRED_BORG_VERSION=""
# END server-provided pinning

SERVER=""
TOKEN=""
AGENT_NAME=""
REINSTALL="0"
AGENT_REF="main"
AGENT_SOURCE="server"
BORG_VERSION="1"
BORG_VERSION_SET="0"
BORG_SOURCE="server"
SKIP_BORG_INSTALL="0"
SERVICE_USER_MODE="current"
SERVICE_USER_MODE_SET="0"
REMOTE_UPGRADE="1"
REMOTE_UPGRADE_SET="0"
NO_REMOTE_UPGRADE_MARKER="/etc/borg-ui-agent-no-remote-upgrade"
# Deliberately not under /etc/borg-ui-agent: that directory is owned by the
# service user, so the agent could replace any file in it, and root sources
# this one.
UPGRADE_CONF="/etc/borg-ui-agent-upgrade.conf"
UPGRADE_UNIT="/etc/systemd/system/borg-ui-agent-upgrade.service"
UPGRADE_PATH_UNIT="/etc/systemd/system/borg-ui-agent-upgrade.path"
# The agent asks for an upgrade by creating this. It is in the agent-owned
# config directory on purpose: creating it is the whole privilege being
# granted, and nothing ever reads it, only its existence.
UPGRADE_TRIGGER="/etc/borg-ui-agent/upgrade-requested"
SERVICE_USER=""
SERVICE_GROUP=""
SSH_CHECK_REQUESTED="0"
SERVICE_HOME=""
SERVICE_READ_WRITE_PATHS="/etc/borg-ui-agent /tmp"
AGENT_ROOT="/opt/borg-ui-agent"
BORG_FORWARDER_DIR="${AGENT_ROOT}/bin"
UPGRADE_HELPER="${AGENT_ROOT}/bin/borg-ui-agent-upgrade"
BORG1_LINK="/usr/local/bin/borg"
BORG2_LINK="/usr/local/bin/borg2"
CONFIG_DIR="/etc/borg-ui-agent"
# Linux or Darwin. The layout above is Linux's; configure_darwin_layout
# replaces it on a Mac. Overridable so a test can walk either flow anywhere.
PLATFORM="${BORG_UI_AGENT_PLATFORM:-$(uname -s)}"
LOG_DIR=""
LAUNCH_AGENTS_DIR=""
AGENT_JOB_LABEL="com.borg-ui.agent"
UPGRADE_JOB_LABEL="com.borg-ui.agent-upgrade"
PYTHON_BIN="python3"
# The repository this endpoint backs up to. The agent reports it to the server
# (agent.repository_defaults), which pre-fills the repository form with it, so
# it lives in the agent's environment: the service definition carries it, and
# this file remembers it across reinstalls.
BORG_REPO_VALUE=""
BORG_REMOTE_PATH_VALUE=""
BORG_REPO_SET="0"
BORG_REMOTE_PATH_SET="0"
PROMPT="1"
AGENT_ENV_FILE=""
# Where agent.env is built before it is renamed into the config directory.
# Root's own directory on Linux, on the same filesystem, since the config
# directory belongs to the service user.
AGENT_ENV_STAGING_DIR="/etc"
MACHINE_ARCH=""
MACHINE_PLATFORM="linux"
MACHINE_FLOOR=""
MACHINE_FLOOR_NAME="glibc"

usage() {
  cat <<'USAGE'
Usage:
  curl -fsSL http://SERVER:PORT/agent/install.sh | sudo bash -s -- \
    --server http://SERVER:PORT \
    --token TOKEN \
    --name AGENT_NAME \
    [--version main] \
    [--borg-version 1|2|both] \
    [--borg-source server|distro] \
    [--agent-source server|git] \
    [--service-user current|borg-ui-agent|root|USERNAME] \
    [--skip-borg-install]

  curl -fsSL http://SERVER:PORT/agent/install.sh | sudo bash -s -- \
    --reinstall \
    [--version main] \
    [--borg-version 1|2|both] \
    [--skip-borg-install]

On macOS the agent runs as the user whose data it backs up, under launchd, so
the same commands run without sudo and without --service-user:

  curl -fsSL http://SERVER:PORT/agent/install.sh | bash -s -- \
    --server http://SERVER:PORT --token TOKEN --name AGENT_NAME \
    [--borg-version 1|2|both] [--skip-borg-install]

Borg install options:
  --borg-version 1      Install/verify Borg 1 as 'borg' (default).
  --borg-version 2      Install/verify Borg 2 as 'borg2' (advanced beta).
  --borg-version both   Install/verify Borg 1 and Borg 2.
  --skip-borg-install   Do not install Borg; register/reinstall with detected binaries only.

Repository options:
  --borg-repo URL       The repository this machine backs up to. The agent
                        reports it to Borg UI, which pre-fills the repository
                        form with it. Recorded in the service's environment as
                        BORG_REPO and kept across reinstalls; on a reinstall a
                        flag replaces that one value.
  --borg-remote-path P  The Borg executable on that host (BORG_REMOTE_PATH),
                        for a host that offers several.
  --no-prompt           Do not ask for these on the terminal. Without the flag
                        a first-time macOS install with a terminal asks for
                        them, and offers to open an SSH connection to an
                        ssh:// repository so the host key and the login can be
                        confirmed while someone is there to answer. A Linux
                        install never asks; it takes them as flags only.

Remote upgrade options:
  --no-remote-upgrade   Do not install the privileged self-upgrade helper. The
                        endpoint can then only be updated by running this
                        installer on the machine with --reinstall. A reinstall
                        remembers this choice; pass --remote-upgrade to undo it.

  --borg-source server  Install the exact Borg versions this Borg UI server runs,
                        from the static binaries published with those releases
                        (default). Agent and server then speak the same Borg.
  --borg-source distro  Use distribution packages instead. The version is then
                        whatever the distribution ships, which may differ from
                        the server's. Required on platforms with no published
                        static binary, such as 32-bit ARM. Borg 1 only: no
                        distribution ships Borg 2 yet. Linux only.

Agent install options:
  --agent-source server Install the agent package the enrolling server offers
                        (default), so the agent matches the server it talks to.
  --agent-source git    Install from the upstream Git repository at --version.
                        Intended for development.

Service user options (Linux only):
  --service-user current        Run as the user who invoked sudo (default).
  --service-user borg-ui-agent  Run as the dedicated borg-ui-agent system user.
  --service-user root           Run as root. Advanced; grants root-level Borg operations.
  --service-user USERNAME       Run as an existing local user.

Reinstall mode updates the agent package and service definition on an already
enrolled machine. It preserves the agent's config.toml and does not require an
enrollment token, agent name, or registration. By default, reinstall mode skips
Borg installation; pass --borg-version to verify or update Borg binaries.
USAGE
}

# --- macOS -------------------------------------------------------------------
# The agent runs as the user whose data it backs up, under launchd, and
# everything it needs lives in that user's own directories. There is no
# service user, no root-owned file and no /usr/local/bin symlink: the forwarder
# directory is the first entry of the service PATH instead.
configure_darwin_layout() {
  AGENT_ROOT="${HOME}/Library/Application Support/borg-ui-agent"
  CONFIG_DIR="${AGENT_ROOT}"
  LOG_DIR="${HOME}/Library/Logs/borg-ui-agent"
  LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
  BORG_FORWARDER_DIR="${AGENT_ROOT}/bin"
  UPGRADE_HELPER="${AGENT_ROOT}/bin/borg-ui-agent-upgrade"
  UPGRADE_CONF="${AGENT_ROOT}/upgrade.conf"
  UPGRADE_TRIGGER="${AGENT_ROOT}/upgrade-requested"
  NO_REMOTE_UPGRADE_MARKER="${AGENT_ROOT}/no-remote-upgrade"
  AGENT_ENV_STAGING_DIR="${AGENT_ROOT}"
  # One launchd job both runs the helper and watches the trigger.
  UPGRADE_UNIT="${LAUNCH_AGENTS_DIR}/${UPGRADE_JOB_LABEL}.plist"
  UPGRADE_PATH_UNIT="${UPGRADE_UNIT}"
  BORG1_LINK="${BORG_FORWARDER_DIR}/borg"
  BORG2_LINK="${BORG_FORWARDER_DIR}/borg2"
  PYTHON_BIN="${AGENT_ROOT}/python/bin/python3"
  SERVICE_USER="$(id -un)"
  SERVICE_GROUP="$(id -gn)"
  SERVICE_HOME="${HOME}"
  # Borg is verified by the name the agent resolves, so the forwarders have to
  # be reachable here the way they are under launchd.
  export PATH="${BORG_FORWARDER_DIR}:${PATH}"
}

# Root-owned on Linux, where the agent runs as another user and must not be
# able to replace what root executes; the user's own files on macOS.
own_root() {
  if [[ "${PLATFORM}" == "Linux" ]]; then
    chown root:root "$@"
  fi
}

# $1 the expected digest, $2 the file. macOS ships sha256sum only since 15;
# shasum is everywhere.
verify_sha256() {
  local actual
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$2" | awk '{print $1}')"
  else
    actual="$(shasum -a 256 "$2" | awk '{print $1}')"
  fi
  [[ -n "$1" && "$1" == "${actual}" ]]
}

as_service_user() {
  if [[ "${PLATFORM}" == "Linux" ]]; then
    runuser -u "${SERVICE_USER}" -- "$@"
  else
    "$@"
  fi
}

xml_escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

# An ssh:// repository's login and host, for an SSH check. A port after the
# host is honoured; IPv6 literals in brackets are not parsed.
ssh_target_of() {
  local authority="${1#*://}"
  authority="${authority%%/*}"
  SSH_TARGET_HOST="${authority}"
  SSH_TARGET_PORT="22"
  if [[ "${authority}" == *:* && "${authority##*:}" =~ ^[0-9]+$ ]]; then
    SSH_TARGET_HOST="${authority%:*}"
    SSH_TARGET_PORT="${authority##*:}"
  fi
}

# One connection as the user the agent runs as: the first contact with a host
# is where the host key gets confirmed, which a service cannot do later. The
# remote command is ignored by a forced borg serve, whose stdin then ends at
# once, so this returns either way. A failure is reported, not fatal.
test_ssh_target() {
  local rc=0
  ssh_target_of "$1"
  # A host that starts with "-" would reach ssh as an option such as
  # -oProxyCommand=..., which runs a command on this machine.
  if [[ -z "${SSH_TARGET_HOST}" || "${SSH_TARGET_HOST}" == -* ]]; then
    echo "Not an SSH host: '${SSH_TARGET_HOST}'. Skipping the SSH check." >&2
    return 0
  fi
  echo "Connecting to ${SSH_TARGET_HOST} (port ${SSH_TARGET_PORT}) as ${SERVICE_USER}."
  as_service_user ssh -o ConnectTimeout=15 -p "${SSH_TARGET_PORT}" -- \
    "${SSH_TARGET_HOST}" exit </dev/null || rc=$?
  if [[ "${rc}" -eq 0 ]]; then
    echo "SSH connection to ${SSH_TARGET_HOST}: OK."
  else
    echo "SSH connection to ${SSH_TARGET_HOST} failed (exit ${rc}). The agent cannot reach" >&2
    echo "this repository until ${SERVICE_USER} can log in there without a prompt." >&2
  fi
}

# Asks for the repository on the terminal, when there is one and nothing was
# given on the command line. Reads the terminal directly: stdin is the script
# itself when it is piped into bash.
ask_repository_defaults() {
  local answer
  { exec 3<>/dev/tty; } 2>/dev/null || return 0
  printf 'Borg repository this machine backs up to (BORG_REPO, e.g. ssh://user@host:23/./repo; empty to skip): ' >&3
  IFS= read -r BORG_REPO_VALUE <&3 || BORG_REPO_VALUE=""
  if [[ -n "${BORG_REPO_VALUE}" ]]; then
    printf 'Borg executable on that host (BORG_REMOTE_PATH, empty for the default): ' >&3
    IFS= read -r BORG_REMOTE_PATH_VALUE <&3 || BORG_REMOTE_PATH_VALUE=""
    if [[ "${BORG_REPO_VALUE}" == ssh://* ]]; then
      printf 'Open an SSH connection to it now, to confirm the host key and the login? [Y/n] ' >&3
      IFS= read -r answer <&3 || answer="n"
      if [[ -z "${answer}" || "${answer}" =~ ^[Yy] ]]; then
        SSH_CHECK_REQUESTED="1"
      fi
    fi
  fi
  exec 3>&-
}

# The values land on one KEY="value" line each, read back by this script and
# by systemd, so a quote, a backslash or a line break would change what the
# file means. launchd's plist escapes its own delimiters.
validate_repository_values() {
  local name value
  # The command the Add Agent dialog shows carries a placeholder for the
  # repository; one left in place would be reported as this machine's repository.
  if [[ "${BORG_REPO_VALUE}" == "<"*">" ]]; then
    echo "Replace ${BORG_REPO_VALUE} with the repository this machine backs up to," >&2
    echo "or leave --borg-repo out." >&2
    exit 2
  fi
  for name in BORG_REPO BORG_REMOTE_PATH; do
    if [[ "${name}" == "BORG_REPO" ]]; then value="${BORG_REPO_VALUE}"; else value="${BORG_REMOTE_PATH_VALUE}"; fi
    case "${value}" in
      *\"* | *\\* | *$'\n'*)
        echo "${name} must not contain quotes, backslashes or line breaks." >&2
        exit 2
        ;;
    esac
  done
}

# The values as KEY="value" lines, 0600, next to the config: what the service
# definition is rendered from, and what a reinstall reads back.
#
# On Linux root writes this into a directory the service user owns, and the
# agent can start that run itself through the upgrade trigger. A redirect or a
# chown there would follow a link the agent planted in the file's place, so
# the file is built in root's staging directory and renamed over whatever
# entry is there, which follows nothing. It stays root's: systemd reads it as
# root, and the agent gets the values from its environment.
write_agent_env() {
  local staged
  if [[ -z "${BORG_REPO_VALUE}" && -z "${BORG_REMOTE_PATH_VALUE}" ]]; then
    rm -f "${AGENT_ENV_FILE}"
    return 0
  fi
  staged="$(mktemp "${AGENT_ENV_STAGING_DIR}/.borg-ui-agent-env.XXXXXX")"
  {
    [[ -n "${BORG_REPO_VALUE}" ]] && printf 'BORG_REPO="%s"\n' "${BORG_REPO_VALUE}"
    [[ -n "${BORG_REMOTE_PATH_VALUE}" ]] && printf 'BORG_REMOTE_PATH="%s"\n' "${BORG_REMOTE_PATH_VALUE}"
    true
  } >"${staged}"
  chmod 0600 "${staged}"
  mv -f "${staged}" "${AGENT_ENV_FILE}"
}

read_agent_env() {
  [[ -r "${AGENT_ENV_FILE}" ]] || return 0
  # A flag on the command line wins; the file fills in only what was not given.
  if [[ "${BORG_REPO_SET}" == "0" ]]; then
    BORG_REPO_VALUE="$(sed -nE 's/^BORG_REPO="(.*)"$/\1/p' "${AGENT_ENV_FILE}" | head -n 1)"
  fi
  if [[ "${BORG_REMOTE_PATH_SET}" == "0" ]]; then
    BORG_REMOTE_PATH_VALUE="$(sed -nE 's/^BORG_REMOTE_PATH="(.*)"$/\1/p' "${AGENT_ENV_FILE}" | head -n 1)"
  fi
}

# Loads a launchd job, or reloads it when its definition changed: launchd reads
# a plist only at bootstrap, and bootstrapping a loaded job is an error.
ensure_launch_agent() {
  local label="$1" plist="$2" domain
  domain="gui/$(id -u)"
  if launchctl print "${domain}/${label}" >/dev/null 2>&1; then
    if [[ "${label}" == "${UPGRADE_JOB_LABEL}" && "${BORG_UI_UPGRADE_JOB:-}" == "1" ]]; then
      # This very job is running the reinstall; unloading it would end the
      # reinstall here. The rewritten definition applies at the next login.
      return 0
    fi
    launchctl bootout "${domain}/${label}" || true
    # bootout can return before launchd has let go of the label.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      launchctl print "${domain}/${label}" >/dev/null 2>&1 || break
      sleep 0.5
    done
  fi
  # A bootstrap that follows a bootout too closely fails with an input/output
  # error and succeeds moments later, so it is tried again before giving up.
  for _ in 1 2 3 4 5; do
    if launchctl bootstrap "${domain}" "${plist}" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  launchctl bootstrap "${domain}" "${plist}"
}

# The agent job. KeepAlive with a throttle is Restart=always / RestartSec=10.
# launchd expands no ~ and sources no shell profile, so every path is absolute
# and the PATH the agent resolves Borg through is stated here, forwarders
# first. No secret goes in: the passphrase arrives per job from the server.
write_agent_launch_agent() {
  local plist="${LAUNCH_AGENTS_DIR}/${AGENT_JOB_LABEL}.plist" root logs repo_env=""
  root="$(xml_escape "${AGENT_ROOT}")"
  logs="$(xml_escape "${LOG_DIR}")"
  if [[ -n "${BORG_REPO_VALUE}" ]]; then
    repo_env+="    <key>BORG_REPO</key>
    <string>$(xml_escape "${BORG_REPO_VALUE}")</string>
"
  fi
  if [[ -n "${BORG_REMOTE_PATH_VALUE}" ]]; then
    repo_env+="    <key>BORG_REMOTE_PATH</key>
    <string>$(xml_escape "${BORG_REMOTE_PATH_VALUE}")</string>
"
  fi
  cat >"${plist}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${AGENT_JOB_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${root}/.venv/bin/borg-ui-agent</string>
    <string>--config</string>
    <string>${root}/config.toml</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${root}/bin:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
${repo_env}  </dict>
  <key>StandardOutPath</key>
  <string>${logs}/agent.log</string>
  <key>StandardErrorPath</key>
  <string>${logs}/agent.err</string>
</dict>
</plist>
PLIST
  chmod 0644 "${plist}"
}

# The upgrade job: launchd's PathState keeps it running while the trigger
# exists, which is what a systemd path unit's PathExists= does. The helper
# removes the trigger first, so one request runs it once.
write_upgrade_launch_agent() {
  local root logs
  root="$(xml_escape "${AGENT_ROOT}")"
  logs="$(xml_escape "${LOG_DIR}")"
  cat >"${UPGRADE_UNIT}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${UPGRADE_JOB_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${root}/bin/borg-ui-agent-upgrade</string>
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>KeepAlive</key>
  <dict>
    <key>PathState</key>
    <dict>
      <key>${root}/upgrade-requested</key>
      <true/>
    </dict>
  </dict>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>${root}/bin:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>BORG_UI_UPGRADE_ETC</key>
    <string>${root}</string>
    <key>BORG_UI_UPGRADE_CONF</key>
    <string>${root}/upgrade.conf</string>
    <key>BORG_UI_UPGRADE_TRIGGER</key>
    <string>${root}/upgrade-requested</string>
    <key>BORG_UI_UPGRADE_JOB</key>
    <string>1</string>
  </dict>
  <key>StandardOutPath</key>
  <string>${logs}/upgrade.log</string>
  <key>StandardErrorPath</key>
  <string>${logs}/upgrade.log</string>
</dict>
</plist>
PLIST
  chmod 0644 "${UPGRADE_UNIT}"

  # A trigger left over from before would run the helper the moment the job
  # loads, reinstalling on top of this install.
  rm -f "${UPGRADE_TRIGGER}"
  ensure_launch_agent "${UPGRADE_JOB_LABEL}" "${UPGRADE_UNIT}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server)
      SERVER="${2:-}"
      shift 2
      ;;
    --token)
      TOKEN="${2:-}"
      shift 2
      ;;
    --name)
      AGENT_NAME="${2:-}"
      shift 2
      ;;
    --reinstall)
      REINSTALL="1"
      shift
      ;;
    --version)
      AGENT_REF="${2:-main}"
      shift 2
      ;;
    --borg-version)
      BORG_VERSION="${2:-1}"
      case "${BORG_VERSION}" in
        1|2|both)
          ;;
        *)
          echo "--borg-version must be one of: 1, 2, both." >&2
          exit 2
          ;;
      esac
      BORG_VERSION_SET="1"
      shift 2
      ;;
    --skip-borg-install)
      SKIP_BORG_INSTALL="1"
      shift
      ;;
    --borg-repo)
      BORG_REPO_VALUE="${2:-}"
      BORG_REPO_SET="1"
      shift 2
      ;;
    --borg-remote-path)
      BORG_REMOTE_PATH_VALUE="${2:-}"
      BORG_REMOTE_PATH_SET="1"
      shift 2
      ;;
    --no-prompt)
      PROMPT="0"
      shift
      ;;
    --no-remote-upgrade)
      REMOTE_UPGRADE="0"
      REMOTE_UPGRADE_SET="1"
      shift
      ;;
    --remote-upgrade)
      REMOTE_UPGRADE="1"
      REMOTE_UPGRADE_SET="1"
      shift
      ;;
    --borg-source)
      BORG_SOURCE="${2:-server}"
      case "${BORG_SOURCE}" in
        server|distro)
          ;;
        *)
          echo "--borg-source must be one of: server, distro." >&2
          exit 2
          ;;
      esac
      shift 2
      ;;
    --agent-source)
      AGENT_SOURCE="${2:-server}"
      case "${AGENT_SOURCE}" in
        server|git)
          ;;
        *)
          echo "--agent-source must be one of: server, git." >&2
          exit 2
          ;;
      esac
      shift 2
      ;;
    --service-user)
      if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "--service-user requires one of: current, borg-ui-agent, root, or an existing username." >&2
        exit 2
      fi
      SERVICE_USER_MODE="$2"
      SERVICE_USER_MODE_SET="1"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "${PLATFORM}" == "Darwin" ]]; then
  configure_darwin_layout
  if [[ "${EUID}" -eq 0 ]]; then
    echo "On macOS, run this installer as the user whose data is backed up, without sudo." >&2
    echo "A root job would need its own Full Disk Access grant and still could not read that user's data without it." >&2
    exit 1
  fi
  if [[ "${SERVICE_USER_MODE_SET}" == "1" ]]; then
    echo "--service-user is Linux only; on macOS the agent runs as the current user." >&2
    exit 2
  fi
  if [[ "${BORG_SOURCE}" == "distro" ]]; then
    echo "--borg-source distro is Linux only; macOS has no distribution Borg." >&2
    exit 2
  fi
  # The agent's jobs live in the user's launchd login session (gui/<uid>),
  # which exists only while the user is logged in at the Mac, at its screen
  # or through Screen Sharing. An ssh session alone has none: the jobs could
  # not be loaded now and would not run until that login.
  if ! launchctl print "gui/$(id -u)" >/dev/null 2>&1; then
    echo "$(id -un) is not logged in at this Mac; the agent runs in that login session." >&2
    echo "Log in as $(id -un) at the Mac or through Screen Sharing, then run this again." >&2
    exit 1
  fi
elif [[ "${PLATFORM}" != "Linux" ]]; then
  echo "This installer supports Linux and macOS; this machine reports ${PLATFORM}." >&2
  exit 1
elif [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root, usually through sudo." >&2
  exit 1
fi

if [[ "${REINSTALL}" == "1" ]]; then
  if [[ ! -r "${CONFIG_DIR}/config.toml" ]]; then
    echo "Reinstall mode requires an existing ${CONFIG_DIR}/config.toml." >&2
    echo "Use the Add Agent install command for first-time enrollment." >&2
    exit 2
  fi
  if [[ "${BORG_VERSION_SET}" == "0" ]]; then
    SKIP_BORG_INSTALL="1"
    echo "Skipping Borg installation by default for reinstall mode."
  fi
  # Reinstall takes no --server, but the agent package still comes from the
  # server this machine is enrolled against. Prefer the root-owned upgrade
  # record: config.toml belongs to the service user, so an agent that rewrote
  # its own server_url would otherwise have this reinstall fetch and run code
  # from wherever it named, and record that server for every later upgrade.
  if [[ -z "${SERVER}" && -r "${UPGRADE_CONF}" ]]; then
    SERVER="$(sed -nE 's/^SERVER="(.*)"$/\1/p' "${UPGRADE_CONF}" | head -n 1)"
    # set-server moves config.toml only, so the two can name different
    # servers. The record still wins, for the reason above; say what it takes
    # to move it, because no reinstall from the old address ever will. The
    # config's address is shown only as a plain URL and never as a command to
    # copy: the agent can write that file.
    ENROLLED_SERVER="$(sed -nE 's/^server_url[[:space:]]*=[[:space:]]*"(.*)"[[:space:]]*$/\1/p' \
      "${CONFIG_DIR}/config.toml" | head -n 1)"
    if [[ -n "${SERVER}" && -n "${ENROLLED_SERVER}" &&
      "${ENROLLED_SERVER%/}" != "${SERVER%/}" ]]; then
      if [[ ! "${ENROLLED_SERVER}" =~ ^https?://[A-Za-z0-9._:/-]+$ ]]; then
        ENROLLED_SERVER="another server"
      fi
      echo "The upgrade record names ${SERVER}, but this agent is enrolled" >&2
      echo "against ${ENROLLED_SERVER}. Reinstalling from ${SERVER}." >&2
      echo "If this endpoint was moved on purpose, run the reinstall with --server" >&2
      echo "and the new address to make remote upgrade work again." >&2
    fi
  fi
  if [[ -z "${SERVER}" ]]; then
    SERVER="$(sed -nE 's/^server_url[[:space:]]*=[[:space:]]*"(.*)"[[:space:]]*$/\1/p' \
      "${CONFIG_DIR}/config.toml" | head -n 1)"
  fi
elif [[ -z "${SERVER}" || -z "${TOKEN}" || -z "${AGENT_NAME}" ]]; then
  echo "--server, --token, and --name are required." >&2
  usage >&2
  exit 2
fi

AGENT_ENV_FILE="${CONFIG_DIR}/agent.env"
if [[ "${REINSTALL}" == "1" ]]; then
  read_agent_env
elif [[ "${PLATFORM}" == "Darwin" && "${BORG_REPO_SET}" == "0" &&
  "${BORG_REMOTE_PATH_SET}" == "0" && "${PROMPT}" == "1" ]]; then
  # Only on macOS, where someone runs the command at the Mac. A Linux install
  # is as often scripted, over ssh -t or by configuration management, and a
  # question on its terminal would hang it.
  ask_repository_defaults
fi
validate_repository_values

# A server that knows which endpoint is asking resolves that endpoint's pins
# into the block at the top of this script (installer_pins_for_agent in
# app/api/agent_installer.py). The pinned Borg version has to beat two things
# that describe how this endpoint was installed rather than what it should
# run: the --borg-version the upgrade helper passes from upgrade.conf, and
# reinstall mode's skip-by-default above. Without that precedence a Borg
# choice made in the UI could never reach an endpoint.
#
# Setting BORG_VERSION_SET and clearing SKIP_BORG_INSTALL is also what makes
# the choice stick: write_upgrade_conf then records BORG_INSTALL_MODE from
# BORG_VERSION, so this endpoint's own record follows the pin.
apply_pinned_borg_version() {
  if [[ -z "${PINNED_DESIRED_BORG_VERSION}" ]]; then
    return 0
  fi

  # The server drops anything but 1 or 2 before serving it. Repeated here
  # because this script is also runnable straight from the repository, and a
  # value that reaches the case below unmatched would skip Borg silently.
  case "${PINNED_DESIRED_BORG_VERSION}" in
    1 | 2) ;;
    *)
      echo "Ignoring unusable pinned Borg version" \
        "'${PINNED_DESIRED_BORG_VERSION}'." >&2
      return 0
      ;;
  esac

  BORG_VERSION="${PINNED_DESIRED_BORG_VERSION}"
  BORG_VERSION_SET="1"
  SKIP_BORG_INSTALL="0"

  if [[ "${BORG_VERSION}" == "2" && "${BORG_SOURCE}" == "distro" ]]; then
    # install_borg2 exits when the source is distro, which would fail this
    # whole reinstall and lose the agent upgrade with it. The pin is explicit,
    # so prefer the server's static binaries over refusing.
    BORG_SOURCE="server"
    echo "No distribution ships Borg 2, so the pinned Borg 2 comes from the" \
      "server's binaries."
  fi

  echo "This endpoint is pinned to Borg ${BORG_VERSION}."
}

apply_pinned_borg_version

resolve_user_group_home() {
  local username="$1"
  local passwd_entry

  passwd_entry="$(getent passwd "${username}" || true)"
  if [[ -z "${passwd_entry}" ]]; then
    echo "Service user '${username}' does not exist. Create it first or choose --service-user current, borg-ui-agent, or root." >&2
    exit 2
  fi

  SERVICE_USER="${username}"
  SERVICE_GROUP="$(id -gn "${username}")"
  SERVICE_HOME="$(printf '%s\n' "${passwd_entry}" | cut -d: -f6)"
  if [[ -z "${SERVICE_HOME}" ]]; then
    SERVICE_HOME="/"
  fi
}

resolve_current_service_user() {
  if [[ -z "${SUDO_USER:-}" || "${SUDO_USER:-}" == "root" ]]; then
    echo "SUDO_USER is not set. Re-run with sudo from a non-root user, or pass --service-user root or --service-user USERNAME." >&2
    exit 2
  fi
  resolve_user_group_home "${SUDO_USER}"
}

resolve_service_identity() {
  case "${SERVICE_USER_MODE}" in
    current)
      resolve_current_service_user
      ;;
    borg-ui-agent)
      if ! getent passwd borg-ui-agent >/dev/null; then
        useradd --system --user-group --home-dir /var/lib/borg-ui-agent \
          --create-home --shell /usr/sbin/nologin borg-ui-agent
      fi
      resolve_user_group_home "borg-ui-agent"
      SERVICE_READ_WRITE_PATHS="/etc/borg-ui-agent /var/lib/borg-ui-agent /tmp"
      ;;
    root)
      resolve_user_group_home "root"
      ;;
    *)
      resolve_user_group_home "${SERVICE_USER_MODE}"
      ;;
  esac
}

# In reinstall mode, preserve the existing service user from the live systemd
# unit unless the caller explicitly chose one with --service-user. Without
# this, a bare --reinstall would silently flip User= to the sudo invoker and
# the service would lose read access to /etc/borg-ui-agent/config.toml.
if [[ "${PLATFORM}" == "Linux" && "${REINSTALL}" == "1" && "${SERVICE_USER_MODE_SET}" == "0" ]]; then
  existing_unit_user=""
  if [[ -r /etc/systemd/system/borg-ui-agent.service ]]; then
    existing_unit_user="$(awk -F= '/^User=/ {print $2; exit}' \
      /etc/systemd/system/borg-ui-agent.service 2>/dev/null || true)"
  fi
  if [[ -n "${existing_unit_user}" ]]; then
    SERVICE_USER_MODE="${existing_unit_user}"
    echo "Reinstall: preserving existing service user '${existing_unit_user}'."
  fi
fi

# A reinstall keeps the operator's earlier answer about remote upgrade unless
# this run gives one explicitly. The marker records a decline; its absence
# means "never asked", which is also what an endpoint installed before remote
# upgrade existed looks like, and that endpoint should gain the helper here.
if [[ "${REMOTE_UPGRADE_SET}" == "0" && -e "${NO_REMOTE_UPGRADE_MARKER}" ]]; then
  REMOTE_UPGRADE="0"
  echo "Reinstall: remote upgrade stays declined (${NO_REMOTE_UPGRADE_MARKER} exists)."
fi

if [[ "${PLATFORM}" == "Linux" ]]; then
  if [[ ! -r /etc/os-release ]]; then
    echo "Cannot detect Linux distribution: /etc/os-release is missing." >&2
    exit 1
  fi

  . /etc/os-release
  OS_ID="${ID:-}"
  OS_ID_LIKE="${ID_LIKE:-}"
  OS_FAMILY="${OS_ID} ${OS_ID_LIKE}"
  if [[ "${OS_FAMILY}" != *debian* && "${OS_FAMILY}" != *ubuntu* && "${OS_FAMILY}" != *raspbian* ]]; then
    echo "This installer currently supports Debian-family Linux distributions." >&2
    exit 1
  fi

  export DEBIAN_FRONTEND=noninteractive
  resolve_service_identity

  apt-get update
  apt-get install -y python3 python3-venv python3-pip curl ca-certificates
  # Only the development install path needs git; the default installs a package
  # built by the enrolling server.
  if [[ "${AGENT_SOURCE}" == "git" ]]; then
    apt-get install -y git
  fi

  install -d -m 0755 /opt/borg-ui-agent
  install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 /etc/borg-ui-agent
  if [[ "${SERVICE_USER_MODE}" == "borg-ui-agent" ]]; then
    install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 /var/lib/borg-ui-agent
  fi
else
  # The user's own directories; the config inside is 0600 on its own.
  install -d -m 0700 "${AGENT_ROOT}"
  install -d -m 0755 "${LOG_DIR}" "${LAUNCH_AGENTS_DIR}"
fi

# Asked for with the repository questions, which only a macOS install asks.
# The connection runs as the service user, the user the agent runs as, so the
# host key lands in its known_hosts.
if [[ "${SSH_CHECK_REQUESTED}" == "1" ]]; then
  test_ssh_target "${BORG_REPO_VALUE}"
fi

prepare_agent_config_path() {
  local config_path="${CONFIG_DIR}/config.toml"

  if [[ "${REINSTALL}" == "1" ]]; then
    if [[ ! -f "${config_path}" || -L "${config_path}" ]]; then
      echo "Agent config '${config_path}' must be a regular file." >&2
      exit 1
    fi
    if [[ "${PLATFORM}" == "Linux" ]]; then
      chown "${SERVICE_USER}:${SERVICE_GROUP}" "${config_path}"
    fi
    chmod 0600 "${config_path}"
    return
  fi

  rm -f "${config_path}"
}

prepare_agent_config_path

verify_borg_major() {
  local binary_name="$1"
  local expected_major="$2"
  local binary_path

  binary_path="$(command -v "${binary_name}" 2>/dev/null || true)"
  if [[ -z "${binary_path}" ]]; then
    echo "Required Borg binary '${binary_name}' was not found." >&2
    return 1
  fi

  verify_borg_path "${binary_path}" "${binary_name}" "${expected_major}"
}

verify_borg_path() {
  local binary_path="$1"
  local binary_name="$2"
  local expected_major="$3"
  local output major

  if [[ ! -x "${binary_path}" ]]; then
    echo "Required Borg binary '${binary_name}' was not executable at ${binary_path}." >&2
    return 1
  fi

  output="$("${binary_path}" --version 2>&1)"
  major="$(printf '%s\n' "${output}" | sed -nE 's/.* ([0-9]+)\..*/\1/p' | head -n 1)"
  if [[ "${major}" != "${expected_major}" ]]; then
    echo "Expected ${binary_name} to be Borg ${expected_major}.x, got: ${output}" >&2
    return 1
  fi

  echo "Verified ${binary_name}: ${output} (${binary_path})"
}

# Which published static binary this machine can run. Borg builds against a
# minimum glibc on Linux and a minimum macOS on Darwin, so the newest build
# the machine satisfies is the right one.
detect_machine() {
  MACHINE_ARCH="$(uname -m)"
  case "${MACHINE_ARCH}" in
    amd64) MACHINE_ARCH="x86_64" ;;
    arm64) MACHINE_ARCH="aarch64" ;;
  esac

  if [[ "${PLATFORM}" == "Darwin" ]]; then
    MACHINE_PLATFORM="darwin"
    MACHINE_FLOOR_NAME="macOS"
    MACHINE_FLOOR="$(sw_vers -productVersion 2>/dev/null || true)"
    return
  fi

  MACHINE_PLATFORM="linux"
  MACHINE_FLOOR_NAME="glibc"
  MACHINE_FLOOR="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')"
  if [[ -z "${MACHINE_FLOOR}" ]]; then
    MACHINE_FLOOR="$(ldd --version 2>/dev/null | head -n 1 |
      grep -oE '[0-9]+\.[0-9]+$' || true)"
  fi
}

# True when the machine's glibc, or macOS, is at least $1. sort -V orders
# versions, and -C reports whether the input was already ordered.
machine_floor_at_least() {
  [[ -n "${MACHINE_FLOOR}" ]] || return 1
  printf '%s\n%s\n' "$1" "${MACHINE_FLOOR}" | sort -V -C
}

select_borg_binary() {
  local major="$1"
  local row_major row_platform row_arch row_floor row_sha row_url best_floor=""

  BINARY_URL=""
  BINARY_SHA=""

  while read -r row_major row_platform row_arch row_floor row_sha row_url; do
    [[ -n "${row_major:-}" ]] || continue
    [[ "${row_major}" == "${major}" ]] || continue
    [[ "${row_platform}" == "${MACHINE_PLATFORM}" ]] || continue
    [[ "${row_arch}" == "${MACHINE_ARCH}" ]] || continue
    machine_floor_at_least "${row_floor}" || continue

    if [[ -z "${best_floor}" ]] ||
      printf '%s\n%s\n' "${best_floor}" "${row_floor}" | sort -V -C; then
      best_floor="${row_floor}"
      BINARY_URL="${row_url}"
      BINARY_SHA="${row_sha}"
    fi
  done <<<"${PINNED_BORG_BINARIES}"

  [[ -n "${BINARY_URL}" ]]
}

# The lowest glibc or macOS the pinned Borg $1 asks of this platform and
# architecture (the floor a machine has to clear), or nothing when no binary
# exists for them at all. Borg raises the floor whenever it moves its build
# runner, so the number comes from the manifest, never from this script.
lowest_floor_offered() {
  local major="$1"
  local row_major row_platform row_arch row_floor row_sha row_url lowest=""

  while read -r row_major row_platform row_arch row_floor row_sha row_url; do
    [[ -n "${row_major:-}" ]] || continue
    [[ "${row_major}" == "${major}" ]] || continue
    [[ "${row_platform}" == "${MACHINE_PLATFORM}" ]] || continue
    [[ "${row_arch}" == "${MACHINE_ARCH}" ]] || continue
    if [[ -z "${lowest}" ]] ||
      printf '%s\n%s\n' "${row_floor}" "${lowest}" | sort -V -C; then
      lowest="${row_floor}"
    fi
  done <<<"${PINNED_BORG_BINARIES}"

  printf '%s' "${lowest}"
}

# What to do when the pinned Borg $1 (version $2) cannot come from the server.
# Borg 1 has distribution packages; Borg 2 has none, so the only way past is a
# self-managed install exposed under the name the agent resolves: 'borg2' at
# the link $3, the same contract the forwarder written by
# install_borg_from_server fulfils. A pip install alone provides only 'borg'.
# The suggested commands are pinned to the server's version, so agent and
# server keep speaking the same Borg; without a reported version there is
# nothing to pin and no command is printed.
borg_fallback_advice() {
  local major="$1" version="$2" link="$3"

  if [[ "${MACHINE_PLATFORM}" == "darwin" ]]; then
    echo "Install Borg ${major} yourself, expose it as '${link##*/}' on PATH, and re-run" >&2
    echo "with --skip-borg-install." >&2
    return
  fi

  if [[ "${major}" == "1" ]]; then
    echo "Re-run with --borg-source distro to use the distribution package," >&2
    echo "or with --skip-borg-install to manage Borg yourself." >&2
    return
  fi

  echo "No distribution ships Borg 2 yet. Install the version this server runs" >&2
  echo "yourself and expose it as 'borg2' on PATH, then re-run with --skip-borg-install." >&2
  if [[ -n "${version}" ]]; then
    echo "For example (needs a C toolchain, Borg's build dependencies and OpenSSL 3.2 or newer):" >&2
    echo "  python3 -m venv /opt/borg2" >&2
    printf '  /opt/borg2/bin/pip install --pre "borgbackup==%s" "borgstore[rclone,sftp,rest,s3,blake3]"\n' "${version}" >&2
    echo "  ln -sfn /opt/borg2/bin/borg ${link}" >&2
  fi
}

install_borg_binary() {
  local major="$1" version="$2" dest_dir dest tmp

  dest_dir="${AGENT_ROOT}/borg${major}/${version}"
  dest="${dest_dir}/borg"

  if [[ -x "${dest}" ]]; then
    echo "Borg ${version} already present at ${dest}."
  else
    install -d -m 0755 "${AGENT_ROOT}" "${AGENT_ROOT}/borg${major}" "${dest_dir}"
    tmp="$(mktemp)"
    echo "Downloading Borg ${version} for ${MACHINE_ARCH} (${MACHINE_FLOOR_NAME} ${MACHINE_FLOOR})."
    curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}" "${BINARY_URL}"
    if ! verify_sha256 "${BINARY_SHA}" "${tmp}"; then
      rm -f "${tmp}"
      echo "Checksum mismatch for Borg ${version}; refusing to install it." >&2
      exit 1
    fi
    install -m 0755 "${tmp}" "${dest}"
    rm -f "${tmp}"
  fi

  verify_borg_path "${dest}" "borg${major}" "${major}"
  BORG_BINARY_PATH="${dest}"
}

# A forwarder rather than a symlink to the binary: it is the one place that can
# later carry policy (exit-code handling, elevation) without touching callers.
# It lives under AGENT_ROOT so the agent keeps reporting an installer-managed
# binary; /usr/local/bin holds only a symlink to it.
#
# STREAM INVARIANT: never merge stdout into stderr here. Borg UI parses Borg's
# stdout (--json) and reads stderr for warnings, so the two must stay separate.
write_forwarder() {
  local name="$1" target="$2" link="$3" forwarder

  forwarder="${BORG_FORWARDER_DIR}/${name}"
  install -d -m 0755 "${BORG_FORWARDER_DIR}"
  cat >"${forwarder}" <<FORWARDER
#!/usr/bin/env bash
# Installed by the Borg UI agent installer. Runs the Borg version this machine's
# Borg UI server runs, ahead of any distribution package on PATH.
exec "${target}" "\$@"
FORWARDER
  own_root "${forwarder}"
  chmod 0755 "${forwarder}"

  # The agent finds Borg through PATH, and /usr/local/bin precedes /usr/bin, so
  # this symlink is what makes it use the pinned binary rather than the
  # distribution's. Anything else already sitting there is left alone. On
  # macOS the link lives in the forwarder directory, which leads the job's
  # PATH, and a forwarder that already carries the name needs no link.
  if [[ "${link}" == "${forwarder}" ]]; then
    return
  fi
  if [[ -L "${link}" ]] || [[ ! -e "${link}" ]]; then
    ln -sfn "${forwarder}" "${link}"
  else
    echo "${link} exists and is not a symlink; leaving it untouched." >&2
    echo "The agent will use whichever ${name} PATH resolves to." >&2
  fi
}

install_borg_from_server() {
  local major="$1" version="$2" link="$3"

  if [[ -z "${version}" ]]; then
    echo "This Borg UI server did not report a Borg ${major} version." >&2
    borg_fallback_advice "${major}" "" "${link}"
    exit 1
  fi

  if ! select_borg_binary "${major}"; then
    local floor
    floor="$(lowest_floor_offered "${major}")"
    if [[ -n "${floor}" ]]; then
      echo "Borg ${version} for ${MACHINE_ARCH} needs ${MACHINE_FLOOR_NAME} ${floor} or newer; this machine has ${MACHINE_FLOOR_NAME} ${MACHINE_FLOOR:-unknown}." >&2
    elif [[ "${MACHINE_PLATFORM}" == "darwin" ]]; then
      echo "No published Borg ${version} binary for macOS on ${MACHINE_ARCH}." >&2
    else
      echo "No published Borg ${version} binary for ${MACHINE_ARCH}." >&2
      echo "Borg publishes no static binary for 32-bit ARM or musl systems." >&2
    fi
    borg_fallback_advice "${major}" "${version}" "${link}"
    exit 1
  fi

  install_borg_binary "${major}" "${version}"
  write_forwarder "borg${major}" "${BORG_BINARY_PATH}" "${link}"

  # The agent resolves Borg through PATH, so confirm the name really reaches
  # what was just installed and not a distribution package that shadows it.
  local path_name="${link##*/}"
  verify_borg_major "${path_name}" "${major}"
  if ! "${path_name}" --version 2>&1 | grep -qF "${version}"; then
    echo "Warning: '${path_name}' on PATH is not the ${version} just installed." >&2
    echo "The agent would then run a different Borg than this server." >&2
  fi
}

install_borg1() {
  if [[ "${BORG_SOURCE}" == "distro" ]]; then
    if command -v borg >/dev/null 2>&1; then
      echo "Existing borg detected; verifying without replacing it."
      verify_borg_major "borg" "1"
      return
    fi
    apt-get install -y borgbackup
    verify_borg_major "borg" "1"
    return
  fi

  install_borg_from_server "1" "${PINNED_BORG1_VERSION}" "${BORG1_LINK}"
}

# Borg 2 reaches rclone remotes by driving an rclone process, which borgstore
# expects on PATH. It is a separate Go program that no Borg release bundles, so
# rclone repositories fail at use time unless it is installed here. Installed
# alongside Borg 2 rather than as an opt-in: a node that cannot reach a whole
# class of repositories is a worse default than one extra package.
install_rclone() {
  local version

  if ! command -v rclone >/dev/null 2>&1 && [[ "${PLATFORM}" == "Linux" ]]; then
    # Non-fatal under `set -e`: a failed install must fall through to the warning
    # below, not abort the whole installer and leave Borg 2 without an agent.
    apt-get install -y rclone || true
  fi

  if ! command -v rclone >/dev/null 2>&1; then
    if [[ "${PLATFORM}" == "Linux" ]]; then
      echo "Warning: rclone could not be installed; rclone: repositories will not work." >&2
    else
      echo "Warning: rclone is not installed; rclone: repositories will not work until it is (rclone.org)." >&2
    fi
    return
  fi

  # borgstore requires 1.57.0 or newer. Older distributions ship less than that
  # (Debian 11 has 1.53), which is worth saying now rather than at backup time.
  version="$(rclone version 2>/dev/null | head -n 1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)"
  if [[ -n "${version}" ]] &&
    ! printf '%s\n%s\n' "1.57.0" "${version}" | sort -V -C; then
    echo "Warning: rclone ${version} is older than the 1.57.0 borgstore requires." >&2
    echo "rclone: repositories will not work until it is updated, see rclone.org." >&2
    return
  fi

  echo "Verified rclone: ${version:-unknown version}"
}

install_borg2() {
  if [[ "${BORG_SOURCE}" == "distro" ]]; then
    echo "No distribution ships Borg 2 yet; --borg-source distro cannot install it." >&2
    exit 1
  fi

  install_borg_from_server "2" "${PINNED_BORG2_VERSION}" "${BORG2_LINK}"
  install_rclone
}

if [[ "${SKIP_BORG_INSTALL}" == "1" ]]; then
  echo "Skipping Borg installation by request."
else
  detect_machine
  case "${BORG_VERSION}" in
    1)
      install_borg1
      ;;
    2)
      install_borg2
      ;;
    both)
      install_borg1
      install_borg2
      ;;
  esac
fi

# The agent package comes from the enrolling server by default, so a node runs
# the agent belonging to the server it talks to rather than whatever the
# upstream default branch holds today. --agent-source git keeps the old
# behaviour for development.
#
# Resolved into a variable rather than returned from a command substitution:
# an `exit` inside `$(...)` only leaves the subshell, so a failure there would
# hand pip an empty argument instead of stopping the install.
resolve_agent_package_source() {
  if [[ "${AGENT_SOURCE}" == "git" ]]; then
    AGENT_PIP_ARGS=("git+https://github.com/karanhudia/borg-ui.git@${AGENT_REF}")
    return
  fi

  if [[ -z "${SERVER}" ]]; then
    echo "No server URL is known, so the agent package cannot be located." >&2
    echo "Pass --server, or use --agent-source git." >&2
    exit 1
  fi

  if [[ -z "${PINNED_AGENT_VERSION}" ]]; then
    echo "This Borg UI server offers no agent package to install." >&2
    echo "Its image predates server-provided agent packages, or was built" >&2
    echo "without one. Re-run with --agent-source git to install from the" >&2
    echo "upstream repository instead." >&2
    exit 1
  fi

  # Air-gapped by construction: the agent wheel and its dependency wheels are all
  # served by this one server, so pip resolves the whole closure from --find-links
  # with the index switched off. No PyPI, no compiler on the node -- it reaches
  # exactly one host, the one it is enrolling against.
  AGENT_PIP_ARGS=(
    --no-index
    --find-links "${SERVER%/}/agent/dist/"
    "borg-ui-agent==${PINNED_AGENT_VERSION}"
  )

  # pip ignores an http find-links host unless it is named as trusted, and
  # then reports only "no matching distribution" (#1272). The whole authority
  # goes in, port and all: pip takes host:port, and it spares parsing a
  # bracketed IPv6 address. Over https nothing is added: verification stays
  # on, against the system trust store on Debian-family pip, so a self-signed
  # server certificate installed with update-ca-certificates satisfies pip as
  # it does curl and the agent.
  if [[ "${SERVER}" == http://* ]]; then
    local authority="${SERVER#http://}"
    AGENT_PIP_ARGS+=(--trusted-host "${authority%%/*}")
  fi
}

AGENT_PIP_ARGS=()
resolve_agent_package_source

# Which published Python build this machine can run: the pinned version's
# build for its platform and architecture.
select_python_runtime() {
  local row_platform row_arch row_sha row_url

  RUNTIME_URL=""
  RUNTIME_SHA=""

  while read -r row_platform row_arch row_sha row_url; do
    [[ -n "${row_platform:-}" ]] || continue
    [[ "${row_platform}" == "${MACHINE_PLATFORM}" ]] || continue
    [[ "${row_arch}" == "${MACHINE_ARCH}" ]] || continue
    RUNTIME_URL="${row_url}"
    RUNTIME_SHA="${row_sha}"
  done <<<"${PINNED_PYTHON_RUNTIMES}"

  [[ -n "${RUNTIME_URL}" ]]
}

# macOS ships no Python the agent can use (the system python3 is a Command Line
# Tools stub at 3.9), so the server pins a relocatable CPython build the way it
# pins Borg: selected by architecture, verified against the manifest's digest,
# unpacked under the agent root. A reinstall keeps a runtime whose recorded
# version matches the pin and replaces one that does not, together with the
# virtualenv made from it, which links to the interpreter by path.
install_python_runtime() {
  local runtime_dir="${AGENT_ROOT}/python" stamp tmp
  stamp="${runtime_dir}/.borg-ui-runtime"

  if [[ -z "${PINNED_PYTHON_VERSION}" ]]; then
    echo "This Borg UI server offers no Python runtime for macOS." >&2
    echo "Its image predates macOS agents." >&2
    exit 1
  fi
  if [[ -x "${PYTHON_BIN}" && -r "${stamp}" ]] &&
    [[ "$(cat "${stamp}")" == "${PINNED_PYTHON_VERSION}" ]]; then
    echo "Python ${PINNED_PYTHON_VERSION} already present at ${runtime_dir}."
    return
  fi

  detect_machine
  if ! select_python_runtime; then
    echo "No published Python ${PINNED_PYTHON_VERSION} build for macOS on ${MACHINE_ARCH}." >&2
    exit 1
  fi

  tmp="$(mktemp -d)"
  echo "Downloading Python ${PINNED_PYTHON_VERSION} for ${MACHINE_ARCH}."
  curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}/python.tar.gz" "${RUNTIME_URL}"
  if ! verify_sha256 "${RUNTIME_SHA}" "${tmp}/python.tar.gz"; then
    rm -rf "${tmp}"
    echo "Checksum mismatch for Python ${PINNED_PYTHON_VERSION}; refusing to install it." >&2
    exit 1
  fi
  # Unpacked and tried beside the runtime in use, which stays until the new
  # one has answered: a failed extraction or a broken build leaves the agent
  # with the interpreter it had. The archive unpacks to python/.
  rm -rf "${runtime_dir}.new" "${runtime_dir}.old"
  mkdir -p "${runtime_dir}.new"
  if ! tar -xzf "${tmp}/python.tar.gz" -C "${runtime_dir}.new" ||
    ! "${runtime_dir}.new/python/bin/python3" -c 'import sys' >/dev/null 2>&1; then
    rm -rf "${tmp}" "${runtime_dir}.new"
    echo "Python ${PINNED_PYTHON_VERSION} could not be unpacked or does not run; keeping the current runtime." >&2
    exit 1
  fi
  rm -rf "${tmp}"
  printf '%s\n' "${PINNED_PYTHON_VERSION}" >"${runtime_dir}.new/python/.borg-ui-runtime"
  if [[ -d "${runtime_dir}" ]]; then
    mv "${runtime_dir}" "${runtime_dir}.old"
  fi
  mv "${runtime_dir}.new/python" "${runtime_dir}"
  rm -rf "${runtime_dir}.new"
  # The previous runtime waits until the agent is installed on the new one:
  # the virtualenv in use links to it by path and comes back with it.
  echo "Installed Python ${PINNED_PYTHON_VERSION} at ${runtime_dir}."
}

# The virtualenv in use and, when it was replaced, the runtime it links to.
restore_previous_agent() {
  if [[ -d "${AGENT_ROOT}/.venv.old" ]]; then
    rm -rf "${AGENT_ROOT}/.venv"
    mv "${AGENT_ROOT}/.venv.old" "${AGENT_ROOT}/.venv"
  fi
  if [[ -d "${AGENT_ROOT}/python.old" ]]; then
    rm -rf "${AGENT_ROOT}/python"
    mv "${AGENT_ROOT}/python.old" "${AGENT_ROOT}/python"
  fi
}

if [[ "${PLATFORM}" == "Darwin" ]]; then
  install_python_runtime
fi

# The agent wheel requires Python 3.11+. Under --no-index pip reports only "no
# matching distribution", which hides the real cause, so name it here. Every
# source needs it -- the wheel does not change with --agent-source git.
if ! "${PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "The agent package needs Python 3.11 or newer; this machine has $("${PYTHON_BIN}" -V 2>&1)." >&2
  if [[ "${PLATFORM}" == "Darwin" ]]; then
    # The runtime was swapped already; the virtualenv in use links to the
    # one that stepped aside, so bring that back before giving up.
    restore_previous_agent
    echo "Keeping the current agent." >&2
  else
    echo "Install a newer python3 and re-run." >&2
  fi
  exit 1
fi

if [[ "${PLATFORM}" == "Darwin" ]]; then
  # A virtualenv embeds its own path in every script it installs, so it is
  # built where it runs. The one in use steps aside and comes back, together
  # with the runtime it links to, if the package cannot be installed, so a
  # failed download leaves the agent it had.
  rm -rf "${AGENT_ROOT}/.venv.old"
  if [[ -d "${AGENT_ROOT}/.venv" ]]; then
    mv "${AGENT_ROOT}/.venv" "${AGENT_ROOT}/.venv.old"
  fi
  if ! "${PYTHON_BIN}" -m venv "${AGENT_ROOT}/.venv" ||
    ! "${AGENT_ROOT}/.venv/bin/pip" install --upgrade --force-reinstall "${AGENT_PIP_ARGS[@]}"; then
    restore_previous_agent
    echo "The agent package could not be installed; keeping the current agent." >&2
    exit 1
  fi
  rm -rf "${AGENT_ROOT}/.venv.old" "${AGENT_ROOT}/python.old"
else
  python3 -m venv "${AGENT_ROOT}/.venv"
  "${AGENT_ROOT}/.venv/bin/pip" install --upgrade --force-reinstall "${AGENT_PIP_ARGS[@]}"
fi

if [[ "${REINSTALL}" == "1" ]]; then
  echo "Preserving existing agent registration at ${CONFIG_DIR}/config.toml."
else
  # Register the machine with Borg UI using borg-ui-agent register.
  as_service_user "${AGENT_ROOT}/.venv/bin/borg-ui-agent" \
    --config "${CONFIG_DIR}/config.toml" \
    register \
    --server "${SERVER}" \
    --token "${TOKEN}" \
    --name "${AGENT_NAME}"
fi

# Backing up a whole machine means reading files the service user does not own.
# Without this, only --service-user root can produce a complete backup, and any
# operator wanting one is pushed to running the agent as root.
#
# CAP_DAC_READ_SEARCH grants exactly what a backup needs — read any file — and
# nothing else: no writing, no chown, no command execution. It inherits to the
# Borg child process, is scoped to this service rather than to a binary anyone
# can execute, and is compatible with NoNewPrivileges, so the unit keeps its
# hardened baseline.
#
# Restoring to paths the service user cannot write needs more than this and is
# deliberately not granted.
#
# A root service already holds every capability, and a bounding set there would
# restrict it rather than extend it, so the block is left out in that case.
SERVICE_CAPABILITIES=""
if [[ "${SERVICE_USER}" != "root" ]]; then
  SERVICE_CAPABILITIES="AmbientCapabilities=CAP_DAC_READ_SEARCH
CapabilityBoundingSet=CAP_DAC_READ_SEARCH"
fi

write_agent_env

if [[ "${PLATFORM}" == "Linux" ]]; then
# The repository values stay in the 0600 file: the unit is world-readable, and
# a repository URL can carry a login. The "-" tolerates a missing file.
cat >/etc/systemd/system/borg-ui-agent.service <<SERVICE
[Unit]
Description=Borg UI managed agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
ExecStart=/opt/borg-ui-agent/.venv/bin/borg-ui-agent --config /etc/borg-ui-agent/config.toml run
Restart=always
RestartSec=10
WorkingDirectory=${SERVICE_HOME}
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=${SERVICE_READ_WRITE_PATHS}
${SERVICE_CAPABILITIES}
EnvironmentFile=-/etc/borg-ui-agent/agent.env

[Install]
WantedBy=multi-user.target
SERVICE
else
  write_agent_launch_agent
fi

# Everything the self-upgrade helper needs, in a file only root can write. The
# helper takes no arguments and reads only this, so a compromised agent cannot
# redirect the install source, change the service user, or inject installer
# flags. That is what makes the sudoers rule safe to grant.
write_upgrade_conf() {
  local agent_id borg_install_mode

  agent_id="$(sed -nE 's/^agent_id[[:space:]]*=[[:space:]]*"(.*)"[[:space:]]*$/\1/p' \
    "${CONFIG_DIR}/config.toml" | head -n 1)"
  # config.toml belongs to the service user, and root sources what we write
  # below, so anything but a plain identifier here would be a root shell for a
  # compromised agent.
  if [[ ! "${agent_id}" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Could not read a usable agent_id from" >&2
    echo "${CONFIG_DIR}/config.toml; skipping remote upgrade setup. This" >&2
    echo "endpoint stays on the manual reinstall path." >&2
    return 1
  fi

  if [[ "${BORG_VERSION_SET}" == "0" && "${SKIP_BORG_INSTALL}" == "1" ]] &&
    [[ -r "${UPGRADE_CONF}" ]]; then
    # A bare --reinstall skips Borg by default. That is a choice about this run,
    # not about the endpoint, so keep whatever mode was recorded rather than
    # pinning every future remote upgrade to "skip".
    borg_install_mode="$(sed -nE 's/^BORG_INSTALL_MODE="(.*)"$/\1/p' \
      "${UPGRADE_CONF}" | head -n 1)"
  fi
  if [[ -z "${borg_install_mode:-}" ]]; then
    if [[ "${SKIP_BORG_INSTALL}" == "1" ]]; then
      borg_install_mode="skip"
    else
      borg_install_mode="${BORG_VERSION}"
    fi
  fi

  if [[ ! "${SERVER%/}" =~ ^https?://[A-Za-z0-9._:/-]+$ ]]; then
    echo "Server URL '${SERVER}' is not a plain URL; skipping remote upgrade" >&2
    echo "setup. This endpoint stays on the manual reinstall path." >&2
    return 1
  fi

  install -m 0644 /dev/null "${UPGRADE_CONF}"
  own_root "${UPGRADE_CONF}"
  cat >"${UPGRADE_CONF}" <<CONF
# Written by the Borg UI agent installer. Read by
# ${AGENT_ROOT}/bin/borg-ui-agent-upgrade, which takes no arguments.
SERVER="${SERVER%/}"
AGENT_ID="${agent_id}"
BORG_INSTALL_MODE="${borg_install_mode}"
BORG_SOURCE="${BORG_SOURCE}"
SERVICE_USER_MODE="${SERVICE_USER_MODE}"
SERVICE_USER="${SERVICE_USER}"
SERVICE_GROUP="${SERVICE_GROUP}"
AGENT_ROOT="${AGENT_ROOT}"
CONF
}

write_upgrade_helper() {
  install -d -m 0755 "${AGENT_ROOT}/bin"
  cat >"${UPGRADE_HELPER}" <<'UPGRADE_HELPER'
#!/usr/bin/env bash
# Installed by the Borg UI agent installer. Started as root by
# borg-ui-agent-upgrade.service, which the agent may start through one narrow
# sudoers rule.
#
# It takes NO ARGUMENTS on purpose. Every parameter comes from
# /etc/borg-ui-agent-upgrade.conf, which sits outside the agent-owned config
# directory and only root can write, so a compromised agent cannot change the
# install source, the service user, or the installer flags. Adding an argument
# here would undo that.
set -euo pipefail

# The overrides are test seams on Linux, where systemd passes no environment
# from whoever starts the unit, so the only way to use them is to already be
# root. On macOS the per-user launchd job sets them to the user's paths.
etc="${BORG_UI_UPGRADE_ETC:-/etc/borg-ui-agent}"
conf="${BORG_UI_UPGRADE_CONF:-/etc/borg-ui-agent-upgrade.conf}"
trigger="${BORG_UI_UPGRADE_TRIGGER:-/etc/borg-ui-agent/upgrade-requested}"
agent_config="${etc}/config.toml"

# Only a request runs a reinstall. launchd may start a job speculatively when
# it is loaded; without this an install would reinstall itself as its last step.
if [[ ! -e "${trigger}" ]]; then
  echo "No upgrade requested; nothing to do."
  exit 0
fi

# systemd re-runs a .path unit, and launchd a PathState job, for as long as the
# trigger is there, so clear it before doing anything that can fail.
rm -f "${trigger}"

if [[ ! -r "${conf}" ]]; then
  echo "Missing ${conf}; nothing to upgrade from." >&2
  exit 1
fi

# shellcheck source=/dev/null
. "${conf}"

for required in SERVER AGENT_ID BORG_INSTALL_MODE SERVICE_USER AGENT_ROOT; do
  if [[ -z "${!required:-}" ]]; then
    echo "${conf} is missing ${required}." >&2
    exit 1
  fi
done

# This script runs what it downloads, as root. An http URL is refused rather
# than downgraded to a warning.
if [[ "${SERVER}" != https://* ]]; then
  echo "Remote upgrade requires an https server URL; ${conf} names ${SERVER}." >&2
  exit 1
fi

# A config left behind by an earlier enrollment must not be able to point a
# live agent's upgrade at a host it no longer talks to.
enrolled_server=""
if [[ -r "${agent_config}" ]]; then
  enrolled_server="$(sed -nE 's/^server_url[[:space:]]*=[[:space:]]*"(.*)"[[:space:]]*$/\1/p' \
    "${agent_config}" | head -n 1)"
fi
if [[ "${enrolled_server%/}" != "${SERVER%/}" ]]; then
  echo "${conf} names ${SERVER}, but this agent is enrolled against" >&2
  echo "'${enrolled_server}'. Refusing to upgrade." >&2
  exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

# --proto '=https' holds across redirects, and --max-redirs 0 means there are
# none to hold across: any redirect is an error rather than a hop to somewhere
# this script would then execute as root.
fetch() {
  curl -fsS --proto '=https' --tlsv1.2 --max-redirs 0 -o "$2" "$1"
}

query="?agent_id=${AGENT_ID}"
fetch "${SERVER%/}/agent/install.sh${query}" "${workdir}/install.sh"
fetch "${SERVER%/}/agent/install.sh.sha256${query}" "${workdir}/install.sh.sha256"

expected="$(tr -d '[:space:]' <"${workdir}/install.sh.sha256")"
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "${workdir}/install.sh" | awk '{print $1}')"
else
  actual="$(shasum -a 256 "${workdir}/install.sh" | awk '{print $1}')"
fi
if [[ -z "${expected}" || "${expected}" != "${actual}" ]]; then
  echo "Installer checksum mismatch; expected '${expected}', got '${actual}'." >&2
  echo "Nothing was executed." >&2
  exit 1
fi

args=(--reinstall)
if [[ "$(uname -s)" != "Darwin" ]]; then
  # A macOS agent runs as the user; the installer refuses the flag there.
  args+=(--service-user "${SERVICE_USER}")
fi
if [[ "${BORG_INSTALL_MODE}" == "skip" ]]; then
  args+=(--skip-borg-install)
else
  args+=(--borg-version "${BORG_INSTALL_MODE}")
  # Without this an endpoint installed from distribution packages would be
  # repointed at the server's static binaries by its first upgrade.
  args+=(--borg-source "${BORG_SOURCE:-server}")
fi

echo "Reinstalling the Borg UI agent from ${SERVER}."
bash "${workdir}/install.sh" "${args[@]}"
UPGRADE_HELPER
  own_root "${UPGRADE_HELPER}"
  chmod 0755 "${UPGRADE_HELPER}"
}

write_upgrade_unit() {
  cat >"${UPGRADE_UNIT}" <<UPGRADE_UNIT_FILE
[Unit]
Description=Borg UI agent self-upgrade
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${AGENT_ROOT}/bin/borg-ui-agent-upgrade
UPGRADE_UNIT_FILE
  chown root:root "${UPGRADE_UNIT}"
  chmod 0644 "${UPGRADE_UNIT}"
}

# The escalation, and the whole of it: the agent creates one file, systemd
# notices and runs the helper as root. There is no sudo, no setuid binary and
# no argument the agent can pass, so nothing here has to survive the agent unit
# being run with NoNewPrivileges=true, which is what defeats sudo.
write_upgrade_path_unit() {
  cat >"${UPGRADE_PATH_UNIT}" <<'UPGRADE_PATH_FILE'
[Unit]
Description=Borg UI agent self-upgrade request

[Path]
PathExists=/etc/borg-ui-agent/upgrade-requested
Unit=borg-ui-agent-upgrade.service

[Install]
WantedBy=multi-user.target
UPGRADE_PATH_FILE
  chown root:root "${UPGRADE_PATH_UNIT}"
  chmod 0644 "${UPGRADE_PATH_UNIT}"

  # A trigger left over from before, or created while the path unit was off,
  # would fire the helper the moment the unit starts, running a second
  # installer as root on top of this one.
  rm -f "${UPGRADE_TRIGGER}"

  # The unit files are new, so systemd has to be told about them before the
  # path unit can be enabled. The reload at the end of the script is too late.
  systemctl daemon-reload
  systemctl enable --now borg-ui-agent-upgrade.path
}

remove_upgrade_artifacts() {
  if [[ "${PLATFORM}" == "Linux" ]]; then
    systemctl disable --now borg-ui-agent-upgrade.path >/dev/null 2>&1 || true
  elif [[ "${BORG_UI_UPGRADE_JOB:-}" != "1" ]]; then
    launchctl bootout "gui/$(id -u)/${UPGRADE_JOB_LABEL}" >/dev/null 2>&1 || true
  fi
  rm -f "${UPGRADE_PATH_UNIT}" "${UPGRADE_UNIT}" "${UPGRADE_HELPER}" \
    "${UPGRADE_CONF}" "${UPGRADE_TRIGGER}"
  # An install that predates the path unit granted the agent a sudoers rule.
  # Take it away rather than leaving a live escalation behind.
  if [[ "${PLATFORM}" == "Linux" ]]; then
    rm -f /etc/sudoers.d/borg-ui-agent-upgrade
  fi
}

# The watcher: a path unit on Linux, the PathState job on macOS. An unwatched
# trigger makes the helper unreachable, so do not leave the unit and helper
# behind pretending otherwise.
arm_upgrade_watcher() {
  if [[ "${PLATFORM}" == "Linux" ]]; then
    write_upgrade_unit
    write_upgrade_path_unit
  else
    write_upgrade_launch_agent
  fi
}

if [[ "${REMOTE_UPGRADE}" == "1" ]] && write_upgrade_conf; then
  write_upgrade_helper
  if arm_upgrade_watcher; then
    rm -f "${NO_REMOTE_UPGRADE_MARKER}"
    if [[ "${PLATFORM}" == "Linux" ]]; then
      rm -f /etc/sudoers.d/borg-ui-agent-upgrade
    fi
    echo "Remote upgrade is available on this endpoint."
  else
    remove_upgrade_artifacts
  fi
else
  remove_upgrade_artifacts
  if [[ "${REMOTE_UPGRADE}" == "0" ]]; then
    install -m 0644 /dev/null "${NO_REMOTE_UPGRADE_MARKER}"
    own_root "${NO_REMOTE_UPGRADE_MARKER}"
    echo "Remote upgrade declined. Update this endpoint with --reinstall."
  fi
fi

if [[ "${PLATFORM}" == "Darwin" ]]; then
  ensure_launch_agent "${AGENT_JOB_LABEL}" "${LAUNCH_AGENTS_DIR}/${AGENT_JOB_LABEL}.plist"
  if [[ "${REINSTALL}" == "1" ]]; then
    echo "Borg UI agent reinstalled and restarted."
  else
    echo "Borg UI agent installed and started."
  fi
  echo "Check status with: launchctl print gui/$(id -u)/${AGENT_JOB_LABEL}"
  echo "Log: ${LOG_DIR}/agent.log"
  exit 0
fi

/opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check \
  --user "${SERVICE_USER}" \
  --group "${SERVICE_GROUP}" \
  --exec /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml

systemctl daemon-reload
if [[ "${REINSTALL}" == "1" ]]; then
  systemctl enable borg-ui-agent
  systemctl restart borg-ui-agent
  echo "Borg UI agent reinstalled and restarted."
else
  systemctl enable --now borg-ui-agent
  echo "Borg UI agent installed and started."
fi

echo "Check status with: systemctl status borg-ui-agent"
"""

UNINSTALLER_SCRIPT = r"""#!/usr/bin/env bash
# Removes the Borg UI agent from this machine.
#
# Deliberately not `set -e`: every removal tolerates a missing target, and a
# half-removed machine is worse than a fully reported one. Failures are
# collected and printed at the end (spec section 6.5).
set -uo pipefail

# Overridable as BORG_UI_UNINSTALL_<NAME> so the test harness can point the
# whole inventory at a tmpdir. A real run has none of these set, so each takes
# its real path: the Linux layout, or on macOS the per-user layout the
# installer wrote. The prefix matters on macOS, where the script runs in the
# user's own shell with no sudo to reset the environment: an exported LOG_DIR
# there must not become a path this script removes.
PLATFORM="${BORG_UI_AGENT_PLATFORM:-$(uname -s)}"
if [[ "${PLATFORM}" == "Darwin" ]]; then
  DEFAULT_AGENT_ROOT="${HOME}/Library/Application Support/borg-ui-agent"
  DEFAULT_CONFIG_DIR="${DEFAULT_AGENT_ROOT}"
  DEFAULT_LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
  DEFAULT_SERVICE_UNIT="${DEFAULT_LAUNCH_AGENTS_DIR}/com.borg-ui.agent.plist"
  DEFAULT_UPGRADE_UNIT="${DEFAULT_LAUNCH_AGENTS_DIR}/com.borg-ui.agent-upgrade.plist"
  DEFAULT_UPGRADE_PATH_UNIT="${DEFAULT_UPGRADE_UNIT}"
  DEFAULT_UPGRADE_CONF="${DEFAULT_AGENT_ROOT}/upgrade.conf"
  DEFAULT_NO_REMOTE_UPGRADE_MARKER="${DEFAULT_AGENT_ROOT}/no-remote-upgrade"
  DEFAULT_BORG1_LINK="${DEFAULT_AGENT_ROOT}/bin/borg"
  DEFAULT_BORG2_LINK="${DEFAULT_AGENT_ROOT}/bin/borg2"
  DEFAULT_LOG_DIR="${HOME}/Library/Logs/borg-ui-agent"
else
  DEFAULT_AGENT_ROOT="/opt/borg-ui-agent"
  DEFAULT_CONFIG_DIR="/etc/borg-ui-agent"
  DEFAULT_SERVICE_UNIT="/etc/systemd/system/borg-ui-agent.service"
  DEFAULT_UPGRADE_UNIT="/etc/systemd/system/borg-ui-agent-upgrade.service"
  DEFAULT_UPGRADE_PATH_UNIT="/etc/systemd/system/borg-ui-agent-upgrade.path"
  DEFAULT_UPGRADE_CONF="/etc/borg-ui-agent-upgrade.conf"
  DEFAULT_NO_REMOTE_UPGRADE_MARKER="/etc/borg-ui-agent-no-remote-upgrade"
  DEFAULT_BORG1_LINK="/usr/local/bin/borg"
  DEFAULT_BORG2_LINK="/usr/local/bin/borg2"
  DEFAULT_LOG_DIR=""
fi
AGENT_ROOT="${BORG_UI_UNINSTALL_AGENT_ROOT:-${DEFAULT_AGENT_ROOT}}"
CONFIG_DIR="${BORG_UI_UNINSTALL_CONFIG_DIR:-${DEFAULT_CONFIG_DIR}}"
CONFIG_FILE="${BORG_UI_UNINSTALL_CONFIG_FILE:-${CONFIG_DIR}/config.toml}"
UPGRADE_TRIGGER="${BORG_UI_UNINSTALL_UPGRADE_TRIGGER:-${CONFIG_DIR}/upgrade-requested}"
SERVICE_UNIT="${BORG_UI_UNINSTALL_SERVICE_UNIT:-${DEFAULT_SERVICE_UNIT}}"
UPGRADE_UNIT="${BORG_UI_UNINSTALL_UPGRADE_UNIT:-${DEFAULT_UPGRADE_UNIT}}"
UPGRADE_PATH_UNIT="${BORG_UI_UNINSTALL_UPGRADE_PATH_UNIT:-${DEFAULT_UPGRADE_PATH_UNIT}}"
UPGRADE_CONF="${BORG_UI_UNINSTALL_UPGRADE_CONF:-${DEFAULT_UPGRADE_CONF}}"
UPGRADE_HELPER="${BORG_UI_UNINSTALL_UPGRADE_HELPER:-${AGENT_ROOT}/bin/borg-ui-agent-upgrade}"
LEGACY_SUDOERS="${BORG_UI_UNINSTALL_LEGACY_SUDOERS:-/etc/sudoers.d/borg-ui-agent-upgrade}"
NO_REMOTE_UPGRADE_MARKER="${BORG_UI_UNINSTALL_NO_REMOTE_UPGRADE_MARKER:-${DEFAULT_NO_REMOTE_UPGRADE_MARKER}}"
STATE_DIR="${BORG_UI_UNINSTALL_STATE_DIR:-/var/lib/borg-ui-agent}"
BORG1_LINK="${BORG_UI_UNINSTALL_BORG1_LINK:-${DEFAULT_BORG1_LINK}}"
BORG2_LINK="${BORG_UI_UNINSTALL_BORG2_LINK:-${DEFAULT_BORG2_LINK}}"
LOG_DIR="${BORG_UI_UNINSTALL_LOG_DIR:-${DEFAULT_LOG_DIR}}"
DEDICATED_USER="${BORG_UI_UNINSTALL_DEDICATED_USER:-borg-ui-agent}"
UNREGISTER_TIMEOUT="${BORG_UI_UNINSTALL_UNREGISTER_TIMEOUT:-5}"

KEEP_BORG="0"
KEEP_USER="0"
KEEP_CONFIG="0"

FAILURES=()

note_failure() {
  FAILURES+=("$1")
}

# Wrapped so the test harness can stub them. No logic of their own.
run_systemctl() {
  systemctl "$@" >/dev/null 2>&1
}

run_userdel() {
  userdel --remove "$1" >/dev/null 2>&1
}

run_launchctl() {
  launchctl "$@" >/dev/null 2>&1
}

is_darwin() {
  [[ "${PLATFORM:-Linux}" == "Darwin" ]]
}

usage() {
  cat <<'USAGE'
Usage:
  curl -fsSL http://SERVER:PORT/agent/uninstall.sh | sudo bash

  On macOS, as the user the agent runs as, without sudo:
  curl -fsSL http://SERVER:PORT/agent/uninstall.sh | bash

Removes the Borg UI agent from this machine: the service, the upgrade helper,
the virtualenv, the configuration, and the dedicated service user.

Your own Borg installation and your backup repositories are never touched.

Options:
  --keep-borg     Leave the Borg binaries this installer placed, and their
                  symlinks, in place
  --keep-user     Leave the dedicated borg-ui-agent user and its state
                  directory in place
  --keep-config   Leave the agent's configuration in place (config.toml,
                  agent.env and scripts.d), for a reinstall against the same
                  registration
  --help          Print this message

A Borg installed by your distribution is never removed, with or without
--keep-borg. A service user that is not the dedicated borg-ui-agent account is
never deleted, with or without --keep-user.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-borg) KEEP_BORG="1"; shift ;;
    --keep-user) KEEP_USER="1"; shift ;;
    --keep-config) KEEP_CONFIG="1"; shift ;;
    --help|-h) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Run with --help for usage." >&2
      exit 2
      ;;
  esac
done
stop_service() {
  if is_darwin; then
    run_launchctl bootout "gui/$(id -u)/com.borg-ui.agent"
    return 0
  fi
  run_systemctl disable --now borg-ui-agent
}

# Split from stop_service on purpose. remove_service_user reads User= from this
# unit to decide whether the account is ours to delete, so the unit has to
# outlive that decision. Removing it earlier does not fail loudly: it makes the
# dedicated-account removal a silent no-op on every real run.
remove_service_unit() {
  rm -f "${SERVICE_UNIT}" || note_failure "could not remove ${SERVICE_UNIT}"
}

# Spec section 6.2 says to reuse the installer's remove_upgrade_artifacts
# (app/api/agent_installer.py:1050). The installer and the uninstaller are two
# separate bash strings served to different machines, so there is no runtime to
# share: what is reused is the inventory, item for item. If the installer's
# list ever grows, this one has to grow with it, and a stale copy here leaves
# an escalation path behind on a machine that is meant to be clean.
remove_upgrade_artifacts() {
  if is_darwin; then
    run_launchctl bootout "gui/$(id -u)/com.borg-ui.agent-upgrade"
  else
    run_systemctl disable --now borg-ui-agent-upgrade.path
  fi
  rm -f "${UPGRADE_PATH_UNIT}" "${UPGRADE_UNIT}" "${UPGRADE_HELPER}" \
    "${UPGRADE_CONF}" "${UPGRADE_TRIGGER}" \
    || note_failure "could not remove the upgrade artifacts"
  # An install that predates the path unit granted the agent a sudoers rule.
  # Take it away rather than leaving a live escalation behind on a machine
  # that is supposed to have no Borg UI on it. A macOS agent never had one.
  if ! is_darwin; then
    rm -f "${LEGACY_SUDOERS}" || note_failure "could not remove ${LEGACY_SUDOERS}"
  fi
}

# SAFETY RULE 1 (spec section 6.2). A link is ours only when it resolves to a
# path under AGENT_ROOT, which is where the installer's forwarder scripts live.
# The same test _classify_install_source uses to label a binary
# "borg-ui-installer" in the UI, so the card and this script agree by
# construction. A distro Borg at /usr/bin/borg, or a link an operator pointed
# somewhere else, is left exactly as it is: removing a system-package Borg
# would break Borg for everything else on the machine.
remove_borg_links() {
  if [[ "${KEEP_BORG}" == "1" ]]; then
    echo "Leaving the Borg binaries and their symlinks in place."
    return 0
  fi

  local link resolved root
  root="$(cd "${AGENT_ROOT}" 2>/dev/null && pwd -P)" || root=""
  for link in "${BORG1_LINK}" "${BORG2_LINK}"; do
    [[ -L "${link}" ]] || continue
    resolved="$(readlink -f "${link}" 2>/dev/null || true)"
    if [[ -n "${root}" && "${resolved}" == "${root}"/* ]]; then
      rm -f "${link}" || note_failure "could not remove ${link}"
    else
      echo "Leaving ${link} alone: it does not point into ${AGENT_ROOT}."
    fi
  done
}

# SAFETY RULE 2 (spec section 6.2). The account is deleted only when the unit
# says the service ran as the dedicated account this installer creates. An
# install run with --service-user current binds the unit to the operator's own
# login account, and deleting that would take their home directory with it.
# A missing unit tells us nothing, so it deletes nothing.
remove_service_user() {
  # A macOS agent runs as the user who installed it; there is no account of ours.
  if is_darwin; then
    return 0
  fi
  if [[ "${KEEP_USER}" == "1" ]]; then
    echo "Leaving the service user and its state directory in place."
    return 0
  fi

  rm -rf "${STATE_DIR}" || note_failure "could not remove ${STATE_DIR}"

  local unit_user=""
  if [[ -r "${SERVICE_UNIT}" ]]; then
    unit_user="$(awk -F= '/^User=/ {print $2; exit}' "${SERVICE_UNIT}" 2>/dev/null || true)"
  fi

  if [[ "${unit_user}" != "${DEDICATED_USER}" ]]; then
    if [[ -n "${unit_user}" ]]; then
      echo "Leaving the '${unit_user}' account alone: only the dedicated ${DEDICATED_USER} account is removed."
    fi
    return 0
  fi

  # A swallowed failure here is the worst kind: the account survives and the
  # script still reports a clean removal. systemctl's status stays unchecked on
  # purpose, because disabling an already-absent unit is the idempotent case.
  if ! run_userdel "${DEDICATED_USER}"; then
    note_failure "could not delete the ${DEDICATED_USER} account"
  fi
}

# Removes what is under the agent root except what the options keep. On macOS
# the configuration lives there, and kept is what Linux keeps in its config
# directory: the registration, the recorded repository, and the user's own
# scripts. With --keep-borg the binaries and the forwarders that reach them
# stay: a symlink kept on PATH resolves into this directory, so keeping the
# link without them leaves a Borg that cannot start.
empty_agent_root() {
  local entry name
  for entry in "${AGENT_ROOT}"/* "${AGENT_ROOT}"/.[!.]*; do
    [[ -e "${entry}" || -L "${entry}" ]] || continue
    name="${entry##*/}"
    if [[ "${KEEP_CONFIG}" == "1" ]]; then
      case "${entry}" in
        "${CONFIG_FILE}" | "${CONFIG_DIR}/agent.env" | "${CONFIG_DIR}/scripts.d") continue ;;
      esac
    fi
    if [[ "${KEEP_BORG}" == "1" ]]; then
      case "${name}" in
        borg1 | borg2) continue ;;
        bin)
          rm -f "${UPGRADE_HELPER}" || note_failure "could not remove ${UPGRADE_HELPER}"
          continue
          ;;
      esac
    fi
    rm -rf "${entry}" || note_failure "could not remove ${entry}"
  done
  # Only what is empty goes here, so nothing that was kept is touched. An
  # install that stopped before its binary arrived leaves such a directory.
  local kept
  for kept in "${AGENT_ROOT}"/borg[12]/* "${AGENT_ROOT}/borg1" \
    "${AGENT_ROOT}/borg2" "${AGENT_ROOT}/bin" "${AGENT_ROOT}"; do
    if [[ -d "${kept}" && ! -L "${kept}" ]]; then
      rmdir "${kept}" 2>/dev/null || true
    fi
  done
}

remove_agent_files() {
  if is_darwin; then
    empty_agent_root
    if [[ "${KEEP_CONFIG}" == "1" ]]; then
      echo "Keeping ${CONFIG_FILE}."
    fi
    if [[ -n "${LOG_DIR}" ]]; then
      rm -rf "${LOG_DIR}" || note_failure "could not remove ${LOG_DIR}"
    fi
    return 0
  fi

  if [[ "${KEEP_BORG}" == "1" ]]; then
    empty_agent_root
  else
    rm -rf "${AGENT_ROOT}" || note_failure "could not remove ${AGENT_ROOT}"
  fi
  rm -f "${NO_REMOTE_UPGRADE_MARKER}" \
    || note_failure "could not remove ${NO_REMOTE_UPGRADE_MARKER}"

  if [[ "${KEEP_CONFIG}" == "1" ]]; then
    # The operator asked to keep the file, not to keep the upgrade trigger:
    # an unwatched trigger left behind is a request nothing will ever serve.
    rm -f "${UPGRADE_TRIGGER}" || note_failure "could not remove ${UPGRADE_TRIGGER}"
    echo "Keeping ${CONFIG_FILE}."
    return 0
  fi

  rm -rf "${CONFIG_DIR}" || note_failure "could not remove ${CONFIG_DIR}"
}

report() {
  # The early return is load-bearing, not just tidy: under `set -u`, bash 3.2
  # (which macOS ships, and which runs these tests locally) aborts on
  # "${FAILURES[@]}" when the array is empty. Expanding it only after the count
  # check is what keeps the happy path working there. If you restructure this,
  # check it on bash 3.2, not only on CI's bash 5.
  if [[ ${#FAILURES[@]} -eq 0 ]]; then
    echo "Borg UI agent removed."
    return 0
  fi
  echo "Borg UI agent removed, with problems:" >&2
  local failure
  for failure in "${FAILURES[@]}"; do
    echo "  - ${failure}" >&2
  done
  return 1
}

# Best effort, and deliberately so (spec section 6.4). The server marks the
# machine revoked, so the card reflects reality without the operator clicking
# Delete. A stranded agent cannot reach its server, which is a likely reason to
# be uninstalling in the first place, so a failure here reports and continues.
#
# The token is read from the config and sent only to the server_url recorded in
# that same file, never to a URL passed on the command line, so a pasted script
# cannot be steered into exfiltrating the credential. It is never echoed.
unregister() {
  if [[ ! -r "${CONFIG_FILE}" ]]; then
    echo "No readable config at ${CONFIG_FILE}; skipping the unregister call."
    return 0
  fi

  local server token
  server="$(awk -F'"' '/^server_url[[:space:]]*=/ {print $2; exit}' "${CONFIG_FILE}")"
  token="$(awk -F'"' '/^agent_token[[:space:]]*=/ {print $2; exit}' "${CONFIG_FILE}")"

  if [[ -z "${server}" || -z "${token}" ]]; then
    echo "The config carries no server URL and token; skipping the unregister call."
    return 0
  fi

  # The header goes in on stdin rather than as an argument: a command line is
  # world-readable through ps, and this one runs as root. curl's config format
  # escapes backslash and double quote inside a quoted value.
  local quoted="${token//\\/\\\\}"
  quoted="${quoted//\"/\\\"}"

  if printf 'header = "X-Borg-Agent-Authorization: Bearer %s"\n' "${quoted}" \
    | curl -fsS --max-time "${UNREGISTER_TIMEOUT}" -X POST --config - \
      "${server%/}/api/agents/unregister" >/dev/null 2>&1; then
    echo "Server notified: this endpoint is now revoked."
  else
    echo "Could not reach ${server} to unregister. Removing locally anyway."
  fi
  return 0
}

if is_darwin; then
  if [[ "$(id -u)" == "0" ]]; then
    echo "On macOS, run this as the user the agent runs as, without sudo." >&2
    exit 1
  fi
elif [[ "$(id -u)" != "0" ]]; then
  echo "This must run as root. Pipe it into 'sudo bash'." >&2
  exit 1
fi

unregister
stop_service
remove_upgrade_artifacts
remove_borg_links
remove_service_user
remove_service_unit
remove_agent_files
if ! is_darwin; then
  run_systemctl daemon-reload
fi
report
"""


def _installed_borg_version(interface_factory, label: str) -> str | None:
    """The exact Borg version this server runs, or None if it has none.

    Read from the binary rather than kept as a constant, so it cannot drift
    from what the server actually executes when a base image is bumped.
    """
    try:
        raw = interface_factory().get_version()
    except Exception as exc:  # a missing binary must not break the installer
        logger.warning(
            "Could not determine server Borg version", borg=label, error=str(exc)
        )
        return None

    match = re.search(r"\d+\.\d+(?:\.\d+)?(?:[A-Za-z]\d+)?", raw or "")
    return match.group(0) if match else None


def _agent_dist_dir() -> Path:
    return Path(os.getenv("AGENT_PACKAGE_DIR", DEFAULT_AGENT_PACKAGE_DIR))


def agent_package_path() -> Path | None:
    """The agent wheel built into this image, if present."""
    wheels = sorted(_agent_dist_dir().glob("borg_ui_agent-*.whl"))
    return wheels[-1] if wheels else None


def agent_package_version() -> str | None:
    """The version of the agent wheel this image serves, if any.

    The installer pins the version and installs `borg-ui-agent==<version>` from the
    served wheelhouse, so the node runs the agent this server was built with.
    """
    package = agent_package_path()
    if package is None:
        return None
    # Wheel filename: {name}-{version}-{python}-{abi}-{platform}.whl
    parts = package.stem.split("-")
    return parts[1] if len(parts) >= 2 else None


# A pin is interpolated into a block the endpoint executes as root, and it
# arrives from the database rather than from a filename on this server. One
# conservative shape for anything that claims to be a version: no quotes, no
# spaces, no shell metacharacters, and short enough to be a version rather
# than a payload.
_SAFE_PIN = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")


@dataclass(frozen=True)
class InstallerPins:
    """The versions the script served to one endpoint pins.

    `agent_version` of None means track the wheel this server serves.
    `desired_borg_version` of None means leave the installed Borg alone.
    """

    agent_version: Optional[str] = None
    desired_borg_version: Optional[str] = None


def installer_pins_for_agent(db: Session, agent_id: Optional[str]) -> InstallerPins:
    """One endpoint's pins, or the unpinned defaults.

    An unknown agent_id is deliberately not an error. This is the public
    install endpoint: first-time enrollment has no agent row yet, and
    answering differently for a known and an unknown id would make the route a
    probe for which agent ids exist.

    Both values are whitelisted here, at the boundary between the database and
    a root-executed script, rather than trusted from the PUT route that wrote
    them. That route validates, but a row can predate a validation rule or be
    edited by hand, and the cost of the check is a regex.
    """
    if not agent_id:
        return InstallerPins()

    agent = db.query(AgentMachine).filter(AgentMachine.agent_id == agent_id).first()
    if agent is None:
        return InstallerPins()

    agent_version = agent.desired_agent_version
    # fullmatch, not match: `$` also matches just before a trailing newline, so
    # `match` would accept "0.1.3\n" and interpolate the newline into the
    # script's PINNED_AGENT_VERSION assignment.
    if agent_version is not None and _SAFE_PIN.fullmatch(agent_version) is None:
        logger.warning(
            "agent_installer_pin_refused",
            agent_id=agent_id,
            field="desired_agent_version",
        )
        agent_version = None

    borg_version = agent.desired_borg_version
    if borg_version not in ("1", "2"):
        if borg_version:
            logger.warning(
                "agent_installer_pin_refused",
                agent_id=agent_id,
                field="desired_borg_version",
            )
        borg_version = None

    return InstallerPins(agent_version=agent_version, desired_borg_version=borg_version)


def render_installer_script(pins: Optional[InstallerPins] = None) -> str:
    """Pin the installer to the versions this server runs and this endpoint
    wants.

    Only the delimited block at the top of the script is rewritten. The rest is
    served verbatim, so the script in the repository stays the script that runs.

    `pins` default to unpinned, which is first-time enrollment and every
    request that names no agent: the served wheel and no Borg override, which
    is what this function pinned for every caller before phase 5.
    """
    pins = pins or InstallerPins()
    versions = {
        "1": _installed_borg_version(BorgInterface, "borg1"),
        "2": _installed_borg_version(Borg2Interface, "borg2"),
    }

    pinning = "\n".join(
        [
            PINNING_BEGIN,
            "# Filled in by the Borg UI instance that served this script.",
            f'PINNED_BORG1_VERSION="{versions["1"] or ""}"',
            f'PINNED_BORG2_VERSION="{versions["2"] or ""}"',
            f'PINNED_BORG_BINARIES="{binary_table(versions)}"',
            f'PINNED_PYTHON_VERSION="{CURRENT_PYTHON_RUNTIME}"',
            f'PINNED_PYTHON_RUNTIMES="{runtime_table()}"',
            f'PINNED_AGENT_VERSION="'
            f'{pins.agent_version or agent_package_version() or ""}"',
            f'PINNED_DESIRED_BORG_VERSION="{pins.desired_borg_version or ""}"',
            PINNING_END,
        ]
    )

    start = INSTALLER_SCRIPT.index(PINNING_BEGIN)
    end = INSTALLER_SCRIPT.index(PINNING_END) + len(PINNING_END)
    return INSTALLER_SCRIPT[:start] + pinning + INSTALLER_SCRIPT[end:]


@router.get("/agent/install.sh")
async def get_agent_installer(
    agent_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    # render_installer_script runs `borg --version` (a blocking subprocess) and
    # touches the filesystem, so it is offloaded to a worker thread rather than run
    # on the event loop of this public endpoint. The pins are resolved before that
    # hand-off: an InstallerPins is plain strings, so no ORM object bound to this
    # request's session is touched from the worker thread.
    pins = installer_pins_for_agent(db, agent_id)
    script = await asyncio.to_thread(render_installer_script, pins)
    return Response(content=script, media_type="text/x-shellscript")


@router.get("/agent/install.sh.sha256")
async def get_agent_installer_checksum(
    agent_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    """The SHA256 of the script this server serves at /agent/install.sh.

    The self-upgrade helper runs the downloaded script as root, so it verifies
    the download against this before executing anything. Rendered through the
    same function as the script itself, for the same endpoint, so the two agree
    for as long as the server's pinned versions and that endpoint's pins do not
    change between the helper's two requests. A server restarted into a new
    release in that window, or a pin changed in it, makes the helper refuse and
    retry later, which is the direction to fail in.
    """
    pins = installer_pins_for_agent(db, agent_id)
    script = await asyncio.to_thread(render_installer_script, pins)
    digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
    return Response(content=f"{digest}\n", media_type="text/plain")


@router.get("/agent/uninstall.sh")
async def get_agent_uninstaller() -> Response:
    """The uninstaller this server serves, identical for every caller.

    Unauthenticated, matching install.sh beside it. Acceptable because the
    script is static: it carries no credential, no pins and no per-agent data,
    and does nothing unless an operator with root on a machine chooses to run
    it there. It reveals only that a Borg UI server is present, which
    install.sh already reveals (spec section 8).

    Takes no query parameters and touches no database, so unlike the installer
    it needs neither a session nor a worker thread.
    """
    return Response(content=UNINSTALLER_SCRIPT, media_type="text/x-shellscript")


@router.get("/agent/dist/")
async def get_agent_dist_index() -> Response:
    """A find-links index of the agent wheelhouse this image serves.

    The installer runs `pip install --no-index --find-links <server>/agent/dist/`,
    so the agent and its whole dependency closure come from this one server and the
    install is air-gapped: pip reads this page, follows the wheel links, and never
    touches an index. A node installs the agent belonging to the server it enrols
    against, which matters whenever a deployment runs ahead of the default branch.
    """
    wheels = sorted(_agent_dist_dir().glob("*.whl"))
    links = "\n".join(f'    <a href="{w.name}">{w.name}</a><br>' for w in wheels)
    html = (
        "<!DOCTYPE html>\n"
        "<html><head><title>borg-ui-agent wheelhouse</title></head>\n"
        f"<body>\n{links}\n</body></html>\n"
    )
    return Response(content=html, media_type="text/html")


@router.get("/agent/dist/{filename}")
async def get_agent_wheel(filename: str) -> FileResponse:
    """Serve one wheel from the agent wheelhouse."""
    # A path parameter never spans '/', but reject anything that is not a plain
    # wheel filename sitting directly in the dist dir, so nothing outside it can be
    # reached.
    if filename != Path(filename).name or not filename.endswith(".whl"):
        raise HTTPException(status_code=404, detail="Not found")
    wheel = _agent_dist_dir() / filename
    if not wheel.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(
        wheel,
        media_type="application/octet-stream",
        filename=filename,
    )
