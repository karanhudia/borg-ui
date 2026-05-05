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
  - icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/></svg>'
    title: Backup
    details: Run Borg backups with live progress, logs, schedules, and maintenance jobs.
    link: /usage-guide
  - icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v6h6"/><path d="M12 7v5l3 2"/></svg>'
    title: Restore
    details: Browse archives, restore selected files, and verify restore paths.
    link: /usage-guide
  - icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="8" x="2" y="3" rx="2"/><rect width="20" height="8" x="2" y="13" rx="2"/><path d="M6 7h.01"/><path d="M6 17h.01"/></svg>'
    title: Remote Machines
    details: Manage SSH connections and remote backup targets from the UI.
    link: /ssh-keys
  - icon: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>'
    title: Operations
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
