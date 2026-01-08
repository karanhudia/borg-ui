# Devcontainer Configuration Design

**Date:** 2026-01-07
**Author:** Claude Sonnet 4.5
**Status:** Approved

## Overview

Add VS Code devcontainer configuration to enable containerized development environment for Borg Web UI. This provides a consistent, reproducible development setup with all dependencies pre-installed.

## Requirements

- Full-stack development environment (Python + Node.js)
- All services installed in devcontainer (Redis, Borg Backup)
- Complete VS Code extension set for Python, TypeScript, Docker, Git, and testing
- Match production environment versions (Python 3.10, Node.js 22)
- Auto-setup on container creation

## Architecture

### File Structure

```
.devcontainer/
├── devcontainer.json    # Main VS Code devcontainer configuration
├── Dockerfile           # Custom image with Borg + Redis
└── post-create.sh       # Setup script run after container creation
```

### Base Configuration

- **Base Image:** Python 3.10 on Debian/Ubuntu
- **Additional Features:** Node.js 22 via VS Code dev container features
- **User:** Non-root `vscode` user with sudo access
- **Workspace Mount:** Bind mount with consistent file permissions

### Services & Dependencies

**Installed Services:**
- Redis Server (via apt, auto-starts)
- Borg Backup 1.4.3+ (via pip, matching production)
- All Borg system dependencies (libacl1, libssl, liblz4, libzstd, libxxhash, etc.)

**Python Environment:**
- Python 3.10
- All packages from `requirements.txt`
- pytest, coverage, and dev tools

**Frontend Environment:**
- Node.js 22 with npm
- All packages from `frontend/package.json`
- Vite dev server

**Port Forwarding:**
- `8081` - Backend API (FastAPI/uvicorn)
- `5173` - Frontend dev server (Vite)
- `6379` - Redis (for debugging)

### VS Code Extensions

**Python Development:**
- `ms-python.python` - Python language support
- `ms-python.vscode-pylance` - Python language server
- `ms-python.black-formatter` - Black formatter
- `charliermarsh.ruff` - Ruff linter

**Frontend Development:**
- `dbaeumer.vscode-eslint` - ESLint
- `esbenp.prettier-vscode` - Prettier formatter
- `bradlc.vscode-tailwindcss` - Tailwind IntelliSense

**Database & Docker:**
- `ms-azuretools.vscode-docker` - Docker management
- `alexcvzz.vscode-sqlite` - SQLite viewer

**Git & Testing:**
- `eamodio.gitlens` - Git features
- `hbenl.vscode-test-explorer` - Test Explorer
- `ryanluker.vscode-coverage-gutters` - Coverage visualization

### Post-Creation Setup

The `post-create.sh` script will:
1. Start Redis server in background
2. Install Python dependencies from `requirements.txt`
3. Install frontend dependencies from `frontend/package.json`
4. Create necessary directories (`/data`, `/backups`, etc.)
5. Set up database and initial configuration

### Development Workflow

**Backend Development:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8081
```

**Frontend Development:**
```bash
cd frontend && npm run dev
```

**Run Tests:**
```bash
pytest
```

**Database Access:**
- SQLite database at `/data/borg.db`
- Use SQLite extension to browse

## Benefits

- **Consistency:** Every developer gets identical environment
- **Quick Setup:** Single click to start developing
- **No Local Pollution:** All tools contained in container
- **Production Parity:** Matches production Python/Node versions
- **Integrated Testing:** All test tools pre-installed

## Trade-offs

**Chosen Approach (Self-contained):**
- ✅ Simple, single-container setup
- ✅ No external dependencies needed
- ✅ Tests run immediately
- ❌ Slightly larger container size
- ❌ Redis data ephemeral (acceptable for dev)

**Alternative (docker-compose services):**
- ✅ Closer to production setup
- ✅ Smaller devcontainer
- ❌ More complex configuration
- ❌ Requires docker-compose knowledge

## Implementation Files

1. `.devcontainer/Dockerfile` - Custom image with Redis, Borg, and system dependencies
2. `.devcontainer/devcontainer.json` - VS Code configuration with extensions and settings
3. `.devcontainer/post-create.sh` - Setup script for dependencies and services

## Testing

To test the devcontainer:
1. Open VS Code command palette
2. Run "Dev Containers: Rebuild and Reopen in Container"
3. Wait for post-create script to complete
4. Verify services running: `redis-cli ping`, `borg --version`
5. Run test suite: `pytest`
6. Start dev servers and verify ports accessible
