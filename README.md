# Borgmatic Web UI

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borgmatic-ui)](https://hub.docker.com/r/ainullcode/borgmatic-ui)
[![License](https://img.shields.io/badge/license-Proprietary-red)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)

A modern, user-friendly web interface for [Borgmatic](https://torsion.org/borgmatic/) backup management. Deploy in seconds with Docker, manage backups through an intuitive dashboard, and monitor your data protection strategy with ease.

![Borgmatic Web UI Screenshot](docs/assets/screenshot.png)

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Documentation](#documentation)
- [API Reference](#api-reference)
- [Contributing](#contributing)
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
- Docker and Docker Compose installed
- 512MB RAM minimum (1GB recommended)
- Network access to backup destinations

### Installation (30 seconds)

```bash
# Clone repository
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui

# Start services
docker-compose up -d

# Access web interface
open http://localhost:8000
```

**Default credentials:**
- Username: `admin`
- Password: `admin123`

⚠️ **Change the default password immediately after first login!**

---

## Installation

**⭐ Complete installation guide:** [INSTALL.md](INSTALL.md)

### Supported Platforms

Works on any platform with Docker:
- ✅ Linux (amd64, arm64, armv7)
- ✅ macOS (Intel & Apple Silicon)
- ✅ Windows
- ✅ Raspberry Pi, NAS devices

### Docker Images

Pre-built multi-arch images: [`ainullcode/borgmatic-ui:latest`](https://hub.docker.com/r/ainullcode/borgmatic-ui)

**Install time:** 30-60 seconds (pulling image only)

---

## Documentation

- **[Installation Guide](INSTALL.md)** - Complete setup instructions
- **[Security Guide](SECURITY.md)** - Security best practices
- **[API Documentation](http://localhost:8000/api/docs)** - Interactive API docs (after install)
- **[Contributing](.github/CONTRIBUTING.md)** - How to contribute
- **[Specification](docs/SPECIFICATION.md)** - Technical specification
- **[Future Plans](docs/FUTURE_ENHANCEMENTS.md)** - Planned features

---

## API Reference

### OpenAPI Documentation

Once the application is running, access the interactive API documentation:

- **Swagger UI**: `http://localhost:8000/api/docs`
- **ReDoc**: `http://localhost:8000/api/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### Postman Collection

Import the [Postman collection](Borgmatic_UI_API.postman_collection.json) for easy API testing.

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

## Configuration

### Environment Variables

Create a `.env` file based on [`.env.example`](.env.example):

```bash
# Docker Image
DOCKER_IMAGE=ainullcode/borgmatic-ui:latest

# Security (REQUIRED - change these!)
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Database
DATABASE_URL=sqlite:////app/data/borgmatic.db

# Logging
LOG_LEVEL=INFO

# CORS
CORS_ORIGINS=["http://localhost:8000"]
```

### Volumes

Mount these directories for persistent data:

- `/app/config` - Borgmatic configuration files
- `/app/data` - Database and SSH keys
- `/app/logs` - Application logs
- `/backups` - Backup storage location

### Ports

- `8000` - Web interface and API (configurable)

---

## Contributing

We welcome contributions! However, this project uses a **proprietary license**.

### How to Contribute

1. ⚠️ **Do NOT fork** this repository
2. Create an issue to discuss your proposed changes
3. Clone the repository and create a feature branch
4. Submit a pull request with your changes

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for detailed guidelines.

### Contribution License Agreement

By submitting a pull request, you agree that your contributions will be licensed under the same proprietary license and you grant the copyright holder perpetual rights to use, modify, and distribute your contributions.

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

For commercial licensing or special permissions, contact the author.

---

## Support

### Getting Help

- 📖 **Documentation**: Check the [docs](docs/) directory
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)
- 📧 **Contact**: Open an issue for support

### Resources

- **Docker Hub**: https://hub.docker.com/r/ainullcode/borgmatic-ui
- **Borgmatic Docs**: https://torsion.org/borgmatic/
- **Borg Backup**: https://borgbackup.readthedocs.io/

---

## Acknowledgments

Built with:
- [Borgmatic](https://torsion.org/borgmatic/) - Backup automation
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [Tailwind CSS](https://tailwindcss.com/) - Styling

---

## Security

Found a security vulnerability? Please report it privately via GitHub Security Advisories.

---

**Made with ❤️ by [Karan Hudia](https://github.com/karanhudia)**

© 2025 Karan Hudia. All Rights Reserved.
