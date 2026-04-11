<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/affae94f-5fdb-4690-8427-9c6164f1e267" />
    <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/6e2bca71-91e6-41ed-8ab0-6917dc27fc6e" />
    <img alt="Borg UI Logo v2" src="https://github.com/user-attachments/assets/6e2bca71-91e6-41ed-8ab0-6917dc27fc6e" width="360" />
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
  <strong>A modern web interface for <a href="https://borgbackup.readthedocs.io/">Borg Backup</a></strong>
</p>

<p align="center">
  Run backups, browse archives, restore files, manage repositories, and automate schedules from one interface.
</p>

> [!NOTE]
> Borg UI is developed with modern AI tooling as part of the workflow. Architecture, security, and release decisions are reviewed before merge.

## Highlights

- Dashboard for repository health, activity, schedules, and storage
- Repository management for local, SSH, and SFTP destinations
- Live backup progress, archive browsing, and restore workflows
- Automated schedules, maintenance actions, and pre/post backup hooks
- Notifications through 100+ Apprise services
- Remote machine management with SSH key deployment and storage visibility
- Support for BorgBackup 1.x and BorgBackup 2 beta workflows
- Multi-architecture containers for `amd64`, `arm64`, and `armv7`

## Release Readiness

- Current generated line coverage reports: backend `58.82%`, frontend `81.66%`, combined `64.36%`
- Release confidence is built on multiple test lanes: backend unit coverage, backend API integration, frontend unit coverage, frontend build validation, and core, extended, and SSH smoke suites against a built app

## Interface

### Operations Overview

Track repository health, recent activity, storage, and day-to-day backup execution from the main product surfaces.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/b7b68221-f649-4bb9-9be3-c0abc0acc670" />
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/90264678-e6ad-436c-b04d-4c804e7f5ec1" />
  <img alt="Borg UI dashboard" src="https://github.com/user-attachments/assets/90264678-e6ad-436c-b04d-4c804e7f5ec1" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/52902bd5-cd7e-45df-88fe-bc641fb565a2" />
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/2f0f27a3-5462-4474-bca2-8fb9a7166969" />
  <img alt="Repository management" src="https://github.com/user-attachments/assets/2f0f27a3-5462-4474-bca2-8fb9a7166969" width="100%" />
</picture>

### Backup and Restore Workflows

Monitor live backup progress, inspect archives, and work through restore flows without dropping to the CLI.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/4b168836-22bb-4a1a-b41e-1eab26e1b213" />
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/47c92914-53f7-449a-a34b-d99835154c84" />
  <img alt="Live backup progress" src="https://github.com/user-attachments/assets/47c92914-53f7-449a-a34b-d99835154c84" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/2319a6f7-1d14-4fc4-a03e-59df69946490" />
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/3822b1d9-3066-4a73-b9ee-6542f5885164" />
  <img alt="Archive browser" src="https://github.com/user-attachments/assets/3822b1d9-3066-4a73-b9ee-6542f5885164" width="100%" />
</picture>

### Automation and Integrations

Automate schedules, manage remote machines, and configure notifications for ongoing backup operations.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/2ddff79b-71c0-4f33-99bd-e7ec25495345" />
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/5d4ce81c-abdb-4dcf-81e9-e66b10804104" />
  <img alt="Backup schedule management" src="https://github.com/user-attachments/assets/5d4ce81c-abdb-4dcf-81e9-e66b10804104" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/d060f71c-0f0c-4f75-8960-0229aaeaabf5" />
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/055937c6-bfee-4632-b302-d49f593f5abd" />
  <img alt="Remote machines management" src="https://github.com/user-attachments/assets/055937c6-bfee-4632-b302-d49f593f5abd" width="100%" />
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/user-attachments/assets/daace69d-c7e8-4a3d-8ca3-eeb0d174dc5b" />
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/user-attachments/assets/87827aa7-133b-4978-9078-b87890cee77e" />
  <img alt="Notification services" src="https://github.com/user-attachments/assets/87827aa7-133b-4978-9078-b87890cee77e" width="100%" />
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
