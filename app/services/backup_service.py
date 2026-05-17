from __future__ import annotations

import asyncio
import os
import json
import re
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import BackupJob, Repository, RepositoryScript, SystemSettings
from app.database.database import SessionLocal
from app.config import settings
from app.core.borg_router import BorgRouter
from app.core.borg_errors import format_error_message, is_lock_error
from app.services.notification_service import notification_service
from app.services.script_executor import execute_script
from app.services.script_library_executor import ScriptLibraryExecutor
from app.services.mqtt_service import mqtt_service
from app.services.restore_check_canary import (
    ensure_restore_canary,
    should_include_restore_canary,
    to_restore_canary_archive_source_path,
)
from app.utils.ssh_paths import resolve_sshfs_source_path
from app.utils.source_locations import (
    decode_source_locations,
    flatten_source_locations,
)
from app.utils.borg_env import (
    build_repository_borg_env,
    cleanup_temp_key_file,
    setup_borg_env,
)
from app.utils.ssh_utils import (
    resolve_repo_ssh_key_file,  # noqa: F401
)  # Backward-compatible patch target for tests

logger = structlog.get_logger()


class BackupService:
    """Service for executing backups with real-time log streaming"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running backup processes by job_id
        self.error_msgids = {}  # Track error message IDs by job_id
        self.log_buffers = {}  # Track in-memory log buffers by job_id (for running jobs)
        self.ssh_mounts = {}  # Track SSH mount IDs by job_id: {job_id: [mount_id, ...]}

    def _resolve_grouped_source_paths(
        self, db: Session, source_locations: list[dict]
    ) -> list[str]:
        from app.database.models import SSHConnection

        source_paths: list[str] = []
        for location in source_locations:
            paths = location.get("paths") or []
            if location.get("source_type") == "remote":
                connection_id = location.get("source_ssh_connection_id")
                connection = (
                    db.query(SSHConnection)
                    .filter(SSHConnection.id == connection_id)
                    .first()
                )
                if not connection:
                    raise ValueError(
                        f"SSH connection {connection_id} not found for remote source"
                    )
                source_paths.extend(
                    f"ssh://{connection.username}@{connection.host}:{connection.port}"
                    f"{resolve_sshfs_source_path(path, connection.default_path)}"
                    for path in paths
                )
            else:
                source_paths.extend(paths)

        return source_paths

    def _get_operation_timeouts(self, db: Session = None) -> dict:
        """
        Get operation timeouts from database settings, with fallback to config values.
        UI settings take priority over environment variables.

        Returns:
            dict with keys: info_timeout, list_timeout, init_timeout, backup_timeout
        """
        timeouts = {
            "info_timeout": settings.borg_info_timeout,
            "list_timeout": settings.borg_list_timeout,
            "backup_timeout": settings.backup_timeout,
            "source_size_timeout": settings.source_size_timeout,
        }

        try:
            # Use provided session or create one
            close_session = False
            if db is None:
                db = SessionLocal()
                close_session = True

            try:
                system_settings = db.query(SystemSettings).first()
                if system_settings:
                    # Override with DB values if they exist
                    if system_settings.info_timeout:
                        timeouts["info_timeout"] = system_settings.info_timeout
                    if system_settings.list_timeout:
                        timeouts["list_timeout"] = system_settings.list_timeout
                    if system_settings.backup_timeout:
                        timeouts["backup_timeout"] = system_settings.backup_timeout
                    if system_settings.source_size_timeout:
                        timeouts["source_size_timeout"] = (
                            system_settings.source_size_timeout
                        )
            finally:
                if close_session:
                    db.close()
        except Exception as e:
            logger.warning(
                "Failed to get timeouts from DB, using config defaults", error=str(e)
            )

        return timeouts

    async def _run_hook(
        self, script: str, hook_name: str, timeout: int, job_id: int
    ) -> dict:
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
        logger.info(
            f"Running {hook_name} hook", job_id=job_id, script_preview=script[:100]
        )

        # Use the shared script executor (same as test endpoint)
        # This guarantees identical execution environment and behavior
        result = await execute_script(
            script=script,
            timeout=float(timeout),
            env=os.environ.copy(),
            context=f"{hook_name} (job {job_id})",
        )

        # Map result format to what the backup service expects
        return {
            "success": result["success"],
            "returncode": result["exit_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }

    async def _execute_hooks(
        self,
        db: Session,
        repo_record: Repository,
        hook_type: str,  # 'pre-backup' or 'post-backup'
        backup_result: str = None,  # 'success', 'failure', 'warning' (for post-backup)
        job_id: int = None,
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
        has_library_scripts = (
            db.query(RepositoryScript)
            .filter(
                RepositoryScript.repository_id == repo_record.id,
                RepositoryScript.hook_type == hook_type,
                RepositoryScript.enabled == True,
            )
            .count()
            > 0
        )

        if has_library_scripts:
            # Use script library
            logger.info(
                "Using script library for hooks",
                repository_id=repo_record.id,
                hook_type=hook_type,
            )

            executor = ScriptLibraryExecutor(db)
            result = await executor.execute_hooks(
                repository_id=repo_record.id,
                hook_type=hook_type,
                backup_result=backup_result,
                backup_job_id=job_id,
            )

            return {
                "success": result["success"],
                "execution_logs": result["execution_logs"],
                "scripts_executed": result["scripts_executed"],
                "scripts_failed": result["scripts_failed"],
                "using_library": True,
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
                    "using_library": False,
                }

            logger.info(
                "Using inline script (legacy)",
                repository_id=repo_record.id,
                hook_type=hook_type,
                backup_result=backup_result,
            )

            # Execute inline script
            executor = ScriptLibraryExecutor(db)
            # Use appropriate timeout based on hook type
            timeout = (
                repo_record.pre_hook_timeout
                if hook_type == "pre-backup"
                else repo_record.post_hook_timeout
            ) or 300
            result = await executor.execute_inline_script(
                script_content=inline_script,
                script_type=hook_type,
                timeout=timeout,
                repository=repo_record,
                backup_job_id=job_id,
                backup_result=backup_result,
            )

            return {
                "success": result["success"],
                "execution_logs": result["logs"],
                "scripts_executed": 1,
                "scripts_failed": 0 if result["success"] else 1,
                "using_library": False,
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

                logger.info(
                    "Starting log rotation",
                    max_age_days=max_age_days,
                    max_total_size_mb=max_total_size_mb,
                )

                # Use log_manager for combined cleanup (age + size)
                result = log_manager.cleanup_logs_combined(
                    db=db,
                    max_age_days=max_age_days,
                    max_total_size_mb=max_total_size_mb,
                    dry_run=False,
                )

                if result["success"]:
                    logger.info(
                        "Log rotation completed successfully",
                        total_deleted=result["total_deleted_count"],
                        size_freed_mb=result["total_deleted_size_mb"],
                        age_deleted=result["age_cleanup"]["deleted_count"],
                        size_deleted=result["size_cleanup"]["deleted_count"],
                    )
                else:
                    logger.warning(
                        "Log rotation completed with errors",
                        total_deleted=result["total_deleted_count"],
                        size_freed_mb=result["total_deleted_size_mb"],
                        errors=result["total_errors"],
                    )

            finally:
                if close_db:
                    db.close()

        except Exception as e:
            logger.error("Log rotation failed", error=str(e))

    def get_log_buffer(self, job_id: int, tail_lines: int = 500) -> tuple[list, bool]:
        """
        Get the last N lines from the in-memory log buffer for a running job.

        Args:
            job_id: The backup job ID
            tail_lines: Number of lines to return from the end of buffer (default 500)

        Returns:
            Tuple of (log_lines, buffer_exists)
            - log_lines: List of log lines (most recent tail_lines lines)
            - buffer_exists: True if buffer was created (even if empty), False if job hasn't started yet
        """
        buffer_exists = job_id in self.log_buffers
        buffer = self.log_buffers.get(job_id, [])

        # Debug logging
        logger.info(
            "get_log_buffer called",
            job_id=job_id,
            buffer_exists=buffer_exists,
            buffer_size=len(buffer),
            all_job_ids=list(self.log_buffers.keys()),
        )

        # Return last N lines (tail) and existence flag
        tail = buffer[-tail_lines:] if len(buffer) > tail_lines else buffer
        return (tail, buffer_exists)

    async def _update_archive_stats(
        self,
        db: Session,
        job_id: int,
        repository_path: str,
        archive_name: str,
        env: dict,
    ):
        """Update backup job with final archive statistics"""
        try:
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if not job:
                logger.warning("Job not found for stats update", job_id=job_id)
                return

            repo_record = (
                db.query(Repository).filter(Repository.path == repository_path).first()
            )
            if not repo_record:
                logger.warning(
                    "Repository record not found for archive stats update",
                    repository=repository_path,
                )
                return
            router = BorgRouter(repo_record)

            # Get timeouts from DB settings (with fallback to config)
            timeouts = self._get_operation_timeouts(db)

            info_cmd = router.build_archive_info_command(repository_path, archive_name)
            info_process = await asyncio.create_subprocess_exec(
                *info_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            info_stdout, info_stderr = await asyncio.wait_for(
                info_process.communicate(), timeout=timeouts["info_timeout"]
            )

            if info_process.returncode == 0:
                try:
                    info_data = json.loads(info_stdout.decode())
                    archives = info_data.get("archives", [])
                    if archives:
                        archive_info = archives[0]
                        stats = archive_info.get("stats", {})

                        # Update job with final statistics
                        job.original_size = stats.get(
                            "original_size", job.original_size or 0
                        )
                        job.compressed_size = stats.get(
                            "compressed_size", job.compressed_size or 0
                        )
                        job.deduplicated_size = stats.get(
                            "deduplicated_size", job.deduplicated_size or 0
                        )
                        job.nfiles = stats.get("nfiles", job.nfiles or 0)

                        db.commit()
                        logger.info(
                            "Updated archive statistics",
                            job_id=job_id,
                            archive=archive_name,
                            original_size=job.original_size,
                            compressed_size=job.compressed_size,
                            deduplicated_size=job.deduplicated_size,
                            nfiles=job.nfiles,
                        )
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Failed to parse borg info output for archive",
                        job_id=job_id,
                        error=str(e),
                    )
            else:
                logger.warning(
                    "Failed to get archive info",
                    job_id=job_id,
                    archive=archive_name,
                    returncode=info_process.returncode,
                )

        except asyncio.TimeoutError:
            logger.warning("Timeout while updating archive stats", job_id=job_id)
        except Exception as e:
            logger.error("Failed to update archive stats", job_id=job_id, error=str(e))

    async def _update_repository_stats(
        self, db: Session, repository_path: str, env: dict
    ):
        """Update repository statistics after a successful backup"""
        try:
            repo_record = (
                db.query(Repository).filter(Repository.path == repository_path).first()
            )
            if not repo_record:
                logger.warning(
                    "Repository record not found for stats update",
                    repository=repository_path,
                )
                return
            router = BorgRouter(repo_record)

            # Get timeouts from DB settings (with fallback to config)
            timeouts = self._get_operation_timeouts(db)

            list_cmd = router.build_repo_list_command(repository_path)
            list_process = await asyncio.create_subprocess_exec(
                *list_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            list_stdout, list_stderr = await asyncio.wait_for(
                list_process.communicate(), timeout=timeouts["list_timeout"]
            )

            if list_process.returncode == 0:
                try:
                    archives_data = json.loads(list_stdout.decode())
                    archive_count = len(archives_data.get("archives", []))
                    repo_record.archive_count = archive_count
                    logger.info(
                        "Updated archive count",
                        repository=repository_path,
                        count=archive_count,
                    )
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse borg list output", error=str(e))

            info_cmd = router.build_repo_info_command(repository_path)
            info_process = await asyncio.create_subprocess_exec(
                *info_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            info_stdout, info_stderr = await asyncio.wait_for(
                info_process.communicate(), timeout=timeouts["info_timeout"]
            )

            if info_process.returncode == 0:
                try:
                    info_data = json.loads(info_stdout.decode())
                    cache_stats = info_data.get("cache", {}).get("stats", {})

                    # Get total repository size (unique_size is deduplicated size)
                    unique_size = cache_stats.get("unique_size", 0)
                    if unique_size > 0:
                        # Format size to human readable
                        repo_record.total_size = self._format_bytes(unique_size)
                        logger.info(
                            "Updated repository size",
                            repository=repository_path,
                            size=repo_record.total_size,
                        )
                except json.JSONDecodeError as e:
                    logger.warning("Failed to parse borg info output", error=str(e))

            # Update last_backup timestamp
            repo_record.last_backup = datetime.utcnow()

            db.commit()
            logger.info("Repository statistics updated", repository=repository_path)

            # Publish a full DB-derived MQTT snapshot immediately after stats changes.
            mqtt_service.sync_state_with_db(db, reason="repository stats updated")

        except asyncio.TimeoutError:
            logger.warning(
                "Timeout while updating repository stats", repository=repository_path
            )
        except Exception as e:
            logger.error(
                "Failed to update repository stats",
                repository=repository_path,
                error=str(e),
            )

    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes to human readable string"""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"

    async def _calculate_source_size(
        self, source_paths: list[str], exclude_patterns: list[str] = None
    ) -> int:
        """Calculate total size of source directories in bytes.

        Delegates to calculate_path_size_bytes with the configured timeout.
        Supports local paths and SSH URLs; applies Borg-compatible exclude patterns.
        """
        from app.utils.fs import calculate_path_size_bytes

        timeout = self._get_operation_timeouts()["source_size_timeout"]
        return await calculate_path_size_bytes(source_paths, exclude_patterns, timeout)

    async def _calculate_and_update_size_background(
        self, job_id: int, source_paths: list[str], exclude_patterns: list[str] = None
    ):
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

            logger.info(
                "Background size calculation started",
                job_id=job_id,
                source_paths=source_paths,
                path_count=len(source_paths),
                exclude_count=len(exclude_patterns),
            )
            total_expected_size = await self._calculate_source_size(
                source_paths, exclude_patterns
            )

            if total_expected_size > 0:
                # Update the job record with the calculated size
                db = SessionLocal()
                try:
                    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
                    if job and job.status == "running":
                        job.total_expected_size = total_expected_size
                        db.commit()
                        logger.info(
                            "Background size calculation completed and job updated",
                            job_id=job_id,
                            total_expected_size=total_expected_size,
                            size_formatted=self._format_bytes(total_expected_size),
                        )
                    else:
                        logger.info(
                            "Background size calculation completed but job no longer running",
                            job_id=job_id,
                        )
                finally:
                    db.close()
            else:
                logger.warning(
                    "Background size calculation completed but returned 0 - check paths accessibility",
                    job_id=job_id,
                    source_paths=source_paths,
                    message="ETA and progress percentage will not be available",
                )

        except Exception as e:
            logger.error(
                "Error in background size calculation",
                job_id=job_id,
                error=str(e),
                error_type=type(e).__name__,
                source_paths=source_paths,
            )

    def _parse_ssh_url(self, ssh_url: str) -> dict:
        """
        Parse SSH URL to extract connection details
        Format: ssh://user@host:port/path
        Returns: dict with keys: username, host, port, path
        """
        match = re.match(r"ssh://([^@]+)@([^:]+):(\d+)(/.*)", ssh_url)
        if match:
            username, host, port, path = match.groups()
            return {"username": username, "host": host, "port": port, "path": path}
        return None

    # OLD IMPLEMENTATION - Kept for rollback (DO NOT USE)
    # This method had a critical bug: missing SSH key authentication in SSHFS
    # Use mount_service.mount_ssh_directory() instead
    async def _mount_ssh_path_OLD_BROKEN(self, ssh_url: str, job_id: int) -> str:
        """
        Mount an SSH path via SSHFS to a temporary directory
        Returns: local mount point path, or None if mount failed
        """
        try:
            # Check if SSHFS is available
            try:
                check_process = await asyncio.create_subprocess_exec(
                    "which",
                    "sshfs",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await check_process.communicate()
                if check_process.returncode != 0:
                    logger.error(
                        "SSHFS not found - cannot mount remote paths",
                        ssh_url=ssh_url,
                        job_id=job_id,
                        hint="Install SSHFS package or rebuild Docker image with SSHFS support",
                    )
                    return None
            except Exception as check_error:
                logger.error(
                    "Error checking for SSHFS", error=str(check_error), job_id=job_id
                )
                return None

            # Parse SSH URL
            parsed = self._parse_ssh_url(ssh_url)
            if not parsed:
                logger.error("Failed to parse SSH URL", ssh_url=ssh_url, job_id=job_id)
                return None

            # Create temporary mount point with directory structure
            # Extract the last component of the remote path for a clean archive structure
            remote_path = parsed["path"]
            path_basename = os.path.basename(remote_path.rstrip("/"))

            # Create a temporary root directory
            temp_root = tempfile.mkdtemp(prefix=f"borg_backup_root_{job_id}_")

            # Create the mount point inside with the remote directory name
            mount_dir = os.path.join(temp_root, path_basename)
            os.makedirs(mount_dir, exist_ok=True)

            logger.info(
                "Created temporary mount point",
                temp_root=temp_root,
                mount_point=mount_dir,
                remote_basename=path_basename,
                ssh_url=ssh_url,
                job_id=job_id,
            )

            # Get current user's UID and GID for mount options
            current_uid = os.getuid()
            current_gid = os.getgid()

            # Build SSHFS command
            cmd = [
                "sshfs",
                f"{parsed['username']}@{parsed['host']}:{parsed['path']}",
                mount_dir,
                "-p",
                parsed["port"],
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "ConnectTimeout=30",
                "-o",
                "ServerAliveInterval=15",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "reconnect",
                "-o",
                "follow_symlinks",
                "-o",
                "allow_other",  # Allow non-root user to access mount
                "-o",
                f"uid={current_uid}",  # Set mount owner to current user
                "-o",
                f"gid={current_gid}",  # Set mount group to current user's group
                "-o",
                "workaround=rename",  # Compatibility workaround for SFTP servers
            ]

            logger.info(
                "Mounting SSH path via SSHFS", command=" ".join(cmd), job_id=job_id
            )

            # Execute mount command in background (SSHFS daemonizes)
            # We'll check if the mount succeeded rather than waiting for the process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
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
                        "ls",
                        "-A",
                        mount_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    test_stdout, test_stderr = await asyncio.wait_for(
                        test_process.communicate(), timeout=2
                    )

                    if test_process.returncode == 0:
                        logger.info(
                            "Successfully mounted and verified SSH path",
                            temp_root=temp_root,
                            mount_point=mount_dir,
                            ssh_url=ssh_url,
                            attempt=attempt + 1,
                            job_id=job_id,
                        )

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
                            stderr_msg = (
                                test_stderr.decode().strip()
                                if test_stderr
                                else "Unknown error"
                            )
                            logger.error(
                                "Mount verification failed after retries",
                                ssh_url=ssh_url,
                                mount_point=mount_dir,
                                test_stderr=stderr_msg,
                                job_id=job_id,
                            )
                            await self._unmount_ssh_path(mount_dir, job_id)
                            cleanup_on_failure()
                            return None

                except asyncio.TimeoutError:
                    # Verification timed out, wait and retry if not last attempt
                    if attempt < 4:
                        await asyncio.sleep(1)
                    else:
                        logger.error(
                            "Timeout verifying mount after retries",
                            ssh_url=ssh_url,
                            mount_point=mount_dir,
                            job_id=job_id,
                        )
                        await self._unmount_ssh_path(mount_dir, job_id)
                        cleanup_on_failure()
                        return None
                except Exception as e:
                    logger.error(
                        "Error verifying mount",
                        ssh_url=ssh_url,
                        mount_point=mount_dir,
                        error=str(e),
                        job_id=job_id,
                    )
                    if attempt == 4:
                        await self._unmount_ssh_path(mount_dir, job_id)
                        cleanup_on_failure()
                        return None
                    await asyncio.sleep(1)

        except asyncio.TimeoutError:
            logger.error(
                "Timeout while mounting SSH path", ssh_url=ssh_url, job_id=job_id
            )
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
                job_id=job_id,
            )
            try:
                import shutil

                shutil.rmtree(temp_root, ignore_errors=True)
            except:
                pass
            return None
        except Exception as e:
            logger.error(
                "Error mounting SSH path", ssh_url=ssh_url, error=str(e), job_id=job_id
            )
            try:
                import shutil

                shutil.rmtree(temp_root, ignore_errors=True)
            except:
                pass
            return None

    # OLD IMPLEMENTATION - Kept for rollback (DO NOT USE)
    async def _unmount_ssh_path_OLD(self, mount_point: str, job_id: int):
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
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)

            if process.returncode == 0:
                logger.info(
                    "Successfully unmounted SSH path",
                    mount_point=mount_point,
                    job_id=job_id,
                )
                # Remove the empty mount point directory
                try:
                    os.rmdir(mount_point)
                    logger.debug(
                        "Removed mount point directory",
                        mount_point=mount_point,
                        job_id=job_id,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to remove mount point directory",
                        mount_point=mount_point,
                        error=str(e),
                        job_id=job_id,
                    )
            else:
                logger.error(
                    "Failed to unmount SSH path",
                    mount_point=mount_point,
                    stderr=stderr.decode(),
                    returncode=process.returncode,
                    job_id=job_id,
                )

        except asyncio.TimeoutError:
            logger.error(
                "Timeout while unmounting SSH path",
                mount_point=mount_point,
                job_id=job_id,
            )
        except Exception as e:
            logger.error(
                "Error unmounting SSH path",
                mount_point=mount_point,
                error=str(e),
                job_id=job_id,
            )

    async def _prepare_source_paths(
        self, source_paths: list[str], job_id: int, source_connection_id: int = None
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """
        Prepare source paths for backup by mounting SSH URLs via SSHFS
        Uses the new mount_service with proper SSH key authentication.

        Optimized to mount multiple paths from the same SSH connection under a single shared temp root,
        which allows proper working directory usage and avoids exclude pattern conflicts.

        Args:
            source_paths: List of paths to prepare (may include SSH URLs)
            job_id: Backup job ID
            source_connection_id: SSH connection ID for remote data source (if applicable)

        Returns: tuple of (processed_paths, ssh_mount_info)
            - processed_paths: list of paths to backup (SSH URLs replaced with relative paths from temp_root)
            - ssh_mount_info: list of (temp_root, relative_path) tuples for SSH mounts
                Where relative_path is the path relative to temp_root that preserves original structure
        """
        from app.services.mount_service import mount_service
        from app.database.models import SSHConnection
        from collections import defaultdict

        processed_paths = []
        mount_ids = []
        ssh_mount_info = []  # Track (temp_root, relative_path) for SSH mounts

        db = SessionLocal()
        try:
            # First pass: Parse and group SSH paths by connection_id
            ssh_paths_by_connection = defaultdict(
                list
            )  # connection_id -> [(ssh_url, parsed_data), ...]
            local_paths = []

            for path in source_paths:
                if path.startswith("ssh://"):
                    # Parse SSH URL: ssh://user@host:port/path
                    parsed = self._parse_ssh_url(path)
                    if not parsed:
                        logger.error(
                            "Failed to parse SSH URL", path=path, job_id=job_id
                        )
                        continue

                    # Use provided connection_id if available, otherwise lookup by host/user/port
                    connection = None
                    if source_connection_id:
                        connection = (
                            db.query(SSHConnection)
                            .filter(SSHConnection.id == source_connection_id)
                            .first()
                        )
                        if not connection:
                            logger.error(
                                "SSH connection not found by ID",
                                connection_id=source_connection_id,
                                path=path,
                                job_id=job_id,
                            )
                            continue
                    else:
                        # Fallback: Find SSHConnection matching host/user/port
                        connection = (
                            db.query(SSHConnection)
                            .filter(
                                SSHConnection.host == parsed["host"],
                                SSHConnection.username == parsed["username"],
                                SSHConnection.port == int(parsed["port"]),
                            )
                            .first()
                        )

                        if not connection:
                            logger.error(
                                "No SSH connection found for host",
                                host=parsed["host"],
                                username=parsed["username"],
                                port=parsed["port"],
                                path=path,
                                job_id=job_id,
                            )
                            continue

                    ssh_paths_by_connection[connection.id].append(
                        (path, parsed, connection)
                    )
                else:
                    # Local path - use as-is
                    local_paths.append(path)

            # Second pass: Mount SSH paths. Reuse the first SSHFS temp root across
            # source connections so Borg can run from one cwd and store relative
            # remote paths instead of /tmp/sshfs_mount_* implementation paths.
            shared_ssh_temp_root = None
            for connection_id, paths_data in ssh_paths_by_connection.items():
                remote_paths = [parsed["path"] for _, parsed, _ in paths_data]
                connection = paths_data[0][2]  # Get connection from first item

                logger.info(
                    "Mounting SSH paths from same connection",
                    connection_id=connection_id,
                    host=connection.host,
                    path_count=len(remote_paths),
                    remote_paths=remote_paths,
                    job_id=job_id,
                )

                try:
                    # Mount all paths from this connection under a single shared temp root
                    mount_kwargs = {
                        "connection_id": connection_id,
                        "remote_paths": remote_paths,
                        "job_id": job_id,
                    }
                    if shared_ssh_temp_root is not None:
                        mount_kwargs["temp_root"] = shared_ssh_temp_root

                    (
                        temp_root,
                        mount_info_list,
                    ) = await mount_service.mount_ssh_paths_shared(**mount_kwargs)
                    if shared_ssh_temp_root is None:
                        shared_ssh_temp_root = temp_root

                    # Process mount results
                    for (mount_id, relative_path), (original_url, parsed, _) in zip(
                        mount_info_list, paths_data
                    ):
                        processed_paths.append(relative_path)
                        mount_ids.append(mount_id)
                        ssh_mount_info.append((temp_root, relative_path))

                        logger.info(
                            "Mounted SSH path for backup (shared temp root)",
                            original=original_url,
                            temp_root=temp_root,
                            relative_path=relative_path,
                            mount_id=mount_id,
                            connection_id=connection_id,
                            job_id=job_id,
                        )

                except Exception as e:
                    logger.error(
                        "Failed to mount SSH paths from connection",
                        connection_id=connection_id,
                        path_count=len(remote_paths),
                        error=str(e),
                        error_type=type(e).__name__,
                        job_id=job_id,
                    )
                    # Skip all paths from this connection

            # Add local paths at the end. Borg UI's managed restore canary is a
            # local path, but when the backup cwd is an SSHFS root we stage that
            # tiny generated payload under the same cwd so it still archives as
            # .borg-ui/restore-canaries/... instead of an absolute data-dir path.
            prepared_local_paths = []
            for local_path in local_paths:
                canary_archive_path = to_restore_canary_archive_source_path(
                    local_path, settings.data_dir
                )
                if canary_archive_path and shared_ssh_temp_root:
                    source = Path(local_path)
                    target = Path(shared_ssh_temp_root) / canary_archive_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                    if source.is_dir():
                        shutil.copytree(source, target)
                    else:
                        shutil.copy2(source, target)
                    prepared_local_paths.append(canary_archive_path)
                    logger.info(
                        "Staged restore canary under SSH backup cwd",
                        source=str(source),
                        staged_path=str(target),
                        archive_path=canary_archive_path,
                        job_id=job_id,
                    )
                else:
                    prepared_local_paths.append(local_path)

            processed_paths.extend(prepared_local_paths)

            # Store mount_ids for cleanup
            if mount_ids:
                self.ssh_mounts[job_id] = mount_ids

            logger.info(
                "Source paths prepared",
                total_paths=len(source_paths),
                ssh_path_count=len(ssh_mount_info),
                local_path_count=len(local_paths),
                connection_count=len(ssh_paths_by_connection),
                job_id=job_id,
            )

            return processed_paths, ssh_mount_info

        finally:
            db.close()

    async def _cleanup_ssh_mounts(self, job_id: int):
        """
        Cleanup all SSH mounts for a job using mount_service

        NOTE: mount_ssh_paths_shared() returns duplicate mount_ids when multiple files
        share the same parent directory. We deduplicate before unmounting to avoid
        trying to unmount the same mount multiple times.

        Example:
          - Backup: /home/user/file1.txt, /home/user/file2.txt
          - mount_ssh_paths_shared returns: [(mount_id_A, path1), (mount_id_A, path2)]
          - self.ssh_mounts[job_id] = [mount_id_A, mount_id_A]
          - We deduplicate to: [mount_id_A] before unmounting
        """
        from app.services.mount_service import mount_service

        if job_id not in self.ssh_mounts:
            return

        mount_ids = self.ssh_mounts[job_id]

        # CRITICAL: Deduplicate mount_ids before unmounting
        # mount_ssh_paths_shared() reuses mount_ids for files in the same parent,
        # so the list can contain duplicates (e.g., [id1, id1, id1, id2, id2])
        unique_mount_ids = list(
            dict.fromkeys(mount_ids)
        )  # Preserves order, removes duplicates

        logger.info(
            "Cleaning up SSH mounts",
            job_id=job_id,
            total_mount_refs=len(mount_ids),
            unique_mounts=len(unique_mount_ids),
        )

        if len(unique_mount_ids) < len(mount_ids):
            logger.debug(
                "Deduplicated mount_ids (multiple files shared same parent)",
                original_count=len(mount_ids),
                unique_count=len(unique_mount_ids),
                duplicates_removed=len(mount_ids) - len(unique_mount_ids),
                job_id=job_id,
            )

        # Get mount info for all unique mounts and sort by path depth (deepest first)
        mount_infos = []
        for mount_id in unique_mount_ids:
            mount_info = mount_service.get_mount(mount_id)
            if mount_info:
                mount_infos.append((mount_id, mount_info))
            else:
                logger.warning(
                    "Mount not found in active mounts", mount_id=mount_id, job_id=job_id
                )

        # Sort by mount point path length (longer = deeper = unmount first)
        # This correctly handles parent-child relationships:
        # - /tmp/.../home/karanhudia/test-backup-source (longer)
        # - /tmp/.../home/karanhudia (shorter, is parent, unmount last)
        mount_infos.sort(key=lambda x: len(x[1].mount_point), reverse=True)

        logger.debug(
            "Unmounting in depth order",
            job_id=job_id,
            order=[mi.mount_point for _, mi in mount_infos],
        )

        # Unmount in sorted order (deepest first)
        for mount_id, mount_info in mount_infos:
            try:
                success = await mount_service.unmount(mount_id)
                if success:
                    logger.debug(
                        "Successfully unmounted",
                        mount_id=mount_id,
                        mount_point=mount_info.mount_point,
                        job_id=job_id,
                    )
                else:
                    logger.warning(
                        "Failed to unmount",
                        mount_id=mount_id,
                        mount_point=mount_info.mount_point,
                        job_id=job_id,
                    )
            except Exception as e:
                logger.error(
                    "Error during unmount",
                    mount_id=mount_id,
                    mount_point=mount_info.mount_point,
                    error=str(e),
                    job_id=job_id,
                )

        # Remove from tracking
        del self.ssh_mounts[job_id]

    def _resolve_backup_command_paths(
        self,
        processed_source_paths: list[str],
        ssh_mount_info: list[tuple[str, str]],
        job_id: int,
    ) -> tuple[list[str], str | None]:
        backup_cwd = None
        backup_paths = processed_source_paths

        if ssh_mount_info:
            ssh_path_count = len(ssh_mount_info)
            temp_roots = list(
                dict.fromkeys(temp_root for temp_root, _ in ssh_mount_info)
            )

            if len(temp_roots) == 1:
                backup_cwd = temp_roots[0]
                backup_paths = [
                    relative_path for _, relative_path in ssh_mount_info
                ] + processed_source_paths[ssh_path_count:]
                logger.info(
                    "Using cwd for SSH mount backup (preserves original path structure)",
                    cwd=backup_cwd,
                    backup_paths=backup_paths,
                    job_id=job_id,
                )
            else:
                logger.warning(
                    "Multiple SSH mounts with different temp roots - using absolute paths",
                    temp_root_count=len(temp_roots),
                    job_id=job_id,
                )
                backup_paths = [
                    os.path.join(temp_root, relative_path)
                    for temp_root, relative_path in ssh_mount_info
                ]
                backup_paths.extend(processed_source_paths[ssh_path_count:])

        rewritten_paths = []
        has_canary_path = False
        for path in backup_paths:
            canary_archive_path = to_restore_canary_archive_source_path(
                path, settings.data_dir
            )
            if canary_archive_path:
                rewritten_paths.append(canary_archive_path)
                has_canary_path = True
            else:
                rewritten_paths.append(path)

        if has_canary_path:
            backup_paths = rewritten_paths
            if backup_cwd is None:
                backup_cwd = str(Path(settings.data_dir))
                logger.info(
                    "Using hidden archive path for restore canary",
                    cwd=backup_cwd,
                    job_id=job_id,
                )
            else:
                logger.info(
                    "Using hidden archive path for restore canary with existing backup cwd",
                    cwd=backup_cwd,
                    job_id=job_id,
                )

        return backup_paths, backup_cwd

    async def execute_backup(
        self,
        job_id: int,
        repository: str,
        db: Session = None,
        archive_name: str = None,
        skip_hooks: bool = False,
        source_directories: list[str] = None,
        source_ssh_connection_id: int = None,
        source_locations: list[dict] = None,
        exclude_patterns_override: list[str] = None,
        compression_override: str = None,
        custom_flags_override: str = None,
        upload_ratelimit_kib: int = None,
    ):
        """Execute backup using borg directly for better control

        Args:
            job_id: Backup job ID
            repository: Repository path
            db: Database session (optional, will create new if not provided)
            archive_name: Optional custom archive name (if None, will use default manual-backup naming)
            skip_hooks: If True, skip pre/post-backup hook execution (used by multi-repo schedules that
                        manage hook execution explicitly to avoid running scripts twice)
            source_directories: Optional source path override for backup plans.
            source_ssh_connection_id: Optional SSH source connection for source_directories.
            source_locations: Optional grouped source path override for backup plans.
            exclude_patterns_override: Optional exclude pattern override for backup plans.
            compression_override: Optional compression override for backup plans.
            custom_flags_override: Optional custom flags override for backup plans.
            upload_ratelimit_kib: Optional Borg upload rate limit in KiB/s.
        """

        # Use provided session or create a new one
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        temp_key_file = None  # Track SSH key file for cleanup

        try:
            # Get job
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if not job:
                logger.error("Job not found", job_id=job_id)
                return

            # Get job/schedule name for notifications
            job_name = None
            if job.scheduled_job_id:
                from app.database.models import ScheduledJob

                scheduled_job = (
                    db.query(ScheduledJob)
                    .filter(ScheduledJob.id == job.scheduled_job_id)
                    .first()
                )
                if scheduled_job:
                    job_name = scheduled_job.name

            # Check if this is a remote backup
            if job.execution_mode == "remote_ssh":
                logger.info("Delegating to remote backup service", job_id=job_id)
                from app.services.remote_backup_service import remote_backup_service

                # Get repository record
                repo_record = (
                    db.query(Repository).filter(Repository.path == repository).first()
                )
                if not repo_record:
                    raise Exception(f"Repository not found: {repository}")

                remote_source_paths = (
                    flatten_source_locations(source_locations)
                    if source_locations is not None
                    else source_directories
                    if source_directories is not None
                    else json.loads(repo_record.source_directories or "[]")
                )
                remote_exclude_patterns = (
                    exclude_patterns_override
                    if exclude_patterns_override is not None
                    else json.loads(repo_record.exclude_patterns or "[]")
                )
                remote_compression = compression_override or repo_record.compression
                remote_custom_flags = (
                    custom_flags_override
                    if custom_flags_override is not None
                    else repo_record.custom_flags
                )
                remote_source_connection_id = (
                    source_ssh_connection_id
                    if source_directories is not None
                    else job.source_ssh_connection_id
                )

                # Execute remote backup
                await remote_backup_service.execute_remote_backup(
                    job_id=job_id,
                    source_ssh_connection_id=remote_source_connection_id,
                    repository_id=repo_record.id,
                    source_paths=remote_source_paths,
                    exclude_patterns=remote_exclude_patterns,
                    compression=remote_compression,
                    custom_flags=remote_custom_flags,
                    upload_ratelimit_kib=upload_ratelimit_kib,
                )
                return

            # No log files - maximum performance
            # Try to update status - may fail if job was deleted after we queried it
            try:
                job.status = "running"
                job.started_at = datetime.utcnow()
                db.commit()
                mqtt_service.sync_state_with_db(db, reason="backup started")
            except Exception as status_error:
                # Job was deleted while starting - exit gracefully
                logger.warning(
                    "Could not update job to running status (job may have been deleted)",
                    job_id=job_id,
                    error=str(status_error),
                )
                return

            # Build borg create command directly
            # Format: borg create --progress --stats --list REPOSITORY::ARCHIVE PATH [PATH ...]
            # Use local time for archive names so they're meaningful to users
            if not archive_name:
                repo_for_archive_name = None
                try:
                    repo_for_archive_name = (
                        db.query(Repository)
                        .filter(Repository.path == repository)
                        .first()
                    )
                except Exception as e:
                    logger.warning(
                        "Could not look up repository for archive naming",
                        repository=repository,
                        error=str(e),
                    )

                if (
                    repo_for_archive_name
                    and getattr(repo_for_archive_name, "borg_version", 1) == 2
                ):
                    archive_name = "manual-backup"
                else:
                    archive_name = (
                        f"manual-backup-{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
                    )

            # Store archive name on the job for later reference
            try:
                job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
                if job:
                    job.archive_name = archive_name
                    db.commit()
            except Exception as e:
                logger.warning(
                    "Could not save archive_name on job", job_id=job_id, error=str(e)
                )

            # Set environment variables for borg
            env = setup_borg_env()

            # Use modern exit codes for better error handling
            # 0 = success, 1 = warning, 2+ = error
            # Modern: 0 = success, 1-99 reserved, 3-99 = errors, 100-127 = warnings
            env["BORG_EXIT_CODES"] = "modern"

            # Look up repository record to get passphrase and repository-specific settings.
            # Backup plans may override source/config while still targeting the repository.
            source_paths = None  # No default - must be configured
            exclude_patterns = []  # Default no exclusions
            compression = "lz4"  # Default compression
            router = None
            using_source_override = (
                source_directories is not None or source_locations is not None
            )
            try:
                repo_record = (
                    db.query(Repository).filter(Repository.path == repository).first()
                )
                if repo_record:
                    router = BorgRouter(repo_record)
                    # Check if repository is in observability-only mode
                    if repo_record.mode == "observe":
                        error_msg = "Cannot create backups for observability-only repositories. This repository is configured for browsing and restoring existing archives only."
                        logger.error(
                            error_msg, repository=repository, mode=repo_record.mode
                        )
                        raise ValueError(error_msg)
                    # Get compression setting from repository or caller override.
                    if compression_override:
                        compression = compression_override
                        logger.info(
                            "Using compression override",
                            repository=repository,
                            compression=compression,
                        )
                    elif repo_record.compression:
                        compression = repo_record.compression
                        logger.info(
                            "Using compression from repository",
                            repository=repository,
                            compression=compression,
                        )

                    if source_locations is not None:
                        normalized_locations = decode_source_locations(
                            json.dumps(source_locations),
                            source_type="mixed",
                            source_directories=source_directories or [],
                        )
                        source_dirs = flatten_source_locations(normalized_locations)
                        source_paths = self._resolve_grouped_source_paths(
                            db, normalized_locations
                        )
                    elif using_source_override:
                        source_dirs = source_directories or []
                    elif repo_record.source_directories:
                        try:
                            source_dirs = json.loads(repo_record.source_directories)
                        except json.JSONDecodeError as e:
                            error_msg = (
                                f"Could not parse source_directories JSON: {str(e)}"
                            )
                            logger.error(error_msg, repository=repository)
                            raise ValueError(error_msg)
                    else:
                        error_msg = "No source directories configured for this repository. Please add source directories in repository settings."
                        logger.error(error_msg, repository=repository)
                        raise ValueError(error_msg)

                    if not source_dirs or not isinstance(source_dirs, list):
                        error_msg = "No source directories configured for this backup."
                        logger.error(error_msg, repository=repository)
                        raise ValueError(error_msg)

                    effective_source_ssh_connection_id = (
                        None
                        if source_locations is not None
                        else source_ssh_connection_id
                        if source_directories is not None
                        else repo_record.source_ssh_connection_id
                    )

                    # Check if this is a remote source (pull-based backup)
                    if source_locations is not None:
                        logger.info(
                            "Using grouped source locations",
                            repository=repository,
                            source_locations=normalized_locations,
                            source_directories=source_paths,
                        )
                    elif effective_source_ssh_connection_id:
                        from app.database.models import SSHConnection

                        connection = (
                            db.query(SSHConnection)
                            .filter(
                                SSHConnection.id == effective_source_ssh_connection_id
                            )
                            .first()
                        )

                        if connection:
                            # Convert source paths from the SFTP/browsing view into
                            # executable SSH paths for SSHFS mounts.
                            source_paths = [
                                f"ssh://{connection.username}@{connection.host}:{connection.port}{resolve_sshfs_source_path(path, connection.default_path)}"
                                for path in source_dirs
                            ]
                            logger.info(
                                "Using remote source directories (pull-based backup)",
                                repository=repository,
                                connection_id=connection.id,
                                connection_host=connection.host,
                                source_directories=source_paths,
                            )
                        else:
                            error_msg = f"SSH connection {effective_source_ssh_connection_id} not found for remote source"
                            logger.error(error_msg, repository=repository)
                            raise ValueError(error_msg)
                    else:
                        # Local source paths
                        source_paths = source_dirs
                        logger.info(
                            "Using local source directories",
                            repository=repository,
                            source_directories=source_paths,
                        )

                    # Parse exclude patterns from JSON if available, or use caller override.
                    if exclude_patterns_override is not None:
                        exclude_patterns = exclude_patterns_override
                        logger.info(
                            "Using exclude pattern override",
                            repository=repository,
                            exclude_patterns=exclude_patterns,
                        )
                    elif repo_record.exclude_patterns:
                        try:
                            patterns = json.loads(repo_record.exclude_patterns)
                            if (
                                patterns
                                and isinstance(patterns, list)
                                and len(patterns) > 0
                            ):
                                exclude_patterns = patterns
                                logger.info(
                                    "Using exclude patterns from repository",
                                    repository=repository,
                                    exclude_patterns=exclude_patterns,
                                )
                        except json.JSONDecodeError as e:
                            logger.warning(
                                "Could not parse exclude_patterns JSON",
                                repository=repository,
                                error=str(e),
                            )
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

            router.validate_local_repository_access()

            if should_include_restore_canary(repo_record):
                canary_path = ensure_restore_canary(repo_record)
                if str(canary_path) not in source_paths:
                    source_paths = [*source_paths, str(canary_path)]
                    logger.info(
                        "Added restore canary to backup source paths",
                        job_id=job_id,
                        repository_id=repo_record.id,
                        canary_path=str(canary_path),
                    )

            # Use repository path as-is (already contains full SSH URL for SSH repos)
            actual_repository_path = repository

            # Setup SSH-specific configuration if this is an SSH repository
            env, temp_key_file = build_repository_borg_env(
                repo_record,
                db,
                keepalive=True,
                base_env=env,
            )
            if temp_key_file:
                logger.info(
                    "Using SSH key for remote repository",
                    repository=actual_repository_path,
                )

                # Set BORG_REMOTE_PATH if specified (path to borg binary on remote)
                if repo_record.remote_path:
                    env["BORG_REMOTE_PATH"] = repo_record.remote_path
                    logger.info(
                        "Using custom remote borg path",
                        remote_path=repo_record.remote_path,
                        repository=actual_repository_path,
                    )

            # Initialize hook logs
            hook_logs = []

            # Run pre-backup hooks (script library or inline)
            if repo_record and not skip_hooks:
                logger.info(
                    "Executing pre-backup hooks", job_id=job_id, repository=repository
                )
                hook_result = await self._execute_hooks(
                    db=db,
                    repo_record=repo_record,
                    hook_type="pre-backup",
                    job_id=job_id,
                )

                # Add hook logs
                if hook_result["execution_logs"]:
                    hook_logs.extend(hook_result["execution_logs"])

                logger.info(
                    "Pre-backup hooks completed",
                    scripts_executed=hook_result["scripts_executed"],
                    scripts_failed=hook_result["scripts_failed"],
                    using_library=hook_result["using_library"],
                )

                if not hook_result["success"]:
                    # There are two independent skip mechanisms, but only one can be active per backup
                    # because _run_hook always uses *either* library scripts *or* the inline script —
                    # never both.  Priority within the library path is first-fail-wins: the first
                    # script marked skip_on_failure that fails triggers the skip and the remaining
                    # assignments are not evaluated.

                    # Library-script path: RepositoryScript.skip_on_failure on the assignment
                    # signals a graceful skip (e.g. "not the leader node, stand down").
                    if hook_result.get("should_skip"):
                        skip_script = hook_result.get(
                            "skip_script_name", "pre-backup script"
                        )
                        logger.info(
                            "Backup skipped gracefully by pre-backup script",
                            job_id=job_id,
                            script=skip_script,
                        )
                        job.status = "skipped"
                        job.error_message = f"Skipped by '{skip_script}'"
                        job.logs = "\n".join(hook_logs)
                        job.completed_at = datetime.utcnow()
                        db.commit()
                        return

                    # Inline-script path: Repository.skip_on_hook_failure on the repo itself.
                    # Only reached when no library scripts are assigned (using_library=False).
                    if not hook_result.get("using_library") and getattr(
                        repo_record, "skip_on_hook_failure", False
                    ):
                        logger.info(
                            "Backup skipped gracefully by inline pre-backup script",
                            job_id=job_id,
                        )
                        job.status = "skipped"
                        job.error_message = "Skipped by pre-backup script"
                        job.logs = "\n".join(hook_logs)
                        job.completed_at = datetime.utcnow()
                        db.commit()
                        return

                    error_msg = json.dumps(
                        {
                            "key": "backend.errors.service.preBackupHooksFailed",
                            "params": {
                                "failed": hook_result["scripts_failed"],
                                "total": hook_result["scripts_executed"],
                            },
                        }
                    )
                    logger.error(
                        "Pre-backup hooks failed",
                        job_id=job_id,
                        scripts_failed=hook_result["scripts_failed"],
                        scripts_executed=hook_result["scripts_executed"],
                    )

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
                                db, repository, error_msg, job_id, job_name
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to send backup failure notification",
                                error=str(e),
                            )

                        return
                    else:
                        logger.warning(
                            "Pre-backup hooks failed but continuing anyway",
                            job_id=job_id,
                            continue_on_failure=True,
                        )

            # Calculate total expected size of source directories in background
            # This runs asynchronously without blocking backup start
            # Progress percentage will update when calculation completes
            logger.info(
                "Starting background calculation of source directories size",
                source_paths=source_paths,
                job_id=job_id,
                exclude_patterns=exclude_patterns,
            )
            asyncio.create_task(
                self._calculate_and_update_size_background(
                    job_id, source_paths, exclude_patterns
                )
            )

            # Prepare source paths: mount SSH URLs via SSHFS
            logger.info(
                "Preparing source paths (mounting SSH URLs if needed)",
                source_paths=source_paths,
                source_connection_id=effective_source_ssh_connection_id,
                job_id=job_id,
            )
            processed_source_paths, ssh_mount_info = await self._prepare_source_paths(
                source_paths,
                job_id,
                source_connection_id=effective_source_ssh_connection_id,
            )
            if not processed_source_paths:
                logger.error(
                    "No valid source paths after processing (all SSH mounts failed?)",
                    job_id=job_id,
                )
                job.status = "failed"
                job.error_message = json.dumps(
                    {"key": "backend.errors.service.failedPrepareSourcePaths"}
                )
                job.completed_at = datetime.utcnow()
                db.commit()
                mqtt_service.sync_state_with_db(
                    db, reason="backup failed: no valid source paths"
                )
                return
            logger.info(
                "Source paths prepared",
                original_count=len(source_paths),
                processed_count=len(processed_source_paths),
                ssh_mount_count=len(ssh_mount_info),
                job_id=job_id,
            )

            custom_flag_list = []
            custom_flags_text = (
                custom_flags_override
                if custom_flags_override is not None
                else repo_record.custom_flags
                if repo_record
                else None
            )
            if custom_flags_text:
                custom_flags = custom_flags_text.strip()
                if custom_flags:
                    import shlex

                    try:
                        custom_flag_list = shlex.split(custom_flags)
                        logger.info(
                            "Added custom flags to borg create command",
                            job_id=job_id,
                            custom_flags=custom_flags,
                        )
                    except ValueError as e:
                        logger.warning(
                            "Failed to parse custom flags, skipping",
                            job_id=job_id,
                            custom_flags=custom_flags,
                            error=str(e),
                        )

            cmd = router.build_backup_create_command(
                repository_path=actual_repository_path,
                archive_name=archive_name,
                compression=compression,
                exclude_patterns=exclude_patterns,
                custom_flags=custom_flag_list,
                upload_ratelimit_kib=upload_ratelimit_kib,
            )

            backup_paths, backup_cwd = self._resolve_backup_command_paths(
                processed_source_paths,
                ssh_mount_info,
                job_id,
            )

            # Add all source paths to the command
            cmd.extend(backup_paths)

            logger.info(
                "Starting borg backup",
                job_id=job_id,
                repository=actual_repository_path,
                archive=archive_name,
                cwd=backup_cwd,
                command=" ".join(cmd),
            )

            # Send backup start notification (size will be updated by background task)
            try:
                await notification_service.send_backup_start(
                    db, repository, archive_name, source_paths, None, job_name
                )
            except Exception as e:
                logger.warning("Failed to send backup start notification", error=str(e))

            # Execute command - NO LOG FILE FOR MAXIMUM PERFORMANCE
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
                env=env,
                cwd=backup_cwd,  # Use cwd for SSH mounts to get cleaner archive paths
            )
            process_wait_task = asyncio.get_running_loop().create_task(process.wait())

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
            live_progress_exposed = False

            # In-memory circular log buffer (for UI streaming)
            log_buffer = []
            MAX_BUFFER_SIZE = 1000  # Keep last 1000 lines (~100KB RAM)
            # Snapshot the count of pre-backup hook lines collected so far.
            # Used later to distinguish pre-hook lines from post-hook lines.
            pre_hook_count = len(hook_logs)

            # Store buffer reference for external access (Activity page)
            self.log_buffers[job_id] = log_buffer
            logger.info(
                "Created log buffer for job", job_id=job_id, buffer_id=id(log_buffer)
            )

            # Create temporary log file to capture ALL logs (not just buffer)
            temp_log_file = (
                self.log_dir
                / f"backup_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            )
            log_file_handle = None
            try:
                # 64KB buffer - optimal for log files, reduces disk I/O without excessive memory use
                log_file_handle = open(temp_log_file, "w", buffering=65536)
            except Exception as e:
                logger.warning(
                    "Failed to create log file, logs will only be in memory",
                    job_id=job_id,
                    error=str(e),
                )
                temp_log_file = None

            # Prepend pre-backup hook output so it appears at the top of the running
            # log view (the buffer is what get_job_logs reads for in-progress jobs).
            if hook_logs:
                log_buffer.extend(hook_logs)
                if log_file_handle:
                    for line in hook_logs:
                        log_file_handle.write(line + "\n")

            # Smart current_file tracking: Only show files taking >3 seconds
            file_start_times = {}  # Track when each file started processing
            last_shown_file = None

            # Speed tracking: Moving average over 30-second window
            speed_tracking = []  # List of (timestamp, original_size) tuples
            SPEED_WINDOW_SECONDS = 30  # Calculate speed over last 30 seconds

            async def check_cancellation():
                """Periodic heartbeat to check for cancellation independent of log output"""
                nonlocal cancelled
                while not cancelled and not process_wait_task.done():
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(process_wait_task), timeout=3.0
                        )
                        break
                    except asyncio.TimeoutError:
                        pass
                    db.refresh(job)
                    if job.status == "cancelled":
                        logger.info(
                            "Backup job cancelled (heartbeat), terminating process",
                            job_id=job_id,
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
                """Stream log output from process and parse JSON progress"""
                nonlocal \
                    cancelled, \
                    last_commit_time, \
                    last_shown_file, \
                    speed_tracking, \
                    captured_exit_code, \
                    live_progress_exposed
                try:
                    async for line in process.stdout:
                        if cancelled:
                            break

                        line_str = line.decode("utf-8", errors="replace").strip()

                        # Write to full log file (captures ALL logs for download)
                        if log_file_handle:
                            try:
                                log_file_handle.write(line_str + "\n")
                            except Exception:
                                pass  # Silently ignore write errors to avoid breaking backup

                        # Add to in-memory circular log buffer (for UI streaming)
                        log_buffer.append(line_str)
                        if len(log_buffer) > MAX_BUFFER_SIZE:
                            log_buffer.pop(0)  # Remove oldest line

                        # Debug: Log first line added to buffer
                        if len(log_buffer) == 1:
                            logger.info(
                                "First log line added to buffer",
                                job_id=job_id,
                                buffer_id=id(log_buffer),
                            )

                        # Parse Borg progress output from the shared JSON contract
                        # used by Borg create with --log-json.
                        try:
                            if line_str and line_str[0] == "{":
                                json_msg = json.loads(line_str)
                                msg_type = json_msg.get("type")

                                # Parse archive_progress messages for real-time stats
                                if msg_type == "archive_progress":
                                    # Update size/file stats (in memory, no DB write yet)
                                    job.original_size = json_msg.get("original_size", 0)
                                    job.compressed_size = json_msg.get(
                                        "compressed_size", 0
                                    )
                                    job.deduplicated_size = json_msg.get(
                                        "deduplicated_size", 0
                                    )
                                    job.nfiles = json_msg.get("nfiles", 0)

                                    # Calculate backup speed using moving average (30-second window)
                                    if job.original_size > 0:
                                        current_time = asyncio.get_event_loop().time()

                                        # Add current data point
                                        speed_tracking.append(
                                            (current_time, job.original_size)
                                        )

                                        # Remove data points older than window
                                        speed_tracking[:] = [
                                            (t, s)
                                            for t, s in speed_tracking
                                            if current_time - t <= SPEED_WINDOW_SECONDS
                                        ]

                                        # Calculate speed from moving average (need at least 2 data points)
                                        if len(speed_tracking) >= 2:
                                            time_diff = (
                                                speed_tracking[-1][0]
                                                - speed_tracking[0][0]
                                            )
                                            size_diff = (
                                                speed_tracking[-1][1]
                                                - speed_tracking[0][1]
                                            )

                                            if time_diff > 0 and size_diff > 0:
                                                # Speed in MB/s
                                                job.backup_speed = (
                                                    size_diff / (1024 * 1024)
                                                ) / time_diff
                                            elif time_diff > 0:
                                                # No size change yet (early in backup or deduplication)
                                                job.backup_speed = 0.0

                                        # Calculate progress percentage if we have expected size
                                        if (
                                            job.total_expected_size
                                            and job.total_expected_size > 0
                                        ):
                                            job.progress_percent = min(
                                                100.0,
                                                (
                                                    job.original_size
                                                    / job.total_expected_size
                                                )
                                                * 100.0,
                                            )

                                            # Calculate estimated time remaining (in seconds)
                                            remaining_bytes = (
                                                job.total_expected_size
                                                - job.original_size
                                            )
                                            if (
                                                remaining_bytes > 0
                                                and job.backup_speed > 0
                                            ):
                                                # Speed is in MB/s, convert remaining bytes to MB
                                                remaining_mb = remaining_bytes / (
                                                    1024 * 1024
                                                )
                                                job.estimated_time_remaining = int(
                                                    remaining_mb / job.backup_speed
                                                )
                                            else:
                                                job.estimated_time_remaining = 0

                                    # SMART CURRENT_FILE TRACKING: Only show files taking >3 seconds
                                    current_path = json_msg.get("path", "")
                                    if current_path:
                                        current_time = asyncio.get_event_loop().time()

                                        # Track when this file started
                                        if current_path not in file_start_times:
                                            file_start_times[current_path] = (
                                                current_time
                                            )

                                        # Check how long this file has been processing
                                        file_duration = (
                                            current_time
                                            - file_start_times[current_path]
                                        )

                                        if file_duration > 3.0:
                                            # Large/slow file - worth showing to user
                                            if current_path != job.current_file:
                                                job.current_file = current_path
                                                last_shown_file = current_path
                                                # Commit immediately so frontend sees it on next poll
                                                db.commit()
                                                last_commit_time = (
                                                    asyncio.get_event_loop().time()
                                                )
                                        elif current_path != last_shown_file:
                                            # Fast file - don't show it, keep showing last large file or clear it
                                            if (
                                                last_shown_file
                                                and last_shown_file
                                                not in file_start_times
                                            ):
                                                # Last shown file is done, clear the display
                                                job.current_file = None
                                                last_shown_file = None

                                        # Clean up old file tracking (keep memory usage low)
                                        if len(file_start_times) > 100:
                                            # Remove files we finished more than 10 seconds ago
                                            old_files = [
                                                f
                                                for f, t in file_start_times.items()
                                                if current_time - t > 10.0
                                                and f != current_path
                                            ]
                                            for old_file in old_files:
                                                del file_start_times[old_file]

                                    # Check if finished
                                    finished = json_msg.get("finished", False)
                                    if finished:
                                        # Archive is complete
                                        job.progress = 100
                                        job.progress_percent = 100.0
                                        logger.info(
                                            "Archive creation finished", job_id=job_id
                                        )
                                    else:
                                        # Show indeterminate progress (1%) while backup is running
                                        if job.progress == 0 and job.original_size > 0:
                                            job.progress = 1
                                            job.progress_percent = 1.0

                                    # Persist the first live progress snapshot immediately so
                                    # polling clients can observe a running job before short
                                    # backups complete and roll straight into the terminal state.
                                    has_live_progress = any(
                                        [
                                            (job.original_size or 0) > 0,
                                            (job.nfiles or 0) > 0,
                                            bool(job.current_file),
                                            (job.backup_speed or 0) > 0,
                                        ]
                                    )
                                    if has_live_progress and not live_progress_exposed:
                                        db.commit()
                                        live_progress_exposed = True
                                        last_commit_time = (
                                            asyncio.get_event_loop().time()
                                        )

                                    # PERFORMANCE OPTIMIZATION: Batched commits (every 3 seconds)
                                    current_time = asyncio.get_event_loop().time()
                                    if (
                                        current_time - last_commit_time
                                        >= COMMIT_INTERVAL
                                    ):
                                        db.commit()
                                        last_commit_time = current_time
                                        logger.debug(
                                            "Batched commit: progress update",
                                            job_id=job_id,
                                            nfiles=job.nfiles,
                                            original_size=job.original_size,
                                        )

                                # Parse progress_percent messages for percentage
                                elif msg_type == "progress_percent":
                                    finished = json_msg.get("finished", False)
                                    if finished:
                                        job.progress_percent = 100
                                        job.progress = 100
                                    else:
                                        current = json_msg.get("current", 0)
                                        total = json_msg.get("total", 1)
                                        if total > 0:
                                            progress_value = int(
                                                (current / total) * 100
                                            )
                                            job.progress_percent = progress_value
                                            job.progress = progress_value

                                    # Batched commit (no immediate commit)
                                    current_time = asyncio.get_event_loop().time()
                                    if (
                                        current_time - last_commit_time
                                        >= COMMIT_INTERVAL
                                    ):
                                        db.commit()
                                        last_commit_time = current_time

                                # Parse file_status messages for current file
                                elif msg_type == "file_status":
                                    status = json_msg.get("status", "")
                                    path = json_msg.get("path", "")
                                    if path:
                                        # Apply same smart filtering
                                        file_duration = (
                                            asyncio.get_event_loop().time()
                                            - file_start_times.get(
                                                path, asyncio.get_event_loop().time()
                                            )
                                        )
                                        if file_duration > 3.0:
                                            job.current_file = f"[{status}] {path}"
                                            last_shown_file = path

                                # Parse log_message for errors with msgid
                                elif msg_type == "log_message":
                                    levelname = json_msg.get("levelname", "")
                                    message = json_msg.get("message", "")
                                    msgid = json_msg.get("msgid", "")

                                    if levelname in ["ERROR", "CRITICAL"] and msgid:
                                        # Store error msgid for later use
                                        if job_id not in self.error_msgids:
                                            self.error_msgids[job_id] = []
                                        self.error_msgids[job_id].append(
                                            {
                                                "msgid": msgid,
                                                "message": message,
                                                "levelname": levelname,
                                            }
                                        )
                                        logger.error(
                                            "Borg error detected",
                                            job_id=job_id,
                                            msgid=msgid,
                                            message=message,
                                        )

                                    # Also capture exit code from warning messages (e.g., "terminating with warning status, rc 105")
                                    if levelname == "WARNING" and "rc " in message:
                                        rc_match = re.search(r"rc\s+(\d+)", message)
                                        if rc_match:
                                            captured_rc = int(rc_match.group(1))
                                            # Store captured exit code for later status determination
                                            # This will be used if process.returncode is 0 but borg actually exited with a warning
                                            captured_exit_code = captured_rc
                                            logger.info(
                                                "Captured exit code from log message",
                                                job_id=job_id,
                                                exit_code=captured_rc,
                                                message=message,
                                            )

                        except (json.JSONDecodeError, ValueError):
                            pass
                        except Exception as e:
                            logger.warning(
                                "Failed to parse JSON progress",
                                job_id=job_id,
                                error=str(e),
                                line=line_str[:100],
                            )

                except asyncio.CancelledError:
                    logger.info("Log streaming cancelled", job_id=job_id)
                    raise
                finally:
                    # Final commit to save last state
                    db.commit()
                    logger.debug(
                        "Final commit after stream_logs completed", job_id=job_id
                    )

            # Define a task to periodically sync state with DB for MQTT
            async def periodic_sync_state():
                """Periodically sync state with DB for MQTT progress updates"""
                nonlocal cancelled
                try:
                    while not cancelled and not process_wait_task.done():
                        # Sync state with DB every 15 seconds to publish progress updates
                        mqtt_service.sync_state_with_db(
                            db, reason="backup progress update"
                        )
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(process_wait_task), timeout=15.0
                            )
                            break
                        except asyncio.TimeoutError:
                            pass
                except asyncio.CancelledError:
                    logger.info("Periodic sync state task cancelled", job_id=job_id)
                    raise
                except Exception as e:
                    logger.error(
                        "Error in periodic sync state task", job_id=job_id, error=str(e)
                    )

            # Run all tasks concurrently
            try:
                await asyncio.gather(
                    check_cancellation(),
                    stream_logs(),
                    periodic_sync_state(),
                    return_exceptions=True,
                )
            except asyncio.CancelledError:
                logger.info("Backup task cancelled", job_id=job_id)
                cancelled = True
                process.terminate()
                await process.wait()
                raise

            # Wait for process to complete if not already terminated
            if not process_wait_task.done():
                await process_wait_task

            def publish_terminal_state(reason: str):
                """Persist a terminal state before slow post-processing runs."""
                if job.completed_at is None:
                    job.completed_at = datetime.utcnow()
                db.commit()
                mqtt_service.sync_state_with_db(db, reason=reason)

            # Use the actual exit code from the process, or fall back to captured code from logs
            # This handles cases where borg sends the exit code in log messages but process.returncode is 0
            actual_returncode = process.returncode
            if (
                actual_returncode == 0
                and captured_exit_code is not None
                and captured_exit_code != 0
            ):
                # Process exited with 0 but logs indicated a different code (e.g., 105 for warnings)
                logger.info(
                    "Using exit code from log messages instead of process return code",
                    job_id=job_id,
                    process_returncode=actual_returncode,
                    captured_exit_code=captured_exit_code,
                )
                actual_returncode = captured_exit_code

            # Update job status using modern exit codes (if not already cancelled)
            # 0 = success, 1 = warning (legacy), 2 = error (legacy)
            # Modern: 0 = success, 3-99 = errors, 100-127 = warnings
            if job.status == "cancelled":
                logger.info("Backup job was cancelled", job_id=job_id)
                publish_terminal_state("backup cancelled")
                if repo_record and not skip_hooks:
                    logger.info(
                        "Executing post-backup hooks (cancelled case)",
                        job_id=job_id,
                        repository=repository,
                    )
                    hook_result = await self._execute_hooks(
                        db=db,
                        repo_record=repo_record,
                        hook_type="post-backup",
                        backup_result="failure",
                        job_id=job_id,
                    )

                    if hook_result["execution_logs"]:
                        hook_logs.extend(hook_result["execution_logs"])

                    logger.info(
                        "Post-backup hooks completed (cancelled case)",
                        scripts_executed=hook_result["scripts_executed"],
                        scripts_failed=hook_result["scripts_failed"],
                        using_library=hook_result["using_library"],
                    )

                    if not hook_result["success"]:
                        logger.warning(
                            "Post-backup hooks failed after cancellation",
                            job_id=job_id,
                            scripts_failed=hook_result["scripts_failed"],
                        )
            elif actual_returncode == 0:
                job.status = "completed"
                job.progress = 100
                publish_terminal_state("backup completed: borg create finished")
                # Update archive statistics with final deduplicated size
                await self._update_archive_stats(
                    db, job_id, repository, archive_name, env
                )
                # Update repository statistics after successful backup
                await self._update_repository_stats(db, repository, env)

                # Run post-backup hooks (script library or inline)
                post_hook_failed = False
                if repo_record and not skip_hooks:
                    logger.info(
                        "Executing post-backup hooks",
                        job_id=job_id,
                        repository=repository,
                    )
                    hook_result = await self._execute_hooks(
                        db=db,
                        repo_record=repo_record,
                        hook_type="post-backup",
                        backup_result="success",
                        job_id=job_id,
                    )

                    # Add hook logs
                    if hook_result["execution_logs"]:
                        hook_logs.extend(hook_result["execution_logs"])

                    logger.info(
                        "Post-backup hooks completed",
                        scripts_executed=hook_result["scripts_executed"],
                        scripts_failed=hook_result["scripts_failed"],
                        using_library=hook_result["using_library"],
                    )

                    if not hook_result["success"]:
                        post_hook_failed = True
                        logger.warning(
                            "Post-backup hooks failed",
                            job_id=job_id,
                            scripts_failed=hook_result["scripts_failed"],
                        )
                        # Mark as failed if post-hooks fail
                        job.status = "failed"
                        job.error_message = json.dumps(
                            {
                                "key": "backend.errors.service.postBackupHooksFailed",
                                "params": {
                                    "failed": hook_result["scripts_failed"],
                                    "total": hook_result["scripts_executed"],
                                },
                            }
                        )
                        publish_terminal_state("backup failed after post-backup hooks")

                # Send notification after post-hook completes
                if post_hook_failed:
                    # Send failure notification if post-hook failed
                    try:
                        await notification_service.send_backup_failure(
                            db, repository, job.error_message, job_id, job_name
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to send backup failure notification", error=str(e)
                        )
                else:
                    # Send success notification if everything succeeded
                    try:
                        stats = {
                            "original_size": job.original_size,
                            "compressed_size": job.compressed_size,
                            "deduplicated_size": job.deduplicated_size,
                        }
                        await notification_service.send_backup_success(
                            db,
                            repository,
                            archive_name,
                            stats,
                            job.completed_at,
                            job_name,
                            started_at=job.started_at,
                            nfiles=job.nfiles,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to send backup success notification", error=str(e)
                        )

            elif actual_returncode == 1 or (100 <= actual_returncode <= 127):
                # Warning (legacy exit code 1 or modern exit codes 100-127)
                job.status = "completed_with_warnings"
                job.progress = 100
                job.error_message = json.dumps(
                    {
                        "key": "backend.errors.service.backupCompletedWithWarning",
                        "params": {"exitCode": actual_returncode},
                    }
                )
                logger.warning(
                    "Backup completed with warning",
                    job_id=job_id,
                    exit_code=actual_returncode,
                )
                publish_terminal_state(
                    "backup completed with warnings: borg create finished"
                )
                # Update archive statistics with final deduplicated size
                await self._update_archive_stats(
                    db, job_id, repository, archive_name, env
                )
                # Update repository statistics even with warnings
                await self._update_repository_stats(db, repository, env)

                # Run post-backup hooks even with warnings (script library or inline)
                post_hook_failed = False
                if repo_record and not skip_hooks:
                    logger.info(
                        "Executing post-backup hooks (warning case)",
                        job_id=job_id,
                        repository=repository,
                    )
                    hook_result = await self._execute_hooks(
                        db=db,
                        repo_record=repo_record,
                        hook_type="post-backup",
                        backup_result="warning",
                        job_id=job_id,
                    )

                    # Add hook logs
                    if hook_result["execution_logs"]:
                        hook_logs.extend(hook_result["execution_logs"])

                    logger.info(
                        "Post-backup hooks completed (warning case)",
                        scripts_executed=hook_result["scripts_executed"],
                        scripts_failed=hook_result["scripts_failed"],
                        using_library=hook_result["using_library"],
                    )

                    if not hook_result["success"]:
                        post_hook_failed = True
                        logger.warning(
                            "Post-backup hooks failed",
                            job_id=job_id,
                            scripts_failed=hook_result["scripts_failed"],
                        )
                        # Mark as failed if post-hooks fail
                        job.status = "failed"
                        job.error_message = json.dumps(
                            {
                                "key": "backend.errors.service.backupWarningPostHooksFailed",
                                "params": {
                                    "failed": hook_result["scripts_failed"],
                                    "total": hook_result["scripts_executed"],
                                },
                            }
                        )
                        publish_terminal_state(
                            "backup failed after warning post-backup hooks"
                        )

                # Send notification after post-hook completes (for warning case)
                if post_hook_failed:
                    # Send failure notification if post-hook failed
                    try:
                        await notification_service.send_backup_failure(
                            db, repository, job.error_message, job_id, job_name
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to send backup failure notification", error=str(e)
                        )
                else:
                    # Send warning notification (backup completed with warnings but post-hook succeeded)
                    try:
                        stats = {
                            "original_size": job.original_size,
                            "compressed_size": job.compressed_size,
                            "deduplicated_size": job.deduplicated_size,
                        }
                        await notification_service.send_backup_warning(
                            db,
                            repository,
                            archive_name,
                            job.error_message,
                            stats,
                            job.completed_at,
                            job_name,
                            started_at=job.started_at,
                            nfiles=job.nfiles,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to send backup warning notification", error=str(e)
                        )
            else:
                job.status = "failed"
                # Build comprehensive error message with msgid details
                error_parts = []
                lock_error_detected = False

                # Check if we have captured error msgids
                if job_id in self.error_msgids and self.error_msgids[job_id]:
                    # Use the first critical error or the first error
                    errors = self.error_msgids[job_id]
                    primary_error = next(
                        (e for e in errors if e["levelname"] == "CRITICAL"), errors[0]
                    )

                    # Check if this is a lock error (checks msgid and exit code)
                    if is_lock_error(
                        exit_code=actual_returncode, msgid=primary_error["msgid"]
                    ):
                        lock_error_detected = True
                        # Store repository path in error message for easy access
                        error_parts.append(f"LOCK_ERROR::{repository}")

                    # Format error with details and suggestions
                    formatted_error = format_error_message(
                        msgid=primary_error["msgid"],
                        original_message=primary_error["message"],
                        exit_code=actual_returncode,
                    )
                    error_parts.append(formatted_error)

                    # Add additional errors if present
                    if len(errors) > 1:
                        error_parts.append(
                            json.dumps(
                                {
                                    "key": "backend.errors.borg.additionalErrors",
                                    "params": {"count": len(errors) - 1},
                                }
                            )
                        )
                else:
                    # Fallback to simple exit code message
                    error_parts.append(
                        format_error_message(exit_code=actual_returncode)
                    )

                job.error_message = "\n".join(error_parts)
                publish_terminal_state("backup failed")

                # Log lock error for visibility
                if lock_error_detected:
                    msgid = (
                        primary_error["msgid"]
                        if job_id in self.error_msgids and self.error_msgids[job_id]
                        else None
                    )
                    logger.warning(
                        "Backup failed due to lock error",
                        job_id=job_id,
                        repository=repository,
                        msgid=msgid,
                        borg_exit_code=actual_returncode,
                    )

                # Run post-backup hooks on FAILURE (solves #85!)
                # Scripts with run_on='failure' or run_on='always' will execute
                if repo_record and not skip_hooks:
                    logger.info(
                        "Executing post-backup hooks (failure case)",
                        job_id=job_id,
                        repository=repository,
                    )
                    hook_result = await self._execute_hooks(
                        db=db,
                        repo_record=repo_record,
                        hook_type="post-backup",
                        backup_result="failure",
                        job_id=job_id,
                    )

                    # Add hook logs
                    if hook_result["execution_logs"]:
                        hook_logs.extend(hook_result["execution_logs"])

                    logger.info(
                        "Post-backup hooks completed (failure case)",
                        scripts_executed=hook_result["scripts_executed"],
                        scripts_failed=hook_result["scripts_failed"],
                        using_library=hook_result["using_library"],
                    )

                    if not hook_result["success"]:
                        logger.warning(
                            "Post-backup hooks also failed",
                            job_id=job_id,
                            scripts_failed=hook_result["scripts_failed"],
                        )
                        # Append hook failure to error message
                        job.error_message += "\n" + json.dumps(
                            {
                                "key": "backend.errors.service.postBackupHooksAlsoFailed",
                                "params": {
                                    "failed": hook_result["scripts_failed"],
                                    "total": hook_result["scripts_executed"],
                                },
                            }
                        )
                    else:
                        logger.info(
                            "Post-backup hooks executed successfully despite backup failure",
                            job_id=job_id,
                        )

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
                # Save if job failed/cancelled OR has warnings.
                # log_buffer already contains pre-hook lines; check it plus post-hook lines.
                post_hook_logs = hook_logs[pre_hook_count:]
                has_warnings = any(
                    "WARNING" in line or "ERROR" in line
                    for line in list(log_buffer) + list(post_hook_logs)
                )
                should_save_logs = (
                    job.status in ["failed", "cancelled"]
                    or actual_returncode not in [0, None]
                    or has_warnings
                )
            elif log_save_policy == "failed_only":
                # Save only if job failed/cancelled
                should_save_logs = job.status in [
                    "failed",
                    "cancelled",
                ] or actual_returncode not in [0, None]

            # Close the log file handle
            if log_file_handle:
                try:
                    log_file_handle.close()
                except Exception:
                    pass

            # Handle log file based on policy
            if should_save_logs:
                try:
                    # Append post-backup hook logs to the log file.
                    # Pre-backup hook lines were already written at buffer-creation time;
                    # only append the lines added after borg ran to avoid duplication.
                    post_hook_logs = hook_logs[pre_hook_count:]
                    if post_hook_logs and temp_log_file and temp_log_file.exists():
                        with open(temp_log_file, "a") as f:
                            f.write("\n=== Post-backup Hook Logs ===\n")
                            f.write("\n".join(post_hook_logs))
                            f.write("\n")

                    # Use the temp log file as the permanent log file (contains ALL logs)
                    if temp_log_file and temp_log_file.exists():
                        job.log_file_path = str(temp_log_file)
                        job.has_logs = True
                        job.logs = f"Logs saved to: {temp_log_file.name}"

                        # Count lines in file for logging
                        try:
                            with open(temp_log_file, "r") as f:
                                line_count = sum(1 for _ in f)
                        except Exception:
                            line_count = 0

                        logger.info(
                            "Full logs saved per policy",
                            job_id=job_id,
                            status=job.status,
                            policy=log_save_policy,
                            log_file=str(temp_log_file),
                            log_lines=line_count,
                        )
                    else:
                        # Fallback: save buffer if no temp file.
                        # log_buffer already contains pre-hook lines; only append post-hook.
                        fallback_log_file = (
                            self.log_dir
                            / f"backup_job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                        )
                        post_hook_logs = hook_logs[pre_hook_count:]
                        combined_logs = list(log_buffer) + list(post_hook_logs)
                        fallback_log_file.write_text("\n".join(combined_logs))
                        job.log_file_path = str(fallback_log_file)
                        job.has_logs = True
                        job.logs = f"Logs saved to: {fallback_log_file.name}"
                        logger.warning(
                            "Using buffer fallback for logs",
                            job_id=job_id,
                            log_lines=len(combined_logs),
                        )
                except Exception as e:
                    job.has_logs = False
                    job.logs = f"Failed to save logs: {str(e)}"
                    logger.error("Failed to save log file", job_id=job_id, error=str(e))
            else:
                # Delete temp log file since policy says not to save
                if temp_log_file and temp_log_file.exists():
                    try:
                        temp_log_file.unlink()
                        logger.debug(
                            "Deleted temp log file per policy",
                            job_id=job_id,
                            policy=log_save_policy,
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to delete temp log file",
                            job_id=job_id,
                            error=str(e),
                        )

                # Save full transcript to job.logs so the completed-job view always
                # shows pre-hook + borg output + post-hook regardless of save policy.
                # log_buffer already contains pre-hook lines (prepended at creation);
                # append only post-hook lines to avoid duplication.
                post_hook_logs = hook_logs[pre_hook_count:]
                combined = list(log_buffer) + list(post_hook_logs)
                if combined:
                    job.logs = "\n".join(combined)
                    logger.info(
                        "Backup completed, full transcript stored in DB (no file per policy)",
                        job_id=job_id,
                        policy=log_save_policy,
                        lines=len(combined),
                    )
                else:
                    job.logs = None
                    logger.info(
                        "Backup completed, no logs saved per policy",
                        job_id=job_id,
                        policy=log_save_policy,
                    )

            db.commit()
            logger.info("Backup completed", job_id=job_id, status=job.status)
            mqtt_service.sync_state_with_db(db, reason="backup completed")

            # Send failure notification if backup failed
            if job.status == "failed":
                try:
                    await notification_service.send_backup_failure(
                        db,
                        repository,
                        job.error_message or "Unknown error",
                        job_id,
                        job_name,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to send backup failure notification", error=str(e)
                    )

        except Exception as e:
            logger.error("Backup execution failed", job_id=job_id, error=str(e))

            # Close log file handle if open
            if "log_file_handle" in locals() and log_file_handle:
                try:
                    log_file_handle.close()
                except Exception:
                    pass

            # Try to update job status - may fail if job was deleted during execution
            try:
                failure_text = str(e)
                job.status = "failed"
                try:
                    parsed_error = json.loads(failure_text)
                    job.error_message = (
                        failure_text
                        if isinstance(parsed_error, dict) and parsed_error.get("key")
                        else json.dumps({"key": "backend.errors.borg.unknownError"})
                    )
                except (TypeError, json.JSONDecodeError):
                    job.error_message = json.dumps(
                        {"key": "backend.errors.borg.unknownError"}
                    )
                job.completed_at = datetime.utcnow()
                if not job.logs:
                    job.logs = failure_text
                db.commit()
                mqtt_service.sync_state_with_db(
                    db, reason="backup failed with exception"
                )

                # Send failure notification
                try:
                    await notification_service.send_backup_failure(
                        db, repository, str(e), job_id, job_name
                    )
                except Exception as notif_error:
                    logger.warning(
                        "Failed to send backup failure notification",
                        error=str(notif_error),
                    )
            except Exception as commit_error:
                logger.warning(
                    "Could not update job status in current session, retrying with fresh session",
                    job_id=job_id,
                    error=str(commit_error),
                )
                db.rollback()
                retry_db = SessionLocal()
                try:
                    retry_job = (
                        retry_db.query(BackupJob).filter(BackupJob.id == job_id).first()
                    )
                    if retry_job:
                        retry_job.status = "failed"
                        try:
                            parsed_error = json.loads(str(e))
                            retry_job.error_message = (
                                str(e)
                                if isinstance(parsed_error, dict)
                                and parsed_error.get("key")
                                else json.dumps(
                                    {"key": "backend.errors.borg.unknownError"}
                                )
                            )
                        except (TypeError, json.JSONDecodeError):
                            retry_job.error_message = json.dumps(
                                {"key": "backend.errors.borg.unknownError"}
                            )
                        retry_job.completed_at = datetime.utcnow()
                        if not retry_job.logs:
                            retry_job.logs = str(e)
                        retry_db.commit()
                        mqtt_service.sync_state_with_db(
                            retry_db, reason="backup failed with exception (retry)"
                        )
                    else:
                        logger.warning(
                            "Could not find backup job during retry failure update",
                            job_id=job_id,
                        )
                except Exception as retry_error:
                    logger.warning(
                        "Could not update job status after retry (job may have been deleted during execution)",
                        job_id=job_id,
                        error=str(retry_error),
                    )
                    retry_db.rollback()
                finally:
                    retry_db.close()
        finally:
            # Ensure log file handle is closed
            if "log_file_handle" in locals() and log_file_handle:
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
                logger.error(
                    "Failed to cleanup SSH mounts", job_id=job_id, error=str(e)
                )

            # Clean up temporary SSH key file if it exists
            try:
                cleanup_temp_key_file(temp_key_file)
                if temp_key_file:
                    logger.debug(
                        "Cleaned up temporary SSH key file", temp_key_file=temp_key_file
                    )
            except Exception as e:
                logger.warning(
                    "Failed to delete temporary SSH key file",
                    temp_key_file=temp_key_file,
                    error=str(e),
                )

            # Close the database session only if we created it
            if close_db:
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
            logger.info(
                "Sent SIGTERM to backup process", job_id=job_id, pid=process.pid
            )

            # Wait up to 5 seconds for graceful termination
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
                logger.info("Backup process terminated gracefully", job_id=job_id)
            except asyncio.TimeoutError:
                # Force kill if it doesn't terminate gracefully
                process.kill()
                logger.warning(
                    "Force killed backup process (SIGKILL)",
                    job_id=job_id,
                    pid=process.pid,
                )
                await process.wait()

            return True
        except Exception as e:
            logger.error("Failed to cancel backup process", job_id=job_id, error=str(e))
            return False


# Global instance
backup_service = BackupService()
