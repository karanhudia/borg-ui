#!/usr/bin/env bash
#
# Borg UI native installer for Debian and Ubuntu hosts.
#
# Installs Borg UI straight onto a Linux host with no container layer: bare
# metal, a KVM/Proxmox VM, or an LXC container are all the same thing from
# here. Docker stays the recommended path; this exists for the hosts that do
# not run Docker.
#
#   curl -fsSLO https://github.com/karanhudia/borg-ui/releases/latest/download/install.sh
#   curl -fsSL https://github.com/karanhudia/borg-ui/releases/latest/download/install.sh.sha256 | sha256sum -c -
#   sudo bash install.sh
#
# The installer is published as an asset of each release with its checksum
# beside it, so that names a fixed artifact and verifies it before it runs as
# root. Piping a branch download straight into a root shell is not the
# documented path.
#
# Re-running the script upgrades an existing install in place: the release is
# unpacked beside the current one and the "current" symlink is moved, so the
# data directory, database and SSH keys are never touched.
set -euo pipefail

REPO="${BORG_UI_REPO:-karanhudia/borg-ui}"
PREFIX="/opt/borg-ui"
DATA_DIR="/var/lib/borg-ui"
CONFIG_DIR="/etc/borg-ui"
ENV_FILE="${CONFIG_DIR}/borg-ui.env"
UNIT_FILE="/etc/systemd/system/borg-ui.service"
SERVICE_USER="root"
PORT="8081"
VERSION=""
START_SERVICE="true"
SKIP_BORG2="false"
DATA_DIR_EXPLICIT="false"
PREVIOUS_RELEASE=""
PORT_EXPLICIT="false"
SERVICE_USER_EXPLICIT="false"

usage() {
  cat <<'USAGE'
Usage: install.sh [options]

  --version <v>        Release to install (default: the latest GitHub release)
  --port <n>           Port to serve on (default: 8081, ignored on upgrades)
  --data-dir <path>    Data directory (default: /var/lib/borg-ui, ignored on upgrades)
  --service-user <u>   User the service runs as (default: root; see below)
  --skip-borg2         Do not install Borg 2, even where it is supported
  --no-start           Install and enable the service but do not start it
  -h, --help           Show this help

The service runs as root by default because a host backup tool has to read
files it does not own -- /etc, other users' home directories, database
directories. Pass --service-user borg for a restricted install; that user
will only be able to back up what it can read.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --port) PORT="$2"; PORT_EXPLICIT="true"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; DATA_DIR_EXPLICIT="true"; shift 2 ;;
    --service-user) SERVICE_USER="$2"; SERVICE_USER_EXPLICIT="true"; shift 2 ;;
    --skip-borg2) SKIP_BORG2="true"; shift ;;
    --no-start) START_SERVICE="false"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log() { echo "==> $*"; }
warn() { echo "warning: $*" >&2; }
die() { echo "error: $*" >&2; exit 1; }

# --- preflight -------------------------------------------------------------

preflight() {
  [[ "$(id -u)" -eq 0 ]] || die "run this installer as root (sudo bash install.sh)"

  command -v apt-get >/dev/null 2>&1 ||
    die "this installer supports Debian and Ubuntu only; see docs/installation.md for the manual steps"

  command -v systemctl >/dev/null 2>&1 ||
    die "systemd is required; this host has no systemctl"

  # An LXC container without systemd as PID 1 (or a chroot) accepts systemctl
  # but cannot run units. Saying so now beats a confusing failure at enable time.
  systemctl is-system-running --quiet 2>/dev/null ||
    [[ -d /run/systemd/system ]] ||
    die "systemd is not running as PID 1 here; Borg UI needs a system container or VM, not a chroot"

  case "$(uname -m)" in
    x86_64) MACHINE_ARCH="x86_64" ;;
    aarch64|arm64) MACHINE_ARCH="aarch64" ;;
    *) die "unsupported architecture $(uname -m); Borg publishes no static binary for it" ;;
  esac

  MACHINE_GLIBC="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')"
  if [[ -z "${MACHINE_GLIBC}" ]]; then
    MACHINE_GLIBC="$(ldd --version 2>/dev/null | head -n 1 | grep -oE '[0-9]+\.[0-9]+$' || true)"
  fi
  [[ -n "${MACHINE_GLIBC}" ]] || die "could not determine this host's glibc version"
}

