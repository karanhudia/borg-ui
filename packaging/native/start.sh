#!/usr/bin/env bash
#
# Native counterpart of the Docker entrypoint's launch sequence. The container
# does its filesystem and user setup here too because an image is stateless; on
# a host the installer has already done that, so this file is only the boot
# steps that have to run on every start.
set -euo pipefail

# The release directory, with symlinks resolved: this file lives at
# <prefix>/current/packaging/native/start.sh, and "current" points into
# <prefix>/releases/<version>.
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"

# Each release carries its own virtualenv, so an upgrade never rewrites the one
# a running service is importing from. The systemd unit passes its path; the
# fallback only exists so this script can be run by hand from an installed tree.
VENV="${BORG_UI_VENV:-${APP_ROOT}/venv}"
PYTHON="${VENV}/bin/python"
PORT="${PORT:-8081}"

if [[ ! -x "${PYTHON}" ]]; then
  echo "[borg-ui] No Python environment at ${VENV}; re-run the installer." >&2
  exit 1
fi

cd "${APP_ROOT}"
export PYTHONPATH="${APP_ROOT}"

# Bring the database up to date before anything reads it: deploy_ssh_key below
# reads SSH keys from it, and on a first boot the tables do not exist yet.
# Runs here rather than inside the app because gunicorn would fork workers that
# each race over the same database. A failure stops the boot on purpose --
# serving from a database in an unknown state is worse than not starting.
echo "[borg-ui] Checking database..."
"${PYTHON}" -m app.database.db_upgrade

echo "[borg-ui] Deploying SSH keys..."
"${PYTHON}" app/scripts/deploy_ssh_key.py || echo "[borg-ui] Warning: SSH key deployment failed" >&2

# Package installation jobs are queued through the API, so give it time to come
# up first. Backgrounded, exactly as the container does it.
(
  sleep 5
  "${PYTHON}" app/scripts/startup_packages.py || echo "[borg-ui] Warning: package startup failed" >&2
) &

echo "[borg-ui] Starting on port ${PORT}..."
# Access logs go to /dev/null because the FastAPI middleware already logs every
# request with structured logging; enabling both duplicates each line.
exec "${VENV}/bin/gunicorn" app.main:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --worker-class uvicorn.workers.UvicornWorker \
  --timeout 0 \
  --graceful-timeout 30 \
  --worker-tmp-dir /dev/shm \
  --access-logfile /dev/null \
  --error-logfile -
