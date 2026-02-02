<div align="center">
  
**A modern web interface for [Borg Backup](https://borgbackup.readthedocs.io/)**

Zero-configuration deployment - just run and go.

**[📚 Documentation](https://karanhudia.github.io/borg-ui)** • **[🐳 Docker Hub](https://hub.docker.com/r/ainullcode/borg-ui)** • **[💬 Discord](https://discord.gg/5KfVa5QkdQ)**

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borg-ui)](https://hub.docker.com/r/ainullcode/borg-ui)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)
[![Tests](https://github.com/karanhudia/borg-ui/workflows/Tests/badge.svg)](https://github.com/karanhudia/borg-ui/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/karanhudia/borg-ui/branch/main/graph/badge.svg)](https://codecov.io/gh/karanhudia/borg-ui)
[![Discord](https://img.shields.io/discord/1331215029498732686?color=5865F2&logo=discord&logoColor=white&label=Discord)](https://discord.gg/5KfVa5QkdQ)

</div>

---

> [!NOTE]
> This project uses [Claude Code](https://claude.ai/code) as a development assistant. I'm a full-stack developer with 10+ years of experience, and I personally review all AI-generated code before merging. Architecture decisions, security practices, and testing are human-driven. Claude Code is acknowledged as a co-author in git commits. All code is open source for community review - your backups deserve scrutiny, and I encourage it.

---

## Features & Screenshots

### Modern Dashboard

Monitor all your repositories, backup status, and system metrics at a glance. View repository health, recent activity feed, storage usage, and quick access to common operations. Get a comprehensive overview of your entire backup infrastructure in one place.

<div align="center">
  <img width="800" alt="Modern Dashboard with activity monitoring" src="https://github.com/user-attachments/assets/3e9c7ae6-1507-4fe1-8f8b-8231a458bca0" />
</div>

---

### Live Backup Progress

Watch your backups execute in real-time with detailed progress tracking. Monitor current file being processed, backup speed (MB/s), data statistics (original, compressed, deduplicated sizes), estimated time remaining, and overall completion percentage.

<div align="center">
  <img width="800" alt="Real-time backup progress with live metrics" src="https://github.com/user-attachments/assets/de7e870a-2db9-4384-be71-59e8bdd67373" />
</div>

---

### Repository Management

Create and manage repositories with support for local storage, SSH, and SFTP connections. Configure encryption (repokey, keyfile), compression algorithms (lz4, zstd, zlib, lzma, auto, obfuscate), source directories, exclude patterns, and custom borg flags. Import existing repositories or create new ones with step-by-step wizard.

<div align="center">
  <img width="800" alt="Repository details" src="https://github.com/user-attachments/assets/bddfae3c-4bd6-473f-aa5e-5e2cf3d54f4b" />
  <img width="800" alt="Create Repository Dialog" src="https://github.com/user-attachments/assets/f6b56ebb-0edf-4910-98ba-53021a7bd4cd" />
</div>

---

### Smart Notifications

Get instant alerts for backup events via 100+ notification services powered by Apprise. Configure Email, Slack, Discord, Telegram, Pushover, Microsoft Teams, and many more. Set up per-repository notification preferences with customizable templates for backup start, success, failure, and warnings.

<div align="center">
  <img width="800" alt="Notification settings with 100+ integrations" src="https://github.com/user-attachments/assets/1ae11394-d4d1-4fc8-b501-965dd5bc9743" />
</div>

---

### Archive Browsing

Browse and restore files from any backup archive with 600x faster performance using Redis caching. Navigate through your backup history, preview file contents, and restore individual files or entire directories.

<div align="center">
  <img width="800" alt="Archive Browsing" src="https://github.com/user-attachments/assets/5c42bb10-cfc4-468b-bfd3-bd403ba29516" />
</div>

---

### Schedule Management

Create and manage automated backup schedules with visual cron builder. Configure multi-repository backups, set up pre/post scripts, enable automatic pruning and compacting, and track execution history with detailed logs.

<div align="center">
  <img width="800" alt="Create and View Schedule Tab" src="https://github.com/user-attachments/assets/ab824ea3-afca-4872-85b9-77781e393b97" />
</div>

---

## Key Features

- **Backup Management** - Create, schedule, and monitor backups with live progress tracking
- **Archive Browser** - Browse and restore files from any backup archive with Redis caching (600x faster for large repos)
- **Repository Management** - Support for local, SSH, and SFTP repositories with multiple compression options
- **Scheduling** - Visual cron job builder with execution history
- **Pre/Post Backup Hooks** - Run custom scripts before/after backups (e.g., stop Docker containers, database dumps)
- **Notifications** - Get alerts via 100+ services (Email, Slack, Discord, Telegram, Pushover, etc.)
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
      # Mount directories you want to backup (REPLACE with your actual paths)
      - /home/yourusername:/local:rw           # Replace with your directory path
      # - /mnt/data:/local/data:rw             # Additional directories as needed
    environment:
      - TZ=America/Chicago  # Set your timezone
      - PUID=1000
      - PGID=1000

volumes:
  borg_data:
  borg_cache:
```

**⚠️ Security Note:** Replace `/home/yourusername` with your actual directory path. Only mount directories you want to backup. See the [Configuration Guide](https://karanhudia.github.io/borg-ui/configuration) for more examples and security best practices.

**📝 Remote-to-Remote Backups:** Backing up from one remote machine to another (via SSH URLs) is supported out-of-the-box. The docker-compose.yml includes FUSE support for mounting remote filesystems.

Start the container:

```bash
docker compose up -d
```

Access at `http://localhost:8081`

**Default credentials:** `admin` / `admin123` (you'll be prompted to change on first login)

---

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
  --cap-add SYS_ADMIN \
  --device /dev/fuse \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/yourusername:/local:rw \
  ainullcode/borg-ui:latest
```

**Notes:**
- Replace `/home/yourusername` with your actual directory path (e.g., `/home/john`, `/Users/sarah`, `/mnt/data`)
- Replace `1000` with your user/group ID. Find yours with `id -u && id -g`
- Add more `-v` flags for additional directories you want to backup
- See [Configuration Guide](https://karanhudia.github.io/borg-ui/configuration) for security best practices

---

## Documentation

**[Full Documentation](https://karanhudia.github.io/borg-ui)** - Complete guides and tutorials

- [Installation Guide](https://karanhudia.github.io/borg-ui/installation) - Detailed installation for all platforms
- [Configuration Guide](https://karanhudia.github.io/borg-ui/configuration) - Environment variables and setup options
- [Docker Container Hooks](docs/docker-hooks.md) - Stop/start Docker containers during backups
- [Notifications Setup](https://karanhudia.github.io/borg-ui/notifications) - Configure alerts via email, Slack, Discord, and more
- [SSH Keys Guide](https://karanhudia.github.io/borg-ui/ssh-keys) - Setting up SSH for remote backups
- [Security Guide](https://karanhudia.github.io/borg-ui/security) - Best practices and security recommendations
- [API Documentation](http://localhost:8081/api/docs) - Interactive API docs (after installation)

---

## Configuration

### Auto-Configured on First Run

- **SECRET_KEY** - Randomly generated and persisted
- **Database** - SQLite at `/data/borg.db` (includes encrypted SSH keys)
- **SSH Keys** - Stored encrypted in database, deployed to `/home/borg/.ssh` at runtime

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

### Volume Mounts for Backup Sources

**⚠️ Important Security Consideration:**

The container needs access to directories you want to backup. Instead of mounting your entire filesystem (`/:/local:rw`), **mount only specific directories** you need:

```yaml
volumes:
  # ✅ Recommended: Mount specific directories
  - /home/yourusername:/local:rw       # Replace with your path
  - /mnt/data:/local/data:rw           # Additional directories

  # ❌ NOT Recommended: Full filesystem access
  # - /:/local:rw  # Security risk - avoid unless absolutely necessary
```

**Best Practices:**
- Mount only directories that contain data to backup
- Use read-only (`:ro`) for backup-only directories if you don't need to restore to them
- For multiple directories, add multiple volume mounts instead of mounting root
- See the [Configuration Guide](https://karanhudia.github.io/borg-ui/configuration/) for detailed examples

---

## Support

- **Discord**: [Join our community](https://discord.gg/5KfVa5QkdQ) - Get help, share your setup, suggest features
- **Documentation**: [Full Documentation](https://karanhudia.github.io/borg-ui)
- **Bug Reports**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)

---

## Development

For developers who want to contribute:

### Quick Start (Docker - No Hot Reload)

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
docker compose up -d --build
```

### Development with Hot Reload

For active development with automatic code reloading.

**Prerequisites:** Python 3.11+, Node.js 20.19+, Redis (or Docker for Redis only)

```bash
# Run everything with one command (starts Redis, backend, and frontend)
./scripts/dev.sh

# Or run frontend and backend separately:
./scripts/backend-dev.sh  # Terminal 1: Backend on :8081
cd frontend && npm run dev  # Terminal 2: Frontend on :7879
```

- Frontend: http://localhost:7879 (Vite HMR)
- Backend: http://localhost:8081 (Uvicorn reload)

See [Development Guide](https://karanhudia.github.io/borg-ui/development) for detailed setup.

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for contribution guidelines.

---

## License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Built with [Borg Backup](https://borgbackup.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), and [Material-UI](https://mui.com/)

Made with ❤️ by [Karan Hudia](https://github.com/karanhudia)

</div>
