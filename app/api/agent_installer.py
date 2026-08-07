import os
import re
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from app.api.borg_binaries import binary_table
from app.core.borg import BorgInterface
from app.core.borg2 import Borg2Interface

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
# Borg versions it runs and the checksums of the matching static binaries.
PINNED_BORG1_VERSION=""
PINNED_BORG2_VERSION=""
PINNED_BORG_BINARIES=""
PINNED_AGENT_PACKAGE=""
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
SERVICE_USER=""
SERVICE_GROUP=""
SERVICE_HOME=""
SERVICE_READ_WRITE_PATHS="/etc/borg-ui-agent /tmp"
AGENT_ROOT="/opt/borg-ui-agent"
BORG_FORWARDER_DIR="${AGENT_ROOT}/bin"
BORG1_LINK="/usr/local/bin/borg"
BORG2_LINK="/usr/local/bin/borg2"

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

Borg install options:
  --borg-version 1      Install/verify Borg 1 as 'borg' (default).
  --borg-version 2      Install/verify Borg 2 as 'borg2' (advanced beta).
  --borg-version both   Install/verify Borg 1 and Borg 2.
  --skip-borg-install   Do not install Borg; register/reinstall with detected binaries only.

  --borg-source server  Install the exact Borg versions this Borg UI server runs,
                        from the static binaries published with those releases
                        (default). Agent and server then speak the same Borg.
  --borg-source distro  Use distribution packages instead. The version is then
                        whatever the distribution ships, which may differ from
                        the server's. Required on platforms with no published
                        static binary, such as 32-bit ARM.

Agent install options:
  --agent-source server Install the agent package the enrolling server offers
                        (default), so the agent matches the server it talks to.
  --agent-source git    Install from the upstream Git repository at --version.
                        Intended for development.

Service user options:
  --service-user current        Run as the user who invoked sudo (default).
  --service-user borg-ui-agent  Run as the dedicated borg-ui-agent system user.
  --service-user root           Run as root. Advanced; grants root-level Borg operations.
  --service-user USERNAME       Run as an existing local user.

Reinstall mode updates the agent package and systemd unit on an already enrolled
machine. It preserves /etc/borg-ui-agent/config.toml and does not require an
enrollment token, agent name, or registration. By default, reinstall mode skips
Borg installation; pass --borg-version to verify or update Borg binaries.
USAGE
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

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root, usually through sudo." >&2
  exit 1
fi

if [[ "${REINSTALL}" == "1" ]]; then
  if [[ ! -r /etc/borg-ui-agent/config.toml ]]; then
    echo "Reinstall mode requires an existing /etc/borg-ui-agent/config.toml." >&2
    echo "Use the Add Agent install command for first-time enrollment." >&2
    exit 2
  fi
  if [[ "${BORG_VERSION_SET}" == "0" ]]; then
    SKIP_BORG_INSTALL="1"
    echo "Skipping Borg installation by default for reinstall mode."
  fi
  # Reinstall takes no --server, but the agent package still comes from the
  # server this machine is enrolled against.
  if [[ -z "${SERVER}" ]]; then
    SERVER="$(sed -nE 's/^server_url[[:space:]]*=[[:space:]]*"(.*)"[[:space:]]*$/\1/p' \
      /etc/borg-ui-agent/config.toml | head -n 1)"
  fi
elif [[ -z "${SERVER}" || -z "${TOKEN}" || -z "${AGENT_NAME}" ]]; then
  echo "--server, --token, and --name are required." >&2
  usage >&2
  exit 2
fi

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
if [[ "${REINSTALL}" == "1" && "${SERVICE_USER_MODE_SET}" == "0" ]]; then
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

