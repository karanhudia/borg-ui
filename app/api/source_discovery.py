from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user, require_any_role
from app.database.models import User
from app.services.source_discovery import SourceDiscoveryResult, scan_database_sources

router = APIRouter(tags=["source-discovery"])


@router.get("/databases", response_model=SourceDiscoveryResult)
async def scan_databases(
    current_user: User = Depends(get_current_user),
) -> SourceDiscoveryResult:
    require_any_role(current_user, "admin", "operator")
    return scan_database_sources()
