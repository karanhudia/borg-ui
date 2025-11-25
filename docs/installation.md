---
layout: default
title: Installation
nav_order: 2
description: "How to install Borg Web UI on various platforms"
---

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
  -e TZ=America/Chicago \
  -e PUID=1000 \
  -e PGID=1000 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/yourusername:/local:rw \
  ainullcode/borg-ui:latest
```

**⚠️ Security Note:** Replace `/home/yourusername` with your actual directory path. See the [Restrict Filesystem Access](#restrict-filesystem-access) section below for details.

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
      # Mount directories you want to backup (REPLACE with your actual paths)
      - /home/yourusername:/local:rw     # Replace with your directory path
    environment:
      - TZ=America/Chicago  # Set your timezone
      - PUID=1000
      - PGID=1000

volumes:
  borg_data:
  borg_cache:
```

**⚠️ Security Note:** Replace `/home/yourusername` with your actual directory path. See the [Restrict Filesystem Access](#restrict-filesystem-access) section below for more information.

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
      - /mnt/user:/local:rw  # Customize to specific shares if needed
    environment:
      - TZ=America/Chicago  # Set your timezone
      - PUID=99
      - PGID=100
```

**Note:** `/mnt/user` provides access to all Unraid shares. For better security, mount specific shares only (e.g., `/mnt/user/documents:/local:rw`).

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
- `TZ`: `America/Chicago` (your timezone)
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

### Set Timezone (Recommended)

Set your local timezone for correct archive timestamps and scheduling:

```yaml
environment:
  - TZ=America/Chicago  # Set your timezone
  - PUID=1000
  - PGID=1000
```

**Common timezones:**
- **US East Coast**: `America/New_York`
- **US Central**: `America/Chicago`
- **US West Coast**: `America/Los_Angeles`
- **UK**: `Europe/London`
- **Central Europe**: `Europe/Paris`
- **India**: `Asia/Kolkata`
- **Japan**: `Asia/Tokyo`
- **Australia (Sydney)**: `Australia/Sydney`

[Full timezone list →](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

{: .note }
> **Why set timezone?** Docker containers default to UTC. Without setting `TZ`, your archive names and timestamps will show UTC time instead of your local time, which can be confusing.

### Change Port

To use a different port:

```yaml
environment:
  - PORT=8082
ports:
  - "8082:8082"
```

### Restrict Filesystem Access

**⚠️ Important Security Consideration**

For production use, mount only the specific directories you need to backup instead of broad filesystem access:

```yaml
volumes:
  # ✅ Recommended: Mount specific directories
  - /home/yourusername:/local:rw         # Replace with your path
  - /mnt/data:/local/data:rw             # Additional directories as needed
  - /opt/myapp:/local/myapp:ro           # Read-only if only backing up

  # ❌ NOT Recommended: Full filesystem access
  # - /:/local:rw  # Security risk - avoid in production
```

**Common Patterns:**

**Personal Computer:**
```yaml
- /home/john:/local:rw           # Home directory
- /home/john/documents:/local:rw # Or just documents
```

**Server:**
```yaml
- /var/www:/local/www:ro         # Website files (read-only)
- /var/lib/postgresql:/local/db:rw  # Database directory
- /opt/apps:/local/apps:rw       # Application data
```

**Multiple Users:**
```yaml
- /home/user1:/local/user1:rw
- /home/user2:/local/user2:rw
- /mnt/shared:/local/shared:rw
```

**Best Practices:**
- Mount only directories that need backup
- Use `:ro` (read-only) for backup-only directories where you won't restore files
- For multiple directories, add multiple volume mounts
- Never mount root (`/`) unless absolutely necessary for system-level backups

See [Configuration Guide](configuration.md) for more examples and details.

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

## Advanced Configuration

### Docker Container Management (Optional)

If you need to stop/start Docker containers during backups (e.g., for database consistency), you can mount the Docker socket:

**⚠️ Security Warning:** Mounting `/var/run/docker.sock` gives the container access to your Docker daemon (equivalent to root access). Only enable if you need this functionality.

#### Enable Docker Socket Access

Edit your `docker-compose.yml` and add the docker.sock volume:

```yaml
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
      - /home/yourusername:/local:rw  # Replace with your path
      # Add this line for Docker container management:
      - /var/run/docker.sock:/var/run/docker.sock:rw
    environment:
      - TZ=America/Chicago
      - PUID=1000
      - PGID=1000
```

Restart the container:
```bash
docker compose down
docker compose up -d
```

#### Usage

Once enabled, you can use pre/post backup scripts in your repository configuration to control containers:

**Pre-backup script example:**
```bash
#!/bin/bash
# Install Docker CLI if not present
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
fi

# Stop database container
docker stop postgres-db
```

**Post-backup script example:**
```bash
#!/bin/bash
# Restart database container
docker start postgres-db
```

See the **[Docker Container Hooks Guide](../docs/docker-hooks.md)** for detailed examples, security considerations, and best practices.

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

### Wrong Timestamps in Archives

If archive timestamps show UTC instead of your local time:

```yaml
environment:
  - TZ=Asia/Kolkata  # Add your timezone
```

Then restart:
```bash
docker compose down && docker compose up -d
```

Verify:
```bash
docker exec borg-web-ui date
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
