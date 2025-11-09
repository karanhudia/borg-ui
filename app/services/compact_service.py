import asyncio
import os
import re
import json
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import CompactJob, Repository
from app.database.database import SessionLocal
from app.config import settings

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

class CompactService:
    """Service for executing repository compact operations with real-time progress tracking"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running processes by job_id

    async def execute_compact(self, job_id: int, repository_id: int, db: Session = None):
        """Execute repository compact operation with progress tracking"""

        # Create a new database session for this background task
        db = SessionLocal()

        try:
            # Get job
            job = db.query(CompactJob).filter(CompactJob.id == job_id).first()
            if not job:
                logger.error("Compact job not found", job_id=job_id)
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

            # Add SSH options for remote repos
            # Add SSH options for remote repos with keepalive for orphan prevention
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR",
                "-o", "ServerAliveInterval=15",   # Send keepalive every 15s
                "-o", "ServerAliveCountMax=3",    # Give up after 3 failures (~45s)
                "-o", "TCPKeepAlive=yes"          # Enable TCP-level keepalives
            ]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            # Build command
            cmd = ["borg", "compact", "--progress", "--log-json"]
            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])
            cmd.append(repository.path)

            logger.info("Starting borg compact", job_id=job_id, repository=repository.path, command=" ".join(cmd))

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
                        logger.info("Compact job cancelled, terminating process", job_id=job_id)
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

                        # Parse JSON progress messages (similar to check_service.py)
                        try:
                            if line_str and line_str[0] == '{':
                                json_msg = json.loads(line_str)
                                msg_type = json_msg.get('type')

                                # Parse progress_percent messages for compact operations
                                if msg_type == 'progress_percent':
                                    message = json_msg.get('message', '')
                                    finished = json_msg.get('finished', False)
                                    current = json_msg.get('current', 0)
                                    total = json_msg.get('total', 1)

                                    # Build progress message with operation counts when available
                                    # Skip appending counts when message is empty (phase transitions)
                                    if message:
                                        job.progress_message = f"{message} ({current}/{total})"
                                    # Don't update progress_message when message is empty (keeps last good message)

                                    if not finished:
                                        # Extract percentage from current/total
                                        if total > 0:
                                            percentage = (current / total) * 100
                                            job.progress = int(percentage)

                                        # Batched commit
                                        current_time = asyncio.get_event_loop().time()
                                        if current_time - last_commit_time >= COMMIT_INTERVAL:
                                            db.commit()
                                            last_commit_time = current_time
                                            logger.info("Compact progress committed to DB",
                                                       job_id=job_id,
                                                       progress=job.progress,
                                                       message=message)
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
            elif process.returncode == 0:
                job.status = "completed"
                job.progress = 100
                job.progress_message = "Compact completed successfully"
                job.completed_at = datetime.utcnow()
                # Update repository's last_compact timestamp
                repository.last_compact = datetime.utcnow()
                logger.info("Compact completed successfully", job_id=job_id)
            else:
                job.status = "failed"
                job.error_message = f"Compact failed with exit code {process.returncode}"
                job.completed_at = datetime.utcnow()
                logger.error("Compact failed", job_id=job_id, exit_code=process.returncode)

            # Save logs if failed or cancelled
            if job.status in ['failed', 'cancelled']:
                log_file = self.log_dir / f"compact_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                try:
                    log_file.write_text('\n'.join(log_buffer))
                    job.logs = f"Logs saved to: {log_file.name}"
                    logger.warning("Compact logs saved for debugging",
                                 job_id=job_id,
                                 log_file=str(log_file))
                except Exception as e:
                    job.logs = f"Failed to save logs: {str(e)}"
                    logger.error("Failed to save log buffer", job_id=job_id, error=str(e))

            db.commit()
            logger.info("Compact job completed", job_id=job_id, status=job.status)

        except Exception as e:
            logger.error("Compact execution failed", job_id=job_id, error=str(e))
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
compact_service = CompactService()
