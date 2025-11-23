---
layout: default
title: Configuration
nav_order: 3
description: "Environment variables, volumes, and settings"
---

# Configuration Guide

Customize Borg Web UI for your environment.

---

## Auto-Configured Settings

These are automatically set up on first run - no configuration needed:

| Setting | Auto-Configuration |
|---------|-------------------|
| **SECRET_KEY** | Randomly generated (32 bytes), persisted to `/data/.secret_key` |
| **DATABASE_URL** | SQLite at `/data/borg_web_ui.db` |
| **LOG_FILE** | `/data/logs/borg-ui.log` |
| **SSH_KEYS_DIR** | `/data/ssh_keys` |

---

## Environment Variables

### Port Configuration

```yaml
environment:
  - PORT=8082  # Default: 8081
```

Access at `http://localhost:8082`

### User/Group IDs

Match your host user for proper permissions:

```yaml
environment:
  - PUID=1000  # Your user ID
  - PGID=1000  # Your group ID
```

Find your IDs:
```bash
id -u  # User ID
id -g  # Group ID
```

**Common IDs:**
- Linux/Raspberry Pi: `1000:1000`
- Unraid: `99:100`
- macOS: `501:20`

### Logging

```yaml
environment:
  - LOG_LEVEL=DEBUG  # Default: INFO
  # Options: DEBUG, INFO, WARNING, ERROR
```

### Initial Admin Password

Set a custom admin password on first run:

```yaml
environment:
  - INITIAL_ADMIN_PASSWORD=your-secure-password
```

**Note:** If not set, defaults to `admin123`. You'll be prompted to change it on first login.

---

## Volume Mounts

### Application Data

**Required volumes:**

```yaml
volumes:
  - borg_data:/data                       # Application data
  - borg_cache:/home/borg/.cache/borg    # Borg cache
```

**What's stored in `/data`:**
- SQLite database
- SSH keys
- Application logs
- Auto-generated SECRET_KEY
- User settings

### Filesystem Access

**Default configuration:**

```yaml
volumes:
  - /:/local:rw  # Mount entire host filesystem
```

**Why mount the host filesystem?**
- Access backup sources anywhere on the system
- Store backup repositories locally
- Maximum flexibility for backup operations

**Security consideration:** The default mounts your entire filesystem. For production, restrict access to specific directories.

### Restricted Access (Recommended for Production)

Mount only the directories you need:

```yaml
volumes:
  # Backup sources (read-only)
  - /home/user/documents:/sources/documents:ro
  - /home/user/photos:/sources/photos:ro

  # Backup destinations (read-write)
  - /mnt/backup-drive:/backups:rw

  # Required application volumes
  - borg_data:/data
  - borg_cache:/home/borg/.cache/borg
```

**Example for NAS backup:**

```yaml
volumes:
  # Source data
  - /mnt/user/Documents:/sources/documents:ro
  - /mnt/user/Media:/sources/media:ro

  # Backup repository location
  - /mnt/user/Backups:/backups:rw

  # Application data
  - borg_data:/data
  - borg_cache:/home/borg/.cache/borg
```

---

## Custom Volume Locations

Store application data in a specific location:

```yaml
volumes:
  borg_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/storage/borg-data

  borg_cache:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/storage/borg-cache
```

---

## Repository Configuration

**Important:** Repositories are configured through the web UI, not Docker volumes.

Supported repository types:
- **Local paths**: `/local/backups/my-repo`, `/backups/my-repo`
- **SSH/SFTP**: `user@host:/path/to/repo`
- **Cloud storage**: Via rclone (S3, Azure, Google Cloud)

No need for a separate `borg_backups` volume!

---

## Network Configuration

### Using a Reverse Proxy

**Nginx example:**

```nginx
server {
    listen 80;
    server_name backups.example.com;

    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Traefik example:**

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.borg-ui.rule=Host(`backups.example.com`)"
      - "traefik.http.routers.borg-ui.entrypoints=websecure"
      - "traefik.http.routers.borg-ui.tls.certresolver=letsencrypt"
      - "traefik.http.services.borg-ui.loadbalancer.server.port=8081"
```

