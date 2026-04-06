---
layout: default
title: Development Guide
nav_order: 10
description: "Setting up a development environment for Borg Web UI"
permalink: /development
---

# Development Guide

This guide covers setting up a development environment for Borg Web UI with hot reload support for both frontend and backend.

---

## Prerequisites

- **Git** - Version control
- **Docker & Docker Compose** - Required (backend runs in Docker to access borg/borg2 binaries)
- **Node.js 20.19+** - Frontend development (Vite requires this version)
- **Python 3.10+** - Optional, only needed for running tests locally

---

## Quick Start

### Clone the Repository

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
```

### Configure Ports (Optional)

Copy `.env.example` to `.env` if it exists, or create a `.env` file:

```bash
# .env
PUID=501          # your user ID (id -u)
PGID=20           # your group ID (id -g)
PORT=8082         # production backend port
DEV_PORT=8083     # dev backend port (must differ from PORT)
TZ=Asia/Kolkata   # your timezone
```

If `.env` is absent, defaults are `PORT=8082` and `DEV_PORT=8083`.

---

## Development Mode

### Start the Dev Environment

```bash
./scripts/dev.sh
```

This script:
1. Reads `DEV_PORT` from `.env` (default `8083`)
2. Starts the backend in Docker (`borg-web-ui-dev`) — isolated from any running production containers
3. Mounts your local `./app` source into the container for hot reload — no image rebuild needed on code changes
4. Starts the Vite frontend dev server locally

**Access:**
- Frontend (hot reload): [http://localhost:7879](http://localhost:7879)
- Dev backend API: `http://localhost:DEV_PORT` (default `8083`)

**Stop:** Press `Ctrl+C` — containers are torn down automatically.

---

## Production Testing

To build and test the full production image locally (frontend bundled, gunicorn, no hot reload):

```bash
docker-compose up -d --build
```

**Access:** [http://localhost:PORT](http://localhost:PORT) (default `8082`)

Production and dev environments use different container names and ports, so they can run simultaneously:

| | Production | Development |
|---|---|---|
| Backend container | `borg-web-ui` | `borg-web-ui-dev` |
| Redis container | `borg-redis` | optional only |
| Backend port | `PORT` (default `8082`) | `DEV_PORT` (default `8083`) |
| Redis port | `6379` | optional only |
| Frontend | built into image | Vite dev server on `7879` |
| Data | `borg_data` Docker volume | `.local-data/` folder |

---

## Project Structure

```
borg-ui/
├── app/                      # Python backend (FastAPI)
│   ├── main.py               # Application entry point
│   ├── api/                  # API route handlers
│   ├── core/                 # Borg wrappers (borg.py, borg2.py)
│   ├── services/             # Business logic
│   └── database/             # Models and migrations
├── frontend/                 # React frontend
│   ├── src/
│   │   ├── components/       # Reusable components
│   │   ├── pages/            # Page components
│   │   ├── hooks/            # Custom React hooks
│   │   ├── services/         # API client
│   │   └── utils/            # Utility functions
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── dev.sh                # Full dev environment (recommended)
│   └── backend-dev.sh        # Backend-only helper
├── docker-compose.yml        # Production compose
├── docker-compose.dev.yml    # Dev compose (standalone, not an override)
└── Dockerfile
```

---

## Environment Variables

The dev environment sets these automatically via `docker-compose.dev.yml`:

| Variable | Dev Value | Description |
|----------|-----------|-------------|
| `DATA_DIR` | `/data` (→ `.local-data/`) | Data directory inside container |
| `DATABASE_URL` | `sqlite:////data/borg.db` | SQLite database path |
| `SECRET_KEY` | `dev-secret-key-not-for-production` | JWT signing key |
| `PORT` | value of `DEV_PORT` from `.env` | Backend port inside container |

The Vite dev server proxies `/api/*` requests to the backend — `dev.sh` configures this automatically via `VITE_PROXY_TARGET`.

---

## Frontend Development

### Available Scripts

```bash
cd frontend
npm run dev          # Start dev server with HMR
npm run build        # Production build
npm run typecheck    # TypeScript type checking
npm run lint         # ESLint
npm run format       # Prettier formatting
npm run format:check # Check formatting
```

---

## Backend Development

### API Documentation

With the dev backend running, access:
- Swagger UI: `http://localhost:DEV_PORT/api/docs`
- ReDoc: `http://localhost:DEV_PORT/api/redoc`

### Exec into the dev container

```bash
docker exec -it borg-web-ui-dev bash
```

Both borg binaries are available inside:
```bash
borg --version    # Borg 1.x
borg2 --version   # Borg 2.x
```

---

## Running Tests

### Backend Tests

```bash
# From project root
pytest

# With coverage
pytest --cov=app --cov-report=html
```

Production-critical Borg work is tested primarily through API-driven flows. The current focus is real Borg 1 coverage for repository lifecycle, backup execution, archive operations, restore, maintenance, and schedule-triggered runs.

See [Testing](testing) for the short list of scenarios we treat as mandatory before trusting a release with production backups.

CI separates fast coverage jobs from black-box smoke jobs. The main `Tests` workflow handles backend coverage plus frontend quality, tests, and build in parallel, while `Smoke Tests` runs a built app against core and extended Borg production flows.

```bash
python3 tests/smoke/run_core_smoke.py --url http://localhost:8082
python3 tests/smoke/run_extended_smoke.py --url http://localhost:8082
```

---

## Troubleshooting

### Node.js Version Too Old

If you see `Vite requires Node.js version 20.19+`:

```bash
node --version      # check current version
nvm install 20      # install via nvm
nvm use 20
```

### Port Already in Use

```bash
# Check what is on the dev port
lsof -i :8083

# Or change DEV_PORT in .env
DEV_PORT=8084
```

### Backend changes not reloading

Uvicorn watches `/app/app` inside the container, which is your local `./app` directory. If reload isn't triggering, check that the file was saved and the dev container is running:

```bash
docker logs -f borg-web-ui-dev
```
