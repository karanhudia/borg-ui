from fastapi import APIRouter, Response

router = APIRouter(tags=["agent-installer"])


INSTALLER_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail

SERVER=""
TOKEN=""
AGENT_NAME=""
VERSION="main"

usage() {
  cat <<'USAGE'
Usage:
  curl -fsSL http://SERVER:PORT/agent/install.sh | sudo bash -s -- \
    --server http://SERVER:PORT \
    --token TOKEN \
    --name AGENT_NAME \
    [--version main]
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
      VERSION="${2:-main}"
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
OS_FAMILY="${ID:-} ${ID_LIKE:-}"
if [[ "${OS_FAMILY}" != *debian* && "${OS_FAMILY}" != *ubuntu* && "${OS_FAMILY}" != *raspbian* ]]; then
  echo "This installer currently supports Debian, Ubuntu, and Raspberry Pi OS." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl borgbackup

if ! getent passwd borg-ui-agent >/dev/null; then
  useradd --system --user-group --home-dir /var/lib/borg-ui-agent \
    --create-home --shell /usr/sbin/nologin borg-ui-agent
fi

install -d -m 0755 /opt/borg-ui-agent
install -d -o borg-ui-agent -g borg-ui-agent -m 0750 /etc/borg-ui-agent
install -d -o borg-ui-agent -g borg-ui-agent -m 0750 /var/lib/borg-ui-agent

python3 -m venv /opt/borg-ui-agent/.venv
/opt/borg-ui-agent/.venv/bin/python -m pip install --upgrade pip wheel
/opt/borg-ui-agent/.venv/bin/pip install \
  "git+https://github.com/karanhudia/borg-ui.git@${VERSION}"

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
