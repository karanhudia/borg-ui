---
layout: default
title: Home
nav_order: 1
description: "A modern web interface for Borg Backup"
permalink: /
---

# Borg Web UI

A modern web interface for [Borg Backup](https://borgbackup.readthedocs.io/). Manage backups through a clean UI instead of complex terminal commands.

**[GitHub](https://github.com/karanhudia/borg-ui)** • **[Docker Hub](https://hub.docker.com/r/ainullcode/borg-ui)** • **[Latest Release](https://github.com/karanhudia/borg-ui/releases)**

---

## Quick Start

```bash
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/yourusername:/local:rw \
  ainullcode/borg-ui:latest
```

**Note:** Replace `/home/yourusername` with your actual directory path.

Access at `http://localhost:8081` • Default login: `admin` / `admin123`

See [Installation Guide](installation) for other methods and security best practices.

---

## Features

**Core Functionality**
- Backup management with live progress tracking
- Archive browser with file-level restore
- Repository management (local, SSH, SFTP)
- Visual cron scheduler
- Notifications via 100+ services (Email, Slack, Discord, Telegram, etc.)
- SSH key management
- Real-time system monitoring

**Technical**
- Zero configuration - auto-generates security keys
- Multi-platform - amd64, arm64, armv7
- Responsive design - works on mobile
- Production-ready with comprehensive test suite

---

## Documentation

### Getting Started

- **[Installation Guide](installation)** - Docker Compose, Portainer, Unraid installation
- **[Configuration Guide](configuration)** - Environment variables, volumes, permissions
- **[Usage Guide](usage-guide)** - Create your first backup

### Features

- **[Notifications Setup](notifications)** - Email, Slack, Discord, and 100+ services
- **[SSH Keys Guide](ssh-keys)** - Remote backup configuration
- **[Security Guide](security)** - Hardening and best practices

### Reference

- **[API Documentation](http://localhost:8081/api/docs)** - Interactive Swagger UI (after installation)
- **[System Specification](SPECIFICATION)** - Architecture and technical details

---

## Screenshots

### Dashboard
![Dashboard](https://github.com/user-attachments/assets/9478189e-4b47-46ae-b672-ad77df6d7040)

### Live Backup Progress
![Backup Progress](https://github.com/user-attachments/assets/550e396e-ec36-4737-9821-899c99265f64)

### Repository Management
![Repository Details](https://github.com/user-attachments/assets/4d85cc2f-cfe6-489f-bdb9-67c1ca2e4035)

---

## Installation

### Docker Compose

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
      - /home/yourusername:/local:rw  # Replace with your directory
    environment:
      - PUID=1000
      - PGID=1000

volumes:
  borg_data:
  borg_cache:
```

Start: `docker compose up -d`

**Other platforms:** [Installation Guide](installation) • **Security:** [Volume Mount Best Practices](configuration#filesystem-access)

---

## Configuration

### Environment Variables

```yaml
environment:
  - PORT=8081              # Application port
  - PUID=1000              # User ID for file permissions
  - PGID=1000              # Group ID for file permissions
  - LOG_LEVEL=INFO         # Logging level
```

### Volume Mounts

**⚠️ Security Best Practice:**

Mount only the directories you need to backup:

```yaml
volumes:
  # ✅ Recommended: Specific directories
  - /home/yourusername:/local:rw       # Replace with your path
  - /mnt/data:/local/data:rw           # Additional directories

  # ❌ NOT Recommended: Full filesystem
  # - /:/local:rw  # Avoid in production - use for testing only
```

**Common Patterns:**
- **Single directory:** `-v /home/john:/local:rw`
- **Multiple directories:** Add more `-v` flags for each directory
- **Read-only:** Use `:ro` for backup-only directories

See [Configuration Guide](configuration#filesystem-access) for detailed examples.

---

## Common Use Cases

### Home Server / NAS
Back up your Synology NAS, Unraid server, or personal data to:
- External USB drives
- Network storage
- Remote servers via SSH
- Cloud storage

### Raspberry Pi
Lightweight enough for Pi while backing up to:
- USB storage
- Another Pi on your network
- Cloud services
- NAS devices

### Production Servers
Manage infrastructure backups from one interface:
- Automated scheduled backups
- Health monitoring
- Quick file restoration
- Retention policy management

---

## Security

**Built-in Security:**
- Auto-generated SECRET_KEY on first run
- JWT authentication with secure sessions
- Runs as non-root user (configurable PUID/PGID)
- Encrypted repository support

**Best Practices:**
- Change default password immediately
- Use HTTPS in production (reverse proxy)
- Restrict volume mounts to necessary directories
- Use SSH keys (not passwords) for remote repositories
- Enable firewall rules

See [Security Guide](security) for complete recommendations.

---

## Notifications

Get alerts for backup events via:
- **Email** (Gmail, Outlook, custom SMTP)
- **Messaging** (Slack, Discord, Telegram, Microsoft Teams)
- **Push** (Pushover, Pushbullet, ntfy)
- **SMS** (Twilio, AWS SNS)
- **100+ other services** via [Apprise](https://github.com/caronc/apprise)

Configure in **Settings > Notifications** tab.

See [Notifications Setup](notifications) for detailed configuration.

---

## Support

**Documentation:** You're reading it!

**Issues:** [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)

**Discussions:** [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)

---

## License

GNU General Public License v3.0 - See [LICENSE](https://github.com/karanhudia/borg-ui/blob/main/LICENSE)

---

## Acknowledgments

Built with [Borg Backup](https://borgbackup.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), and [Material-UI](https://mui.com/)

Made by [Karan Hudia](https://github.com/karanhudia)