# True when version $1 is less than or equal to version $2.
version_le() { printf '%s\n%s\n' "$1" "$2" | sort -V -C; }

# --- packages --------------------------------------------------------------

APT_PACKAGES=(
  ca-certificates curl unzip
  python3 python3-venv python3-dev
  # Shared libraries Borg links against, and the FUSE stack that mounting
  # archives needs. Mirrors the runtime base image's package list.
  libacl1 liblz4-1 libzstd1 libxxhash0 libfuse3-3 fuse3
  openssh-client sshfs sshpass rsync
)

install_packages() {
  log "Installing system packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq

  # libfuse3-3 was renamed libfuse3-4 in Debian trixie; ask for whichever the
  # release actually has rather than pinning one and failing on the other.
  if ! apt-cache show libfuse3-3 >/dev/null 2>&1; then
    APT_PACKAGES=("${APT_PACKAGES[@]/libfuse3-3/libfuse3-4}")
  fi

  apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"

  # Borg's FUSE mounts are served by the app and browsed by other processes.
  if [[ -f /etc/fuse.conf ]]; then
    sed -i 's/^#user_allow_other/user_allow_other/' /etc/fuse.conf
  fi
}

# --- release download ------------------------------------------------------

resolve_version() {
  if [[ -n "${VERSION}" ]]; then
    VERSION="${VERSION#v}"
    return
  fi

  log "Resolving the latest release"
  local tag
  tag="$(curl -fsSL --proto '=https' --tlsv1.2 \
    "https://api.github.com/repos/${REPO}/releases/latest" |
    grep -m1 '"tag_name"' | cut -d'"' -f4 || true)"
  [[ -n "${tag}" ]] || die "could not resolve the latest release; pass --version explicitly"
  VERSION="${tag#v}"
}

download_release() {
  local base tarball sha url
  base="https://github.com/${REPO}/releases/download/v${VERSION}"
  tarball="borg-ui-${VERSION}.tar.gz"

  RELEASE_DIR="${PREFIX}/releases/${VERSION}"
  if [[ -d "${RELEASE_DIR}" ]]; then
    log "Release ${VERSION} is already unpacked at ${RELEASE_DIR}"
    return
  fi

  # Staged on the same filesystem as the destination, so the rename below is a
  # real rename. From /tmp it would be a copy-and-delete, and an interruption
  # mid-copy would leave a partial RELEASE_DIR that the next run takes for a
  # finished release.
  local tmp
  install -d -m 0755 "${PREFIX}/releases"
  tmp="$(mktemp -d "${PREFIX}/releases/.staging.XXXXXX")"
  trap 'rm -rf "${tmp}"' RETURN

  log "Downloading Borg UI ${VERSION}"
  url="${base}/${tarball}"
  curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}/${tarball}" "${url}" ||
    die "could not download ${url}; check that release v${VERSION} publishes a native tarball"
  curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}/${tarball}.sha256" "${url}.sha256" ||
    die "could not download the checksum for ${tarball}; refusing to install unverified code"

  sha="$(cut -d' ' -f1 <"${tmp}/${tarball}.sha256")"
  printf '%s  %s\n' "${sha}" "${tmp}/${tarball}" | sha256sum -c - >/dev/null ||
    die "checksum mismatch for ${tarball}; refusing to install it"

  # Unpacked under the temporary directory and renamed into place, so
  # RELEASE_DIR only ever exists complete. Extracting straight into it would
  # leave a truncated tree behind on an interrupted run, and the next run would
  # take that for an already-unpacked release.
  mkdir -p "${tmp}/unpack"
  tar -xzf "${tmp}/${tarball}" -C "${tmp}/unpack" --strip-components=1
  mv "${tmp}/unpack" "${RELEASE_DIR}"
}

# --- host layout -----------------------------------------------------------

