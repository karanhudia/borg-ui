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
from app.services.notification_service import notification_service
from app.services.script_executor import execute_script

logger = structlog.get_logger()

class BackupService:
    """Service for executing backups with real-time log streaming"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running backup processes by job_id
        self.error_msgids = {}  # Track error message IDs by job_id
        self.log_buffers = {}  # Track in-memory log buffers by job_id (for running jobs)

    async def _run_hook(self, script: str, hook_name: str, timeout: int, job_id: int) -> dict:
        """
        Run a pre or post backup hook script using the shared script executor.

        This method delegates to the shared execute_script() function,
        ensuring identical behavior with the test endpoint.

        Args:
            script: Shell script to execute
            hook_name: Name of the hook (for logging)
            timeout: Timeout in seconds
            job_id: Backup job ID

        Returns:
            dict with success, stdout, stderr, returncode
        """
        logger.info(f"Running {hook_name} hook", job_id=job_id, script_preview=script[:100])

        # Use the shared script executor (same as test endpoint)
        # This guarantees identical execution environment and behavior
        result = await execute_script(
            script=script,
            timeout=float(timeout),
            env=os.environ.copy(),
            context=f"{hook_name} (job {job_id})"
        )

        # Map result format to what the backup service expects
        return {
            "success": result["success"],
            "returncode": result["exit_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"]
        }

    def rotate_logs(self, max_age_days: int = 30, max_files: int = 100):
        """
        Rotate backup log files to prevent disk space issues
        - Deletes logs older than max_age_days
        - Keeps only max_files most recent log files
        """
        try:
            import time

            if not self.log_dir.exists():
                return

            # Get all log files
            log_files = list(self.log_dir.glob("backup_*.log"))

            if not log_files:
                return

            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            deleted_count = 0

            # Delete files older than max_age_days
            for log_file in log_files:
                try:
                    file_age = current_time - log_file.stat().st_mtime
                    if file_age > max_age_seconds:
                        log_file.unlink()
                        deleted_count += 1
                        logger.debug("Deleted old log file", file=log_file.name, age_days=int(file_age / 86400))
                except Exception as e:
                    logger.warning("Failed to delete log file", file=log_file.name, error=str(e))

            # Get remaining files and sort by modification time (newest first)
            log_files = sorted(
                [f for f in self.log_dir.glob("backup_*.log")],
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )

            # Keep only max_files most recent
            if len(log_files) > max_files:
                for log_file in log_files[max_files:]:
                    try:
                        log_file.unlink()
                        deleted_count += 1
                        logger.debug("Deleted excess log file", file=log_file.name)
                    except Exception as e:
                        logger.warning("Failed to delete log file", file=log_file.name, error=str(e))

            if deleted_count > 0:
                logger.info("Log rotation completed",
                          deleted=deleted_count,
                          remaining=len(log_files) - deleted_count,
                          max_age_days=max_age_days,
                          max_files=max_files)

        except Exception as e:
            logger.error("Log rotation failed", error=str(e))

    def get_log_buffer(self, job_id: int, tail_lines: int = 500) -> list:
        """
        Get the last N lines from the in-memory log buffer for a running job.

        Args:
            job_id: The backup job ID
            tail_lines: Number of lines to return from the end of buffer (default 500)

        Returns:
            List of log lines (most recent tail_lines lines)
        """
        buffer = self.log_buffers.get(job_id, [])
        if not buffer:
            return []

        # Return last N lines (tail)
        return buffer[-tail_lines:] if len(buffer) > tail_lines else buffer

    async def _update_archive_stats(self, db: Session, job_id: int, repository_path: str, archive_name: str, env: dict):
        """Update backup job with final archive statistics"""
        try:
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if not job:
                logger.warning("Job not found for stats update", job_id=job_id)
                return

            # Get specific archive info using borg info --json
            archive_path = f"{repository_path}::{archive_name}"
            info_cmd = ["borg", "info", "--json", archive_path]
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
                    archives = info_data.get("archives", [])
                    if archives:
                        archive_info = archives[0]
                        stats = archive_info.get("stats", {})

                        # Update job with final statistics
                        job.original_size = stats.get("original_size", job.original_size or 0)
                        job.compressed_size = stats.get("compressed_size", job.compressed_size or 0)
                        job.deduplicated_size = stats.get("deduplicated_size", job.deduplicated_size or 0)
                        job.nfiles = stats.get("nfiles", job.nfiles or 0)

                        db.commit()
                        logger.info("Updated archive statistics",
                                  job_id=job_id,
                                  archive=archive_name,
                                  original_size=job.original_size,
                                  compressed_size=job.compressed_size,
                                  deduplicated_size=job.deduplicated_size,
                                  nfiles=job.nfiles)
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse borg info output for archive", job_id=job_id, error=str(e))
            else:
                logger.warning("Failed to get archive info",
                             job_id=job_id,
                             archive=archive_name,
                             returncode=info_process.returncode)

        except asyncio.TimeoutError:
            logger.warning("Timeout while updating archive stats", job_id=job_id)
        except Exception as e:
            logger.error("Failed to update archive stats", job_id=job_id, error=str(e))

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

    async def _calculate_source_size(self, source_paths: list[str]) -> int:
        """
        Calculate total size of source directories in bytes using du
        Returns total size in bytes, or 0 if calculation fails
        """
        try:
            total_size = 0

            for path in source_paths:
                try:
                    # Use du to get directory size in bytes
                    # -s: summarize (total for directory)
                    # -B1: block size of 1 byte (for precise byte count)
                    cmd = ["du", "-s", "-B1", path]

                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

                    if process.returncode == 0:
                        # Parse output: "1234567\t/path/to/dir"
                        output = stdout.decode().strip()
                        if output:
                            size_str = output.split('\t')[0]
                            path_size = int(size_str)
                            total_size += path_size
                            logger.info("Calculated directory size", path=path, size=path_size, size_formatted=self._format_bytes(path_size))
                    else:
                        logger.warning("Failed to calculate directory size", path=path, stderr=stderr.decode())

                except asyncio.TimeoutError:
                    logger.warning("Timeout while calculating directory size", path=path)
                except Exception as e:
                    logger.warning("Error calculating directory size", path=path, error=str(e))

            logger.info("Total source size calculated", total_size=total_size, total_formatted=self._format_bytes(total_size))
            return total_size

        except Exception as e:
            logger.error("Failed to calculate total source size", error=str(e))
            return 0

    async def execute_backup(self, job_id: int, repository: str, db: Session = None, archive_name: str = None):
        """Execute backup using borg directly for better control

        Args:
            job_id: Backup job ID
            repository: Repository path
            db: Database session (optional, will create new if not provided)
            archive_name: Optional custom archive name (if None, will use default manual-backup naming)
        """

        # Create a new database session for this background task
        db = SessionLocal()
        temp_key_file = None  # Track SSH key file for cleanup

        try:
            # Get job
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if not job:
                logger.error("Job not found", job_id=job_id)
                return

            # No log files - maximum performance
            job.status = "running"
            job.started_at = datetime.utcnow()
            db.commit()

            # Build borg create command directly
            # Format: borg create --progress --stats --list REPOSITORY::ARCHIVE PATH [PATH ...]
            # Use local time for archive names so they're meaningful to users
            if not archive_name:
                archive_name = f"manual-backup-{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"

            # Set environment variables for borg
            env = os.environ.copy()

            # Use modern exit codes for better error handling
            # 0 = success, 1 = warning, 2+ = error
            # Modern: 0 = success, 1-99 reserved, 3-99 = errors, 100-127 = warnings
            env['BORG_EXIT_CODES'] = 'modern'

            # Skip interactive prompts (auto-accept for unencrypted repos, etc.)
            env['BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK'] = 'yes'
            env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'

            # Configure lock behavior to prevent timeout issues with SSH repositories
            # Wait up to 180 seconds (3 minutes) for locks instead of default 1 second
            env["BORG_LOCK_WAIT"] = "180"
            # Mark this container's hostname as unique to avoid lock conflicts
            env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

            # Add SSH options to disable host key checking for remote repos
            # This allows automatic connection to new hosts without manual intervention
            ssh_opts = [
                "-o", "StrictHostKeyChecking=no",  # Don't check host keys
                "-o", "UserKnownHostsFile=/dev/null",  # Don't save host keys
                "-o", "LogLevel=ERROR",  # Reduce SSH verbosity
                "-o", "RequestTTY=no",  # Disable TTY allocation to prevent shell initialization output
                "-o", "PermitLocalCommand=no"  # Prevent local command execution
            ]
            env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

            # Look up repository record to get passphrase, source directories, exclude patterns, and compression
            source_paths = None  # No default - must be configured
            exclude_patterns = []  # Default no exclusions
            compression = "lz4"  # Default compression
            try:
                repo_record = db.query(Repository).filter(Repository.path == repository).first()
                if repo_record:
                    # Check if repository is in observability-only mode
                    if repo_record.mode == "observe":
                        error_msg = "Cannot create backups for observability-only repositories. This repository is configured for browsing and restoring existing archives only."
                        logger.error(error_msg, repository=repository, mode=repo_record.mode)
                        raise ValueError(error_msg)
                    # Set passphrase if available
                    if repo_record.passphrase:
                        env['BORG_PASSPHRASE'] = repo_record.passphrase
                        logger.info("Using passphrase from repository record", repository=repository)

                    # Get compression setting from repository
                    if repo_record.compression:
                        compression = repo_record.compression
                        logger.info("Using compression from repository", repository=repository, compression=compression)

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
                                error_msg = "No source directories configured for this repository. Please add source directories in repository settings."
                                logger.error(error_msg, repository=repository)
                                raise ValueError(error_msg)
                        except json.JSONDecodeError as e:
                            error_msg = f"Could not parse source_directories JSON: {str(e)}"
                            logger.error(error_msg, repository=repository)
                            raise ValueError(error_msg)
                    else:
                        error_msg = "No source directories configured for this repository. Please add source directories in repository settings."
                        logger.error(error_msg, repository=repository)
                        raise ValueError(error_msg)

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
                    error_msg = f"Repository record not found in database: {repository}"
                    logger.error(error_msg, repository=repository)
                    raise ValueError(error_msg)
            except ValueError:
                # Re-raise ValueError (from source_directories validation)
                raise
            except Exception as e:
                error_msg = f"Could not look up repository record: {str(e)}"
                logger.error(error_msg, error=str(e))
                raise ValueError(error_msg)

            # Use repository path as-is (already contains full SSH URL for SSH repos)
            actual_repository_path = repository

            # Setup SSH-specific configuration if this is an SSH repository
            if repo_record and repo_record.repository_type == "ssh":
                # Setup SSH key if available
                if repo_record.ssh_key_id:
                    from app.database.models import SSHKey
                    from cryptography.fernet import Fernet
                    import base64
                    from app.config import settings
                    import tempfile

                    ssh_key = db.query(SSHKey).filter(SSHKey.id == repo_record.ssh_key_id).first()
                    if ssh_key:
                        # Decrypt private key
                        encryption_key = settings.secret_key.encode()[:32]
                        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
                        private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

                        # Ensure private key ends with newline
                        if not private_key.endswith('\n'):
                            private_key += '\n'

                        # Create temporary key file
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as f:
                            f.write(private_key)
                            temp_key_file = f.name

                        os.chmod(temp_key_file, 0o600)

                        # Update SSH command to use the key
                        ssh_opts = [
                            "-i", temp_key_file,
                            "-o", "StrictHostKeyChecking=no",
                            "-o", "UserKnownHostsFile=/dev/null",
                            "-o", "LogLevel=ERROR",
                            "-o", "RequestTTY=no",  # Disable TTY allocation to prevent shell initialization output
                            "-o", "PermitLocalCommand=no"  # Prevent local command execution
                        ]
                        env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"
                        logger.info("Using SSH key for remote repository",
                                  ssh_key_id=repo_record.ssh_key_id,
                                  repository=actual_repository_path)

                # Set BORG_REMOTE_PATH if specified (path to borg binary on remote)
                if repo_record.remote_path:
                    env['BORG_REMOTE_PATH'] = repo_record.remote_path
                    logger.info("Using custom remote borg path",
                              remote_path=repo_record.remote_path,
                              repository=actual_repository_path)

            # Initialize hook logs
            hook_logs = []

            # Run pre-backup hook if configured
            if repo_record and repo_record.pre_backup_script:
                logger.info("Running pre-backup hook", job_id=job_id, repository=repository)
                hook_timeout = repo_record.hook_timeout or 300
                pre_hook_result = await self._run_hook(
                    repo_record.pre_backup_script,
                    "pre-backup",
                    hook_timeout,
                    job_id
                )

                # Log hook output
                hook_log_entry = [
                    "=" * 80,
                    "PRE-BACKUP HOOK",
                    "=" * 80,
                    f"Exit Code: {pre_hook_result['returncode']}",
                    f"Status: {'SUCCESS' if pre_hook_result['success'] else 'FAILED'}",
                    "",
                    "STDOUT:",
                    pre_hook_result['stdout'] if pre_hook_result['stdout'] else "(empty)",
                    "",
                    "STDERR:",
                    pre_hook_result['stderr'] if pre_hook_result['stderr'] else "(empty)",
                    "=" * 80,
                    ""
                ]
                hook_logs.extend(hook_log_entry)

                if not pre_hook_result["success"]:
                    error_msg = f"Pre-backup hook failed: {pre_hook_result['stderr']}"
                    logger.error(error_msg, job_id=job_id)

                    # Check if we should continue or abort
                    if not repo_record.continue_on_hook_failure:
                        job.status = "failed"
                        job.error_message = error_msg
                        job.logs = "\n".join(hook_logs)
                        job.completed_at = datetime.utcnow()
                        db.commit()

                        # Send failure notification for pre-hook failure
                        try:
                            await notification_service.send_backup_failure(
                                db, repository, error_msg, job_id
                            )
                        except Exception as e:
                            logger.warning("Failed to send backup failure notification", error=str(e))

                        return
                    else:
                        logger.warning("Pre-backup hook failed but continuing anyway",
                                     job_id=job_id,
                                     continue_on_failure=True)
                else:
                    logger.info("Pre-backup hook completed successfully", job_id=job_id)

            # Calculate total expected size of source directories
            logger.info("Calculating total size of source directories", source_paths=source_paths)
            total_expected_size = await self._calculate_source_size(source_paths)
            if total_expected_size > 0:
                job.total_expected_size = total_expected_size
                db.commit()
                logger.info("Stored expected size", job_id=job_id, total_expected_size=total_expected_size,
                          size_formatted=self._format_bytes(total_expected_size))
            else:
                logger.warning("Could not calculate expected size, progress percentage will not be accurate")

            # Build command with source directories and exclude patterns
            cmd = [
                "borg", "create",
                "--progress",
                "--stats",
                # "--list",  # REMOVED: Generates massive output, not needed for progress tracking
                "--show-rc",  # Show return code for better debugging
                "--log-json",  # Structured JSON logging
                "--compression", compression,
            ]

            # Add exclude patterns
            for pattern in exclude_patterns:
                cmd.extend(["--exclude", pattern])

            # Add custom flags if specified
            if repo_record and repo_record.custom_flags:
                custom_flags = repo_record.custom_flags.strip()
                if custom_flags:
                    # Split custom flags by whitespace and add to command
                    # This allows users to specify multiple flags like "--stats --list"
                    import shlex
                    try:
                        custom_flag_list = shlex.split(custom_flags)
                        cmd.extend(custom_flag_list)
                        logger.info("Added custom flags to borg create command",
                                  job_id=job_id,
                                  custom_flags=custom_flags)
                    except ValueError as e:
                        logger.warning("Failed to parse custom flags, skipping",
                                     job_id=job_id,
                                     custom_flags=custom_flags,
                                     error=str(e))

            # Add repository::archive
            cmd.append(f"{actual_repository_path}::{archive_name}")

            # Add all source paths to the command
            cmd.extend(source_paths)

            logger.info("Starting borg backup", job_id=job_id, repository=actual_repository_path, archive=archive_name, command=" ".join(cmd))

            # Send backup start notification
            try:
                await notification_service.send_backup_start(
                    db, repository, archive_name, source_paths, total_expected_size
                )
            except Exception as e:
                logger.warning("Failed to send backup start notification", error=str(e))

            # Execute command - NO LOG FILE FOR MAXIMUM PERFORMANCE
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

            # Performance optimization: Batch database commits
            last_commit_time = asyncio.get_event_loop().time()
            COMMIT_INTERVAL = 3.0  # Commit every 3 seconds for performance

            # In-memory circular log buffer (only saved on failure)
            log_buffer = []
            MAX_BUFFER_SIZE = 1000  # Keep last 1000 lines (~100KB RAM)

            # Store buffer reference for external access (Activity page)
            self.log_buffers[job_id] = log_buffer

            # Smart current_file tracking: Only show files taking >3 seconds
            file_start_times = {}  # Track when each file started processing
            last_shown_file = None

            # Speed tracking: Moving average over 30-second window
            speed_tracking = []  # List of (timestamp, original_size) tuples
            SPEED_WINDOW_SECONDS = 30  # Calculate speed over last 30 seconds

            async def check_cancellation():
                """Periodic heartbeat to check for cancellation independent of log output"""
                nonlocal cancelled
                while not cancelled and process.returncode is None:
                    await asyncio.sleep(3)  # Check every 3 seconds (reduced from 1s for performance)
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
                nonlocal cancelled, last_commit_time, last_shown_file, speed_tracking
                try:
                    async for line in process.stdout:
                        if cancelled:
                            break

                        line_str = line.decode('utf-8', errors='replace').strip()

                        # Add to in-memory circular log buffer (for failure debugging)
                        log_buffer.append(line_str)
                        if len(log_buffer) > MAX_BUFFER_SIZE:
                            log_buffer.pop(0)  # Remove oldest line

                        # PERFORMANCE OPTIMIZATION: Fast JSON detection (check first char only)
                        # Parse JSON progress messages only
                        try:
                            if line_str and line_str[0] == '{':
                                json_msg = json.loads(line_str)
                                msg_type = json_msg.get('type')

                                # Parse archive_progress messages for real-time stats
                                if msg_type == 'archive_progress':
                                    # Update size/file stats (in memory, no DB write yet)
                                    job.original_size = json_msg.get('original_size', 0)
                                    job.compressed_size = json_msg.get('compressed_size', 0)
                                    job.deduplicated_size = json_msg.get('deduplicated_size', 0)
                                    job.nfiles = json_msg.get('nfiles', 0)

                                    # Calculate backup speed using moving average (30-second window)
                                    if job.original_size > 0:
                                        current_time = asyncio.get_event_loop().time()

                                        # Add current data point
                                        speed_tracking.append((current_time, job.original_size))

                                        # Remove data points older than window
                                        speed_tracking[:] = [(t, s) for t, s in speed_tracking
                                                           if current_time - t <= SPEED_WINDOW_SECONDS]

                                        # Calculate speed from moving average (need at least 2 data points)
                                        if len(speed_tracking) >= 2:
                                            time_diff = speed_tracking[-1][0] - speed_tracking[0][0]
                                            size_diff = speed_tracking[-1][1] - speed_tracking[0][1]

                                            if time_diff > 0 and size_diff > 0:
                                                # Speed in MB/s
                                                job.backup_speed = (size_diff / (1024 * 1024)) / time_diff
                                            elif time_diff > 0:
                                                # No size change yet (early in backup or deduplication)
                                                job.backup_speed = 0.0

                                        # Calculate progress percentage if we have expected size
                                        if job.total_expected_size and job.total_expected_size > 0:
                                            job.progress_percent = min(100.0, (job.original_size / job.total_expected_size) * 100.0)

                                            # Calculate estimated time remaining (in seconds)
                                            remaining_bytes = job.total_expected_size - job.original_size
                                            if remaining_bytes > 0 and job.backup_speed > 0:
                                                # Speed is in MB/s, convert remaining bytes to MB
                                                remaining_mb = remaining_bytes / (1024 * 1024)
                                                job.estimated_time_remaining = int(remaining_mb / job.backup_speed)
                                            else:
                                                job.estimated_time_remaining = 0

                                    # SMART CURRENT_FILE TRACKING: Only show files taking >3 seconds
                                    current_path = json_msg.get('path', '')
                                    if current_path:
                                        current_time = asyncio.get_event_loop().time()

                                        # Track when this file started
                                        if current_path not in file_start_times:
                                            file_start_times[current_path] = current_time

                                        # Check how long this file has been processing
                                        file_duration = current_time - file_start_times[current_path]

                                        if file_duration > 3.0:
                                            # Large/slow file - worth showing to user
                                            job.current_file = current_path
                                            last_shown_file = current_path
                                        elif current_path != last_shown_file:
                                            # Fast file - don't show it, keep showing last large file or clear it
                                            if last_shown_file and last_shown_file not in file_start_times:
                                                # Last shown file is done, clear the display
                                                job.current_file = None
                                                last_shown_file = None

                                        # Clean up old file tracking (keep memory usage low)
                                        if len(file_start_times) > 100:
                                            # Remove files we finished more than 10 seconds ago
                                            old_files = [f for f, t in file_start_times.items()
                                                       if current_time - t > 10.0 and f != current_path]
                                            for old_file in old_files:
                                                del file_start_times[old_file]

                                    # Check if finished
                                    finished = json_msg.get('finished', False)
                                    if finished:
                                        # Archive is complete
                                        job.progress = 100
                                        job.progress_percent = 100.0
                                        logger.info("Archive creation finished", job_id=job_id)
                                    else:
                                        # Show indeterminate progress (1%) while backup is running
                                        if job.progress == 0 and job.original_size > 0:
                                            job.progress = 1
                                            job.progress_percent = 1.0

                                    # PERFORMANCE OPTIMIZATION: Batched commits (every 3 seconds)
                                    current_time = asyncio.get_event_loop().time()
                                    if current_time - last_commit_time >= COMMIT_INTERVAL:
                                        db.commit()
                                        last_commit_time = current_time
                                        logger.debug("Batched commit: progress update",
                                                   job_id=job_id,
                                                   nfiles=job.nfiles,
                                                   original_size=job.original_size)

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

                                    # Batched commit (no immediate commit)
                                    current_time = asyncio.get_event_loop().time()
                                    if current_time - last_commit_time >= COMMIT_INTERVAL:
                                        db.commit()
                                        last_commit_time = current_time

                                # Parse file_status messages for current file
                                elif msg_type == 'file_status':
                                    status = json_msg.get('status', '')
                                    path = json_msg.get('path', '')
                                    if path:
                                        # Apply same smart filtering
                                        file_duration = asyncio.get_event_loop().time() - file_start_times.get(path, asyncio.get_event_loop().time())
                                        if file_duration > 3.0:
                                            job.current_file = f"[{status}] {path}"
                                            last_shown_file = path

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

                        except (json.JSONDecodeError, ValueError):
                            # Not a JSON line, just regular log output - ignore
                            pass
                        except Exception as e:
                            logger.warning("Failed to parse JSON progress",
                                         job_id=job_id,
                                         error=str(e),
                                         line=line_str[:100])

                except asyncio.CancelledError:
                    logger.info("Log streaming cancelled", job_id=job_id)
                    raise
                finally:
                    # Final commit to save last state
                    db.commit()
                    logger.debug("Final commit after stream_logs completed", job_id=job_id)

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
                # Update archive statistics with final deduplicated size
                await self._update_archive_stats(db, job_id, repository, archive_name, env)
                # Update repository statistics after successful backup
                await self._update_repository_stats(db, repository, env)

                # Run post-backup hook if configured
                post_hook_failed = False
                if repo_record and repo_record.post_backup_script:
                    logger.info("Running post-backup hook", job_id=job_id, repository=repository)
                    hook_timeout = repo_record.hook_timeout or 300
                    post_hook_result = await self._run_hook(
                        repo_record.post_backup_script,
                        "post-backup",
                        hook_timeout,
                        job_id
                    )

                    # Log post-hook output
                    post_hook_log_entry = [
                        "=" * 80,
                        "POST-BACKUP HOOK",
                        "=" * 80,
                        f"Exit Code: {post_hook_result['returncode']}",
                        f"Status: {'SUCCESS' if post_hook_result['success'] else 'FAILED'}",
                        "",
                        "STDOUT:",
                        post_hook_result['stdout'] if post_hook_result['stdout'] else "(empty)",
                        "",
                        "STDERR:",
                        post_hook_result['stderr'] if post_hook_result['stderr'] else "(empty)",
                        "=" * 80,
                        ""
                    ]
                    hook_logs.extend(post_hook_log_entry)

                    if not post_hook_result["success"]:
                        post_hook_failed = True
                        logger.warning("Post-backup hook failed",
                                     job_id=job_id,
                                     stderr=post_hook_result['stderr'])
                        # Mark as failed if post-hook fails
                        job.status = "failed"
                        job.error_message = f"Backup succeeded but post-backup hook failed: {post_hook_result['stderr']}"
                    else:
                        logger.info("Post-backup hook completed successfully", job_id=job_id)

                # Send notification after post-hook completes
                if post_hook_failed:
                    # Send failure notification if post-hook failed
                    try:
                        await notification_service.send_backup_failure(
                            db, repository, job.error_message, job_id
                        )
                    except Exception as e:
                        logger.warning("Failed to send backup failure notification", error=str(e))
                else:
                    # Send success notification if everything succeeded
                    try:
                        stats = {
                            "original_size": job.original_size,
                            "compressed_size": job.compressed_size,
                            "deduplicated_size": job.deduplicated_size
                        }
                        await notification_service.send_backup_success(
                            db, repository, archive_name, stats, job.completed_at
                        )
                    except Exception as e:
                        logger.warning("Failed to send backup success notification", error=str(e))
            elif 100 <= process.returncode <= 127:
                # Warning (modern exit code system)
                job.status = "completed"
                job.progress = 100
                job.error_message = f"Backup completed with warning (exit code {process.returncode})"
                logger.warning("Backup completed with warning", job_id=job_id, exit_code=process.returncode)
                # Update archive statistics with final deduplicated size
                await self._update_archive_stats(db, job_id, repository, archive_name, env)
                # Update repository statistics even with warnings
                await self._update_repository_stats(db, repository, env)

                # Run post-backup hook even with warnings
                post_hook_failed = False
                if repo_record and repo_record.post_backup_script:
                    logger.info("Running post-backup hook", job_id=job_id, repository=repository)
                    hook_timeout = repo_record.hook_timeout or 300
                    post_hook_result = await self._run_hook(
                        repo_record.post_backup_script,
                        "post-backup",
                        hook_timeout,
                        job_id
                    )

                    # Log post-hook output
                    post_hook_log_entry = [
                        "=" * 80,
                        "POST-BACKUP HOOK",
                        "=" * 80,
                        f"Exit Code: {post_hook_result['returncode']}",
                        f"Status: {'SUCCESS' if post_hook_result['success'] else 'FAILED'}",
                        "",
                        "STDOUT:",
                        post_hook_result['stdout'] if post_hook_result['stdout'] else "(empty)",
                        "",
                        "STDERR:",
                        post_hook_result['stderr'] if post_hook_result['stderr'] else "(empty)",
                        "=" * 80,
                        ""
                    ]
                    hook_logs.extend(post_hook_log_entry)

                    if not post_hook_result["success"]:
                        post_hook_failed = True
                        logger.warning("Post-backup hook failed",
                                     job_id=job_id,
                                     stderr=post_hook_result['stderr'])
                        # Mark as failed if post-hook fails
                        job.status = "failed"
                        job.error_message = f"Backup succeeded with warning but post-backup hook failed: {post_hook_result['stderr']}"
                    else:
                        logger.info("Post-backup hook completed successfully", job_id=job_id)

                # Send notification after post-hook completes (for warning case)
                if post_hook_failed:
                    # Send failure notification if post-hook failed
                    try:
                        await notification_service.send_backup_failure(
                            db, repository, job.error_message, job_id
                        )
                    except Exception as e:
                        logger.warning("Failed to send backup failure notification", error=str(e))
                else:
                    # Send success notification (backup completed with warnings but post-hook succeeded)
                    try:
                        stats = {
                            "original_size": job.original_size,
                            "compressed_size": job.compressed_size,
                            "deduplicated_size": job.deduplicated_size
                        }
                        await notification_service.send_backup_success(
                            db, repository, archive_name, stats, job.completed_at
                        )
                    except Exception as e:
                        logger.warning("Failed to send backup success notification", error=str(e))
            else:
                job.status = "failed"
                # Build comprehensive error message with msgid details
                error_parts = []
                is_lock_error = False

                # Check if we have captured error msgids
                if job_id in self.error_msgids and self.error_msgids[job_id]:
                    # Use the first critical error or the first error
                    errors = self.error_msgids[job_id]
                    primary_error = next((e for e in errors if e['levelname'] == 'CRITICAL'), errors[0])

                    # Check if this is a lock error
                    if primary_error['msgid'] in ['LockTimeout', 'LockError']:
                        is_lock_error = True
                        # Store repository path in error message for easy access
                        error_parts.append(f"LOCK_ERROR::{repository}")

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

                # Log lock error for visibility
                if is_lock_error:
                    logger.warning("Backup failed due to lock timeout",
                                 job_id=job_id,
                                 repository=repository,
                                 msgid=primary_error['msgid'])

                # Run post-backup hook on failure if configured (fixes #85)
                if repo_record and repo_record.post_backup_script and repo_record.run_post_backup_on_failure:
                    logger.info("Running post-backup hook on failure", job_id=job_id, repository=repository)
                    hook_timeout = repo_record.hook_timeout or 300
                    try:
                        post_hook_result = await self._run_hook(
                            repo_record.post_backup_script,
                            "post-backup",
                            hook_timeout,
                            job_id
                        )

                        # Log post-hook output
                        post_hook_log_entry = [
                            "=" * 80,
                            "POST-BACKUP HOOK (ON FAILURE)",
                            "=" * 80,
                            f"Exit Code: {post_hook_result['returncode']}",
                            f"Status: {'SUCCESS' if post_hook_result['success'] else 'FAILED'}",
                            "",
                            "STDOUT:",
                            post_hook_result['stdout'] if post_hook_result['stdout'] else "(empty)",
                            "",
                            "STDERR:",
                            post_hook_result['stderr'] if post_hook_result['stderr'] else "(empty)",
                            "=" * 80,
                            ""
                        ]
                        hook_logs.extend(post_hook_log_entry)

                        if not post_hook_result["success"]:
                            logger.warning("Post-backup hook failed after backup failure",
                                         job_id=job_id,
                                         stderr=post_hook_result['stderr'])
                            # Append hook failure to error message
                            job.error_message += f"\n\nPost-backup hook also failed: {post_hook_result['stderr']}"
                        else:
                            logger.info("Post-backup hook completed successfully after backup failure", job_id=job_id)
                    except Exception as hook_error:
                        logger.error("Exception while running post-backup hook on failure",
                                   job_id=job_id,
                                   error=str(hook_error))
                        hook_logs.append(f"Post-backup hook execution error: {str(hook_error)}")

            if job.completed_at is None:
                job.completed_at = datetime.utcnow()

            # CONDITIONAL LOG SAVING: Only save logs on failure/cancellation for debugging
            # Always save hook logs if present
            if job.status in ['failed', 'cancelled'] or process.returncode not in [0, None]:
                # Save log buffer to file for debugging
                log_file = self.log_dir / f"backup_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                try:
                    combined_logs = hook_logs + log_buffer if hook_logs else log_buffer
                    log_file.write_text('\n'.join(combined_logs))
                    # Store log file path so Activity page can read and display logs
                    job.log_file_path = str(log_file)
                    job.logs = f"Logs saved to: {log_file.name}"
                    logger.warning("Backup failed/cancelled, logs saved for debugging",
                                 job_id=job_id,
                                 status=job.status,
                                 log_file=str(log_file),
                                 log_lines=len(combined_logs))
                except Exception as e:
                    job.logs = f"Failed to save logs: {str(e)}"
                    logger.error("Failed to save log buffer to file", job_id=job_id, error=str(e))
            else:
                # Success - save hook logs if present, otherwise no logs for performance
                if hook_logs:
                    job.logs = "\n".join(hook_logs)
                    logger.info("Backup completed successfully with hooks, hook logs saved", job_id=job_id)
                else:
                    job.logs = None
                    logger.info("Backup completed successfully, no logs saved", job_id=job_id)

            db.commit()
            logger.info("Backup completed", job_id=job_id, status=job.status)

            # Send failure notification if backup failed
            if job.status == "failed":
                try:
                    await notification_service.send_backup_failure(
                        db, repository, job.error_message or "Unknown error", job_id
                    )
                except Exception as e:
                    logger.warning("Failed to send backup failure notification", error=str(e))

        except Exception as e:
            logger.error("Backup execution failed", job_id=job_id, error=str(e))
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()

            # Send failure notification
            try:
                await notification_service.send_backup_failure(
                    db, repository, str(e), job_id
                )
            except Exception as notif_error:
                logger.warning("Failed to send backup failure notification", error=str(notif_error))
        finally:
            # Remove from running processes
            if job_id in self.running_processes:
                del self.running_processes[job_id]
                logger.debug("Removed backup process from tracking", job_id=job_id)

            # Clean up log buffer (no longer needed after job completes)
            if job_id in self.log_buffers:
                del self.log_buffers[job_id]
                logger.debug("Cleaned up log buffer", job_id=job_id)

            # Clean up error msgids
            if job_id in self.error_msgids:
                del self.error_msgids[job_id]

            # Clean up temporary SSH key file if it exists
            if temp_key_file and os.path.exists(temp_key_file):
                try:
                    os.unlink(temp_key_file)
                    logger.debug("Cleaned up temporary SSH key file", temp_key_file=temp_key_file)
                except Exception as e:
                    logger.warning("Failed to delete temporary SSH key file", temp_key_file=temp_key_file, error=str(e))

            # Close the database session
            db.close()

    async def cancel_backup(self, job_id: int) -> bool:
        """
        Cancel a running backup job by terminating its process

        Args:
            job_id: The backup job ID to cancel

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
            logger.info("Sent SIGTERM to backup process", job_id=job_id, pid=process.pid)

            # Wait up to 5 seconds for graceful termination
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
                logger.info("Backup process terminated gracefully", job_id=job_id)
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate gracefully
                process.kill()
                logger.warning("Force killed backup process (SIGKILL)", job_id=job_id, pid=process.pid)
                await process.wait()

            return True
        except Exception as e:
            logger.error("Failed to cancel backup process", job_id=job_id, error=str(e))
            return False

# Global instance
backup_service = BackupService()
