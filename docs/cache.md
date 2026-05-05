---
title: Cache
nav_order: 7
description: "Redis and archive browsing cache behavior"
---

# Cache

Borg UI uses caching to make repeated archive browsing faster.

The first browse of a large archive can still be slow because Borg has to list archive contents. After that, cached results can be served much faster.

## Backends

Borg UI supports:

- Redis cache
- in-memory fallback cache

Redis is recommended for normal Docker Compose deployments. In-memory cache works, but it is lost whenever the app restarts.

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

Priority:

1. saved UI setting
2. `REDIS_URL`
3. `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB`
4. in-memory fallback

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
