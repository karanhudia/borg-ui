#!/usr/bin/env bash
#
# Runs scripts/install.sh against a throwaway Debian container with systemd as
# PID 1, across the state transitions that plain reading keeps missing: a second
# run, a run with different flags, and a run over an interrupted one.
#
#   ./scripts/test-native-install.sh              # full matrix
#   ./scripts/test-native-install.sh --keep       # leave the container running
#   ./scripts/test-native-install.sh --case upgrade
#
# Needs Docker with a Linux daemon. The container is privileged because systemd
# needs it; it is a disposable test container and nothing else runs in it.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

IMAGE="debian:13"
NAME="borg-ui-install-test"
KEEP="false"
ONLY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep) KEEP="true"; shift ;;
    --case) ONLY="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

PASSED=0
FAILED=0
FAILURES=()

cleanup() {
  if [[ "${KEEP}" == "true" ]]; then
    echo "Container ${NAME} left running. Shell into it with:"
    echo "  docker exec -it ${NAME} bash"
    return
  fi
  docker rm -f "${NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

c() { docker exec "${NAME}" bash -c "$1"; }
c_quiet() { docker exec "${NAME}" bash -c "$1" >/dev/null 2>&1; }

check() {
  local what="$1" cmd="$2"
  if c_quiet "${cmd}"; then
    echo "    ok: ${what}"
    PASSED=$((PASSED + 1))
  else
    echo "    FAIL: ${what}"
    FAILED=$((FAILED + 1))
    FAILURES+=("${what}")
  fi
}

run_case() {
  [[ -z "${ONLY}" ]] || [[ "${ONLY}" == "$1" ]]
}

# --- build the artifact the installer consumes -----------------------------

# Deliberately does not build. `npm ci` wipes frontend/node_modules, and a
# worktree may have that symlinked into another checkout, so an implicit build
# here can destroy a working tree somewhere else. Build it yourself, once.
if ! compgen -G 'dist/borg-ui-*.tar.gz' >/dev/null; then
  echo "No tarball in dist/. Build one first:" >&2
  echo "  fnm exec --using=22 -- ./scripts/build-native-tarball.sh dist" >&2
  exit 1
fi
TARBALL="$(ls -t dist/borg-ui-*.tar.gz | head -n 1)"

# The installer installs the unit, start.sh and the app from the tarball, not
# from this working tree. Editing a source file and re-running the harness
# therefore tests the previous build, which makes a correct fix look broken.
newer="$(find app packaging scripts/install.sh requirements.txt VERSION frontend/src \
  -newer "${TARBALL}" -type f -print -quit 2>/dev/null || true)"
if [[ -n "${newer}" ]]; then
  echo "error: ${TARBALL} is older than ${newer}" >&2
  echo "The harness installs from the tarball, so this would test stale code. Rebuild:" >&2
  echo "  fnm exec --using=22 -- ./scripts/build-native-tarball.sh dist" >&2
  exit 1
fi

echo "==> Using ${TARBALL}"

# --- boot a systemd container ----------------------------------------------

# The stock Debian image has no /sbin/init, so it cannot be started with
# systemd as PID 1 until systemd-sysv is in it. Bake that into a base image
# once rather than trying to install it into a container that cannot boot;
# Docker caches the layer, so repeat runs skip this.
BASE_IMAGE="borg-ui-install-test-base:${IMAGE//[:\/]/-}"
echo "==> Preparing ${BASE_IMAGE}"
docker build -q -t "${BASE_IMAGE}" - >/dev/null <<DOCKERFILE
FROM ${IMAGE}
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends systemd systemd-sysv curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
DOCKERFILE

echo "==> Starting ${IMAGE} with systemd as PID 1"
docker rm -f "${NAME}" >/dev/null 2>&1 || true
docker run -d --name "${NAME}" --privileged \
  --tmpfs /run --tmpfs /run/lock \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw --cgroupns=host \
  "${BASE_IMAGE}" >/dev/null

booted="false"
for _ in $(seq 1 60); do
  state="$(docker exec "${NAME}" systemctl is-system-running 2>/dev/null || true)"
  case "${state}" in
    running|degraded) booted="true"; break ;;
  esac
  sleep 1
done
[[ "${booted}" == "true" ]] || {
  echo "systemd never came up in the container:" >&2
  docker logs "${NAME}" 2>&1 | tail -20 >&2
  exit 1
}

# Staged in /root, not /tmp: systemd mounts a tmpfs over /tmp while it
# boots, which hides anything copied there first.
docker cp "${TARBALL}" "${NAME}:/root/release.tar.gz"
docker cp scripts/install.sh "${NAME}:/root/install.sh"

