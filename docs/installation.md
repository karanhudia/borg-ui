---
layout: default
title: Installation
nav_order: 2
description: "How to install Borg Web UI on various platforms"
---

# Installation Guide

Borg Web UI runs as a Docker container. Choose your setup below, configure your volume mounts, and run `docker compose up -d`.

---

## Docker Compose (Recommended)

Pick one of the three options below, create `docker-compose.yml`, and run `docker compose up -d`.

> **`/local`** is where borg-ui reads files to back up — mount your existing data directories here.
> **Backup repositories** (where borg actually stores backups) are configured in the UI after setup.

---

### Option 1 — No Redis (Simple)

Good for occasional use. Uses in-memory caching.

```yaml
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
      - /path/to/your/data:/local:rw   # replace with the directory you want to back up
    environment:
      - TZ=America/Chicago             # replace with your timezone
      - PUID=1000                      # replace with your user ID: run `id -u`
      - PGID=1000                      # replace with your group ID: run `id -g`

volumes:
  borg_data:
  borg_cache:
```

---

### Option 2 — With Redis (Recommended)

Redis speeds up archive browsing ~600x. Recommended if you browse archives regularly.

```yaml
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
      - /path/to/your/data:/local:rw   # replace with the directory you want to back up
    environment:
      - TZ=America/Chicago             # replace with your timezone
      - PUID=1000                      # replace with your user ID: run `id -u`
      - PGID=1000                      # replace with your group ID: run `id -g`
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - borg_network

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

---

### Option 3 — External Redis

If you want Redis on a separate machine or Docker stack. Run the Redis compose on the Redis machine, and the borg-ui compose on the borg-ui machine.

**On the Redis machine** — `docker-compose.redis.yml`:

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: borg-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
```

**On the borg-ui machine** — `docker-compose.yml`:

```yaml
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
      - /path/to/your/data:/local:rw   # replace with the directory you want to back up
    environment:
      - TZ=America/Chicago             # replace with your timezone
      - PUID=1000                      # replace with your user ID: run `id -u`
      - PGID=1000                      # replace with your group ID: run `id -g`
      - REDIS_URL=redis://192.168.1.100:6379/0   # replace with your Redis machine's IP
      # With password:
      # - REDIS_URL=redis://:your-password@192.168.1.100:6379/0

volumes:
  borg_data:
  borg_cache:
```

---

**Mount multiple directories** — you can add as many volume entries as you need:

```yaml
volumes:
  - /home/john:/local:rw
  - /var/www:/local/www:ro
  - /mnt/photos:/local/photos:rw
```

**Permission errors?** Run `id -u && id -g` on your host to find the right `PUID`/`PGID`.

---

## Portainer

1. **Stacks** > **Add Stack**
2. Name: `borg-ui`
3. Paste one of the Docker Compose configurations above (with your directories and timezone filled in)
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
      - /mnt/user:/local:rw  # or mount specific shares
    environment:
      - TZ=America/Chicago   # replace with your timezone
      - PUID=99
      - PGID=100
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - borg_network

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
  -v /path/to/your/data:/local:rw \
  ainullcode/borg-ui:latest
```

Replace `/path/to/your/data` with the directory you want to back up (e.g. `/home/john` or `/mnt/photos`).

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
