---
title: Configuration
nav_order: 3
description: "Environment variables, volumes, settings, and runtime defaults"
---

# Configuration

Most configuration is available in the UI under Settings. Use environment variables for deployment-time defaults and settings that must exist before the app starts.

## Core Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8081` | HTTP port inside the container and usually on the host |
| `ENVIRONMENT` | `production` | Runtime mode |
| `PUID` | `1001` | Host user ID for file ownership |
| `PGID` | `1001` | Host group ID for file ownership |
| `TZ` | host/default | Timezone used for logs and schedules |
| `DATA_DIR` | `/data` | App database, logs, SSH material, generated secret |
| `SECRET_KEY` | generated | JWT/session signing key. Auto-generated into `/data/.secret_key` if omitted |
| `INITIAL_ADMIN_PASSWORD` | `admin123` | Password for the first `admin` user |
| `LOG_LEVEL` | `INFO` | Backend log level |
| `LOCAL_MOUNT_POINTS` | `/local` | Comma-separated container paths shown as local mounts in the file browser |
| `BASE_PATH` | empty | Sub-path deployment, for example `/borg-ui` |

## Volumes

Required:

```yaml
volumes:
  - borg_data:/data
  - borg_cache:/home/borg/.cache/borg
  - /host/path:/local:rw
```

What they mean:

- `/data`: Borg UI application state. Back this up.
- `/home/borg/.cache/borg`: Borg cache. Keep it for performance.
- `/local`: host data exposed to Borg UI for local backups and repositories.

If you mount a different container path, update `LOCAL_MOUNT_POINTS`.

Example:

```yaml
volumes:
  - /mnt/photos:/photos:ro
  - /mnt/backups:/backups:rw
environment:
  - LOCAL_MOUNT_POINTS=/photos,/backups
```

## Local Path Mapping

Container paths are what Borg UI can see.

If this is your volume:

```yaml
- /mnt/usb-drive:/local:rw
```

Then use this in Borg UI:

```text
/local/some-folder
```

not:

```text
/mnt/usb-drive/some-folder
```

## Redis Cache

Redis settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_HOST` | `localhost` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database number |
| `REDIS_PASSWORD` | empty | Redis password |
| `REDIS_URL` | empty | Full Redis URL. Takes precedence over host/port/db |
| `CACHE_TTL_SECONDS` | `7200` | Archive cache TTL |
| `CACHE_MAX_SIZE_MB` | `2048` | Cache size target |

The UI can override Redis URL, cache TTL, and max cache size in Settings > System > Cache.

Priority for UI-managed cache settings:

1. saved database value, when changed from default
2. environment variable
3. built-in default

## Operation Timeouts

Timeout settings can be changed in Settings > System > Operation Timeouts.

Environment defaults:

| Variable | Default | Used for |
| --- | --- | --- |
| `BORG_MOUNT_TIMEOUT` | `120` | `borg mount` |
| `BORG_INFO_TIMEOUT` | `600` | repository info and stats |
| `BORG_LIST_TIMEOUT` | `600` | archive and file listing |
| `BORG_INIT_TIMEOUT` | `300` | repository initialization |
| `BACKUP_TIMEOUT` | `3600` | backup and restore commands |
| `SOURCE_SIZE_TIMEOUT` | `3600` | source size calculation |
| `SCRIPT_TIMEOUT` | `120` | pre/post-backup scripts |

Priority for UI-managed timeout settings:

1. saved database value, when changed from default
2. environment variable
3. built-in default

## Authentication

Default mode is local username/password auth.

Related settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DISABLE_AUTHENTICATION` | `false` | Trust a reverse proxy auth header |
| `ALLOW_INSECURE_NO_AUTH` | `false` | Disable auth entirely. Use only for local development |
| `PROXY_AUTH_HEADER` | `X-Forwarded-User` | Username header for trusted-header auth |
| `PROXY_AUTH_ROLE_HEADER` | empty | Optional global role header |
| `PROXY_AUTH_ALL_REPOSITORIES_ROLE_HEADER` | empty | Optional default repository role header |
| `PROXY_AUTH_EMAIL_HEADER` | empty | Optional email header |
| `PROXY_AUTH_FULL_NAME_HEADER` | empty | Optional display-name header |
| `PUBLIC_BASE_URL` | empty | Public URL used by auth flows when needed |

Built-in OIDC is configured in the UI, not through a long list of environment variables.

Use trusted-header auth only when the Borg UI container is reachable exclusively through the trusted proxy. Otherwise anyone who reaches the app directly can spoof identity headers.

## Licensing and Activation

| Variable | Default | Purpose |
| --- | --- | --- |
| `ACTIVATION_SERVICE_URL` | `https://license.borgui.com` | License activation endpoint |
| `ACTIVATION_TIMEOUT_SECONDS` | `10` | Activation request timeout |
| `ENABLE_STARTUP_LICENSE_SYNC` | `true` in production | Sync license/full-access state at startup |

Set `ENABLE_STARTUP_LICENSE_SYNC=false` to prevent startup contact with the activation service.

## Reverse Proxy Sub-Path

Set `BASE_PATH` only when serving under a sub-path:

```yaml
environment:
  - BASE_PATH=/borg-ui
```

Your proxy must strip `/borg-ui` before forwarding requests to the container. See [Reverse Proxy](reverse-proxy).

## Related

- [Installation](installation)
- [Cache](cache)
- [Security](security)
- [Remote Machines](ssh-keys)
