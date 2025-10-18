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
from app.core.borg_errors import format_error_message, get_error_details

logger = structlog.get_logger()

class BackupService:
    """Service for executing backups with real-time log streaming"""

    def __init__(self):
        self.log_dir = Path("/data/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running backup processes by job_id
        self.error_msgids = {}  # Track error message IDs by job_id

    async def _update_repository_stats(self, db: Session, repository_path: str, env: dict):
        """Update repository statistics after a successful backup"""
        try:
            repo_record = db.query(Repository).filter(Repository.path == repository_path).first()
            if not repo_record:
                logger.warning("Repository record not found for stats update", repository=repository_path)
                return

            # Get archive count using borg list --json
            list_cmd = ["borg", "list", "--json", repository_path]
            list_process = await asyncio.create_subprocess_exec(
                *list_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            list_stdout, list_stderr = await asyncio.wait_for(list_process.communicate(), timeout=30)

            if list_process.returncode == 0:
                try:
                    archives_data = json.loads(list_stdout.decode())
                    archive_count = len(archives_data.get("archives", []))
                    repo_record.archive_count = archive_count
                    logger.info("Updated archive count", repository=repository_path, count=archive_count)
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse borg list output", error=str(e))

            # Get repository info using borg info --json
            info_cmd = ["borg", "info", "--json", repository_path]
            info_process = await asyncio.create_subprocess_exec(
                *info_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            info_stdout, info_stderr = await asyncio.wait_for(info_process.communicate(), timeout=30)

            if info_process.returncode == 0:
                try:
                    info_data = json.loads(info_stdout.decode())
                    cache_stats = info_data.get("cache", {}).get("stats", {})

                    # Get total repository size (unique_size is deduplicated size)
                    unique_size = cache_stats.get("unique_size", 0)
                    if unique_size > 0:
                        # Format size to human readable
                        repo_record.total_size = self._format_bytes(unique_size)
                        logger.info("Updated repository size", repository=repository_path, size=repo_record.total_size)
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse borg info output", error=str(e))

            # Update last_backup timestamp
            repo_record.last_backup = datetime.utcnow()

            db.commit()
            logger.info("Repository statistics updated", repository=repository_path)

        except asyncio.TimeoutError:
            logger.warning("Timeout while updating repository stats", repository=repository_path)
        except Exception as e:
            logger.error("Failed to update repository stats", repository=repository_path, error=str(e))

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"

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

            # Add SSH options to disable host key checking for remote repos
            # This allows automatic connection to new hosts without manual intervention
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",  # Don't check host keys
                "-o", "UserKnownHostsFile=/dev/null",  # Don't save host keys
                "-o", "LogLevel=ERROR"  # Reduce SSH verbosity
            ]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            # Look up repository record to get passphrase, source directories, and exclude patterns
            source_paths = ["/data"]  # Default backup path
            exclude_patterns = []  # Default no exclusions
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

                    # Parse exclude patterns from JSON if available
                    if repo_record.exclude_patterns:
                        try:
                            patterns = json.loads(repo_record.exclude_patterns)
                            if patterns and isinstance(patterns, list) and len(patterns) > 0:
                                exclude_patterns = patterns
                                logger.info("Using exclude patterns from repository",
                                          repository=repository,
                                          exclude_patterns=exclude_patterns)
                        except json.JSONDecodeError as e:
                            logger.warning("Could not parse exclude_patterns JSON",
                                         repository=repository, error=str(e))
                else:
                    logger.warning("Repository record not found, using defaults", repository=repository)
            except Exception as e:
                logger.warning("Could not look up repository record", error=str(e))

            # Build command with source directories and exclude patterns
            cmd = [
                "borg", "create",
                "--progress",
                "--stats",
                "--list",
                "--show-rc",  # Show return code for better debugging
                "--log-json",  # Structured JSON logging
                "--compression", "lz4",
            ]

            # Add exclude patterns
            for pattern in exclude_patterns:
                cmd.extend(["--exclude", pattern])

            # Add repository::archive
            cmd.append(f"{repository}::{archive_name}")

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

                # Track this process so it can be cancelled
                self.running_processes[job_id] = process

                # Flag to track cancellation
                cancelled = False

                async def check_cancellation():
                    """Periodic heartbeat to check for cancellation independent of log output"""
                    nonlocal cancelled
                    while not cancelled and process.returncode is None:
                        await asyncio.sleep(1)  # Check every second
                        db.refresh(job)
                        if job.status == "cancelled":
                            logger.info("Backup job cancelled (heartbeat), terminating process", job_id=job_id)
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
                    """Stream log output from process and parse JSON progress"""
                    nonlocal cancelled
                    try:
                        async for line in process.stdout:
                            if cancelled:
                                break

                            line_str = line.decode('utf-8', errors='replace').strip()
                            timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                            log_line = f"[{timestamp}] {line_str}\n"
                            f.write(log_line)
                            f.flush()  # Force write to disk immediately

                            # Try to parse JSON progress messages
                            try:
                                if line_str.startswith('{') and line_str.endswith('}'):
                                    json_msg = json.loads(line_str)
                                    msg_type = json_msg.get('type')

                                    # Parse archive_progress messages for real-time stats
                                    if msg_type == 'archive_progress':
                                        job.original_size = json_msg.get('original_size', 0)
                                        job.compressed_size = json_msg.get('compressed_size', 0)
                                        job.deduplicated_size = json_msg.get('deduplicated_size', 0)
                                        job.nfiles = json_msg.get('nfiles', 0)
                                        job.current_file = json_msg.get('path', '')
                                        db.commit()
                                        logger.debug("Updated progress from archive_progress",
                                                   job_id=job_id,
                                                   nfiles=job.nfiles,
                                                   current_file=job.current_file)

                                    # Parse progress_percent messages for percentage
                                    elif msg_type == 'progress_percent':
                                        finished = json_msg.get('finished', False)
                                        if finished:
                                            job.progress_percent = 100
                                            job.progress = 100
                                        else:
                                            current = json_msg.get('current', 0)
                                            total = json_msg.get('total', 1)
                                            if total > 0:
                                                progress_value = int((current / total) * 100)
                                                job.progress_percent = progress_value
                                                job.progress = progress_value
                                        db.commit()
                                        logger.debug("Updated progress percent",
                                                   job_id=job_id,
                                                   percent=job.progress_percent)

                                    # Parse file_status messages for current file
                                    elif msg_type == 'file_status':
                                        status = json_msg.get('status', '')
                                        path = json_msg.get('path', '')
                                        if path:
                                            job.current_file = f"[{status}] {path}"
                                            db.commit()

                                    # Parse log_message for errors with msgid
                                    elif msg_type == 'log_message':
                                        levelname = json_msg.get('levelname', '')
                                        message = json_msg.get('message', '')
                                        msgid = json_msg.get('msgid', '')
                                        if levelname in ['ERROR', 'CRITICAL'] and msgid:
                                            # Store error msgid for later use
                                            if job_id not in self.error_msgids:
                                                self.error_msgids[job_id] = []
                                            self.error_msgids[job_id].append({
                                                'msgid': msgid,
                                                'message': message,
                                                'levelname': levelname
                                            })
                                            logger.error("Borg error detected",
                                                       job_id=job_id,
                                                       msgid=msgid,
                                                       message=message)

                            except json.JSONDecodeError:
                                # Not a JSON line, just regular log output
                                pass
                            except Exception as e:
                                logger.warning("Failed to parse JSON progress",
                                             job_id=job_id,
                                             error=str(e),
                                             line=line_str[:100])

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
                    logger.info("Backup task cancelled", job_id=job_id)
                    cancelled = True
                    process.terminate()
                    await process.wait()
                    raise

                # Wait for process to complete if not already terminated
                if process.returncode is None:
                    await process.wait()

                # Update job status using modern exit codes (if not already cancelled)
                # 0 = success, 1 = warning (legacy), 2 = error (legacy)
                # Modern: 0 = success, 3-99 = errors, 100-127 = warnings
                if job.status == "cancelled":
                    logger.info("Backup job was cancelled", job_id=job_id)
                    job.completed_at = datetime.utcnow()
                elif process.returncode == 0:
                    job.status = "completed"
                    job.progress = 100
                    # Update repository statistics after successful backup
                    await self._update_repository_stats(db, repository, env)
                elif 100 <= process.returncode <= 127:
                    # Warning (modern exit code system)
                    job.status = "completed"
                    job.progress = 100
                    job.error_message = f"Backup completed with warning (exit code {process.returncode})"
                    logger.warning("Backup completed with warning", job_id=job_id, exit_code=process.returncode)
                    # Update repository statistics even with warnings
                    await self._update_repository_stats(db, repository, env)
                else:
                    job.status = "failed"
                    # Build comprehensive error message with msgid details
                    error_parts = []

                    # Check if we have captured error msgids
                    if job_id in self.error_msgids and self.error_msgids[job_id]:
                        # Use the first critical error or the first error
                        errors = self.error_msgids[job_id]
                        primary_error = next((e for e in errors if e['levelname'] == 'CRITICAL'), errors[0])

                        # Format error with details and suggestions
                        formatted_error = format_error_message(
                            msgid=primary_error['msgid'],
                            original_message=primary_error['message'],
                            exit_code=process.returncode
                        )
                        error_parts.append(formatted_error)

                        # Add additional errors if present
                        if len(errors) > 1:
                            error_parts.append(f"\n\nAdditional errors encountered: {len(errors) - 1}")
                    else:
                        # Fallback to simple exit code message
                        error_parts.append(format_error_message(
                            exit_code=process.returncode
                        ))

                    job.error_message = "\n".join(error_parts)

                if job.completed_at is None:
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
            # Remove from running processes
            if job_id in self.running_processes:
                del self.running_processes[job_id]
                logger.debug("Removed backup process from tracking", job_id=job_id)

            # Clean up error msgids
            if job_id in self.error_msgids:
                del self.error_msgids[job_id]

            # Close the database session
            db.close()

# Global instance
backup_service = BackupService()