install_run() {
  echo "  \$ install.sh $*"
  if docker exec "${NAME}" bash /root/install.sh --tarball /root/release.tar.gz "$@"; then
    return 0
  fi
  echo "  --- journalctl -u borg-ui -n 60 ---"
  docker exec "${NAME}" journalctl -u borg-ui -n 60 --no-pager 2>&1 | sed 's/^/  /' || true
  return 1
}

# --- the matrix -------------------------------------------------------------

if run_case fresh; then
  echo "==> Case: fresh install"
  install_run
  check "service is active" "systemctl is-active --quiet borg-ui"
  check "app answers on 8081" "curl -fsS -o /dev/null http://127.0.0.1:8081/"
  check "database created" "test -f /var/lib/borg-ui/borg.db"
  check "borg resolves to the pinned binary" "readlink -f \$(command -v borg) | grep -q '^/opt/borg-ui/'"
  check "unit puts the prefix first on PATH" "grep -q 'Environment=PATH=/opt/borg-ui/bin:' /etc/systemd/system/borg-ui.service"
fi

if run_case rerun; then
  echo "==> Case: plain re-run is idempotent"
  install_run
  check "service still active" "systemctl is-active --quiet borg-ui"
  check "app still answers" "curl -fsS -o /dev/null http://127.0.0.1:8081/"
  check "database not recreated" "test -f /var/lib/borg-ui/borg.db"
  check "one release kept plus the previous" "test \$(ls /opt/borg-ui/releases | wc -l) -le 2"
fi

if run_case flags; then
  echo "==> Case: a re-run must not override the installed data dir or port"
  install_run --data-dir /srv/elsewhere --port 9999
  check "data dir unchanged" "grep -q '^DATA_DIR=/var/lib/borg-ui\$' /etc/borg-ui/borg-ui.env"
  check "port unchanged" "grep -q '^PORT=8081\$' /etc/borg-ui/borg-ui.env"
  check "no stray directory created" "! test -d /srv/elsewhere"
  check "app still on the original port" "curl -fsS -o /dev/null http://127.0.0.1:8081/"
fi

if run_case nostart; then
  echo "==> Case: --no-start must not take a running service down"
  install_run --no-start
  check "service left running" "systemctl is-active --quiet borg-ui"
  check "app still answers" "curl -fsS -o /dev/null http://127.0.0.1:8081/"
fi

if run_case skipborg2; then
  echo "==> Case: --skip-borg2 removes a borg2 it can no longer provide"
  c_quiet "install -d /opt/borg-ui/bin && printf '#!/bin/sh\\nexit 0\\n' > /opt/borg-ui/bin/borg2 && chmod +x /opt/borg-ui/bin/borg2 && ln -sfn /opt/borg-ui/bin/borg2 /usr/local/bin/borg2"
  install_run --skip-borg2
  check "stale borg2 forwarder removed" "! test -e /opt/borg-ui/bin/borg2"
  check "stale borg2 link removed" "! test -e /usr/local/bin/borg2"
fi

if run_case partial; then
  echo "==> Case: a half-built virtualenv is rebuilt, not trusted"
  c_quiet "rm -f /opt/borg-ui/releases/*/venv/.install-complete"
  install_run
  check "marker written again" "ls /opt/borg-ui/releases/*/venv/.install-complete >/dev/null"
  check "app answers after the rebuild" "curl -fsS -o /dev/null http://127.0.0.1:8081/"
fi

if run_case serviceuser; then
  echo "==> Case: changing the service user re-owns the existing data"
  install_run --service-user borgui
  check "unit runs as the new user" "grep -q '^User=borgui\$' /etc/systemd/system/borg-ui.service"
  check "database re-owned" "test \"\$(stat -c %U /var/lib/borg-ui/borg.db)\" = borgui"
  check "secret key re-owned" "test \"\$(stat -c %U /var/lib/borg-ui/.secret_key)\" = borgui"
  check "service came up as the new user" "systemctl is-active --quiet borg-ui"
  check "app answers as the new user" "curl -fsS -o /dev/null http://127.0.0.1:8081/"
fi

# --- report -----------------------------------------------------------------

echo
echo "==> ${PASSED} passed, ${FAILED} failed"
if ((FAILED > 0)); then
  printf '    %s\n' "${FAILURES[@]}"
  echo
  echo "Logs:  docker exec ${NAME} journalctl -u borg-ui -n 50 --no-pager"
  exit 1
fi
