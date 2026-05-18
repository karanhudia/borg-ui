from __future__ import annotations

import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import structlog
import os
from dotenv import load_dotenv

from app.api import (
    auth,
    dashboard,
    backup,
    backup_plans,
    archives,
    restore,
    schedule,
    settings as settings_api,
    events,
    repositories,
    ssh_keys,
    system,
    filesystem,
    browse,
    notifications,
    scripts,
    packages,
    activity,
    scripts_library,
    mounts,
    metrics,
    tokens,
    permissions,
    managed_machines,
    agents,
    source_discovery,
)
from app.api.v2 import router as v2_router
from app.routers import config
from app.database.database import engine
from app.database.models import Base
from app.config import get_runtime_app_version, settings
from app.core.proxy_auth import inspect_proxy_auth_config
from app.core.security import create_first_user
from app.services.licensing_service import sync_licensing_state

# Load environment variables
load_dotenv()

# Base path for sub-directory reverse proxy deployment (e.g., /borg-ui)
_base_path_raw = os.getenv("BASE_PATH", "").strip().rstrip("/")
BASE_PATH = "" if _base_path_raw in ("", "/") else _base_path_raw

ROOT_STATIC_FILES: dict[str, str | None] = {
    "logo.png": None,
    "logo.svg": None,
    "favicon.svg": None,
    "favicon.ico": None,
    "favicon-16x16.png": None,
    "favicon-32x32.png": None,
    "announcements.json": "application/json",
}


def _prepare_index_html() -> str | None:
    """Read index.html and optionally rewrite asset paths for BASE_PATH. Cached at module load."""
    try:
        with open("app/static/index.html", "r") as f:
            html = f.read()
    except FileNotFoundError:
        return None
    if BASE_PATH:
        html = html.replace('href="/assets/', f'href="{BASE_PATH}/assets/')
        html = html.replace('src="/assets/', f'src="{BASE_PATH}/assets/')
        html = html.replace('href="/favicon', f'href="{BASE_PATH}/favicon')
        html = html.replace('href="/logo', f'href="{BASE_PATH}/logo')
        html = html.replace(
            "</head>",
            f"<script>"
            f'window.__BASE_PATH__="{BASE_PATH}";'
            f"if(!window.location.pathname.startsWith(window.__BASE_PATH__))"
            f"{{window.location.replace(window.__BASE_PATH__+window.location.pathname+window.location.search+window.location.hash);}}"
            f"</script></head>",
        )
    return html


_cached_index_html = _prepare_index_html()
licensing_refresh_task: asyncio.Task | None = None


def _spawn_background_task(coro):
    task = asyncio.create_task(coro)
    if not isinstance(task, asyncio.Task):
        coro.close()
    return task


def _log_proxy_auth_security_warnings() -> None:
    inspection = inspect_proxy_auth_config()
    if not inspection["enabled"]:
        return

    for warning in inspection["warnings"]:
        logger.warning(
            "Proxy authentication configuration warning",
            code=warning["code"],
            message=warning["message"],
        )


def _log_insecure_no_auth_warning() -> None:
    if not settings.allow_insecure_no_auth:
        return

    logger.warning(
        "Insecure no-auth mode enabled",
        code="insecure_no_auth_enabled",
        message="ALLOW_INSECURE_NO_AUTH is enabled. Borg UI will allow unauthenticated access and impersonate a local user. Use only for local development or explicitly trusted environments.",
    )

    if settings.disable_authentication:
        logger.warning(
            "Proxy auth setting ignored because insecure no-auth is enabled",
            code="auth_mode_conflict",
            message="DISABLE_AUTHENTICATION is ignored while ALLOW_INSECURE_NO_AUTH is enabled. Disable one of the modes so the deployment intent is unambiguous.",
        )


# Configure structured logging
import logging

# Set log level based on environment
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
        if log_level == "DEBUG"
        else structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="Borg Web UI",
    description="A lightweight web interface for Borg backup management",
    version="2.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    root_path=BASE_PATH if BASE_PATH else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend (only if directories exist)
