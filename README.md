
[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borg-ui)](https://hub.docker.com/r/ainullcode/borg-ui)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)
[![Tests](https://github.com/karanhudia/borg-ui/workflows/Tests/badge.svg)](https://github.com/karanhudia/borg-ui/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/karanhudia/borg-ui/branch/main/graph/badge.svg)](https://codecov.io/gh/karanhudia/borg-ui)

A modern, user-friendly web interface for [Borg Backup](https://borgbackup.readthedocs.io/) management. **Zero-configuration deployment** - just run `docker compose up` and you're done!

📚 **[Full Documentation](https://karanhudia.github.io/borg-ui)** | 🐳 **[Docker Hub](https://hub.docker.com/r/ainullcode/borg-ui)**

---

## Why This Exists

I love [Borg Backup](https://borgbackup.readthedocs.io/) - it's powerful, efficient, and reliable. But let's be honest: **the terminal interface is complicated**.

Every time I wanted to:
- Create a backup → Remember the exact `borg create` syntax with all the flags
- Browse archives → Parse verbose terminal output to find what I need
- Restore files → Navigate complex paths and remember extraction commands
- Schedule backups → Write and debug cron jobs manually
- Manage SSH keys → Deal with permissions and deployment across servers

**It was exhausting.** I found myself constantly referring to documentation, copy-pasting commands from notes, and making mistakes that could have been avoided with a simple UI.

So I built Borg Web UI - not to replace Borg's power, but to make it **accessible**. A web interface that handles the complexity while you focus on what matters: keeping your data safe.

### Project Goals

- 🎯 **Simplicity First** - If you can click it, you shouldn't have to type it
- 🚀 **Zero Configuration** - No manual setup, no environment files to edit, just `docker compose up`
- 🔒 **Secure by Default** - Auto-generated secrets, JWT authentication, permission controls
- 📱 **Works Everywhere** - Desktop, tablet, mobile, Raspberry Pi, NAS, cloud servers
- 🌐 **Real-time Feedback** - Live backup progress, instant logs, responsive dashboards
- 💾 **Data Safety** - Never lose your backups or configuration, everything persists

This project solves my personal backup management headaches, and I hope it solves yours too.

---

## Screenshots

### Dashboard

<img width="800" alt="dashboard" src="https://github.com/user-attachments/assets/9478189e-4b47-46ae-b672-ad77df6d7040" />

*Real-time system monitoring with Borg status, CPU, memory, and disk usage metrics, plus recent backup job history*

### Backup Operations
<img width="800" alt="backup-live-progress" src="https://github.com/user-attachments/assets/550e396e-ec36-4737-9821-899c99265f64" />

*Live backup progress tracking showing current file being processed, files count, original size, compressed size, and deduplicated data*

### Repository Management
<img width="800" alt="repository-details" src="https://github.com/user-attachments/assets/4d85cc2f-cfe6-489f-bdb9-67c1ca2e4035" />

*Repository overview showing SSH connection details, compression settings, archive count, and configured source paths*

<img width="800" alt="create-repository" src="https://github.com/user-attachments/assets/d7bba4d2-0fec-4257-8aa2-f72ccfeeb30a" />

*Intuitive repository creation with command preview, encryption options, compression settings, and source directory configuration*
<img width="800" alt="Screenshot 2025-10-31 at 6 36 22 PM" src="https://github.com/user-attachments/assets/52579dae-54d1-4aaf-ad10-aebe93be7d6d" /># Borg Web UI

### Archive Management

<img width="800" alt="archive-view" src="https://github.com/user-attachments/assets/617f6ef5-0bbc-468b-981a-7e6bf8065986" />
<img width="800" alt="archive-explorer" src="https://github.com/user-attachments/assets/92384dcc-b272-444e-b11b-b970d176ccd2" />

### Restore

<img width="800" alt="restore" src="https://github.com/user-attachments/assets/912f8b1d-67e7-44bf-86a1-d36730c7ed05" />

### Scheduling

<img width="800" alt="schedule" src="https://github.com/user-attachments/assets/6ec49db9-8b68-4131-9c19-b102ab77a8c4" />

---

## Table of Contents

- [Features](#features)
- [Installation Methods](#installation-methods)
  - [Method 1: Portainer](#method-1-portainer-recommended)
  - [Method 2: Docker Run](#method-2-docker-run)
  - [Method 3: Docker Compose](#method-3-docker-compose)
- [Mounting Host Filesystem](#mounting-host-filesystem)
- [Configuration](#configuration)
- [Data Persistence](#data-persistence)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [License](#license)
- [Support](#support)

---

## Features

### Core Functionality
- 🎯 **Intuitive Dashboard** - Real-time backup status and system metrics
- 📁 **Backup Management** - Create, schedule, and monitor backups with ease
- 🔍 **Archive Browser** - Browse and restore files from any backup
- 🗂️ **Repository Management** - Support for local, SSH, and SFTP repositories
- 🔐 **SSH Key Management** - Generate, import, and deploy SSH keys securely
- ⏰ **Scheduling** - Visual cron job builder with execution history
- 📊 **Health Monitoring** - System health checks and performance analytics
- 📝 **Log Management** - Real-time log streaming with search and filtering

### Technical Highlights
- ⚡ **Zero Configuration** - No manual SECRET_KEY generation or environment setup required!
- 🔒 **Auto-Secured** - SECRET_KEY automatically generated and persisted on first run
- 📱 **Responsive Design** - Works seamlessly on desktop, tablet, and mobile
- 🌐 **Multi-platform** - Supports amd64, arm64, and armv7 architectures
- 🚀 **Production Ready** - Battle-tested on Raspberry Pi, NAS, and cloud servers

---

## Prerequisites

- Docker installed on your system
- 512MB RAM minimum (1GB recommended)
- Network access to backup destinations

### Default Credentials

After installation, access the web interface at `http://localhost:8081`

- **Username**: `admin`
- **Password**: `admin123`

⚠️ **Change the default password immediately after first login!**

---

## Installation Methods

### Method 1: Portainer (Recommended)

Portainer is the easiest way to deploy with a visual interface.

#### Step 1: Add Stack in Portainer

1. Go to **Stacks** > **Add Stack**
2. Name your stack: `borg-ui`
3. Paste the following:

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
      - ${LOCAL_STORAGE_PATH:-/}:/local:rw

    environment:
      - PUID=1000  # Optional: Your user ID (run: id -u)
      - PGID=1000  # Optional: Your group ID (run: id -g)

volumes:
  borg_data:
    name: borg_data
```

#### Step 2: Deploy Stack

Click **Deploy the stack** and wait 30-60 seconds. That's it!

#### Step 3: Access Application

Open `http://your-server-ip:8081` and login with default credentials.

---

### Method 2: Docker Run

For quick deployment using Docker CLI.

#### Step 1: Create Docker Volume

```bash
docker volume create borg_data
```

#### Step 2: Run Container

```bash
docker run -d \
  --name borg-web-ui \
  --restart unless-stopped \
  -p 8081:8081 \
  -e PUID=1000 \
  -e PGID=1000 \
  -v borg_data:/data \
  -v /:/local:rw \
  ainullcode/borg-ui:latest
```

**Note:** Replace `1000` with your user/group ID. Find yours with `id -u && id -g`

#### Step 3: Verify Container is Running

```bash
docker ps | grep borg-web-ui
docker logs borg-web-ui
```

#### Step 4: Access Application

Open `http://localhost:8081` and login.

---

### Method 3: Docker Compose

For infrastructure-as-code deployments.

#### Step 1: Create Project Directory

```bash
mkdir borg-ui && cd borg-ui
```

#### Step 2: Create `docker-compose.yml`

```yaml
version: '3.8'

services:
  app:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped

    ports:
      - "${PORT:-8081}:8081"

    volumes:
      - borg_data:/data
      - ${LOCAL_STORAGE_PATH:-/}:/local:rw

    environment:
      - PUID=${PUID:-1001}  # Your user ID (run: id -u)
      - PGID=${PGID:-1001}  # Your group ID (run: id -g)
      # Optional: Override defaults (create .env file)
      # - PORT=8082
      # - LOG_LEVEL=DEBUG

volumes:
  borg_data:
    name: borg_data
```

#### Step 3: Start Services

```bash
docker compose up -d
```

#### Step 4: View Logs (Optional)

```bash
docker compose logs -f app
```

#### Step 5: Access Application

Open `http://localhost:8081` and login.

---

## Mounting Host Filesystem

### Why Mount Host Filesystem?

The container automatically mounts your host filesystem at `/local` to:
- Access external drives, NAS mounts, or network storage for repositories
- Keep repositories outside the container (survive container rebuilds)
- Better performance for local/LAN storage vs SSH
- Simpler setup than SSH for local storage

### Default Configuration

By default, the container mounts:
- **All Systems**: `/` (root filesystem) → `/local` in container with read-write access
- **Custom**: Any directory via `LOCAL_STORAGE_PATH` environment variable

⚠️ **Security Consideration**: The default configuration mounts the entire host filesystem with read-write access. While this provides maximum flexibility for backup operations, you should customize the mount based on your specific needs and security requirements.

### Customizing Volume Mounts (Recommended for Security)

Instead of mounting the entire filesystem, you can restrict access to specific directories:

**Step 1**: Customize the mount in your `docker-compose.yml`:

```yaml
volumes:
  # Option 1: Mount specific backup source and destination directories
  - /home/user/my/source/repo:/source:ro    # Source: read-only
  - /home/user/my/destination:/destination:rw  # Destination: read-write

  # Option 2: Mount only user directories (Linux)
  - /home:/local:rw

  # Option 3: Mount only user directories (macOS)
  - /Users:/local:rw

  # Option 4: Mount only NAS or external storage
  - /mnt/nas:/local:rw

  # Option 5: Mount specific backup directories
  - /mnt/backup-storage:/local:rw
```

Or use the `LOCAL_STORAGE_PATH` environment variable in `.env`:

```bash
# Only mount specific directories you need for backups
LOCAL_STORAGE_PATH=/home/user/backups

# Examples for different use cases:
# LOCAL_STORAGE_PATH=/Users        # Only user directories (macOS)
# LOCAL_STORAGE_PATH=/home          # Only user directories (Linux)
# LOCAL_STORAGE_PATH=/mnt/nas       # Only NAS mount point
# LOCAL_STORAGE_PATH=/mnt/backups   # Only backup storage location
```

**Step 2**: Update repository paths in the UI based on your mount configuration

Examples with customized mounts:

| Mount Configuration | Repository Path in UI |
|---------------------|----------------------|
| `/home:/local:rw` | `/local/username/backups/my-repo` |
| `/Users:/local:rw` | `/local/username/backups/my-repo` |
| `/mnt/nas:/local:rw` | `/local/borg-backups/my-repo` |
| `/home/user/my/destination:/destination:rw` | `/destination/my-repo` |

Examples with default `/` mount:
- **macOS**: `/local/Users/your-username/backups/my-repo`
- **Linux**: `/local/home/your-username/backups/my-repo`
- **External Drive**: `/local/mnt/external-drive/backups/important-data`
- **NAS**: `/local/mnt/nas-mount/borg-backups/project-repo`

### Security Best Practices

1. **Principle of Least Privilege**: Only mount directories that are necessary for your backup operations
2. **Use Read-Only Mounts for Source Data**: When backing up data, mount source directories as read-only (`:ro`) to prevent accidental modifications:
   ```yaml
   volumes:
     - /home/user/documents:/source:ro
     - /mnt/backup-drive:/destination:rw
   ```
3. **Separate Source and Destination**: Keep backup sources and backup destinations on separate mounts with appropriate permissions
4. **Audit Your Setup**: Before deploying to production, review what directories are mounted and whether the container truly needs access to them
5. **Container Runs as Non-Root**: The container runs as user `borg` (configurable via PUID/PGID) which provides an additional security layer

### Why the Default Mounts Root Filesystem

The default configuration (`/:/local:rw`) is designed for:
- **Quick Start Experience**: Works out-of-the-box without configuration
- **Maximum Flexibility**: Access any directory for backups without reconfiguration
- **Docker Container Isolation**: The container itself provides isolation from the host

However, for production deployments or security-conscious environments, we **strongly recommend** customizing the volume mounts to restrict access to only the directories you need.

### For Remote Storage (Raspberry Pi, NAS)

If your remote storage is already mounted on your host machine via NFS/CIFS/SMB:

```bash
# Example: Mount Raspberry Pi via NFS (on host machine)
sudo mount -t nfs 192.168.1.250:/home/pi /mnt/raspberry-pi

# Or mount via SMB/CIFS
sudo mount -t cifs //192.168.1.250/share /mnt/raspberry-pi -o username=pi
```

Then set in `.env`:
```bash
LOCAL_STORAGE_PATH=/mnt/raspberry-pi
```

Repositories created at `/local/backups/repo-name` will be stored on your Raspberry Pi!

---

## Configuration

### Auto-Configured Settings

The following are **automatically configured** on first run:

| Setting | Auto-Configuration |
|---------|-------------------|
| **SECRET_KEY** | Randomly generated (32 bytes), persisted to `/data/.secret_key` |
| **DATABASE_URL** | Auto-derived as `sqlite:///data/borg.db` |
| **LOG_FILE** | Auto-derived as `/data/logs/borg-ui.log` |
| **SSH_KEYS_DIR** | Auto-derived as `/data/ssh_keys` |

### Optional Environment Variables

You can override defaults if needed:

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Application port | `8081` |
| `ENVIRONMENT` | Environment mode | `production` |
| `LOG_LEVEL` | Logging level | `INFO` |

Example with overrides:

```yaml
environment:
  - PORT=8082
  - LOG_LEVEL=DEBUG
```

### Backup Repository Configuration

**Important**: You configure backup repositories directly through the web UI, not via Docker volumes!

Repositories can be:
- **Local paths**: `/local/mnt/backup`, `/local/external-drive/backups` (see [Mounting Host Filesystem](#mounting-host-filesystem))
- **SSH/SFTP**: `user@host:/path/to/repo`
- **Cloud storage**: S3, Azure, Google Cloud (via rclone)

No need for a separate `borg_backups` volume!

---

## Data Persistence

### Single Volume for Everything

Only one volume is needed:

**`borg_data`** - Contains:
- SQLite database (`borg.db`)
- Auto-generated SECRET_KEY (`.secret_key`)
- SSH keys
- Configuration files
- Application logs

### Viewing Volume Data

```bash
docker run --rm -v borg_data:/data alpine ls -la /data
```

### Backup and Restore Volume

```bash
# Backup borg_data to tar file
docker run --rm -v borg_data:/data -v $(pwd):/backup alpine tar czf /backup/borg_data_backup.tar.gz -C /data .

# Restore borg_data from tar file
docker run --rm -v borg_data:/data -v $(pwd):/backup alpine tar xzf /backup/borg_data_backup.tar.gz -C /data
```

### Mounting to Custom Location

```yaml
volumes:
  borg_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/storage/borg-data
```

---

## Documentation

📚 **[Full Documentation Site](https://karanhudia.github.io/borg-ui)** - Complete guides, tutorials, and references

### Additional Resources

- **[System Design](SYSTEM_DESIGN.md)** - Architecture and workflow design
- **[Implementation Tasks](IMPLEMENTATION_TASKS.md)** - Development progress
- **[Security Guide](SECURITY.md)** - Security best practices
- **[API Documentation](http://localhost:8081/api/docs)** - Interactive API docs (after installation)

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
environment:
  - PORT=8082
```

### Data Lost After Container Removal

Ensure you're using a Docker volume (not bind mount). The database must be at `/data/borg.db` inside the volume.

### Permission Issues

The container runs as user `borg` with **configurable UID/GID** (default: 1001:1001).

#### Quick Fix: Match your host user (LinuxServer.io style)

Set PUID/PGID environment variables to match your host user:

1. Find your UID/GID:
   ```bash
   id -u && id -g
   ```

2. Set environment variables in your deployment:

**Portainer:**
```yaml
environment:
  - PUID=1000  # Your user ID
  - PGID=1000  # Your group ID
```

**Docker Compose (.env file):**
```bash
# Raspberry Pi / Linux (usually 1000:1000)
PUID=1000
PGID=1000
```

**Docker Run:**
```bash
docker run -d \
  -e PUID=1000 \
  -e PGID=1000 \
  ainullcode/borg-ui:latest
```

3. Restart container:
   ```bash
   docker-compose down && docker-compose up -d
   # or for Portainer: Update Stack
   ```

The container will automatically update the internal user's UID/GID on startup!

#### Why This Matters

- Borg often needs access to system files (owned by root or other users)
- Container user must match host user for `/local` mount permissions
- Wrong UID/GID = "Permission denied" errors when creating repositories

#### For System-Wide Backups

If you need to back up files owned by multiple users or root:

1. **Run container with matching UID** (recommended above)
2. **Use SSH repositories** to backup remote systems
3. **Grant sudo access** to container user on specific borg commands (already configured)

### SECRET_KEY Rotation

To rotate the SECRET_KEY:
```bash
docker exec borg-web-ui rm /data/.secret_key
docker restart borg-web-ui
```

A new SECRET_KEY will be generated automatically. Note: This will invalidate all existing user sessions.

---

## Development

**For developers who want to contribute or modify the code.**

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for frontend development)
- Python 3.9+ (for backend development)

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/karanhudia/borg-ui.git
   cd borg-ui
   ```

2. **Copy environment file (optional for local dev):**
   ```bash
   cp .env.example .env
   ```

3. **Start development environment:**
   ```bash
   docker compose up -d --build
   ```

4. **Access the application:**
    - Frontend: `http://localhost:8081`
    - API Docs: `http://localhost:8081/api/docs`

### Development Workflow

**Backend Development:**
```bash
# View backend logs
docker compose logs -f app

# Run backend tests
docker compose exec app pytest

# Access Python shell
docker compose exec app python
```

**Frontend Development:**
```bash
# Install dependencies
cd frontend && npm install

# Start dev server (with hot reload)
npm run dev

# Build for production
npm run build

# Run tests
npm test
```

### Testing

Borg UI has a comprehensive test suite covering backend API, integration tests, and end-to-end workflows.

**Quick Start:**
```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests with coverage
pytest

# Run only unit tests (fast)
pytest -m "not requires_ui"

# Run integration tests (requires Borg UI running)
pytest -m integration
```

**Test Categories:**

1. **Unit Tests** (`tests/`) - Fast, no external dependencies
   - Archive browsing logic
   - Directory navigation
   - Multiple source directories

2. **Integration Tests** (`test_app.py`) - Requires running server
   - API endpoints
   - Authentication
   - Repository operations
   - Config validation
   - Health checks

3. **End-to-End Tests** - Full workflow testing
   - Backup operations
   - Archive contents validation
   - Restore operations

**Coverage Reports:**

View coverage locally:
```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

**CI/CD:**

Tests run automatically on every push and pull request via GitHub Actions:
- Backend unit tests with coverage
- Integration tests with real Borg repositories
- Frontend build verification
- Coverage reports uploaded to Codecov

See [tests/README.md](tests/README.md) for detailed testing documentation.

### Project Structure

```
borg-ui/
├── app/                    # Backend (FastAPI)
│   ├── api/               # API endpoints
│   ├── database/          # Database models
│   ├── services/          # Business logic
│   ├── config.py          # Auto-configuration logic
│   └── main.py            # Application entry point
├── frontend/              # Frontend (React + TypeScript)
│   ├── src/
│   │   ├── components/   # Reusable components
│   │   ├── pages/        # Page components
│   │   ├── services/     # API clients
│   │   └── App.tsx       # Root component
│   └── package.json
├── docker-compose.yml     # Simplified Docker Compose
├── Dockerfile             # Multi-stage Docker build
└── .env.example           # Development-only template
```

### Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for guidelines.

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

## Support

### Getting Help

- 📖 **Documentation**: [Full Documentation Site](https://karanhudia.github.io/borg-ui)
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)
- 📧 **Contact**: Open an issue for support

### Resources

- **Official Repository**: https://github.com/karanhudia/borg-ui
- **Documentation Site**: https://karanhudia.github.io/borg-ui
- **Docker Hub**: https://hub.docker.com/r/ainullcode/borg-ui
- **Borg Backup Docs**: https://borgbackup.readthedocs.io/

---

## Acknowledgments

Built with:
- [Borg Backup](https://borgbackup.readthedocs.io/) - Deduplication backup program
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [Material-UI](https://mui.com/) - UI components

---

**Made with ❤️ by [Karan Hudia](https://github.com/karanhudia) (ainullcode)**

© 2025 Karan Hudia. All Rights Reserved.
