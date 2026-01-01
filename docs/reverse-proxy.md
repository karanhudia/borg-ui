---
layout: default
title: Reverse Proxy Setup
nav_order: 8
description: "Running Borg Web UI behind reverse proxies with BASE_PATH support"
---

# Reverse Proxy Setup

Configure Borg Web UI to run behind reverse proxies, including subfolder deployments.

---

## Overview

Borg Web UI supports running behind reverse proxies in two configurations:

1. **Root domain**: `https://backups.example.com/` (no BASE_PATH needed)
2. **Subfolder**: `https://example.com/borg/` (requires BASE_PATH configuration)

---

## Subfolder Deployment (BASE_PATH)

{: .new }
> **Updated in v1.38+**: No rebuild required! Just set BASE_PATH and restart.

### Quick Start

To run Borg Web UI in a subfolder (e.g., `/borg`):

1. **Set BASE_PATH environment variable:**

```yaml
environment:
  - BASE_PATH=/borg
```

2. **Restart the container:**

```bash
docker-compose restart
```

**That's it!** No rebuild, no special proxy configuration needed. Works with any reverse proxy (Nginx, Traefik, Caddy, Cloudflare Tunnels, etc.) out of the box.

### How It Works

The app handles BASE_PATH internally, so it works with any reverse proxy configuration:

- User visits: `https://example.com/borg/dashboard`
- Proxy forwards full path `/borg/dashboard` to container (no stripping needed)
- App handles the request and serves the correct page

**No proxy configuration required** - the app adapts to whatever path it receives.

### Configuration

Add to your `docker-compose.yml`:

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    environment:
      - BASE_PATH=/borg
