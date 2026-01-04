import asyncio
import os
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import BackupJob, Repository, RepositoryScript, SystemSettings
from app.database.database import SessionLocal
from app.config import settings
from app.core.borg_errors import format_error_message, get_error_details
from app.services.notification_service import notification_service
from app.services.script_executor import execute_script
from app.services.script_library_executor import ScriptLibraryExecutor

logger = structlog.get_logger()

class BackupService:
    """Service for executing backups with real-time log streaming"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running backup processes by job_id
        self.error_msgids = {}  # Track error message IDs by job_id
        self.log_buffers = {}  # Track in-memory log buffers by job_id (for running jobs)
        self.ssh_mounts = {}  # Track SSH mounts by job_id: {job_id: [(mount_point, ssh_url), ...]}

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

    async def _execute_hooks(
        self,
        db: Session,
        repo_record: Repository,
        hook_type: str,  # 'pre-backup' or 'post-backup'
        backup_result: str = None,  # 'success', 'failure', 'warning' (for post-backup)
        job_id: int = None
    ) -> dict:
        """
        Execute hooks using script library OR inline scripts (backward compatible)

        Priority:
        1. Check if repository has script library scripts configured
        2. If yes, use ScriptLibraryExecutor
        3. If no, fall back to inline scripts (old behavior)

        Returns:
            dict with success, execution_logs, scripts_executed, scripts_failed
        """
        # Check if repository uses script library
        has_library_scripts = db.query(RepositoryScript).filter(
            RepositoryScript.repository_id == repo_record.id,
            RepositoryScript.hook_type == hook_type,
            RepositoryScript.enabled == True
        ).count() > 0

        if has_library_scripts:
            # Use script library
            logger.info("Using script library for hooks",
                       repository_id=repo_record.id,
                       hook_type=hook_type)

            executor = ScriptLibraryExecutor(db)
            result = await executor.execute_hooks(
                repository_id=repo_record.id,
                hook_type=hook_type,
                backup_result=backup_result,
                backup_job_id=job_id
            )

            return {
                "success": result["success"],
                "execution_logs": result["execution_logs"],
                "scripts_executed": result["scripts_executed"],
                "scripts_failed": result["scripts_failed"],
                "using_library": True
            }

        else:
            # Fall back to inline scripts (backward compatibility)
            inline_script = None
            if hook_type == "pre-backup":
                inline_script = repo_record.pre_backup_script
            elif hook_type == "post-backup":
                inline_script = repo_record.post_backup_script

            if not inline_script:
                # No scripts configured
                return {
                    "success": True,
                    "execution_logs": [],
                    "scripts_executed": 0,
                    "scripts_failed": 0,
                    "using_library": False
                }

            logger.info("Using inline script (legacy)",
                       repository_id=repo_record.id,
                       hook_type=hook_type)

            # Execute inline script
            executor = ScriptLibraryExecutor(db)
            # Use appropriate timeout based on hook type
            timeout = (repo_record.pre_hook_timeout if hook_type == 'pre-backup'
                      else repo_record.post_hook_timeout) or 300
            result = await executor.execute_inline_script(
                script_content=inline_script,
                script_type=hook_type,
                timeout=timeout,
                repository_id=repo_record.id,
                backup_job_id=job_id
            )

            return {
                "success": result["success"],
                "execution_logs": result["logs"],
                "scripts_executed": 1,
                "scripts_failed": 0 if result["success"] else 1,
                "using_library": False
            }

    def rotate_logs(self, db: Session = None):
        """
        Rotate backup log files using configurable size + age based rotation.

        Reads settings from database:
        - log_retention_days: Maximum age of logs
        - log_max_total_size_mb: Maximum total size of all logs

        Uses log_manager service for cleanup with protection for running jobs.

        Args:
            db: Database session (required to query settings and running jobs)
        """
        try:
            # Import log_manager here to avoid circular dependency
            from app.services.log_manager import log_manager

            if not self.log_dir.exists():
                return

            # If no database session provided, create one
            if db is None:
                db = SessionLocal()
                close_db = True
            else:
                close_db = False

            try:
                # Get system settings
                system_settings = db.query(SystemSettings).first()
                if not system_settings:
                    system_settings = SystemSettings()
                    db.add(system_settings)
                    db.commit()

                max_age_days = system_settings.log_retention_days or 30
                max_total_size_mb = system_settings.log_max_total_size_mb or 500

                logger.info("Starting log rotation",
                          max_age_days=max_age_days,
                          max_total_size_mb=max_total_size_mb)

                # Use log_manager for combined cleanup (age + size)
                result = log_manager.cleanup_logs_combined(
                    db=db,
                    max_age_days=max_age_days,
                    max_total_size_mb=max_total_size_mb,
                    dry_run=False
                )

                if result["success"]:
                    logger.info("Log rotation completed successfully",
                              total_deleted=result["total_deleted_count"],
                              size_freed_mb=result["total_deleted_size_mb"],
                              age_deleted=result["age_cleanup"]["deleted_count"],
                              size_deleted=result["size_cleanup"]["deleted_count"])
                else:
                    logger.warning("Log rotation completed with errors",
                                 total_deleted=result["total_deleted_count"],
                                 size_freed_mb=result["total_deleted_size_mb"],
                                 errors=result["total_errors"])

            finally:
                if close_db:
                    db.close()

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
            info_stdout, info_stderr = await asyncio.wait_for(info_process.communicate(), timeout=settings.borg_info_timeout)

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
            list_stdout, list_stderr = await asyncio.wait_for(list_process.communicate(), timeout=settings.borg_list_timeout)

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
            info_stdout, info_stderr = await asyncio.wait_for(info_process.communicate(), timeout=settings.borg_info_timeout)

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

    async def _calculate_source_size(self, source_paths: list[str], exclude_patterns: list[str] = None) -> int:
        """
        Calculate total size of source directories in bytes using du
        Supports both local paths and SSH URLs (ssh://user@host:port/path)
        Applies exclude patterns to match Borg's exclusion logic

        Args:
            source_paths: List of source directory paths
            exclude_patterns: List of patterns to exclude (same format as Borg excludes)

        Returns:
            Total size in bytes, or 0 if calculation fails
        """
        try:
            if exclude_patterns is None:
                exclude_patterns = []

            logger.info("Starting source size calculation",
                       paths=source_paths,
                       path_count=len(source_paths),
                       exclude_patterns=exclude_patterns)
            total_size = 0

            for path in source_paths:
                try:
                    # Check if this is an SSH URL
                    if path.startswith('ssh://'):
                        # Parse SSH URL: ssh://user@host:port/path
                        import re
                        match = re.match(r'ssh://([^@]+)@([^:]+):(\d+)(/.*)', path)
                        if match:
                            username, host, port, remote_path = match.groups()

                            # Build du command with exclude patterns
                            # -s: summarize, -b: bytes (portable across systems)
                            du_excludes = ""
                            for pattern in exclude_patterns:
                                # Escape single quotes in pattern for shell safety
                                safe_pattern = pattern.replace("'", "'\\''")
                                du_excludes += f" --exclude='{safe_pattern}'"

                            # Use SSH to run du on the remote host
                            cmd = [
                                "ssh",
                                "-o", "StrictHostKeyChecking=no",
                                "-o", "UserKnownHostsFile=/dev/null",
                                "-o", "LogLevel=ERROR",
                                "-o", "ConnectTimeout=10",
                                "-p", port,
                                f"{username}@{host}",
                                f"du -sb{du_excludes} {remote_path} 2>/dev/null | cut -f1"
                            ]

                            process = await asyncio.create_subprocess_exec(
                                *cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )

                            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=settings.script_timeout)

                            if process.returncode == 0:
                                output = stdout.decode().strip()
                                if output and output.isdigit():
                                    path_size = int(output)
                                    total_size += path_size
                                    logger.info("Calculated remote directory size", path=path, size=path_size, size_formatted=self._format_bytes(path_size))
                                else:
                                    logger.warning("Failed to parse remote directory size", path=path, output=output)
                            else:
                                logger.warning("Failed to calculate remote directory size", path=path, stderr=stderr.decode())
                        else:
                            logger.warning("Invalid SSH URL format", path=path)
                    else:
                        # Local path - use local du
                        # -s: summarize (total for directory)
                        # -B1: block size of 1 byte (for precise byte count)
                        # --exclude: exclude patterns (same as Borg patterns)
                        cmd = ["du", "-s", "-B1"]

                        # Add exclude patterns
                        for pattern in exclude_patterns:
                            cmd.extend(["--exclude", pattern])

                        cmd.append(path)

                        process = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )

                        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

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
                    logger.warning("Timeout while calculating directory size (120s timeout exceeded)",
                                 path=path,
                                 timeout_seconds=120)
                except Exception as e:
                    logger.warning("Error calculating directory size",
                                 path=path,
                                 error=str(e),
                                 error_type=type(e).__name__)

            if total_size > 0:
                logger.info("Total source size calculated successfully",
                          total_size=total_size,
                          total_formatted=self._format_bytes(total_size),
                          paths_processed=len(source_paths))
            else:
                logger.warning("Source size calculation returned 0 - all paths failed or were empty",
                             paths=source_paths,
                             paths_count=len(source_paths))
            return total_size

        except Exception as e:
            logger.error("Failed to calculate total source size",
                       error=str(e),
                       error_type=type(e).__name__,
                       paths=source_paths)
            return 0

    async def _calculate_and_update_size_background(self, job_id: int, source_paths: list[str], exclude_patterns: list[str] = None):
        """
        Background task to calculate source size and update job record
        Runs without blocking the backup start

        Args:
            job_id: The backup job ID
            source_paths: List of source directory paths
            exclude_patterns: List of patterns to exclude (same format as Borg excludes)
        """
        try:
            if exclude_patterns is None:
                exclude_patterns = []

            logger.info("Background size calculation started",
                       job_id=job_id,
                       source_paths=source_paths,
                       path_count=len(source_paths),
                       exclude_count=len(exclude_patterns))
            total_expected_size = await self._calculate_source_size(source_paths, exclude_patterns)

            if total_expected_size > 0:
                # Update the job record with the calculated size
                db = SessionLocal()
                try:
                    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
                    if job and job.status == "running":
                        job.total_expected_size = total_expected_size
                        db.commit()
                        logger.info("Background size calculation completed and job updated",
                                   job_id=job_id,
                                   total_expected_size=total_expected_size,
                                   size_formatted=self._format_bytes(total_expected_size))
                    else:
                        logger.info("Background size calculation completed but job no longer running",
                                   job_id=job_id)
                finally:
                    db.close()
            else:
                logger.warning("Background size calculation completed but returned 0 - check paths accessibility",
                             job_id=job_id,
                             source_paths=source_paths,
                             message="ETA and progress percentage will not be available")

        except Exception as e:
            logger.error("Error in background size calculation",
                       job_id=job_id,
                       error=str(e),
                       error_type=type(e).__name__,
                       source_paths=source_paths)

    def _parse_ssh_url(self, ssh_url: str) -> dict:
        """
        Parse SSH URL to extract connection details
        Format: ssh://user@host:port/path
        Returns: dict with keys: username, host, port, path
        """
        match = re.match(r'ssh://([^@]+)@([^:]+):(\d+)(/.*)', ssh_url)
        if match:
            username, host, port, path = match.groups()
            return {
                'username': username,
                'host': host,
                'port': port,
                'path': path
            }
        return None

    async def _mount_ssh_path(self, ssh_url: str, job_id: int) -> str:
        """
        Mount an SSH path via SSHFS to a temporary directory
        Returns: local mount point path, or None if mount failed
        """
        try:
            # Check if SSHFS is available
            try:
                check_process = await asyncio.create_subprocess_exec(
                    "which", "sshfs",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await check_process.communicate()
                if check_process.returncode != 0:
                    logger.error(
                        "SSHFS not found - cannot mount remote paths",
                        ssh_url=ssh_url,
                        job_id=job_id,
                        hint="Install SSHFS package or rebuild Docker image with SSHFS support"
                    )
                    return None
            except Exception as check_error:
                logger.error("Error checking for SSHFS", error=str(check_error), job_id=job_id)
                return None

            # Parse SSH URL
            parsed = self._parse_ssh_url(ssh_url)
            if not parsed:
                logger.error("Failed to parse SSH URL", ssh_url=ssh_url, job_id=job_id)
                return None

            # Create temporary mount point with directory structure
            # Extract the last component of the remote path for a clean archive structure
            remote_path = parsed['path']
            path_basename = os.path.basename(remote_path.rstrip('/'))

            # Create a temporary root directory
            temp_root = tempfile.mkdtemp(prefix=f"borg_backup_root_{job_id}_")

            # Create the mount point inside with the remote directory name
            mount_dir = os.path.join(temp_root, path_basename)
            os.makedirs(mount_dir, exist_ok=True)

            logger.info("Created temporary mount point",
                       temp_root=temp_root,
                       mount_point=mount_dir,
                       remote_basename=path_basename,
                       ssh_url=ssh_url,
                       job_id=job_id)

            # Get current user's UID and GID for mount options
            current_uid = os.getuid()
            current_gid = os.getgid()

            # Build SSHFS command
            cmd = [
                "sshfs",
                f"{parsed['username']}@{parsed['host']}:{parsed['path']}",
                mount_dir,
                "-p", parsed['port'],
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=30",
                "-o", "ServerAliveInterval=15",
                "-o", "ServerAliveCountMax=3",
                "-o", "reconnect",
                "-o", "follow_symlinks",
                "-o", "allow_other",  # Allow non-root user to access mount
                "-o", f"uid={current_uid}",  # Set mount owner to current user
                "-o", f"gid={current_gid}",  # Set mount group to current user's group
                "-o", "workaround=rename"  # Compatibility workaround for SFTP servers
            ]

            logger.info("Mounting SSH path via SSHFS", command=" ".join(cmd), job_id=job_id)

            # Execute mount command in background (SSHFS daemonizes)
            # We'll check if the mount succeeded rather than waiting for the process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL
            )

            # Give SSHFS a moment to start mounting (it forks immediately)
            await asyncio.sleep(1)

            # Helper function to cleanup on failure
            def cleanup_on_failure():
                try:
                    import shutil
                    shutil.rmtree(temp_root, ignore_errors=True)
                except:
                    pass

            # Check if the mount succeeded by trying to access the directory
            # We do this in a loop to give SSHFS time to establish the mount
            for attempt in range(5):  # Try for up to 5 seconds
                try:
                    # Try to list the directory to verify mount is accessible
                    test_process = await asyncio.create_subprocess_exec(
                        "ls", "-A", mount_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    test_stdout, test_stderr = await asyncio.wait_for(test_process.communicate(), timeout=2)

                    if test_process.returncode == 0:
                        logger.info("Successfully mounted and verified SSH path",
                                   temp_root=temp_root,
                                   mount_point=mount_dir,
                                   ssh_url=ssh_url,
                                   attempt=attempt+1,
                                   job_id=job_id)

                        # Track this mount for cleanup (store both mount_dir and temp_root)
                        if job_id not in self.ssh_mounts:
                            self.ssh_mounts[job_id] = []
                        self.ssh_mounts[job_id].append((mount_dir, temp_root, ssh_url))

                        return temp_root  # Return temp_root for backup, not mount_dir
                    else:
                        # Mount not ready yet, wait and retry
                        if attempt < 4:
                            await asyncio.sleep(1)
                        else:
                            # Final attempt failed
                            stderr_msg = test_stderr.decode().strip() if test_stderr else "Unknown error"
                            logger.error("Mount verification failed after retries",
                                       ssh_url=ssh_url,
                                       mount_point=mount_dir,
                                       test_stderr=stderr_msg,
                                       job_id=job_id)
                            await self._unmount_ssh_path(mount_dir, job_id)
                            cleanup_on_failure()
                            return None

                except asyncio.TimeoutError:
                    # Verification timed out, wait and retry if not last attempt
                    if attempt < 4:
                        await asyncio.sleep(1)
                    else:
                        logger.error("Timeout verifying mount after retries",
                                   ssh_url=ssh_url,
                                   mount_point=mount_dir,
                                   job_id=job_id)
                        await self._unmount_ssh_path(mount_dir, job_id)
                        cleanup_on_failure()
                        return None
                except Exception as e:
                    logger.error("Error verifying mount",
                               ssh_url=ssh_url,
                               mount_point=mount_dir,
                               error=str(e),
                               job_id=job_id)
                    if attempt == 4:
                        await self._unmount_ssh_path(mount_dir, job_id)
                        cleanup_on_failure()
                        return None
                    await asyncio.sleep(1)

        except asyncio.TimeoutError:
            logger.error("Timeout while mounting SSH path", ssh_url=ssh_url, job_id=job_id)
            try:
                import shutil
                shutil.rmtree(temp_root, ignore_errors=True)
            except:
                pass
            return None
        except FileNotFoundError as e:
            logger.error(
                "SSHFS command not found - install SSHFS or rebuild Docker image",
                ssh_url=ssh_url,
                error=str(e),
                job_id=job_id
            )
            try:
                import shutil
                shutil.rmtree(temp_root, ignore_errors=True)
            except:
                pass
            return None
        except Exception as e:
            logger.error("Error mounting SSH path", ssh_url=ssh_url, error=str(e), job_id=job_id)
            try:
                import shutil
                shutil.rmtree(temp_root, ignore_errors=True)
            except:
                pass
            return None

    async def _unmount_ssh_path(self, mount_point: str, job_id: int):
        """
        Unmount an SSHFS mount point
        """
        try:
            logger.info("Unmounting SSH path", mount_point=mount_point, job_id=job_id)

            # Use fusermount -u to unmount (works on Linux)
            # On macOS, use umount
            import platform
            if platform.system() == "Darwin":
                cmd = ["umount", mount_point]
            else:
                cmd = ["fusermount", "-u", mount_point]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)

            if process.returncode == 0:
                logger.info("Successfully unmounted SSH path", mount_point=mount_point, job_id=job_id)
                # Remove the empty mount point directory
                try:
                    os.rmdir(mount_point)
                    logger.debug("Removed mount point directory", mount_point=mount_point, job_id=job_id)
                except Exception as e:
                    logger.warning("Failed to remove mount point directory", mount_point=mount_point, error=str(e), job_id=job_id)
            else:
                logger.error("Failed to unmount SSH path",
                           mount_point=mount_point,
                           stderr=stderr.decode(),
                           returncode=process.returncode,
                           job_id=job_id)

        except asyncio.TimeoutError:
            logger.error("Timeout while unmounting SSH path", mount_point=mount_point, job_id=job_id)
        except Exception as e:
            logger.error("Error unmounting SSH path", mount_point=mount_point, error=str(e), job_id=job_id)

    async def _prepare_source_paths(self, source_paths: list[str], job_id: int) -> list[str]:
        """
        Prepare source paths for backup by mounting SSH URLs via SSHFS
        Returns: list of processed paths (SSH URLs replaced with temp root directories)
        """
        processed_paths = []

        for path in source_paths:
            if path.startswith('ssh://'):
                # Mount SSH path - this returns the temp_root directory
                temp_root = await self._mount_ssh_path(path, job_id)
                if temp_root:
                    processed_paths.append(temp_root)
                    logger.info("Using mounted path for backup", original=path, backup_root=temp_root, job_id=job_id)
                else:
                    logger.error("Failed to mount SSH path, skipping from backup", path=path, job_id=job_id)
                    # Don't add this path to processed_paths - skip it
            else:
                # Local path - use as-is
                processed_paths.append(path)

        return processed_paths

    async def _cleanup_ssh_mounts(self, job_id: int):
        """
        Cleanup all SSH mounts for a job
        """
        if job_id not in self.ssh_mounts:
            return

        mounts = self.ssh_mounts[job_id]
        logger.info("Cleaning up SSH mounts", job_id=job_id, mount_count=len(mounts))

        for mount_point, temp_root, ssh_url in mounts:
            # Unmount the SSHFS mount
            await self._unmount_ssh_path(mount_point, job_id)

            # Remove the temporary root directory
            try:
                import shutil
                shutil.rmtree(temp_root, ignore_errors=True)
                logger.debug("Removed temporary root directory", temp_root=temp_root, job_id=job_id)
            except Exception as e:
                logger.warning("Failed to remove temporary root directory",
                             temp_root=temp_root,
                             error=str(e),
                             job_id=job_id)

        # Remove from tracking
        del self.ssh_mounts[job_id]

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

            # Run pre-backup hooks (script library or inline)
            if repo_record:
                logger.info("Executing pre-backup hooks", job_id=job_id, repository=repository)
                hook_result = await self._execute_hooks(
                    db=db,
                    repo_record=repo_record,
                    hook_type="pre-backup",
                    job_id=job_id
                )

                # Add hook logs
                if hook_result["execution_logs"]:
                    hook_logs.extend(hook_result["execution_logs"])

                logger.info("Pre-backup hooks completed",
                           scripts_executed=hook_result["scripts_executed"],
                           scripts_failed=hook_result["scripts_failed"],
                           using_library=hook_result["using_library"])

                if not hook_result["success"]:
                    error_msg = f"Pre-backup hooks failed: {hook_result['scripts_failed']}/{hook_result['scripts_executed']} scripts failed"
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
                        logger.warning("Pre-backup hooks failed but continuing anyway",
                                     job_id=job_id,
                                     continue_on_failure=True)

            # Calculate total expected size of source directories in background
            # This runs asynchronously without blocking backup start
            # Progress percentage will update when calculation completes
            logger.info("Starting background calculation of source directories size",
                       source_paths=source_paths,
                       job_id=job_id,
                       exclude_patterns=exclude_patterns)
            asyncio.create_task(self._calculate_and_update_size_background(job_id, source_paths, exclude_patterns))

            # Prepare source paths: mount SSH URLs via SSHFS
            logger.info("Preparing source paths (mounting SSH URLs if needed)", source_paths=source_paths, job_id=job_id)
            processed_source_paths = await self._prepare_source_paths(source_paths, job_id)
            if not processed_source_paths:
                logger.error("No valid source paths after processing (all SSH mounts failed?)", job_id=job_id)
                job.status = "failed"
                job.error_message = "Failed to prepare source paths: all SSH mounts failed or no valid paths"
                job.completed_at = datetime.utcnow()
                db.commit()
                return
            logger.info("Source paths prepared", original_count=len(source_paths), processed_count=len(processed_source_paths), job_id=job_id)

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

            # Add all source paths to the command (using processed paths with mounted SSH URLs)
            cmd.extend(processed_source_paths)

            logger.info("Starting borg backup", job_id=job_id, repository=actual_repository_path, archive=archive_name, command=" ".join(cmd))

            # Send backup start notification (size will be updated by background task)
            try:
                await notification_service.send_backup_start(
                    db, repository, archive_name, source_paths, None
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

            # Track captured exit code from log messages (e.g., rc 105)
            # This is used if process.returncode is 0 but borg actually exited with a warning code
            captured_exit_code = None

            # Performance optimization: Batch database commits
            last_commit_time = asyncio.get_event_loop().time()
            COMMIT_INTERVAL = 3.0  # Commit every 3 seconds for performance

            # In-memory circular log buffer (for UI streaming)
            log_buffer = []
            MAX_BUFFER_SIZE = 1000  # Keep last 1000 lines (~100KB RAM)

            # Store buffer reference for external access (Activity page)
            self.log_buffers[job_id] = log_buffer

            # Create temporary log file to capture ALL logs (not just buffer)
            temp_log_file = self.log_dir / f"backup_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            log_file_handle = None
            try:
                # 64KB buffer - optimal for log files, reduces disk I/O without excessive memory use
                log_file_handle = open(temp_log_file, 'w', buffering=65536)
            except Exception as e:
                logger.warning("Failed to create log file, logs will only be in memory", job_id=job_id, error=str(e))
                temp_log_file = None

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
                nonlocal cancelled, last_commit_time, last_shown_file, speed_tracking, captured_exit_code
                try:
                    async for line in process.stdout:
                        if cancelled:
                            break

                        line_str = line.decode('utf-8', errors='replace').strip()

                        # Write to full log file (captures ALL logs for download)
                        if log_file_handle:
                            try:
                                log_file_handle.write(line_str + '\n')
                            except Exception:
                                pass  # Silently ignore write errors to avoid breaking backup

                        # Add to in-memory circular log buffer (for UI streaming)
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

                                    # Also capture exit code from warning messages (e.g., "terminating with warning status, rc 105")
                                    if levelname == 'WARNING' and 'rc ' in message:
                                        rc_match = re.search(r'rc\s+(\d+)', message)
                                        if rc_match:
                                            captured_rc = int(rc_match.group(1))
                                            # Store captured exit code for later status determination
                                            # This will be used if process.returncode is 0 but borg actually exited with a warning
                                            captured_exit_code = captured_rc
                                            logger.info("Captured exit code from log message",
                                                       job_id=job_id,
                                                       exit_code=captured_rc,
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

            # Use the actual exit code from the process, or fall back to captured code from logs
            # This handles cases where borg sends the exit code in log messages but process.returncode is 0
            actual_returncode = process.returncode
            if actual_returncode == 0 and captured_exit_code is not None and captured_exit_code != 0:
                # Process exited with 0 but logs indicated a different code (e.g., 105 for warnings)
                logger.info("Using exit code from log messages instead of process return code",
                           job_id=job_id,
                           process_returncode=actual_returncode,
                           captured_exit_code=captured_exit_code)
                actual_returncode = captured_exit_code

            # Update job status using modern exit codes (if not already cancelled)
            # 0 = success, 1 = warning (legacy), 2 = error (legacy)
            # Modern: 0 = success, 3-99 = errors, 100-127 = warnings
            if job.status == "cancelled":
                logger.info("Backup job was cancelled", job_id=job_id)
                job.completed_at = datetime.utcnow()
            elif actual_returncode == 0:
                job.status = "completed"
                job.progress = 100
                # Update archive statistics with final deduplicated size
                await self._update_archive_stats(db, job_id, repository, archive_name, env)
                # Update repository statistics after successful backup
                await self._update_repository_stats(db, repository, env)

                # Run post-backup hooks (script library or inline)
                post_hook_failed = False
                if repo_record:
                    logger.info("Executing post-backup hooks", job_id=job_id, repository=repository)
                    hook_result = await self._execute_hooks(
                        db=db,
                        repo_record=repo_record,
                        hook_type="post-backup",
                        backup_result="success",
                        job_id=job_id
                    )

                    # Add hook logs
                    if hook_result["execution_logs"]:
                        hook_logs.extend(hook_result["execution_logs"])

                    logger.info("Post-backup hooks completed",
                               scripts_executed=hook_result["scripts_executed"],
                               scripts_failed=hook_result["scripts_failed"],
                               using_library=hook_result["using_library"])

                    if not hook_result["success"]:
                        post_hook_failed = True
                        logger.warning("Post-backup hooks failed",
                                     job_id=job_id,
                                     scripts_failed=hook_result["scripts_failed"])
                        # Mark as failed if post-hooks fail
                        job.status = "failed"
                        job.error_message = f"Backup succeeded but post-backup hooks failed: {hook_result['scripts_failed']}/{hook_result['scripts_executed']} scripts failed"

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
            elif 100 <= actual_returncode <= 127:
                # Warning (modern exit code system)
                job.status = "completed_with_warnings"
                job.progress = 100
                job.error_message = f"Backup completed with warning (exit code {actual_returncode})"
                logger.warning("Backup completed with warning", job_id=job_id, exit_code=actual_returncode)
                # Update archive statistics with final deduplicated size
                await self._update_archive_stats(db, job_id, repository, archive_name, env)
                # Update repository statistics even with warnings
                await self._update_repository_stats(db, repository, env)

                # Run post-backup hooks even with warnings (script library or inline)
                post_hook_failed = False
                if repo_record:
                    logger.info("Executing post-backup hooks (warning case)", job_id=job_id, repository=repository)
                    hook_result = await self._execute_hooks(
                        db=db,
                        repo_record=repo_record,
                        hook_type="post-backup",
                        backup_result="warning",
                        job_id=job_id
                    )

                    # Add hook logs
                    if hook_result["execution_logs"]:
                        hook_logs.extend(hook_result["execution_logs"])

                    logger.info("Post-backup hooks completed (warning case)",
                               scripts_executed=hook_result["scripts_executed"],
                               scripts_failed=hook_result["scripts_failed"],
                               using_library=hook_result["using_library"])

                    if not hook_result["success"]:
                        post_hook_failed = True
                        logger.warning("Post-backup hooks failed",
                                     job_id=job_id,
                                     scripts_failed=hook_result["scripts_failed"])
                        # Mark as failed if post-hooks fail
                        job.status = "failed"
                        job.error_message = f"Backup succeeded with warning but post-backup hooks failed: {hook_result['scripts_failed']}/{hook_result['scripts_executed']} scripts failed"

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
                    # Send warning notification (backup completed with warnings but post-hook succeeded)
                    try:
                        stats = {
                            "original_size": job.original_size,
                            "compressed_size": job.compressed_size,
                            "deduplicated_size": job.deduplicated_size
                        }
                        await notification_service.send_backup_warning(
                            db, repository, archive_name, job.error_message, stats, job.completed_at
                        )
                    except Exception as e:
                        logger.warning("Failed to send backup warning notification", error=str(e))
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
                        exit_code=actual_returncode
                    )
                    error_parts.append(formatted_error)

                    # Add additional errors if present
                    if len(errors) > 1:
                        error_parts.append(f"\n\nAdditional errors encountered: {len(errors) - 1}")
                else:
                    # Fallback to simple exit code message
                    error_parts.append(format_error_message(
                        exit_code=actual_returncode
                    ))

                job.error_message = "\n".join(error_parts)

                # Log lock error for visibility
                if is_lock_error:
                    logger.warning("Backup failed due to lock timeout",
                                 job_id=job_id,
                                 repository=repository,
                                 msgid=primary_error['msgid'])

                # Run post-backup hooks on FAILURE (solves #85!)
                # Scripts with run_on='failure' or run_on='always' will execute
                if repo_record:
                    logger.info("Executing post-backup hooks (failure case)", job_id=job_id, repository=repository)
                    hook_result = await self._execute_hooks(
                        db=db,
                        repo_record=repo_record,
                        hook_type="post-backup",
                        backup_result="failure",
                        job_id=job_id
                    )

                    # Add hook logs
                    if hook_result["execution_logs"]:
                        hook_logs.extend(hook_result["execution_logs"])

                    logger.info("Post-backup hooks completed (failure case)",
                               scripts_executed=hook_result["scripts_executed"],
                               scripts_failed=hook_result["scripts_failed"],
                               using_library=hook_result["using_library"])

                    if not hook_result["success"]:
                        logger.warning("Post-backup hooks also failed",
                                     job_id=job_id,
                                     scripts_failed=hook_result["scripts_failed"])
                        # Append hook failure to error message
                        job.error_message += f"\n\nPost-backup hooks also failed: {hook_result['scripts_failed']}/{hook_result['scripts_executed']} scripts failed"
                    else:
                        logger.info("Post-backup hooks executed successfully despite backup failure", job_id=job_id)

            if job.completed_at is None:
                job.completed_at = datetime.utcnow()

            # CONFIGURABLE LOG SAVING: Check system settings for log save policy
            # Get log save policy from SystemSettings
            system_settings = db.query(SystemSettings).first()
            if not system_settings:
                system_settings = SystemSettings()
                db.add(system_settings)
                db.commit()

            log_save_policy = system_settings.log_save_policy or "failed_and_warnings"

            # Determine if logs should be saved based on policy
            should_save_logs = False

            if log_save_policy == "all_jobs":
                # Save logs for all jobs
                should_save_logs = True
            elif log_save_policy == "failed_and_warnings":
                # Save if job failed/cancelled OR has warnings
                combined_logs = hook_logs + log_buffer if hook_logs else log_buffer
                has_warnings = any('WARNING' in line or 'ERROR' in line for line in combined_logs)
                should_save_logs = (
                    job.status in ['failed', 'cancelled'] or
                    actual_returncode not in [0, None] or
                    has_warnings
                )
            elif log_save_policy == "failed_only":
                # Save only if job failed/cancelled
                should_save_logs = (
                    job.status in ['failed', 'cancelled'] or
                    actual_returncode not in [0, None]
                )

            # Close the log file handle
            if log_file_handle:
                try:
                    log_file_handle.close()
                except Exception:
                    pass

            # Handle log file based on policy
            if should_save_logs:
                try:
                    # Append hook logs to the full log file if we have them
                    if hook_logs and temp_log_file and temp_log_file.exists():
                        with open(temp_log_file, 'a') as f:
                            f.write('\n=== Hook Logs ===\n')
                            f.write('\n'.join(hook_logs))
                            f.write('\n')

                    # Use the temp log file as the permanent log file (contains ALL logs)
                    if temp_log_file and temp_log_file.exists():
                        job.log_file_path = str(temp_log_file)
                        job.has_logs = True
                        job.logs = f"Logs saved to: {temp_log_file.name}"

                        # Count lines in file for logging
                        try:
                            with open(temp_log_file, 'r') as f:
                                line_count = sum(1 for _ in f)
                        except Exception:
                            line_count = 0

                        logger.info("Full logs saved per policy",
                                    job_id=job_id,
                                    status=job.status,
                                    policy=log_save_policy,
                                    log_file=str(temp_log_file),
                                    log_lines=line_count)
                    else:
                        # Fallback: save buffer if no temp file
                        fallback_log_file = self.log_dir / f"backup_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                        combined_logs = hook_logs + log_buffer if hook_logs else log_buffer
                        fallback_log_file.write_text('\n'.join(combined_logs))
                        job.log_file_path = str(fallback_log_file)
                        job.has_logs = True
                        job.logs = f"Logs saved to: {fallback_log_file.name}"
                        logger.warning("Using buffer fallback for logs", job_id=job_id, log_lines=len(combined_logs))
                except Exception as e:
                    job.has_logs = False
                    job.logs = f"Failed to save logs: {str(e)}"
                    logger.error("Failed to save log file", job_id=job_id, error=str(e))
            else:
                # Delete temp log file since policy says not to save
                if temp_log_file and temp_log_file.exists():
                    try:
                        temp_log_file.unlink()
                        logger.debug("Deleted temp log file per policy", job_id=job_id, policy=log_save_policy)
                    except Exception as e:
                        logger.warning("Failed to delete temp log file", job_id=job_id, error=str(e))

                # Save hook logs in database for reference if we have them
                if hook_logs:
                    job.logs = "\n".join(hook_logs)
                    logger.info("Backup completed, only hook logs saved", job_id=job_id, policy=log_save_policy)
                else:
                    job.logs = None
                    logger.info("Backup completed, no logs saved per policy", job_id=job_id, policy=log_save_policy)

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

            # Close log file handle if open
            if 'log_file_handle' in locals() and log_file_handle:
                try:
                    log_file_handle.close()
                except Exception:
                    pass

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
            # Ensure log file handle is closed
            if 'log_file_handle' in locals() and log_file_handle:
                try:
                    log_file_handle.close()
                    logger.debug("Closed log file handle", job_id=job_id)
                except Exception:
                    pass

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

            # Clean up SSH mounts (unmount all SSHFS mounts for this job)
            try:
                await self._cleanup_ssh_mounts(job_id)
            except Exception as e:
                logger.error("Failed to cleanup SSH mounts", job_id=job_id, error=str(e))

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
