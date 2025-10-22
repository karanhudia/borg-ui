from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import structlog
import os
from dotenv import load_dotenv

from app.api import auth, dashboard, backup, archives, restore, schedule, settings as settings_api, events, repositories, ssh_keys
from app.database.database import engine
from app.database.models import Base
from app.core.security import create_first_user

# Load environment variables
load_dotenv()

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
        structlog.dev.ConsoleRenderer() if log_level == "DEBUG" else structlog.processors.JSONRenderer()
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
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Configure CORS
from app.config import settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
app.mount("/assets", StaticFiles(directory="app/static/assets"), name="assets")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include API routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(backup.router, prefix="/api/backup", tags=["Backup"])
app.include_router(archives.router, prefix="/api/archives", tags=["Archives"])
app.include_router(restore.router, prefix="/api/restore", tags=["Restore"])
app.include_router(schedule.router, prefix="/api/schedule", tags=["Schedule"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["Settings"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(repositories.router, prefix="/api/repositories", tags=["Repositories"])
app.include_router(ssh_keys.router, prefix="/api/ssh-keys", tags=["SSH Keys"])

@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting Borg Web UI")

    # Create first user if no users exist
    await create_first_user()

    logger.info("Borg Web UI started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("Shutting down Borg Web UI")

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application"""
    try:
        with open("app/static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Borg Web UI</h1><p>Frontend not built yet. Please run the build process.</p>")

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def catch_all(full_path: str):
    """Catch-all route for SPA routing - serves index.html for frontend routes"""
    # Don't interfere with API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    # Don't interfere with static assets
    if full_path.startswith("assets/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404, detail="Not Found")

    # Serve index.html for all other routes (frontend routes)
    try:
        with open("app/static/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Borg Web UI</h1><p>Frontend not built yet. Please run the build process.</p>")

@app.get("/api")
async def api_info():
    """API information endpoint"""
    return {
        "name": "Borg Web UI API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "status": "running"
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
            client_ip=request.client.host if request.client else None
        )

    response = await call_next(request)

    if should_log:
        # Log errors and warnings with more detail
        if response.status_code >= 400:
            logger.warning(
                "request_failed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code
            )
        else:
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code
            )

    return response 