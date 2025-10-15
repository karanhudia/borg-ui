# Testing Guide - Docker Volumes Setup

## Prerequisites

- Docker installed and running
- Git repository cloned

## Quick Start (Docker Volumes - Recommended)

```bash
# 1. Clone the repository (if not already done)
git clone <repo-url>
cd borg-ui

# 2. Start the application (volumes created automatically)
docker-compose up -d

# 3. Access the application
open http://localhost:7879
```

That's it! Docker will automatically create the `borg_data` and `borg_backups` volumes.

## What Happens Automatically

When you run `docker-compose up -d`:

1. **Docker volumes are created** (if they don't exist):
   - `borg_data` - Stores database, configs, logs, SSH keys
   - `borg_backups` - Stores Borg backup repositories

2. **Application starts** and initializes:
   - Database is created at first run
   - Application directories are set up
   - Web UI becomes available at http://localhost:7879

3. **No manual setup required!**

## Verify Volume Creation

```bash
# List Docker volumes
docker volume ls | grep borg

# Expected output:
# local     borg_backups
# local     borg_data

# Inspect a volume
docker volume inspect borg_data

# Browse volume contents
docker run --rm -it -v borg_data:/data alpine sh -c "ls -lah /data"
```

## Testing Steps

### 1. Test Fresh Installation

```bash
# Stop and remove everything
docker-compose down -v

# Start fresh
docker-compose up -d

# Check logs
docker-compose logs -f

# Access UI
open http://localhost:7879
```

### 2. Test Data Persistence

```bash
# Create some data in the UI (configs, SSH keys, etc.)

# Restart the container
docker-compose restart

# Or stop and start
docker-compose down
docker-compose up -d

# Verify data persists by checking the UI
open http://localhost:7879
```

### 3. Test Volume Backup

```bash
# Backup the data volume
docker run --rm \
  -v borg_data:/source:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/borg-data-backup.tar.gz -C /source .

# Verify backup was created
ls -lh borg-data-backup.tar.gz
```

### 4. Test Volume Restore

```bash
# Stop the application
docker-compose down

# Remove the volume
docker volume rm borg_data

# Recreate the volume
docker volume create borg_data

# Restore from backup
docker run --rm \
  -v borg_data:/target \
  -v $(pwd):/backup \
  alpine sh -c "tar xzf /backup/borg-data-backup.tar.gz -C /target"

# Start the application
docker-compose up -d

# Verify restored data in UI
open http://localhost:7879
```

### 5. Test Portainer Integration (Optional)

If you have Portainer installed:

```bash
# Access Portainer
open http://localhost:9000

# Navigate to: Volumes
# You should see:
# - borg_data
# - borg_backups

# You can browse, backup, and manage volumes from Portainer UI
```

## Alternative: Test with Bind Mounts (Legacy)

If you prefer bind mounts for development:

```bash
# Use the bind-mounts compose file
docker-compose -f docker-compose.bind-mounts.yml up -d

# This creates ./data and ./backups directories on host
ls -la ./data ./backups
```

## Common Commands

### Volume Management

```bash
# List all volumes
docker volume ls

# Inspect volume
docker volume inspect borg_data

# Remove unused volumes
docker volume prune

# Remove specific volume (container must be stopped)
docker volume rm borg_data
```

### Container Management

```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Restart
docker-compose restart

# View logs
docker-compose logs -f

# Execute command in container
docker-compose exec app sh
```

### Rebuild After Changes

```bash
# Rebuild and restart
docker-compose up -d --build

# Force rebuild (no cache)
docker-compose build --no-cache
docker-compose up -d
```

## Troubleshooting

### Issue: Volumes not persisting

**Check:**
```bash
# Verify volumes exist
docker volume ls | grep borg

# Check if volumes are mounted
docker inspect borg-ui | grep -A 20 Mounts
```

**Fix:**
```bash
# Recreate volumes
docker-compose down -v
docker-compose up -d
```

### Issue: Permission errors

**Check:**
```bash
# Check volume ownership
docker run --rm -it -v borg_data:/data alpine ls -la /data
```

**Fix:**
```bash
# The application should handle permissions automatically
# If issues persist, check application logs
docker-compose logs app
```

### Issue: Cannot connect to database

**Check:**
```bash
# Verify database file exists in volume
docker run --rm -v borg_data:/data alpine ls -la /data/*.db
```

**Fix:**
```bash
# Restart the application
docker-compose restart

# If still failing, check logs
docker-compose logs app | grep -i database
```

### Issue: Docker daemon not running

**macOS (Colima):**
```bash
# Start Colima
colima start

# Check status
colima status
```

**Docker Desktop:**
```bash
# Start Docker Desktop application
open -a Docker
```

## Performance Testing

### Test Backup Speed

```bash
# Create test data
docker run --rm -v borg_data:/data alpine sh -c "dd if=/dev/urandom of=/data/test.bin bs=1M count=100"

# Time the backup
time docker run --rm \
  -v borg_data:/source:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/test-backup.tar.gz -C /source .

# Clean up
rm test-backup.tar.gz
docker run --rm -v borg_data:/data alpine rm /data/test.bin
```

### Test Application Performance

```bash
# Monitor resource usage
docker stats borg-ui

# Check response time
time curl -s http://localhost:7879/api/health/system

# Load test (requires `ab` tool)
ab -n 100 -c 10 http://localhost:7879/api/health/system
```

## Expected Results

### ✅ Successful Installation
- Docker volumes `borg_data` and `borg_backups` created
- Container starts without errors
- UI accessible at http://localhost:7879
- Health check passes: http://localhost:7879/api/health/system
- Logs show no errors

### ✅ Data Persistence
- Data survives container restart
- Data survives `docker-compose down && docker-compose up`
- Configurations, SSH keys, and database persist

### ✅ Volume Operations
- Backup creates tar.gz file successfully
- Restore from backup works
- Volume browsing shows correct files
- Portainer (if installed) shows volumes

## CI/CD Testing

For automated testing in CI/CD:

```bash
#!/bin/bash
set -e

# Start application
docker-compose up -d

# Wait for health check
timeout 60 bash -c 'until curl -f http://localhost:7879/api/health/system; do sleep 2; done'

# Run tests
curl -f http://localhost:7879/api/health/system
docker volume ls | grep -q borg_data
docker volume ls | grep -q borg_backups

# Cleanup
docker-compose down -v

echo "✅ All tests passed!"
```

## Next Steps After Testing

1. **Configure the application** via UI:
   - Create borgmatic configuration
   - Generate SSH keys
   - Set up repositories
   - Run test backup

2. **Set up monitoring**:
   - Check backup logs
   - Monitor volume usage
   - Set up alerts

3. **Production deployment**:
   - Review VOLUME_MANAGEMENT.md for backup strategies
   - Set up regular volume backups
   - Configure external storage if needed
   - Deploy to Portainer/Swarm if using orchestration

## Additional Resources

- **Volume Management**: See `VOLUME_MANAGEMENT.md`
- **Implementation Tasks**: See `IMPLEMENTATION_TASKS.md`
- **System Design**: See `SYSTEM_DESIGN.md`
- **Docker Volumes Documentation**: https://docs.docker.com/storage/volumes/