### Custom Network

```yaml
networks:
  borg-network:
    driver: bridge

services:
  borg-ui:
    networks:
      - borg-network
```

---

## Performance Tuning

### For Large Repositories

Increase Borg cache size by mounting to fast storage:

```yaml
volumes:
  - /path/to/ssd/borg-cache:/home/borg/.cache/borg
```

### For Raspberry Pi / Low Memory

```yaml
environment:
  - WORKERS=1  # Reduce concurrent workers
```

---

## Security Configuration

### Change SECRET_KEY

The SECRET_KEY is auto-generated on first run. To rotate it:

```bash
docker exec borg-web-ui rm /data/.secret_key
docker restart borg-web-ui
```

**Note:** This invalidates all user sessions.

### Enable HTTPS

Use a reverse proxy (Nginx, Traefik, Caddy) with Let's Encrypt certificates.

**Never expose the application directly to the internet without HTTPS.**

### Restrict Access

**Using firewall:**
```bash
# Allow only from local network
sudo ufw allow from 192.168.1.0/24 to any port 8081
```

**Using Docker:**
```yaml
ports:
  - "127.0.0.1:8081:8081"  # Only accessible from localhost
```

Then access via reverse proxy or SSH tunnel.

---

## Backup Configuration Data

### Backup Application Data

```bash
# Backup borg_data volume
docker run --rm \
  -v borg_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/borg-data-backup.tar.gz -C /data .
```

### Restore Application Data

```bash
# Restore borg_data volume
docker run --rm \
  -v borg_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/borg-data-backup.tar.gz -C /data
```

---

## Example Configurations

### Basic Home Setup

```yaml
version: '3.8'

services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /home:/local:rw
    environment:
      - PUID=1000
      - PGID=1000

volumes:
  borg_data:
  borg_cache:
```

### Production Setup with Restricted Access

```yaml
version: '3.8'

services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "127.0.0.1:8081:8081"  # Only localhost
    volumes:
      # Application data
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg

      # Backup sources (read-only)
      - /var/www:/sources/www:ro
      - /home/user:/sources/home:ro

      # Backup destination
      - /mnt/backups:/backups:rw
    environment:
      - PUID=1000
      - PGID=1000
      - LOG_LEVEL=INFO
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.borg-ui.rule=Host(`backups.example.com`)"
      - "traefik.http.routers.borg-ui.tls=true"

volumes:
  borg_data:
  borg_cache:
```

### NAS Setup (Unraid/TrueNAS)

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - /mnt/user/appdata/borg-ui:/data
      - /mnt/user/appdata/borg-ui/cache:/home/borg/.cache/borg
      - /mnt/user/Documents:/sources/documents:ro
      - /mnt/user/Media:/sources/media:ro
      - /mnt/user/Backups:/backups:rw
    environment:
      - PUID=99
      - PGID=100
```

---

## Troubleshooting

### Database Locked Error

If multiple containers are using the same database:

```bash
# Stop all containers
docker stop borg-web-ui

# Check for locks
docker exec borg-web-ui ls -la /data/

# Restart
docker start borg-web-ui
```

### Permission Issues

Verify PUID/PGID match your host user:

```bash
# Check file ownership
docker exec borg-web-ui ls -la /data/

# Check container user
docker exec borg-web-ui id

# Fix ownership if needed
docker exec borg-web-ui chown -R borg:borg /data
```

### High Memory Usage

Reduce Borg cache or move to disk-based cache:

```yaml
volumes:
  - /path/to/slower/storage:/home/borg/.cache/borg
```

---

## Next Steps

- [Notifications Setup](notifications.md) - Configure alerts
- [SSH Keys Guide](ssh-keys.md) - Set up remote backups
- [Usage Guide](usage-guide.md) - Create your first backup
