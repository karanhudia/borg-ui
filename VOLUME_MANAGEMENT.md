# Volume Management Guide

## Overview

Borg UI uses Docker **bind mounts** to persist data between container restarts. This means directories on your host system are mounted directly into the container, making data accessible from both the host and container.

## Volume Structure

```
borg-ui/
├── data/              # Main data directory (auto-created)
│   ├── config/        # Borgmatic configuration files
│   ├── logs/          # Backup job logs
│   ├── ssh_keys/      # SSH keys (restricted permissions)
│   └── borgmatic.db   # SQLite database (created by app)
└── backups/           # Borg backup repositories (auto-created)
```

## Docker Compose Configuration

From `docker-compose.yml`:

```yaml
volumes:
  # Data directory - contains all persistent data
  - ./data:/data:rw

  # Backup storage - mount to external storage or NAS
  - ./backups:/backups:rw

  # System volumes (read-only)
  - /etc/cron.d:/etc/cron.d:ro
  - /etc/localtime:/etc/localtime:ro
```

**Bind Mount Syntax**: `<host-path>:<container-path>:<permissions>`
- `rw` = read-write
- `ro` = read-only

## Volume Creation Methods

### Method 1: Automatic Creation (Easiest)

Docker automatically creates host directories when you start the container:

```bash
# Clone the repository
git clone <repo-url>
cd borg-ui

# Start the application (volumes created automatically)
docker-compose up -d
```

**What happens:**
1. Docker creates `./data` and `./backups` directories if they don't exist
2. The application creates subdirectories on first run:
   - `./data/config/`
   - `./data/logs/`
   - `./data/ssh_keys/`
3. The database file is created: `./data/borgmatic.db`

### Method 2: Manual Pre-Creation (Recommended for Production)

For better control over permissions and structure:

```bash
# Run the setup script
./setup-volumes.sh
```

Or manually:

```bash
# Create directory structure
mkdir -p ./data/{config,logs,ssh_keys}
mkdir -p ./backups

# Set permissions
chmod 755 ./data
chmod 755 ./backups
chmod 755 ./data/config
chmod 755 ./data/logs
chmod 700 ./data/ssh_keys  # Restricted for security

# Start the application
docker-compose up -d
```

### Method 3: Docker-managed Volumes (Portainer-style)

Use Docker-managed volumes instead of bind mounts (recommended for production/Portainer):

**Use the provided `docker-compose.volumes.yml`:**

```bash
# Start with Docker-managed volumes
docker-compose -f docker-compose.volumes.yml up -d
```

**Or create your own configuration:**

```yaml
services:
  app:
    # ... service configuration ...
    volumes:
      # Docker-managed volumes (auto-created by Docker)
      - borg_data:/data:rw
      - borg_backups:/backups:rw

# Volume definitions
volumes:
  borg_data:
    name: borg_data
    driver: local

  borg_backups:
    name: borg_backups
    driver: local
```

**What happens:**
1. Docker automatically creates named volumes on first run
2. Volumes are stored in Docker's internal storage
3. Managed through Docker commands or Portainer UI
4. No need to manually create directories

**Advantages:**
- ✅ Automatically created by Docker
- ✅ Works seamlessly with Portainer
- ✅ Better for Docker Swarm/production
- ✅ Portable across Docker environments
- ✅ Easier backup/restore with Docker tools
- ✅ Better performance on non-Linux systems

**Volume Management Commands:**

```bash
# List volumes
docker volume ls | grep borg

# Inspect volume
docker volume inspect borg_data

# Backup volume to tar
docker run --rm \
  -v borg_data:/source:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/borg-data-backup.tar.gz -C /source .

# Restore volume from tar
docker run --rm \
  -v borg_data:/target \
  -v $(pwd):/backup \
  alpine sh -c "rm -rf /target/* && tar xzf /backup/borg-data-backup.tar.gz -C /target"

# Browse volume contents
docker run --rm -it \
  -v borg_data:/data \
  alpine sh -c "ls -lah /data"
```

