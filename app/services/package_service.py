"""
Package installation service - handles async package installation jobs.

Phase 6 moved the job row to `operations` (spec 6.2, 6.3): `start_install_job`
only enqueues, the runner dispatches `run_install_job`, and the captured output
lives in the operation's log file rather than two columns.
"""

import asyncio
import os
from datetime import datetime
import structlog
from sqlalchemy.orm import Session

from app.database.models import InstalledPackage, Operation, PackageInstallJob
from app.services.operations.enqueue import enqueue
from app.services.operations.package_facade import (
    PackageInstallFacade,
    resolve_package_job,
)

logger = structlog.get_logger()


class PackageInstallService:
    """Service for handling background package installation"""

    async def start_install_job(self, db: Session, package_id: int):
        """Queue a package installation. The runner starts it (spec 7.1);
        nothing is spawned here. Returns the job immediately."""
        package = (
            db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
        )
        if not package:
            raise ValueError(f"Package {package_id} not found")

        operation = enqueue(
            db,
            "package_install",
            trigger="manual",
            params={"package_id": package_id},
        )
        logger.info(
            "Queued package install operation",
            job_id=operation.id,
            package=package.name,
        )
        return PackageInstallFacade(db, operation)

    async def run_install_job(self, job_id: int):
        """Run the installation. Called by the operations runner."""
        from app.database.database import SessionLocal

        db = SessionLocal()
        job = None
        # Bound before the try: the failure handler below reads it, and the
        # first statement in the try is what resolves it.
        package_id = None

        try:
            job = resolve_package_job(db, job_id)
            package_id = job.package_id if job else None
            package = (
                db.query(InstalledPackage)
                .filter(InstalledPackage.id == package_id)
                .first()
                if package_id is not None
                else None
            )
            install_command = package.install_command if package else None
            package_name = package.name if package else None

            if not job or not package:
                logger.error(
                    "Job or package not found", job_id=job_id, package_id=package_id
                )
                return

            # Update job status to installing - may fail if job was deleted after we queried it
            try:
                job.status = "installing"
                job.started_at = datetime.utcnow()
                package.status = "installing"
                db.commit()
            except Exception as status_error:
                # Job was deleted while starting - exit gracefully
                logger.warning(
                    "Could not update job to installing status (job may have been deleted)",
                    job_id=job_id,
                    error=str(status_error),
                )
                return

            logger.info(
                "Starting package installation", job_id=job_id, package=package_name
            )

            # Run installation command
            process = await asyncio.create_subprocess_shell(
                install_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
            )

            # Store PID for orphan detection
            job.process_pid = process.pid
            if process.pid:
                try:
                    with open(f"/proc/{process.pid}/stat", "r") as f:
                        stat = f.read().split()
                        job.process_start_time = int(stat[21])  # starttime in jiffies
                except Exception:
                    pass
            db.commit()

            # Wait for completion with timeout (5 minutes)
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=300.0
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise Exception("Package installation timed out (5 minute limit)")

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            # Update job and package status
            job.exit_code = exit_code
            job.write_output(stdout_str, stderr_str)
            job.completed_at = datetime.utcnow()

            if exit_code == 0:
                job.status = "completed"
                package.status = "installed"
                package.installed_at = datetime.utcnow()
                package.install_log = f"STDOUT:\n{stdout_str}\n\nSTDERR:\n{stderr_str}"
                logger.info(
                    "Package installation completed",
                    job_id=job_id,
                    package=package_name,
                )
            else:
                job.status = "failed"
                job.error_message = f"Installation failed with exit code {exit_code}"
                package.status = "failed"
                package.install_log = f"Exit code: {exit_code}\n\nSTDOUT:\n{stdout_str}\n\nSTDERR:\n{stderr_str}"
                logger.error(
                    "Package installation failed",
                    job_id=job_id,
                    package=package_name,
                    exit_code=exit_code,
                )

            package.last_check = datetime.utcnow()
            db.commit()

        except Exception as e:
            logger.error("Package installation error", job_id=job_id, error=str(e))

            # Try to update job status - may fail if job was deleted during execution
            try:
                if job:
                    job.status = "failed"
                    job.error_message = str(e)
                    job.completed_at = datetime.utcnow()
                    db.commit()

                # Update package status
                package = (
                    db.query(InstalledPackage)
                    .filter(InstalledPackage.id == package_id)
                    .first()
                )
                if package:
                    package.status = "failed"
                    package.install_log = f"Error: {str(e)}"
                    package.last_check = datetime.utcnow()
                    db.commit()
            except Exception as commit_error:
                # Job or package may have been deleted while running - that's okay
                logger.warning(
                    "Could not update job/package status (may have been deleted during execution)",
                    job_id=job_id,
                    error=str(commit_error),
                )
                db.rollback()

        finally:
            db.close()

    def get_job_status(self, db: Session, job_id: int):
        """Get the current status of a job. Operations first, then a
        pre-phase-6 legacy row."""
        return resolve_package_job(db, job_id)

    def get_running_jobs(self, db: Session) -> list:
        """Get all currently running/pending jobs"""
        jobs = [
            PackageInstallFacade(db, op)
            for op in db.query(Operation)
            .filter(
                Operation.kind == "package_install",
                Operation.status.in_(("queued", "running")),
            )
            .all()
        ]
        # Pre-phase-6 rows only; goes away with the table in phase 9.
        jobs.extend(
            db.query(PackageInstallJob)
            .filter(PackageInstallJob.status.in_(["pending", "installing"]))
            .all()
        )
        return jobs


# Global service instance
package_service = PackageInstallService()
