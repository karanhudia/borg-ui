"""
API endpoints for configuration export/import.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database.database import get_db
from app.services.borgmatic_service import BorgmaticExportService, BorgmaticImportService
from app.dependencies import get_current_user

router = APIRouter(prefix="/config", tags=["config"])


class ExportRequest(BaseModel):
    """Request model for exporting configurations."""
    repository_ids: Optional[List[int]] = None  # None = export all
    include_schedules: bool = True
    include_borg_ui_metadata: bool = True


class ImportRequest(BaseModel):
    """Request model for importing configurations."""
    merge_strategy: str = "skip_duplicates"  # skip_duplicates, replace, rename
    dry_run: bool = False


@router.post("/export/borgmatic")
async def export_borgmatic_config(
    request: ExportRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Export Borg UI configurations to borgmatic YAML format.

    Returns a YAML file download.
    """
    export_service = BorgmaticExportService(db)

    try:
        yaml_content = export_service.export_to_yaml(
            repository_ids=request.repository_ids,
            include_schedules=request.include_schedules,
            include_borg_ui_metadata=request.include_borg_ui_metadata
        )

        if not yaml_content:
            raise HTTPException(status_code=404, detail="No repositories found to export")

        # Return as downloadable YAML file
        filename = "borg-ui-export.yaml"
        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/import/borgmatic")
async def import_borgmatic_config(
    file: UploadFile = File(...),
    merge_strategy: str = Query("skip_duplicates", regex="^(skip_duplicates|replace|rename)$"),
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Import borgmatic YAML configuration into Borg UI.

    Accepts:
    - Standard borgmatic configuration files
    - Borg UI exported configurations (for round-trip)

    merge_strategy options:
    - skip_duplicates: Skip if repository/schedule name exists
    - replace: Replace existing configurations
    - rename: Auto-rename to avoid conflicts
    """
    # Validate file type
    if not file.filename.endswith(('.yaml', '.yml')):
        raise HTTPException(status_code=400, detail="File must be a YAML file (.yaml or .yml)")

    try:
        # Read file content
        content = await file.read()
        yaml_content = content.decode('utf-8')

        # Import configuration
        import_service = BorgmaticImportService(db)
        result = import_service.import_from_yaml(
            yaml_content=yaml_content,
            merge_strategy=merge_strategy,
            dry_run=dry_run
        )

        return result

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/export/repositories")
async def list_exportable_repositories(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get list of repositories available for export.
    """
    from app.database.models import Repository

    repositories = db.query(Repository).all()

    return {
        "repositories": [
            {
                "id": repo.id,
                "name": repo.name,
                "path": repo.path,
                "repository_type": repo.repository_type,
                "has_schedule": bool(repo.source_directories),
                "has_checks": bool(repo.check_interval_days)
            }
            for repo in repositories
        ]
    }
