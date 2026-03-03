# Codebase Structure

**Analysis Date:** 2026-03-03

## Directory Layout

```
borg-ui/
├── app/                           # FastAPI backend application
│   ├── api/                       # REST API endpoints (routers)
│   ├── core/                      # Core utilities (Borg, auth, errors)
│   ├── database/                  # Database models and configuration
│   ├── models/                    # Legacy models (being replaced)
│   ├── routers/                   # Additional router definitions
│   ├── services/                  # Business logic and operations
│   ├── static/                    # Static assets and frontend build
│   ├── utils/                     # Shared utility functions
│   ├── tests/                     # Backend tests
│   ├── main.py                    # FastAPI application entry point
│   └── config.py                  # Configuration/settings
├── frontend/                      # React SPA frontend application
│   ├── src/                       # Frontend source code
│   │   ├── components/            # React components (UI building blocks)
│   │   ├── pages/                 # Page components (routed views)
│   │   ├── services/              # API client and data fetching
│   │   ├── hooks/                 # Custom React hooks
│   │   ├── context/               # React Context providers
│   │   ├── types/                 # TypeScript type definitions
│   │   ├── utils/                 # Utility functions
│   │   ├── locales/               # i18n translation files
│   │   ├── test/                  # Test utilities and helpers
│   │   ├── App.tsx                # Root app component
│   │   ├── main.tsx               # React entry point
│   │   └── index.css              # Global styles
│   ├── public/                    # Static assets (logo, favicon)
│   ├── build/                     # Built/compiled frontend
│   ├── coverage/                  # Test coverage reports
│   ├── vite.config.ts             # Vite build configuration
│   ├── tsconfig.json              # TypeScript configuration
│   ├── vitest.config.ts           # Vitest testing configuration
│   ├── eslint.config.mjs          # ESLint linting rules
│   └── package.json               # Dependencies and scripts
├── tests/                         # Integration/E2E tests
├── config/                        # Configuration files
├── data/                          # Data directory (databases, logs)
├── docs/                          # Documentation
├── .github/                       # GitHub workflows and CI/CD
├── scripts/                       # Utility scripts
├── docker-compose.yml             # Docker Compose configuration
├── Dockerfile                     # Container image definition
└── README.md                      # Project overview
```

## Directory Purposes

**Backend Structure:**

**`app/api/`:**
- Purpose: FastAPI router definitions for REST endpoints
- Contains: Python modules, one per feature area (backup.py, schedule.py, repositories.py, etc.)
- Key files:
  - `app/api/backup.py`: Backup operation endpoints
  - `app/api/schedule.py`: Schedule CRUD and job management
  - `app/api/repositories.py`: Repository configuration endpoints
  - `app/api/dashboard.py`: Dashboard statistics and overview
  - `app/api/auth.py`: Authentication and user management
  - `app/api/archives.py`: Archive listing and metadata
  - `app/api/restore.py`: Restore operation endpoints
  - `app/api/ssh_keys.py`: SSH key management
  - `app/api/settings.py`: Application settings endpoints
- Pattern: Each module defines a FastAPI router with related endpoints sharing a URL prefix

**`app/services/`:**
- Purpose: Business logic and external system operations
- Contains: Large Python modules implementing core functionality
- Key files:
  - `app/services/backup_service.py`: Borg create command execution, job management
  - `app/services/repositories.py`: Repository validation, initialization, locking
  - `app/services/schedule.py`: Cron scheduling and scheduled job execution
  - `app/services/restore_service.py`: Archive extraction and restore operations
  - `app/services/ssh_keys.py`: SSH key generation, storage, encryption
  - `app/services/notification_service.py`: Email, webhook, and system notifications
  - `app/services/mount_service.py`: Archive mounting via FUSE
  - `app/services/mqtt_service.py`: MQTT broker integration
  - `app/services/script_library_executor.py`: User script execution framework
- Pattern: Singleton-like pattern; services imported and used across API endpoints

**`app/core/`:**
- Purpose: Core utilities and cross-cutting concerns
- Contains:
  - `app/core/borg.py`: Borg CLI wrapper; executes all Borg commands
  - `app/core/borg_errors.py`: Borg-specific error types and parsing
  - `app/core/security.py`: JWT authentication, user creation, current user dependency
- Pattern: Low-level abstraction; used throughout service and API layers

**`app/database/`:**
- Purpose: Data persistence and ORM
- Contains:
  - `app/database/models.py`: SQLAlchemy model definitions (User, Repository, BackupJob, etc.)
  - `app/database/database.py`: Engine creation, session factory, database dependency
  - `app/database/migrations/`: Alembic migration files
