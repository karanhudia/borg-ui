from fastapi import APIRouter
import os
import structlog

from app.core.borg import BorgInterface

logger = structlog.get_logger()
router = APIRouter(tags=["system"])

# Initialize Borg interface
borg = BorgInterface()

@router.get("/info")
async def get_system_info():
    """Get system information including app and borg versions"""
    try:
        # Get app version from VERSION file (primary) or environment variable (fallback)
        app_version = "dev"
        try:
            with open('/app/VERSION', 'r') as f:
                app_version = f.read().strip()
                if not app_version:
                    app_version = os.getenv('APP_VERSION', 'dev')
        except FileNotFoundError:
            app_version = os.getenv('APP_VERSION', 'dev')
        except Exception as e:
            logger.warning("Failed to read VERSION file", error=str(e))
            app_version = os.getenv('APP_VERSION', 'dev')

        # Get borg version
        borg_version = None
        try:
            system_info = await borg.get_system_info()
            borg_version = system_info.get('borg_version')
        except Exception as e:
            logger.warning("Failed to get borg version", error=str(e))

        return {
            "app_version": app_version,
            "borg_version": borg_version
        }
    except Exception as e:
        logger.error("Failed to get system info", error=str(e))
        return {
            "app_version": "unknown",
            "borg_version": None
        }
