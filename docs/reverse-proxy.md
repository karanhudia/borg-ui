---
title: Reverse Proxy
nav_order: 4
description: "Run Borg UI behind Nginx, Caddy, Traefik, or another reverse proxy"
---

# Reverse Proxy

Run Borg UI behind a reverse proxy for TLS, public hostnames, and optional external authentication.

For production, terminate HTTPS at the reverse proxy, load balancer, ingress
controller, or orchestrator. Borg UI runs as the upstream application; it does
not issue certificates, store TLS private keys, or renew certificates inside the
app process.

Passkey registration and login require a stable HTTPS browser origin for
non-localhost deployments. Serve the frontend and API from the same public
origin, for example `https://backups.example.com`, so passkeys, cookies, OIDC,
and Cloud Storage OAuth callbacks all see the same site. Split-origin frontend
and API deployments need custom CORS and cookie handling and are not the normal
deployment path.

For a passkey-ready deployment:

- set `PUBLIC_BASE_URL` to the normal browser URL, including `BASE_PATH` for
  sub-path deployments
- keep `PUBLIC_BASE_URL` on HTTPS except for localhost development
- forward `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and
  `X-Forwarded-For`
- list only the proxy IPs that may be trusted in `TRUSTED_PROXIES` when Borg UI
  should use forwarded headers
- keep direct container access unavailable to users so they cannot bypass the
  public HTTPS origin or spoof trusted headers

## Root Domain

Example public URL:

```text
https://backups.example.com
```

Backend environment:

```yaml
environment:
  - PUBLIC_BASE_URL=https://backups.example.com
  - TRUSTED_PROXIES=127.0.0.1
```

Nginx:

```nginx
server {
    listen 443 ssl http2;
    server_name backups.example.com;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
    }
}
```

NGINX terminates TLS for Borg UI, but certificate provisioning stays outside
Borg UI. Use your NGINX or certificate tooling to obtain and renew certificates,
such as Certbot or acme.sh with an HTTP challenge, a Cloudflare DNS challenge,
or another DNS provider challenge. Mount or reference those certificates in
NGINX; do not mount TLS private keys into Borg UI for in-process HTTPS.

Caddy:

```text
backups.example.com {
    reverse_proxy 127.0.0.1:8081
}
```

Caddy is the lowest-friction option for many single-host deployments because it
automatically obtains and renews Let's Encrypt certificates for public hostnames
that can complete ACME validation.

## Sub-Path Deployment

Example public URL:

```text
https://example.com/borg-ui
```

Set:

```yaml
environment:
  - BASE_PATH=/borg-ui
  - PUBLIC_BASE_URL=https://example.com/borg-ui
```

Your proxy must strip the `/borg-ui` prefix before forwarding to Borg UI.

Nginx:

```nginx
location /borg-ui/ {
    proxy_pass http://127.0.0.1:8081/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
}
```

Do not rely on direct container access at `/borg-ui` as a production path. Put the sub-path behavior in the proxy.

OIDC callback example:

```text
https://example.com/borg-ui/api/auth/oidc/callback
```

If Borg UI builds the wrong public URL behind your proxy, set:

```yaml
environment:
  - PUBLIC_BASE_URL=https://example.com/borg-ui
```

If you rely on forwarded headers instead, make sure the proxy IP is listed in `TRUSTED_PROXIES`. The value is a comma-separated list of proxy IPs.

## Cloud Storage OAuth Callbacks

Google Drive and Microsoft OneDrive OAuth callbacks return to Borg UI at these
API paths:

```text
/api/rclone/oauth/callback/drive
/api/rclone/oauth/callback/onedrive
```

The public redirect URL registered with the provider must exactly match the
browser URL for the deployment. For a root-domain deployment, use:

```text
https://backups.example.com/api/rclone/oauth/callback/drive
https://backups.example.com/api/rclone/oauth/callback/onedrive
```

For a sub-path deployment, include the sub-path:

```text
https://example.com/borg-ui/api/rclone/oauth/callback/drive
https://example.com/borg-ui/api/rclone/oauth/callback/onedrive
```

Set `PUBLIC_BASE_URL` when the backend cannot infer the public URL from trusted
forwarded headers. Borg UI validates this value before starting a provider-owned
OAuth flow and rejects non-HTTPS public URLs except for localhost development.
Provider client IDs and secrets are saved by an admin in Cloud Storage and are
never returned to ordinary frontend responses.

Make sure the proxy forwards the callback path to Borg UI without requiring a
browser to reach rclone's loopback listener at `127.0.0.1:53682`. After a
Borg UI-owned callback, the browser shows a completion page and the Cloud
Storage dialog polls a server-side session marker. rclone loopback/manual
authorization remains available for unsupported providers and advanced setups.

## Traefik Example

Traefik can also automate Let's Encrypt issuance and renewal. Define an ACME
certificate resolver in Traefik's static configuration, then point the Borg UI
router at that resolver:

```yaml
entryPoints:
  web:
    address: ":80"
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: ops@example.com
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web
```

```yaml
services:
  app:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    labels:
      - traefik.enable=true
      - traefik.http.routers.borg-ui.rule=Host(`backups.example.com`)
      - traefik.http.routers.borg-ui.entrypoints=websecure
      - traefik.http.routers.borg-ui.tls.certresolver=letsencrypt
      - traefik.http.services.borg-ui.loadbalancer.server.port=8081
    environment:
      - PUBLIC_BASE_URL=https://backups.example.com
```

If HTTP challenge is not available, configure Traefik's ACME DNS challenge with
Cloudflare or another DNS provider. That certificate automation remains a
Traefik/proxy responsibility, not a Borg UI app responsibility.

## Trusted-Header Auth

Only use trusted-header auth when an authenticated proxy is the only way to reach Borg UI.

Environment:

```yaml
environment:
  - DISABLE_AUTHENTICATION=true
  - PROXY_AUTH_HEADER=X-Forwarded-User
  - PROXY_AUTH_ROLE_HEADER=X-Borg-Role
  - PROXY_AUTH_ALL_REPOSITORIES_ROLE_HEADER=X-Borg-All-Repositories-Role
  - PROXY_AUTH_EMAIL_HEADER=X-Borg-Email
  - PROXY_AUTH_FULL_NAME_HEADER=X-Borg-Full-Name
```

Valid role values:

- `viewer`
- `operator`
- `admin`

If users can reach Borg UI directly, they can spoof these headers. Isolate the container on a private Docker network or bind it only to localhost.

See [Authentication and SSO](authentication) for auth mode details.

## WebSockets and Streaming

Borg UI uses streaming for job progress and logs. The proxy must support:

- HTTP/1.1 upstream
- upgrade headers
- long-lived connections
- disabled buffering for streaming routes

## Related

- [Security](security)
- [Configuration](configuration)
- [Authentication and SSO](authentication)