- Pattern: Models define database schema; migrations track schema evolution

**`app/utils/`:**
- Purpose: Shared utilities and helpers
- Contains:
  - `app/utils/datetime_utils.py`: UTC timestamp handling, serialization
  - `app/utils/process_utils.py`: Process execution, output capture
  - `app/utils/script_params.py`: Script parameter parsing and validation

**Frontend Structure:**

**`frontend/src/components/`:**
- Purpose: Reusable React UI components
- Contains: Component files, typically one component per file with `.tsx` extension
- Naming: PascalCase (e.g., `BackupJobsTable.tsx`, `RepositoryWizard.tsx`)
- Organization: Components organized by feature area
  - Wizard components: `wizard/` subdirectory
  - Dialog components: Named `*Dialog.tsx`
  - Form components: Named `*Form.tsx` or `*Input.tsx`
  - Table/list components: Named `*Table.tsx`, `*List.tsx`, `*Card.tsx`
- Key files:
  - `frontend/src/components/Layout.tsx`: Main app layout wrapper
  - `frontend/src/components/ProtectedRoute.tsx`: Auth guard component
  - `frontend/src/components/RepositoryWizard.tsx`: Multi-step repo creation
  - `frontend/src/components/BackupJobsTable.tsx`: Job status and history

**`frontend/src/pages/`:**
- Purpose: Page-level components corresponding to routes
- Contains: Full-page components; one per route
- Naming: PascalCase matching route name (e.g., `Backup.tsx` → `/backup` route)
- Key files:
  - `frontend/src/pages/Login.tsx`: Authentication form
  - `frontend/src/pages/DashboardNew.tsx`: Dashboard overview
  - `frontend/src/pages/Backup.tsx`: Manual backup interface
  - `frontend/src/pages/Repositories.tsx`: Repository management
  - `frontend/src/pages/Schedule.tsx`: Schedule management
  - `frontend/src/pages/Restore.tsx`: Restore operation interface
  - `frontend/src/pages/Archives.tsx`: Archive browsing

**`frontend/src/services/`:**
- Purpose: API client and data fetching logic
- Contains:
  - `frontend/src/services/api.ts`: Axios instance, base config, API client methods
- Pattern: Centralized HTTP client with interceptors for auth token handling

**`frontend/src/hooks/`:**
- Purpose: Custom React hooks for shared logic
- Contains:
  - `frontend/src/hooks/useAuth.tsx`: Authentication state and login/logout
  - `frontend/src/hooks/useMaintenanceJobs.ts`: Maintenance job polling
  - `frontend/src/hooks/useMatomo.ts`: Analytics tracking
- Pattern: React hooks encapsulate stateful logic; used by multiple components

**`frontend/src/context/`:**
- Purpose: React Context providers for app-wide state
- Contains:
  - `frontend/src/context/AppContext.tsx`: Global app settings, preferences, analytics
  - `frontend/src/context/ThemeContext.tsx`: Theme (light/dark mode)
- Pattern: Providers wrap `<App />` in `main.tsx`; consumed via `useContext`

**`frontend/src/types/`:**
- Purpose: TypeScript type definitions for domain models
- Contains: Type interfaces matching backend API response shapes
- Pattern: Exported types imported in components and services

**`frontend/src/utils/`:**
- Purpose: Utility functions and helpers
- Contains:
  - `frontend/src/utils/matomo.ts`: Analytics utilities
  - Date/time helpers, validation functions, string utilities
- Pattern: Pure functions; no side effects

**`frontend/src/locales/`:**
- Purpose: i18n translation files for multi-language support
- Contains: JSON files per language (en.json, es.json, de.json)
- Pattern: i18next loads translations; used via `useTranslation` hook

**`frontend/src/test/`:**
- Purpose: Test utilities and helpers
- Contains:
  - `frontend/src/test/test-utils.tsx`: Test setup, custom render functions
  - `frontend/src/test/helpers.tsx`: Mock data, test utilities

## Key File Locations

**Entry Points:**
- Backend: `app/main.py` - FastAPI application initialization
- Frontend: `frontend/src/main.tsx` - React DOM render
- Frontend app logic: `frontend/src/App.tsx` - Route definitions and auth wrapper

**Configuration:**
- Backend: `app/config.py` - Settings class with all configuration
- Backend: `.env` file - Environment variable overrides (not committed)
- Frontend: `frontend/vite.config.ts` - Vite build configuration
- Frontend: `frontend/tsconfig.json` - TypeScript compiler options

