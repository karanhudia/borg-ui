from fastapi import APIRouter, Response

router = APIRouter(tags=["agent-installer"])


INSTALLER_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail

SERVER=""
TOKEN=""
AGENT_NAME=""
REINSTALL="0"
AGENT_REF="main"
BORG_VERSION="1"
BORG_VERSION_SET="0"
SKIP_BORG_INSTALL="0"
SERVICE_USER_MODE="current"
SERVICE_USER=""
SERVICE_GROUP=""
SERVICE_HOME=""
SERVICE_READ_WRITE_PATHS="/etc/borg-ui-agent /tmp"
BORG2_VENV="/opt/borg-ui-agent/borg2-venv"
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
    --service-user)
      if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "--service-user requires one of: current, borg-ui-agent, root, or an existing username." >&2
        exit 2
      fi
      SERVICE_USER_MODE="$2"
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
apt-get install -y python3 python3-venv python3-pip git curl ca-certificates

install -d -m 0755 /opt/borg-ui-agent
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 /etc/borg-ui-agent
if [[ "${SERVICE_USER_MODE}" == "borg-ui-agent" ]]; then
  install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 /var/lib/borg-ui-agent
fi

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

install_borg1() {
  if command -v borg >/dev/null 2>&1; then
    echo "Existing borg detected; verifying without replacing it."
    verify_borg_major "borg" "1"
    return
  fi

  apt-get install -y borgbackup
  verify_borg_major "borg" "1"
}

install_borg2() {
  if command -v borg2 >/dev/null 2>&1; then
    echo "Existing borg2 detected; verifying without replacing it."
    verify_borg_major "borg2" "2"
    return
  fi

  if [[ -e "${BORG2_LINK}" || -L "${BORG2_LINK}" ]]; then
    echo "${BORG2_LINK} exists but is not available as borg2 on PATH; refusing to replace it." >&2
    exit 1
  fi

  if [[ -x "${BORG2_VENV}/bin/borg" ]]; then
    echo "Existing Borg 2 virtualenv detected; linking without reinstalling."
    verify_borg_path "${BORG2_VENV}/bin/borg" "borg2" "2"
    ln -s "${BORG2_VENV}/bin/borg" "${BORG2_LINK}"
    verify_borg_major "borg2" "2"
    return
  fi

  apt-get install -y \
    build-essential \
    libacl1-dev \
    liblz4-dev \
    libssl-dev \
    libxxhash-dev \
    libzstd-dev \
    pkg-config \
    python3-dev

  python3 -m venv "${BORG2_VENV}"
  "${BORG2_VENV}/bin/python" -m pip install --upgrade pip wheel
  "${BORG2_VENV}/bin/pip" install --pre "borgbackup>=2.0.0b1,<3"
  ln -s "${BORG2_VENV}/bin/borg" "${BORG2_LINK}"
  verify_borg_major "borg2" "2"
}

if [[ "${SKIP_BORG_INSTALL}" == "1" ]]; then
  echo "Skipping Borg installation by request."
else
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

python3 -m venv /opt/borg-ui-agent/.venv
/opt/borg-ui-agent/.venv/bin/python -m pip install --upgrade pip wheel
/opt/borg-ui-agent/.venv/bin/pip install --upgrade --force-reinstall \
  "git+https://github.com/karanhudia/borg-ui.git@${AGENT_REF}"

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


@router.get("/agent/install.sh")
async def get_agent_installer() -> Response:
    return Response(content=INSTALLER_SCRIPT, media_type="text/x-shellscript")