if os.path.exists("app/static/assets"):
    app.mount("/assets", StaticFiles(directory="app/static/assets"), name="assets")
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include API routers
app.include_router(
    metrics.router
)  # /metrics endpoint (disabled by default, no API prefix)
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(backup.router, prefix="/api/backup", tags=["Backup"])
app.include_router(
    backup_plans.router, prefix="/api/backup-plans", tags=["Backup Plans"]
)
app.include_router(archives.router, prefix="/api/archives", tags=["Archives"])
app.include_router(browse.router, prefix="/api/browse", tags=["Browse"])
app.include_router(restore.router, prefix="/api/restore", tags=["Restore"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["Schedule"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["Settings"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(
    repositories.router, prefix="/api/repositories", tags=["Repositories"]
)
app.include_router(ssh_keys.router, prefix="/api/ssh-keys", tags=["SSH Keys"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(filesystem.router, prefix="/api/filesystem", tags=["Filesystem"])
app.include_router(
    scripts.router, prefix="/api/scripts", tags=["Scripts"]
)  # Old script test endpoint
app.include_router(
    scripts_library.router, prefix="/api", tags=["Script Library"]
)  # New script management
app.include_router(packages.router, prefix="/api/packages", tags=["Packages"])
app.include_router(notifications.router)
app.include_router(activity.router)
app.include_router(config.router, prefix="/api")
app.include_router(mounts.router)  # Mount management API

app.include_router(tokens.router, prefix="/api")
app.include_router(permissions.router, prefix="/api")
app.include_router(managed_machines.router)
app.include_router(agents.router)
app.include_router(
    source_discovery.router,
    prefix="/api/source-discovery",
    tags=["Source Discovery"],
)

app.include_router(v2_router, prefix="/api/v2")  # Borg 2 versioned API


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting Borg Web UI")
    _log_insecure_no_auth_warning()
    _log_proxy_auth_security_warnings()
    from app.database.database import SessionLocal

    # Run database migrations
    from app.database.migrations import run_migrations

    try:
        run_migrations()
    except Exception as e:
        logger.error("Failed to run migrations", error=str(e))
        # Don't fail startup, just log the error

    app_version = get_runtime_app_version()

    # Initialize local licensing state and attempt hidden full access activation
    # only when explicitly enabled for this runtime.
    if settings.enable_startup_license_sync:
        try:
            db = SessionLocal()
            try:
                await sync_licensing_state(db, app_version=app_version)
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to initialize licensing state", error=str(e))
    else:
        logger.info("Startup licensing sync disabled", environment=settings.environment)

    async def licensing_refresh_loop():
        while True:
            try:
                await asyncio.sleep(60 * 60)
                db = SessionLocal()
                try:
                    await sync_licensing_state(db, app_version=app_version)
                finally:
                    db.close()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Background licensing refresh failed", error=str(e))

    global licensing_refresh_task
    licensing_refresh_task = _spawn_background_task(licensing_refresh_loop())

    # Create first user if no users exist
    await create_first_user()

    # Load Redis URL from database and reconfigure cache service
    from app.services.cache_service import archive_cache
    from app.database.models import SystemSettings

    try:
        db = SessionLocal()
        try:
            settings_obj = db.query(SystemSettings).first()
            if settings_obj and settings_obj.redis_url:
                result = archive_cache.reconfigure(
                    redis_url=settings_obj.redis_url,
                    cache_max_size_mb=settings_obj.cache_max_size_mb,
                )
                if result["success"]:
                    logger.info(
                        "Cache service configured from database",
                        backend=result["backend"],
                        connection_info=result.get("connection_info"),
                    )
                else:
                    logger.warning(
                        "Failed to configure Redis from database, using fallback",
                        backend=result["backend"],
                    )
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to configure cache from database", error=str(e))

    # Cache borg system info on startup (prevents repeated borg --version calls)
    from app.core.borg import borg

    try:
        await borg.get_system_info()
        logger.info("Borg system info cached")
    except Exception as e:
        logger.warning("Failed to cache borg system info", error=str(e))

    # Rotate old backup logs on startup (if enabled)
    from app.services.backup_service import backup_service
    from app.database.database import SessionLocal
    from app.database.models import SystemSettings

    try:
        db = SessionLocal()
        try:
            # Check if log cleanup on startup is enabled
            system_settings = db.query(SystemSettings).first()
            if system_settings and system_settings.log_cleanup_on_startup:
                backup_service.rotate_logs(db=db)
                logger.info("Log rotation completed")
            else:
                logger.info("Log cleanup on startup is disabled, skipping")
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to rotate logs", error=str(e))

    # Cleanup orphaned jobs from container restarts
    from app.utils.process_utils import cleanup_orphaned_jobs, cleanup_orphaned_mounts

    try:
        db = SessionLocal()
        cleanup_orphaned_jobs(db)
        db.close()
        logger.info("Orphaned job cleanup completed")
    except Exception as e:
        logger.error("Failed to cleanup orphaned jobs", error=str(e))

    # Cleanup orphaned mounts from container restarts
    try:
        cleanup_orphaned_mounts()
        logger.info("Orphaned mount cleanup completed")
    except Exception as e:
        logger.error("Failed to cleanup orphaned mounts", error=str(e))

    # Note: Package auto-installation now handled by entrypoint.sh startup script
    # This runs asynchronously via /app/app/scripts/startup_packages.py
    # Package installation jobs will start in the background after API is ready

    # Start scheduled backup checker (background task)
    from app.api.schedule import check_scheduled_jobs

    # Track background tasks for cleanup
    app.state.background_tasks = []

    task1 = _spawn_background_task(check_scheduled_jobs())
    app.state.background_tasks.append(task1)
    logger.info("Scheduled job checker started")

    # Start stats refresh scheduler (background task)
    from app.services.stats_refresh_scheduler import stats_refresh_scheduler

    task2 = asyncio.create_task(stats_refresh_scheduler.start())
    app.state.background_tasks.append(task2)
    logger.info("Stats refresh scheduler started")

    # Initialize MQTT service from database settings (using new implementation)
    from app.services.mqtt_service import mqtt_service, build_mqtt_runtime_config
    from app.database.database import SessionLocal
    from app.database.models import SystemSettings

    try:
        db = SessionLocal()
        try:
            settings_obj = db.query(SystemSettings).first()
            if settings_obj:
                mqtt_config = build_mqtt_runtime_config(settings_obj)
                mqtt_service.configure(mqtt_config)
                logger.info(
                    "MQTT service configured from database",
                    enabled=settings_obj.mqtt_enabled,
                    broker_url=settings_obj.mqtt_broker_url,
                )

                # If MQTT is enabled (and beta toggle on), publish ...
                if settings_obj.mqtt_enabled and settings_obj.mqtt_beta_enabled:
                    try:
                        mqtt_service.sync_state_with_db(db, reason="startup")
                        logger.info("Published MQTT DB-derived state on startup")
                    except Exception as sync_error:
                        logger.warning(
                            "Failed to publish MQTT DB-derived state on startup",
                            error=str(sync_error),
                        )
            else:
                logger.info("No system settings found, MQTT service not configured")
        finally:
            db.close()
    except Exception as e:
        logger.warning("Failed to configure MQTT service from database", error=str(e))

    # Start MQTT sync scheduler (background task)
    from app.services.mqtt_sync_scheduler import start_mqtt_sync_scheduler

    task4 = asyncio.create_task(start_mqtt_sync_scheduler())
    app.state.background_tasks.append(task4)
    logger.info("MQTT sync scheduler started")

    logger.info("Borg Web UI started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Shutting down Borg Web UI")

    global licensing_refresh_task
    if licensing_refresh_task:
        licensing_refresh_task.cancel()
        try:
            await licensing_refresh_task
        except asyncio.CancelledError:
            pass
        licensing_refresh_task = None

    # Cancel background tasks
    tasks = getattr(app.state, "background_tasks", [])
    if tasks:
        logger.info(f"Cancelling {len(tasks)} background tasks")
        for task in tasks:
            task.cancel()

        # Wait for tasks to finish cancelling
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("Background tasks cancelled")
        except Exception as e:
            logger.warning("Error waiting for background tasks to cancel", error=str(e))

        # Cleanup MQTT service on shutdown
        from app.services.mqtt_service import mqtt_service

        try:
            mqtt_service.disconnect()
            logger.info("MQTT service disconnected")
        except Exception as e:
            logger.warning("Error disconnecting MQTT service", error=str(e))


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application"""
    if _cached_index_html is not None:
        return HTMLResponse(content=_cached_index_html)
    return HTMLResponse(
        content="<h1>Borg Web UI</h1><p>Frontend not built yet. Please run the build process.</p>"
    )


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def catch_all(full_path: str):
    """Catch-all route for SPA routing - serves index.html for frontend routes"""
    # Don't interfere with API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    # Don't interfere with static assets
    if full_path.startswith("assets/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404, detail="Not Found")

    # Serve static files from root (logo, favicon, announcements manifest, etc.)
    if full_path in ROOT_STATIC_FILES:
        file_path = f"app/static/{full_path}"
        if os.path.exists(file_path):
            return FileResponse(file_path, media_type=ROOT_STATIC_FILES[full_path])
        raise HTTPException(status_code=404, detail="Not Found")

    # Serve index.html for all other routes (frontend routes)
    if _cached_index_html is not None:
        return HTMLResponse(content=_cached_index_html)
    return HTMLResponse(
        content="<h1>Borg Web UI</h1><p>Frontend not built yet. Please run the build process.</p>"
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration and startup scripts"""
    return {"status": "healthy", "service": "borg-web-ui"}


@app.get("/api")
async def api_info():
    """API information endpoint"""
    return {
        "name": "Borg Web UI API",
        "version": get_runtime_app_version(),
        "docs": "/api/docs",
        "status": "running",
    }


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests (except static assets and SSE streams)"""
    # Skip logging for static assets and SSE streams to reduce noise
    skip_paths = ["/assets/", "/static/", "/api/events/stream"]
    should_log = not any(request.url.path.startswith(path) for path in skip_paths)

    if should_log:
        logger.info(
            "request_received",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else None,
        )

    response = await call_next(request)

    if should_log:
        # Log errors and warnings with more detail
        if response.status_code >= 400:
            logger.warning(
                "request_failed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )
        else:
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )

    return response
