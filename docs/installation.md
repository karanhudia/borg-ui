# Installation Guide

Complete installation instructions for all platforms.

---

## Quick Start

The fastest way to get started:

```bash
docker run -d \
  --name borg-web-ui \
  --restart unless-stopped \
  -p 8081:8081 \
  -e PUID=1000 \
  -e PGID=1000 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /:/local:rw \
  ainullcode/borg-ui:latest
```

Access at `http://localhost:8081`

**Default credentials:** `admin` / `admin123`

---

## Installation Methods

### Docker Compose (Recommended)

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /:/local:rw
    environment:
      - PUID=1000
      - PGID=1000

volumes:
  borg_data:
  borg_cache:
```

Start the container:

```bash
docker compose up -d
```

### Portainer

1. Go to **Stacks** > **Add Stack**
2. Name your stack: `borg-ui`
3. Paste the docker-compose configuration above
4. Click **Deploy the stack**
5. Access at `http://your-server-ip:8081`

### Unraid

#### Option 1: Docker Compose (Recommended)

1. Install **Compose Manager** plugin
2. Go to **Docker** > **Compose** > **Add New Stack**
3. Name: `borg-ui`
4. Paste configuration:

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - /mnt/user/appdata/borg-ui:/data
      - /mnt/user/appdata/borg-ui/cache:/home/borg/.cache/borg
      - /mnt/user:/local:rw
    environment:
      - PUID=99
      - PGID=100
```

5. Click **Compose Up**

#### Option 2: Unraid Web UI

1. Go to **Docker** tab > **Add Container**
2. Configure:
   - **Name**: `borg-web-ui`
   - **Repository**: `ainullcode/borg-ui:latest`
   - **Network Type**: `Bridge`

**Port Mappings:**
- Container Port `8081` → Host Port `8081`

**Volume Mappings:**
| Container Path | Host Path | Access |
|----------------|-----------|--------|
| `/data` | `/mnt/user/appdata/borg-ui` | Read/Write |
| `/home/borg/.cache/borg` | `/mnt/user/appdata/borg-ui/cache` | Read/Write |
| `/local` | `/mnt/user` | Read/Write |

**Environment Variables:**
- `PUID`: `99`
- `PGID`: `100`

3. Click **Apply**

---

## Post-Installation

### First Login

1. Access `http://localhost:8081` (or your server IP)
2. Login with default credentials:
   - Username: `admin`
   - Password: `admin123`
3. You'll be prompted to change your password

### Verify Installation

Check that the container is running:

```bash
docker ps | grep borg-web-ui
docker logs borg-web-ui
```

You should see:
```
INFO: Application startup complete
INFO: Uvicorn running on http://0.0.0.0:8081
```

---

## Customization

### Change Port

To use a different port:

```yaml
environment:
  - PORT=8082
ports:
  - "8082:8082"
```

### Restrict Filesystem Access

Instead of mounting the entire filesystem (`/:/local:rw`), mount only specific directories:

```yaml
volumes:
  - /home/user/backups:/backups:rw
  - /home/user/data:/data-source:ro
```

See [Configuration Guide](configuration.md) for details.

### Set User/Group IDs

Match your host user to avoid permission issues:

```bash
# Find your IDs
id -u && id -g

# Set in docker-compose.yml
environment:
  - PUID=1000  # Your user ID
  - PGID=1000  # Your group ID
```

---

## Updating

### Docker Compose

```bash
docker compose pull
docker compose up -d
```

### Docker Run

```bash
docker pull ainullcode/borg-ui:latest
docker stop borg-web-ui
docker rm borg-web-ui
# Run the docker run command again
```

### Portainer

1. Go to **Stacks**
2. Select `borg-ui`
3. Click **Pull and redeploy**

---

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker logs borg-web-ui
```

### Port Already in Use

Change the port:
```yaml
ports:
  - "8082:8081"
```

### Permission Denied Errors

Match your host user ID:
```yaml
environment:
  - PUID=1000
  - PGID=1000
```

Find your IDs: `id -u && id -g`

### Cannot Access Web Interface

Check firewall rules:
```bash
# Linux
sudo ufw allow 8081

# Check container is running
docker ps | grep borg-web-ui
```

---

## Uninstallation

### Remove Container

```bash
docker compose down
# or
docker stop borg-web-ui && docker rm borg-web-ui
```

### Remove Data (Optional)

```bash
# WARNING: This deletes all application data
docker volume rm borg_data borg_cache
```

---

## Next Steps

- [Configuration Guide](configuration.md) - Customize your setup
- [Usage Guide](usage-guide.md) - Create your first backup
- [Notifications Setup](notifications.md) - Get alerts for backup events
