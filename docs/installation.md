---
title: Installation
nav_order: 2
description: "Install Borg UI with Docker"
---

# Installation

Borg UI is distributed as a Docker image.

Use Docker Compose unless you only need a quick local test. The recommended Compose example gives you persistent app data, Borg cache, Redis, and clear volume mappings.

## Recommended Docker Compose

Create `docker-compose.yml`:

```yaml
services:
  app:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "${PORT:-8081}:${PORT:-8081}"
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /etc/localtime:/etc/localtime:ro
      - ${LOCAL_STORAGE_PATH:-/home/youruser}:/local:rw
    environment:
      - PORT=${PORT:-8081}
      - PUID=${PUID:-1001}
      - PGID=${PGID:-1001}
      - TZ=${TZ:-UTC}
      - LOCAL_MOUNT_POINTS=${LOCAL_MOUNT_POINTS:-/local}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=0
    depends_on:
      redis:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    container_name: borg-redis
    restart: unless-stopped
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save ""
      --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

volumes:
  borg_data:
  borg_cache:
```

Start it:

```bash
docker compose up -d
```

Open:

```text
http://localhost:8081
```

Default login:

```text
username: admin
password: admin123
```

Change the password immediately after first login. You can set a different first password with `INITIAL_ADMIN_PASSWORD`.

## Install Without Redis

Redis is optional. If you do not want to run Redis, remove the `redis` service and `depends_on` block from the Compose file, then add this environment variable to the app service:

```yaml
environment:
  - REDIS_HOST=disabled
```

With Redis disabled, Borg UI uses in-memory archive browsing cache. Backups and restores still work. Repeated archive browsing can be slower, and the cache is lost when the app restarts.

## Pick the Right Host Path

The `LOCAL_STORAGE_PATH` host path is mounted into the container at `/local`.

Example:

```yaml
volumes:
  - /mnt/usb-drive:/local:rw
```

Then this host path:

```text
/mnt/usb-drive/borg-backups/laptop
```

is this container path in Borg UI:

```text
/local/borg-backups/laptop
```

Do not add the host prefix again inside the UI.

## Permissions

Set `PUID` and `PGID` to the host user that should own restored files and write backup repositories.

Find them with:

```bash
id -u
id -g
```

Example `.env`:

```bash
PORT=8081
PUID=1000
PGID=1000
LOCAL_STORAGE_PATH=/mnt/usb-drive
TZ=America/Chicago
```

## Redis

Redis is used as an archive-browsing cache. It is not required for backups or restores.

The Compose example uses Redis without disk persistence:

```text
--save ""
--appendonly no
```

That means cached archive listings survive app container restarts while Redis keeps running, but they do not survive a Redis container restart. This is fine because Borg UI can rebuild the cache.

Set `REDIS_HOST=disabled` when you intentionally run without Redis. Otherwise the app tries the configured Redis host first and falls back to in-memory cache if it cannot connect.

## Optional Docker Socket

Only mount the Docker socket if you use script hooks to stop or start containers during backups:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

This grants powerful host access to the Borg UI container. See [Docker Hooks](docker-hooks).

## Optional Archive Mounting

Archive mounting requires FUSE access:

```yaml
cap_add:
  - SYS_ADMIN
devices:
  - /dev/fuse:/dev/fuse
security_opt:
  - apparmor:unconfined
```

Add this only if you need `borg mount` support. See [Mounting Archives](mounting).

## Docker Run

For a quick test:

```bash
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/youruser:/local:rw \
  ainullcode/borg-ui:latest
```

This does not include Redis. Use Compose for normal deployments.

## Upgrade

```bash
docker compose pull
docker compose up -d
```

Do not delete `borg_data` or `borg_cache` unless you intentionally want to remove application state or Borg cache data.

## Next

- [Usage Guide](usage-guide)
- [Configuration](configuration)
- [Security](security)
