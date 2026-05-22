---
title: Cache
nav_order: 7
description: "Redis and archive browsing cache behavior"
---

# Cache

Borg UI uses caching to make repeated archive browsing faster.

The first browse of a large archive can still be slow because Borg has to list archive contents. After that, cached results can be served much faster.

There are two separate caches involved in normal Docker deployments:

- Borg UI archive cache: Redis or the in-memory fallback used by archive browsing.
- Borg files cache: Borg's own cache under `/home/borg/.cache/borg`, used by `borg create` to avoid reprocessing unchanged files during backups.

Redis does not make backup creation faster. If backup jobs are slow after a container pull or restart, troubleshoot the Borg files cache and source mounts first.

## Backends

Borg UI supports:

- Redis cache
- in-memory fallback cache

Redis is recommended for normal Docker Compose deployments. In-memory cache works, but it is lost whenever the app restarts.

To intentionally run without Redis, set `REDIS_HOST=disabled`. Borg UI will use in-memory cache and will not try to connect to `localhost:6379`.

## Default Compose Behavior

The recommended Compose setup includes Redis:

```yaml
redis:
  image: redis:7-alpine
  command: >
    redis-server
    --maxmemory 2gb
    --maxmemory-policy allkeys-lru
    --save ""
    --appendonly no
```

This Redis cache does not persist to disk. It survives app container restarts if the Redis container keeps running, but it does not survive a Redis container restart.

That is acceptable because cached archive listings can be rebuilt.

## Settings

Open Settings > System > Cache to configure:

- Redis URL
- cache TTL
- max cache size
- clear cache
- refresh repository stats

Valid UI ranges:

| Setting | Range |
| --- | --- |
| TTL | 1 to 10080 minutes |
| Max size | 100 to 10240 MB |

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | empty | Full Redis URL. Takes precedence |
| `REDIS_HOST` | `localhost` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis DB |
| `REDIS_PASSWORD` | empty | Redis password |
| `CACHE_TTL_SECONDS` | `7200` | Initial TTL default |
| `CACHE_MAX_SIZE_MB` | `2048` | Initial max cache size |

`REDIS_URL` accepts `redis://`, `rediss://`, and `unix://` URLs.

Set `REDIS_HOST=disabled` to force in-memory cache.

Runtime connection priority:

1. saved Redis URL from Settings > System > Cache, when present
2. `REDIS_URL`
3. `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB`
4. in-memory fallback

Environment variables set startup defaults. Cache settings in the UI update the running service; keep important deployment defaults in Compose or `.env`.

## External Redis

Example:

```yaml
environment:
  - REDIS_URL=redis://redis.example.com:6379/0
```

With password:

```yaml
environment:
  - REDIS_URL=redis://:password@redis.example.com:6379/0
```

With TLS:

```yaml
environment:
  - REDIS_URL=rediss://:password@redis.example.com:6379/0
```

With a Unix socket:

```yaml
environment:
  - REDIS_URL=unix:///run/redis/redis.sock?db=0
```

With a Unix socket and password:

```yaml
environment:
  - REDIS_URL=unix:///run/redis/redis.sock?db=0&password=password
```

For `unix://` URLs, mount the Redis socket into the Borg UI container at the same path used in `REDIS_URL`.

## When to Clear Cache

Clear cache when:

- archive listings look stale
- Redis memory usage is too high
- you changed Redis connection settings
- you are debugging archive browsing

Clearing cache does not delete Borg archives.

## Troubleshooting

### Redis unavailable

Borg UI falls back to in-memory cache. Archive browsing still works, but first loads are slower and cache is lost on app restart.

### Cache does not survive restart

Check which container restarted. The default Redis setup has no disk persistence.

### Slow first browse

Expected for very large archives. Cache helps repeated browsing; it does not remove the initial Borg listing cost.

### Slow first backup after a pull or restart

`docker compose pull` does not remove Docker volumes or bind mounts by itself. A backup that is slow only for the first run after a container update usually means Borg could not fully reuse its files cache for that run.

Check these items:

- Keep `/home/borg/.cache/borg` mounted to persistent storage. A named volume such as `borg_cache:/home/borg/.cache/borg` or a stable host bind mount such as `./cache:/home/borg/.cache/borg` is fine.
- Keep source directories mounted at the same container paths. Borg's files cache uses absolute filenames, so changing `/local/photos` to `/photos`, or moving the same host path between container paths, can make a later backup behave like a first scan.
- Make sure the cache is writable by the configured `PUID` and `PGID`. Permission problems can prevent Borg from updating or reading cache state.
- If the source path is an SSHFS, FUSE, network, or removable-drive mount with unstable inode numbers, Borg's default files-cache mode can treat unchanged files as modified. In that case, set repository custom Borg flags to a mode that ignores inode numbers, for example `--files-cache=mtime,size`. Use this only when you understand the reduced change-detection safety for that filesystem.
- After an image update that changes the bundled Borg version, the first backup may need extra cache validation or rebuild work. Later runs should speed up again if the cache volume and source mount paths stay stable.

Useful checks from the Docker host:

```bash
docker exec borg-web-ui sh -lc 'id borg && ls -ld /home/borg/.cache/borg'
docker exec borg-web-ui sh -lc 'find /home/borg/.cache/borg -maxdepth 2 -type f | head'
docker compose ps redis
```

If Redis restarted, archive browsing cache is cold, but that should not by itself slow `borg create` backup jobs.