```

Or in `.env` file:

```bash
BASE_PATH=/borg
```

**BASE_PATH Rules:**
- Must start with `/` (e.g., `/borg` not `borg`)
- No trailing slash (e.g., `/borg` not `/borg/`)
- Defaults to `/` if not set
- Can be changed at any time without rebuilding

---

## Nginx Configuration

### Subfolder Deployment

```nginx
server {
    listen 80;
    server_name example.com;

    location /borg {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for SSE events)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

**Docker configuration:**

```yaml
environment:
  - BASE_PATH=/borg
```

**Note**: Notice `location /borg` and `proxy_pass http://localhost:8081` (no trailing slashes) - this forwards the full path to the container.

### Root Domain

```nginx
server {
    listen 80;
    server_name backups.example.com;

    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for SSE events)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

**Docker configuration:**

```yaml
# No BASE_PATH needed (defaults to /)
```

### With SSL (Let's Encrypt)

```nginx
server {
    listen 443 ssl http2;
    server_name backups.example.com;

    ssl_certificate /etc/letsencrypt/live/backups.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/backups.example.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}

server {
    listen 80;
    server_name backups.example.com;
    return 301 https://$server_name$request_uri;
}
```

---

## Traefik Configuration

### Subfolder Deployment

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    environment:
      - BASE_PATH=/borg
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.borg-ui.rule=Host(`example.com`) && PathPrefix(`/borg`)"
      - "traefik.http.routers.borg-ui.entrypoints=websecure"
      - "traefik.http.routers.borg-ui.tls.certresolver=letsencrypt"
      - "traefik.http.services.borg-ui.loadbalancer.server.port=8081"
```

**Note**: No stripprefix middleware needed - the app handles the BASE_PATH internally.

### Root Domain

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.borg-ui.rule=Host(`backups.example.com`)"
      - "traefik.http.routers.borg-ui.entrypoints=websecure"
      - "traefik.http.routers.borg-ui.tls.certresolver=letsencrypt"
      - "traefik.http.services.borg-ui.loadbalancer.server.port=8081"
```

---

## Caddy Configuration

### Subfolder Deployment

```caddyfile
example.com {
    handle /borg* {
        reverse_proxy localhost:8081
    }
}
```

**Docker configuration:**

```yaml
environment:
  - BASE_PATH=/borg
```

**Note**: No uri strip_prefix needed - the app handles the BASE_PATH internally.

### Root Domain

```caddyfile
backups.example.com {
    reverse_proxy localhost:8081
}
```

---

## Apache Configuration

### Subfolder Deployment

```apache
<VirtualHost *:80>
    ServerName example.com

    ProxyPreserveHost On
    ProxyPass /borg http://localhost:8081/borg
    ProxyPassReverse /borg http://localhost:8081/borg

    # WebSocket support
    RewriteEngine on
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule /borg/(.*) ws://localhost:8081/borg/$1 [P,L]
</VirtualHost>
```

**Docker configuration:**

```yaml
environment:
  - BASE_PATH=/borg
```

**Note**: No prefix stripping - the proxy forwards the full path to the container.

### Root Domain

```apache
<VirtualHost *:443>
    ServerName backups.example.com

    SSLEngine on
    SSLCertificateFile /path/to/cert.pem
    SSLCertificateKeyFile /path/to/key.pem

    ProxyPreserveHost On
    ProxyPass / http://localhost:8081/
    ProxyPassReverse / http://localhost:8081/

    # WebSocket support
    RewriteEngine on
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule /(.*) ws://localhost:8081/$1 [P,L]
</VirtualHost>
```

---

## Docker Network Integration

If your reverse proxy runs in Docker, use Docker networks:

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    networks:
      - proxy_network
    environment:
      - BASE_PATH=/borg

networks:
  proxy_network:
    external: true
```

Then configure your proxy to use `http://borg-web-ui:8081` instead of `localhost:8081`.

---

## Common Issues

### Assets Not Loading

**Symptom**: Frontend shows blank page or 404 errors for assets

**Solution**: Clear browser cache and hard refresh (Ctrl+Shift+R or Cmd+Shift+R)

```bash
# Restart container to apply BASE_PATH
docker-compose restart
```

### Authentication Redirects

**Symptom**: Login redirects to wrong URL

**Solution**: Ensure BASE_PATH is set correctly and restart container

```yaml
environment:
  - BASE_PATH=/borg
```

### API Calls Failing

**Symptom**: API returns 404 errors

**Solution**: Ensure BASE_PATH matches the URL path and that your proxy is forwarding requests to the container. No special proxy configuration needed.

### SSE Connection Errors

**Symptom**: Real-time events not working

**Solution**: Ensure WebSocket/SSE support in proxy configuration:

```nginx
# Nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 86400;
```

---

## Testing

### Local Testing

**Root deployment (no BASE_PATH):**
```yaml
# docker-compose.yml or .env
# Don't set BASE_PATH, or set it to empty/root
BASE_PATH=/
# or simply omit BASE_PATH
```

Access at: `http://localhost:8081/`

**Subfolder deployment:**
```yaml
# docker-compose.yml or .env
BASE_PATH=/borg
```

Access at: `http://localhost:8081/borg/`

**Works directly!** No reverse proxy needed for local testing.

### Verify Configuration

1. **Check health endpoint:**
   ```bash
   # Root deployment
   curl http://localhost:8081/health

   # Subfolder deployment
   curl http://localhost:8081/borg/health
   ```

2. **Check API info:**
   ```bash
   # Root deployment
   curl http://localhost:8081/api

   # Subfolder deployment
   curl http://localhost:8081/borg/api
   ```

3. **Access web interface:**
   - Root deployment: `http://localhost:8081/`
   - Subfolder deployment: `http://localhost:8081/borg/`

### Debug Mode

Enable debug logging to troubleshoot:

```yaml
environment:
  - LOG_LEVEL=DEBUG
  - BASE_PATH=/borg
```

Check logs:
```bash
docker logs borg-web-ui
```

---

## Security Best Practices

### Use HTTPS

Always use HTTPS when exposing to the internet:

```nginx
# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name backups.example.com;
    return 301 https://$server_name$request_uri;
}
```

### Restrict Access by IP

```nginx
location /borg/ {
    allow 192.168.1.0/24;
    deny all;

    proxy_pass http://localhost:8081/;
}
```

### Use Authentication

Add basic auth in Nginx:

```nginx
location /borg/ {
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;

    proxy_pass http://localhost:8081/;
}
```

Or use Traefik middleware:

```yaml
labels:
  - "traefik.http.middlewares.borg-auth.basicauth.users=user:$$apr1$$..."
  - "traefik.http.routers.borg-ui.middlewares=borg-auth"
```

---

## Example Deployments

### Home Server with Subfolder

```yaml
# docker-compose.yml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    networks:
      - web

  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    environment:
      - BASE_PATH=/backups
    networks:
      - web
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /home/user:/local:rw

networks:
  web:
    driver: bridge

volumes:
  borg_data:
  borg_cache:
```

```nginx
# nginx.conf
server {
    listen 80;
    server_name home.example.com;

    location /backups/ {
        proxy_pass http://borg-ui:8081/;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Production with Traefik

```yaml
# docker-compose.yml
services:
  traefik:
    image: traefik:v2.10
    command:
      - "--api.insecure=false"
      - "--providers.docker=true"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@example.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "letsencrypt:/letsencrypt"

  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.borg-ui.rule=Host(`backups.example.com`)"
      - "traefik.http.routers.borg-ui.entrypoints=websecure"
      - "traefik.http.routers.borg-ui.tls.certresolver=letsencrypt"
      - "traefik.http.services.borg-ui.loadbalancer.server.port=8081"
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /var/backups:/local:rw

volumes:
  letsencrypt:
  borg_data:
  borg_cache:
```

---

## Next Steps

- [Configuration Guide](configuration.md) - Environment variables and volumes
- [Security Guide](security.md) - Harden your installation
- [Installation Guide](installation.md) - Initial setup
