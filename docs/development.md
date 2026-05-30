---
title: Development
nav_order: 10
description: "Set up a Borg UI development environment"
permalink: /development
---

# Development

Use the dev script for normal local development. It runs the backend in Docker and the frontend locally with Vite.

## Requirements

- Docker
- Docker Compose
- Node.js 20.19+
- Python 3.10+ for local test tooling

## Start

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
./scripts/dev.sh
```

The script starts:

- backend container: `borg-web-ui-dev`
- frontend dev server: `http://localhost:7879`
- backend API: `http://localhost:8083` by default

Set `DEV_PORT` in `.env` if `8083` is already used.

## Local Cloud Storage OAuth

Google Drive and OneDrive Borg UI-owned OAuth can run against the local dev
server. Because the public URL is `localhost`, Borg UI allows HTTP for this
development case.

Set `PUBLIC_BASE_URL` in the repository root `.env` file before starting
`./scripts/dev.sh`. Provider OAuth app credentials can be saved from the Cloud
Storage dialog after the app starts, or supplied as backend environment
variables for repeatable local runs:

```dotenv
PUBLIC_BASE_URL=http://localhost:7879
GOOGLE_DRIVE_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_DRIVE_OAUTH_CLIENT_SECRET=your-google-client-secret
ONEDRIVE_OAUTH_CLIENT_ID=your-microsoft-client-id
ONEDRIVE_OAUTH_CLIENT_SECRET=your-microsoft-client-secret
```

Register these redirect URLs in the provider OAuth app:

```text
http://localhost:7879/api/rclone/oauth/callback/drive
http://localhost:7879/api/rclone/oauth/callback/onedrive
```

To obtain OAuth credentials, create a Google Cloud project in the
[Google Cloud Console](https://console.cloud.google.com/) and enable the Google
Drive API, or register a Microsoft Entra application in the
[Azure portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
for OneDrive. If the `PUBLIC_BASE_URL`, client ID, or client secret values are
not configured, Google Drive and OneDrive fall back to rclone's loopback/manual
authorization flow.

The callback hits Vite on port `7879`, and Vite proxies `/api` to the backend
container on `DEV_PORT` (`8083` by default). Client secrets stay in the backend
environment or encrypted Borg UI settings; ordinary provider metadata only
reports whether credentials are configured and where they came from.

## Production-Style Local Run

```bash
docker compose up -d --build
```

Default app URL:

```text
http://localhost:8081
```

Set `PORT` in `.env` to change it.

## Useful Files

```text
app/                    FastAPI backend
frontend/               React frontend
scripts/dev.sh          full dev environment
docker-compose.yml      production-style compose
docker-compose.dev.yml  dev backend compose
docs/                   VitePress docs
```

## Frontend Commands

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run lint
npm run format:check
npm run build
```

## Backend Commands

Run from the repository root:

```bash
ruff check app tests
ruff format --check app tests
pytest
```

## Docs Commands

```bash
cd docs
npm ci
npm run dev
npm run build
```

## API Docs

With the app running:

```text
http://localhost:8081/api/docs
```

In dev mode, use the `DEV_PORT` backend URL.

## Container Shell

```bash
docker exec -it borg-web-ui-dev bash
```

Check Borg binaries:

```bash
borg --version
borg2 --version
```

## Pre-Commit Hooks

Install hooks if you use them locally:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Make sure frontend dependencies are installed first, otherwise pre-push hooks that call `prettier`, `tsc`, or `eslint` will fail.

## Smoke Tests

Production-critical flows are covered by smoke tests against a running app.

Example:

```bash
python3 tests/smoke/run_core_smoke.py --url http://localhost:8081
```

See [Testing](testing).
