"""
Script testing API for testing pre/post backup hooks
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import structlog
from sqlalchemy.orm import Session
from app.api.auth import get_current_user
from app.database.models import User, Repository, SSHConnection
from app.database.database import get_db
from app.services.script_executor import execute_script
from app.services.template_service import get_system_variables

router = APIRouter()
logger = structlog.get_logger()


class ScriptTestRequest(BaseModel):
    script: str
    repository_id: Optional[int] = (
        None  # When set, inject BORG_UI_ context for that repository
    )


class ScriptTestResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float


@router.post("/test", response_model=ScriptTestResponse)
async def test_script(
    request: ScriptTestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Test run a script using the shared script executor"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"key": "backend.errors.scripts.adminAccessRequired"},
        )

    if not request.script or request.script.strip() == "":
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.scripts.scriptCannotBeEmpty"},
        )

    # Base sandboxed environment
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "TMPDIR": "/tmp",
    }

    # If a repository_id is supplied, inject the same BORG_UI_ variables that a real
    # backup run would provide so scripts that reference them can be tested accurately.
    if request.repository_id:
        repo = (
            db.query(Repository).filter(Repository.id == request.repository_id).first()
        )
        if repo:
            # Resolve source SSH connection (SSHFS pull: on repo; remote SSH push: no job yet,
            # so we check the repo field only — push-mode connection is on the BackupJob at
            # runtime, but for testing we use whatever is available on the repo record)
            source_connection = None
            if repo.source_ssh_connection_id:
                source_connection = (
                    db.query(SSHConnection)
                    .filter(SSHConnection.id == repo.source_ssh_connection_id)
                    .first()
                )

            system_vars = get_system_variables(
                repository_id=repo.id,
                repository_name=repo.name,
                repository_path=repo.path,
                hook_type="pre-backup",
                source_host=source_connection.host if source_connection else None,
                source_port=source_connection.port if source_connection else None,
                source_username=source_connection.username
                if source_connection
                else None,
            )
            env.update(system_vars)
            logger.info(
                "Script test: injected repository context",
                repository_id=repo.id,
                has_source_connection=source_connection is not None,
            )

    # Use shared script executor with sandboxed environment
    result = await execute_script(
        script=request.script, timeout=30.0, env=env, context="test"
    )

    logger.info(
        "Script test completed",
        user=current_user.username,
        exit_code=result["exit_code"],
        execution_time=result["execution_time"],
    )

    # Raise HTTP exception if timeout
    if result["exit_code"] == -1 and "timed out" in result["stderr"]:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.scripts.scriptExecutionTimedOut"},
        )

    return ScriptTestResponse(
        success=result["success"],
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        execution_time=result["execution_time"],
    )
