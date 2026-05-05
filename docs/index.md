---
layout: home
title: Borg UI
hero:
  name: Borg UI
  text: Borg backups, with a web UI.
  tagline: Create repositories, run backups, browse archives, restore files, and manage schedules from one self-hosted interface.
  image:
    src: /hero-icon@2x.png
    alt: Borg UI
  actions:
    - theme: brand
      text: Install
      link: /installation
    - theme: alt
      text: GitHub
      link: https://github.com/karanhudia/borg-ui
features:
  - title: Backup
    details: Run Borg backups with live progress, logs, schedules, and maintenance jobs.
    link: /usage-guide
  - title: Restore
    details: Browse archives, restore selected files, and verify restore paths.
    link: /usage-guide
  - title: Remote Machines
    details: Manage SSH connections and remote backup targets from the UI.
    link: /ssh-keys
  - title: Operations
    details: Configure notifications, metrics, cache, security, and reverse proxy deployments.
    link: /configuration
---

## Quick Start

```bash
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/youruser:/local:rw \
  ainullcode/borg-ui:latest
```

Open `http://localhost:8081` and log in with `admin` / `admin123`.

Use Docker Compose for normal deployments. See [Installation](installation).

## Main Docs

- [Installation](installation)
- [Configuration](configuration)
- [Usage Guide](usage-guide)
- [Security](security)
- [Reverse Proxy](reverse-proxy)
- [Notifications](notifications)
- [Cache](cache)
- [Prometheus Metrics](METRICS)
- [Development](development)
- [Testing](testing)
