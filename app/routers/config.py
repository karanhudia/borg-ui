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
from app.core.security import get_current_user

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

    Returns a ZIP file containing separate config files for each repository.
    """
    export_service = BorgmaticExportService(db)

    try:
        # For multiple repos, always get metadata first to extract repo names for filenames
        # We'll remove it later if not requested
        need_metadata_for_filenames = request.repository_ids is None or len(request.repository_ids or []) != 1

        configs = export_service.export_all_repositories(
            repository_ids=request.repository_ids,
            include_schedules=request.include_schedules,
            include_borg_ui_metadata=True  # Always include temporarily to get repo names
        )

        if not configs:
            raise HTTPException(status_code=404, detail="No repositories found to export")

        # If only one repository, return single YAML file
        if len(configs) == 1:
            import yaml
            config = configs[0].copy()

            # Remove metadata if not requested
            if not request.include_borg_ui_metadata:
                config.pop('borg_ui_metadata', None)

            yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False)

            filename = "borgmatic-config.yaml"
            return Response(
                content=yaml_content,
                media_type="application/x-yaml",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )

        # Multiple repositories: create ZIP with separate config files
        import io
        import zipfile
        import yaml

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for i, config in enumerate(configs):
                # Get repository name from metadata or generate one
                repo_name = config.get('borg_ui_metadata', {}).get('repository', {}).get('name', f'repo-{i+1}')
                # Sanitize filename
                safe_name = "".join(c for c in repo_name if c.isalnum() or c in ('-', '_')).lower()

                # Remove metadata from individual files if not requested
                config_copy = config.copy()
                if not request.include_borg_ui_metadata:
                    config_copy.pop('borg_ui_metadata', None)

                yaml_content = yaml.dump(config_copy, default_flow_style=False, sort_keys=False)
                zip_file.writestr(f"{safe_name}.yaml", yaml_content)

        zip_buffer.seek(0)
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=borgmatic-configs.zip"
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
    - Single YAML files (.yaml, .yml)
    - ZIP files containing multiple YAML configs (.zip)
    - Standard borgmatic configuration files
    - Borg UI exported configurations (for round-trip)

    merge_strategy options:
    - skip_duplicates: Skip if repository/schedule name exists
    - replace: Replace existing configurations
    - rename: Auto-rename to avoid conflicts
    """
    # Validate file type
    if not file.filename.endswith(('.yaml', '.yml', '.zip')):
        raise HTTPException(status_code=400, detail="File must be a YAML (.yaml, .yml) or ZIP file")

    try:
        content = await file.read()
        import_service = BorgmaticImportService(db)

        # Handle ZIP files with multiple configs
        if file.filename.endswith('.zip'):
            import io
            import zipfile
            import yaml

            combined_result = {
                'success': True,
                'repositories_created': 0,
                'repositories_updated': 0,
                'schedules_created': 0,
                'schedules_updated': 0,
                'warnings': [],
                'errors': []
            }

            with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
                yaml_files = [f for f in zip_file.namelist() if f.endswith(('.yaml', '.yml'))]

                if not yaml_files:
                    raise HTTPException(status_code=400, detail="ZIP file contains no YAML files")

                for yaml_file in yaml_files:
                    try:
                        yaml_content = zip_file.read(yaml_file).decode('utf-8')
                        result = import_service.import_from_yaml(
                            yaml_content=yaml_content,
                            merge_strategy=merge_strategy,
                            dry_run=dry_run
                        )

                        # Aggregate results
                        combined_result['repositories_created'] += result.get('repositories_created', 0)
                        combined_result['repositories_updated'] += result.get('repositories_updated', 0)
                        combined_result['schedules_created'] += result.get('schedules_created', 0)
                        combined_result['schedules_updated'] += result.get('schedules_updated', 0)
                        combined_result['warnings'].extend(result.get('warnings', []))

                        if not result.get('success'):
                            combined_result['errors'].append(f"{yaml_file}: {result.get('error', 'Unknown error')}")

                    except Exception as e:
                        combined_result['errors'].append(f"{yaml_file}: {str(e)}")

            # Update repository stats for newly created repositories (non-blocking - don't fail import)
            if not dry_run and combined_result['repositories_created'] > 0:
                from app.database.models import Repository
                from app.api.repositories import update_repository_stats
                import structlog
                logger = structlog.get_logger()

                # Get the newly created repositories
                repositories = db.query(Repository).order_by(Repository.id.desc()).limit(combined_result['repositories_created']).all()
                for repo in repositories:
                    try:
                        await update_repository_stats(repo, db)
                    except Exception as e:
                        # Log but don't fail the import - stats can be updated later
                        logger.warning("Failed to update repository stats after import",
                                     repository=repo.name,
                                     error=str(e))

            return combined_result

        # Handle single YAML file
        else:
            yaml_content = content.decode('utf-8')
            result = import_service.import_from_yaml(
                yaml_content=yaml_content,
                merge_strategy=merge_strategy,
                dry_run=dry_run
            )

            # Update repository stats for newly created repositories (non-blocking - don't fail import)
            if not dry_run and result.get('repositories_created', 0) > 0:
                from app.database.models import Repository
                from app.api.repositories import update_repository_stats
                import structlog
                logger = structlog.get_logger()

                # Get the newly created repository (last one added to DB)
                repositories = db.query(Repository).order_by(Repository.id.desc()).limit(result['repositories_created']).all()
                for repo in repositories:
                    try:
                        await update_repository_stats(repo, db)
                    except Exception as e:
                        # Log but don't fail the import - stats can be updated later
                        logger.warning("Failed to update repository stats after import",
                                     repository=repo.name,
                                     error=str(e))

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
