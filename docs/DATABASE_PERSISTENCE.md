# Database Persistence Guide

## Overview

Borg UI uses **SQLite** as its database. The database file is stored **outside the container** on your host machine, ensuring data persists across container rebuilds, updates, and restarts.

---

## How It Works

### Database Location

**Inside Container:**
```
/app/data/borg.db
```

**On Host Machine:**
```
./data/borg.db
```

### Docker Volume Mount

The `docker-compose.yml` file mounts the host directory to the container:

```yaml
volumes:
  - ./data:/app/data:rw
```

This means:
- ✅ Database survives container deletion
- ✅ Database survives container rebuilds
- ✅ Database survives image updates
- ✅ You can backup the database file directly
- ✅ You can restore by replacing the file

---

## Configuration

### Database URL

In `.env` or `docker-compose.yml`:

```bash
DATABASE_URL=sqlite:////app/data/borg.db
```

**Note the 4 slashes:** `sqlite:////`
- `sqlite://` = SQLite protocol
- `//` = Absolute path follows
- `/app/data/borg.db` = Full path in container

---

## Verifying Persistence

### Test 1: Check Database File Exists

```bash
# On your host machine
ls -lh ./data/borg.db

# Should show something like:
# -rw-r--r--  1 user  staff   256K Jan 14 10:30 ./data/borg.db
```

### Test 2: Create Test Data

```bash
# 1. Start the application
docker-compose up -d

# 2. Login and create some data (user, SSH key, repository, etc.)

# 3. Stop the container
docker-compose down

# 4. Check database file still exists
ls -lh ./data/borg.db

# 5. Restart the container
docker-compose up -d

# 6. Login - your data should still be there!
```

### Test 3: Rebuild Container

```bash
# 1. Make sure you have data in the application

# 2. Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 3. Login - your data should still be there!
```

---

## Backing Up the Database

### Manual Backup

```bash
# Stop the application first (recommended)
docker-compose down

# Copy the database file
cp ./data/borg.db ./data/borg-backup-$(date +%Y%m%d).db

# Or create a compressed backup
tar -czf borg-backup-$(date +%Y%m%d).tar.gz ./data/

# Restart
docker-compose up -d
```

### Automated Backup Script

Create `backup-db.sh`:

```bash
#!/bin/bash
BACKUP_DIR="./backups/db"
mkdir -p "$BACKUP_DIR"

# Create backup with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp ./data/borg.db "$BACKUP_DIR/borg-$TIMESTAMP.db"

# Keep only last 7 days of backups
find "$BACKUP_DIR" -name "borg-*.db" -mtime +7 -delete

echo "✅ Database backed up to: $BACKUP_DIR/borg-$TIMESTAMP.db"
```

Run it:
```bash
chmod +x backup-db.sh
./backup-db.sh
```

### Backup with Cron

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd /path/to/borg-ui && ./backup-db.sh
```

---

## Restoring the Database

### From Backup

```bash
# 1. Stop the application
docker-compose down

# 2. Replace the database file
cp ./data/borg-backup-20250114.db ./data/borg.db

# 3. Restart
docker-compose up -d
```

### From Another Server

```bash
# 1. Copy database from old server
scp user@old-server:/path/to/borg-ui/data/borg.db ./data/

# 2. Start the application
docker-compose up -d
```

---

## Troubleshooting

### Database File Not Found

If you see errors about missing database:

```bash
# Check if data directory exists
ls -la ./data/

# If it doesn't exist, create it
mkdir -p ./data
chmod 755 ./data

# Restart container
docker-compose restart
```

The application will automatically create a new database file on first run.

### Database Locked Error

If you see "database is locked":

```bash
# Check if multiple processes are accessing the database
docker-compose ps

# Stop all containers
docker-compose down

# Check for lingering processes
ps aux | grep borg

# Restart
docker-compose up -d
```

### Permissions Issues

If you get permission denied errors:

```bash
# Fix ownership (run on host)
sudo chown -R $USER:$USER ./data/

# Fix permissions
chmod 644 ./data/borg.db
chmod 755 ./data/
```

### Database Corrupted

If database becomes corrupted:

```bash
# 1. Stop the application
docker-compose down

# 2. Check integrity
sqlite3 ./data/borg.db "PRAGMA integrity_check;"

# If corrupted, restore from backup
cp ./data/borg-backup-YYYYMMDD.db ./data/borg.db

# Or start fresh (⚠️ loses all data!)
rm ./data/borg.db

# 3. Restart
docker-compose up -d
```

---

## Migrating to New Machine

### Export Data

On old machine:

```bash
# 1. Stop the application
docker-compose down

# 2. Create archive
tar -czf borg-data-export.tar.gz \
  ./data/ \
  ./config/ \
  ./backups/ \
  .env

# 3. Transfer to new machine
scp borg-data-export.tar.gz user@new-machine:/path/to/destination/
```

### Import Data

On new machine:

```bash
# 1. Clone repository
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui

# 2. Extract backup
tar -xzf /path/to/borg-data-export.tar.gz

# 3. Start the application
docker-compose up -d
```

---

## Why SQLite?

**Advantages:**
- ✅ **Zero Configuration** - No database server needed
- ✅ **File-Based** - Easy backup (just copy one file)
- ✅ **Lightweight** - Low memory footprint (~1-2MB)
- ✅ **Fast** - Great for single-server deployments
- ✅ **Reliable** - Used by millions of applications
- ✅ **Simple** - No database credentials to manage

**Perfect For:**
- Single-server deployments (99% of use cases)
- Home labs and personal use
- Small to medium businesses
- Up to 100s of backup jobs
- Up to 1000s of archives

**When to Consider PostgreSQL:**
- Multiple application instances (load balancing)
- Very high concurrent users (100+)
- Need for complex queries and reporting
- Enterprise deployments with HA requirements

---

## Database Size Management

### Check Database Size

```bash
# On host
du -h ./data/borg.db

# Or inside container
docker exec borg-web-ui du -h /app/data/borg.db
```

### Vacuum Database (Optimize)

SQLite can accumulate free space. Vacuum to reclaim it:

```bash
# Stop application first
docker-compose down

# Vacuum the database
sqlite3 ./data/borg.db "VACUUM;"

# Restart
docker-compose up -d
```

### Typical Sizes

| Archives | Jobs | Size |
|----------|------|------|
| 10 | 5 | ~100 KB |
| 100 | 20 | ~1 MB |
| 1000 | 50 | ~10 MB |
| 10000 | 100 | ~100 MB |

---

## Summary

✅ **Database persists automatically** - stored in `./data/borg.db`
✅ **Survives container rebuilds** - volume mounted to host
✅ **Easy to backup** - just copy one file
✅ **Simple to migrate** - transfer data directory
✅ **Zero configuration** - works out of the box

**No action needed - it just works!** 🎉
