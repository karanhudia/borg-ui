import asyncio
import structlog
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Optional
import shutil

from app.database.models import RestoreJob, Repository, SSHConnection, SSHKey
from app.core.borg import borg
from app.database.database import SessionLocal
from app.services.notification_service import notification_service

logger = structlog.get_logger()


class RestoreService:
    """Service for managing restore operations"""

    def __init__(self):
        self.running_processes = {}  # Track running restore processes by job_id

    async def execute_restore(
        self,
        job_id: int,
        repository_path: str,
        archive_name: str,
        destination: str,
        paths: list = None,
        repository_type: str = 'local',
        destination_type: str = 'local',
        destination_connection_id: Optional[int] = None,
        ssh_connection_id: Optional[int] = None
    ):
        """
        Execute a restore operation with progress tracking
        Routes to appropriate execution method based on repository and destination types

        Args:
            job_id: ID of the RestoreJob record
            repository_path: Path to the borg repository
            archive_name: Name of the archive to restore
            destination: Destination path for restore
            paths: Optional list of specific paths to restore (empty for full restore)
            repository_type: Type of repository ('local' or 'ssh')
            destination_type: Type of destination ('local' or 'ssh')
            destination_connection_id: SSH connection ID for SSH destinations
            ssh_connection_id: SSH connection ID for SSH repositories
        """
        # Determine execution mode and route to appropriate method
        execution_mode = f"{repository_type}_to_{destination_type}"

        logger.info("Routing restore operation",
                   job_id=job_id,
                   execution_mode=execution_mode,
                   repository_type=repository_type,
                   destination_type=destination_type)

        if execution_mode == "local_to_local":
            await self._execute_local_to_local(
                job_id, repository_path, archive_name, destination, paths
            )
        elif execution_mode == "ssh_to_local":
            await self._execute_ssh_to_local(
                job_id, repository_path, archive_name, destination, paths
            )
        elif execution_mode == "local_to_ssh":
            await self._execute_local_to_ssh(
                job_id, repository_path, archive_name, destination, paths, destination_connection_id
            )
        else:
            # This should never happen due to API validation, but handle it gracefully
            db_session = SessionLocal()
            try:
                job = db_session.query(RestoreJob).filter(RestoreJob.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_message = f"Unsupported execution mode: {execution_mode}"
                    job.completed_at = datetime.now(timezone.utc)
                    db_session.commit()
            finally:
                db_session.close()
            logger.error("Unsupported execution mode", execution_mode=execution_mode, job_id=job_id)

    async def _execute_local_to_local(
        self,
        job_id: int,
        repository_path: str,
        archive_name: str,
        destination: str,
        paths: list = None
    ):
        """
        Execute restore from local repository to local destination
        This is the original/existing implementation
        """
        # Create new database session
        db_session = SessionLocal()

        try:
            # Get job record
            job = db_session.query(RestoreJob).filter(RestoreJob.id == job_id).first()
            if not job:
                logger.error("Restore job not found", job_id=job_id)
                return

            # Get repository details for passphrase and remote_path
            repository = db_session.query(Repository).filter(Repository.path == repository_path).first()

            # Update job status to running - may fail if job was deleted after we queried it
            try:
                job.status = "running"
                job.started_at = datetime.now(timezone.utc)
                db_session.commit()
            except Exception as status_error:
                # Job was deleted while starting - exit gracefully
                logger.warning("Could not update job to running status (job may have been deleted)",
                              job_id=job_id, error=str(status_error))
                return

            logger.info("Starting restore operation",
                       job_id=job_id,
                       repository=repository_path,
                       archive=archive_name,
                       destination=destination,
                       paths=paths)

            # Ensure destination directory exists
            dest_path = Path(destination)
            if not dest_path.exists():
                try:
                    dest_path.mkdir(parents=True, exist_ok=True)
                    logger.info("Created destination directory", path=destination)
                except Exception as e:
                    logger.error("Failed to create destination directory", error=str(e))
                    job.status = "failed"
                    job.error_message = f"Failed to create destination directory: {str(e)}"
                    job.completed_at = datetime.now(timezone.utc)
                    db_session.commit()
                    return

            try:
                # Build borg extract command with progress tracking and JSON output
                cmd = ["borg", "extract", "--progress", "--log-json"]

                if repository and repository.remote_path:
                    cmd.extend(["--remote-path", repository.remote_path])

                if repository and repository.bypass_lock:
                    cmd.append("--bypass-lock")

                cmd.append(f"{repository_path}::{archive_name}")

                # Add paths if specified
                if paths:
                    cmd.extend(paths)

                # Set up environment
                env = os.environ.copy()
                if repository and repository.passphrase:
                    env["BORG_PASSPHRASE"] = repository.passphrase

                # Configure lock behavior to prevent timeout issues with SSH repositories
                # Wait up to 180 seconds (3 minutes) for locks instead of default 1 second
                env["BORG_LOCK_WAIT"] = "180"
                # Mark this container's hostname as unique to avoid lock conflicts
                env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

                # Add SSH options
                ssh_opts = [
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "LogLevel=ERROR"
                ]
                env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

                logger.info("Executing restore command", command=" ".join(cmd), cwd=destination)

                # Execute command with progress tracking
                # Extract directly to destination (no temp directory)
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,  # Pipe stdin so we can close it
                    cwd=destination,
                    env=env
                )
                
                # Close stdin immediately to prevent hanging on prompts
                if process.stdin:
                    process.stdin.close()

                # Track this process so it can be cancelled
                self.running_processes[job_id] = process

                # Track progress
                current_file = ""
                stdout_lines = []
                stderr_lines = []
                last_update_time = datetime.now(timezone.utc)
                seen_files = set()  # Track unique files
                nfiles = 0

                # Speed tracking: Moving average over 30-second window (same as backup jobs)
                speed_tracking = []  # List of (timestamp, restored_size) tuples
                SPEED_WINDOW_SECONDS = 30  # Calculate speed over last 30 seconds

                # Read stderr for progress (borg writes progress to stderr)
                # With --log-json, we get JSON progress messages
                async def read_stderr():
                    nonlocal current_file, last_update_time, nfiles, speed_tracking
                    buffer = b''

                    while True:
                        chunk = await process.stderr.read(8192)  # Read in chunks
                        if not chunk:
                            break

                        buffer += chunk

                        # Split on both \r and \n to handle progress updates
                        while b'\r' in buffer or b'\n' in buffer:
                            # Find the next separator
                            r_pos = buffer.find(b'\r')
                            n_pos = buffer.find(b'\n')

                            # Use whichever comes first
                            if r_pos == -1:
                                pos = n_pos
                                sep_len = 1
                            elif n_pos == -1:
                                pos = r_pos
                                sep_len = 1
                            else:
                                pos = min(r_pos, n_pos)
                                sep_len = 1

                            if pos == -1:
                                break

                            line_bytes = buffer[:pos]
                            buffer = buffer[pos + sep_len:]

                            if not line_bytes:
                                continue

                            line_text = line_bytes.decode('utf-8', errors='replace').strip()
                            if line_text:
                                stderr_lines.append(line_text)

                                # Parse JSON progress messages from stderr
                                try:
                                    # Check if line is JSON (starts with {)
                                    if line_text and line_text[0] == '{':
                                        json_msg = json.loads(line_text)
                                        msg_type = json_msg.get('type')

                                        # Parse progress_percent messages for restore progress
                                        if msg_type == 'progress_percent' and not json_msg.get('finished'):
                                            # Extract byte counts and current file
                                            restored_size = json_msg.get('current', 0)
                                            original_size = json_msg.get('total', 0)
                                            file_info = json_msg.get('info', [])
                                            current_file = file_info[0] if file_info else ""

                                            # Update job with size stats
                                            job.restored_size = restored_size
                                            job.original_size = original_size

                                            # Calculate progress percentage
                                            if original_size > 0:
                                                job.progress_percent = min(100.0, (restored_size / original_size) * 100.0)

                                            # Count unique files
                                            if current_file and current_file not in seen_files:
                                                seen_files.add(current_file)
                                                nfiles = len(seen_files)

                                            job.current_file = current_file
                                            job.nfiles = nfiles

                                            # Calculate restore speed using moving average (30-second window)
                                            if restored_size > 0:
                                                current_time = asyncio.get_event_loop().time()

                                                # Add current data point
                                                speed_tracking.append((current_time, restored_size))

                                                # Remove data points older than window
                                                speed_tracking[:] = [(t, s) for t, s in speed_tracking
                                                                   if current_time - t <= SPEED_WINDOW_SECONDS]

                                                # Calculate speed from moving average (need at least 2 data points)
                                                if len(speed_tracking) >= 2:
                                                    time_diff = speed_tracking[-1][0] - speed_tracking[0][0]
                                                    size_diff = speed_tracking[-1][1] - speed_tracking[0][1]

                                                    if time_diff > 0 and size_diff > 0:
                                                        # Speed in MB/s
                                                        job.restore_speed = (size_diff / (1024 * 1024)) / time_diff
                                                    elif time_diff > 0:
                                                        # No size change yet
                                                        job.restore_speed = 0.0

                                                    # Calculate estimated time remaining (in seconds)
                                                    remaining_bytes = original_size - restored_size
                                                    if remaining_bytes > 0 and job.restore_speed > 0:
                                                        # Speed is in MB/s, convert remaining bytes to MB
                                                        remaining_mb = remaining_bytes / (1024 * 1024)
                                                        job.estimated_time_remaining = int(remaining_mb / job.restore_speed)
                                                    else:
                                                        job.estimated_time_remaining = 0

                                            # Commit every 2 seconds to reduce database load
                                            now = datetime.now(timezone.utc)
                                            if (now - last_update_time).total_seconds() >= 2.0:
                                                try:
                                                    db_session.commit()
                                                    last_update_time = now
                                                    logger.info("Restore progress update",
                                                              job_id=job_id,
                                                              percent=job.progress_percent,
                                                              nfiles=nfiles,
                                                              speed_mb_s=job.restore_speed,
                                                              eta_seconds=job.estimated_time_remaining,
                                                              file=current_file[:50] if current_file else '')
                                                except:
                                                    db_session.rollback()
                                except json.JSONDecodeError:
                                    # Not JSON, ignore (might be non-JSON log messages)
                                    pass
                                except Exception as e:
                                    logger.debug("Failed to parse progress line", line=line_text[:100], error=str(e))

                # Read stdout for any output
                async def read_stdout():
                    async for line in process.stdout:
                        stdout_lines.append(line.decode().strip())

                # Wait for both streams and process completion
                await asyncio.gather(read_stderr(), read_stdout())
                await process.wait()

                # Final update
                if current_file:
                    job.current_file = current_file

                # Update job with results
                if process.returncode == 0:
                    # Extraction completed successfully (directly to destination)
                    job.status = "completed"
                    job.progress = 100
                    job.progress_percent = 100.0
                    job.completed_at = datetime.now(timezone.utc)
                    job.logs = "\n".join(stderr_lines) if stderr_lines else "Restore completed successfully"

                    logger.info("Restore completed successfully",
                               job_id=job_id,
                               repository=repository_path,
                               archive=archive_name,
                               destination=destination,
                               nfiles=nfiles)

                    # Send success notification
                    try:
                        await notification_service.send_restore_success(
                            db_session, repository_path, archive_name, destination, None, None
                        )
                    except Exception as e:
                        logger.warning("Failed to send restore success notification", error=str(e))
                elif process.returncode == 1 or (100 <= process.returncode <= 127):
                    # Exit code 1 or 100-127 can be warnings OR errors
                    # If no files were restored, treat as failure (likely permission/path error)
                    stderr_output = "\n".join(stderr_lines)

                    if nfiles == 0:
                        # No files restored - this is a failure, not a warning
                        job.status = "failed"

                        # Try to extract meaningful error from stderr
                        error_hint = "Check logs for details."
                        if "permission denied" in stderr_output.lower():
                            error_hint = "Permission denied - you may need root access or different destination path."
                        elif "no such file" in stderr_output.lower():
                            error_hint = "Path not found in archive or destination doesn't exist."
                        elif not stderr_output.strip():
                            error_hint = "No error output from borg. Files may not exist in archive or permission denied."

                        job.error_message = f"Restore failed: 0 files extracted (exit code {process.returncode}). {error_hint}"
                        job.completed_at = datetime.now(timezone.utc)
                        job.logs = f"STDOUT:\n{chr(10).join(stdout_lines) if stdout_lines else '(no output)'}\n\nSTDERR:\n{stderr_output if stderr_output else '(no output)'}"

                        logger.error("Restore failed - no files extracted",
                                   job_id=job_id,
                                   repository=repository_path,
                                   archive=archive_name,
                                   destination=destination,
                                   exit_code=process.returncode,
                                   nfiles=nfiles)

                        # Send failure notification
                        try:
                            await notification_service.send_restore_failure(
                                db_session, repository_path, archive_name,
                                f"0 files restored. Exit code {process.returncode}. Likely permission or path error.",
                                None
                            )
                        except Exception as e:
                            logger.warning("Failed to send restore failure notification", error=str(e))
                    else:
                        # Files were restored, but with warnings
                        job.status = "completed_with_warnings"
                        job.progress = 100
                        job.progress_percent = 100.0
                        job.completed_at = datetime.now(timezone.utc)
                        job.error_message = f"Restore completed with warnings (exit code {process.returncode})"
                        job.logs = f"STDOUT:\n{chr(10).join(stdout_lines)}\n\nSTDERR:\n{stderr_output}"

                        logger.warning("Restore completed with warnings",
                                   job_id=job_id,
                                   repository=repository_path,
                                   archive=archive_name,
                                   destination=destination,
                                   exit_code=process.returncode,
                                   nfiles=nfiles)

                        # Send warning notification (use success notification with note about warnings)
                        try:
                            await notification_service.send_restore_success(
                                db_session, repository_path, archive_name, destination, None, None
                            )
                        except Exception as e:
                            logger.warning("Failed to send restore warning notification", error=str(e))
                else:
                    job.status = "failed"
                    stderr_output = "\n".join(stderr_lines)
                    job.error_message = stderr_output or f"Process exited with code {process.returncode}"
                    job.completed_at = datetime.now(timezone.utc)
                    job.logs = f"STDOUT:\n{chr(10).join(stdout_lines)}\n\nSTDERR:\n{stderr_output}"

                    logger.error("Restore failed",
                                job_id=job_id,
                                return_code=process.returncode,
                            error=stderr_output)

                    # Send failure notification
                    try:
                        await notification_service.send_restore_failure(
                            db_session, repository_path, archive_name, job.error_message, None
                        )
                    except Exception as e:
                        logger.warning("Failed to send restore failure notification", error=str(e))

                db_session.commit()

            except Exception as e:
                # Handle any unexpected errors during extraction
                logger.error("Unexpected error during extraction", job_id=job_id, error=str(e))
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)
                db_session.commit()

        except Exception as e:
            logger.error("Restore execution failed",
                        job_id=job_id,
                        error=str(e))

            # Update job status to failed
            try:
                job = db_session.query(RestoreJob).filter(RestoreJob.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_message = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    db_session.commit()

                    # Send failure notification
                    try:
                        await notification_service.send_restore_failure(
                            db_session, repository_path, archive_name, str(e), None
                        )
                    except Exception as notif_error:
                        logger.warning("Failed to send restore failure notification", error=str(notif_error))
                else:
                    logger.warning("Could not update job status - job was deleted during execution", job_id=job_id)
            except Exception as update_error:
                # Job may have been deleted while running - that's okay
                logger.warning("Could not update job status (job may have been deleted during execution)",
                              job_id=job_id, error=str(update_error))
                db_session.rollback()
        finally:
            # Remove from running processes
            if job_id in self.running_processes:
                del self.running_processes[job_id]
                logger.debug("Removed restore process from tracking", job_id=job_id)

            db_session.close()

    async def cancel_restore(self, job_id: int) -> bool:
        """
        Cancel a running restore job by terminating its process

        Args:
            job_id: The restore job ID to cancel

        Returns:
            True if the process was found and terminated, False otherwise
        """
        if job_id not in self.running_processes:
            logger.warning("No running process found for job", job_id=job_id)
            return False

        process = self.running_processes[job_id]

        try:
            # Try to terminate the process gracefully first
            process.terminate()
            logger.info("Sent SIGTERM to restore process", job_id=job_id, pid=process.pid)

            # Wait up to 5 seconds for graceful termination
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
                logger.info("Restore process terminated gracefully", job_id=job_id)
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate gracefully
                process.kill()
                logger.warning("Force killed restore process (SIGKILL)", job_id=job_id, pid=process.pid)
                await process.wait()

            return True
        except Exception as e:
            logger.error("Failed to cancel restore process", job_id=job_id, error=str(e))
            return False

    async def _execute_ssh_to_local(
        self,
        job_id: int,
        repository_path: str,
        archive_name: str,
        destination: str,
        paths: list = None
    ):
        """
        Execute restore from SSH repository to local destination
        Uses borg's native SSH repository support
        Similar to local_to_local but repository is on remote server
        """
        # This is essentially the same as local_to_local since borg handles SSH repos natively
        # The repository_path should already be in SSH URL format (ssh://user@host/path)
        await self._execute_local_to_local(job_id, repository_path, archive_name, destination, paths)

    async def _execute_local_to_ssh(
        self,
        job_id: int,
        repository_path: str,
        archive_name: str,
        destination: str,
        paths: list = None,
        destination_connection_id: int = None
    ):
        """
        Execute restore from local repository to SSH destination
        Two-phase approach:
        1. Extract to temporary directory (0-80% progress)
        2. Transfer to remote via rsync (80-100% progress)
        """
        db_session = SessionLocal()
        temp_path = None

        try:
            # Get job record
            job = db_session.query(RestoreJob).filter(RestoreJob.id == job_id).first()
            if not job:
                logger.error("Restore job not found", job_id=job_id)
                return

            # Get repository details
            repository = db_session.query(Repository).filter(Repository.path == repository_path).first()

            # Get SSH connection details
            if not destination_connection_id:
                raise ValueError("SSH destination requires destination_connection_id")

            ssh_connection = db_session.query(SSHConnection).filter(
                SSHConnection.id == destination_connection_id
            ).first()
            if not ssh_connection:
                raise ValueError(f"SSH connection {destination_connection_id} not found")

            # Update job status to running
            try:
                job.status = "running"
                job.started_at = datetime.now(timezone.utc)
                db_session.commit()
            except Exception as status_error:
                logger.warning("Could not update job to running status", job_id=job_id, error=str(status_error))
                return

            logger.info("Starting local→SSH restore (two-phase)",
                       job_id=job_id,
                       repository=repository_path,
                       archive=archive_name,
                       ssh_destination=f"{ssh_connection.username}@{ssh_connection.host}:{destination}")

            # ===== PHASE 1: Extract to temporary directory (0-80%) =====
            temp_path = f"/tmp/restore_{job_id}"
            os.makedirs(temp_path, exist_ok=True)

            # Store temp path in job for cleanup
            job.temp_extraction_path = temp_path
            db_session.commit()

            logger.info("Phase 1: Extracting to temporary directory", temp_path=temp_path)

            # Build borg extract command
            cmd = ["borg", "extract", "--progress", "--log-json"]

            if repository and repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])

            if repository and repository.bypass_lock:
                cmd.append("--bypass-lock")

            cmd.append(f"{repository_path}::{archive_name}")

            if paths:
                cmd.extend(paths)

            # Set up environment
            env = os.environ.copy()
            if repository and repository.passphrase:
                env["BORG_PASSPHRASE"] = repository.passphrase

            env["BORG_LOCK_WAIT"] = "180"
            env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

            ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR"]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            logger.info("Executing extraction command", command=" ".join(cmd), cwd=temp_path)

            # Execute extraction
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                cwd=temp_path,
                env=env
            )

            if process.stdin:
                process.stdin.close()

            self.running_processes[job_id] = process

            # Track extraction progress (map to 0-80%)
            current_file = ""
            stderr_lines = []
            last_update_time = datetime.now(timezone.utc)
            seen_files = set()
            nfiles = 0
            speed_tracking = []
            SPEED_WINDOW_SECONDS = 30

            async def read_stderr():
                nonlocal current_file, last_update_time, nfiles, speed_tracking
                buffer = b''

                while True:
                    chunk = await process.stderr.read(8192)
                    if not chunk:
                        break

                    buffer += chunk

                    while b'\r' in buffer or b'\n' in buffer:
                        r_pos = buffer.find(b'\r')
                        n_pos = buffer.find(b'\n')

                        if r_pos == -1:
                            pos = n_pos
                            sep_len = 1
                        elif n_pos == -1:
                            pos = r_pos
                            sep_len = 1
                        else:
                            pos = min(r_pos, n_pos)
                            sep_len = 1

                        if pos == -1:
                            break

                        line_bytes = buffer[:pos]
                        buffer = buffer[pos + sep_len:]

                        if not line_bytes:
                            continue

                        line_text = line_bytes.decode('utf-8', errors='replace').strip()
                        if line_text:
                            stderr_lines.append(line_text)

                            try:
                                if line_text and line_text[0] == '{':
                                    json_msg = json.loads(line_text)
                                    msg_type = json_msg.get('type')

                                    if msg_type == 'progress_percent' and not json_msg.get('finished'):
                                        restored_size = json_msg.get('current', 0)
                                        original_size = json_msg.get('total', 0)
                                        file_info = json_msg.get('info', [])
                                        current_file = file_info[0] if file_info else ""

                                        job.restored_size = restored_size
                                        job.original_size = original_size

                                        # Map extraction progress to 0-80%
                                        if original_size > 0:
                                            extraction_percent = min(100.0, (restored_size / original_size) * 100.0)
                                            job.progress_percent = extraction_percent * 0.8  # Scale to 0-80%

                                        if current_file and current_file not in seen_files:
                                            seen_files.add(current_file)
                                            nfiles = len(seen_files)

                                        job.current_file = f"Extracting: {current_file}"
                                        job.nfiles = nfiles

                                        # Calculate speed
                                        if restored_size > 0:
                                            current_time = asyncio.get_event_loop().time()
                                            speed_tracking.append((current_time, restored_size))
                                            speed_tracking[:] = [(t, s) for t, s in speed_tracking
                                                               if current_time - t <= SPEED_WINDOW_SECONDS]

                                            if len(speed_tracking) >= 2:
                                                time_diff = speed_tracking[-1][0] - speed_tracking[0][0]
                                                size_diff = speed_tracking[-1][1] - speed_tracking[0][1]

                                                if time_diff > 0 and size_diff > 0:
                                                    job.restore_speed = (size_diff / (1024 * 1024)) / time_diff

                                                remaining_bytes = original_size - restored_size
                                                if remaining_bytes > 0 and job.restore_speed > 0:
                                                    remaining_mb = remaining_bytes / (1024 * 1024)
                                                    job.estimated_time_remaining = int(remaining_mb / job.restore_speed)
                                                else:
                                                    job.estimated_time_remaining = 0

                                        now = datetime.now(timezone.utc)
                                        if (now - last_update_time).total_seconds() >= 2.0:
                                            try:
                                                db_session.commit()
                                                last_update_time = now
                                                logger.info("Phase 1 progress",
                                                          job_id=job_id,
                                                          percent=job.progress_percent,
                                                          file=current_file[:50] if current_file else '')
                                            except:
                                                db_session.rollback()
                            except (json.JSONDecodeError, Exception) as e:
                                pass

            async def read_stdout():
                async for line in process.stdout:
                    pass  # Discard stdout

            await asyncio.gather(read_stderr(), read_stdout())
            await process.wait()

            # Exit code 1 = success with warnings (e.g., xattr warnings on non-macOS systems)
            # Exit codes 100-127 = partial success
            if process.returncode == 0 or process.returncode == 1 or (100 <= process.returncode <= 127):
                if process.returncode == 1:
                    # Extract only warning/error messages (not JSON progress)
                    warning_msgs = [
                        line for line in stderr_lines
                        if not line.strip().startswith('{') and line.strip()
                    ]
                    if warning_msgs:
                        logger.warning(
                            "Phase 1 completed with warnings",
                            temp_path=temp_path,
                            nfiles=nfiles,
                            warnings=warning_msgs[-5:]  # Last 5 warnings
                        )
                logger.info("Phase 1 completed: Extraction successful", temp_path=temp_path, nfiles=nfiles)
            else:
                # Extract only error messages (not JSON progress)
                error_msgs = [
                    line for line in stderr_lines
                    if not line.strip().startswith('{') and line.strip()
                ]
                raise Exception(f"Extraction failed with code {process.returncode}: {' '.join(error_msgs[-10:])}")

            # Update progress to 80% before starting transfer
            job.progress_percent = 80.0
            job.current_file = "Preparing transfer to remote server..."
            db_session.commit()

            # ===== PHASE 2: Transfer to remote via rsync (80-100%) =====
            logger.info("Phase 2: Transferring to remote server")

            # Get SSH key
            ssh_key = db_session.query(SSHKey).filter(SSHKey.id == ssh_connection.ssh_key_id).first()
            if not ssh_key:
                raise Exception(f"SSH key {ssh_connection.ssh_key_id} not found")

            # Create temporary SSH key file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as key_file:
                key_file.write(ssh_key.private_key)
                key_file_path = key_file.name

            os.chmod(key_file_path, 0o600)

            try:
                # Build rsync command
                rsync_cmd = [
                    "rsync",
                    "-avz",
                    "--progress",
                    "-e", f"ssh -i {key_file_path} -p {ssh_connection.port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
                    f"{temp_path}/",  # Source (trailing slash = contents of directory)
                    f"{ssh_connection.username}@{ssh_connection.host}:{destination}/"  # Destination
                ]

                logger.info("Executing rsync transfer", command=" ".join(rsync_cmd))

                # Execute rsync
                rsync_process = await asyncio.create_subprocess_exec(
                    *rsync_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                self.running_processes[job_id] = rsync_process

                # Track rsync progress (map to 80-100%)
                rsync_stderr_lines = []
                rsync_stdout_lines = []

                async def read_rsync_output():
                    # rsync outputs progress to stdout
                    async for line in rsync_process.stdout:
                        line_str = line.decode('utf-8', errors='replace').strip()
                        rsync_stdout_lines.append(line_str)

                        # Try to parse rsync progress (format: "  1,234,567  12%  123.45kB/s    0:00:12")
                        # This is basic parsing - rsync progress is not as structured as borg's
                        if '%' in line_str:
                            try:
                                parts = line_str.split()
                                for part in parts:
                                    if part.endswith('%'):
                                        percent_str = part.replace('%', '')
                                        rsync_percent = float(percent_str)
                                        # Map rsync 0-100% to overall 80-100%
                                        job.progress_percent = 80.0 + (rsync_percent * 0.2)
                                        job.current_file = f"Transferring files: {rsync_percent:.0f}%"
                                        db_session.commit()
                                        logger.info("Phase 2 progress",
                                                  job_id=job_id,
                                                  overall_percent=job.progress_percent,
                                                  rsync_percent=rsync_percent)
                                        break
                            except:
                                pass

                async def read_rsync_stderr():
                    async for line in rsync_process.stderr:
                        line_str = line.decode('utf-8', errors='replace').strip()
                        rsync_stderr_lines.append(line_str)

                await asyncio.gather(read_rsync_output(), read_rsync_stderr())
                await rsync_process.wait()

                if rsync_process.returncode != 0:
                    raise Exception(f"Transfer failed with code {rsync_process.returncode}: {' '.join(rsync_stderr_lines[-10:])}")

                logger.info("Phase 2 completed: Transfer successful")

                # Mark as completed
                job.status = "completed"
                job.progress = 100
                job.progress_percent = 100.0
                job.completed_at = datetime.now(timezone.utc)
                job.current_file = "Restore completed"
                job.logs = f"Extraction:\n{chr(10).join(stderr_lines[-50:])}\n\nTransfer:\n{chr(10).join(rsync_stdout_lines[-50:])}"
                db_session.commit()

                logger.info("Local→SSH restore completed successfully",
                           job_id=job_id,
                           repository=repository_path,
                           archive=archive_name,
                           destination=f"{ssh_connection.host}:{destination}")

                # Send success notification
                try:
                    await notification_service.send_restore_success(
                        db_session, repository_path, archive_name,
                        f"{ssh_connection.host}:{destination}", None, None
                    )
                except Exception as e:
                    logger.warning("Failed to send restore success notification", error=str(e))

            finally:
                # Clean up SSH key file
                try:
                    os.unlink(key_file_path)
                except Exception as e:
                    logger.warning("Failed to delete temporary key file", error=str(e))

        except Exception as e:
            logger.error("Local→SSH restore failed", job_id=job_id, error=str(e))

            try:
                job = db_session.query(RestoreJob).filter(RestoreJob.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_message = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    db_session.commit()

                    # Send failure notification
                    try:
                        await notification_service.send_restore_failure(
                            db_session, repository_path, archive_name, str(e), None
                        )
                    except Exception as notif_error:
                        logger.warning("Failed to send restore failure notification", error=str(notif_error))
            except Exception as update_error:
                logger.warning("Could not update job status", job_id=job_id, error=str(update_error))
                db_session.rollback()

        finally:
            # Clean up temporary directory
            if temp_path and os.path.exists(temp_path):
                try:
                    shutil.rmtree(temp_path)
                    logger.info("Cleaned up temporary directory", path=temp_path)
                except Exception as e:
                    logger.warning("Failed to clean up temporary directory", path=temp_path, error=str(e))

            # Remove from running processes
            if job_id in self.running_processes:
                del self.running_processes[job_id]

            db_session.close()


# Global instance
restore_service = RestoreService()
