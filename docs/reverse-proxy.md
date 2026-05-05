---
title: Reverse Proxy
nav_order: 4
description: "Run Borg UI behind Nginx, Caddy, Traefik, or another reverse proxy"
---

# Reverse Proxy

Run Borg UI behind a reverse proxy for TLS, public hostnames, and optional external authentication.

When using built-in OIDC, the frontend and API must be served from the same public origin.

## Root Domain

Example public URL:

```text
https://backups.example.com
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
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
    }
}
```

Caddy:

```text
backups.example.com {
    reverse_proxy 127.0.0.1:8081
}
```

## Sub-Path Deployment

Example public URL:

```text
https://example.com/borg-ui
```

Set:

```yaml
environment:
  - BASE_PATH=/borg-ui
```

Your proxy must strip the `/borg-ui` prefix before forwarding to Borg UI.

Nginx:

```nginx
location /borg-ui/ {
    proxy_pass http://127.0.0.1:8081/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
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

## Traefik Example

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
```

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
