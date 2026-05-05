---
title: Installation
nav_order: 2
description: "Install Borg UI with Docker"
---

# Installation

Borg UI is distributed as a Docker image.

Use Docker Compose unless you only need a quick local test.

Pick one Compose workflow:

- [No Redis](#option-1-no-redis-simple): simplest setup. Uses in-memory archive cache.
- [With Redis](#option-2-with-redis-recommended): recommended for normal installs.
- [External Redis](#option-3-external-redis): use Redis from another host, stack, or managed service.

For Portainer or Unraid, use the same settings and see the platform notes below.

## Option 1: No Redis (Simple)

Use this for small installs or occasional archive browsing. Backups and restores work normally. Archive browsing cache is kept in memory and is lost when the app restarts.

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
      - REDIS_HOST=disabled

volumes:
  borg_data:
  borg_cache:
```

## Option 2: With Redis (Recommended)

Use this for normal deployments. Redis makes repeated archive browsing faster and keeps cache across app container restarts.

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

## Option 3: External Redis

Use this when Redis already runs somewhere else.

Create `docker-compose.yml` on the Borg UI host:

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
      - REDIS_URL=redis://redis.example.com:6379/0
      - REDIS_HOST=disabled

volumes:
  borg_data:
  borg_cache:
```

Replace `redis.example.com` with your Redis host.

Examples:

```text
redis://redis.example.com:6379/0
redis://:password@redis.example.com:6379/0
rediss://:password@redis.example.com:6379/0
unix:///run/redis/redis.sock?db=0
unix:///run/redis/redis.sock?db=0&password=password
```

`REDIS_URL` takes precedence over `REDIS_HOST`. Keeping `REDIS_HOST=disabled` prevents Borg UI from trying `localhost:6379` if the external URL is unavailable.

For `unix://` Redis URLs, mount the Redis socket into the Borg UI container at the same path used in `REDIS_URL`.

If you need to create the external Redis instance too, run Redis on that host with a small Compose file:

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: borg-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
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
```

Only expose Redis to trusted networks. If Redis is reachable across a network, use firewall rules, a private network, or Redis authentication.

## Start Borg UI

From the directory containing `docker-compose.yml`:

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

## Portainer

In Portainer, create a Stack and paste one of the Compose files above.

Use real host paths for volumes. Paths are evaluated on the Docker host, not on your laptop or browser session.

Recommended checks before deploying:

- keep `/data` persistent with `borg_data` or a host bind mount
- set `PUID` and `PGID` for the host user that should own restored files
- set `LOCAL_STORAGE_PATH` to the host path that contains repositories or backup sources
- keep `LOCAL_MOUNT_POINTS=/local` unless you change the container mount path
- use the Redis Compose option, external Redis, or `REDIS_HOST=disabled`

If you mount the Docker socket for hooks, remember that the container may still need the Docker CLI installed. See [Docker Hooks](docker-hooks).

## Unraid

On Unraid, use either the Docker Compose Manager plugin or the Docker web UI.

Recommended defaults:

```text
PUID=99
PGID=100
TZ=<your timezone>
```

Common path mapping:

```text
/mnt/user/appdata/borg-ui -> /data
/mnt/user/appdata/borg-ui/cache -> /home/borg/.cache/borg
/mnt/user/backups -> /local
```

Then use `/local/...` paths inside Borg UI.

Set `LOCAL_MOUNT_POINTS=/local` unless you use a different container path.

For Redis, use the Compose Redis option, an existing Redis container, an external Redis URL, or `REDIS_HOST=disabled`.

If you use the Docker web UI instead of Compose, add the same container paths and environment variables manually. Make sure `/data` points to persistent appdata storage.

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

## Optional FUSE Access

Archive mounting uses `borg mount` and requires FUSE access.

Remote source backups and SSH restore destinations use SSHFS and also require FUSE access.

```yaml
cap_add:
  - SYS_ADMIN
devices:
  - /dev/fuse:/dev/fuse
security_opt:
  - apparmor:unconfined
environment:
  - BORG_FUSE_IMPL=pyfuse3
```

Add this only if you need archive mounts, SSHFS remote source backups, or SSH restore destinations. See [Mounting Archives](mounting).

## Docker Run

For a quick test:

```bash
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -e REDIS_HOST=disabled \
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
