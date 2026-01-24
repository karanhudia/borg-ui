"""
API endpoints for script library management (Phase 2)

Provides CRUD operations for scripts, script assignment to repositories,
and script execution history.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
import os
import hashlib

from app.database.database import get_db
from app.database.models import Script, RepositoryScript, ScriptExecution, Repository, User
from app.core.security import get_current_user
from app.config import settings
from app.services.script_executor import execute_script
import structlog

logger = structlog.get_logger()
router = APIRouter()

# Pydantic schemas
class ScriptCreate(BaseModel):
    name: str
    description: Optional[str] = None
    content: str  # The actual script content
    timeout: int = 300
    run_on: str = "always"  # 'success', 'failure', 'always', 'warning'
    category: str = "custom"  # 'custom', 'template'

class ScriptUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    timeout: Optional[int] = None
    run_on: Optional[str] = None

class ScriptResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    file_path: str
    category: str
    timeout: int
    run_on: str
    usage_count: int
    is_template: bool
    created_at: datetime
    updated_at: datetime

class ScriptDetailResponse(ScriptResponse):
    content: str  # Include script content in detail view
    repositories: List[dict]  # List of repos using this script
    recent_executions: List[dict]  # Last 5 executions

class RepositoryScriptAssignment(BaseModel):
    script_id: int
    hook_type: str  # 'pre-backup' or 'post-backup'
    execution_order: int = 1
    enabled: bool = True
    custom_timeout: Optional[int] = None
    custom_run_on: Optional[str] = None
    continue_on_error: Optional[bool] = True

# Helper functions
def ensure_scripts_directory():
    """Ensure /data/scripts/library directory exists"""
    scripts_dir = Path(settings.data_dir) / "scripts" / "library"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    return scripts_dir

def generate_script_filename(name: str, script_id: Optional[int] = None) -> str:
    """Generate a safe filename from script name"""
    # Create safe filename from name
    safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name.lower())
    safe_name = safe_name[:50]  # Limit length

    # Add hash for uniqueness if ID provided
    if script_id:
        name_hash = hashlib.md5(f"{script_id}_{name}".encode()).hexdigest()[:8]
        return f"{safe_name}_{name_hash}.sh"
    else:
        # For new scripts, add timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{safe_name}_{timestamp}.sh"

def write_script_file(file_path: Path, content: str) -> None:
    """Write script content to file with proper permissions"""
    file_path.write_text(content)
    file_path.chmod(0o755)  # Make executable

def read_script_file(file_path: Path) -> str:
    """Read script content from file"""
    full_path = Path(settings.data_dir) / "scripts" / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Script file not found: {file_path}")
    return full_path.read_text()

# API Endpoints

@router.get("/scripts", response_model=List[ScriptResponse])
async def list_scripts(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all scripts

    Query parameters:
    - category: Filter by category ('custom', 'template')
    - search: Search in name and description
    """
    query = db.query(Script)

    if category:
        query = query.filter(Script.category == category)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Script.name.like(search_pattern)) |
            (Script.description.like(search_pattern))
        )

    scripts = query.order_by(Script.created_at.desc()).all()

    return [
        ScriptResponse(
            id=script.id,
            name=script.name,
            description=script.description,
            file_path=script.file_path,
            category=script.category,
            timeout=script.timeout,
            run_on=script.run_on,
            usage_count=script.usage_count,
            is_template=script.is_template,
            created_at=script.created_at,
            updated_at=script.updated_at
        )
        for script in scripts
    ]

