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
- **Docker & Docker Compose** - For Redis and optional full-stack development
- **Python 3.11+** - Backend development
- **Node.js 20.19+** - Frontend development (Vite requires this version)

---

## Quick Start

### Clone the Repository

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
```

---

## Development Setup

### Option 1: All-in-One Script (Recommended)

Run everything with one command:

```bash
./scripts/dev.sh
```

This script:
1. Starts Redis in Docker
2. Creates local data directories (`.local-data/`)
3. Starts the backend with `uvicorn --reload`
4. Starts the frontend with `vite` dev server

**Access:**
- Frontend: [http://localhost:7879](http://localhost:7879)
- Backend API: [http://localhost:8081](http://localhost:8081)
- Redis: localhost:6379

**Stop:** Press `Ctrl+C`

---

### Option 2: Run Frontend and Backend Separately

For more control, run each service in a separate terminal:

**Terminal 1 - Backend:**

```bash
./scripts/backend-dev.sh
```

**Terminal 2 - Frontend:**

```bash
cd frontend
npm install  # First time only
npm run dev
```

---

## Project Structure

```
borg-ui/
├── app/                    # Python backend (FastAPI)
│   ├── main.py            # Application entry point
│   ├── routers/           # API endpoints
│   ├── services/          # Business logic
│   └── models/            # Database models
├── frontend/              # React frontend
│   ├── src/
│   │   ├── components/    # Reusable components
│   │   ├── pages/         # Page components
│   │   ├── hooks/         # Custom React hooks
│   │   ├── services/      # API client
│   │   └── utils/         # Utility functions
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   ├── dev.sh             # Full dev environment script
│   ├── backend-dev.sh     # Backend-only dev script
│   └── release.sh         # Release automation
├── docker-compose.yml     # Production compose
└── Dockerfile
```

---

## Environment Variables

The development scripts automatically set these environment variables:

| Variable | Dev Value | Description |
|----------|-----------|-------------|
| `DATA_DIR` | `.local-data` | Local data directory |
| `DATABASE_URL` | `sqlite:///.local-data/borg.db` | SQLite database path |
| `SECRET_KEY` | `dev-secret-key-not-for-production` | JWT signing key |
| `ENVIRONMENT` | `development` | App environment |
| `PORT` | `8081` | Backend port |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |

---

## Frontend Development

### Install Dependencies

```bash
cd frontend
npm install
```

### Available Scripts

```bash
npm run dev          # Start dev server with HMR
npm run build        # Production build
npm run typecheck    # TypeScript type checking
npm run lint         # ESLint
npm run format       # Prettier formatting
npm run format:check # Check formatting
```

### Proxy Configuration

The Vite dev server proxies API requests to the backend. See `frontend/vite.config.ts`:

```typescript
proxy: {
  '/api': {
    target: 'http://localhost:8081',
    changeOrigin: true,
  },
}
```

---

## Backend Development

### Virtual Environment (Optional but Recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run Backend Manually

```bash
export DATA_DIR=".local-data"
export DATABASE_URL="sqlite:///.local-data/borg.db"
export SECRET_KEY="dev-secret-key"
export ENVIRONMENT="development"

python3 -m uvicorn app.main:app --reload --port 8081
```

### API Documentation

With the backend running, access:
- Swagger UI: [http://localhost:8081/api/docs](http://localhost:8081/api/docs)
- ReDoc: [http://localhost:8081/api/redoc](http://localhost:8081/api/redoc)

---

## Running Tests

### Backend Tests

```bash
# From project root
pytest

# With coverage
pytest --cov=app --cov-report=html
```

### Frontend Type Checking

```bash
cd frontend
npm run typecheck
```

---

## Making a Release

Use the release script:

```bash
./scripts/release.sh v1.2.3
```

This script:
1. Validates the version format (vX.Y.Z)
2. Updates the VERSION file
3. Runs tests and type checking
4. Commits and tags the release
5. Pushes to GitHub (triggers Docker build)

Or from the frontend directory:

```bash
npm run release
```

---

## Troubleshooting

### Node.js Version Too Old

If you see `Vite requires Node.js version 20.19+`:

```bash
# Check your version
node --version

# Update Node.js (using nvm)
nvm install 20
nvm use 20
```

### Port Already in Use

```bash
# Find process using port 8081
lsof -i :8081

# Kill it
kill -9 <PID>
```

### Redis Connection Failed

Make sure Redis is running:

```bash
# Start Redis via Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Or via the dev script (starts automatically)
./scripts/dev.sh
```

### Backend Can't Find Borg

The backend requires Borg Backup installed. For local development without Borg:
- Use Docker Compose dev mode (Option 3) which has Borg pre-installed
- Or install Borg locally: `brew install borgbackup` (macOS) or `apt install borgbackup` (Ubuntu)

---

## Contributing

See [CONTRIBUTING.md](https://github.com/karanhudia/borg-ui/blob/main/.github/CONTRIBUTING.md) for:
- Code style guidelines
- Pull request process
- Issue reporting
