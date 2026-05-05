---
layout: default
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
