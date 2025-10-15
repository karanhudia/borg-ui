import asyncio
import os
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import BackupJob
from app.config import settings

logger = structlog.get_logger()

class BackupService:
    """Service for executing backups with real-time log streaming"""

    def __init__(self):
        self.log_dir = Path("/data/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def execute_backup(self, job_id: int, repository: str, config_file: str, db: Session):
        """Execute backup using borg directly for better control"""

        # Get job
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            logger.error("Job not found", job_id=job_id)
            return

        # Create log file
        log_file = self.log_dir / f"backup_{job_id}.log"
        job.log_file_path = str(log_file)
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()

        # Build borg create command directly
        # Format: borg create --progress --stats --list REPOSITORY::ARCHIVE PATH
        archive_name = f"manual-backup-{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}"

        cmd = [
            "borg", "create",
            "--progress",
            "--stats",
            "--list",
            "--compression", "lz4",
            f"{repository}::{archive_name}",
            "/data"  # Default backup path - could be made configurable
        ]

        # Set environment variables for borg
        env = os.environ.copy()

        # Skip interactive prompts (auto-accept for unencrypted repos, etc.)
        env['BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK'] = 'yes'
        env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'

        # If you have a passphrase stored somewhere, set it here:
        # env['BORG_PASSPHRASE'] = 'your-passphrase'

        logger.info("Starting borg backup", job_id=job_id, repository=repository, archive=archive_name, command=" ".join(cmd))

        try:
            # Execute command and stream to log file
            with open(log_file, 'w') as f:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
                    env=env
                )

                # Stream output line by line
                async for line in process.stdout:
                    line_str = line.decode('utf-8', errors='replace')
                    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    log_line = f"[{timestamp}] {line_str}"
                    f.write(log_line)
                    f.flush()  # Force write to disk immediately

                # Wait for process to complete
                await process.wait()

                # Update job status
                if process.returncode == 0:
                    job.status = "completed"
                    job.progress = 100
                else:
                    job.status = "failed"
                    job.error_message = f"Backup failed with exit code {process.returncode}"

                job.completed_at = datetime.utcnow()

                # Read full logs and store in database
                with open(log_file, 'r') as log_read:
                    job.logs = log_read.read()

                db.commit()
                logger.info("Backup completed", job_id=job_id, status=job.status)

        except Exception as e:
            logger.error("Backup execution failed", job_id=job_id, error=str(e))
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()

# Global instance
backup_service = BackupService()
