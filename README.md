# Borgmatic Web UI

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borgmatic-ui)](https://hub.docker.com/r/ainullcode/borgmatic-ui)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)

A modern, user-friendly web interface for [Borgmatic](https://torsion.org/borgmatic/) backup management. **Zero-configuration deployment** - just run `docker compose up` and you're done!

**Official Repository**: https://github.com/karanhudia/borg-ui

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation Methods](#installation-methods)
  - [Method 1: Portainer](#method-1-portainer-recommended)
  - [Method 2: Docker Run](#method-2-docker-run)
  - [Method 3: Docker Compose](#method-3-docker-compose)
- [Configuration](#configuration)
- [How to Use with Different Systems](#how-to-use-with-different-systems)
  - [Raspberry Pi Setup](#raspberry-pi-setup)
  - [macOS Setup](#macos-setup)
  - [Linux Setup](#linux-ubuntudebian-setup)
  - [NAS Setup](#nas-synologyqnap-setup)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)
- [API Reference](#api-reference)
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

## Quick Start

### Prerequisites
- Docker installed on your system
- 512MB RAM minimum (1GB recommended)
- Network access to backup destinations

### 30-Second Deployment

```bash
# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  app:
    image: ainullcode/borgmatic-ui:latest
    container_name: borgmatic-web-ui
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - borg_data:/data
      - ${LOCAL_STORAGE_PATH:-/}:/local:rw  # Access host filesystem

volumes:
  borg_data:
EOF

# Start the container
docker compose up -d

# That's it! Everything else is auto-configured.
```

### Default Credentials
Access the web interface at `http://localhost:8081`

- **Username**: `admin`
- **Password**: `admin123`

⚠️ **Change the default password immediately after first login!**

---

## Installation Methods

### Method 1: Portainer (Recommended)

Portainer is the easiest way to deploy with a visual interface.

#### Step 1: Add Stack in Portainer

1. Go to **Stacks** > **Add Stack**
2. Name your stack: `borgmatic-ui`
3. Paste the following:

```yaml
version: '3.8'

services:
  borgmatic-ui:
    image: ainullcode/borgmatic-ui:latest
    container_name: borgmatic-web-ui
    restart: unless-stopped

    ports:
      - "8081:8081"

    volumes:
      - borg_data:/data
      - ${LOCAL_STORAGE_PATH:-/}:/local:rw

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
  --name borgmatic-web-ui \
  --restart unless-stopped \
  -p 8081:8081 \
  -v borg_data:/data \
  -v /:/local:rw \
  ainullcode/borgmatic-ui:latest
```

#### Step 3: Verify Container is Running

```bash
docker ps | grep borgmatic-web-ui
docker logs borgmatic-web-ui
```

#### Step 4: Access Application

Open `http://localhost:8081` and login.

---

### Method 3: Docker Compose

For infrastructure-as-code deployments.

#### Step 1: Create Project Directory

```bash
mkdir borgmatic-ui && cd borgmatic-ui
```

#### Step 2: Create `docker-compose.yml`

```yaml
version: '3.8'

services:
  app:
    image: ainullcode/borgmatic-ui:latest
    container_name: borgmatic-web-ui
    restart: unless-stopped

    ports:
      - "${PORT:-8081}:8081"

    volumes:
      - borg_data:/data
      - ${LOCAL_STORAGE_PATH:-/}:/local:rw

    # Optional: Override defaults
    # environment:
    #   - PORT=8082
    #   - LOG_LEVEL=DEBUG
    #   - LOCAL_STORAGE_PATH=/home  # Linux users

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

## Configuration

### Auto-Configured Settings

The following are **automatically configured** on first run:

| Setting | Auto-Configuration |
|---------|-------------------|
| **SECRET_KEY** | Randomly generated (32 bytes), persisted to `/data/.secret_key` |
| **DATABASE_URL** | Auto-derived as `sqlite:///data/borgmatic.db` |
| **BORGMATIC_CONFIG_PATH** | Auto-derived as `/data/config/borgmatic.yaml` |
| **LOG_FILE** | Auto-derived as `/data/logs/borgmatic-ui.log` |
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

**Important**: You configure backup repositories in the borgmatic config file through the web UI, not via Docker volumes!

Repositories can be:
- **Local paths**: `/mnt/backup`, `/external-drive/backups`
- **SSH/SFTP**: `user@host:/path/to/repo`
- **Cloud storage**: S3, Azure, Google Cloud (via rclone)

No need for a separate `borg_backups` volume!

### Accessing Host Filesystem for Repositories

**Built-in Feature**: The container automatically mounts your host filesystem at `/local` for easy repository access.

#### Why Host Filesystem Mount?

- Repositories survive container rebuilds
- Access external drives, NAS mounts, or network storage
- Simpler than SSH for local or network-attached storage
- Better performance for local/LAN storage

#### Default Configuration

By default, the container mounts:
- **All Systems**: `/` (root filesystem) → `/local` in container
- **Custom**: Any directory via `LOCAL_STORAGE_PATH` environment variable (e.g., `/Users`, `/home`, `/mnt/nas`)

#### Setup Instructions

**Step 1**: (Optional) Customize the mount path by creating `.env` file:

```bash
# .env
# Default: Entire filesystem (/)
# LOCAL_STORAGE_PATH=/

# Custom examples:
# LOCAL_STORAGE_PATH=/Users        # Only user directories (macOS)
# LOCAL_STORAGE_PATH=/home          # Only user directories (Linux)
# LOCAL_STORAGE_PATH=/mnt/nas       # Only NAS mount point
```

**Step 2**: Restart the container (only if you changed the mount path):

```bash
docker compose down
docker compose up -d
```

**Step 3**: Create repositories in the UI using `/local/` prefix:

Examples (with default `/` mount):
- **macOS**: `/local/Users/your-username/backups/my-repo`
- **Linux**: `/local/home/your-username/backups/my-repo`
- **External Drive**: `/local/mnt/external-drive/backups/important-data`
- **NAS**: `/local/mnt/nas-mount/borg-backups/project-repo`

#### For Remote Storage (Raspberry Pi, NAS)

If your Raspberry Pi or NAS is already mounted on your host machine via NFS/CIFS/SMB:

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

Repositories created at `/local/backups/repo-name` will actually be stored on your Raspberry Pi!

---

## How to Use with Different Systems

### Raspberry Pi Setup

**Complete workflow for Raspberry Pi users:**

#### Step 1: Deploy on Raspberry Pi

1. **Pull the latest Docker image:**
   ```bash
   docker pull ainullcode/borgmatic-ui:latest
   ```

2. **Find your Raspberry Pi user's UID/GID:**
   ```bash
   id -u && id -g
   # Usually outputs: 1000 and 1000
   ```

3. **Create `.env` file in your project directory:**
   ```bash
   mkdir -p ~/borgmatic-ui && cd ~/borgmatic-ui
   cat > .env << 'EOF'
   # Raspberry Pi user (usually 1000:1000)
   PUID=1000
   PGID=1000

   # Mount your home directory for easy access
   LOCAL_STORAGE_PATH=/home/pi
   EOF
   ```

4. **Create docker-compose.yml:**
   ```bash
   cat > docker-compose.yml << 'EOF'
   version: '3.8'

   services:
     app:
       image: ainullcode/borgmatic-ui:latest
       container_name: borgmatic-web-ui
       restart: unless-stopped

       build:
         args:
           - PUID=${PUID:-1001}
           - PGID=${PGID:-1001}

       ports:
         - "8081:8081"

       volumes:
         - borg_data:/data
         - ${LOCAL_STORAGE_PATH:-/}:/local:rw

   volumes:
     borg_data:
       name: borg_data
   EOF
   ```

5. **Start the container:**
   ```bash
   docker-compose up -d
   ```

6. **Verify it's running:**
   ```bash
   docker ps | grep borgmatic-web-ui
   docker logs borgmatic-web-ui
   ```

#### Step 2: Create Repositories in the UI

1. **Access the web interface:** `http://raspberry-pi-ip:8081`

2. **Login with default credentials:**
   - Username: `admin`
   - Password: `admin123`

3. **Go to Config tab** and create your borgmatic configuration

4. **Create a repository** at `/local/backups/my-repo`
   - Since `LOCAL_STORAGE_PATH=/home/pi`, this creates the repo at `/home/pi/backups/my-repo` on your Raspberry Pi
   - The container user (UID 1000) matches your Pi user (UID 1000), so no permission errors!

#### Step 3: Test Backup

1. **Go to Backup tab**
2. **Run your first backup**
3. **Check the repository** on your Pi:
   ```bash
   ls -la /home/pi/backups/my-repo
   ```

### macOS Setup

**For macOS users:**

1. **Find your macOS user's UID/GID:**
   ```bash
   id -u && id -g
   # Usually outputs: 501 and 20
   ```

2. **Create `.env` file:**
   ```bash
   # macOS user (varies by system)
   PUID=501
   PGID=20

   # Mount only your user directory
   LOCAL_STORAGE_PATH=/Users
   ```

3. **Follow the same docker-compose.yml setup as Raspberry Pi**

4. **Create repositories at:** `/local/your-username/backups/my-repo`
   - This maps to `/Users/your-username/backups/my-repo` on your Mac

### Linux (Ubuntu/Debian) Setup

**For Linux users:**

1. **Find your user's UID/GID:**
   ```bash
   id -u && id -g
   # Usually outputs: 1000 and 1000
   ```

2. **Create `.env` file:**
   ```bash
   # Linux user (usually 1000:1000)
   PUID=1000
   PGID=1000

   # Mount home directories
   LOCAL_STORAGE_PATH=/home
   ```

3. **Follow the same docker-compose.yml setup**

4. **Create repositories at:** `/local/username/backups/my-repo`

### NAS (Synology/QNAP) Setup

**For NAS users:**

1. **Find your NAS user's UID/GID:**
   ```bash
   # SSH into your NAS
   id -u && id -g
   ```

2. **Create `.env` file:**
   ```bash
   # Match your NAS user
   PUID=1024  # Example Synology UID
   PGID=100   # Example Synology GID

   # Mount your volume
   LOCAL_STORAGE_PATH=/volume1
   ```

3. **Deploy via Portainer or Docker CLI**

4. **Create repositories at:** `/local/backups/my-repo`

### Common Patterns

**Repository Locations:**

| System | LOCAL_STORAGE_PATH | Repository Path in UI | Actual Path on Host |
|--------|-------------------|----------------------|---------------------|
| **Raspberry Pi** | `/home/pi` | `/local/backups/repo` | `/home/pi/backups/repo` |
| **macOS** | `/Users` | `/local/username/backups/repo` | `/Users/username/backups/repo` |
| **Linux** | `/home` | `/local/username/backups/repo` | `/home/username/backups/repo` |
| **NAS** | `/volume1` | `/local/backups/repo` | `/volume1/backups/repo` |
| **External Drive** | `/mnt/external` | `/local/backups/repo` | `/mnt/external/backups/repo` |

**UID/GID Reference:**

| System | Typical UID | Typical GID |
|--------|------------|-------------|
| **Raspberry Pi** | 1000 | 1000 |
| **Linux (Ubuntu/Debian)** | 1000 | 1000 |
| **macOS** | 501 | 20 |
| **Synology NAS** | 1024+ | 100 |
| **QNAP NAS** | 500+ | 100 |

### Testing Your Setup

**Verify permissions are correct:**

```bash
# Create a test repository in the UI at /local/backups/test-repo

# Check ownership on host
ls -la /your/mount/point/backups/test-repo

# Should be owned by your user, not root or a mismatched UID
```

**If you see "Permission denied" errors:**

1. **Check your UID/GID in `.env` matches your host user**
2. **Rebuild the container:** `docker-compose down && docker-compose up -d --build`
3. **Verify container user:** `docker exec borgmatic-web-ui id`
4. **Check file ownership:** `ls -la /your/mount/point`

---

## Data Persistence

### Single Volume for Everything

Only one volume is needed:

**`borg_data`** - Contains:
- SQLite database (`borgmatic.db`)
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
      device: /mnt/storage/borgmatic-data
```

---

## Documentation

- **[System Design](SYSTEM_DESIGN.md)** - Architecture and workflow design
- **[Implementation Tasks](IMPLEMENTATION_TASKS.md)** - Development progress
- **[Security Guide](SECURITY.md)** - Security best practices
- **[API Documentation](http://localhost:8081/api/docs)** - Interactive API docs (after installation)

---

## API Reference

### OpenAPI Documentation

Once running, access interactive API documentation:

- **Swagger UI**: `http://localhost:8081/api/docs`
- **ReDoc**: `http://localhost:8081/api/redoc`
- **OpenAPI JSON**: `http://localhost:8081/openapi.json`

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Authenticate and get JWT token |
| `/api/backups` | GET, POST | List and create backups |
| `/api/archives` | GET | Browse backup archives |
| `/api/repositories` | GET, POST | Manage repositories |
| `/api/ssh-keys` | GET, POST | Manage SSH keys |
| `/api/schedules` | GET, POST | Manage backup schedules |
| `/api/health/system` | GET | System health check |

---

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker logs borgmatic-web-ui
```

### Port Already in Use

Change the port:
```yaml
environment:
  - PORT=8082
```

### Data Lost After Container Removal

Ensure you're using a Docker volume (not bind mount). The database must be at `/data/borgmatic.db` inside the volume.

### Permission Issues

The container runs as user `borgmatic` with **configurable UID/GID** (default: 1001:1001).

#### Quick Fix: Match your host user

**Option 1: Use .env file (Recommended)**

1. Find your UID/GID:
   ```bash
   id -u && id -g
   ```

2. Create `.env` file:
   ```bash
   # Raspberry Pi / Linux (usually 1000:1000)
   PUID=1000
   PGID=1000
   ```

3. Rebuild container:
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

**Option 2: Docker Compose with build args**

```yaml
services:
  app:
    build:
      args:
        - PUID=1000  # Your user ID
        - PGID=1000  # Your group ID
```

**Option 3: Fix permissions on host**

If you can't rebuild, fix permissions on the host:
```bash
# For specific directory
sudo chown -R 1001:1001 /local/home/karanhudia

# Or match container user to your user
docker exec borgmatic-web-ui id  # Check container UID/GID
```

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
docker exec borgmatic-web-ui rm /data/.secret_key
docker restart borgmatic-web-ui
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

### Project Structure

```
borgmatic-ui/
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

**Proprietary License - Copyright © 2025 Karan Hudia (ainullcode)**

### ✅ You CAN:
- Use this software for personal or commercial purposes
- Submit pull requests with improvements
- Report issues and bugs
- Pull and use Docker images from Docker Hub

### ❌ You CANNOT:
- Fork or copy this repository
- Create derivative works
- Redistribute the source code
- Use the code in other projects
- Remove copyright notices

See the [LICENSE](LICENSE) file for complete terms.

---

## Support

### Getting Help

- 📖 **Documentation**: Check the [docs](docs/) directory
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)
- 📧 **Contact**: Open an issue for support

### Resources

- **Official Repository**: https://github.com/karanhudia/borg-ui
- **Docker Hub**: https://hub.docker.com/r/ainullcode/borgmatic-ui
- **Borgmatic Docs**: https://torsion.org/borgmatic/
- **Borg Backup**: https://borgbackup.readthedocs.io/

---

## Acknowledgments

Built with:
- [Borgmatic](https://torsion.org/borgmatic/) - Backup automation
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [Material-UI](https://mui.com/) - UI components

---

**Made with ❤️ by [Karan Hudia](https://github.com/karanhudia) (ainullcode)**

© 2025 Karan Hudia. All Rights Reserved.
