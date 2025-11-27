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

# Setup SSH key symlink for root user (when PUID=0)
# When borg user runs as root (UID 0), SSH looks for keys in /root/.ssh
# but we deploy them to /home/borg/.ssh. Create symlink to handle this.
if [ "$PUID" = "0" ]; then
    echo "[$(date)] PUID is 0 (root), creating symlink /root/.ssh -> /home/borg/.ssh"
    # Remove existing /root/.ssh if it's a directory or symlink
    if [ -L /root/.ssh ]; then
        rm /root/.ssh
        echo "[$(date)] Removed existing /root/.ssh symlink"
    elif [ -d /root/.ssh ] && [ ! -L /root/.ssh ]; then
        # If it's a real directory, back it up before removing
        if [ "$(ls -A /root/.ssh 2>/dev/null)" ]; then
            echo "[$(date)] Backing up existing /root/.ssh to /root/.ssh.backup"
            mv /root/.ssh /root/.ssh.backup
        else
            rm -rf /root/.ssh
        fi
    fi
    # Create symlink
    ln -sf /home/borg/.ssh /root/.ssh
    echo "[$(date)] Created symlink /root/.ssh -> /home/borg/.ssh"
fi

# Setup Docker socket access if mounted
if [ -S /var/run/docker.sock ]; then
    DOCKER_SOCK_GID=$(stat -c '%g' /var/run/docker.sock)
    echo "[$(date)] Docker socket detected (GID: ${DOCKER_SOCK_GID})"

    # Check if docker group exists
    if getent group docker > /dev/null 2>&1; then
        # Docker group exists, update its GID if needed
        CURRENT_DOCKER_GID=$(getent group docker | cut -d: -f3)
        if [ "$CURRENT_DOCKER_GID" != "$DOCKER_SOCK_GID" ]; then
            groupmod -o -g "${DOCKER_SOCK_GID}" docker
            echo "[$(date)] Updated docker group GID from ${CURRENT_DOCKER_GID} to ${DOCKER_SOCK_GID}"
        else
            echo "[$(date)] Docker group already has correct GID ${DOCKER_SOCK_GID}"
        fi
        # Add borg user to docker group
        usermod -a -G docker borg
        echo "[$(date)] Added borg user to docker group - docker commands will work in scripts"
    else
        # Docker group doesn't exist, try to create it
        # Use -o flag to allow duplicate GID (in case another group has this GID)
        if groupadd -o -g "${DOCKER_SOCK_GID}" docker 2>/dev/null; then
            echo "[$(date)] Created docker group with GID ${DOCKER_SOCK_GID}"
            # Add borg user to docker group
            usermod -a -G docker borg
            echo "[$(date)] Added borg user to docker group - docker commands will work in scripts"
        else
            # Group creation failed, likely because GID is taken by another group
            # Find the group that has this GID and add borg to it
            EXISTING_GROUP=$(getent group "${DOCKER_SOCK_GID}" | cut -d: -f1)
            if [ -n "$EXISTING_GROUP" ]; then
                echo "[$(date)] GID ${DOCKER_SOCK_GID} already used by group '${EXISTING_GROUP}', adding borg to it"
                usermod -a -G "${EXISTING_GROUP}" borg
                echo "[$(date)] Added borg user to ${EXISTING_GROUP} group - docker commands will work in scripts"
            else
                echo "[$(date)] Warning: Could not create docker group or find existing group with GID ${DOCKER_SOCK_GID}"
            fi
        fi
    fi
else
    echo "[$(date)] Docker socket not mounted, skipping docker group setup"
fi

# Deploy SSH keys from database to filesystem
echo "[$(date)] Deploying SSH keys..."
python3 /app/app/scripts/deploy_ssh_key.py || echo "[$(date)] Warning: SSH key deployment failed"

# Switch to borg user and start the application
echo "[$(date)] Starting Borg Web UI as user borg (${PUID}:${PGID})..."
cd /app
PORT=${PORT:-8081}

# Start package installation in background (non-blocking)
# This runs after a delay to ensure API is ready
(
    sleep 5  # Give the API time to fully start
    echo "[$(date)] Starting package installation jobs..."
    python3 /app/app/scripts/startup_packages.py || echo "[$(date)] Warning: Package startup failed"
) &

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
