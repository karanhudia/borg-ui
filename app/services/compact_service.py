import asyncio
import json
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import CompactJob, Repository
from app.database.database import SessionLocal
from app.config import settings
from app.core.borg import borg
from app.services.maintenance_state import apply_compact_completion
from app.utils.db_retries import commit_with_retry
from app.utils.borg_env import build_repository_borg_env, cleanup_temp_key_file

logger = structlog.get_logger()


def get_process_start_time(pid: int) -> int:
    """
    Read process start time from /proc/[pid]/stat
    Returns: jiffies since system boot (unique per process)
    """
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            stat_data = f.read()
        # Parse: pid (comm) state ppid ... starttime (22nd field)
        # Split by ) to handle process names with spaces/parens
        fields = stat_data.split(")")[1].split()
        starttime = int(fields[19])  # 22nd field overall
        return starttime
    except Exception as e:
        logger.error("Failed to read process start time", pid=pid, error=str(e))
        return 0


class CompactService:
    """Service for executing repository compact operations with real-time progress tracking"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running processes by job_id

    async def cancel_compact(self, job_id: int) -> bool:
        """Cancel a running compact job by terminating its tracked process."""
        if job_id not in self.running_processes:
            logger.warning("No running compact process found for job", job_id=job_id)
            return False

        process = self.running_processes[job_id]
        try:
            process.terminate()
            logger.info(
                "Sent SIGTERM to compact process", job_id=job_id, pid=process.pid
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                logger.warning(
                    "Force killed compact process (SIGKILL)",
                    job_id=job_id,
                    pid=process.pid,
                )
                await process.wait()
            return True
        except Exception as e:
            logger.error(
                "Failed to cancel compact process", job_id=job_id, error=str(e)
            )
            return False

    async def execute_compact(
        self, job_id: int, repository_id: int, db: Session = None
    ):
        """Execute repository compact operation with progress tracking"""

        # Create a new database session for this background task
        db = SessionLocal()
        temp_key_file = None

        try:
            # Get job
            job = db.query(CompactJob).filter(CompactJob.id == job_id).first()
            if not job:
                logger.error("Compact job not found", job_id=job_id)
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
                    action="compact_missing_repo",
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
                    action="compact_start",
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
                show_progress=True,
            )
            if temp_key_file:
                logger.info("Using SSH key for compact", job_id=job_id)

            # Build command with --verbose to show freed space summary
            cmd = [borg.borg_cmd, "compact", "--progress", "--verbose", "--log-json"]
            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])
            cmd.append(repository.path)

            logger.info(
                "Starting borg compact",
                job_id=job_id,
                repository=repository.path,
                command=" ".join(cmd),
            )

            # Execute command
            # Note: --progress writes to stderr, not stdout, so we need to capture stderr separately
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,  # Capture stderr separately for progress
                env=env,
            )

            # Store PID and start time for orphan detection on container restart
            process_start_time = get_process_start_time(process.pid)

            def persist_pid_tracking():
                job.process_pid = process.pid
                job.process_start_time = process_start_time

            await commit_with_retry(
                db,
                prepare=persist_pid_tracking,
                logger=logger,
                action="compact_store_pid",
                job_id=job_id,
                repository_id=repository_id,
            )

            logger.info(
                "Stored PID tracking info",
                job_id=job_id,
                pid=job.process_pid,
                start_time=job.process_start_time,
            )

            # Track this process so it can be cancelled
            self.running_processes[job_id] = process

            # Flag to track cancellation
            cancelled = False

            # Performance optimization: Batch database commits
            last_commit_time = asyncio.get_event_loop().time()
            COMMIT_INTERVAL = 3.0  # Commit every 3 seconds

            # Progress message throttling to prevent spam
            last_progress_update = {}  # Track last update time per message
            PROGRESS_THROTTLE_INTERVAL = (
                2.0  # Only update progress message every 2 seconds for same message
            )

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
                            "Compact job cancelled, terminating process", job_id=job_id
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
                """Stream log output from process and parse progress"""
                nonlocal cancelled, last_commit_time
                try:
                    # Read from stderr where --progress output goes
                    async for line in process.stderr:
                        if cancelled:
                            break

                        line_str = line.decode("utf-8", errors="replace").strip()

                        # Add to log buffer
                        log_buffer.append(line_str)
                        if len(log_buffer) > MAX_BUFFER_SIZE:
                            log_buffer.pop(0)

                        # Parse JSON progress messages (similar to check_service.py)
                        try:
                            if line_str and line_str[0] == "{":
                                json_msg = json.loads(line_str)
                                msg_type = json_msg.get("type")

                                # Parse progress_percent messages for compact operations
                                if msg_type == "progress_percent":
                                    message = json_msg.get("message", "")
                                    finished = json_msg.get("finished", False)
                                    current = json_msg.get("current", 0)
                                    total = json_msg.get("total", 1)

                                    current_time = asyncio.get_event_loop().time()

                                    # Build progress message with operation counts when available
                                    # Skip appending counts when message is empty (phase transitions)
                                    if message:
                                        progress_msg = f"{message} ({current}/{total})"

                                        # Throttle progress message updates to prevent spam
                                        # Only update if this is a new message or enough time has passed
                                        last_update_time = last_progress_update.get(
                                            progress_msg, 0
                                        )
                                        if (
                                            current_time - last_update_time
                                            >= PROGRESS_THROTTLE_INTERVAL
                                        ):
                                            job.progress_message = progress_msg
                                            last_progress_update[progress_msg] = (
                                                current_time
                                            )
                                    # Don't update progress_message when message is empty (keeps last good message)

                                    if not finished:
                                        # Extract percentage from current/total
                                        if total > 0:
                                            percentage = (current / total) * 100
                                            job.progress = int(percentage)

                                        # Batched commit
                                        if (
                                            current_time - last_commit_time
                                            >= COMMIT_INTERVAL
                                        ):
                                            progress = job.progress
                                            progress_message = job.progress_message

                                            def persist_progress():
                                                job.progress = progress
                                                job.progress_message = progress_message

                                            await commit_with_retry(
                                                db,
                                                prepare=persist_progress,
                                                logger=logger,
                                                action="compact_progress",
                                                job_id=job_id,
                                                repository_id=repository_id,
                                            )
                                            last_commit_time = current_time
                                            logger.info(
                                                "Compact progress committed to DB",
                                                job_id=job_id,
                                                progress=job.progress,
                                                message=message,
                                            )
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            # Not JSON or invalid format, skip
                            pass

                except asyncio.CancelledError:
                    logger.info("Log streaming cancelled", job_id=job_id)
                    raise
                finally:
                    # Final commit
                    final_progress = job.progress
                    final_progress_message = job.progress_message

                    def persist_stream_state():
                        job.progress = final_progress
                        job.progress_message = final_progress_message

                    await commit_with_retry(
                        db,
                        prepare=persist_stream_state,
                        logger=logger,
                        action="compact_stream_finalize",
                        job_id=job_id,
                        repository_id=repository_id,
                    )

            # Run both tasks concurrently
            try:
                await asyncio.gather(
                    check_cancellation(), stream_logs(), return_exceptions=True
                )
            except asyncio.CancelledError:
                logger.info("Compact task cancelled", job_id=job_id)
                cancelled = True
                process.terminate()
                await process.wait()
                raise

            # Wait for process to complete
            if process.returncode is None:
                await process.wait()

            # Update job status
            if job.status == "cancelled":
                logger.info("Compact job was cancelled", job_id=job_id)
                job.completed_at = datetime.utcnow()
            else:
                apply_compact_completion(
                    job,
                    repository,
                    process.returncode,
                )
                if job.status == "completed":
                    logger.info("Compact completed successfully", job_id=job_id)
                elif job.status == "completed_with_warnings":
                    logger.warning(
                        "Compact completed with warnings",
                        job_id=job_id,
                        exit_code=process.returncode,
                    )
                else:
                    logger.error(
                        "Compact failed", job_id=job_id, exit_code=process.returncode
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
                    / f"compact_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
                try:
                    log_file.write_text("\n".join(log_buffer))
                    # Store file path and set has_logs flag (like backup/prune jobs)
                    job.log_file_path = str(log_file)
                    job.has_logs = True
                    job.logs = f"Logs saved to: {log_file.name}"  # Kept for backwards compatibility
                    if job.status == "completed":
                        logger.info(
                            "Compact logs saved",
                            job_id=job_id,
                            log_file=str(log_file),
                            log_lines=len(log_buffer),
                        )
                    else:
                        logger.warning(
                            "Compact logs saved for debugging",
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
            final_progress = job.progress
            final_progress_message = job.progress_message
            final_completed_at = job.completed_at
            final_error_message = job.error_message
            final_log_file_path = job.log_file_path
            final_has_logs = job.has_logs
            final_logs = job.logs
            repository_last_compact = repository.last_compact

            def persist_final_state():
                job.status = final_status
                job.progress = final_progress
                job.progress_message = final_progress_message
                job.completed_at = final_completed_at
                job.error_message = final_error_message
                job.log_file_path = final_log_file_path
                job.has_logs = final_has_logs
                job.logs = final_logs
                repository.last_compact = repository_last_compact

            await commit_with_retry(
                db,
                prepare=persist_final_state,
                logger=logger,
                action="compact_finalize",
                job_id=job_id,
                repository_id=repository_id,
            )
            logger.info("Compact job completed", job_id=job_id, status=job.status)

        except Exception as e:
            logger.error("Compact execution failed", job_id=job_id, error=str(e))

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
                    action="compact_fail",
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
compact_service = CompactService()
