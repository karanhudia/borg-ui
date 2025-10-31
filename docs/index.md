---
layout: default
title: Borg Web UI - Documentation
---

# Borg Web UI Documentation

Welcome to the official documentation for **Borg Web UI** - a modern, user-friendly web interface for Borg Backup management.

## Quick Links

- 🏠 [GitHub Repository](https://github.com/karanhudia/borg-ui)
- 🐳 [Docker Hub](https://hub.docker.com/r/ainullcode/borg-ui)
- 📦 [Latest Release](https://github.com/karanhudia/borg-ui/releases)

---

## Getting Started

### What is Borg Web UI?

Borg Web UI makes [Borg Backup](https://borgbackup.readthedocs.io/) easy to use. Instead of memorizing complex terminal commands, you get a beautiful web interface that handles everything for you.

### Why Was This Built?

I love Borg Backup, but the terminal interface is complicated. Every backup task required:
- Remembering exact command syntax
- Parsing verbose terminal output
- Writing and debugging cron jobs
- Managing SSH keys and permissions manually

**It was exhausting.** So I built this web UI to make Borg accessible to everyone - from beginners to power users.

### Quick Install

```bash
# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  app:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      - borg_data:/data
      - ${LOCAL_STORAGE_PATH:-/}:/local:rw

volumes:
  borg_data:
EOF

# Start the container
docker compose up -d
```

Access at `http://localhost:8081` (default credentials: `admin` / `admin123`)

---

## 📖 New to Borg Web UI?

**[→ Start Here: Complete Usage Guide](usage-guide.md)**

Learn how to create your first backup in minutes:
- **Local Backups** (USB drives, NAS, etc.) - No SSH needed!
- **SSH/Remote Backups** (Off-site protection) - With easy SSH key setup

Both methods use the same simple workflow. The guide covers everything step-by-step.

---

## Documentation

### Core Guides

- **[📖 Usage Guide](usage-guide.md)** - **Step-by-step guides for creating local and SSH backups**
- **[Installation Guide](https://github.com/karanhudia/borg-ui#installation-methods)** - Multiple deployment methods (Portainer, Docker Run, Docker Compose)
- **[Configuration Guide](https://github.com/karanhudia/borg-ui#configuration)** - Environment variables and settings
- **[Troubleshooting](https://github.com/karanhudia/borg-ui#troubleshooting)** - Common issues and solutions

### Technical Documentation

- **[System Specification](SPECIFICATION.md)** - Complete system architecture and API reference
- **[Database Persistence](DATABASE_PERSISTENCE.md)** - How data is stored and managed
- **[Future Enhancements](FUTURE_ENHANCEMENTS.md)** - Planned features and roadmap

### API Reference

Once installed, access interactive API documentation:
- **Swagger UI**: `http://localhost:8081/api/docs`
- **ReDoc**: `http://localhost:8081/api/redoc`
- **OpenAPI JSON**: `http://localhost:8081/openapi.json`

---

## Key Features

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
- ⚡ **Zero Configuration** - No manual setup required
- 🔒 **Auto-Secured** - SECRET_KEY automatically generated on first run
- 📱 **Responsive Design** - Works on desktop, tablet, and mobile
- 🌐 **Multi-platform** - Supports amd64, arm64, and armv7 architectures
- 🚀 **Production Ready** - Battle-tested on Raspberry Pi, NAS, and cloud servers

---

## Project Goals

🎯 **Simplicity First** - If you can click it, you shouldn't have to type it

🚀 **Zero Configuration** - No manual setup, no environment files to edit, just `docker compose up`

🔒 **Secure by Default** - Auto-generated secrets, JWT authentication, permission controls

📱 **Works Everywhere** - Desktop, tablet, mobile, Raspberry Pi, NAS, cloud servers

🌐 **Real-time Feedback** - Live backup progress, instant logs, responsive dashboards

💾 **Data Safety** - Never lose your backups or configuration, everything persists

---

## Common Use Cases

### Home Server / NAS Backups
Perfect for backing up your home server, Synology NAS, or personal data to:
- External USB drives
- Network storage (NFS/CIFS mounts)
- Remote servers via SSH
- Cloud storage (S3, Azure, Google Cloud)

### Raspberry Pi Backups
Lightweight enough to run on Raspberry Pi while backing up to:
- USB-attached storage
- Another Raspberry Pi on your network
- Cloud backup services
- NAS devices

### Server Infrastructure
Manage backups for multiple servers from a central web interface:
- Schedule automated backups
- Monitor backup health across infrastructure
- Restore files quickly when needed
- Maintain backup retention policies

---

## Support

### Getting Help

- 📖 **Documentation**: You're reading it!
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)
- 📧 **Contact**: Open an issue for support

### Resources

- **Borg Backup Documentation**: [borgbackup.readthedocs.io](https://borgbackup.readthedocs.io/)
- **Docker Documentation**: [docs.docker.com](https://docs.docker.com/)
- **FastAPI Documentation**: [fastapi.tiangolo.com](https://fastapi.tiangolo.com/)

---

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](https://github.com/karanhudia/borg-ui/blob/main/LICENSE) file for details.

---

## Acknowledgments

Built with:
- [Borg Backup](https://borgbackup.readthedocs.io/) - Deduplication backup program
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [React](https://react.dev/) - Frontend framework
- [Material-UI](https://mui.com/) - UI components

---

**Made with ❤️ by [Karan Hudia](https://github.com/karanhudia) (ainullcode)**

*This project solves my personal backup management headaches, and I hope it solves yours too.*
