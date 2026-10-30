---
title: Security
nav_order: 7
description: "Security practices for Borg UI deployments"
---

# Security

Borg UI controls backup and restore operations. Treat it as sensitive infrastructure.

This page is about hardening your deployment. For what the software itself stores,
encrypts, and sends anywhere else, see
[What Borg UI Does With Your Data](trust).

## First Steps

After installation:

1. Change the default `admin` password in Settings > Account.
2. Use a strong `INITIAL_ADMIN_PASSWORD` for new deployments.
3. Keep `/data` private and backed up.
4. Put the app behind TLS if it is reachable over a network.
5. Keep Borg UI updated.

## Protect `/data`

The `/data` volume contains:

- SQLite database
- generated secret key
- logs
- encrypted SSH key material
- job metadata

Anyone who can read or modify `/data` can affect the Borg UI instance.

## Docker Socket

Mounting `/var/run/docker.sock` gives the Borg UI container control over the host Docker daemon.

Only mount it if Docker hook scripts need it:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

Do not mount it for normal backups. If hook scripts only need limited Docker container actions, prefer a Docker socket proxy and set Borg UI's Docker CLI endpoint with `DOCKER_HOST=tcp://docker-socket-proxy:2375`.

## Authentication Modes

Recommended order:

1. Built-in local auth for small/self-hosted deployments.
2. Built-in OIDC for SSO.
3. Trusted-header auth only behind a locked-down reverse proxy.

Never expose trusted-header auth directly to users.

## OIDC

Use built-in OIDC when Borg UI should talk directly to the identity provider.

Keep frontend and API on the same public origin. Split-origin setups need explicit CORS/cookie work and are not the default supported path.

See [Authentication and SSO](authentication) for setup details.

## Trusted-Header Auth

Trusted-header auth reads identity from proxy-set headers.

Safe only when:

- the Borg UI container is not directly reachable
- the proxy strips incoming user-controlled auth headers
- only the proxy can set the trusted headers

If direct access is possible, a user can spoof headers and impersonate another user.

See [Authentication and SSO](authentication) for header settings.

## Metrics

The `/metrics` endpoint should be private or token-protected.

Recommended:

- enable metrics only when needed
- require a token
- let Prometheus scrape it over a private network
- expose Grafana, not `/metrics`, to users

## Remote SSH Access

Use Remote Machines and SSH keys instead of passwords.

For remote backup users:

- use a dedicated Unix user
- grant only required filesystem access
- restrict Borg keys with `borg serve --restrict-to-path` where practical
- rotate keys when access changes

## Repository Locks

Breaking a Borg lock while another Borg process is active can corrupt or damage a repository.

Before breaking a lock, confirm there is no:

- running backup
- restore
- check
- prune
- compact
- mount
- external Borg process

## Password Reset

If an admin is locked out and you have shell access to the container:

```bash
docker exec -it borg-web-ui python -m app.scripts.reset_password admin newpassword123
```

Shell access to the container is equivalent to administrative access.

## Reverse Proxy Checklist

- terminate TLS at the proxy
- forward `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`
- support WebSocket/SSE-style long-running connections
- do not expose trusted-header auth directly
- register OIDC callback URLs using the public URL users actually open

See [Reverse Proxy](reverse-proxy).

## Updates

Update with:

```bash
docker compose pull
docker compose up -d
```

Keep `/data` and Borg repository backups before major upgrades.

### Operator Path Restriction Upgrades

New non-admin server backup sources and `R`/`r` roots in `--pattern` flags are
checked when selected: they must be absolute, contain no `..`, resolve inside
`LOCAL_MOUNT_POINTS`, and neither contain nor be inside `/app` or `DATA_DIR`.
New dump, export, and btrfs staging metadata must also avoid those reserved
directories, but may live outside the mount points. New agent sources and
pattern roots, and restores from agent repositories, require an administrator.
See [Access Control](access-control#operator-path-restrictions) and
[Configuration](configuration#volumes) for the complete role and path rules.

**Existing plans are not migrated or revalidated at runtime.** Their stored
paths, metadata, and pattern roots remain usable in manual and scheduled runs,
including paths outside the newly allowed area. Operators can retain or remove
those paths while editing other fields. Removing a path and adding it again
makes it a new selection. Plans with no remaining repositories cannot retain
unchecked paths. Copying sources from an administrator-configured repository
remains permitted.

An administrator should review existing plans after upgrading. Use
`GET /api/backup-plans/` with an administrator account to inspect every plan and
its repository links, then edit plans that exceed the intended access:

- Review both `source_directories` and structured `source_locations`, including
  existing agent paths and the associated agent machine.
- Review `R`/`r` roots in plan `custom_flags` and link `custom_flags_override`,
  including disabled links that could later resume.
- Review database `dump_path`, container `export_path`, and btrfs snapshot
  `staging_path` metadata for reserved-directory access.
- Remove or narrow sources and roots outside the intended mount points or
  covering the application or data directory. Review existing agent paths with
  the administrator responsible for that host.

These are selection-time checks, not complete filesystem confinement. A path
that is safe when selected can later be replaced by a symlink; execution does
not repeat the check. The contents of `--patterns-from` and `--exclude-from`
files are not validated by these new checks (their file paths retain the
existing mount-point validation). ZFS `dataset`/`mountpoint` and database
`backup_paths` retain their existing behavior. Metadata path strings, including
remote SSH locations' database `dump_path` and container `export_path`, are
checked against the server's reserved-path policy. With
`script_execution_target=source`, those metadata scripts still execute on the
SSH host; these checks do not confine its filesystem or symlinks. Managed agents
have no allowed-root configuration, which is why new operator agent paths and
agent restores are refused.

Non-admin Borg mount targets, including automatically suffixed occupied targets,
must resolve strictly below `DATA_DIR/mounts` before directory creation. SSHFS
staging paths are bounded for everyone: `..` is normalized and a symlink escape
is refused before creating the target or mounting it. An administrator backup
that previously followed such an escape now fails instead of reading the
symlink's target on the server; ordinary administrator path selection is
unchanged.
