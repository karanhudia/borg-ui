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
`./scripts/dev.sh`. Provider OAuth app credentials are saved from the Cloud
Storage dialog after the app starts:

```dotenv
PUBLIC_BASE_URL=http://localhost:7879
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
for OneDrive. If `PUBLIC_BASE_URL` is missing or the provider app credentials
have not been saved in Cloud Storage, Google Drive and OneDrive fall back to
rclone's loopback/manual authorization flow.

The callback hits Vite on port `7879`, and Vite proxies `/api` to the backend
container on `DEV_PORT` (`8083` by default). Client secrets stay in the backend
database as encrypted Borg UI settings; ordinary provider metadata only reports
whether credentials are configured.

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

## Releases

Create releases only through the checked-in release command, from a clean local
`main` that exactly matches `origin/main`:

```bash
./scripts/release.sh v2.2.7
```

For a stable semantic-version bump, `./scripts/bump-version.sh patch` (or
`minor` / `major`) delegates to the same release command.

The command updates `VERSION`, the frontend manifest and lockfile, and the
backend/OpenAPI version metadata. It verifies that every location matches,
commits the release, and pushes an annotated tag. GitHub Actions then refuses
tags whose metadata does not match or whose commit is not reachable from `main`,
before creating the GitHub release or publishing Docker images.

Published tags are immutable. If a released version needs a correction, publish
the next patch release rather than amending or re-pointing the existing tag.

## Smoke Tests

Production-critical flows are covered by smoke tests against a running app.

Example:

```bash
python3 tests/smoke/run_core_smoke.py --url http://localhost:8081
```

See [Testing](testing).
