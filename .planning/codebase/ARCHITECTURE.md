# Architecture

**Analysis Date:** 2026-03-03

## Pattern Overview

**Overall:** Layered monolith with clear separation between frontend (React SPA) and backend (FastAPI REST API)

**Key Characteristics:**
- Frontend and backend are independently deployable
- Backend follows REST API conventions with FastAPI router-based organization
- Frontend uses React hooks and React Query for state management
- Asynchronous job processing for long-running backup operations
- Database-driven with SQLAlchemy ORM (SQLite or PostgreSQL support)

## Layers

**Presentation Layer (Frontend):**
- Purpose: User interface and client-side logic
- Location: `frontend/src/`
- Contains: React components, pages, services, hooks, utilities
- Depends on: Backend REST API via `services/api.ts`
- Used by: Web browsers (HTTP clients)

**API Layer (Backend):**
- Purpose: REST endpoint definitions and request handling
- Location: `app/api/`
- Contains: FastAPI routers, request/response models, endpoint logic
- Depends on: Service layer, database models, core utilities
- Used by: Frontend via HTTP, external tools via OpenAPI docs

**Service Layer (Backend):**
- Purpose: Business logic, orchestration, and external system integration
- Location: `app/services/`
- Contains: Borg backup operations, SSH connections, notifications, job scheduling
- Depends on: Database models, core utilities, external systems
- Used by: API layer, background job processors

**Core Layer (Backend):**
- Purpose: Low-level utilities and cross-cutting concerns
- Location: `app/core/`
- Contains: Borg CLI wrapper, security (auth, JWT), error handling
- Depends on: System utilities, standard library
- Used by: Service and API layers

**Database Layer (Backend):**
- Purpose: Data persistence and ORM
- Location: `app/database/`
- Contains: SQLAlchemy models, database configuration, migrations
- Depends on: SQLAlchemy, configured database backend
- Used by: Service and API layers via dependency injection

**Utilities (Backend):**
- Purpose: Shared helper functions
- Location: `app/utils/`
- Contains: Date/time handling, process execution, script parameter handling
- Depends on: Standard library
- Used by: Service and API layers

## Data Flow

**User Authentication Flow:**

1. User submits credentials via `Login.tsx`
2. Frontend calls `POST /api/auth/login` with username/password
3. `app/api/auth.py` validates credentials against `User` model in database
4. Backend returns JWT token if valid
5. Frontend stores token in localStorage
6. Token included in `Authorization` header for subsequent requests
7. `useAuth` hook reads token and provides auth context to app
8. `ProtectedRoute` component enforces authentication on protected pages

**Backup Job Execution Flow:**

1. User initiates backup from `Backup.tsx` page
2. Frontend calls `POST /api/backup/start` with repository path
3. `app/api/backup.py` creates `BackupJob` record in database
4. Backend returns job ID and status "pending"
5. `backup_service.py` starts async backup process via Borg CLI
6. Backend writes job status updates to `BackupJob.status` (pending → running → success/failed)
7. Frontend polls `GET /api/dashboard/` to fetch updated job status via React Query
8. Dashboard displays job status changes and progress
9. After completion, frontend fetches updated archives via `GET /api/archives/`
10. Frontend updates local state with fresh archive data

**Repository Configuration Flow:**

1. User creates/edits repository via `RepositoryWizard.tsx`
2. Frontend calls API to create/update `Repository` model
3. Backend validates configuration and stores in database
4. Service layer uses configuration to execute Borg commands
5. Changes reflected immediately in dashboard via React Query invalidation

**State Management:**
- Backend: Source of truth stored in SQLite/PostgreSQL database
- Frontend: React Query manages server state caching with configurable stale times
- Real-time updates: Polling via React Query with 30s stale time, 5min cache time
- Long-running operations: Async job queue with status tracking in database

## Key Abstractions

**Repository:**
- Purpose: Represents a Borg backup repository (local or remote)
- Examples: `app/database/models.py` (model), `app/services/repositories.py` (service)
- Pattern: Encapsulates configuration, connection info, authentication state
- Properties: path, encryption, compression, remote connection details, auth status

**BackupJob:**
- Purpose: Represents a single backup execution with status tracking
- Examples: `app/database/models.py` (model), `app/api/backup.py` (endpoint)
- Pattern: Transient records created per backup execution
- Properties: repository path, status, start/end times, error messages

**SSHConnection:**
- Purpose: Reusable SSH connection configuration for remote repositories and data sources
- Examples: `app/database/models.py` (model), `app/api/ssh_keys.py` (endpoint)
- Pattern: Many-to-many with Repository for backup destinations and data sources
- Properties: host, port, username, SSH key reference

**ScheduledJob:**
- Purpose: Cron-scheduled backup or maintenance operations
- Examples: `app/database/models.py` (model), `app/api/schedule.py` (endpoint)
- Pattern: Defines schedule and target repositories; executed by background scheduler
- Properties: cron expression, type (backup/check/prune), linked repositories

**Borg Wrapper:**
- Purpose: Execute Borg backup CLI commands with error handling
- Examples: `app/core/borg.py`
- Pattern: Subprocess wrapper that parses output and raises typed exceptions
- Usage: All Borg operations flow through this single interface

## Entry Points

**Backend Entry Point:**
- Location: `app/main.py`
- Triggers: Application startup via Uvicorn/Gunicorn
- Responsibilities: FastAPI app initialization, router registration, middleware setup, database table creation, security initialization

**Frontend Entry Point:**
- Location: `frontend/src/main.tsx`
- Triggers: Browser page load
- Responsibilities: React DOM initialization, provider setup (Theme, Auth, Query, Router), i18n initialization

**Background Job Processing:**
- Location: Not explicitly in main.py; implemented via `services/` modules and APScheduler
- Triggers: Time-based scheduler (scheduled backups/checks) and job status polling
- Responsibilities: Execute scheduled operations, update job status, trigger notifications

## Error Handling

**Strategy:** Layered error handling with specific exception types and user-friendly messaging

**Patterns:**

- **Backend API errors:** FastAPI HTTPException with status codes and detail messages
- **Service layer errors:** Custom exceptions in `app/core/borg_errors.py` (BorgError, BorgRepositoryNotFound, etc.)
- **Borg CLI errors:** Output parsing in `app/core/borg.py` converts exit codes to typed exceptions
- **Frontend errors:** API errors caught in service layer, displayed via toast notifications (react-hot-toast)
- **Database errors:** SQLAlchemy errors caught and converted to HTTPException in API layer
- **Validation:** Pydantic models validate all request/response data

## Cross-Cutting Concerns

**Logging:**
- Backend: Structured logging via `structlog` with JSON output (or console in DEBUG mode)
- Frontend: Console logging only, no persistent logs
- Configuration: `LOG_LEVEL` environment variable controls backend logging level

**Validation:**
- Backend: Pydantic BaseModel for request/response validation
- Frontend: React Hook Form with custom validators on form components
- Database: SQLAlchemy model constraints (unique, foreign keys, nullable)

**Authentication:**
- Backend: JWT tokens via `fastapi-jwt-extended` or similar
- JWT payload: user ID, username, token expiration
- Token storage: Backend validates signature; frontend stores in localStorage
- Proxy auth: Optional `X-Forwarded-User` header bypass for reverse proxy scenarios
- Endpoint protection: `@router.get()` decorator with `Depends(get_current_user)`

**CORS:**
- Backend: CORSMiddleware configured with allowed origins from settings
- Default: http://localhost:7879, http://localhost:8000
- Production: Configured via `CORS_ORIGINS` environment variable

---

*Architecture analysis: 2026-03-03*