# An upgrade must act on the paths the running install uses, not on this
# script's defaults. Without this a re-run of a `--data-dir /srv/borg-ui`
# install would provision and chown /var/lib/borg-ui, leave the real data
# directory's permissions unfixed, and print the wrong URL.
load_persisted_settings() {
  [[ -f "${ENV_FILE}" ]] || return 0

  local key persisted explicit
  for key in DATA_DIR PORT; do
    # systemd lets a later assignment win and strips one layer of matching
    # quotes, so read it the same way: last match, unquoted. Anything fancier
    # than that (escapes, line continuations) is rejected rather than guessed
    # at, because acting on a misparsed DATA_DIR would chown the wrong tree.
    persisted="$(grep "^${key}=" "${ENV_FILE}" | tail -n 1 | cut -d= -f2- || true)"
    [[ -n "${persisted}" ]] || continue
    case "${persisted}" in
      \"*\") persisted="${persisted#\"}"; persisted="${persisted%\"}" ;;
      \'*\') persisted="${persisted#\'}"; persisted="${persisted%\'}" ;;
    esac
    if [[ "${persisted}" == *\\* ]]; then
      die "${ENV_FILE} sets ${key} with escapes this installer will not guess at; simplify it and re-run"
    fi

    explicit="${key}_EXPLICIT"
    if [[ "${!explicit}" == "true" ]] && [[ "${!key}" != "${persisted}" ]]; then
      warn "${ENV_FILE} already says ${key}=${persisted}; keeping that."
      warn "To change it, edit that file and run: systemctl restart borg-ui"
    fi
    printf -v "${key}" '%s' "${persisted}"
  done

  # The service user lives in the unit, not the env file. Resetting it on a
  # re-run would rewrite the unit with User=root and hand the data directory
  # to root, quietly undoing a deliberate --service-user install.
  persisted="$(grep -m1 '^User=' "${UNIT_FILE}" 2>/dev/null | cut -d= -f2- || true)"
  if [[ -n "${persisted}" ]]; then
    if [[ "${SERVICE_USER_EXPLICIT}" == "true" ]] && [[ "${SERVICE_USER}" != "${persisted}" ]]; then
      log "Changing the service user from ${persisted} to ${SERVICE_USER}"
    else
      SERVICE_USER="${persisted}"
    fi
  fi
}

create_service_user() {
  [[ "${SERVICE_USER}" != "root" ]] || return 0

  if ! getent passwd "${SERVICE_USER}" >/dev/null; then
    log "Creating service user ${SERVICE_USER}"
    groupadd -f "${SERVICE_USER}"
    useradd -r -g "${SERVICE_USER}" -d "${DATA_DIR}/home" -s /usr/sbin/nologin "${SERVICE_USER}"
  fi

  # Mounting and browsing Borg archives over FUSE needs the fuse group where
  # the distribution still gates /dev/fuse on it.
  groupadd -f fuse
  usermod -a -G fuse "${SERVICE_USER}"
}

create_directories() {
  local group
  group="$(id -gn "${SERVICE_USER}")"

  log "Creating directories under ${DATA_DIR}"
  install -d -m 0755 "${CONFIG_DIR}"
  install -d -m 0750 -o "${SERVICE_USER}" -g "${group}" \
    "${DATA_DIR}" "${DATA_DIR}/logs" "${DATA_DIR}/config" \
    "${DATA_DIR}/backups" "${DATA_DIR}/home" "${DATA_DIR}/cache"
  install -d -m 0700 -o "${SERVICE_USER}" -g "${group}" \
    "${DATA_DIR}/ssh_keys" "${DATA_DIR}/borg_keys" "${DATA_DIR}/cache/borg"

  # Borg writes keyfiles to $HOME/.config/borg/keys. Point that at the data
  # directory so a repository key survives an upgrade, the same way the Docker
  # entrypoint symlinks it onto the mounted volume.
  install -d -m 0700 -o "${SERVICE_USER}" -g "${group}" "${DATA_DIR}/home/.config/borg"
  if [[ ! -L "${DATA_DIR}/home/.config/borg/keys" ]]; then
    rm -rf "${DATA_DIR}/home/.config/borg/keys"
    ln -sfn "${DATA_DIR}/borg_keys" "${DATA_DIR}/home/.config/borg/keys"
  fi
  chown -h "${SERVICE_USER}:${group}" "${DATA_DIR}/home/.config/borg/keys"
}

# --- Borg ------------------------------------------------------------------

# Reads the pinned binary table the server itself serves to agents, so a native
# host runs exactly the Borg the Docker image runs. Prints "<sha> <url>" for the
# newest binary this machine's glibc can run, or nothing when there is none.
select_borg_binary() {
  local major="$1"
  python3 - "$major" "${MACHINE_ARCH}" "${MACHINE_GLIBC}" \
    "${RELEASE_DIR}/app/api/borg_binaries.json" <<'PY'
import json, sys
from pathlib import Path

major, arch, glibc, manifest_path = sys.argv[1:5]
manifest = json.loads(Path(manifest_path).read_text())
version = manifest["current"].get(major)
if not version:
    sys.exit(0)


def parts(value):
    return tuple(int(piece) for piece in value.split("."))


best = None
for row in manifest["binaries"].get(version, []):
    if row["arch"] != arch or parts(row["min_glibc"]) > parts(glibc):
        continue
    if best is None or parts(row["min_glibc"]) > parts(best["min_glibc"]):
        best = row

if best is None:
    sys.exit(0)

url = manifest["release_url"].format(version=version, asset=best["asset"])
print(f"{best['sha256']} {url} {version}")
PY
}

# A forwarder rather than a bare symlink: it is the one place that can later
# carry policy without touching callers. Matches what the agent installer does.
write_forwarder() {
  local name="$1" target="$2" link="/usr/local/bin/$1"

  install -d -m 0755 "${PREFIX}/bin"
  cat >"${PREFIX}/bin/${name}" <<FORWARDER
#!/usr/bin/env bash
# Installed by the Borg UI native installer.
exec ${target} "\$@"
FORWARDER
  chmod 0755 "${PREFIX}/bin/${name}"

  if [[ -L "${link}" ]] || [[ ! -e "${link}" ]]; then
    ln -sfn "${PREFIX}/bin/${name}" "${link}"
  else
    warn "${link} exists and is not a symlink; leaving it alone"
    warn "The service still uses ${PREFIX}/bin/${name}, which its unit puts"
    warn "first on PATH; your shell keeps resolving ${name} to ${link}"
  fi
}

install_borg_binary() {
  local major="$1" row sha url version dest tmp

  row="$(select_borg_binary "${major}")" || row=""
  [[ -n "${row}" ]] || return 1

  read -r sha url version <<<"${row}"
  dest="${PREFIX}/borg/${version}/borg"

  if [[ ! -x "${dest}" ]]; then
    log "Installing Borg ${version} for ${MACHINE_ARCH}"
    install -d -m 0755 "${PREFIX}/borg" "${PREFIX}/borg/${version}"
    tmp="$(mktemp)"
    curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}" "${url}"
    if ! printf '%s  %s\n' "${sha}" "${tmp}" | sha256sum -c - >/dev/null; then
      rm -f "${tmp}"
      die "checksum mismatch for Borg ${version}; refusing to install it"
    fi
    install -m 0755 "${tmp}" "${dest}"
    rm -f "${tmp}"
  fi

  BORG_BINARY="${dest}"
}

