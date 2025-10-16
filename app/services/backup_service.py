import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import BackupJob, Repository
from app.database.database import SessionLocal
from app.config import settings

logger = structlog.get_logger()

class BackupService:
    """Service for executing backups with real-time log streaming"""

    def __init__(self):
        self.log_dir = Path("/data/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def execute_backup(self, job_id: int, repository: str, config_file: str, db: Session = None):
        """Execute backup using borg directly for better control"""

        # Create a new database session for this background task
        db = SessionLocal()

        try:
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
            # Format: borg create --progress --stats --list REPOSITORY::ARCHIVE PATH [PATH ...]
            archive_name = f"manual-backup-{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}"

            # Set environment variables for borg
            env = os.environ.copy()

            # Use modern exit codes for better error handling
            # 0 = success, 1 = warning, 2+ = error
            # Modern: 0 = success, 1-99 reserved, 3-99 = errors, 100-127 = warnings
            env['BORG_EXIT_CODES'] = 'modern'

            # Skip interactive prompts (auto-accept for unencrypted repos, etc.)
            env['BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK'] = 'yes'
            env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'

            # Look up repository record to get passphrase and source directories
            source_paths = ["/data"]  # Default backup path
            try:
                repo_record = db.query(Repository).filter(Repository.path == repository).first()
                if repo_record:
                    # Set passphrase if available
                    if repo_record.passphrase:
                        env['BORG_PASSPHRASE'] = repo_record.passphrase
                        logger.info("Using passphrase from repository record", repository=repository)

                    # Parse source directories from JSON if available
                    if repo_record.source_directories:
                        try:
                            source_dirs = json.loads(repo_record.source_directories)
                            if source_dirs and isinstance(source_dirs, list) and len(source_dirs) > 0:
                                source_paths = source_dirs
                                logger.info("Using source directories from repository",
                                          repository=repository,
                                          source_directories=source_paths)
                            else:
                                logger.info("No source directories configured, using default /data",
                                          repository=repository)
                        except json.JSONDecodeError as e:
                            logger.warning("Could not parse source_directories JSON, using default /data",
                                         repository=repository, error=str(e))
                else:
                    logger.warning("Repository record not found, using defaults", repository=repository)
            except Exception as e:
                logger.warning("Could not look up repository record", error=str(e))

            # Build command with source directories
            cmd = [
                "borg", "create",
                "--progress",
                "--stats",
                "--list",
                "--show-rc",  # Show return code for better debugging
                "--log-json",  # Structured JSON logging
                "--compression", "lz4",
                f"{repository}::{archive_name}",
            ]
            # Add all source paths to the command
            cmd.extend(source_paths)

            logger.info("Starting borg backup", job_id=job_id, repository=repository, archive=archive_name, command=" ".join(cmd))

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

                # Update job status using modern exit codes
                # 0 = success, 1 = warning (legacy), 2 = error (legacy)
                # Modern: 0 = success, 3-99 = errors, 100-127 = warnings
                if process.returncode == 0:
                    job.status = "completed"
                    job.progress = 100
                elif 100 <= process.returncode <= 127:
                    # Warning (modern exit code system)
                    job.status = "completed"
                    job.progress = 100
                    job.error_message = f"Backup completed with warning (exit code {process.returncode})"
                    logger.warning("Backup completed with warning", job_id=job_id, exit_code=process.returncode)
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
        finally:
            # Close the database session
            db.close()

# Global instance
backup_service = BackupService()
