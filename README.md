<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/assets/logo-dark.png" />
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/assets/logo-light.png" />
    <img alt="Borg UI Logo v2" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/assets/logo-light.png" width="360" />
  </picture>
</div>

---

<div align="center">
  <h5>
    <a href="https://borgui.com">Website</a>
    <span> | </span>
    <a href="https://docs.borgui.com">Documentation</a>
    <span> | </span>
    <a href="https://hub.docker.com/r/ainullcode/borg-ui">Docker Hub</a>
  </h5>
</div>

<div align="center">

[![Docker Hub](https://img.shields.io/docker/pulls/ainullcode/borg-ui)](https://hub.docker.com/r/ainullcode/borg-ui)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](LICENSE)
[![GitHub Actions](https://github.com/karanhudia/borg-ui/workflows/Build%20and%20Publish%20Docker%20Images/badge.svg)](https://github.com/karanhudia/borg-ui/actions)
[![Tests](https://github.com/karanhudia/borg-ui/workflows/Tests/badge.svg)](https://github.com/karanhudia/borg-ui/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/karanhudia/borg-ui/branch/main/graph/badge.svg)](https://codecov.io/gh/karanhudia/borg-ui)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/5KfVa5QkdQ)

</div>

<p align="center">
  <strong>A modern web interface for <a href="https://borgbackup.readthedocs.io/">Borg Backup</a></strong><br>
  Run backups, browse archives, restore files, manage repositories, and automate schedules from one interface.
</p>

## Highlights

- Dashboard for repository health, activity, schedules, and storage
- Repository management for local, SSH, and SFTP destinations
- Live backup progress, archive browsing, and restore workflows
- Automated schedules, maintenance actions, and pre/post backup hooks
- Notifications through 100+ Apprise services
- Remote machine management with SSH key deployment and storage visibility
- Support for BorgBackup 1.x and BorgBackup 2 beta workflows
- Multi-architecture containers for `amd64`, `arm64`, and `armv7`

> [!NOTE]
> Borg UI is developed with modern AI tooling as part of the workflow. Architecture, security, and release decisions are reviewed before merge.

## Release Readiness

- Current generated line coverage reports: backend `58.82%`, frontend `81.66%`, combined `64.36%`
- Release confidence is built on multiple test lanes: backend unit coverage, backend API integration, frontend unit coverage, frontend build validation, and core, extended, and SSH smoke suites against a built app
- Docker Hub publishes the user-facing app image `ainullcode/borg-ui`; the separate `borg-ui-runtime-base` image is an internal CI artifact and should remain private

## Interface

### Operations Overview

Track repository health, recent activity, storage, and day-to-day backup execution from the main product surfaces.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/dashboard-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/dashboard-light.png" />
  <img alt="Borg UI dashboard" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/dashboard-light.png" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/repositories-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/repositories-light.png" />
  <img alt="Repository management" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/repositories-light.png" width="100%" />
</picture>

### Backup and Restore Workflows

Monitor live backup progress, inspect archives, and work through restore flows without dropping to the CLI.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/backup-progress-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/backup-progress-light.png" />
  <img alt="Live backup progress" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/backup-progress-light.png" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/archive-browser-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/archive-browser-light.png" />
  <img alt="Archive browser" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/archive-browser-light.png" width="100%" />
</picture>

### Automation and Integrations

Automate schedules, manage remote machines, and configure notifications for ongoing backup operations.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/schedule-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/schedule-light.png" />
  <img alt="Backup schedule management" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/schedule-light.png" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/remote-machines-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/remote-machines-light.png" />
  <img alt="Remote machines management" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/remote-machines-light.png" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/notifications-dark.png" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/notifications-light.png" />
  <img alt="Notification services" src="https://raw.githubusercontent.com/karanhudia/borg-ui/main/screenshots/readme/notifications-light.png" width="100%" />
</picture>

## Getting Started

```bash
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/yourusername:/local:rw \
  ainullcode/borg-ui:latest
```

Access the app at `http://localhost:8081` with `admin` / `admin123`.

For setup details, see the [installation guide](https://docs.borgui.com/installation).

## Documentation

- [Full documentation](https://docs.borgui.com)
- [Development guide](https://docs.borgui.com/development)
- [Testing guide](https://docs.borgui.com/testing)

## Enterprise

For teams that need commercial support, larger rollouts, or an enterprise conversation, Borg UI can also support evaluation and deployment beyond the core open source setup.

- [Learn more](https://borgui.com/buy)
- Contact: [sales@borgui.com](mailto:sales@borgui.com)
- You can also explore the live product and documentation at [borgui.com](https://borgui.com)

## Support

- [Discord community](https://discord.gg/5KfVa5QkdQ)
- [GitHub issues](https://github.com/karanhudia/borg-ui/issues)

## Star History

<div align="center">

<a href="https://star-history.com/#karanhudia/borg-ui&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=karanhudia/borg-ui&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=karanhudia/borg-ui&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=karanhudia/borg-ui&type=Date" />
  </picture>
</a>

</div>

## Contributing

See the [contributing guide](.github/CONTRIBUTING.md) and the [development guide](https://docs.borgui.com/development).

## License

This project is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE).

<div align="center">

Made with ❤️ by [Karan Hudia](https://github.com/karanhudia)

</div>
