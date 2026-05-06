---
title: Architecture
nav_order: 8
description: "How Borg UI is built and where the important state lives"
---

# Architecture

This page describes the current Borg UI implementation. It is not a product roadmap.

## Runtime

Borg UI runs as a Dockerized web application:

- FastAPI backend
- React frontend built with Vite and Material UI
- SQLite database under `/data`
- Borg and Borg 2 CLI binaries inside the container
- Optional Redis cache for archive browsing

The Docker image published for users is:

```bash
ainullcode/borg-ui:latest
```

The default HTTP port is `8081`.

## Persistent State

The `/data` volume contains application state:

- SQLite database
- generated secret key
- logs
- encrypted SSH key material
- job metadata

The Borg cache volume is separate:

```text
/home/borg/.cache/borg
```

Keep both volumes when upgrading.

## Backup Model

Borg UI does not replace Borg. It coordinates Borg CLI operations and stores UI state around them.

Supported repository targets include:

- local paths mounted into the container
- SSH repositories
- SFTP/remote-machine workflows exposed by the UI
- Borg 1 repositories
- Borg 2 beta repositories, where enabled by plan/settings

Backups, restores, checks, prunes, compacts, mounts, and archive browsing are all executed as backend jobs.

## API

The backend exposes API routes under `/api`.

After starting the app, interactive API docs are available at:

```text
http://localhost:8081/api/docs
```

Do not hard-code docs examples as an API contract. Use the live OpenAPI output for exact request and response shapes.

## Frontend

The frontend is a Vite React application. The main app routes include:

- dashboard
- repositories
- archives
- backup jobs
- schedules
- activity
- remote machines
- settings

The old `/ssh-keys` route redirects to `/ssh-connections`. User-facing docs should call this area "Remote Machines".

## Background Work

Long-running Borg work is tracked as jobs. Job logs are stored on disk and referenced from the database.

Main job categories:

- backup
- restore
- check
- compact
- prune
- archive delete
- restore verification

System settings control concurrency, retention of logs, timeouts, cache settings, notifications, beta flags, and integrations.

## Integrations

Built-in integrations include:

- Apprise notifications
- JSON webhooks through Apprise `json://` and `jsons://`
- Prometheus metrics at `/metrics`
- OIDC login
- reverse-proxy trusted-header auth
- MQTT/Home Assistant, behind the MQTT beta flag
- pre/post-backup script hooks

## Security Boundaries

Important boundaries:

- Anyone with shell access to the container can administer the app.
- Anyone with Docker socket access can control the host Docker daemon.
- Trusted-header auth is safe only when the app is reachable exclusively through the trusted proxy.
- `/metrics` should stay private or require a token.
- `/data` must be protected like application secrets.

For deployment hardening, see [Security](security).
