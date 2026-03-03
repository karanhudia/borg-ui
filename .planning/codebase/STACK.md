# Technology Stack

**Analysis Date:** 2026-03-03

## Languages

**Primary:**
- Python 3.10 - Backend API server and core Borg operations management
- TypeScript 5.9 - React frontend and type safety
- Node.js 22 (Alpine) - Frontend build and development server

**Secondary:**
- JavaScript (in config files and build scripts)
- Shell scripts (deployment, testing, setup)

## Runtime

**Backend:**
- Python 3.10-slim (Docker base image)
- FastAPI 0.128.8 - Web framework
- Uvicorn 0.24.0 - ASGI server
- Gunicorn 25.1.0 - Production application server

**Frontend:**
- Node 22-alpine - Build environment
- React 18.2.0 - UI framework
- Vite 7.2.4 - Build tool and dev server

**Package Managers:**
- npm (Node) - Frontend dependencies with lockfile (package-lock.json)
- pip (Python) - Backend dependencies with lockfile (requirements.txt)

## Frameworks

**Backend:**
- FastAPI 0.128.8 - REST API framework with automatic OpenAPI documentation
- SQLAlchemy 2.0.46 - ORM for database operations
- Alembic 1.12.1 - Database migration management
- Pydantic 2.12.5 - Data validation using Python type hints
- Pydantic Settings 2.1.0 - Configuration management

**Frontend:**
- React 18.2.0 - Component-based UI library
- React Router 7.13.0 - Client-side routing
- TanStack React Query 5.90.10 - Data fetching and caching
- i18next 25.8.13 - Internationalization framework
- React i18next 16.5.4 - React binding for i18next

**UI/Styling:**
- Material-UI (MUI) 7.3.5 - Component library
- Tailwind CSS 3.4.18 - Utility-first CSS framework
- Emotion 11.14+ - CSS-in-JS styling (via MUI)
- Lucide React 0.554.0 - Icon library

**Testing:**
- Vitest 4.0.18 - Unit/integration test framework (frontend)
- Testing Library React 16.3.2 - React component testing utilities
- Testing Library Jest DOM 6.9.1 - DOM matchers
- pytest 7.4.3 - Unit testing framework (backend)
- pytest-cov 7.0.0 - Test coverage reporting
- pytest-asyncio 0.21.1 - Async test support

**Build/Dev Tools:**
- Vite 7.2.4 - Frontend bundler and dev server
- @vitejs/plugin-react 5.1.1 - React support for Vite
- @vitest/coverage-v8 4.0.18 - Coverage reporting
- @vitest/ui 4.0.18 - Test UI dashboard
- Prettier 3.6.2 - Code formatter
- ESLint 9.39.1 - JavaScript linting
- TypeScript ESLint 8.48.0 - TypeScript linting
- Husky 9.1.7 - Git hooks framework
- Lint-staged 16.2.7 - Pre-commit linting

## Key Dependencies

**Critical Backend:**
- borgbackup[fuse] 1.4.3+ - Core backup software with FUSE mount support
- redis 7.1.1 - In-memory cache for archive browsing (optional but recommended)
- paho-mqtt 1.6.1 - MQTT client for Home Assistant integration
- apprise 1.9.6 - Multi-service notification delivery
- croniter 6.0.0 - Cron expression parsing for scheduling
- httpx 0.25.2 - Async HTTP client
- python-jose[cryptography] 3.4.0 - JWT token handling
- bcrypt 5.0.0 - Password hashing
- cryptography 46.0.5 - Encryption utilities
- structlog 25.5.0 - Structured logging
- pyyaml 6.0.1 - YAML parsing for configuration
- python-multipart 0.0.20 - Multipart form data parsing
- psutil 7.2.2 - System resource monitoring
- fastapi-cache2 0.2.1 - Caching middleware for FastAPI

**Critical Frontend:**
- axios 1.13.2 - HTTP client for API communication
- react-hook-form 7.66.1 - Efficient form state management
- react-hot-toast 2.6.0 - Toast notification library
- recharts 3.5.0 - Data visualization (charts and graphs)
- date-fns 4.1.0 - Date manipulation utilities
- cron-parser 5.5.0 - Cron expression parsing
- @monaco-editor/react 4.7.0 - Code editor component

**Development:**
- happy-dom 20.3.7 - Lightweight DOM implementation for testing
- jsdom 28.1.0 - JavaScript implementation of web standards
- axios-mock-adapter 2.1.0 - Mock axios for testing

## Configuration

**Environment Variables:**
- `.env` file (created from `.env.example`) - Runtime configuration
- `DATA_DIR` - Persistent data directory (default: `/data`)
- `DATABASE_URL` - SQLite database path (auto-derived from DATA_DIR)
- `ENVIRONMENT` - production/development mode
- `PORT` - Application port (default: 8081)
- `LOG_LEVEL` - DEBUG/INFO/WARNING/ERROR/CRITICAL
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` - Redis connection settings
- `REDIS_URL` - External Redis URL (takes precedence)
- `DISABLE_AUTHENTICATION` - Bypass built-in auth for reverse proxy
- `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT` - MQTT broker connection
- `VITE_API_URL` - Frontend API endpoint (default: `/api`)

**Build Configuration:**
- `frontend/vite.config.ts` - Vite bundler and dev server config
- `frontend/tsconfig.json` - TypeScript compiler options
- `frontend/tailwind.config.js` - Tailwind CSS customization
- `frontend/postcss.config.cjs` - PostCSS plugin configuration
- `frontend/eslint.config.mjs` - ESLint rules (flat config format)
- `frontend/.prettierrc.json` - Code formatting rules
- `frontend/vitest.config.ts` - Test runner configuration

**Python Configuration:**
- `app/config.py` - Settings class using Pydantic BaseSettings
- `Dockerfile` - Multi-stage build (frontend + backend)
- `docker-compose.yml` - Local development orchestration with Redis service

## Platform Requirements

**Development:**
- Node 22+ (Alpine-based)
- Python 3.10+
- Docker and Docker Compose (for local environment)
- npm/pip for dependency management
- Git for version control

**Production:**
- Docker (containerized deployment)
- 2+ CPU cores recommended
- 2GB+ RAM recommended
- SQLite database storage (or external database via DATABASE_URL)
- Redis 7+ optional but recommended for archive browsing performance
- MQTT broker optional for Home Assistant integration

**OS Support:**
- Linux (primary deployment target)
- macOS (local development)
- Windows (via WSL2/Docker Desktop)

## Deployment Configuration

**Container Image:**
- Python 3.10-slim base
- Frontend built with Node 22-alpine, assets copied to static directory
- System dependencies: borgbackup, FUSE, SSH client, cron, curl
- Gunicorn + Uvicorn for ASGI application serving
- Health check via HTTP GET on configured port

**Data Persistence:**
- SQLite database at `/data/borg.db` (or configurable via DATABASE_URL)
- SSH keys directory at `/data/ssh_keys`
- Logs at `/data/logs/borg-ui.log`
- Secret key persisted at `/data/.secret_key`
- Borg repository cache at `/home/borg/.cache/borg`

**Networking:**
- Port 8081 (HTTP, configurable via PORT)
- Port 6379 (Redis, internal Docker network)
- Volume mounts for filesystem access to backup sources
- CORS configured for frontend at `http://localhost:7879` and `http://localhost:8000` (development)

---

*Stack analysis: 2026-03-03*
