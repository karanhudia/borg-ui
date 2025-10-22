#!/bin/bash
set -e

# Default values
PUID=${PUID:-1001}
PGID=${PGID:-1001}

echo "[$(date)] Borg Web UI Entrypoint"
echo "[$(date)] PUID: $PUID | PGID: $PGID"

# Get current borg user UID/GID
CURRENT_PUID=$(id -u borg)
CURRENT_PGID=$(id -g borg)

# Check if UID/GID needs to be changed
if [ "$PUID" != "$CURRENT_PUID" ] || [ "$PGID" != "$CURRENT_PGID" ]; then
    echo "[$(date)] Updating borg user UID:GID from ${CURRENT_PUID}:${CURRENT_PGID} to ${PUID}:${PGID}"

    # Change group ID if needed
    if [ "$PGID" != "$CURRENT_PGID" ]; then
        groupmod -o -g "$PGID" borg
    fi

    # Change user ID if needed
    if [ "$PUID" != "$CURRENT_PUID" ]; then
        usermod -o -u "$PUID" borg
    fi

    # Update ownership of key directories
    echo "[$(date)] Updating ownership of /data, /backups, /home/borg..."
    chown -R borg:borg /data /backups /home/borg /var/log/borg /etc/borg 2>/dev/null || true

    echo "[$(date)] UID/GID update complete"
else
    echo "[$(date)] UID/GID already correct, skipping update"
fi

# Deploy SSH keys from database to filesystem
echo "[$(date)] Deploying SSH keys..."
python3 /app/app/scripts/deploy_ssh_key.py || echo "[$(date)] Warning: SSH key deployment failed"

# Switch to borg user and start the application
echo "[$(date)] Starting Borg Web UI as user borg (${PUID}:${PGID})..."
cd /app
PORT=${PORT:-8081}

# Note: Access logs disabled (/dev/null) because FastAPI middleware already logs all requests
# with structured logging. This prevents duplicate log entries.
exec gosu borg gunicorn app.main:app \
    --bind 0.0.0.0:${PORT} \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 0 \
    --graceful-timeout 30 \
    --access-logfile /dev/null \
    --error-logfile -