prepare_agent_config_path() {
  local config_path="/etc/borg-ui-agent/config.toml"

  if [[ "${REINSTALL}" == "1" ]]; then
    if [[ ! -f "${config_path}" || -L "${config_path}" ]]; then
      echo "Agent config '${config_path}' must be a regular file." >&2
      exit 1
    fi
    chown "${SERVICE_USER}:${SERVICE_GROUP}" /etc/borg-ui-agent/config.toml
    chmod 0600 /etc/borg-ui-agent/config.toml
    return
  fi

  rm -f /etc/borg-ui-agent/config.toml
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
# minimum glibc, so the newest build the machine satisfies is the right one.
detect_machine() {
  MACHINE_ARCH="$(uname -m)"
  case "${MACHINE_ARCH}" in
    amd64) MACHINE_ARCH="x86_64" ;;
    arm64) MACHINE_ARCH="aarch64" ;;
  esac

  MACHINE_GLIBC="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')"
  if [[ -z "${MACHINE_GLIBC}" ]]; then
    MACHINE_GLIBC="$(ldd --version 2>/dev/null | head -n 1 |
      grep -oE '[0-9]+\.[0-9]+$' || true)"
  fi
}

# True when the machine's glibc is at least $1. sort -V orders versions, and -C
# reports whether the input was already ordered.
glibc_at_least() {
  [[ -n "${MACHINE_GLIBC}" ]] || return 1
  printf '%s\n%s\n' "$1" "${MACHINE_GLIBC}" | sort -V -C
}

select_borg_binary() {
  local major="$1"
  local row_major row_arch row_glibc row_sha row_url best_glibc=""

  BINARY_URL=""
  BINARY_SHA=""

  while read -r row_major row_arch row_glibc row_sha row_url; do
    [[ -n "${row_major:-}" ]] || continue
    [[ "${row_major}" == "${major}" ]] || continue
    [[ "${row_arch}" == "${MACHINE_ARCH}" ]] || continue
    glibc_at_least "${row_glibc}" || continue

    if [[ -z "${best_glibc}" ]] ||
      printf '%s\n%s\n' "${best_glibc}" "${row_glibc}" | sort -V -C; then
      best_glibc="${row_glibc}"
      BINARY_URL="${row_url}"
      BINARY_SHA="${row_sha}"
    fi
  done <<<"${PINNED_BORG_BINARIES}"

  [[ -n "${BINARY_URL}" ]]
}

install_borg_binary() {
  local major="$1" version="$2" dest_dir dest tmp

  dest_dir="${AGENT_ROOT}/borg${major}/${version}"
  dest="${dest_dir}/borg"

  if [[ -x "${dest}" ]]; then
    echo "Borg ${version} already present at ${dest}."
  else
    install -d -o root -g root -m 0755 "${AGENT_ROOT}" \
      "${AGENT_ROOT}/borg${major}" "${dest_dir}"
    tmp="$(mktemp)"
    echo "Downloading Borg ${version} for ${MACHINE_ARCH} (glibc ${MACHINE_GLIBC})."
    curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}" "${BINARY_URL}"
    if ! printf '%s  %s\n' "${BINARY_SHA}" "${tmp}" | sha256sum -c - >/dev/null; then
      rm -f "${tmp}"
      echo "Checksum mismatch for Borg ${version}; refusing to install it." >&2
      exit 1
    fi
    install -o root -g root -m 0755 "${tmp}" "${dest}"
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
  install -d -o root -g root -m 0755 "${BORG_FORWARDER_DIR}"
  cat >"${forwarder}" <<FORWARDER
