"""
Script testing API for testing pre/post backup hooks
"""
import asyncio
import tempfile
import os
import time
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import structlog
from app.api.auth import get_current_user
from app.database.models import User

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
    """Test run a script in a sandboxed environment"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if not request.script or request.script.strip() == "":
        raise HTTPException(status_code=400, detail="Script cannot be empty")

    # Create a temporary file for the script
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(request.script)
            script_path = f.name

        # Make script executable
        os.chmod(script_path, 0o700)

        # Run the script with timeout and capture output
        start_time = time.time()

        try:
            process = await asyncio.create_subprocess_exec(
                '/bin/bash',
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Add some basic sandboxing environment variables
                env={
                    'PATH': '/usr/local/bin:/usr/bin:/bin',
                    'HOME': '/tmp',
                    'TMPDIR': '/tmp',
                }
            )

            # Wait for completion with timeout (30 seconds)
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=30.0
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                # Kill the process if it times out
                process.kill()
                await process.wait()
                raise HTTPException(
                    status_code=400,
                    detail="Script execution timed out (30 second limit)"
                )

            execution_time = time.time() - start_time

            # Decode output
            stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""

            logger.info("Script test completed",
                       user=current_user.username,
                       exit_code=exit_code,
                       execution_time=execution_time)

            return ScriptTestResponse(
                success=exit_code == 0 and not stderr_str,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                execution_time=execution_time
            )

        except Exception as e:
            logger.error("Script test execution failed", error=str(e))
            raise HTTPException(status_code=500, detail=f"Script execution failed: {str(e)}")

    finally:
        # Clean up the temporary file
        try:
            if os.path.exists(script_path):
                os.unlink(script_path)
        except Exception as e:
            logger.warning("Failed to delete temporary script file", error=str(e))