install_borg1() {
  if install_borg_binary 1; then
    # Borg UI resolves Borg 1 as plain "borg" on PATH.
    write_forwarder borg "${BORG_BINARY}"
    return
  fi

  warn "no pinned Borg 1 binary matches ${MACHINE_ARCH}/glibc ${MACHINE_GLIBC}; using the distribution package"
  apt-get install -y --no-install-recommends borgbackup
}

# Borg 2 has no stable release and no distribution package. Prefer the pinned
# static binary; where this machine's glibc is too old for it, build it into
# its own virtualenv, which needs a compiler and OpenSSL 3.2 or newer (2.0.0b24
# takes argon2 from OpenSSL). Where neither is possible the install continues
# without Borg 2: Borg 1 repositories are unaffected.
install_borg2() {
  if [[ "${SKIP_BORG2}" == "true" ]]; then
    log "Skipping Borg 2 (--skip-borg2)"
    return
  fi

  if install_borg_binary 2; then
    write_forwarder borg2 "${BORG_BINARY}"
    return
  fi

  local openssl_version
  openssl_version="$(openssl version 2>/dev/null | awk '{print $2}' | grep -oE '^[0-9]+\.[0-9]+\.[0-9]+' || true)"
  if [[ -z "${openssl_version}" ]] || ! version_le "3.2.0" "${openssl_version}"; then
    warn "Borg 2 needs OpenSSL 3.2 or newer to build; this host has ${openssl_version:-none}."
    warn "Borg 2 repositories will be unavailable. Borg 1 repositories work normally."
    warn "Debian 13 (trixie) and Ubuntu 25.04 or newer carry a new enough OpenSSL."
    return
  fi

  log "Building Borg ${BORG2_VERSION} (no static binary matches glibc ${MACHINE_GLIBC})"
  apt-get install -y --no-install-recommends \
    build-essential pkg-config libssl-dev libacl1-dev liblz4-dev \
    libzstd-dev libxxhash-dev libfuse3-dev

  python3 -m venv "${PREFIX}/borg2-venv"
  "${PREFIX}/borg2-venv/bin/pip" install --quiet --upgrade pip setuptools wheel
  "${PREFIX}/borg2-venv/bin/pip" install --quiet --pre \
    "borgbackup==${BORG2_VERSION}" \
    "borgstore[rclone,sftp,rest,s3,blake3]==${BORGSTORE_VERSION}" ||
    { warn "Borg 2 failed to build; Borg 2 repositories will be unavailable"; return; }

  write_forwarder borg2 "${PREFIX}/borg2-venv/bin/borg"
}

