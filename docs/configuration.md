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
| **DATABASE_URL** | SQLite at `/data/borg.db` (includes encrypted SSH keys) |
| **JOB_LOGS** | Stored in `/data/logs/` (backup_job_*.log, check_job_*.log, compact_job_*.log) |
| **SSH_KEYS_DIR** | `/data/ssh_keys` (used for temporary files during SSH operations) |

**Note:** Application logs (FastAPI, uvicorn) are sent to Docker logs (stdout/stderr). View with `docker logs borg-web-ui`.

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

**Note:** When `PUID=0` (running as root), SSH keys are symlinked from `/root/.ssh` to `/home/borg/.ssh` automatically.

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

### Proxy/OIDC Authentication

{: .new }
> **New Feature**: Integrate with external authentication providers (Authentik, Authelia, Keycloak, etc.)

Disable the built-in login screen and use your reverse proxy for authentication:

```yaml
environment:
  - DISABLE_AUTHENTICATION=true          # Disable built-in login screen
  - PROXY_AUTH_HEADER=X-Forwarded-User   # Header containing authenticated username (optional, default shown)
```

**How it works:**
- Borg UI reads the authenticated username from HTTP headers set by your reverse proxy
- Users are auto-created on first access
- New users are created as regular users (not admins)
- Admin must manually promote users to admin via Settings > User Management

**Supported authentication providers:**
- **Authentik** (header: `X-authentik-username`)
- **Authelia** (header: `X-Remote-User`)
- **Keycloak** (header: `X-Forwarded-User`)
- **Cloudflare Access** (header: `Cf-Access-Authenticated-User-Email`)
- **Google IAP** (header: `X-Goog-Authenticated-User-Email`)
- **Azure AD** (header: `X-MS-CLIENT-PRINCIPAL-NAME`)
- Any proxy that sets authentication headers

**Security Requirements:**

⚠️ **CRITICAL**: You MUST ensure Borg UI is only accessible through your authenticated proxy:

```yaml
ports:
  - "127.0.0.1:8081:8081"  # Only accessible via localhost
```

And block direct access with firewall rules:

```bash
sudo ufw deny 8081
sudo ufw allow from 127.0.0.1 to any port 8081
```

**Why:** If Borg UI is directly accessible, anyone can spoof the authentication header and gain access.

