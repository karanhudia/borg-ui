<div align="center">
    <img src="LogoWithName.png" alt="Borg UI" width="300">
</div>

---

<div align="center">
  <h5>
      <a href="https://karanhudia.github.io/borg-ui">Documentation</a>
      <span> | </span>
      <a href="https://hub.docker.com/r/ainullcode/borg-ui">Docker Hub</a>
      <span> | </span>
      <a href="https://discord.gg/5KfVa5QkdQ">Discord</a>
  </h5>
</div>

<div align="center">

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borg-ui)](https://hub.docker.com/r/ainullcode/borg-ui)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)
[![Tests](https://github.com/karanhudia/borg-ui/workflows/Tests/badge.svg)](https://github.com/karanhudia/borg-ui/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/karanhudia/borg-ui/branch/main/graph/badge.svg)](https://codecov.io/gh/karanhudia/borg-ui)
[![Discord](https://img.shields.io/discord/1331215029498732686?color=5865F2&logo=discord&logoColor=white&label=Discord)](https://discord.gg/5KfVa5QkdQ)

</div>

<p align="center">
    <strong>A modern web interface for <a href="https://borgbackup.readthedocs.io/">Borg Backup</a></strong>
</p>

<p align="center">
    Zero-configuration deployment - just run and go.
</p>

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

## Getting Started

**Installation is simple with Docker:**

```bash
# Pull and run
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/yourusername:/local:rw \
  ainullcode/borg-ui:latest
```

Access at `http://localhost:8081` • Default credentials: `admin` / `admin123`

**📖 [Installation Guide](https://karanhudia.github.io/borg-ui/installation)** - Complete setup with Docker Compose, Redis, Portainer, Unraid

---

## Documentation

**[📚 Full Documentation](https://karanhudia.github.io/borg-ui)** - Complete guides and tutorials

Quick links:
- [Installation Guide](https://karanhudia.github.io/borg-ui/installation) - Detailed setup for all platforms
- [Configuration Guide](https://karanhudia.github.io/borg-ui/configuration) - Environment variables and customization
- [Usage Guide](https://karanhudia.github.io/borg-ui/usage-guide) - Creating your first backup
- [Notifications Setup](https://karanhudia.github.io/borg-ui/notifications) - Email, Slack, Discord alerts
- [SSH Keys Guide](https://karanhudia.github.io/borg-ui/ssh-keys) - Remote backup setup
- [Security Guide](https://karanhudia.github.io/borg-ui/security) - Best practices

---

## Support

- **Discord**: [Join our community](https://discord.gg/5KfVa5QkdQ) - Get help, share your setup, suggest features
- **Documentation**: [Full Documentation](https://karanhudia.github.io/borg-ui)
- **Bug Reports**: [GitHub Issues](https://github.com/karanhudia/borg-ui/issues)
- **Discussions**: [GitHub Discussions](https://github.com/karanhudia/borg-ui/discussions)

---

## Contributing

Want to help improve Borg Web UI? See our [Contributing Guide](.github/CONTRIBUTING.md) and [Development Guide](https://karanhudia.github.io/borg-ui/development) to get started.

---

## License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Built with [Borg Backup](https://borgbackup.readthedocs.io/), [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/), and [Material-UI](https://mui.com/)

Made with ❤️ by [Karan Hudia](https://github.com/karanhudia)

</div>
