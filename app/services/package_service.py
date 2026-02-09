"""
Package installation service - handles async package installation jobs
"""
import asyncio
import os
import time
from datetime import datetime
from typing import Optional
import structlog
from sqlalchemy.orm import Session

from app.database.models import InstalledPackage, PackageInstallJob

logger = structlog.get_logger()


class PackageInstallService:
    """Service for handling background package installation"""

    def __init__(self):
        self.running_jobs = {}  # job_id -> asyncio.Task

    async def start_install_job(
        self,
        db: Session,
        package_id: int
    ) -> PackageInstallJob:
        """
        Start a package installation job in the background.
        Returns the job immediately (non-blocking).
        """
        package = db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
        if not package:
            raise ValueError(f"Package {package_id} not found")

        # Create job record
        job = PackageInstallJob(
            package_id=package_id,
            status="pending"
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        logger.info("Created package install job", job_id=job.id, package=package.name)

        # Start background task
        task = asyncio.create_task(
            self._run_install_job(job.id, package_id, package.install_command, package.name)
        )
        self.running_jobs[job.id] = task

        return job

    async def _run_install_job(
        self,
        job_id: int,
        package_id: int,
        install_command: str,
        package_name: str
    ):
        """
        Background task that actually runs the package installation.
        """
        from app.database.database import SessionLocal

        db = SessionLocal()
        job = None

        try:
            job = db.query(PackageInstallJob).filter(PackageInstallJob.id == job_id).first()
            package = db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()

            if not job or not package:
                logger.error("Job or package not found", job_id=job_id, package_id=package_id)
                return

            # Update job status to installing - may fail if job was deleted after we queried it
            try:
                job.status = "installing"
                job.started_at = datetime.utcnow()
                package.status = "installing"
                db.commit()
            except Exception as status_error:
                # Job was deleted while starting - exit gracefully
                logger.warning("Could not update job to installing status (job may have been deleted)",
                              job_id=job_id, error=str(status_error))
                return

            logger.info("Starting package installation", job_id=job_id, package=package_name)

            # Run installation command
            process = await asyncio.create_subprocess_shell(
                install_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}
            )

            # Store PID for orphan detection
            job.process_pid = process.pid
            if process.pid:
                try:
                    with open(f'/proc/{process.pid}/stat', 'r') as f:
                        stat = f.read().split()
                        job.process_start_time = int(stat[21])  # starttime in jiffies
                except Exception:
                    pass
            db.commit()

            # Wait for completion with timeout (5 minutes)
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=300.0
                )
                exit_code = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise Exception("Package installation timed out (5 minute limit)")

            stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""

            # Update job and package status
            job.exit_code = exit_code
            job.stdout = stdout_str
            job.stderr = stderr_str
            job.completed_at = datetime.utcnow()

            if exit_code == 0:
                job.status = "completed"
                package.status = "installed"
                package.installed_at = datetime.utcnow()
                package.install_log = f"STDOUT:\n{stdout_str}\n\nSTDERR:\n{stderr_str}"
                logger.info("Package installation completed", job_id=job_id, package=package_name)
            else:
                job.status = "failed"
                job.error_message = f"Installation failed with exit code {exit_code}"
                package.status = "failed"
                package.install_log = f"Exit code: {exit_code}\n\nSTDOUT:\n{stdout_str}\n\nSTDERR:\n{stderr_str}"
                logger.error("Package installation failed", job_id=job_id, package=package_name, exit_code=exit_code)

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
                package = db.query(InstalledPackage).filter(InstalledPackage.id == package_id).first()
                if package:
                    package.status = "failed"
                    package.install_log = f"Error: {str(e)}"
                    package.last_check = datetime.utcnow()
                    db.commit()
            except Exception as commit_error:
                # Job or package may have been deleted while running - that's okay
                logger.warning("Could not update job/package status (may have been deleted during execution)",
                              job_id=job_id, error=str(commit_error))
                db.rollback()

        finally:
            db.close()
            # Remove from running jobs
            if job_id in self.running_jobs:
                del self.running_jobs[job_id]

    def get_job_status(self, db: Session, job_id: int) -> Optional[PackageInstallJob]:
        """Get the current status of a job"""
        return db.query(PackageInstallJob).filter(PackageInstallJob.id == job_id).first()

    def get_running_jobs(self, db: Session) -> list:
        """Get all currently running/pending jobs"""
        return db.query(PackageInstallJob).filter(
            PackageInstallJob.status.in_(["pending", "installing"])
        ).all()


# Global service instance
package_service = PackageInstallService()