**Core Logic:**
- Backup operations: `app/services/backup_service.py`
- Borg CLI integration: `app/core/borg.py`
- Job scheduling: `app/services/schedule.py`
- Repository management: `app/services/repositories.py`
- Authentication: `app/core/security.py`

**Testing:**
- Backend tests: `app/tests/` (pytest)
- Frontend tests: `frontend/src/**/__tests__/` (Vitest)
- Test utilities: `frontend/src/test/`

## Naming Conventions

**Files:**
- **Backend Python files:** `snake_case.py` (e.g., `backup_service.py`, `borg_errors.py`)
- **Frontend component files:** `PascalCase.tsx` (e.g., `RepositoryWizard.tsx`)
- **Frontend utility files:** `camelCase.ts` (e.g., `matomo.ts`, `datetime_utils.js`)
- **Test files:** `*.test.ts`, `*.test.tsx`, `*.spec.ts` for Vitest; `test_*.py` for pytest

**Directories:**
- **Feature-based:** Most directories named after feature (backup, schedule, repositories)
- **Layer-based:** Some named by function (api, services, utils, core)
- **Lowercase:** All directory names lowercase with underscores (app/api, app/services, frontend/src/components)

**TypeScript:**
- **Components:** PascalCase (Component.tsx)
- **Functions:** camelCase (useAuth, formatDate)
- **Types:** PascalCase (Repository, BackupJob, User)
- **Constants:** UPPER_SNAKE_CASE (API_BASE_URL, DEFAULT_RETRY_COUNT)
- **Interfaces:** PascalCase with optional I prefix (IRepository or Repository)

**Python:**
- **Classes:** PascalCase (User, Repository, BackupJob)
- **Functions:** snake_case (get_current_user, create_backup)
- **Constants:** UPPER_SNAKE_CASE (DEFAULT_TIMEOUT, LOG_LEVEL)
- **Modules:** snake_case (backup_service.py, borg_errors.py)

## Where to Add New Code

**New Feature (e.g., new backup destination type):**
- Primary code:
  - API endpoint: `app/api/[feature].py` (new file or existing matching file)
  - Service logic: `app/services/[feature]_service.py` (new file if significant)
  - Models: Add to `app/database/models.py`
- Frontend:
  - Page/form: `frontend/src/pages/[Feature].tsx` or `frontend/src/components/[Feature]Form.tsx`
  - API calls: Add methods to `frontend/src/services/api.ts`
  - Types: Add to `frontend/src/types/` or inline in api.ts
- Tests:
  - Backend: `app/tests/test_[feature].py`
  - Frontend: `frontend/src/components/__tests__/[Feature].test.tsx` or `frontend/src/pages/__tests__/[Feature].test.tsx`

**New Component/Module:**
- If presentation: `frontend/src/components/[ModuleName].tsx`
- If business logic: `app/services/[module]_service.py`
- If utility function: `app/utils/[function_name].py` (backend) or `frontend/src/utils/[functionName].ts` (frontend)
- If custom hook: `frontend/src/hooks/use[HookName].tsx`

**Utilities:**
- Shared backend helpers: `app/utils/[utility_name].py`
- Shared frontend helpers: `frontend/src/utils/[utilityName].ts`
- Component helpers: Keep in component file unless used by >2 components
- Type utilities: Keep in `frontend/src/types/` or relevant service/utils file

**Configuration & Constants:**
- Backend: `app/config.py` for environment-driven settings
- Frontend: `frontend/src/utils/constants.ts` or top of relevant component/service
- Global frontend constants: Environment variables via `import.meta.env` (Vite)

## Special Directories

**`app/static/`:**
- Purpose: Static assets served by FastAPI (frontend build output, images, CSS)
- Generated: Yes - built frontend copied here during build
- Committed: No - only .gitignore'd build artifacts

**`frontend/build/`:**
- Purpose: Vite build output (compiled JavaScript, CSS, HTML)
- Generated: Yes - created by `npm run build`
- Committed: No

**`frontend/coverage/`:**
- Purpose: Test coverage reports from Vitest
- Generated: Yes - created by `npm run test:coverage`
- Committed: No

**`app/tests/` and `frontend/src/**/__tests__/`:**
- Purpose: Test files parallel to source files
- Generated: No - manually written
- Committed: Yes

**`.env` file:**
- Purpose: Local environment variable overrides for development
- Generated: No - create from `.env.example`
- Committed: No - contains secrets

**`app/database/migrations/`:**
- Purpose: Alembic schema migration history
- Generated: Partially - created by `alembic revision --autogenerate`
- Committed: Yes - part of version control

---

*Structure analysis: 2026-03-03*
