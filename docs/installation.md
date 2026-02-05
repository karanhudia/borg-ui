---
layout: default
title: Installation
nav_order: 2
description: "How to install Borg Web UI on various platforms"
---

# Installation Guide

Choose your platform and copy-paste the configuration. Access at `http://localhost:8081` with credentials: `admin` / `admin123`

---

## Docker Compose (Recommended)

Create `docker-compose.yml` and run `docker compose up -d`:

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
      - /mnt/backup-source:/local:rw
    environment:
      - TZ=America/Chicago
      - PUID=1000
      - PGID=1000
    # Optional: Remove these 3 lines if you don't want Redis
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - borg_network

  # Optional: Redis speeds up archive browsing 600x
  # Remove this entire section if you don't need it
  redis:
    image: redis:7-alpine
    container_name: borg-redis
    restart: unless-stopped
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    networks:
      - borg_network

networks:
  borg_network:

volumes:
  borg_data:
  borg_cache:
```

**First time setup:** Create the backup source directory:
```bash
sudo mkdir -p /mnt/backup-source
sudo chown -R 1000:1000 /mnt/backup-source
```

---

## Portainer

1. **Stacks** > **Add Stack**
2. Name: `borg-ui`
3. Paste the Docker Compose configuration above
4. **Deploy the stack**
5. Access: `http://your-server-ip:8081`

---

## Unraid

### Option 1: Docker Compose Manager

1. Install **Compose Manager** plugin
2. **Docker** > **Compose** > **Add New Stack**
3. Name: `borg-ui`
4. Paste:

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
      - /mnt/user/appdata/borg-ui:/data
      - /mnt/user/appdata/borg-ui/cache:/home/borg/.cache/borg
      - /mnt/user:/local:rw  # Customize to specific shares if needed
    environment:
      - TZ=America/Chicago
      - PUID=99
      - PGID=100
    # Optional: Remove these 3 lines if you don't want Redis
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - borg_network

  # Optional: Redis speeds up archive browsing 600x
  # Remove this entire section if you don't need it
  redis:
    image: redis:7-alpine
    container_name: borg-redis
    restart: unless-stopped
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    networks:
      - borg_network

networks:
  borg_network:
```

5. **Compose Up**

### Option 2: Unraid Web UI

**Docker** tab > **Add Container**:

| Setting | Value |
|---------|-------|
| Name | `borg-web-ui` |
| Repository | `ainullcode/borg-ui:latest` |
| Network Type | `Bridge` |

**Port Mappings:**
- `8081` → `8081`

**Volume Mappings:**
| Container Path | Host Path |
|----------------|-----------|
| `/data` | `/mnt/user/appdata/borg-ui` |
| `/home/borg/.cache/borg` | `/mnt/user/appdata/borg-ui/cache` |
| `/local` | `/mnt/user` |

**Environment:**
- `TZ` = `America/Chicago`
- `PUID` = `99`
- `PGID` = `100`

Click **Apply**

---

## Docker Run (Single Command)

```bash
docker run -d \
  --name borg-web-ui \
  --restart unless-stopped \
  -p 8081:8081 \
  -e TZ=America/Chicago \
  -e PUID=1000 \
  -e PGID=1000 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /mnt/backup-source:/local:rw \
  ainullcode/borg-ui:latest
```

**First time setup:**
```bash
sudo mkdir -p /mnt/backup-source
sudo chown -R 1000:1000 /mnt/backup-source
```

---

## Post-Installation

**1. Login:**
Visit `http://localhost:8081` → Username: `admin` / Password: `admin123`

**2. Change Password:**
You'll be prompted on first login

**3. Create Your First Backup:**
See [Usage Guide](usage-guide.md)

---

## Customization

### Mount Your Directories

Replace `/mnt/backup-source` with your actual directories:

```yaml
volumes:
  - /home/john:/local:rw
  - /var/www:/local/www:ro
  - /mnt/photos:/local/photos:rw
```

### Change Timezone

Find yours at [timezones list](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones):

```yaml
environment:
  - TZ=Europe/London  # or America/New_York, Asia/Tokyo, etc.
```

### Change Port

```yaml
ports:
  - "8082:8081"  # Access on port 8082
```

### Fix Permission Errors

```bash
id -u && id -g  # Shows your user/group IDs
```

Update environment with your IDs:
```yaml
environment:
  - PUID=1000
  - PGID=1000
```

### Connect to External Redis

If Redis is in a separate Docker stack or external server, use `REDIS_URL`:

```yaml
environment:
  - REDIS_URL=redis://192.168.1.100:6379/0

  # With password:
  - REDIS_URL=redis://:your-password@192.168.1.100:6379/0
```

---

## Updating

**Docker Compose:**
```bash
docker compose pull && docker compose up -d
```

**Docker Run:**
```bash
docker pull ainullcode/borg-ui:latest
docker stop borg-web-ui && docker rm borg-web-ui
# Run the docker run command again
```

**Portainer:**
Stacks → Select `borg-ui` → Pull and redeploy

---

## Troubleshooting

**Container won't start:**
```bash
docker logs borg-web-ui
```

**Port already in use:**
```yaml
ports:
  - "8082:8081"
```

**Permission errors:**
```bash
id -u && id -g  # Find your user/group IDs
```
Update `PUID` and `PGID` in environment

**Can't access web interface:**
```bash
sudo ufw allow 8081
docker ps | grep borg-web-ui
```

**Wrong timestamps:**
```yaml
environment:
  - TZ=Your/Timezone
```
Then: `docker compose down && docker compose up -d`

---

## Advanced (Optional)

**Redis (already included):** Speeds up archive browsing 600x. See [Cache Configuration](cache) for tuning or removal

**Remote SSH backups:** See [SSH Remote Mounting Guide](mounting)

**Manage Docker containers during backups:** See [Docker Hooks Guide](docker-hooks)

---

## Uninstall

**Remove container:**
```bash
docker compose down
```

**Remove all data (warning: deletes backups):**
```bash
docker volume rm borg_data borg_cache
```

---

## Next Steps

- [Usage Guide](usage-guide.md) - Create your first backup
- [Notifications Setup](notifications.md) - Email, Slack, Discord alerts
- [Configuration Guide](configuration.md) - Advanced settings