### Method 4: Custom Mount Points

To use different host directories (e.g., external storage):

**Edit `docker-compose.yml`:**

```yaml
volumes:
  # Mount to external SSD
  - /mnt/external-ssd/borg-ui-data:/data:rw

  # Mount to NAS for backups
  - /mnt/nas/borg-backups:/backups:rw
```

**Then create directories on those paths:**

```bash
# On external SSD
sudo mkdir -p /mnt/external-ssd/borg-ui-data/{config,logs,ssh_keys}
sudo chown -R $USER:$USER /mnt/external-ssd/borg-ui-data
sudo chmod 700 /mnt/external-ssd/borg-ui-data/ssh_keys

# On NAS
sudo mkdir -p /mnt/nas/borg-backups
sudo chown -R $USER:$USER /mnt/nas/borg-backups

# Start
docker-compose up -d
```

## Data Persistence Details

### 1. SQLite Database (`/data/borgmatic.db`)

**Created by:** Application on first run
**Contains:**
- User accounts
- Configuration metadata
- SSH key metadata
- Repository information
- Backup job history
- Schedule information

**Backup Strategy:**
```bash
# Backup database
cp ./data/borgmatic.db ./data/borgmatic.db.backup

# Or use SQLite backup
sqlite3 ./data/borgmatic.db ".backup ./data/borgmatic.db.backup"
```

### 2. Configuration Files (`/data/config/`)

**Created by:** User via UI or API
**Format:** YAML (borgmatic configuration format)
**Naming:** `config_<id>.yaml`

**Example:**
```
./data/config/
├── config_1.yaml  # First configuration
├── config_2.yaml  # Second configuration
└── config_3.yaml  # Third configuration
```

### 3. Backup Logs (`/data/logs/`)

**Created by:** Backup jobs
**Format:** Plain text with timestamps
**Naming:** `backup_<job_id>.log`

**Example:**
```
./data/logs/
├── backup_1.log
├── backup_2.log
└── backup_3.log
```

**Retention:** Logs are kept indefinitely. Consider implementing log rotation:

```bash
# Clean logs older than 30 days
find ./data/logs -name "backup_*.log" -mtime +30 -delete
```

### 4. SSH Keys (`/data/ssh_keys/`)

**Created by:** SSH key generation feature (single key system)
**Files:**
- `id_<type>` - Private key (e.g., `id_ed25519`, `id_rsa`)
- `id_<type>.pub` - Public key

**Permissions:**
- Private key: `600` (read/write owner only)
- Public key: `644` (read all, write owner)
- Directory: `700` (owner only)

**Security Notes:**
- Never commit SSH keys to git
- Keep backups of private keys in secure location
- The `.gitignore` already excludes `data/` directory

### 5. Backup Repositories (`/backups/`)

**Created by:** Repository initialization
**Format:** Borg repository format (binary)
**Structure:**
```
./backups/
├── local-repo-1/     # Local repository
├── local-repo-2/     # Another local repository
└── ...
```

**Important:** Remote repositories are stored on remote servers via SSH, not in this directory.

## Volume Management Commands

### Check Volume Status

```bash
# List volumes
docker-compose exec app ls -lah /data
docker-compose exec app ls -lah /backups

# Check disk usage
docker-compose exec app du -sh /data
docker-compose exec app du -sh /backups
```

### Backup Volumes

```bash
# Backup everything
tar -czf borg-ui-backup-$(date +%Y%m%d).tar.gz ./data ./backups

# Backup only data (database, configs, keys)
tar -czf borg-ui-data-$(date +%Y%m%d).tar.gz ./data

# Backup only repositories
tar -czf borg-ui-backups-$(date +%Y%m%d).tar.gz ./backups
```

### Restore Volumes

```bash
# Stop container
docker-compose down

# Restore from backup
tar -xzf borg-ui-backup-20250115.tar.gz

# Start container
docker-compose up -d
```

### Clean Up

