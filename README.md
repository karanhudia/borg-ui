# Borgmatic Web UI

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borgmatic-ui)](https://hub.docker.com/r/ainullcode/borgmatic-ui)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
[![GitHub Actions](https://github.com/ainullcode/borgmatic-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/ainullcode/borgmatic-ui/actions)

A modern, user-friendly web interface for [Borgmatic](https://torsion.org/borgmatic/) backup management. Deploy in seconds with Docker, manage backups through an intuitive dashboard, and monitor your data protection strategy with ease.

**Official Repository**: https://github.com/ainullcode/borgmatic-ui

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation Methods](#installation-methods)
  - [Method 1: Portainer](#method-1-portainer-recommended)
  - [Method 2: Docker Run](#method-2-docker-run)
  - [Method 3: Docker Compose](#method-3-docker-compose)
- [Environment Variables](#environment-variables)
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
- ⚡ **Fast Installation** - 30-60 seconds with pre-built multi-arch Docker images
- 🔒 **Secure** - JWT authentication, encrypted storage, and non-root execution
- 📱 **Responsive Design** - Works seamlessly on desktop, tablet, and mobile
- 🌐 **Multi-platform** - Supports amd64, arm64, and armv7 architectures
- 🚀 **Production Ready** - Battle-tested on Raspberry Pi, NAS, and cloud servers

---

## Quick Start

### Prerequisites
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

Portainer is the easiest way to deploy this application with a visual interface.

#### Step 1: Add Stack in Portainer

1. Go to **Stacks** > **Add Stack**
2. Name your stack: `borgmatic-ui`
3. Paste the following docker-compose configuration:

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
      - borg_backups:/backups

    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=sqlite:////data/borgmatic.db
      - BORGMATIC_CONFIG_PATH=/data/config/borgmatic.yaml
      - BORGMATIC_BACKUP_PATH=/backups
      - ENVIRONMENT=production
      - PORT=8081
      - LOG_LEVEL=INFO

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  borg_data:
    name: borg_data
  borg_backups:
    name: borg_backups
```

#### Step 2: Set Environment Variables

In Portainer's "Environment variables" section, add:

| Variable | Value | Required |
|----------|-------|----------|
| `SECRET_KEY` | Generate with: `openssl rand -base64 32` | ✅ Yes |
| `PORT` | `8081` (or any available port) | Optional |
| `LOG_LEVEL` | `INFO` | Optional |

#### Step 3: Deploy Stack

Click **Deploy the stack** and wait for the container to start (30-60 seconds).

#### Step 4: Access Application

Open `http://your-server-ip:8081` and login with default credentials.

---

### Method 2: Docker Run

For quick deployment using Docker CLI.

#### Step 1: Generate Secret Key

```bash
export SECRET_KEY=$(openssl rand -base64 32)
echo "Your SECRET_KEY: $SECRET_KEY"
# Save this key for future use!
```

#### Step 2: Create Docker Volumes

```bash
docker volume create borg_data
docker volume create borg_backups
```

#### Step 3: Run Container

```bash
docker run -d \
  --name borgmatic-web-ui \
  --restart unless-stopped \
  -p 8081:8081 \
  -v borg_data:/data \
  -v borg_backups:/backups \
  -e SECRET_KEY="$SECRET_KEY" \
  -e DATABASE_URL="sqlite:////data/borgmatic.db" \
  -e BORGMATIC_CONFIG_PATH="/data/config/borgmatic.yaml" \
  -e BORGMATIC_BACKUP_PATH="/backups" \
  -e ENVIRONMENT="production" \
  -e PORT="8081" \
  -e LOG_LEVEL="INFO" \
  ainullcode/borgmatic-ui:latest
```

#### Step 4: Verify Container is Running

```bash
docker ps | grep borgmatic-web-ui
docker logs borgmatic-web-ui
```

#### Step 5: Access Application

Open `http://localhost:8081` and login.

---

### Method 3: Docker Compose

For infrastructure-as-code deployments.

#### Step 1: Create Project Directory

```bash
mkdir borgmatic-ui && cd borgmatic-ui
```

#### Step 2: Create `docker-compose.yml`

Create a file named `docker-compose.yml` with the following content:

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
      - borg_data:/data:rw
      - borg_backups:/backups:rw

    environment:
      - DATA_DIR=/data
      - DATABASE_URL=${DATABASE_URL:-sqlite:////data/borgmatic.db}
      - BORGMATIC_CONFIG_PATH=/data/config/borgmatic.yaml
      - BORGMATIC_BACKUP_PATH=/backups
      - SECRET_KEY=${SECRET_KEY:-change-this-secret-key-in-production}
      - ENVIRONMENT=${ENVIRONMENT:-production}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - PORT=${PORT:-8081}

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

    networks:
      - borg_network

networks:
  borg_network:
    name: borg_network
    driver: bridge

volumes:
  borg_data:
    name: borg_data
  borg_backups:
    name: borg_backups
```

#### Step 3: Generate Secret Key

```bash
export SECRET_KEY=$(openssl rand -base64 32)
echo "Save this SECRET_KEY for Step 4: $SECRET_KEY"
```

#### Step 4: Update Environment Variables

In the `docker-compose.yml` file you created, replace:
- `change-this-secret-key-in-production` with your generated SECRET_KEY from Step 3

#### Step 5: Start Services

```bash
docker-compose up -d
```

Or if using Docker Compose v2:
```bash
docker compose up -d
```

#### Step 6: View Logs (Optional)

```bash
docker-compose logs -f app
```

#### Step 7: Access Application

Open `http://localhost:8081` and login with default credentials.

---

## Environment Variables

All environment variables are optional except `SECRET_KEY`.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (generate with `openssl rand -base64 32`) | `xK8j3mP9...` |

### Application Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Application port | `8081` |
| `ENVIRONMENT` | Environment mode | `production` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `HOST` | Bind address | `0.0.0.0` |

### Database Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection URL | `sqlite:////data/borgmatic.db` |
| `DATA_DIR` | Data directory path | `/data` |

### Borgmatic Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `BORGMATIC_CONFIG_PATH` | Borgmatic config file path | `/data/config/borgmatic.yaml` |
| `BORGMATIC_BACKUP_PATH` | Backup storage path | `/backups` |
| `ENABLE_CRON_BACKUPS` | Enable automatic backups | `false` |

### Security Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiration time | `30` |
| `CORS_ORIGINS` | Allowed CORS origins | `["http://localhost:7879"]` |

---

## Data Persistence

### Docker Volumes

Two volumes are created automatically:

1. **`borg_data`** - Contains:
   - SQLite database (`borgmatic.db`)
   - SSH keys
   - Configuration files
   - Application logs

2. **`borg_backups`** - Contains:
   - Backup repositories
   - Backup archives

### Viewing Volume Data

```bash
# Inspect borg_data volume
docker run --rm -v borg_data:/data alpine ls -la /data

# Inspect borg_backups volume
docker run --rm -v borg_backups:/backups alpine ls -la /backups
```

### Backup and Restore Volumes

```bash
# Backup borg_data to tar file
docker run --rm -v borg_data:/data -v $(pwd):/backup alpine tar czf /backup/borg_data_backup.tar.gz -C /data .

# Restore borg_data from tar file
docker run --rm -v borg_data:/data -v $(pwd):/backup alpine tar xzf /backup/borg_data_backup.tar.gz -C /data
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

Once the application is running, access the interactive API documentation:

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
| `/api/ssh_keys` | GET, POST | Manage SSH keys |
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

Change the port in `.env` or use a different port:
```bash
docker run -p 8082:8081 ...
```

### Data Lost After Container Removal

Ensure you're using Docker volumes (not bind mounts) and verify `DATABASE_URL` points to `/data/borgmatic.db` (inside the volume).

### Permission Issues

The container runs as user `borgmatic` (UID 1001). If mounting host directories, ensure proper permissions:
```bash
chown -R 1001:1001 /path/to/host/directory
```

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

2. **Copy environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` and set your SECRET_KEY:**
   ```bash
   openssl rand -base64 32
   # Copy the output and paste it as SECRET_KEY in .env
   ```

4. **Start development environment:**
   ```bash
   docker-compose up -d --build
   ```

5. **Access the application:**
   - Frontend: `http://localhost:8081`
   - API Docs: `http://localhost:8081/api/docs`

### Development Workflow

**Backend Development:**
```bash
# View backend logs
docker-compose logs -f app

# Run backend tests
docker-compose exec app pytest

# Access Python shell
docker-compose exec app python
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
│   └── main.py           # Application entry point
├── frontend/              # Frontend (React + TypeScript)
│   ├── src/
│   │   ├── components/   # Reusable components
│   │   ├── pages/        # Page components
│   │   ├── services/     # API clients
│   │   └── App.tsx       # Root component
│   └── package.json
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile            # Multi-stage Docker build
└── .env.example          # Environment variables template
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
