"""Borg 2 versioned API — mounted at /api/v2/ in main.py.

All routes here are only reached for repositories with borg_version == 2.
Add new v2 sub-routers here; main.py stays unaware of individual modules.
"""

from fastapi import APIRouter
from app.api.v2 import repositories, archives, backups

router = APIRouter()
router.include_router(
    repositories.router, prefix="/repositories", tags=["Repositories v2"]
)
router.include_router(archives.router, prefix="/archives", tags=["Archives v2"])
router.include_router(backups.router, prefix="/backup", tags=["Backup v2"])
