"""
Mount Service for SSHFS and Borg Archive mounting

Provides unified mount management for:
1. Pull-based backups (SSHFS with SSH key auth)
2. User-facing archive browsing (borg mount)
"""

import asyncio
import os
import subprocess
import tempfile
import shutil
import uuid
import platform
import json
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import structlog
import base64
from cryptography.fernet import Fernet

from app.config import settings
from app.database.database import SessionLocal
from app.database.models import SSHConnection, SSHKey, Repository, SystemSettings

logger = structlog.get_logger()


class MountType(Enum):
    """Type of mount"""
    SSHFS = "sshfs"              # Remote directory mounting
    BORG_ARCHIVE = "borg_archive"  # Specific Borg archive


@dataclass
class MountInfo:
    """Information about an active mount"""
    mount_id: str
    mount_type: MountType
    mount_point: str
    source: str
    created_at: datetime
    job_id: Optional[int] = None
    temp_root: Optional[str] = None
    temp_key_file: Optional[str] = None
    connection_id: Optional[int] = None
    repository_id: Optional[int] = None
    process_pid: Optional[int] = None  # PID of borg mount process (for foreground mounts)


class MountService:
    """Service for managing SSHFS and Borg mounts"""

    def __init__(self):
        self.active_mounts: Dict[str, MountInfo] = {}
        self.mount_base_dir = Path(settings.data_dir) / "mounts"
        self.mount_base_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = Path(settings.data_dir) / "mount_state.json"

        # Load persisted mounts on init
        self._load_state()

        # Clean up stale mounts (mounts in state file but not actually mounted)
        self._cleanup_stale_mounts()

    def _load_state(self):
        """Load mount state from disk"""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)

            for mount_dict in data.get('mounts', []):
                # Convert dict back to MountInfo
                mount_dict['mount_type'] = MountType(mount_dict['mount_type'])
                mount_dict['created_at'] = datetime.fromisoformat(mount_dict['created_at'])
                mount_info = MountInfo(**mount_dict)
                self.active_mounts[mount_info.mount_id] = mount_info

            logger.info(
                "Loaded mount state from disk",
                mount_count=len(self.active_mounts)
            )
        except Exception as e:
            logger.error(
                "Failed to load mount state",
                error=str(e)
            )

    def _save_state(self):
        """Persist mount state to disk"""
        try:
            mounts_list = []
            for mount_info in self.active_mounts.values():
                mount_dict = asdict(mount_info)
                mount_dict['mount_type'] = mount_info.mount_type.value
                mount_dict['created_at'] = mount_info.created_at.isoformat()
                mounts_list.append(mount_dict)

            with open(self.state_file, 'w') as f:
                json.dump({'mounts': mounts_list}, f, indent=2)

            logger.debug(
                "Saved mount state to disk",
                mount_count=len(mounts_list)
            )
        except Exception as e:
            logger.error(
                "Failed to save mount state",
                error=str(e)
            )

    def _cleanup_stale_mounts(self):
        """Remove mounts from state that are no longer active in the system"""
        try:
            # Get list of active mount points from system
            result = subprocess.run(
                ["mount"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.warning("Failed to list system mounts for cleanup")
                return

            active_mount_points = set()
            for line in result.stdout.split('\n'):
                # Extract mount point from mount output
                # Format: "source on /mount/point type filesystem (options)"
                parts = line.split()
                if len(parts) >= 3 and 'on' in parts:
                    try:
                        on_index = parts.index('on')
                        if on_index + 1 < len(parts):
                            active_mount_points.add(parts[on_index + 1])
                    except:
                        pass

            # Check each tracked mount
            stale_mounts = []
            for mount_id, mount_info in self.active_mounts.items():
                if mount_info.mount_point not in active_mount_points:
                    logger.info(
                        "Found stale mount in state file",
                        mount_id=mount_id,
                        mount_point=mount_info.mount_point
                    )
                    stale_mounts.append(mount_id)

            # Remove stale mounts
            for mount_id in stale_mounts:
                del self.active_mounts[mount_id]

            if stale_mounts:
                # Save updated state
                self._save_state()
                logger.info(
                    "Cleaned up stale mounts",
                    count=len(stale_mounts)
                )

        except Exception as e:
            logger.error(
                "Failed to cleanup stale mounts",
                error=str(e)
            )

    async def mount_ssh_directory(
        self,
        connection_id: int,
        remote_path: str,
        job_id: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Mount a remote SSH directory via SSHFS with proper SSH key authentication

        Args:
            connection_id: SSHConnection ID to use
            remote_path: Remote path to mount
            job_id: Optional backup job ID for tracking

        Returns:
            Tuple of (temp_root, mount_id)

        Raises:
            Exception: If mount fails
        """
        db = SessionLocal()
        try:
            # Get SSH connection
            connection = db.query(SSHConnection).filter(
                SSHConnection.id == connection_id
            ).first()

            if not connection:
                raise Exception(f"SSH connection {connection_id} not found")

            # Get SSH key
            ssh_key = db.query(SSHKey).filter(
                SSHKey.id == connection.ssh_key_id
            ).first()

            if not ssh_key:
                raise Exception(
                    f"SSH key {connection.ssh_key_id} not found for connection {connection_id}"
                )

            # Check if SSHFS is available
            if not await self._check_sshfs_available():
                raise Exception(
                    "SSHFS not found - install SSHFS package or rebuild Docker image"
                )

            # Decrypt SSH key
            temp_key_file = self._decrypt_and_write_key(ssh_key)

            # Create temporary mount structure
            path_basename = os.path.basename(remote_path.rstrip('/'))
            temp_root = tempfile.mkdtemp(prefix=f"sshfs_mount_{job_id or 'user'}_")
            mount_dir = os.path.join(temp_root, path_basename)
            os.makedirs(mount_dir, exist_ok=True)

            mount_id = str(uuid.uuid4())

            logger.info(
                "Mounting SSH directory via SSHFS",
                mount_id=mount_id,
                connection_id=connection_id,
                host=connection.host,
                remote_path=remote_path,
                mount_point=mount_dir,
                job_id=job_id
            )

            try:
                # Mount with SSH key authentication
                await self._execute_sshfs_mount(
                    connection=connection,
                    remote_path=remote_path,
                    mount_point=mount_dir,
                    temp_key_file=temp_key_file
                )

                # Verify mount with READ-ONLY check (NEVER write to user data!)
                await self._verify_mount_readable(mount_dir)

                # Track mount
                self.active_mounts[mount_id] = MountInfo(
                    mount_id=mount_id,
                    mount_type=MountType.SSHFS,
                    mount_point=mount_dir,
                    source=f"ssh://{connection.username}@{connection.host}:{connection.port}{remote_path}",
                    created_at=datetime.now(timezone.utc),
                    job_id=job_id,
                    temp_root=temp_root,
                    temp_key_file=temp_key_file,
                    connection_id=connection_id
                )

                logger.info(
                    "Successfully mounted SSH directory",
                    mount_id=mount_id,
                    mount_point=mount_dir,
                    temp_root=temp_root,
                    job_id=job_id
                )

                # Persist state
                self._save_state()

                return temp_root, mount_id

            except Exception as e:
                # Cleanup on failure
                logger.error(
                    "Failed to mount SSH directory",
                    mount_id=mount_id,
                    error=str(e),
                    job_id=job_id
                )
                self._cleanup_temp_files(temp_root, temp_key_file)
                raise

        finally:
            db.close()

    async def mount_borg_archive(
        self,
        repository_id: int,
        archive_name: Optional[str] = None,
        mount_point: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Mount a Borg repository or specific archive for browsing

        Args:
            repository_id: Repository ID to mount
            archive_name: Optional specific archive name (None = mount entire repo)
            mount_point: Optional custom mount point (must be validated)

        Returns:
            Tuple of (mount_point, mount_id)

        Raises:
            Exception: If mount fails
        """
        db = SessionLocal()
        try:
            # Get repository
            repository = db.query(Repository).filter(
                Repository.id == repository_id
            ).first()

            if not repository:
                raise Exception(f"Repository {repository_id} not found")

            # Get system settings for mount timeout
            system_settings = db.query(SystemSettings).first()
            mount_timeout = system_settings.mount_timeout if system_settings and system_settings.mount_timeout else 120

            # Create or validate mount point
            if mount_point:
                # If mount_point doesn't start with /, it's just a name - prepend /data/mounts/
                if not mount_point.startswith('/'):
                    mount_point = str(self.mount_base_dir / mount_point)
                else:
                    # Absolute path provided - validate it
                    self._validate_mount_point(mount_point)

                # If directory exists and is not empty, it's likely stale - clean it first
                if os.path.exists(mount_point):
                    if os.path.isdir(mount_point) and not os.listdir(mount_point):
                        # Empty directory, reuse it
                        pass
                    elif os.path.isdir(mount_point):
                        # Directory exists with content - might be old mount, try to unmount
                        try:
                            subprocess.run(
                                ["fusermount", "-uz", mount_point],
                                capture_output=True,
                                timeout=5
                            )
                        except:
                            pass
                else:
                    os.makedirs(mount_point, exist_ok=True)
            else:
                # Create auto mount point - use archive name for friendly path
                safe_archive_name = archive_name.replace('/', '_').replace(' ', '_') if archive_name else 'repository'
                mount_point = str(
                    self.mount_base_dir / safe_archive_name
                )
                # If path exists, append unique suffix
                if os.path.exists(mount_point):
                    mount_point = f"{mount_point}_{uuid.uuid4().hex[:8]}"
                os.makedirs(mount_point, exist_ok=True)

            mount_id = str(uuid.uuid4())
            temp_key_file = None

            logger.info(
                "Mounting Borg archive",
                mount_id=mount_id,
                repository_id=repository_id,
                repository_name=repository.name,
                archive_name=archive_name,
                mount_point=mount_point
            )

            try:
                # Build borg mount command
                env = os.environ.copy()

                logger.info(
                    "Repository details",
                    mount_id=mount_id,
                    repository_type=repository.repository_type,
                    connection_id=repository.connection_id,
                    has_passphrase=bool(repository.passphrase)
                )

                # Handle SSH repositories
                if repository.repository_type == "ssh":
                    # Always disable strict host key checking for SSH repos
                    ssh_opts = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

                    if repository.connection_id:
                        # Repository linked to SSH connection
                        connection = db.query(SSHConnection).filter(
                            SSHConnection.id == repository.connection_id
                        ).first()

                        logger.info(
                            "SSH connection details",
                            mount_id=mount_id,
                            connection_found=bool(connection),
                            connection_id=repository.connection_id,
                            ssh_key_id=connection.ssh_key_id if connection else None
                        )

                        if connection and connection.ssh_key_id:
                            ssh_key = db.query(SSHKey).filter(
                                SSHKey.id == connection.ssh_key_id
                            ).first()

                            if ssh_key:
                                # Decrypt SSH key
                                temp_key_file = self._decrypt_and_write_key(ssh_key)
                                # Set BORG_RSH with key and SSH options
                                env["BORG_RSH"] = f"ssh -i {temp_key_file} {ssh_opts}"
                                logger.info(
                                    "Set BORG_RSH with key",
                                    mount_id=mount_id,
                                    borg_rsh=env["BORG_RSH"]
                                )
                            else:
                                # No key found, use SSH options only
                                env["BORG_RSH"] = f"ssh {ssh_opts}"
                                logger.info(
                                    "Set BORG_RSH without key (key not found)",
                                    mount_id=mount_id,
                                    borg_rsh=env["BORG_RSH"]
                                )
                        else:
                            # No key configured or connection not found
                            env["BORG_RSH"] = f"ssh {ssh_opts}"
                            logger.info(
                                "Set BORG_RSH without key (no connection or key)",
                                mount_id=mount_id,
                                borg_rsh=env["BORG_RSH"]
                            )
                    else:
                        # SSH repository without connection_id (embedded SSH URL)
                        env["BORG_RSH"] = f"ssh {ssh_opts}"
                        logger.info(
                            "Set BORG_RSH for SSH repo without connection",
                            mount_id=mount_id,
                            borg_rsh=env["BORG_RSH"]
                        )
                else:
                    logger.info(
                        "Not an SSH repository",
                        mount_id=mount_id,
                        repository_type=repository.repository_type
                    )

                # Set passphrase if encrypted
                if repository.passphrase:
                    env["BORG_PASSPHRASE"] = repository.passphrase

                # Build mount command
                cmd = ["borg", "mount"]

                # Add archive-specific mount if specified
                if archive_name:
                    cmd.append(f"{repository.path}::{archive_name}")
                else:
                    cmd.append(repository.path)

                cmd.append(mount_point)

                # Add borg options
                cmd.extend(["-o", "allow_other"])

                # Add foreground flag to prevent daemonization
                # We need to handle the daemonization ourselves to properly track the mount
                cmd.extend(["-f"])  # Run in foreground

                # Add bypass-lock for read-only storage access (observe-only repos)
                if repository.bypass_lock:
                    cmd.append("--bypass-lock")

                # Log command for debugging
                logger.info(
                    "Executing borg mount command",
                    mount_id=mount_id,
                    command=" ".join(cmd),
                    mount_point=mount_point,
                    has_passphrase=bool(repository.passphrase),
                    has_ssh_key=bool(temp_key_file),
                    has_borg_rsh="BORG_RSH" in env
                )

                # Execute mount in foreground mode
                # We'll start it and let it run in the background
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    env=env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL
                )

                logger.info(
                    "Process created",
                    mount_id=mount_id,
                    pid=process.pid
                )

                # Wait for the mount to initialize with retries
                # Large repositories (10TB+) can take 30-60+ seconds to mount
                # In foreground mode, borg mount will continue running
                max_wait_seconds = mount_timeout  # From system settings (default 120 seconds)
                check_interval = 5  # Check every 5 seconds
                total_waited = 0
                mount_verified = False

                while total_waited < max_wait_seconds:
                    await asyncio.sleep(check_interval)
                    total_waited += check_interval

                    # Check if process is still running (it should be for successful mount)
                    if process.returncode is not None:
                        # Process exited - this means mount failed
                        try:
                            stderr = await asyncio.wait_for(
                                process.stderr.read(),
                                timeout=1
                            )
                            error_msg = stderr.decode() if stderr else "Unknown error"
                        except:
                            error_msg = "Unknown error"

                        logger.error(
                            "Borg mount process exited unexpectedly",
                            mount_id=mount_id,
                            returncode=process.returncode,
                            error=error_msg,
                            waited_seconds=total_waited
                        )
                        raise Exception(f"Borg mount failed: {error_msg}")

                    logger.info(
                        "Process still running, checking mount status",
                        mount_id=mount_id,
                        pid=process.pid,
                        waited_seconds=total_waited
                    )

                    # Verify mount is active
                    mount_check = subprocess.run(
                        ["mount"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    if mount_point in mount_check.stdout:
                        mount_verified = True
                        logger.info(
                            "Mount verified successfully",
                            mount_id=mount_id,
                            mount_point=mount_point,
                            waited_seconds=total_waited
                        )
                        break
                    else:
                        logger.info(
                            "Mount point not yet in mount list, waiting...",
                            mount_id=mount_id,
                            mount_point=mount_point,
                            waited_seconds=total_waited,
                            max_wait=max_wait_seconds
                        )

                if not mount_verified:
                    # Timeout reached - mount didn't complete in time
                    logger.error(
                        "Mount timeout - mount point not found after max wait",
                        mount_id=mount_id,
                        mount_point=mount_point,
                        waited_seconds=total_waited
                    )
                    # Kill the process
                    try:
                        process.kill()
                        await process.wait()
                    except:
                        pass
                    raise Exception(f"Mount timeout: mount point not ready after {max_wait_seconds} seconds. Large repositories may need more time.")

                # Track mount
                self.active_mounts[mount_id] = MountInfo(
                    mount_id=mount_id,
                    mount_type=MountType.BORG_ARCHIVE,
                    mount_point=mount_point,
                    source=f"{repository.path}::{archive_name or 'all'}",
                    created_at=datetime.now(timezone.utc),
                    temp_key_file=temp_key_file,
                    repository_id=repository_id,
                    process_pid=process.pid  # Store PID for cleanup
                )

                logger.info(
                    "Successfully mounted Borg archive",
                    mount_id=mount_id,
                    mount_point=mount_point,
                    repository_name=repository.name,
                    archive_name=archive_name
                )

                # Persist state
                self._save_state()

                return mount_point, mount_id

            except Exception as e:
                logger.error(
                    "Failed to mount Borg archive",
                    mount_id=mount_id,
                    error=str(e),
                    repository_id=repository_id
                )
                # Cleanup on failure
                if temp_key_file and os.path.exists(temp_key_file):
                    os.unlink(temp_key_file)
                if os.path.exists(mount_point) and not os.listdir(mount_point):
                    os.rmdir(mount_point)
                raise

        finally:
            db.close()

    async def unmount(self, mount_id: str, force: bool = False) -> bool:
        """
        Unmount and cleanup a mount

        Args:
            mount_id: Mount ID to unmount
            force: Force unmount even if busy

        Returns:
            True if successful, False otherwise
        """
        if mount_id not in self.active_mounts:
            logger.warning("Mount not found in active mounts", mount_id=mount_id)
            return False

        mount_info = self.active_mounts[mount_id]

        logger.info(
            "Unmounting",
            mount_id=mount_id,
            mount_type=mount_info.mount_type.value,
            mount_point=mount_info.mount_point,
            force=force
        )

        try:
            # For Borg mounts with foreground process, kill the process first
            if mount_info.mount_type == MountType.BORG_ARCHIVE and mount_info.process_pid:
                try:
                    logger.info(
                        "Killing borg mount process",
                        mount_id=mount_id,
                        pid=mount_info.process_pid
                    )
                    os.kill(mount_info.process_pid, 15)  # SIGTERM
                    # Wait a bit for graceful shutdown
                    await asyncio.sleep(1)
                    # Verify process is dead
                    try:
                        os.kill(mount_info.process_pid, 0)  # Check if process exists
                        # Still alive, force kill
                        logger.warning(
                            "Process still alive, force killing",
                            mount_id=mount_id,
                            pid=mount_info.process_pid
                        )
                        os.kill(mount_info.process_pid, 9)  # SIGKILL
                    except OSError:
                        # Process is dead
                        pass
                except Exception as e:
                    logger.warning(
                        "Failed to kill borg mount process",
                        mount_id=mount_id,
                        pid=mount_info.process_pid,
                        error=str(e)
                    )

            # Choose unmount method based on type
            if mount_info.mount_type == MountType.SSHFS:
                success = await self._unmount_fuse(mount_info.mount_point, force)
            elif mount_info.mount_type == MountType.BORG_ARCHIVE:
                success = await self._unmount_borg(mount_info.mount_point, force)
            else:
                logger.error("Unknown mount type", mount_type=mount_info.mount_type)
                success = False

            if success:
                # Cleanup temp files
                self._cleanup_temp_files(
                    mount_info.temp_root,
                    mount_info.temp_key_file
                )

                # Remove from tracking
                del self.active_mounts[mount_id]

                # Persist state
                self._save_state()

                logger.info("Successfully unmounted and cleaned up", mount_id=mount_id)
                return True
            else:
                logger.error("Failed to unmount", mount_id=mount_id)
                return False

        except Exception as e:
            logger.error("Error during unmount", mount_id=mount_id, error=str(e))
            return False

    def list_mounts(self) -> List[MountInfo]:
        """List all active mounts"""
        return list(self.active_mounts.values())

    def get_mount(self, mount_id: str) -> Optional[MountInfo]:
        """Get mount info by ID"""
        return self.active_mounts.get(mount_id)

    # Private helper methods

    async def _check_sshfs_available(self) -> bool:
        """Check if SSHFS is installed"""
        try:
            process = await asyncio.create_subprocess_exec(
                "which", "sshfs",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return process.returncode == 0
        except Exception:
            return False

    def _decrypt_and_write_key(self, ssh_key: SSHKey) -> str:
        """
        Decrypt SSH private key and write to temp file

        Args:
            ssh_key: SSHKey model instance

        Returns:
            Path to temporary key file
        """
        # Decrypt private key (reuse pattern from ssh_keys.py)
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

        # Ensure trailing newline
        if not private_key.endswith('\n'):
            private_key += '\n'

        # Create temporary key file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as f:
            f.write(private_key)
            temp_key_file = f.name

        # Set secure permissions
        os.chmod(temp_key_file, 0o600)

        logger.debug("Created temporary SSH key file", key_file=temp_key_file)

        return temp_key_file

    async def _execute_sshfs_mount(
        self,
        connection: SSHConnection,
        remote_path: str,
        mount_point: str,
        temp_key_file: str
    ):
        """Execute SSHFS mount command with SSH key authentication"""
        # Get current user's UID and GID for mount options
        current_uid = os.getuid()
        current_gid = os.getgid()

        # Build SSHFS command WITH IdentityFile (this is the fix!)
        cmd = [
            "sshfs",
            f"{connection.username}@{connection.host}:{remote_path}",
            mount_point,
            "-p", str(connection.port),
            "-o", f"IdentityFile={temp_key_file}",  # CRITICAL: SSH key auth
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=30",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "reconnect",
            "-o", "follow_symlinks",
            "-o", "allow_other",
            "-o", f"uid={current_uid}",
            "-o", f"gid={current_gid}",
            "-o", "workaround=rename"
        ]

        logger.info("Executing SSHFS mount", command=" ".join(cmd))

        # Execute mount command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL
        )

        # Give SSHFS a moment to start mounting
        await asyncio.sleep(1)

        # Check for immediate errors
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
            if process.returncode is not None and process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise Exception(f"SSHFS mount failed: {error_msg}")
        except asyncio.TimeoutError:
            # SSHFS forks to background, timeout is expected for successful mounts
            pass

    async def _verify_mount_readable(self, mount_point: str):
        """
        Verify mount is actually working with READ-ONLY operations

        CRITICAL: NEVER write to user data directories - this caused data corruption!
        We only verify the mount is accessible by reading, not writing.
        """
        # Wait a moment for mount to be ready
        for attempt in range(5):
            try:
                # Verify mount by checking if directory is accessible (read-only)
                # Try to list the directory to confirm mount worked
                entries = os.listdir(mount_point)

                # Try to stat the mount point itself
                stat_info = os.stat(mount_point)

                logger.debug(
                    "Mount verification successful (read-only check)",
                    mount_point=mount_point,
                    attempt=attempt + 1,
                    entries_count=len(entries)
                )
                return  # Success!

            except Exception as e:
                if attempt < 4:
                    # Wait and retry
                    await asyncio.sleep(1)
                else:
                    # Final attempt failed
                    raise Exception(
                        f"Mount verification failed - cannot access {mount_point}: {str(e)}"
                    )

    async def _unmount_fuse(self, mount_point: str, force: bool = False) -> bool:
        """Unmount a FUSE filesystem (SSHFS)"""
        # Choose unmount command based on platform
        if platform.system() == "Darwin":
            cmd = ["umount"]
            if force:
                cmd.append("-f")
            cmd.append(mount_point)
        else:
            cmd = ["fusermount"]
            if force:
                cmd.append("-uz")  # -u unmount, -z lazy
            else:
                cmd.append("-u")
            cmd.append(mount_point)

        # Try unmount with retries
        for attempt in range(3):
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=10
                )

                if process.returncode == 0:
                    logger.info(
                        "Successfully unmounted FUSE",
                        mount_point=mount_point,
                        attempt=attempt + 1
                    )
                    return True
                else:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    logger.warning(
                        "Unmount attempt failed",
                        mount_point=mount_point,
                        attempt=attempt + 1,
                        error=error_msg
                    )

                    # Wait before retry
                    if attempt < 2:
                        await asyncio.sleep(2)

            except asyncio.TimeoutError:
                logger.warning(
                    "Unmount timeout",
                    mount_point=mount_point,
                    attempt=attempt + 1
                )
                if attempt < 2:
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(
                    "Unmount error",
                    mount_point=mount_point,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt < 2:
                    await asyncio.sleep(2)

        return False

    async def _unmount_borg(self, mount_point: str, force: bool = False) -> bool:
        """Unmount a Borg mount"""
        # Try borg umount first
        for attempt in range(3):
            try:
                cmd = ["borg", "umount", mount_point]

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=10
                )

                if process.returncode == 0:
                    logger.info(
                        "Successfully unmounted Borg",
                        mount_point=mount_point,
                        attempt=attempt + 1
                    )
                    return True
                else:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    logger.warning(
                        "Borg unmount attempt failed",
                        mount_point=mount_point,
                        attempt=attempt + 1,
                        error=error_msg
                    )

                    # Try fusermount as fallback
                    if attempt == 2 or force:
                        return await self._unmount_fuse(mount_point, force=True)

                    await asyncio.sleep(2)

            except asyncio.TimeoutError:
                logger.warning(
                    "Borg unmount timeout",
                    mount_point=mount_point,
                    attempt=attempt + 1
                )
                if attempt < 2:
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(
                    "Borg unmount error",
                    mount_point=mount_point,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt < 2:
                    await asyncio.sleep(2)

        return False

    def _cleanup_temp_files(
        self,
        temp_root: Optional[str],
        temp_key_file: Optional[str]
    ):
        """Cleanup temporary directories and key files"""
        # Cleanup temp root directory
        if temp_root and os.path.exists(temp_root):
            try:
                shutil.rmtree(temp_root, ignore_errors=True)
                logger.debug("Cleaned up temp root", temp_root=temp_root)
            except Exception as e:
                logger.warning(
                    "Failed to cleanup temp root",
                    temp_root=temp_root,
                    error=str(e)
                )

        # Cleanup temp key file
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
                logger.debug("Cleaned up temp key file", key_file=temp_key_file)
            except Exception as e:
                logger.warning(
                    "Failed to cleanup temp key file",
                    key_file=temp_key_file,
                    error=str(e)
                )

    def _validate_mount_point(self, path: str):
        """
        Validate mount point is safe

        Raises:
            Exception: If path is not safe
        """
        # Reject sensitive system paths
        sensitive = ['/etc', '/root', '/sys', '/proc', '/boot', '/dev', '/var', '/usr']
        for s in sensitive:
            if path.startswith(s):
                raise Exception(f"Cannot mount to sensitive path: {s}")

        # Prevent path traversal
        if '..' in path:
            raise Exception("Path traversal not allowed")

        # Must be absolute path
        if not os.path.isabs(path):
            raise Exception("Mount point must be an absolute path")


# Global singleton instance
mount_service = MountService()
