# Borg Web UI

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borg-ui)](https://hub.docker.com/r/ainullcode/borg-ui)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)
[![Tests](https://github.com/karanhudia/borg-ui/workflows/Tests/badge.svg)](https://github.com/karanhudia/borg-ui/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/karanhudia/borg-ui/branch/main/graph/badge.svg)](https://codecov.io/gh/karanhudia/borg-ui)
[![Discord](https://img.shields.io/discord/1331215029498732686?color=5865F2&logo=discord&logoColor=white&label=Discord)](https://discord.gg/afjM9vMj)

A modern web interface for [Borg Backup](https://borgbackup.readthedocs.io/). Zero-configuration deployment - just run and go.

**[Documentation](https://karanhudia.github.io/borg-ui)** | **[Docker Hub](https://hub.docker.com/r/ainullcode/borg-ui)**

---

> [!NOTE]
> This project uses [Claude Code](https://claude.ai/code) as a development assistant. I'm a full-stack developer with 10+ years of experience, and I personally review all AI-generated code before merging. Architecture decisions, security practices, and testing are human-driven. Claude Code is acknowledged as a co-author in git commits. All code is open source for community review - your backups deserve scrutiny, and I encourage it.

---

## Screenshots

<img width="800" alt="dashboard" src="https://github.com/user-attachments/assets/3e9c7ae6-1507-4fe1-8f8b-8231a458bca0" />

<img width="800" alt="backup-live-progress" src="https://github.com/user-attachments/assets/550e396e-ec36-4737-9821-899c99265f64" />

<img width="800" alt="repository-details" src="https://github.com/user-attachments/assets/6bae3403-268a-4720-bdfa-087dc2c1df41" />

<img width="800" alt="notifications-settings" src="https://github.com/user-attachments/assets/598f59a7-8f60-4203-ab5d-0ae0ee28ab61" />

<img width="800" alt="packages-install" src="https://github.com/user-attachments/assets/68e25c1b-b6e0-4008-b6cb-e4996a2eee7e" />

---

## Features

- **Backup Management** - Create, schedule, and monitor backups with live progress tracking
- **Archive Browser** - Browse and restore files from any backup archive with Redis caching (600x faster for large repos)
- **Repository Management** - Support for local, SSH, and SFTP repositories with multiple compression options
- **Scheduling** - Visual cron job builder with execution history
- **Pre/Post Backup Hooks** - Run custom scripts before/after backups (e.g., stop Docker containers, database dumps)
- **Notifications** - Get alerts for backup failures and completions via 100+ services (Email, Slack, Discord, Telegram, Pushover, etc.)
- **SSH Key Management** - Generate, import, and deploy SSH keys for remote repositories
- **Real-time Monitoring** - Live backup progress, system metrics, and health checks
- **Multi-platform** - Supports amd64, arm64, and armv7 architectures

---

## Privacy & Analytics

Borg UI collects **anonymous usage statistics** to help us improve the product. We believe in **full transparency**:

- **[View our analytics dashboard publicly](https://analytics.nullcodeai.dev/)** - See exactly what we collect in real-time
- **Opt-out anytime** - Go to Settings → Preferences to disable
- **Self-hosted Matomo** - No third-party services, data stays with us
- **No sensitive data** - We never collect passwords, keys, backup data, or file paths

**We collect:** Page views, feature usage, browser type, screen resolution, navigation patterns

**We DON'T collect:** IP addresses, hostnames, passwords, encryption keys, backup data, file paths, cookies, or any personally identifiable information

Don't like what we're tracking? [Open an issue](https://github.com/karanhudia/borg-ui/issues) and we'll consider adjusting our practices.

Read our full [Privacy Policy](PRIVACY.md) for details. No hidden tracking, no selling data, just transparent analytics to build a better product.

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

- **Discord**: [Join our community](https://discord.gg/afjM9vMj) - Get help, share your setup, suggest features
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

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

Built with [Borg Backup](https://borgbackup.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), and [Material-UI](https://mui.com/)

Made by [Karan Hudia](https://github.com/karanhudia)
