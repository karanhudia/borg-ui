---
layout: default
title: Security
nav_order: 7
description: "Security practices for Borg UI deployments"
---

# Security

Borg UI controls backup and restore operations. Treat it as sensitive infrastructure.

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

Do not mount it for normal backups.

## Authentication Modes

Recommended order:

1. Built-in local auth for small/self-hosted deployments.
2. Built-in OIDC for SSO.
3. Trusted-header auth only behind a locked-down reverse proxy.

Never expose trusted-header auth directly to users.

## OIDC

Use built-in OIDC when Borg UI should talk directly to the identity provider.

Keep frontend and API on the same public origin. Split-origin setups need explicit CORS/cookie work and are not the default supported path.

## Trusted-Header Auth

Trusted-header auth reads identity from proxy-set headers.

Safe only when:

- the Borg UI container is not directly reachable
- the proxy strips incoming user-controlled auth headers
- only the proxy can set the trusted headers

If direct access is possible, a user can spoof headers and impersonate another user.

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
