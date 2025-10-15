#!/bin/bash
set -e

# Default values
PUID=${PUID:-1001}
PGID=${PGID:-1001}

echo "[$(date)] Borgmatic Web UI Entrypoint"
echo "[$(date)] PUID: $PUID | PGID: $PGID"

# Get current borgmatic user UID/GID
CURRENT_PUID=$(id -u borgmatic)
CURRENT_PGID=$(id -g borgmatic)

# Check if UID/GID needs to be changed
if [ "$PUID" != "$CURRENT_PUID" ] || [ "$PGID" != "$CURRENT_PGID" ]; then
    echo "[$(date)] Updating borgmatic user UID:GID from ${CURRENT_PUID}:${CURRENT_PGID} to ${PUID}:${PGID}"

    # Change group ID if needed
    if [ "$PGID" != "$CURRENT_PGID" ]; then
        groupmod -o -g "$PGID" borgmatic
    fi

    # Change user ID if needed
    if [ "$PUID" != "$CURRENT_PUID" ]; then
        usermod -o -u "$PUID" borgmatic
    fi

    # Update ownership of key directories
    echo "[$(date)] Updating ownership of /data, /backups, /home/borgmatic..."
    chown -R borgmatic:borgmatic /data /backups /home/borgmatic /var/log/borgmatic /etc/borgmatic 2>/dev/null || true

    echo "[$(date)] UID/GID update complete"
else
    echo "[$(date)] UID/GID already correct, skipping update"
fi

# Switch to borgmatic user and start the application
echo "[$(date)] Starting Borgmatic Web UI as user borgmatic (${PUID}:${PGID})..."
cd /app
PORT=${PORT:-8081}

exec gosu borgmatic gunicorn app.main:app \
    --bind 0.0.0.0:${PORT} \
    --workers 1 \
    --worker-class uvicorn.workers.UvicornWorker \
    --access-logfile - \
    --error-logfile -
