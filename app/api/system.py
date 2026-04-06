from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import structlog
from typing import Optional

from app.core.borg import BorgInterface
from app.core.borg2 import borg2
from app.core.features import get_current_plan, FEATURES
from app.core.security import get_current_admin_user
from app.config import get_runtime_app_version
from app.database.database import get_db
from app.services.licensing_service import (
    activate_paid_license,
    deactivate_paid_license,
    get_entitlement_summary,
    get_feature_access,
    import_offline_entitlement,
    refresh_entitlement,
)

logger = structlog.get_logger()
router = APIRouter(tags=["system"])

# Initialize Borg interface
borg = BorgInterface()


class LicenseActivationRequest(BaseModel):
    license_key: str = Field(min_length=1)


class OfflineEntitlementImportRequest(BaseModel):
    payload: dict
    signature: str = Field(min_length=1)
    key_id: Optional[str] = None


def _licensing_http_error(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


@router.get("/info")
async def get_system_info(db: Session = Depends(get_db)):
    """Get system information including app and borg versions"""
    try:
        # Get app version from VERSION file (primary) or environment variable (fallback)
        app_version = get_runtime_app_version()

        # Get borg version
        borg_version = None
        try:
            system_info = await borg.get_system_info()
            borg_version = system_info.get('borg_version')
        except Exception as e:
            logger.warning("Failed to get borg version", error=str(e))

        # Get borg2 version
        borg2_version = None
        try:
            borg2_info = await borg2.get_system_info()
            if borg2_info.get('success'):
                borg2_version = borg2_info.get('borg_version')
        except Exception as e:
            logger.warning("Failed to get borg2 version", error=str(e))

        plan = get_current_plan(db)
        entitlement = get_entitlement_summary(db)

        return {
            "app_version": app_version,
            "borg_version": borg_version,
            "borg2_version": borg2_version,
            "plan": plan.value,
            "features": {k: v.value for k, v in FEATURES.items()},
            "feature_access": get_feature_access(db),
            "entitlement": entitlement,
        }
    except Exception as e:
        logger.error("Failed to get system info", error=str(e))
        return {
            "app_version": "unknown",
            "borg_version": None,
            "borg2_version": None,
            "plan": "community",
            "features": {},
            "feature_access": {},
            "entitlement": {
                "status": "none",
                "access_level": "community",
                "is_full_access": False,
                "full_access_consumed": False,
                "expires_at": None,
                "starts_at": None,
                "refresh_after": None,
                "instance_id": None,
                "entitlement_id": None,
                "license_id": None,
                "customer_id": None,
                "ui_state": "community",
                "last_refresh_at": None,
                "last_refresh_error": None,
            },
        }


@router.post("/licensing/refresh")
async def refresh_system_entitlement(
    db: Session = Depends(get_db),
    _: object = Depends(get_current_admin_user),
):
    try:
        result = await refresh_entitlement(db, app_version=get_runtime_app_version())
        return result
    except Exception as e:
        logger.warning("Failed to refresh entitlement", error=str(e))
        raise _licensing_http_error("entitlement_refresh_failed", str(e))


@router.post("/licensing/activate")
async def activate_system_license(
    request: LicenseActivationRequest,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_admin_user),
):
    try:
        return await activate_paid_license(
            db,
            license_key=request.license_key,
            app_version=get_runtime_app_version(),
        )
    except Exception as e:
        logger.warning("Failed to activate paid license", error=str(e))
        raise _licensing_http_error("license_activation_failed", str(e))


@router.post("/licensing/deactivate")
async def deactivate_system_license(
    db: Session = Depends(get_db),
    _: object = Depends(get_current_admin_user),
):
    try:
        return await deactivate_paid_license(db)
    except Exception as e:
        logger.warning("Failed to deactivate paid license", error=str(e))
        raise _licensing_http_error("license_deactivation_failed", str(e))


@router.post("/licensing/import")
async def import_system_entitlement(
    request: OfflineEntitlementImportRequest,
    db: Session = Depends(get_db),
    _: object = Depends(get_current_admin_user),
):
    try:
        document = request.model_dump(exclude_none=True)
        return import_offline_entitlement(db, document)
    except Exception as e:
        logger.warning("Failed to import entitlement", error=str(e))
        raise _licensing_http_error("entitlement_import_failed", str(e))
