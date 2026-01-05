import asyncio
import os
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import PruneJob, Repository
from app.database.database import SessionLocal
from app.config import settings

logger = structlog.get_logger()


class PruneService:
    """Service for executing repository prune operations with job tracking"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running processes by job_id

    async def execute_prune(
        self,
        job_id: int,
        repository_id: int,
        keep_hourly: int,
        keep_daily: int,
        keep_weekly: int,
        keep_monthly: int,
        keep_quarterly: int,
        keep_yearly: int,
        dry_run: bool = False,
        db: Session = None
    ):
        """Execute repository prune operation with job tracking"""

        # Create a new database session for this background task
        db = SessionLocal()

        try:
            # Get job
            job = db.query(PruneJob).filter(PruneJob.id == job_id).first()
            if not job:
                logger.error("Prune job not found", job_id=job_id)
                return

            # Get repository
            repository = db.query(Repository).filter(Repository.id == repository_id).first()
            if not repository:
                logger.error("Repository not found", repository_id=repository_id)
                job.status = "failed"
                job.error_message = f"Repository not found (ID: {repository_id})"
                job.completed_at = datetime.utcnow()
                db.commit()
                return

            # Update job status
            job.status = "running"
            job.started_at = datetime.utcnow()
            db.commit()

            # Set environment variables for borg
            env = os.environ.copy()

            # Add passphrase if available
            if repository.passphrase:
                env['BORG_PASSPHRASE'] = repository.passphrase

            # Configure lock behavior
            env["BORG_LOCK_WAIT"] = "180"
            env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

            # Add SSH options for remote repos
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR",
                "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=3",
                "-o", "TCPKeepAlive=yes",
                "-o", "RequestTTY=no",
                "-o", "PermitLocalCommand=no"
            ]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            # Build prune command
            # Note: --stats is not supported with --dry-run in Borg 1.4.x
            cmd = ["borg", "prune", "--list", "--log-json"]

            # Add dry-run flag if requested
            if dry_run:
                cmd.append("--dry-run")
            else:
                # Only add --stats for non-dry-run operations
                cmd.append("--stats")

            # Add retention policy arguments
            if keep_hourly > 0:
                cmd.extend(["--keep-hourly", str(keep_hourly)])
            if keep_daily > 0:
                cmd.extend(["--keep-daily", str(keep_daily)])
            if keep_weekly > 0:
                cmd.extend(["--keep-weekly", str(keep_weekly)])
            if keep_monthly > 0:
                cmd.extend(["--keep-monthly", str(keep_monthly)])
            if keep_quarterly > 0:
                # Borg 1.4.x uses --keep-3monthly for quarterly (every 3 months)
                # --keep-quarterly was added in borg 1.5.0
                cmd.extend(["--keep-3monthly", str(keep_quarterly)])
            if keep_yearly > 0:
                cmd.extend(["--keep-yearly", str(keep_yearly)])

            # Add remote path if specified
            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])

            cmd.append(repository.path)

            logger.info("Starting borg prune",
                       job_id=job_id,
                       repository=repository.path,
                       dry_run=dry_run,
                       command=" ".join(cmd))

            # Execute command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            # Track this process so it can be cancelled
            self.running_processes[job_id] = process

            # Flag to track cancellation
            cancelled = False

            # In-memory log buffer
            log_buffer = []
            MAX_BUFFER_SIZE = 1000

            async def check_cancellation():
                """Periodic heartbeat to check for cancellation"""
                nonlocal cancelled
                while not cancelled and process.returncode is None:
                    await asyncio.sleep(3)
                    db.refresh(job)
                    if job.status == "cancelled":
                        logger.info("Prune job cancelled, terminating process", job_id=job_id)
                        cancelled = True
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            logger.warning("Process didn't terminate, killing it", job_id=job_id)
                            process.kill()
                            await process.wait()
                        break

            async def stream_logs():
                """Stream log output from process"""
                nonlocal cancelled
                try:
                    # Read from both stdout and stderr
                    async def read_stream(stream, name):
                        try:
                            async for line in stream:
                                if cancelled:
                                    break
                                line_str = line.decode('utf-8', errors='replace').strip()
                                if line_str:
                                    log_buffer.append(f"[{name}] {line_str}")
                                    if len(log_buffer) > MAX_BUFFER_SIZE:
                                        log_buffer.pop(0)
                        except asyncio.CancelledError:
                            pass

                    await asyncio.gather(
                        read_stream(process.stdout, "stdout"),
                        read_stream(process.stderr, "stderr"),
                        return_exceptions=True
                    )

                except asyncio.CancelledError:
                    logger.info("Log streaming cancelled", job_id=job_id)
                    raise

            # Run both tasks concurrently
            try:
                await asyncio.gather(
                    check_cancellation(),
                    stream_logs(),
                    return_exceptions=True
                )
            except asyncio.CancelledError:
                logger.info("Prune task cancelled", job_id=job_id)
                cancelled = True
                process.terminate()
                await process.wait()
                raise

            # Wait for process to complete
            if process.returncode is None:
                await process.wait()

            # Update job status
            if job.status == "cancelled":
                logger.info("Prune job was cancelled", job_id=job_id)
                job.completed_at = datetime.utcnow()
            elif process.returncode == 0:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                logger.info("Prune completed successfully",
                           job_id=job_id,
                           dry_run=dry_run)
            else:
                job.status = "failed"
                job.error_message = f"Prune failed with exit code {process.returncode}"
                job.completed_at = datetime.utcnow()
                logger.error("Prune failed",
                           job_id=job_id,
                           exit_code=process.returncode)

            # Save logs for all completed/failed/cancelled jobs
            if job.status in ['failed', 'cancelled', 'completed']:
                log_file = self.log_dir / f"prune_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                try:
                    log_file.write_text('\n'.join(log_buffer))
                    # Store file path and set has_logs flag (like backup jobs)
                    job.log_file_path = str(log_file)
                    job.has_logs = True
                    job.logs = f"Logs saved to: {log_file.name}"  # Kept for backwards compatibility
                    if job.status == 'completed':
                        logger.info("Prune logs saved",
                                   job_id=job_id,
                                   log_file=str(log_file),
                                   log_lines=len(log_buffer),
                                   dry_run=dry_run)
                    else:
                        logger.warning("Prune logs saved for debugging",
                                     job_id=job_id,
                                     log_file=str(log_file),
                                     log_lines=len(log_buffer))
                except Exception as e:
                    job.has_logs = False
                    job.logs = f"Failed to save logs: {str(e)}"
                    logger.error("Failed to save log buffer", job_id=job_id, error=str(e))

            db.commit()
            logger.info("Prune job completed", job_id=job_id, status=job.status, dry_run=dry_run)

        except Exception as e:
            logger.error("Prune execution failed", job_id=job_id, error=str(e))
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()
        finally:
            # Remove from running processes
            if job_id in self.running_processes:
                del self.running_processes[job_id]

            # Close the database session
            db.close()


# Global instance
prune_service = PruneService()
