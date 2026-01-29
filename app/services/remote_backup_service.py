"""
Remote Backup Service

Executes Borg backups on remote hosts via SSH, allowing the Borg UI to orchestrate
backups from remote machines without pulling data over the network.
"""

import asyncio
import os
import json
import re
import shlex
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import structlog
from sqlalchemy.orm import Session

from app.database.models import BackupJob, Repository, SSHConnection, SSHKey
from app.database.database import SessionLocal
from app.config import settings
from app.services.notification_service import notification_service

logger = structlog.get_logger()


class RemoteBackupService:
    """Execute Borg backups on remote hosts via SSH"""

    def __init__(self):
        self.log_dir = Path(settings.data_dir) / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.running_processes = {}  # Track running SSH processes by job_id

    async def execute_remote_backup(
        self,
        job_id: int,
        source_ssh_connection_id: int,
        repository_id: int,
        source_paths: List[str],
        exclude_patterns: List[str] = None,
        compression: str = "lz4",
        custom_flags: str = None
    ) -> dict:
        """
        Main method to execute backup on remote host

        Process:
        1. Validate SSH connection and repository
        2. Build borg create command
        3. Execute via SSH on remote host
        4. Stream output and parse progress
        5. Update job status
        """
        db = SessionLocal()
        try:
            # Update job status
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if not job:
                raise Exception(f"Backup job {job_id} not found")

            job.status = "running"
            job.started_at = datetime.utcnow()
            db.commit()

            logger.info("Starting remote backup",
                       job_id=job_id,
                       source_connection_id=source_ssh_connection_id,
                       repository_id=repository_id)

            # Load SSH connection
            ssh_connection = db.query(SSHConnection).filter(
                SSHConnection.id == source_ssh_connection_id
            ).first()
            if not ssh_connection:
                raise Exception(f"SSH connection {source_ssh_connection_id} not found")

            if not ssh_connection.is_backup_source:
                raise Exception(f"SSH connection {source_ssh_connection_id} is not enabled as backup source")

            # Load repository
            repository = db.query(Repository).filter(Repository.id == repository_id).first()
            if not repository:
                raise Exception(f"Repository {repository_id} not found")

            # Verify repository is SSH type (Phase 1 limitation)
            if not repository.connection_id:
                raise Exception(
                    "Remote backups currently only support SSH repositories. "
                    "Local repositories will be supported in a future update."
                )

            # Store remote hostname for reference
            job.remote_hostname = ssh_connection.host
            db.commit()

            # Build borg command
            archive_name = f"{{hostname}}-{{now}}"
            borg_command = await self._build_remote_command(
                repository=repository,
                archive_name=archive_name,
                source_paths=source_paths or [],
                exclude_patterns=exclude_patterns or [],
                compression=compression,
                custom_flags=custom_flags,
                borg_binary_path=ssh_connection.borg_binary_path
            )

            logger.info("Built borg command for remote execution",
                       job_id=job_id,
                       command_preview=borg_command[:200])

            # Execute command on remote host
            result = await self._execute_ssh_command(
                ssh_connection=ssh_connection,
                command=borg_command,
                job_id=job_id,
                db=db
            )

            # Update final job status
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if result["success"]:
                job.status = "completed"
                job.progress = 100
                job.progress_percent = 100.0
                logger.info("Remote backup completed successfully", job_id=job_id)
            else:
                job.status = "failed"
                job.error_message = result.get("error", "Remote backup failed")
                logger.error("Remote backup failed",
                           job_id=job_id,
                           error=result.get("error"))

            job.completed_at = datetime.utcnow()
            db.commit()

            # Send notification
            await notification_service.send_backup_notification(
                repository_name=repository.name,
                job_id=job_id,
                status=job.status,
                error_message=job.error_message
            )

            return result

        except Exception as e:
            logger.error("Remote backup execution failed",
                        job_id=job_id,
                        error=str(e),
                        exc_info=True)

            # Update job status
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.commit()

            raise
        finally:
            db.close()

    async def _build_remote_command(
        self,
        repository: Repository,
        archive_name: str,
        source_paths: List[str],
        exclude_patterns: List[str],
        compression: str = "lz4",
        custom_flags: str = None,
        borg_binary_path: str = "/usr/bin/borg"
    ) -> str:
        """
        Build the borg create command for remote execution

        Returns command like:
        BORG_PASSPHRASE='secret' borg create \
          --progress --stats --json \
          --compression lz4 \
          ssh://user@repo-host:/path::{hostname}-{now} \
          /data /etc
        """
        # Get DB session for connection lookup
        db = SessionLocal()
        try:
            repo_url = self._get_repository_url(repository, db)
        finally:
            db.close()

        # Build borg command parts
        cmd_parts = []

        # Add passphrase environment variable if needed
        if repository.encryption and repository.encryption != "none" and repository.passphrase:
            # Use shlex.quote to safely escape the passphrase
            escaped_passphrase = shlex.quote(repository.passphrase)
            cmd_parts.append(f"BORG_PASSPHRASE={escaped_passphrase}")

        # Add remote path if configured
        if repository.remote_path:
            cmd_parts.append(f"BORG_REMOTE_PATH={shlex.quote(repository.remote_path)}")

        # Borg binary path
        cmd_parts.append(shlex.quote(borg_binary_path))

        # Create command
        cmd_parts.append("create")

        # Flags
        cmd_parts.extend(["--progress", "--stats", "--json"])

        # Compression
        if compression:
            cmd_parts.extend(["--compression", compression])

        # Custom flags
        if custom_flags:
            cmd_parts.append(custom_flags)

        # Exclude patterns
        for pattern in exclude_patterns:
            cmd_parts.extend(["--exclude", shlex.quote(pattern)])

        # Repository and archive name
        archive_path = f"{repo_url}::{archive_name}"
        cmd_parts.append(shlex.quote(archive_path))

        # Source paths
        for path in source_paths:
            cmd_parts.append(shlex.quote(path))

        return " ".join(cmd_parts)

    def _get_repository_url(self, repository: Repository, db: Session) -> str:
        """
        Get the repository URL that a remote host should use

        Examples:
        - SSH repo: ssh://backup@repo-host:22/path
        """
        if repository.connection_id:
            # Get SSH connection details
            connection = db.query(SSHConnection).filter(
                SSHConnection.id == repository.connection_id
            ).first()
            if not connection:
                raise ValueError(f"SSH connection {repository.connection_id} not found")
            return f"ssh://{connection.username}@{connection.host}:{connection.port}{repository.path}"
        else:
            raise NotImplementedError(
                "Local repositories are not yet supported for remote backups. "
                "Please use an SSH repository."
            )

    async def _execute_ssh_command(
        self,
        ssh_connection: SSHConnection,
        command: str,
        job_id: int,
        db: Session
    ) -> dict:
        """
        Execute command on remote host via SSH
        Stream stdout/stderr for progress parsing
        """
        try:
            # Load SSH key
            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_connection.ssh_key_id).first()
            if not ssh_key:
                raise Exception(f"SSH key {ssh_connection.ssh_key_id} not found")

            # Create temporary SSH key file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as key_file:
                key_file.write(ssh_key.private_key)
                key_file_path = key_file.name

            # Set proper permissions on key file
            os.chmod(key_file_path, 0o600)

            try:
                # Build SSH command
                ssh_cmd = [
                    "ssh",
                    "-i", key_file_path,
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "ServerAliveInterval=60",
                    "-o", "ServerAliveCountMax=3",
                    "-p", str(ssh_connection.port),
                    f"{ssh_connection.username}@{ssh_connection.host}",
                    command
                ]

                logger.info("Executing SSH command",
                           job_id=job_id,
                           host=ssh_connection.host,
                           command_preview=command[:200])

                # Execute command
                process = await asyncio.create_subprocess_exec(
                    *ssh_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                self.running_processes[job_id] = process

                # Track PID on remote host (if possible to extract from output)
                job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
                if job and process.pid:
                    job.remote_process_pid = process.pid
                    db.commit()

                # Read output and parse progress
                stdout_lines = []
                stderr_lines = []

                async def read_stdout():
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        line_str = line.decode('utf-8', errors='replace').strip()
                        stdout_lines.append(line_str)

                        # Try to parse Borg JSON progress
                        if line_str.startswith('{'):
                            try:
                                progress_data = json.loads(line_str)
                                await self._update_progress_from_json(job_id, progress_data, db)
                            except json.JSONDecodeError:
                                pass

                async def read_stderr():
                    while True:
                        line = await process.stderr.readline()
                        if not line:
                            break
                        line_str = line.decode('utf-8', errors='replace').strip()
                        stderr_lines.append(line_str)
                        logger.debug("Remote backup stderr",
                                   job_id=job_id,
                                   line=line_str)

                # Read both streams concurrently
                await asyncio.gather(read_stdout(), read_stderr())

                # Wait for process to complete
                returncode = await process.wait()

                # Clean up
                del self.running_processes[job_id]

                # Return result
                success = returncode == 0
                return {
                    "success": success,
                    "returncode": returncode,
                    "stdout": "\n".join(stdout_lines),
                    "stderr": "\n".join(stderr_lines),
                    "error": None if success else f"Remote backup failed with exit code {returncode}"
                }

            finally:
                # Clean up temporary key file
                try:
                    os.unlink(key_file_path)
                except Exception as e:
                    logger.warning("Failed to delete temporary key file",
                                 path=key_file_path,
                                 error=str(e))

        except Exception as e:
            logger.error("SSH command execution failed",
                        job_id=job_id,
                        error=str(e),
                        exc_info=True)
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "error": str(e)
            }

    async def _update_progress_from_json(self, job_id: int, data: dict, db: Session):
        """Update job progress from Borg JSON output"""
        try:
            job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
            if not job:
                return

            # Extract progress information
            if "original_size" in data:
                job.original_size = data.get("original_size", 0)
            if "compressed_size" in data:
                job.compressed_size = data.get("compressed_size", 0)
            if "deduplicated_size" in data:
                job.deduplicated_size = data.get("deduplicated_size", 0)
            if "nfiles" in data:
                job.nfiles = data.get("nfiles", 0)

            # Update progress percentage (estimate based on original size)
            if job.total_expected_size and job.total_expected_size > 0:
                progress = min(100.0, (job.original_size / job.total_expected_size) * 100)
                job.progress_percent = progress
                job.progress = int(progress)

            db.commit()

        except Exception as e:
            logger.error("Failed to update progress from JSON",
                        job_id=job_id,
                        error=str(e))

    async def verify_remote_borg(self, ssh_connection_id: int) -> Dict:
        """
        Check if Borg is installed on remote host
        Returns: {installed: bool, version: str, path: str}
        """
        db = SessionLocal()
        try:
            ssh_connection = db.query(SSHConnection).filter(
                SSHConnection.id == ssh_connection_id
            ).first()
            if not ssh_connection:
                raise Exception(f"SSH connection {ssh_connection_id} not found")

            # Load SSH key
            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_connection.ssh_key_id).first()
            if not ssh_key:
                raise Exception(f"SSH key {ssh_connection.ssh_key_id} not found")

            # Create temporary SSH key file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as key_file:
                key_file.write(ssh_key.private_key)
                key_file_path = key_file.name

            os.chmod(key_file_path, 0o600)

            try:
                # Try to find borg binary
                borg_path = ssh_connection.borg_binary_path or "/usr/bin/borg"

                # Build SSH command to check borg
                ssh_cmd = [
                    "ssh",
                    "-i", key_file_path,
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-p", str(ssh_connection.port),
                    f"{ssh_connection.username}@{ssh_connection.host}",
                    f"{borg_path} --version"
                ]

                logger.info("Checking for Borg on remote host",
                           connection_id=ssh_connection_id,
                           host=ssh_connection.host)

                process = await asyncio.create_subprocess_exec(
                    *ssh_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await process.communicate()
                returncode = process.returncode

                if returncode == 0:
                    version_output = stdout.decode('utf-8', errors='replace').strip()
                    # Parse version from output like "borg 1.2.4"
                    version_match = re.search(r'borg\s+([\d.]+)', version_output, re.IGNORECASE)
                    version = version_match.group(1) if version_match else "unknown"

                    logger.info("Borg found on remote host",
                               connection_id=ssh_connection_id,
                               version=version,
                               path=borg_path)

                    return {
                        "installed": True,
                        "version": version,
                        "path": borg_path
                    }
                else:
                    logger.warning("Borg not found on remote host",
                                 connection_id=ssh_connection_id,
                                 stderr=stderr.decode('utf-8', errors='replace'))
                    return {
                        "installed": False,
                        "version": None,
                        "path": None,
                        "error": stderr.decode('utf-8', errors='replace')
                    }

            finally:
                try:
                    os.unlink(key_file_path)
                except Exception as e:
                    logger.warning("Failed to delete temporary key file",
                                 path=key_file_path,
                                 error=str(e))

        except Exception as e:
            logger.error("Failed to verify remote borg",
                        connection_id=ssh_connection_id,
                        error=str(e),
                        exc_info=True)
            return {
                "installed": False,
                "version": None,
                "path": None,
                "error": str(e)
            }
        finally:
            db.close()

    async def cancel_remote_backup(self, job_id: int) -> bool:
        """
        Cancel running remote backup by terminating SSH process
        """
        try:
            process = self.running_processes.get(job_id)
            if process:
                logger.info("Cancelling remote backup", job_id=job_id)
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Remote backup did not terminate, killing",
                                 job_id=job_id)
                    process.kill()
                    await process.wait()

                del self.running_processes[job_id]

                # Update job status
                db = SessionLocal()
                try:
                    job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
                    if job:
                        job.status = "failed"
                        job.error_message = "Backup cancelled by user"
                        job.completed_at = datetime.utcnow()
                        db.commit()
                finally:
                    db.close()

                return True
            else:
                logger.warning("No running process found for job", job_id=job_id)
                return False

        except Exception as e:
            logger.error("Failed to cancel remote backup",
                        job_id=job_id,
                        error=str(e),
                        exc_info=True)
            return False


# Global instance
remote_backup_service = RemoteBackupService()