See [Security Guide - Proxy/OIDC Authentication](security.md#proxyoidc-authentication) for:
- Complete setup examples (Authentik, Authelia, Cloudflare Access, etc.)
- Security best practices
- Troubleshooting guide
- User management

### Reverse Proxy / BASE_PATH

{: .new }
> **New in vX.Y.Z**: BASE_PATH support for subfolder deployments

Run Borg Web UI in a subfolder behind a reverse proxy:

```yaml
environment:
  - BASE_PATH=/borg  # Access at example.com/borg/
```

**Important Notes:**
- Requires container rebuild: `docker-compose up -d --build`
- Must start with `/` and have no trailing slash
- Defaults to `/` (root path) if not set

**Examples:**
- `/borg` → Access at `example.com/borg/`
- `/backup-ui` → Access at `example.com/backup-ui/`
- `/` → Access at `example.com/` (default)

See [Reverse Proxy Setup](reverse-proxy.md) for complete configuration examples with Nginx, Traefik, Caddy, and Apache.

### File Browser Mount Points

{: .new }
> **New in vX.Y.Z**: LOCAL_MOUNT_POINTS for improved file browser navigation

Specify which container paths are host filesystem mounts to highlight them in the file browser:

```yaml
environment:
  - LOCAL_MOUNT_POINTS=/local  # Default
```

**What it does:**
- Highlights host filesystem mounts with a 💾 **HardDrive** icon and **"Host"** badge
- Makes it easy to identify where your actual data lives
- Similar to how SSH mount points are displayed with **"Remote"** badge

**Custom configurations:**

```yaml
# Single mount (default)
volumes:
  - /:/local:rw
environment:
  - LOCAL_MOUNT_POINTS=/local

# Multiple mounts (comma-separated)
volumes:
  - /home/john:/mylocalserver:rw
  - /mnt/nas:/nas:rw
environment:
  - LOCAL_MOUNT_POINTS=/mylocalserver,/nas

# No highlighting (empty string)
environment:
  - LOCAL_MOUNT_POINTS=
```

**In the file browser:**
- 💾 `/local` **[Host]** - Highlighted as host mount
- 🌐 `/mnt/ssh-connection` **[Remote]** - SSH mount point
- 📦 `/backups/repo1` **[Borg]** - Borg repository
- 📁 `/data` - Regular directory

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
- SQLite database (includes encrypted SSH keys)
- Job logs (backup, check, compact operations) in `/data/logs/`
- Auto-generated SECRET_KEY
- Temporary SSH key files during deployment/testing in `/data/ssh_keys/`

### Filesystem Access

**⚠️ Important Security Note**

The container needs access to directories you want to backup. **For production, mount only specific directories** you need:

```yaml
volumes:
  # ✅ Recommended: Mount specific directories
  - /home/yourusername:/local:rw      # Replace with your path
  - /mnt/data:/local/data:rw          # Additional directories

  # ❌ NOT Recommended: Full filesystem access
  # - /:/local:rw  # Development/testing only - avoid in production
```

**Why limit filesystem access?**
- Reduces security risk (principle of least privilege)
- Prevents accidental access to sensitive system files
- Makes it clear which directories are being backed up
- Easier to troubleshoot permission issues

### Mount Pattern Examples

**Personal Computer:**
```yaml
volumes:
  - borg_data:/data
  - borg_cache:/home/borg/.cache/borg
  - /home/john:/local:rw              # Mount home directory
```

**Server with Multiple Directories:**
```yaml
volumes:
  - borg_data:/data
  - borg_cache:/home/borg/.cache/borg
  - /var/www:/local/www:ro            # Website files (read-only)
  - /home/appuser:/local/app:rw       # Application data
  - /var/lib/postgresql:/local/db:rw  # Database directory
```

**NAS Backup (Unraid/TrueNAS):**
```yaml
volumes:
  - borg_data:/data
  - borg_cache:/home/borg/.cache/borg
  - /mnt/user/Documents:/local:ro     # Documents (read-only)
  - /mnt/user/Media:/local/media:ro   # Media files
  - /mnt/backup:/local/backup:rw      # Backup destination
```

**Best Practices:**
- Use simple `/local` mount for single directory
- Use `/local/subdir` pattern for multiple directories
- Use `:ro` (read-only) when you only need to backup, not restore
- Mount backup destinations as `:rw` if storing repositories locally

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

Borg Web UI supports both root domain and subfolder deployments behind reverse proxies.

**Quick Example (Nginx root domain):**

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

        # WebSocket/SSE support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

**For complete reverse proxy setup including:**
- Subfolder deployments (e.g., `example.com/borg/`)
- Nginx, Traefik, Caddy, Apache configurations
- SSL/HTTPS setup
- Docker network integration
- Troubleshooting

See the **[Reverse Proxy Setup Guide](reverse-proxy.md)**

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

{: .new }
> **New in vX.Y.Z**: Configurable operation timeouts for very large repositories

Increase Borg cache size by mounting to fast storage:

```yaml
volumes:
  - /path/to/ssd/borg-cache:/home/borg/.cache/borg
```

#### Operation Timeouts for Very Large Repositories

For repositories with:
- Multi-terabyte deduplicated size
- Hundreds of archives
- Long cache build times on first access

You can configure operation timeouts via **two methods**:

##### Method 1: Web UI (Recommended)

Go to **Settings → System** to configure timeouts with a user-friendly interface:

| Setting | Description | Default |
|---------|-------------|---------|
| Mount Timeout | Time to wait for archive mounts | 120s (2 min) |
| Info Timeout | Borg info operations (verification, stats) | 600s (10 min) |
| List Timeout | Listing archives and files | 600s (10 min) |
| Init Timeout | Creating new repositories | 300s (5 min) |
| Backup/Restore Timeout | Backup and restore operations | 3600s (1 hour) |

**Advantages of UI configuration:**
- No container restart required
- Changes take effect immediately
- Easier to adjust on-the-fly

##### Method 2: Environment Variables

Set timeouts via Docker environment variables:

```yaml
environment:
  # Borg operation timeouts (in seconds)
  - BORG_INFO_TIMEOUT=7200      # 2 hours for borg info (default: 600 = 10 min)
  - BORG_LIST_TIMEOUT=3600      # 1 hour for borg list (default: 600 = 10 min)
  - BORG_INIT_TIMEOUT=900       # 15 min for borg init (default: 300 = 5 min)
  - BORG_EXTRACT_TIMEOUT=7200   # 2 hours for restore (default: 3600 = 1 hour)
  - SCRIPT_TIMEOUT=300          # 5 min for hooks (default: 120 = 2 min)
```

##### Priority Order

The system checks settings in the following order:

| Priority | Source | Notes |
|----------|--------|-------|
| 1 (Highest) | UI Settings (Settings → System) | Stored in database, persists across restarts |
| 2 | Environment Variables | Used if no UI setting is configured |
| 3 | Built-in Defaults | Used if neither UI nor env vars are set |

**How it works:** If you set a timeout in the UI, that value is used. If you haven't configured a UI setting for a particular timeout, the environment variable is used. Both approaches are valid - use whichever fits your workflow better.

**Timeout Usage Reference:**

| Operation | When Used | Default | Recommended for Large Repos |
|-----------|-----------|---------|------------------------------|
| Mount | Mounting archives for browsing | 2 min | 5-10 min (10TB+ repos) |
| Info | Repository verification, stats, import | 10 min | 1-4 hours (based on cache build time) |
| List | Listing archives/files, restore browser | 10 min | 30-60 min |
| Init | Creating new repositories | 5 min | 10-15 min |
| Backup/Restore | Backup and restore operations | 1 hour | 2-4 hours |

**Example for very large repository (via UI):**
1. Go to **Settings → System**
2. Under "Operation Timeouts", set:
   - Mount Timeout: 600 (10 minutes)
   - Info Timeout: 7200 (2 hours)
   - List Timeout: 3600 (1 hour)
3. Click **Save Settings**

**Symptoms you need higher timeouts:**
- "Repository verification timed out" during import
- "Mount timeout" errors when browsing archives or using **Mount Archive** (Archives → Mount)
- Operations fail with timeout errors in logs
- Large operations (info/list) succeed when run manually but fail in UI

For **Mount Archive** specifically, see the [Mounting Archives](mounting) guide for how to mount and when to increase the Mount Timeout (e.g. for 10TB+ repositories).

### For Raspberry Pi / Low Memory

```yaml
environment:
  - WORKERS=1  # Reduce concurrent workers
```

---

## Redis Cache Configuration

{: .new }
> **New in vX.Y.Z**: Redis-based archive caching for 600x faster browsing

Borg Web UI includes Redis caching for dramatically faster archive browsing. Without cache, navigating folders in large archives (1M+ files) takes 60-90 seconds. With cache, it takes less than 100ms.

### Default Setup (Local Redis)

Redis is included in `docker-compose.yml` - no configuration needed.

```yaml
# Already configured in docker-compose.yml
redis:
  image: redis:7-alpine
  command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

**Manage via UI:**
- Go to **Settings → Cache** tab
- View statistics, configure TTL/size, clear cache
- Default: 2-hour TTL, 2GB size limit

### External Redis (For Large Repositories)

Connect to Redis on a separate machine with more RAM:

```yaml
# docker-compose.yml
services:
  app:
    environment:
      # External Redis URL (can also configure via Settings → Cache in UI)
      - REDIS_URL=redis://192.168.1.100:6379/0

      # Or with password
      # - REDIS_URL=redis://:password@192.168.1.100:6379/0

      # Or with Unix socket (when Redis and Borg UI are on same system)
      # - REDIS_URL=unix:///run/redis-socket/redis.sock?db=0&password=password

      # Cache settings
      - CACHE_TTL_SECONDS=7200    # 2 hours
      - CACHE_MAX_SIZE_MB=2048    # 2GB
```

**When to use external Redis:**
- Repositories with 5M+ files
- Multiple large archives
- Limited RAM on Borg Web UI host
- NAS/workstation with spare RAM available

**Full setup guide with examples:** [Cache Configuration](cache)

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
      - /home/yourusername:/local:rw  # Replace with your home directory
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
      - /var/www:/local/www:ro
      - /home/appuser:/local/app:ro

      # Backup destination
      - /mnt/backups:/local/backup:rw
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
      - /mnt/user/Documents:/local:ro         # Documents share
      - /mnt/user/Media:/local/media:ro       # Media share
      - /mnt/user/Backups:/local/backup:rw    # Backup destination
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

- [Cache Configuration](cache.md) - Set up external Redis for 600x faster browsing
- [Notifications Setup](notifications.md) - Configure alerts
- [SSH Keys Guide](ssh-keys.md) - Set up remote backups
- [Usage Guide](usage-guide.md) - Create your first backup
