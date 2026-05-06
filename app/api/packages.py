"""
Package management API for installing system packages
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import structlog
from sqlalchemy.orm import Session
from app.core.authorization import authorize_request
from app.core.security import get_current_user
from app.database.models import User, InstalledPackage, PackageInstallJob
from app.database.database import get_db
from app.services.package_service import package_service
from app.utils.datetime_utils import serialize_datetime

router = APIRouter(dependencies=[Depends(authorize_request)])
logger = structlog.get_logger()


class PackageCreate(BaseModel):
    name: str
    install_command: str
    description: Optional[str] = None


class PackageResponse(BaseModel):
    id: int
    name: str
    install_command: str
    description: Optional[str]
    status: str
    install_log: Optional[str]
    installed_at: Optional[datetime]
    last_check: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: serialize_datetime(v)}


class PackageInstallResponse(BaseModel):
    success: bool
    message: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None


@router.get("/", response_model=List[PackageResponse])
async def list_packages(db: Session = Depends(get_db)):
    """List all installed packages"""
    packages = db.query(InstalledPackage).order_by(InstalledPackage.name).all()
    return packages


@router.post("/", response_model=PackageResponse)
async def create_package(
    package: PackageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a new package to install"""
    # Check if package already exists
    existing = (
        db.query(InstalledPackage).filter(InstalledPackage.name == package.name).first()
    )
    if existing:
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.packages.packageAlreadyExists",
                "params": {"name": package.name},
            },
        )

    # Create package record
    new_package = InstalledPackage(
        name=package.name,
        install_command=package.install_command,
        description=package.description,
        status="pending",
    )
    db.add(new_package)
    db.commit()
    db.refresh(new_package)

    logger.info("Package added", package=package.name, user=current_user.username)
    return new_package


@router.post("/{package_id}/install")
async def install_package(package_id: int, db: Session = Depends(get_db)):
    """Start package installation job (non-blocking)"""
    package = (
        db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
    )
    if not package:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.packages.packageNotFound"}
        )

    # Check if there's already a running job for this package
    existing_job = (
        db.query(PackageInstallJob)
        .filter(
            PackageInstallJob.package_id == package_id,
            PackageInstallJob.status.in_(["pending", "installing"]),
        )
        .first()
    )

    if existing_job:
        return {
            "job_id": existing_job.id,
            "message": "backend.success.packages.installationInProgress",
            "status": existing_job.status,
        }

    try:
        # Start async installation job
        job = await package_service.start_install_job(db, package_id)

        logger.info(
            "Package installation job started", package=package.name, job_id=job.id
        )

        return {
            "job_id": job.id,
            "message": "backend.success.packages.installationStarted",
            "status": job.status,
        }

    except Exception as e:
        logger.error(
            "Failed to start package installation", package=package.name, error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.packages.failedStartInstallation",
                "params": {"error": str(e)},
            },
        )


@router.put("/{package_id}", response_model=PackageResponse)
async def update_package(
    package_id: int,
    package: PackageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update package details"""
    existing_package = (
        db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
    )
    if not existing_package:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.packages.packageNotFound"}
        )

    # Check if name conflicts with another package
    if package.name != existing_package.name:
        name_conflict = (
            db.query(InstalledPackage)
            .filter(
                InstalledPackage.name == package.name, InstalledPackage.id != package_id
            )
            .first()
        )
        if name_conflict:
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.packages.packageAlreadyExists",
                    "params": {"name": package.name},
                },
            )

    # Update package details
    existing_package.name = package.name
    existing_package.install_command = package.install_command
    existing_package.description = package.description
    existing_package.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(existing_package)

    logger.info(
        "Package updated",
        package_id=package_id,
        name=package.name,
        user=current_user.username,
    )
    return existing_package


@router.delete("/{package_id}")
async def delete_package(
    package_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a package from the list (does not uninstall from system)"""
    package = (
        db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
    )
    if not package:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.packages.packageNotFound"}
        )

    package_name = package.name
    db.delete(package)
    db.commit()

    logger.info(
        "Package removed from list", package=package_name, user=current_user.username
    )
    return {"message": "backend.success.packages.packageRemoved"}


@router.post("/{package_id}/reinstall")
async def reinstall_package(
    package_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reinstall a package"""
    package = (
        db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
    )
    if not package:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.packages.packageNotFound"}
        )

    # Reset status to pending before reinstalling
    package.status = "pending"
    package.install_log = None
    package.installed_at = None
    db.commit()

    # Call install endpoint
    return await install_package(package_id, current_user, db)


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: int, db: Session = Depends(get_db)):
    """Get the status of a package installation job"""
    job = db.query(PackageInstallJob).filter(PackageInstallJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.packages.jobNotFound"}
        )

    return {
        "id": job.id,
        "package_id": job.package_id,
        "status": job.status,
        "started_at": serialize_datetime(job.started_at),
        "completed_at": serialize_datetime(job.completed_at),
        "exit_code": job.exit_code,
        "stdout": job.stdout,
        "stderr": job.stderr,
        "error_message": job.error_message,
    }


@router.get("/jobs")
async def list_jobs(db: Session = Depends(get_db)):
    """List all package installation jobs"""
    jobs = (
        db.query(PackageInstallJob)
        .order_by(PackageInstallJob.created_at.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "id": job.id,
            "package_id": job.package_id,
            "status": job.status,
            "started_at": serialize_datetime(job.started_at),
            "completed_at": serialize_datetime(job.completed_at),
            "exit_code": job.exit_code,
            "created_at": serialize_datetime(job.created_at),
        }
        for job in jobs
    ]
