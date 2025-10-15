# Borgmatic Web UI

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borgmatic-ui)](https://hub.docker.com/r/ainullcode/borgmatic-ui)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
[![GitHub Actions](https://github.com/ainullcode/borgmatic-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/ainullcode/borgmatic-ui/actions)

A modern, user-friendly web interface for [Borgmatic](https://torsion.org/borgmatic/) backup management. **Zero-configuration deployment** - just run `docker compose up` and you're done!

**Official Repository**: https://github.com/ainullcode/borgmatic-ui

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation Methods](#installation-methods)
  - [Method 1: Portainer](#method-1-portainer-recommended)
  - [Method 2: Docker Run](#method-2-docker-run)
  - [Method 3: Docker Compose](#method-3-docker-compose)
- [Configuration](#configuration)
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

    # Optional: Override defaults
    # environment:
    #   - PORT=8082
    #   - LOG_LEVEL=DEBUG

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

The container runs as user `borgmatic` (UID 1001). If mounting host directories:
```bash
chown -R 1001:1001 /path/to/host/directory
```

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
   git clone https://github.com/ainullcode/borgmatic-ui.git
   cd borgmatic-ui
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
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/ainullcode/borgmatic-ui/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/ainullcode/borgmatic-ui/discussions)
- 📧 **Contact**: Open an issue for support

### Resources

- **Official Repository**: https://github.com/ainullcode/borgmatic-ui
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
