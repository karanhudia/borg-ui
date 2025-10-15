"""
System information API endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import subprocess
import os
import structlog

logger = structlog.get_logger()
router = APIRouter()


class SystemInfo(BaseModel):
    """System information model"""
    app_version: str
    borg_version: Optional[str]
    borgmatic_version: Optional[str]


def get_command_version(command: str) -> Optional[str]:
    """Get version of a command line tool"""
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Parse version from output (usually first line)
            output = result.stdout.strip() or result.stderr.strip()
            return output.split('\n')[0].strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"Failed to get {command} version", error=str(e))
        return None


@router.get("/info", response_model=SystemInfo)
async def get_system_info():
    """Get system information including versions"""
    try:
        # Get app version from environment variable (set during Docker build)
        app_version = os.getenv("APP_VERSION", "dev")

        # Get Borg version
        borg_version = get_command_version("borg")

        # Get Borgmatic version
        borgmatic_version = get_command_version("borgmatic")

        return SystemInfo(
            app_version=app_version,
            borg_version=borg_version,
            borgmatic_version=borgmatic_version
        )
    except Exception as e:
        logger.error("Failed to get system info", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get system info: {str(e)}")
