import asyncio
import os
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import DeleteArchiveJob, Repository
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

class DeleteArchiveService:
    """Service for executing archive delete operations with real-time progress tracking"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running processes by job_id

    async def execute_delete(self, job_id: int, repository_id: int, archive_name: str, db: Session = None):
        """Execute archive delete operation with progress tracking"""

        # Create a new database session for this background task
        db = SessionLocal()

        try:
            # Get job
            job = db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
            if not job:
                logger.error("Delete archive job not found", job_id=job_id)
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
            job.progress_message = "Starting archive deletion"
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

            # Build command
            cmd = ["borg", "delete", "--stats", "--progress"]
            if repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])
            cmd.append(f"{repository.path}::{archive_name}")

            logger.info("Starting borg delete", job_id=job_id, repository=repository.path, archive=archive_name, command=" ".join(cmd))

            # Execute command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            # Store PID and start time for orphan detection
            job.process_pid = process.pid
            job.process_start_time = get_process_start_time(process.pid)
            job.progress = 50  # Deletion in progress
            job.progress_message = f"Deleting archive {archive_name}"
            db.commit()

            logger.info("Stored PID tracking info",
                       job_id=job_id,
                       pid=job.process_pid,
                       start_time=job.process_start_time)

            # Track this process so it can be cancelled
            self.running_processes[job_id] = process

            # Flag to track cancellation
            cancelled = False

            # In-memory log buffer
            log_buffer = []

            async def check_cancellation():
                """Periodic heartbeat to check for cancellation"""
                nonlocal cancelled
                while not cancelled and process.returncode is None:
                    await asyncio.sleep(3)
                    db.refresh(job)
                    if job.status == "cancelled":
                        logger.info("Delete job cancelled, terminating process", job_id=job_id)
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
                    async for line in process.stderr:
                        if cancelled:
                            break

                        line_str = line.decode('utf-8', errors='replace').strip()
                        if line_str:
                            log_buffer.append(line_str)

                except Exception as e:
                    logger.error("Error reading process output", error=str(e))

            # Start both tasks
            cancellation_task = asyncio.create_task(check_cancellation())
            log_task = asyncio.create_task(stream_logs())

            # Wait for process to complete
            await process.wait()

            # Cancel background tasks
            cancellation_task.cancel()
            log_task.cancel()

            # Clean up process tracking
            self.running_processes.pop(job_id, None)

            # Handle process completion
            if cancelled:
                job.status = "cancelled"
                job.progress_message = "Archive deletion cancelled"
                logger.info("Delete job cancelled", job_id=job_id)
            elif process.returncode == 0:
                job.status = "completed"
                job.progress = 100
                job.progress_message = f"Archive {archive_name} deleted successfully"
                logger.info("Delete job completed", job_id=job_id)
            elif process.returncode == 1 or (100 <= process.returncode <= 127):
                # Warning (legacy exit code 1 or modern exit codes 100-127)
                job.status = "completed_with_warnings"
                job.progress = 100
                job.progress_message = f"Archive {archive_name} deleted with warnings (exit code {process.returncode})"
                job.error_message = f"Archive deletion completed with warnings (exit code {process.returncode})"
                if log_buffer:
                    job.error_message += "\n\n" + "\n".join(log_buffer[-50:])  # Last 50 lines
                logger.warning("Delete job completed with warnings", job_id=job_id, exit_code=process.returncode)
            else:
                job.status = "failed"
                job.progress_message = "Archive deletion failed"
                # Capture error from stderr
                if log_buffer:
                    job.error_message = "\n".join(log_buffer[-50:])  # Last 50 lines
                logger.error("Delete job failed", job_id=job_id, return_code=process.returncode)

            # Save logs
            if log_buffer:
                log_file_path = self.log_dir / f"delete_archive_{job_id}.log"
                with open(log_file_path, 'w') as f:
                    f.write("\n".join(log_buffer))
                job.log_file_path = str(log_file_path)
                job.has_logs = True

            job.completed_at = datetime.utcnow()
            db.commit()

            logger.info("Delete job finished", job_id=job_id, status=job.status)

        except Exception as e:
            logger.error("Failed to execute delete job", job_id=job_id, error=str(e))
            try:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.commit()
            except:
                pass
        finally:
            db.close()

    async def cancel_delete(self, job_id: int, db: Session):
        """Cancel a running delete job"""
        job = db.query(DeleteArchiveJob).filter(DeleteArchiveJob.id == job_id).first()
        if not job:
            raise ValueError(f"Delete job {job_id} not found")

        if job.status != "running":
            raise ValueError(f"Delete job {job_id} is not running (status: {job.status})")

        # Mark as cancelled in database
        job.status = "cancelled"
        db.commit()

        logger.info("Delete job marked for cancellation", job_id=job_id)

# Global service instance
delete_archive_service = DeleteArchiveService()