@router.get("/scripts/{script_id}", response_model=ScriptDetailResponse)
async def get_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get script details including content and usage"""
    script = db.query(Script).filter(Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    # Read script content from file
    try:
        content = read_script_file(script.file_path)
    except Exception as e:
        logger.error("Failed to read script file", script_id=script_id, error=str(e))
        content = f"# Error reading script file: {str(e)}"

    # Get repositories using this script
    repo_scripts = db.query(RepositoryScript).filter(
        RepositoryScript.script_id == script_id
    ).options(joinedload(RepositoryScript.repository)).all()

    # Filter out orphaned associations (where repository was deleted)
    # and clean them up from the database
    valid_repo_scripts = []
    orphaned_ids = []
    for rs in repo_scripts:
        if rs.repository is not None:
            valid_repo_scripts.append(rs)
        else:
            orphaned_ids.append(rs.id)

    # Clean up orphaned associations
    if orphaned_ids:
        db.query(RepositoryScript).filter(RepositoryScript.id.in_(orphaned_ids)).delete(synchronize_session=False)
        db.commit()
        logger.info("Cleaned up orphaned script associations", script_id=script_id, count=len(orphaned_ids))

    repositories = [
        {
            "id": rs.repository_id,
            "name": rs.repository.name,
            "hook_type": rs.hook_type,
            "enabled": rs.enabled
        }
        for rs in valid_repo_scripts
    ]

    # Get recent executions
    executions = db.query(ScriptExecution).filter(
        ScriptExecution.script_id == script_id
    ).order_by(ScriptExecution.started_at.desc()).limit(5).all()

    recent_executions = [
        {
            "id": ex.id,
            "repository_id": ex.repository_id,
            "status": ex.status,
            "started_at": ex.started_at.isoformat() if ex.started_at else None,
            "exit_code": ex.exit_code,
            "execution_time": ex.execution_time
        }
        for ex in executions
    ]

    return ScriptDetailResponse(
        id=script.id,
        name=script.name,
        description=script.description,
        file_path=script.file_path,
        category=script.category,
        timeout=script.timeout,
        run_on=script.run_on,
        usage_count=script.usage_count,
        is_template=script.is_template,
        created_at=script.created_at,
        updated_at=script.updated_at,
        content=content,
        repositories=repositories,
        recent_executions=recent_executions
    )

@router.post("/scripts", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED)
async def create_script(
    script_data: ScriptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new script"""
    # Check if name already exists
    existing = db.query(Script).filter(Script.name == script_data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Script with name '{script_data.name}' already exists")

    # Validate run_on value
    valid_run_on = ['success', 'failure', 'always', 'warning']
    if script_data.run_on not in valid_run_on:
        raise HTTPException(status_code=400, detail=f"run_on must be one of: {', '.join(valid_run_on)}")

    # Ensure scripts directory exists
    scripts_dir = ensure_scripts_directory()

    # Generate filename
    filename = generate_script_filename(script_data.name)
    file_path = scripts_dir / filename
    relative_path = f"library/{filename}"

    # Write script to file
    try:
        write_script_file(file_path, script_data.content)
        logger.info("Script file created", filename=filename, path=str(file_path))
    except Exception as e:
        logger.error("Failed to write script file", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to write script file: {str(e)}")

    # Create database record
    script = Script(
        name=script_data.name,
        description=script_data.description,
        file_path=relative_path,
        category=script_data.category,
        timeout=script_data.timeout,
        run_on=script_data.run_on,
        created_by_user_id=current_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(script)
    db.commit()
    db.refresh(script)

    logger.info("Script created", script_id=script.id, name=script.name, user_id=current_user.id)

    return ScriptResponse(
        id=script.id,
        name=script.name,
        description=script.description,
        file_path=script.file_path,
        category=script.category,
        timeout=script.timeout,
        run_on=script.run_on,
        usage_count=0,
        is_template=False,
        created_at=script.created_at,
        updated_at=script.updated_at
    )

@router.put("/scripts/{script_id}", response_model=ScriptResponse)
async def update_script(
    script_id: int,
    script_data: ScriptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an existing script"""
    script = db.query(Script).filter(Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    # Don't allow editing templates
    if script.is_template:
        raise HTTPException(status_code=400, detail="Cannot edit template scripts. Create a copy instead.")

    # Update name if provided
    if script_data.name is not None:
        # Check for duplicate name
        existing = db.query(Script).filter(
            Script.name == script_data.name,
            Script.id != script_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Script with name '{script_data.name}' already exists")
        script.name = script_data.name

    # Update other fields
    if script_data.description is not None:
        script.description = script_data.description

    if script_data.timeout is not None:
        script.timeout = script_data.timeout

    if script_data.run_on is not None:
        valid_run_on = ['success', 'failure', 'always', 'warning']
        if script_data.run_on not in valid_run_on:
            raise HTTPException(status_code=400, detail=f"run_on must be one of: {', '.join(valid_run_on)}")
        script.run_on = script_data.run_on

    # Update content if provided
    if script_data.content is not None:
        file_path = Path(settings.data_dir) / "scripts" / script.file_path
        try:
            write_script_file(file_path, script_data.content)
            logger.info("Script file updated", script_id=script_id, path=str(file_path))
        except Exception as e:
            logger.error("Failed to update script file", script_id=script_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to update script file: {str(e)}")

    script.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(script)

    logger.info("Script updated", script_id=script.id, name=script.name, user_id=current_user.id)

    return ScriptResponse(
        id=script.id,
        name=script.name,
        description=script.description,
        file_path=script.file_path,
        category=script.category,
        timeout=script.timeout,
        run_on=script.run_on,
        usage_count=script.usage_count,
        is_template=script.is_template,
        created_at=script.created_at,
        updated_at=script.updated_at
    )

@router.delete("/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(
    script_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a script"""
    script = db.query(Script).filter(Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    # Don't allow deleting templates
    if script.is_template:
        raise HTTPException(status_code=400, detail="Cannot delete template scripts")

    # Check if script is in use (only count associations with existing repositories)
    repo_scripts = db.query(RepositoryScript).filter(
        RepositoryScript.script_id == script_id
    ).options(joinedload(RepositoryScript.repository)).all()

    # Filter out orphaned associations and clean them up
    valid_repo_scripts = []
    orphaned_ids = []
    for rs in repo_scripts:
        if rs.repository is not None:
            valid_repo_scripts.append(rs)
        else:
            orphaned_ids.append(rs.id)

    # Clean up orphaned associations
    if orphaned_ids:
        db.query(RepositoryScript).filter(RepositoryScript.id.in_(orphaned_ids)).delete(synchronize_session=False)
        db.commit()
        logger.info("Cleaned up orphaned script associations during delete check", script_id=script_id, count=len(orphaned_ids))

    if len(valid_repo_scripts) > 0:
        repo_names = [rs.repository.name for rs in valid_repo_scripts]

        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete script: it is used by {len(valid_repo_scripts)} repository(ies): {', '.join(repo_names)}"
        )

    # Delete script file
    file_path = Path(settings.data_dir) / "scripts" / script.file_path
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info("Script file deleted", script_id=script_id, path=str(file_path))
    except Exception as e:
        logger.warning("Failed to delete script file", script_id=script_id, error=str(e))
        # Continue with database deletion even if file deletion fails

    # Delete from database (cascade will handle repository_scripts and script_executions)
    db.delete(script)
    db.commit()

    logger.info("Script deleted", script_id=script_id, user_id=current_user.id)

@router.post("/scripts/{script_id}/test")
async def test_script(
    script_id: int,
    timeout: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test execute a script (doesn't save execution to history)"""
    script = db.query(Script).filter(Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    # Read script content
    try:
        content = read_script_file(script.file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read script file: {str(e)}")

    # Execute script
    test_timeout = timeout or script.timeout
    try:
        result = await execute_script(
            script=content,
            timeout=float(test_timeout),
            context=f"test:{script.name}"
        )

        return {
            "success": result["success"],
            "exit_code": result["exit_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "execution_time": result["execution_time"]
        }
    except Exception as e:
        logger.error("Script test execution failed", script_id=script_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Script execution failed: {str(e)}")

# Repository Script Assignment Endpoints

@router.get("/repositories/{repository_id}/scripts")
async def get_repository_scripts(
    repository_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all scripts assigned to a repository"""
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Get pre-backup scripts
    pre_scripts = db.query(RepositoryScript).filter(
        RepositoryScript.repository_id == repository_id,
        RepositoryScript.hook_type == "pre-backup"
    ).options(joinedload(RepositoryScript.script)).order_by(RepositoryScript.execution_order).all()

    # Get post-backup scripts
    post_scripts = db.query(RepositoryScript).filter(
        RepositoryScript.repository_id == repository_id,
        RepositoryScript.hook_type == "post-backup"
    ).options(joinedload(RepositoryScript.script)).order_by(RepositoryScript.execution_order).all()

    def format_script(rs):
        return {
            "id": rs.id,
            "script_id": rs.script_id,
            "script_name": rs.script.name,
            "script_description": rs.script.description,
            "execution_order": rs.execution_order,
            "enabled": rs.enabled,
            "custom_timeout": rs.custom_timeout,
            "custom_run_on": rs.custom_run_on,
            "continue_on_error": rs.continue_on_error,
            "default_timeout": rs.script.timeout,
            "default_run_on": rs.script.run_on
        }

    return {
        "pre_backup": [format_script(rs) for rs in pre_scripts],
        "post_backup": [format_script(rs) for rs in post_scripts]
    }

@router.post("/repositories/{repository_id}/scripts")
async def assign_script_to_repository(
    repository_id: int,
    assignment: RepositoryScriptAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Assign a script to a repository"""
    # Validate repository exists
    repository = db.query(Repository).filter(Repository.id == repository_id).first()
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Validate script exists
    script = db.query(Script).filter(Script.id == assignment.script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    # Validate hook_type
    if assignment.hook_type not in ["pre-backup", "post-backup"]:
        raise HTTPException(status_code=400, detail="hook_type must be 'pre-backup' or 'post-backup'")

    # Check if already assigned
    existing = db.query(RepositoryScript).filter(
        RepositoryScript.repository_id == repository_id,
        RepositoryScript.script_id == assignment.script_id,
        RepositoryScript.hook_type == assignment.hook_type
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Script '{script.name}' is already assigned to this repository as {assignment.hook_type}"
        )

    # Create assignment
    repo_script = RepositoryScript(
        repository_id=repository_id,
        script_id=assignment.script_id,
        hook_type=assignment.hook_type,
        execution_order=assignment.execution_order,
        enabled=assignment.enabled,
        custom_timeout=assignment.custom_timeout,
        custom_run_on=assignment.custom_run_on,
        continue_on_error=assignment.continue_on_error if assignment.continue_on_error is not None else True,
        created_at=datetime.utcnow()
    )

    db.add(repo_script)

    # Update script usage count (count unique repositories, not total associations)
    script.usage_count = db.query(RepositoryScript.repository_id).filter(
        RepositoryScript.script_id == assignment.script_id
    ).distinct().count()
    script.last_used_at = datetime.utcnow()

    db.commit()
    db.refresh(repo_script)

    logger.info("Script assigned to repository",
                script_id=assignment.script_id,
                repository_id=repository_id,
                hook_type=assignment.hook_type)

    return {"success": True, "id": repo_script.id}

@router.put("/repositories/{repository_id}/scripts/{repo_script_id}")
async def update_repository_script_assignment(
    repository_id: int,
    repo_script_id: int,
    execution_order: Optional[float] = None,
    enabled: Optional[bool] = None,
    custom_timeout: Optional[int] = None,
    custom_run_on: Optional[str] = None,
    continue_on_error: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update script assignment settings"""
    repo_script = db.query(RepositoryScript).filter(
        RepositoryScript.id == repo_script_id,
        RepositoryScript.repository_id == repository_id
    ).first()

    if not repo_script:
        raise HTTPException(status_code=404, detail="Script assignment not found")

    if execution_order is not None:
        repo_script.execution_order = execution_order

    if enabled is not None:
        repo_script.enabled = enabled

    if custom_timeout is not None:
        repo_script.custom_timeout = custom_timeout

    if custom_run_on is not None:
        valid_run_on = ['success', 'failure', 'always', 'warning']
        if custom_run_on not in valid_run_on:
            raise HTTPException(status_code=400, detail=f"run_on must be one of: {', '.join(valid_run_on)}")
        repo_script.custom_run_on = custom_run_on

    if continue_on_error is not None:
        repo_script.continue_on_error = continue_on_error

    db.commit()

    logger.info("Repository script assignment updated",
                repo_script_id=repo_script_id,
                repository_id=repository_id)

    return {"success": True}

@router.delete("/repositories/{repository_id}/scripts/{repo_script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_script_from_repository(
    repository_id: int,
    repo_script_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove a script assignment from a repository"""
    repo_script = db.query(RepositoryScript).filter(
        RepositoryScript.id == repo_script_id,
        RepositoryScript.repository_id == repository_id
    ).first()

    if not repo_script:
        raise HTTPException(status_code=404, detail="Script assignment not found")

    script_id = repo_script.script_id

    # Delete assignment
    db.delete(repo_script)

    # Update script usage count (count unique repositories, not total associations)
    script = db.query(Script).filter(Script.id == script_id).first()
    if script:
        script.usage_count = db.query(RepositoryScript.repository_id).filter(
            RepositoryScript.script_id == script_id
        ).distinct().count()

    db.commit()

    logger.info("Script removed from repository",
                repo_script_id=repo_script_id,
                repository_id=repository_id,
                script_id=script_id)


@router.post("/scripts/cleanup-orphans")
async def cleanup_orphaned_script_associations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Clean up orphaned script associations (admin only)

    This removes RepositoryScript entries that reference deleted repositories.
    Useful for fixing database inconsistencies."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Find all script associations
    all_repo_scripts = db.query(RepositoryScript).options(
        joinedload(RepositoryScript.repository)
    ).all()

    # Filter out orphaned associations
    orphaned_ids = []
    for rs in all_repo_scripts:
        if rs.repository is None:
            orphaned_ids.append(rs.id)

    # Delete orphaned associations
    if orphaned_ids:
        db.query(RepositoryScript).filter(RepositoryScript.id.in_(orphaned_ids)).delete(synchronize_session=False)
        db.commit()
        logger.info("Cleaned up orphaned script associations", count=len(orphaned_ids), user=current_user.username)

        return {
            "success": True,
            "cleaned_up": len(orphaned_ids),
            "message": f"Cleaned up {len(orphaned_ids)} orphaned script association(s)"
        }

    return {
        "success": True,
        "cleaned_up": 0,
        "message": "No orphaned script associations found"
    }
