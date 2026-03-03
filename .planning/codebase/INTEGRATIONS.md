# External Integrations

**Analysis Date:** 2026-03-03

## APIs & External Services

**Notification Service:**
- Apprise (Multi-service) - Unified notification delivery across 100+ services
  - SDK/Client: `apprise` (1.9.6)
  - Supported channels: Email, Slack, Discord, Telegram, PushBullet, and many more
  - Implementation: `app/services/notification_service.py` - Sends notifications on backup/restore events
  - Configuration: Stored in database via `NotificationSettings` model

**Home Assistant Integration:**
- MQTT - Real-time state synchronization for Home Assistant
  - SDK/Client: `paho-mqtt` (1.6.1)
  - Implementation: `app/services/mqtt_service.py`
  - Features:
    - Auto-discovery device registration for Home Assistant
    - Sensor definitions for repository status, size, activity
    - Bidirectional sync: publishes metrics and syncs on changes
  - Configuration: `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT`, `MQTT_BASE_TOPIC`
  - Scheduler: `app/services/mqtt_sync_scheduler.py` - Periodic sync tasks

**Analytics/Telemetry:**
- Matomo (Optional) - Privacy-respecting analytics
  - Implementation: `frontend/src/utils/matomo.ts`
  - URL: `https://analytics.nullcodeai.dev` (centralized service)
  - Conditional: User opt-in via Settings → Analytics Consent
  - No tracking until user explicitly enables (defaults to disabled)
  - Stored preference: `analytics_enabled` in database

## Data Storage

**Databases:**
- SQLite (Primary)
  - Connection: `sqlite:////data/borg.db` (auto-derived from DATA_DIR)
  - Client: SQLAlchemy 2.0.46 ORM
  - Alternative: External database via `DATABASE_URL` env var
  - Migrations: Alembic 1.12.1 for schema versioning
  - Models: `app/database/models/` - All schema definitions

**File Storage:**
- Local filesystem only
  - Mounted via Docker volumes (configurable mount points)
  - Default: Entire host filesystem at `/local` (development)
  - Production: Specific directories should be mounted
  - SSH-based remote backups: Via SSH connection to remote servers
  - SSHFS mounts: For remote-to-remote backups (requires privileged container)

**Caching:**
- Redis 7-alpine (Optional but highly recommended)
  - Connection: `redis://localhost:6379/0` (default) or `REDIS_URL` env var
  - Client: `redis` (7.1.1)
  - Purpose: Archive browsing cache (600x performance improvement)
  - Implementation: `app/services/cache_service.py`
  - Fallback: In-memory LRU cache when Redis unavailable
  - Configuration: `CACHE_TTL_SECONDS`, `CACHE_MAX_SIZE_MB` via Settings UI
  - Docker service: `redis` container in docker-compose.yml

## Authentication & Identity

**Auth Provider:**
- Built-in JWT-based authentication
  - Token storage: JWT tokens with HS256 algorithm
  - Session duration: 24 hours (configurable via `access_token_expire_minutes`)
  - Storage: SQLAlchemy database with bcrypt password hashing
  - Implementation: `app/core/security.py`
  - First user: Auto-created on first login with environment-set password

**Proxy Authentication:**
- Optional reverse proxy auth support
  - Enabled: `DISABLE_AUTHENTICATION=true`
  - Header: `X-Forwarded-User` (configurable via `proxy_auth_header`)
  - Use case: Integration with external auth systems (OAuth, LDAP, etc.)
  - Configuration: `app/config.py` Settings class

## Monitoring & Observability

**Error Tracking:**
- Not integrated - Structured logging only
  - Errors logged via structlog

**Logs:**
- Structured logging with structlog 25.5.0
  - Format: JSON in production, human-readable in debug mode
  - Output: Console + file at `/data/logs/borg-ui.log`
  - Level: Configurable via `LOG_LEVEL` env var (default: INFO)
  - Implementation: Initialized in `app/main.py`

**Metrics/Monitoring:**
- Prometheus metrics endpoint
  - Route: `/metrics` (no `/api` prefix)
  - Implementation: `app/api/metrics.py`
  - Metrics include: Backup stats, system health, operation counts
  - Compatible with Prometheus scrapers

**Health Checks:**
- HTTP health endpoint
  - Route: `/` (root) returns HTML frontend
  - Docker healthcheck: `curl -f http://localhost:8081/`
  - Check interval: 30 seconds, timeout: 10 seconds

## CI/CD & Deployment

**Hosting:**
- Docker-first deployment
  - Container registry: Docker Hub (image: `karanhudia/borg-ui`)
  - Base images: `python:3.10-slim` (backend), `node:22-alpine` (frontend builder)

**CI Pipeline:**
- GitHub Actions (inferred from `.github/workflows/`)
  - Tests: Backend pytest, frontend Vitest
  - Build: Multi-stage Docker build
  - Releases: Tagged versions via `scripts/release.sh`

**Container Orchestration:**
- Docker Compose (local development and simple deployments)
  - Services: `app` (main), `redis` (cache)
  - Networks: `borg_network` (bridge)
  - Volumes: `borg_data` (app data), `borg_cache` (Borg cache)
  - Version: 3.8+

## Environment Configuration

**Required env vars (with defaults):**
- `PORT` - Server port (default: 8081)
- `ENVIRONMENT` - Mode: production/development (default: production)
- `DATA_DIR` - Persistent data path (default: `/data`)

**Optional but recommended:**
- `REDIS_HOST`, `REDIS_PORT` - Redis connection (localhost:6379)
- `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT` - Home Assistant MQTT
- `VITE_API_URL` - Frontend API endpoint (default: `/api`)

**Secrets location:**
- `.env` file (Git-ignored, created from `.env.example`)
- Secret key: Auto-generated and persisted to `/data/.secret_key`
- SSH keys: Stored at `/data/ssh_keys` (user-provided for remote repos)

**Secrets NOT stored in env:**
- SSH private keys - Uploaded via UI, stored in `/data/ssh_keys`
- Database passwords - SQLite uses file permissions, external DB via URL
- API tokens - For remote services stored in notification settings

## Webhooks & Callbacks

**Incoming:**
- None detected - Application is single-directional (no external webhook listeners)

**Outgoing:**
- Apprise notifications - Sent to configured services on backup/restore events
  - Triggered by: Backup completion, restore completion, check failures
  - Implementation: `app/services/notification_service.py`

- MQTT publications - State updates to Home Assistant
  - Topics: `borg_ui/repositories/{repo_id}/status`, `.../size`, etc.
  - Triggered by: Repository state changes, backup job completion
  - Auto-discovery: `homeassistant/sensor/borg_ui_{repo_id}_{type}/config`

- HTTP requests to remote Borg repositories
  - Via SSH: OpenSSH client for SSH-based repos
  - Via SSHFS: For remote-to-remote backup capability

## Remote Repository Connections

**SSH/SFTP:**
- Client: OpenSSH (`openssh-client` system package)
- Implementation: `app/services/remote_backup_service.py`
- SSH key management: UI-based key upload to `/data/ssh_keys`
- Authentication: Public key only (passwords not supported for security)
- Connection pooling: Via SSH agent

**SSHFS (Remote-to-Remote):**
- Package: `sshfs` (system package)
- Purpose: Mount remote locations as local filesystems
- Requirement: Privileged Docker container mode
- Use case: Backup one server to another via SSH

---

*Integration audit: 2026-03-03*