# Borg 2 reaches rclone remotes by driving an rclone process. The distribution
# package lags years behind and breaks OneDrive sync, so this takes the same
# official static binary the runtime base image does, pinned and checksummed.
install_rclone() {
  local arch zip url tmp sha

  if [[ -x "${PREFIX}/bin/rclone" ]] &&
    "${PREFIX}/bin/rclone" version 2>/dev/null | grep -qF "v${RCLONE_VERSION}"; then
    return
  fi

  case "${MACHINE_ARCH}" in
    x86_64) arch="amd64"; sha="${RCLONE_SHA256_AMD64}" ;;
    aarch64) arch="arm64"; sha="${RCLONE_SHA256_ARM64}" ;;
  esac

  log "Installing rclone ${RCLONE_VERSION}"
  zip="rclone-v${RCLONE_VERSION}-linux-${arch}.zip"
  url="https://downloads.rclone.org/v${RCLONE_VERSION}/${zip}"
  tmp="$(mktemp -d)"

  curl -fsSL --proto '=https' --tlsv1.2 -o "${tmp}/${zip}" "${url}"
  if ! printf '%s  %s\n' "${sha}" "${tmp}/${zip}" | sha256sum -c - >/dev/null; then
    rm -rf "${tmp}"
    die "checksum mismatch for ${zip}; refusing to install it"
  fi
  unzip -qq -j "${tmp}/${zip}" "*/rclone" -d "${tmp}"
  install -d -m 0755 "${PREFIX}/bin"
  install -m 0755 "${tmp}/rclone" "${PREFIX}/bin/rclone"
  rm -rf "${tmp}"

  if [[ -L /usr/local/bin/rclone ]] || [[ ! -e /usr/local/bin/rclone ]]; then
    ln -sfn "${PREFIX}/bin/rclone" /usr/local/bin/rclone
  fi
}

# --- application -----------------------------------------------------------

