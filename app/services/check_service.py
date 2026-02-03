import asyncio
import os
import re
import json
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import CheckJob, Repository
from app.database.database import SessionLocal
from app.config import settings
from app.services.notification_service import NotificationService

logger = structlog.get_logger()

def get_process_start_time(pid: int) -> int:
    """
    Read process start time from /proc/[pid]/stat
    Returns: jiffies since system boot (unique per process)
    """
    try:
        with open(f'/proc/{pid}/stat', 'r') as f:
            stat_data = f.read()
        # Parse: pid (comm) state ppid ... starttime (22nd field)
        # Split by ) to handle process names with spaces/parens
        fields = stat_data.split(')')[1].split()
        starttime = int(fields[19])  # 22nd field overall
        return starttime
    except Exception as e:
        logger.error("Failed to read process start time", pid=pid, error=str(e))
        return 0

class CheckService:
    """Service for executing repository check operations with real-time progress tracking"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running processes by job_id

    async def execute_check(self, job_id: int, repository_id: int, db: Session = None):
        """Execute repository check operation with progress tracking"""

        # Create a new database session for this background task
        db = SessionLocal()

        try:
            # Get job
            job = db.query(CheckJob).filter(CheckJob.id == job_id).first()
            if not job:
                logger.error("Check job not found", job_id=job_id)
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
            env["BORG_SHOW_PROGRESS"] = "1"  # Force progress output even when not in a TTY

            # Add SSH options for remote repos with keepalive for orphan prevention
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR",
                "-o", "ServerAliveInterval=15",   # Send keepalive every 15s
                "-o", "ServerAliveCountMax=3",    # Give up after 3 failures (~45s)
                "-o", "TCPKeepAlive=yes",         # Enable TCP-level keepalives
                "-o", "RequestTTY=no",            # Disable TTY allocation to prevent shell initialization output
                "-o", "PermitLocalCommand=no"     # Prevent local command execution
            ]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            # Build command
            cmd = ["borg", "check", "--progress", "--log-json"]

            # Add max-duration if specified and not 0 (unlimited)
            # Note: --repository-only is required when using --max-duration
            if job.max_duration and job.max_duration > 0:
                cmd.extend(["--repository-only", "--max-duration", str(job.max_duration)])

            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])
            cmd.append(repository.path)

            logger.info("Starting borg check", job_id=job_id, repository=repository.path, command=" ".join(cmd))

            # Execute command
            # Note: --progress writes to stderr, not stdout, so we need to capture stderr separately
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,  # Capture stderr separately for progress
                env=env
            )

            # Store PID and start time for orphan detection on container restart
            job.process_pid = process.pid
            job.process_start_time = get_process_start_time(process.pid)
            db.commit()

            logger.info("Stored PID tracking info",
                       job_id=job_id,
                       pid=job.process_pid,
                       start_time=job.process_start_time)

            # Track this process so it can be cancelled
            self.running_processes[job_id] = process

            # Flag to track cancellation
            cancelled = False

            # Performance optimization: Batch database commits
            last_commit_time = asyncio.get_event_loop().time()
            COMMIT_INTERVAL = 3.0  # Commit every 3 seconds

            # Progress message throttling to prevent spam
            last_progress_update = {}  # Track last update time per message
            PROGRESS_THROTTLE_INTERVAL = 2.0  # Only update progress message every 2 seconds for same message

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
                        logger.info("Check job cancelled, terminating process", job_id=job_id)
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
                """Stream log output from process and parse progress"""
                nonlocal cancelled, last_commit_time
                try:
                    # Read from stderr where --progress output goes
                    async for line in process.stderr:
                        if cancelled:
                            break

                        line_str = line.decode('utf-8', errors='replace').strip()

                        # Add to log buffer
                        log_buffer.append(line_str)
                        if len(log_buffer) > MAX_BUFFER_SIZE:
                            log_buffer.pop(0)

                        # Log ALL output for debugging
                        if line_str:
                            logger.info("Check output", job_id=job_id, line=line_str[:200])

                        # Parse JSON progress messages (similar to backup_service.py)
                        try:
                            if line_str and line_str[0] == '{':
                                json_msg = json.loads(line_str)
                                msg_type = json_msg.get('type')
                                logger.info("Parsed JSON message", job_id=job_id, msg_type=msg_type, json=json_msg)

                                # Parse progress_percent messages for check operations
                                if msg_type == 'progress_percent':
                                    message = json_msg.get('message', '')
                                    finished = json_msg.get('finished', False)
                                    operation = json_msg.get('operation', 0)
                                    current = json_msg.get('current', 0)
                                    total = json_msg.get('total', 1)

                                    current_time = asyncio.get_event_loop().time()

                                    # Build progress message with operation counts when available
                                    # Skip appending counts when message is empty (phase transitions)
                                    if message:
                                        progress_msg = f"{message} ({current}/{total})"

                                        # Throttle progress message updates to prevent spam
                                        # Only update if this is a new message or enough time has passed
                                        last_update_time = last_progress_update.get(progress_msg, 0)
                                        if current_time - last_update_time >= PROGRESS_THROTTLE_INTERVAL:
                                            job.progress_message = progress_msg
                                            last_progress_update[progress_msg] = current_time
                                    # Don't update progress_message when message is empty (keeps last good message)

                                    if not finished:
                                        # Extract percentage from current/total
                                        if total > 0:
                                            percentage = (current / total) * 100

                                            # Split progress into phases based on operation
                                            # operation 1 = Checking segments (0-50%)
                                            # operation 2+ = Checking archives (50-100%)
                                            if operation == 1:
                                                # Map 0-100% to 0-50%
                                                job.progress = int(percentage / 2)
                                            else:
                                                # Map 0-100% to 50-100%
                                                job.progress = int(50 + (percentage / 2))

                                        # Batched commit
                                        if current_time - last_commit_time >= COMMIT_INTERVAL:
                                            db.commit()
                                            last_commit_time = current_time
                                            logger.info("Check progress committed to DB",
                                                       job_id=job_id,
                                                       progress=job.progress,
                                                       message=message,
                                                       operation=operation)
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            # Not JSON or invalid format, skip
                            pass

                except asyncio.CancelledError:
                    logger.info("Log streaming cancelled", job_id=job_id)
                    raise
                finally:
                    # Final commit
                    db.commit()

            # Run both tasks concurrently
            try:
                await asyncio.gather(
                    check_cancellation(),
                    stream_logs(),
                    return_exceptions=True
                )
            except asyncio.CancelledError:
                logger.info("Check task cancelled", job_id=job_id)
                cancelled = True
                process.terminate()
                await process.wait()
                raise

            # Wait for process to complete
            if process.returncode is None:
                await process.wait()

            # Update job status
            if job.status == "cancelled":
                logger.info("Check job was cancelled", job_id=job_id)
                job.completed_at = datetime.utcnow()
            elif process.returncode == 0:
                job.status = "completed"
                job.progress = 100
                job.progress_message = "Check completed successfully"
                job.completed_at = datetime.utcnow()
                # Update repository's last_check timestamp
                repository.last_check = datetime.utcnow()
                logger.info("Check completed successfully", job_id=job_id)
            elif process.returncode == 1 or (100 <= process.returncode <= 127):
                # Warning (legacy exit code 1 or modern exit codes 100-127)
                job.status = "completed_with_warnings"
                job.progress = 100
                job.progress_message = f"Check completed with warnings (exit code {process.returncode})"
                job.error_message = f"Check completed with warnings (exit code {process.returncode})"
                job.completed_at = datetime.utcnow()
                # Update repository's last_check timestamp even with warnings
                repository.last_check = datetime.utcnow()
                logger.warning("Check completed with warnings", job_id=job_id, exit_code=process.returncode)
            else:
                job.status = "failed"
                job.error_message = f"Check failed with exit code {process.returncode}"
                job.completed_at = datetime.utcnow()
                logger.error("Check failed", job_id=job_id, exit_code=process.returncode)

            # Save logs to file (always, like prune/compact jobs)
            if log_buffer:
                log_file = self.log_dir / f"check_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                try:
                    log_file.write_text('\n'.join(log_buffer))
                    # Store file path and set has_logs flag (like backup/prune/compact jobs)
                    job.log_file_path = str(log_file)
                    job.has_logs = True
                    job.logs = f"Logs saved to: {log_file.name}"  # Kept for backwards compatibility
                    if job.status == 'completed':
                        logger.info("Check logs saved",
                                   job_id=job_id,
                                   log_file=str(log_file),
                                   log_lines=len(log_buffer))
                    else:
                        logger.warning("Check logs saved for debugging",
                                     job_id=job_id,
                                     log_file=str(log_file),
                                     log_lines=len(log_buffer))
                except Exception as e:
                    job.has_logs = False
                    job.logs = f"Failed to save logs: {str(e)}"
                    logger.error("Failed to save log buffer", job_id=job_id, error=str(e))

            db.commit()

            # Send notifications for completed or failed checks (skip cancelled)
            if job.status in ['completed', 'failed']:
                try:
                    # Calculate duration
                    duration_seconds = None
                    if job.started_at and job.completed_at:
                        duration_seconds = int((job.completed_at - job.started_at).total_seconds())

                    # Determine check type (manual vs scheduled)
                    check_type = "scheduled" if job.scheduled_check else "manual"

                    await NotificationService.send_check_completion(
                        db=db,
                        repository_name=repository.name,
                        repository_path=repository.path,
                        status=job.status,
                        duration_seconds=duration_seconds,
                        error_message=job.error_message if job.status == "failed" else None,
                        check_type=check_type
                    )
                    logger.info("Check notification sent", job_id=job_id, status=job.status)
                except Exception as e:
                    # Don't fail the check job if notification fails
                    logger.error("Failed to send check notification", job_id=job_id, error=str(e))

            logger.info("Check job completed", job_id=job_id, status=job.status)

        except Exception as e:
            logger.error("Check execution failed", job_id=job_id, error=str(e))
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()

            # Send failure notification
            try:
                duration_seconds = None
                if job.started_at and job.completed_at:
                    duration_seconds = int((job.completed_at - job.started_at).total_seconds())

                check_type = "scheduled" if job.scheduled_check else "manual"

                await NotificationService.send_check_completion(
                    db=db,
                    repository_name=repository.name if repository else "Unknown",
                    repository_path=repository.path if repository else "Unknown",
                    status="failed",
                    duration_seconds=duration_seconds,
                    error_message=str(e),
                    check_type=check_type
                )
                logger.info("Check failure notification sent", job_id=job_id)
            except Exception as notif_error:
                logger.error("Failed to send check failure notification", job_id=job_id, error=str(notif_error))
        finally:
            # Remove from running processes
            if job_id in self.running_processes:
                del self.running_processes[job_id]

            # Close the database session
            db.close()

# Global instance
check_service = CheckService()
