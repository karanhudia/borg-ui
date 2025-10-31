import asyncio
import structlog
import json
import os
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import Optional

from app.database.models import RestoreJob, Repository
from app.core.borg import borg
from app.database.database import SessionLocal

logger = structlog.get_logger()


class RestoreService:
    """Service for managing restore operations"""

    async def execute_restore(
        self,
        job_id: int,
        repository_path: str,
        archive_name: str,
        destination: str,
        paths: list = None
    ):
        """
        Execute a restore operation with progress tracking

        Args:
            job_id: ID of the RestoreJob record
            repository_path: Path to the borg repository
            archive_name: Name of the archive to restore
            destination: Destination path for restore
            paths: Optional list of specific paths to restore (empty for full restore)
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

            # Update job status to running
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db_session.commit()

            logger.info("Starting restore operation",
                       job_id=job_id,
                       repository=repository_path,
                       archive=archive_name,
                       destination=destination)

            # Build borg extract command with progress tracking
            cmd = ["borg", "extract", "--progress"]

            if repository and repository.remote_path:
                cmd.extend(["--remote-path", repository.remote_path])

            cmd.append(f"{repository_path}::{archive_name}")

            if paths:
                cmd.extend(paths)

            # Set up environment
            env = os.environ.copy()
            if repository and repository.passphrase:
                env["BORG_PASSPHRASE"] = repository.passphrase

            # Add SSH options
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR"
            ]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            logger.info("Executing restore command", command=" ".join(cmd))

            # Execute command with progress tracking
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=destination,
                env=env
            )

            # Track progress
            current_file = ""
            stdout_lines = []
            stderr_lines = []
            last_update_time = datetime.now(timezone.utc)
            seen_files = set()  # Track unique files
            nfiles = 0

            # Read stderr for progress (borg writes progress to stderr)
            # Borg uses \r for progress updates, we need to read raw bytes and split on \r
            async def read_stderr():
                nonlocal current_file, last_update_time, nfiles
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

                            # Parse progress from stderr
                            # Format: "XX.X% Extracting: filepath" with progress updates
                            try:
                                if "% Extracting:" in line_text:
                                    # Extract percentage and file path
                                    parts = line_text.split("% Extracting:", 1)
                                    if len(parts) == 2:
                                        try:
                                            percent = float(parts[0].strip())
                                            current_file = parts[1].strip()

                                            # Count unique files
                                            if current_file and current_file not in seen_files:
                                                seen_files.add(current_file)
                                                nfiles = len(seen_files)

                                            # Update job with percentage, file, and count
                                            job.progress_percent = percent
                                            job.current_file = current_file
                                            job.nfiles = nfiles

                                            # Commit every 2 seconds to reduce database load
                                            now = datetime.now(timezone.utc)
                                            if (now - last_update_time).total_seconds() >= 2.0:
                                                try:
                                                    db_session.commit()
                                                    last_update_time = now
                                                    logger.info("Progress update", job_id=job_id, percent=percent, nfiles=nfiles, file=current_file[:50] if current_file else '')
                                                except:
                                                    db_session.rollback()
                                        except ValueError:
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
                job.status = "completed"
                job.progress = 100
                job.progress_percent = 100.0
                job.completed_at = datetime.now(timezone.utc)
                job.logs = "\n".join(stderr_lines) if stderr_lines else "Restore completed successfully"

                logger.info("Restore completed successfully",
                           job_id=job_id,
                           repository=repository_path,
                           archive=archive_name)
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
            except Exception as update_error:
                logger.error("Failed to update job status", error=str(update_error))
        finally:
            db_session.close()


# Global instance
restore_service = RestoreService()