#!/usr/bin/env bash
# Installed by the Borg UI agent installer. Runs the Borg version this machine's
# Borg UI server runs, ahead of any distribution package on PATH.
exec ${target} "\$@"
FORWARDER
  chown root:root "${forwarder}"
  chmod 0755 "${forwarder}"

  # The agent finds Borg through PATH, and /usr/local/bin precedes /usr/bin, so
  # this symlink is what makes it use the pinned binary rather than the
  # distribution's. Anything else already sitting there is left alone.
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
    echo "Re-run with --borg-source distro to use the distribution package." >&2
    exit 1
  fi

  if ! select_borg_binary "${major}"; then
    echo "No published Borg ${version} binary for ${MACHINE_ARCH} with glibc ${MACHINE_GLIBC:-unknown}." >&2
    echo "Borg publishes no static binary for 32-bit ARM or musl systems." >&2
    echo "Re-run with --borg-source distro to use the distribution package," >&2
    echo "or with --skip-borg-install to manage Borg yourself." >&2
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

  if ! command -v rclone >/dev/null 2>&1; then
    apt-get install -y rclone
  fi

  if ! command -v rclone >/dev/null 2>&1; then
    echo "Warning: rclone could not be installed; rclone: repositories will not work." >&2
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
    AGENT_PACKAGE_SOURCE="git+https://github.com/karanhudia/borg-ui.git@${AGENT_REF}"
    return
  fi

  if [[ -z "${SERVER}" ]]; then
    echo "No server URL is known, so the agent package cannot be located." >&2
    echo "Pass --server, or use --agent-source git." >&2
    exit 1
  fi

  if [[ -z "${PINNED_AGENT_PACKAGE}" ]]; then
    echo "This Borg UI server offers no agent package to install." >&2
    echo "Its image predates server-provided agent packages, or was built" >&2
    echo "without one. Re-run with --agent-source git to install from the" >&2
    echo "upstream repository instead." >&2
    exit 1
  fi

  # pip needs a parseable wheel filename in the URL, so the server pins the
  # filename and the base URL comes from --server (or, on reinstall, from the
  # config of the server this machine is already enrolled against).
  AGENT_PACKAGE_SOURCE="${SERVER%/}/agent/package/${PINNED_AGENT_PACKAGE}"
}

AGENT_PACKAGE_SOURCE=""
resolve_agent_package_source

python3 -m venv "${AGENT_ROOT}/.venv"
"${AGENT_ROOT}/.venv/bin/pip" install --upgrade --force-reinstall \
  "${AGENT_PACKAGE_SOURCE}"

if [[ "${REINSTALL}" == "1" ]]; then
  echo "Preserving existing agent registration at /etc/borg-ui-agent/config.toml."
else
  # Register the machine with Borg UI using borg-ui-agent register.
  runuser -u "${SERVICE_USER}" -- /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
    --config /etc/borg-ui-agent/config.toml \
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

[Install]
WantedBy=multi-user.target
SERVICE

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


def agent_package_path() -> Path | None:
    """The agent wheel built into this image, if present."""
    package_dir = Path(os.getenv("AGENT_PACKAGE_DIR", DEFAULT_AGENT_PACKAGE_DIR))
    wheels = sorted(package_dir.glob("*.whl"))
    return wheels[-1] if wheels else None


def render_installer_script() -> str:
    """Pin the installer to the versions this server runs.

    Only the delimited block at the top of the script is rewritten. The rest is
    served verbatim, so the script in the repository stays the script that runs.
    """
    versions = {
        "1": _installed_borg_version(BorgInterface, "borg1"),
        "2": _installed_borg_version(Borg2Interface, "borg2"),
    }
    package = agent_package_path()

    pinning = "\n".join(
        [
            PINNING_BEGIN,
            "# Filled in by the Borg UI instance that served this script.",
            f'PINNED_BORG1_VERSION="{versions["1"] or ""}"',
            f'PINNED_BORG2_VERSION="{versions["2"] or ""}"',
            f'PINNED_BORG_BINARIES="{binary_table(versions)}"',
            f'PINNED_AGENT_PACKAGE="{package.name if package else ""}"',
            PINNING_END,
        ]
    )

    start = INSTALLER_SCRIPT.index(PINNING_BEGIN)
    end = INSTALLER_SCRIPT.index(PINNING_END) + len(PINNING_END)
    return INSTALLER_SCRIPT[:start] + pinning + INSTALLER_SCRIPT[end:]


@router.get("/agent/install.sh")
async def get_agent_installer() -> Response:
    return Response(content=render_installer_script(), media_type="text/x-shellscript")


@router.get("/agent/package/{filename}")
async def get_agent_package(filename: str) -> FileResponse:
    """Serve the agent package built into this image.

    A node installs the agent belonging to the server it enrolls against, which
    matters whenever a deployment runs ahead of the upstream default branch.
    """
    package = agent_package_path()
    if package is None or filename != package.name:
        raise HTTPException(status_code=404, detail="Agent package not available")

    return FileResponse(
        package,
        media_type="application/octet-stream",
        filename=package.name,
    )
