import asyncio
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import PruneJob, Repository
from app.database.database import SessionLocal
from app.config import settings
from app.core.borg import borg
from app.utils.db_retries import commit_with_retry
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file

logger = structlog.get_logger()


class PruneService:
    """Service for executing repository prune operations with job tracking"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running processes by job_id

    async def cancel_prune(self, job_id: int) -> bool:
        """Cancel a running prune job by terminating its tracked process."""
        if job_id not in self.running_processes:
            logger.warning("No running prune process found for job", job_id=job_id)
            return False

        process = self.running_processes[job_id]
        try:
            process.terminate()
            logger.info("Sent SIGTERM to prune process", job_id=job_id, pid=process.pid)
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                logger.warning(
                    "Force killed prune process (SIGKILL)",
                    job_id=job_id,
                    pid=process.pid,
                )
                await process.wait()
            return True
        except Exception as e:
            logger.error("Failed to cancel prune process", job_id=job_id, error=str(e))
            return False

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
        db: Session = None,
    ):
        """Execute repository prune operation with job tracking"""

        # Create a new database session for this background task
        db = SessionLocal()
        temp_key_file = None

        try:
            # Get job
            job = db.query(PruneJob).filter(PruneJob.id == job_id).first()
            if not job:
                logger.error("Prune job not found", job_id=job_id)
                return

            # Get repository
            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                logger.error("Repository not found", repository_id=repository_id)
                completed_at = datetime.utcnow()

                def persist_missing_repo_state():
                    job.status = "failed"
                    job.error_message = f"Repository not found (ID: {repository_id})"
                    job.completed_at = completed_at

                await commit_with_retry(
                    db,
                    prepare=persist_missing_repo_state,
                    logger=logger,
                    action="prune_missing_repo",
                    job_id=job_id,
                    repository_id=repository_id,
                )
                return

            # Update job status - may fail if job was deleted after we queried it
            try:
                started_at = datetime.utcnow()

                def persist_start_state():
                    job.status = "running"
                    job.started_at = started_at

                await commit_with_retry(
                    db,
                    prepare=persist_start_state,
                    logger=logger,
                    action="prune_start",
                    job_id=job_id,
                    repository_id=repository_id,
                )
            except Exception as status_error:
                # Job was deleted while starting - exit gracefully
                logger.warning(
                    "Could not update job to running status (job may have been deleted)",
                    job_id=job_id,
                    error=str(status_error),
                )
                return

            env, temp_key_file = build_repository_borg_env(
                repository,
                db,
                keepalive=True,
            )
            if temp_key_file:
                logger.info("Using SSH key for prune", job_id=job_id)

            # Build prune command
            # Note: --stats is not supported with --dry-run in Borg 1.4.x
            cmd = [borg.borg_cmd, "prune", "--list", "--log-json"]

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

            logger.info(
                "Starting borg prune",
                job_id=job_id,
                repository=repository.path,
                dry_run=dry_run,
                command=" ".join(cmd),
            )

            # Execute command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
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
                        logger.info(
                            "Prune job cancelled, terminating process", job_id=job_id
                        )
                        cancelled = True
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            logger.warning(
                                "Process didn't terminate, killing it", job_id=job_id
                            )
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
                                line_str = line.decode(
                                    "utf-8", errors="replace"
                                ).strip()
                                if line_str:
                                    log_buffer.append(f"[{name}] {line_str}")
                                    if len(log_buffer) > MAX_BUFFER_SIZE:
                                        log_buffer.pop(0)
                        except asyncio.CancelledError:
                            pass

                    await asyncio.gather(
                        read_stream(process.stdout, "stdout"),
                        read_stream(process.stderr, "stderr"),
                        return_exceptions=True,
                    )

                except asyncio.CancelledError:
                    logger.info("Log streaming cancelled", job_id=job_id)
                    raise

            # Run both tasks concurrently
            try:
                await asyncio.gather(
                    check_cancellation(), stream_logs(), return_exceptions=True
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
                logger.info(
                    "Prune completed successfully", job_id=job_id, dry_run=dry_run
                )
            elif process.returncode == 1 or (100 <= process.returncode <= 127):
                # Warning (legacy exit code 1 or modern exit codes 100-127)
                job.status = "completed_with_warnings"
                job.error_message = (
                    f"Prune completed with warnings (exit code {process.returncode})"
                )
                job.completed_at = datetime.utcnow()
                logger.warning(
                    "Prune completed with warnings",
                    job_id=job_id,
                    exit_code=process.returncode,
                    dry_run=dry_run,
                )
            else:
                job.status = "failed"
                job.error_message = f"Prune failed with exit code {process.returncode}"
                job.completed_at = datetime.utcnow()
                logger.error(
                    "Prune failed", job_id=job_id, exit_code=process.returncode
                )

            # Save logs for all completed/failed/cancelled/warning jobs
            if job.status in [
                "failed",
                "cancelled",
                "completed",
                "completed_with_warnings",
            ]:
                log_file = (
                    self.log_dir
                    / f"prune_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
                try:
                    log_file.write_text("\n".join(log_buffer))
                    # Store file path and set has_logs flag (like backup jobs)
                    job.log_file_path = str(log_file)
                    job.has_logs = True
                    job.logs = f"Logs saved to: {log_file.name}"  # Kept for backwards compatibility
                    if job.status == "completed":
                        logger.info(
                            "Prune logs saved",
                            job_id=job_id,
                            log_file=str(log_file),
                            log_lines=len(log_buffer),
                            dry_run=dry_run,
                        )
                    else:
                        logger.warning(
                            "Prune logs saved for debugging",
                            job_id=job_id,
                            log_file=str(log_file),
                            log_lines=len(log_buffer),
                        )
                except Exception as e:
                    job.has_logs = False
                    job.logs = f"Failed to save logs: {str(e)}"
                    logger.error(
                        "Failed to save log buffer", job_id=job_id, error=str(e)
                    )

            final_status = job.status
            final_completed_at = job.completed_at
            final_error_message = job.error_message
            final_log_file_path = job.log_file_path
            final_has_logs = job.has_logs
            final_logs = job.logs

            def persist_final_state():
                job.status = final_status
                job.completed_at = final_completed_at
                job.error_message = final_error_message
                job.log_file_path = final_log_file_path
                job.has_logs = final_has_logs
                job.logs = final_logs

            await commit_with_retry(
                db,
                prepare=persist_final_state,
                logger=logger,
                action="prune_finalize",
                job_id=job_id,
                repository_id=repository_id,
            )
            logger.info(
                "Prune job completed", job_id=job_id, status=job.status, dry_run=dry_run
            )

        except Exception as e:
            logger.error("Prune execution failed", job_id=job_id, error=str(e))

            # Try to update job status - may fail if job was deleted during execution
            try:
                completed_at = datetime.utcnow()

                def persist_failure_state():
                    job.status = "failed"
                    job.error_message = str(e)
                    job.completed_at = completed_at

                await commit_with_retry(
                    db,
                    prepare=persist_failure_state,
                    logger=logger,
                    action="prune_fail",
                    job_id=job_id,
                    repository_id=repository_id,
                )
            except Exception as commit_error:
                # Job may have been deleted while running - that's okay
                logger.warning(
                    "Could not update job status (job may have been deleted during execution)",
                    job_id=job_id,
                    error=str(commit_error),
                )
                db.rollback()
        finally:
            # Remove from running processes
            if job_id in self.running_processes:
                del self.running_processes[job_id]

            # Clean up temporary SSH key file
            cleanup_temp_key_file(temp_key_file)

            # Close the database session
            db.close()


# Global instance
prune_service = PruneService()
