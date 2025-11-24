# Borg Web UI

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borg-ui)](https://hub.docker.com/r/ainullcode/borg-ui)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)
[![Tests](https://github.com/karanhudia/borg-ui/workflows/Tests/badge.svg)](https://github.com/karanhudia/borg-ui/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/karanhudia/borg-ui/branch/main/graph/badge.svg)](https://codecov.io/gh/karanhudia/borg-ui)

A modern web interface for [Borg Backup](https://borgbackup.readthedocs.io/). Zero-configuration deployment - just run and go.

**[Documentation](https://karanhudia.github.io/borg-ui)** | **[Docker Hub](https://hub.docker.com/r/ainullcode/borg-ui)**

---

## Screenshots

<img width="800" alt="dashboard" src="https://github.com/user-attachments/assets/9478189e-4b47-46ae-b672-ad77df6d7040" />

<img width="800" alt="backup-live-progress" src="https://github.com/user-attachments/assets/550e396e-ec36-4737-9821-899c99265f64" />

<img width="800" alt="repository-details" src="https://github.com/user-attachments/assets/4d85cc2f-cfe6-489f-bdb9-67c1ca2e4035" />

---

## Features

- **Backup Management** - Create, schedule, and monitor backups with live progress tracking
- **Archive Browser** - Browse and restore files from any backup archive
- **Repository Management** - Support for local, SSH, and SFTP repositories with multiple compression options
- **Scheduling** - Visual cron job builder with execution history
- **Notifications** - Get alerts for backup failures and completions via 100+ services (Email, Slack, Discord, Telegram, Pushover, etc.)
- **SSH Key Management** - Generate, import, and deploy SSH keys for remote repositories
- **Real-time Monitoring** - Live backup progress, system metrics, and health checks
- **Multi-platform** - Supports amd64, arm64, and armv7 architectures

---

## Quick Start

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
      - TZ=America/Chicago  # Set your timezone
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

Access at `http://localhost:8081`

**Default credentials:** `admin` / `admin123` (you'll be prompted to change on first login)

### Docker Run

```bash
docker volume create borg_data
docker volume create borg_cache

docker run -d \
  --name borg-web-ui \
  --restart unless-stopped \
  -p 8081:8081 \
  -e TZ=America/Chicago \
  -e PUID=1000 \
  -e PGID=1000 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /:/local:rw \
  ainullcode/borg-ui:latest
```

**Note:** Replace `1000` with your user/group ID. Find yours with `id -u && id -g`

---

## Documentation

**[Full Documentation](https://karanhudia.github.io/borg-ui)** - Complete guides and tutorials

- [Installation Guide](https://karanhudia.github.io/borg-ui/installation) - Detailed installation for all platforms
- [Configuration Guide](https://karanhudia.github.io/borg-ui/configuration) - Environment variables and setup options
- [Notifications Setup](https://karanhudia.github.io/borg-ui/notifications) - Configure alerts via email, Slack, Discord, and more
- [SSH Keys Guide](https://karanhudia.github.io/borg-ui/ssh-keys) - Setting up SSH for remote backups
- [Security Guide](https://karanhudia.github.io/borg-ui/security) - Best practices and security recommendations
- [API Documentation](http://localhost:8081/api/docs) - Interactive API docs (after installation)

---

## Configuration

### Auto-Configured on First Run

- **SECRET_KEY** - Randomly generated and persisted
- **Database** - SQLite at `/data/borg_web_ui.db`
- **SSH Keys** - Stored in `/data/ssh_keys`

### Optional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Application port | `8081` |
| `TZ` | Timezone (e.g., `America/Chicago`, `Europe/London`, `Asia/Kolkata`) | Host timezone |
| `PUID` | User ID for file permissions | `1001` |
| `PGID` | Group ID for file permissions | `1001` |
| `LOG_LEVEL` | Logging level | `INFO` |

---

## Data Persistence

Two volumes are used for persistent data:

- **`borg_data`** - Application data, database, SSH keys, logs
- **`borg_cache`** - Borg repository caches for better performance

The container mounts your host filesystem at `/local` to access backup sources and destinations. For security, you can customize this mount to restrict access to specific directories.

See the [Configuration Guide](https://karanhudia.github.io/borg-ui/configuration/) for details.

---

## Support

- **Documentation**: [Full Documentation](https://karanhudia.github.io/borg-ui)
- **Bug Reports**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)

---

## Development

For developers who want to contribute:

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
docker compose up -d --build
```

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for guidelines.

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

Built with [Borg Backup](https://borgbackup.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), and [Material-UI](https://mui.com/)

Made by [Karan Hudia](https://github.com/karanhudia)
