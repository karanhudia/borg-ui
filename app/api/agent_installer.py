from fastapi import APIRouter, Response

router = APIRouter(tags=["agent-installer"])


INSTALLER_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail

SERVER=""
TOKEN=""
AGENT_NAME=""
AGENT_REF="main"
BORG_VERSION="1"
SKIP_BORG_INSTALL="0"
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
    [--skip-borg-install]

Borg install options:
  --borg-version 1      Install/verify Borg 1 as 'borg' (default).
  --borg-version 2      Install/verify Borg 2 as 'borg2' (advanced beta).
  --borg-version both   Install/verify Borg 1 and Borg 2.
  --skip-borg-install   Do not install Borg; register with detected binaries only.
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
      shift 2
      ;;
    --skip-borg-install)
      SKIP_BORG_INSTALL="1"
      shift
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

if [[ -z "${SERVER}" || -z "${TOKEN}" || -z "${AGENT_NAME}" ]]; then
  echo "--server, --token, and --name are required." >&2
  usage >&2
  exit 2
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
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl ca-certificates

if ! getent passwd borg-ui-agent >/dev/null; then
  useradd --system --user-group --home-dir /var/lib/borg-ui-agent \
    --create-home --shell /usr/sbin/nologin borg-ui-agent
fi

install -d -m 0755 /opt/borg-ui-agent
install -d -o borg-ui-agent -g borg-ui-agent -m 0750 /etc/borg-ui-agent
install -d -o borg-ui-agent -g borg-ui-agent -m 0750 /var/lib/borg-ui-agent

verify_borg_major() {
  local binary_name="$1"
  local expected_major="$2"
  local binary_path output major

  binary_path="$(command -v "${binary_name}" 2>/dev/null || true)"
  if [[ -z "${binary_path}" ]]; then
    echo "Required Borg binary '${binary_name}' was not found." >&2
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
  "${BORG2_VENV}/bin/pip" install --pre "borgbackup>=2,<3"
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
/opt/borg-ui-agent/.venv/bin/pip install \
  "git+https://github.com/karanhudia/borg-ui.git@${AGENT_REF}"

# Register the machine with Borg UI using borg-ui-agent register.
runuser -u borg-ui-agent -- /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml \
  register \
  --server "${SERVER}" \
  --token "${TOKEN}" \
  --name "${AGENT_NAME}"

cat >/etc/systemd/system/borg-ui-agent.service <<'SERVICE'
[Unit]
Description=Borg UI managed agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=borg-ui-agent
Group=borg-ui-agent
ExecStart=/opt/borg-ui-agent/.venv/bin/borg-ui-agent --config /etc/borg-ui-agent/config.toml run
Restart=always
RestartSec=10
WorkingDirectory=/var/lib/borg-ui-agent
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=/etc/borg-ui-agent /var/lib/borg-ui-agent /tmp

[Install]
WantedBy=multi-user.target
SERVICE

/opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check \
  --user borg-ui-agent \
  --group borg-ui-agent \
  --exec /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml

systemctl daemon-reload
systemctl enable --now borg-ui-agent

echo "Borg UI agent installed and started."
echo "Check status with: systemctl status borg-ui-agent"
"""


@router.get("/agent/install.sh")
async def get_agent_installer() -> Response:
    return Response(content=INSTALLER_SCRIPT, media_type="text/x-shellscript")
