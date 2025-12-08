"""
Script testing API for testing pre/post backup hooks
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import structlog
from app.api.auth import get_current_user
from app.database.models import User
from app.services.script_executor import execute_script

router = APIRouter()
logger = structlog.get_logger()

class ScriptTestRequest(BaseModel):
    script: str

class ScriptTestResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float

@router.post("/test", response_model=ScriptTestResponse)
async def test_script(
    request: ScriptTestRequest,
    current_user: User = Depends(get_current_user)
):
    """Test run a script using the shared script executor"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if not request.script or request.script.strip() == "":
        raise HTTPException(status_code=400, detail="Script cannot be empty")

    # Use shared script executor with sandboxed environment
    result = await execute_script(
        script=request.script,
        timeout=30.0,
        env={
            'PATH': '/usr/local/bin:/usr/bin:/bin',
            'HOME': '/tmp',
            'TMPDIR': '/tmp',
        },
        context="test"
    )

    logger.info("Script test completed",
               user=current_user.username,
               exit_code=result["exit_code"],
               execution_time=result["execution_time"])

    # Raise HTTP exception if timeout
    if result["exit_code"] == -1 and "timed out" in result["stderr"]:
        raise HTTPException(
            status_code=400,
            detail="Script execution timed out (30 second limit)"
        )

    return ScriptTestResponse(
        success=result["success"],
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        execution_time=result["execution_time"]
    )