# One virtualenv per release, inside the release. A shared one forces a choice
# between rewriting an environment a live process is importing from and holding
# the service down across the whole install; per-release, the running service
# keeps its own environment untouched while this one is built, and the previous
# release stays complete and startable for a rollback.
install_python_env() {
  local venv="${RELEASE_DIR}/venv"

  # Written only once every requirement is in. Testing for a binary instead
  # would call an interrupted install finished: pip installs in its own order,
  # so bin/gunicorn can exist while later dependencies are still missing.
  if [[ -f "${venv}/.install-complete" ]]; then
    log "Python environment for ${VERSION} is already built"
    return
  fi

  log "Building the Python environment for ${VERSION}"
  rm -rf "${venv}"
  python3 -m venv "${venv}"
  "${venv}/bin/pip" install --quiet --upgrade pip setuptools wheel
  "${venv}/bin/pip" install --quiet -r "${RELEASE_DIR}/requirements.txt"
  touch "${venv}/.install-complete"
}

write_env_file() {
  # Written once. An upgrade must not overwrite the port, data directory or any
  # setting the operator has since edited by hand.
  if [[ -f "${ENV_FILE}" ]]; then
    log "Keeping the existing ${ENV_FILE}"
    return
  fi

  log "Writing ${ENV_FILE}"
  cat >"${ENV_FILE}" <<ENV
# Borg UI configuration. Edit and run: systemctl restart borg-ui
# Every path below is derived from DATA_DIR by the application unless set here.
PORT=${PORT}
DATA_DIR=${DATA_DIR}
HOME=${DATA_DIR}/home
BORG_BACKUP_PATH=${DATA_DIR}/backups
BORG_CACHE_DIR=${DATA_DIR}/cache/borg

# The whole host is browsable as a backup source on a native install; the
# Docker default (/local) only makes sense for a bind-mounted container.
LOCAL_MOUNT_POINTS=/

# Cron scheduling is owned by the application's own scheduler.
ENABLE_CRON_BACKUPS=false

ACTIVATION_SERVICE_URL=https://license.borgui.com
ENABLE_STARTUP_LICENSE_SYNC=true

# Redis is optional. Without it the archive cache is in-memory and is lost on
# restart. To use one, install redis-server and set:
# REDIS_HOST=127.0.0.1
# REDIS_PORT=6379
REDIS_HOST=disabled
ENV
  chmod 0640 "${ENV_FILE}"
  chown "root:$(id -gn "${SERVICE_USER}")" "${ENV_FILE}"
}

# Everything above this point is preparation and leaves the running install
# alone, so a failure there exits with the old release still serving. From here
# on the switch is a symlink move and a restart, and PREVIOUS_RELEASE is what
# install_service falls back to if the new one will not come up.
activate_release() {
  local group
  group="$(id -gn "${SERVICE_USER}")"

  PREVIOUS_RELEASE="$(readlink -f "${PREFIX}/current" 2>/dev/null || true)"
  [[ "${PREVIOUS_RELEASE}" != "${RELEASE_DIR}" ]] || PREVIOUS_RELEASE=""

  # Only when this run will start it again. With --no-start, install_service
  # returns without starting, so stopping here would turn an upgrade into an
  # outage lasting until the operator noticed. The running service keeps
  # serving the code it already loaded; moving the symlink underneath it does
  # not disturb it, and the new release takes effect on the next restart.
  if [[ "${START_SERVICE}" == "true" ]] && systemctl is-active --quiet borg-ui 2>/dev/null; then
    log "Stopping borg-ui for the switch"
    systemctl stop borg-ui
  fi

  log "Activating release ${VERSION}"
  # Root-owned and read-only to the service user: the service executes
  # start.sh and imports the application from this tree, so letting the user
  # it runs as write here would mean a compromised app could replace the code
  # that runs on the next restart. Nothing in the app writes inside the
  # release tree; every path it writes to derives from DATA_DIR.
  chown -R "root:${group}" "${RELEASE_DIR}"
  chmod -R u=rwX,go=rX "${RELEASE_DIR}"
  ln -sfn "${RELEASE_DIR}" "${PREFIX}/current"

  # app/api/agent_installer.py serves the managed-agent wheelhouse from
  # /opt/borg-ui/agent-dist by default; keep that path pointing at this release.
  if [[ -d "${RELEASE_DIR}/agent-dist" ]]; then
    ln -sfn "${RELEASE_DIR}/agent-dist" "${PREFIX}/agent-dist"
  fi
}