```bash
# Remove all volumes (DESTRUCTIVE!)
docker-compose down -v

# Remove only generated data (keeps manual files)
rm -rf ./data/logs/*
rm -rf ./data/config/*

# Remove repositories (VERY DESTRUCTIVE!)
rm -rf ./backups/*
```

## Common Issues

### Issue 1: Permission Denied

**Symptom:** Container can't write to `/data` or `/backups`

**Solution:**
```bash
# Fix ownership
sudo chown -R $USER:$USER ./data ./backups

# Fix permissions
chmod -R 755 ./data
chmod 700 ./data/ssh_keys
```

### Issue 2: Volumes Not Persisting

**Symptom:** Data disappears after restart

**Check:**
1. Verify bind mount in `docker-compose.yml`
2. Check if directories exist on host: `ls -la ./data ./backups`
3. Check container mounts: `docker inspect <container-id> | grep Mounts -A 20`

### Issue 3: Disk Space Full

**Symptom:** Container stops or backups fail

**Solutions:**
```bash
# Check disk usage
df -h
du -sh ./data ./backups

# Clean old logs
find ./data/logs -name "*.log" -mtime +30 -delete

# Compact Borg repositories
docker-compose exec app borgmatic compact --stats

# Move backups to larger storage
mv ./backups /mnt/larger-disk/backups
# Update docker-compose.yml to use new path
```

## Migration Guide

### Moving to New Server

```bash
# On old server
docker-compose down
tar -czf borg-ui-full-backup.tar.gz ./data ./backups
scp borg-ui-full-backup.tar.gz user@new-server:/path/to/borg-ui/

# On new server
cd /path/to/borg-ui
tar -xzf borg-ui-full-backup.tar.gz
docker-compose up -d
```

### Changing Volume Paths

```bash
# Stop container
docker-compose down

# Copy data to new location
cp -a ./data /new/path/data
cp -a ./backups /new/path/backups

# Update docker-compose.yml
sed -i 's|./data:/data|/new/path/data:/data|g' docker-compose.yml
sed -i 's|./backups:/backups|/new/path/backups:/backups|g' docker-compose.yml

# Start container
docker-compose up -d
```

## Best Practices

1. **Regular Backups**: Back up `./data` directory daily (contains database and configs)
2. **Separate Storage**: Use external storage or NAS for `./backups` directory
3. **Monitor Disk Space**: Set up alerts when disk usage exceeds 80%
4. **Test Restores**: Regularly test backup restoration procedures
5. **Secure SSH Keys**: Keep offline backup of SSH private keys
6. **Log Rotation**: Implement log cleanup to prevent disk fill
7. **Repository Maintenance**: Run `borgmatic compact` monthly to reclaim space
8. **Version Control**: Keep `docker-compose.yml` in git, exclude `data/` and `backups/`

## Security Considerations

1. **SSH Keys**: Directory has `700` permissions (owner only)
2. **Database**: Contains password hashes, keep backups secure
3. **Configurations**: May contain repository passwords/passphrases
4. **File Permissions**: Never use `777`, use `755` for directories, `644` for files
5. **Backups**: Encrypt backups of `./data` if storing offsite

## Troubleshooting

### Check Container Logs

```bash
docker-compose logs app
docker-compose logs app --tail 100 -f
```

### Verify Volume Mounts

```bash
docker inspect borg-ui-app-1 | grep -A 10 Mounts
```

### Test Database Connection

```bash
docker-compose exec app sqlite3 /data/borgmatic.db "SELECT * FROM users;"
```

### Check Permissions

```bash
docker-compose exec app ls -lah /data
docker-compose exec app stat /data/ssh_keys
```

## Further Reading

- [Docker Volumes Documentation](https://docs.docker.com/storage/volumes/)
- [Docker Compose Volume Configuration](https://docs.docker.com/compose/compose-file/compose-file-v3/#volumes)
- [Borg Backup Documentation](https://borgbackup.readthedocs.io/)
- [Borgmatic Documentation](https://torsion.org/borgmatic/)
