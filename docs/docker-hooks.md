# Docker Container Management in Backup Hooks

This guide explains how to use Docker container management in pre/post backup hooks to safely backup containers with databases or other stateful applications.

## Table of Contents

- [Why Stop Containers During Backup?](#why-stop-containers-during-backup)
- [Quick Start](#quick-start)
- [Security Considerations](#security-considerations)
- [Example Scripts](#example-scripts)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

## Why Stop Containers During Backup?

Some applications need to be stopped before backing up their data to ensure consistency:

- **Databases** (PostgreSQL, MySQL, MongoDB): Prevent corruption from in-flight transactions
- **Key-value stores** (Redis): Ensure consistent snapshot
- **File-based databases** (SQLite): Prevent locked files
- **Stateful applications**: Ensure clean state during backup

**Alternative approaches:**
- Use database-native backup tools (e.g., `pg_dump`, `mysqldump`)
- Enable database WAL archiving for continuous backup
- Use application-specific backup APIs

However, stopping containers is the simplest and most reliable approach for many use cases.

## Quick Start

### 1. Enable Docker Socket Access

Edit your `docker-compose.yml` and uncomment the docker.sock volume:

```yaml
volumes:
  - borg_data:/data:rw
  - borg_cache:/home/borg/.cache/borg:rw
  - ${LOCAL_STORAGE_PATH:-/}:/local:rw
  # Uncomment the line below:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

### 2. Restart Borg UI

```bash
docker-compose down
docker-compose up -d
```

### 3. Configure Pre/Post Backup Scripts

In the Borg UI:
1. Go to **Repositories**
2. Edit your repository
3. Scroll to **Advanced Settings**
4. Add your pre/post backup scripts

## Security Considerations

⚠️ **IMPORTANT**: Mounting `/var/run/docker.sock` gives the container **full access** to your Docker daemon. This is equivalent to root access on your host system.

### Security Best Practices:

1. **Use read-only when possible**: Mount as `:ro` if you only need to inspect containers
   ```yaml
   - /var/run/docker.sock:/var/run/docker.sock:ro
   ```

2. **Limit container names**: Only stop/start specific containers by name (never use `docker stop $(docker ps -q)`)

3. **Validate scripts**: Test scripts thoroughly before using in production

4. **Monitor logs**: Check backup logs to ensure hooks execute correctly

5. **Use Docker contexts**: Consider using Docker contexts to limit scope

6. **Network isolation**: Keep Borg UI on an isolated network if possible

### Alternatives Without Docker Socket:

If you don't want to mount docker.sock, consider:
- Use database backup commands instead (pg_dump, mysqldump)
- Use application APIs to trigger backups
- Use systemd services to stop/start containers
- Use docker-compose stop/start from host cron jobs

## Example Scripts

### Basic: Stop/Start Single Container

**Pre-backup script:**
```bash
#!/bin/bash
set -e

# Note: Docker CLI (docker.io package) can be installed from the UI
# Go to Settings → Packages and install "docker.io"
# This is a one-time setup that persists across container restarts

# Stop container
echo "Stopping postgres-db container..."
docker stop postgres-db

echo "Container stopped successfully"
```

**Post-backup script:**
```bash
#!/bin/bash
set -e

# Start container
echo "Starting postgres-db container..."
docker start postgres-db

echo "Container started successfully"
```

### Advanced: Stop Multiple Containers with Error Handling

**Pre-backup script:**
```bash
#!/bin/bash
set -e

# Note: Install docker.io package from Settings → Packages if not already installed

# Define containers to stop
CONTAINERS=("postgres-db" "redis-cache" "mysql-db")

# Stop containers gracefully
echo "Stopping containers for backup..."
for container in "${CONTAINERS[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo "Stopping ${container}..."
        docker stop -t 30 "${container}"
        echo "✓ ${container} stopped"
    else
        echo "⚠ ${container} not running, skipping"
    fi
done

# Wait for containers to fully stop
sleep 5

echo "All containers stopped successfully"
```

**Post-backup script:**
```bash
#!/bin/bash
set -e

# Define containers to start (same order as pre-backup)
CONTAINERS=("postgres-db" "redis-cache" "mysql-db")

# Start containers
echo "Starting containers after backup..."
for container in "${CONTAINERS[@]}"; do
    if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
        echo "Starting ${container}..."
        docker start "${container}"

        # Wait for container to be healthy
        for i in {1..30}; do
            if docker inspect --format='{{.State.Status}}' "${container}" | grep -q "running"; then
                echo "✓ ${container} started"
                break
            fi
            sleep 1
        done
    else
        echo "⚠ ${container} does not exist, skipping"
    fi
done

echo "All containers started successfully"
```

### Database-Specific: PostgreSQL Checkpoint

**Pre-backup script:**
```bash
#!/bin/bash
set -e

# Trigger PostgreSQL checkpoint before stopping
echo "Triggering PostgreSQL checkpoint..."
docker exec postgres-db psql -U postgres -c "CHECKPOINT;"

# Stop container
echo "Stopping postgres-db..."
docker stop postgres-db

echo "PostgreSQL ready for backup"
```

### With Notifications

**Pre-backup script:**
```bash
#!/bin/bash
set -e

# Send notification (if using notification service)
echo "📢 Starting backup preparation..."

# Stop containers
CONTAINERS=("postgres-db" "redis-cache")
for container in "${CONTAINERS[@]}"; do
    docker stop -t 30 "${container}" || echo "⚠ Failed to stop ${container}"
done

echo "✓ Containers stopped, backup will proceed"
```

**Post-backup script:**
```bash
#!/bin/bash
set -e

# Start containers
CONTAINERS=("postgres-db" "redis-cache")
for container in "${CONTAINERS[@]}"; do
    docker start "${container}" || echo "⚠ Failed to start ${container}"
done

echo "✓ Containers restarted after backup"
```

### Docker Compose Integration

**Pre-backup script:**
```bash
#!/bin/bash
set -e

# Stop Docker Compose stack
echo "Stopping Docker Compose stack..."
cd /path/to/your/compose/directory
docker-compose stop

echo "Stack stopped for backup"
```

**Post-backup script:**
```bash
#!/bin/bash
set -e

# Start Docker Compose stack
echo "Starting Docker Compose stack..."
cd /path/to/your/compose/directory
docker-compose start

echo "Stack restarted after backup"
```

## Troubleshooting

### Docker Command Not Found

**Error:**
```
bash: docker: command not found
```

**Solution:**
The Docker CLI isn't installed in the container. Install it from the UI:

1. Go to **Settings** → **Packages** tab
2. Find and install **docker.io** package
3. Wait for installation to complete
4. The docker command will be available in your scripts

This is a one-time setup that persists across container restarts.

### Permission Denied

**Error:**
```
permission denied while trying to connect to the Docker daemon socket
```

**Solution 1:** Check docker.sock is mounted:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

**Solution 2:** Restart Borg UI container:
```bash
docker-compose restart
```

### Container Won't Stop

**Error:**
```
Container still running after stop command
```

**Solution:** Increase graceful stop timeout:
```bash
docker stop -t 60 container-name  # Wait 60 seconds before force kill
```

### Hook Timeout

**Error:**
```
Pre-backup hook timed out
```

**Solution:** Hooks have a default timeout (usually 300 seconds). Either:
1. Optimize your script to run faster
2. Reduce the number of containers you stop/start
3. Contact maintainer to increase timeout if needed

### Container Doesn't Restart After Backup

**Problem:** Backup completes but containers stay stopped

**Solution:** Check post-backup script logs in the backup job details. Common issues:
- Script has errors (use `set -e` to catch them)
- Wrong container names
- Containers were removed instead of stopped

**Safety tip:** Always test your post-backup script manually:
```bash
docker exec -it borg-web-ui bash
# Run your post-backup script
bash /path/to/post-backup-script.sh
```

## Best Practices

### 1. Test Scripts Before Production

Always test your scripts manually before enabling them:

```bash
# Enter the container
docker exec -it borg-web-ui bash

# Test pre-backup script
bash -c 'your-pre-backup-script-here'

# Verify containers stopped
docker ps

# Test post-backup script
bash -c 'your-post-backup-script-here'

# Verify containers started
docker ps
```

### 2. Use Graceful Stop Timeouts

Give containers time to shut down gracefully:

```bash
docker stop -t 30 container-name  # 30 second grace period
```

### 3. Log Everything

Add logging to track execution:

```bash
echo "[$(date)] Stopping container: postgres-db"
docker stop postgres-db
echo "[$(date)] Container stopped successfully"
```

### 4. Handle Errors Gracefully

Don't fail the backup if a container is already stopped:

```bash
if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    docker stop "${container}"
else
    echo "Container ${container} not running, skipping"
fi
```

### 5. Verify Container Health After Restart

```bash
# Start container
docker start postgres-db

# Wait for health check
for i in {1..30}; do
    if docker inspect --format='{{.State.Health.Status}}' postgres-db | grep -q "healthy"; then
        echo "Container healthy"
        break
    fi
    sleep 2
done
```

### 6. Use Container Labels

Tag containers that should be stopped for backups:

```yaml
# In your container's docker-compose.yml
labels:
  - "backup.stop=true"
```

Then in your script:
```bash
# Stop all containers with backup.stop label
docker ps --filter "label=backup.stop=true" --format "{{.Names}}" | \
    xargs -r docker stop -t 30
```

### 7. Consider Downtime Windows

Schedule backups during low-usage periods to minimize impact:
- Use cron schedules in Borg UI (e.g., 2 AM daily)
- Stop containers only for critical backups
- Use database dump tools for hot backups

### 8. Monitor Backup Logs

Always check the backup logs after enabling hooks:
1. Go to **Dashboard** → **Backup Jobs**
2. Click on a completed job
3. Scroll to **Hook Execution** section
4. Verify pre/post scripts executed successfully

## Example: Complete PostgreSQL Backup Setup

This is a production-ready example for backing up a PostgreSQL container:

**Pre-backup script:**
```bash
#!/bin/bash
set -e

# Configuration
CONTAINER_NAME="postgres-db"
STOP_TIMEOUT=30

# Note: Install docker.io package from Settings → Packages if not already installed

echo "[$(date)] Starting pre-backup hook for ${CONTAINER_NAME}"

# Check if container exists and is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    # Trigger PostgreSQL checkpoint for clean shutdown
    echo "[$(date)] Triggering PostgreSQL checkpoint..."
    docker exec "${CONTAINER_NAME}" psql -U postgres -c "CHECKPOINT;" || echo "Warning: Checkpoint failed"

    # Stop container gracefully
    echo "[$(date)] Stopping ${CONTAINER_NAME} (${STOP_TIMEOUT}s timeout)..."
    docker stop -t ${STOP_TIMEOUT} "${CONTAINER_NAME}"

    echo "[$(date)] ${CONTAINER_NAME} stopped successfully"
else
    echo "[$(date)] ${CONTAINER_NAME} not running, backup will proceed anyway"
fi

echo "[$(date)] Pre-backup hook completed"
```

**Post-backup script:**
```bash
#!/bin/bash
set -e

# Configuration
CONTAINER_NAME="postgres-db"
HEALTH_CHECK_TIMEOUT=60

echo "[$(date)] Starting post-backup hook for ${CONTAINER_NAME}"

# Check if container exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    # Start container
    echo "[$(date)] Starting ${CONTAINER_NAME}..."
    docker start "${CONTAINER_NAME}"

    # Wait for container to be running
    echo "[$(date)] Waiting for ${CONTAINER_NAME} to be ready..."
    for i in $(seq 1 ${HEALTH_CHECK_TIMEOUT}); do
        if docker inspect --format='{{.State.Status}}' "${CONTAINER_NAME}" | grep -q "running"; then
            echo "[$(date)] ${CONTAINER_NAME} is running"

            # Wait for PostgreSQL to accept connections
            sleep 5
            if docker exec "${CONTAINER_NAME}" pg_isready -U postgres > /dev/null 2>&1; then
                echo "[$(date)] ${CONTAINER_NAME} is ready to accept connections"
                break
            fi
        fi
        sleep 1
    done

    echo "[$(date)] ${CONTAINER_NAME} started successfully"
else
    echo "[$(date)] Warning: ${CONTAINER_NAME} does not exist"
fi

echo "[$(date)] Post-backup hook completed"
```

## Related Documentation

- [Pre/Post Backup Scripts](./backup-hooks.md) - General hook documentation
- [Installation Guide](../docs/installation.md) - Setting up Borg UI
- [Repository Configuration](./repositories.md) - Configuring repositories

## Support

If you encounter issues with Docker hooks:
1. Check the backup job logs in the UI
2. Test your scripts manually in the container
3. Review the [troubleshooting section](#troubleshooting)
4. Open an issue on [GitHub](https://github.com/karanhudia/borg-ui/issues) with:
   - Your docker-compose.yml (sanitized)
   - Your pre/post backup scripts
   - Relevant log output