# Keeps the running release and the one before it, so a rollback always has a
# complete tree with its own virtualenv to go back to. Older ones are only
# disk.
prune_old_releases() {
  local release
  for release in "${PREFIX}"/releases/*/; do
    release="${release%/}"
    [[ -d "${release}" ]] || continue
    [[ "${release}" != "${RELEASE_DIR}" ]] || continue
    [[ "${release}" != "${PREVIOUS_RELEASE}" ]] || continue
    log "Removing superseded release $(basename "${release}")"
    rm -rf "${release}"
  done
}

# Type=exec makes systemctl return as soon as gunicorn is exec'd, which is
# before it has bound the port and says nothing about whether it stayed up. A
# release that dies on a bad migration or a taken port would otherwise count as
# a successful start and never roll back, so wait for the app to actually
# answer.
wait_until_serving() {
  local deadline=$((SECONDS + 90))

  while ((SECONDS < deadline)); do
    if ! systemctl is-active --quiet borg-ui; then
      warn "borg-ui exited during startup"
      return 1
    fi
    if curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/" 2>/dev/null; then
      return 0
    fi
    sleep 2
  done

  warn "borg-ui did not answer on port ${PORT} within 90s"
  return 1
}

install_service() {
  log "Installing the systemd unit"
  sed -e "s|@PREFIX@|${PREFIX}|g" \
      -e "s|@ENV_FILE@|${ENV_FILE}|g" \
      -e "s|@SERVICE_USER@|${SERVICE_USER}|g" \
      -e "s|@SERVICE_GROUP@|$(id -gn "${SERVICE_USER}")|g" \
      "${RELEASE_DIR}/packaging/native/borg-ui.service" >"${UNIT_FILE}"
  systemctl daemon-reload
  systemctl enable borg-ui >/dev/null

  if [[ "${START_SERVICE}" != "true" ]]; then
    log "Not starting the service (--no-start). Apply it with: systemctl restart borg-ui"
    return
  fi

  if systemctl restart borg-ui && wait_until_serving; then
    return
  fi

  # The unit is prefix-based, not release-specific, so pointing "current" back
  # at the previous release is the whole rollback: that tree still has its own
  # virtualenv and was serving a moment ago.
  if [[ -n "${PREVIOUS_RELEASE}" ]] && [[ -d "${PREVIOUS_RELEASE}" ]]; then
    warn "${VERSION} did not start; rolling back to $(basename "${PREVIOUS_RELEASE}")"
    ln -sfn "${PREVIOUS_RELEASE}" "${PREFIX}/current"
    [[ -d "${PREVIOUS_RELEASE}/agent-dist" ]] &&
      ln -sfn "${PREVIOUS_RELEASE}/agent-dist" "${PREFIX}/agent-dist"
    # restart, not start: wait_until_serving also fails on a release that is
    # still "active" but never answers, and start would be a no-op there,
    # leaving the hung new release running behind a rolled-back symlink.
    if systemctl restart borg-ui && wait_until_serving; then
      warn "rolled back; ${PREVIOUS_RELEASE##*/} is serving again"
    else
      warn "the previous release did not come up either"
    fi
  fi
  die "borg-ui ${VERSION} failed to start; see: journalctl -u borg-ui -n 50"
}

report() {
  local address
  address="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo
  log "Borg UI ${VERSION} is installed."
  echo "    URL:      http://${address:-localhost}:${PORT}"
  echo "    Data:     ${DATA_DIR}"
  echo "    Config:   ${ENV_FILE}"
  echo "    Logs:     journalctl -u borg-ui -f"
  echo "    Upgrade:  re-run this installer"
}

main() {
  preflight
  resolve_version
  install_packages
  download_release

  # The pinned Borg and rclone versions travel in the release, so the installer
  # itself carries no version constants and cannot drift from the image.
  # shellcheck source=/dev/null
  source "${RELEASE_DIR}/packaging/native/versions.env"

  load_persisted_settings
  create_service_user
  create_directories
  install_python_env
  install_borg1
  install_borg2
  install_rclone
  write_env_file
  activate_release
  install_service
  prune_old_releases
  report
}

main "$@"
