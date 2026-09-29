"""
Filesystem browsing API endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import os
import shlex
import subprocess
import structlog
import tempfile
from datetime import datetime, timezone

from app.core.security import (
    decrypt_secret,
    get_current_user,
    require_role_dependency,
)
from app.database.database import get_db
from sqlalchemy.orm import Session
from app.database.models import SSHConnection, SSHKey
from app.config import settings
from app.utils.ssh_host_keys import host_key_ssh_opts_for_host
from app.utils.datetime_utils import serialize_datetime
from app.utils.ssh_utils import resolve_ssh_key_file_by_id, ssh_key_auth_args
from app.utils.local_paths import is_within_local_mount, mount_entries_below
from app.utils.ssh_host_validation import (
    normalize_ssh_host,
    normalize_ssh_username,
    ssh_destination,
)

logger = structlog.get_logger()

# Admin or operator: the repository wizard, backup plan source picker and
# restore destination picker are the only callers.
router = APIRouter(
    dependencies=[
        Depends(
            require_role_dependency(
                "admin",
                "operator",
                detail_key="backend.errors.filesystem.operatorAccessRequired",
            )
        )
    ]
)


def _confined(user) -> bool:
    # Admins configure the mounts and repositories themselves, so only
    # operators are held to LOCAL_MOUNT_POINTS.
    return user.role != "admin"


def _require_local_mount_path(path: str, user) -> str:
    """Resolve a local path and refuse it unless it is inside a mount point."""
    resolved = os.path.realpath(path)
    if _confined(user) and not is_within_local_mount(resolved):
        raise HTTPException(
            status_code=403,
            detail={
                "key": "backend.errors.filesystem.permissionDenied",
                "params": {"path": path},
            },
        )
    return resolved


SSH_REMOTE_PATH_FAILURE_MARKERS = (
    "remote readdir",
    "permission denied",
    "no such file",
    "not found",
    "couldn't",
    "cannot",
    "failure",
)

# sftp batch files have no quoting that survives these: a newline ends the
# command, and a following line starting with "!" runs on this host.
SFTP_BATCH_UNSAFE_CHARS = ("\n", "\r", "\0", '"')


class FileSystemItem(BaseModel):
    """Represents a file or directory in the filesystem"""

    name: str
    path: str
    is_directory: bool
    size: Optional[int] = None
    modified: Optional[str] = None
    is_borg_repo: bool = False
    is_local_mount: bool = False  # Whether this is a host filesystem mount point
    permissions: Optional[str] = None


class BrowseResponse(BaseModel):
    """Response for filesystem browse operation"""

    current_path: str
    items: List[FileSystemItem]
    parent_path: Optional[str] = None
    is_inside_local_mount: bool = False  # Whether current path is inside a host mount


def is_borg_repository(path: str) -> bool:
    """
    Detect if a directory is a Borg repository by checking for required files/directories.

    A Borg repository must have:
    - config file (contains repository metadata)
    - data/ directory (stores deduplicated chunks)

    Optional indicators:
    - README file
    - lock.roster file
    - hints.* files
    """
    try:
        if not os.path.isdir(path):
            return False

        # Check for required Borg repository structure
        config_file = os.path.join(path, "config")
        data_dir = os.path.join(path, "data")

        has_config = os.path.isfile(config_file)
        has_data_dir = os.path.isdir(data_dir)

        # Both must exist for it to be a Borg repo
        if has_config and has_data_dir:
            # Additional validation: check if config file has Borg-specific content
            try:
                with open(config_file, "r") as f:
                    content = f.read(100)  # Read first 100 bytes
                    # Borg config files typically start with [repository]
                    if "[repository]" in content:
                        return True
            except:
                pass

            # Even without reading config, if both exist, it's likely a Borg repo
            return True

        return False
    except Exception as e:
        logger.warning(
            "Error checking if directory is Borg repo", path=path, error=str(e)
        )
        return False


def is_borg_repository_ssh(
    host: str, username: str, ssh_key_path: str, remote_path: str, port: int = 22
) -> bool:
    """
    Detect if a remote directory is a Borg repository via SSH.
    """
    try:
        # Check for config file and data directory using 'ls' (compatible with restricted shells)
        # We'll check if both config and data exist
        check_cmd = (
            f"ls {shlex.quote(f'{remote_path}/config')} "
            f"{shlex.quote(f'{remote_path}/data')}"
        )

        ssh_cmd = [
            "ssh",
            *ssh_key_auth_args(ssh_key_path),
            "-p",
            str(port),
            *host_key_ssh_opts_for_host(host, port, username),
            "-o",
            "ConnectTimeout=5",
            "--",
            ssh_destination(username, host),
            check_cmd,
        ]

        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)

        # If both files exist, ls will output both paths
        # Check if output contains both "config" and "data"
        output = result.stdout.strip()
        return "config" in output and "data" in output and result.returncode == 0
    except Exception as e:
        logger.warning(
            "Error checking remote Borg repo", host=host, path=remote_path, error=str(e)
        )
        return False


def _get_matching_ssh_connection(
    db: Session, ssh_key_id: int, host: str, username: str, port: int
):
    try:
        return (
            db.query(SSHConnection)
            .filter(
                SSHConnection.ssh_key_id == ssh_key_id,
                SSHConnection.host == host,
                SSHConnection.username == username,
                SSHConnection.port == port,
            )
            .first()
        )
    except Exception:
        return None


def _validate_remote_path(path: Optional[str]) -> None:
    """Refuse a path that would break out of its sftp batch argument."""
    if path and any(char in path for char in SFTP_BATCH_UNSAFE_CHARS):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.filesystem.invalidRemotePath"},
        )


def _resolve_ssh_target(
    db: Session, current_user, ssh_key_id: int, host: str, username: str, port: int
):
    """Normalize host and username, and keep non-admins on saved connections.

    A stored key is only ever used against the target it was saved with, so a
    non-admin cannot point the server's private key at a host of their choice.
    """
    try:
        host = normalize_ssh_host(host)
        username = normalize_ssh_username(username)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.filesystem.invalidSshTarget"},
        )

    connection = _get_matching_ssh_connection(db, ssh_key_id, host, username, port)
    if connection is None and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail={"key": "backend.errors.filesystem.sshConnectionNotSaved"},
        )
    return host, username, connection


def _login_relative_remote_path_candidate(
    remote_path: str, default_path: Optional[str] = None
) -> Optional[str]:
    normalized = (remote_path or "").strip()
    if not normalized.startswith("/") or normalized == "/":
        return None
    if normalized.startswith("/./"):
        relative_path = normalized.lstrip("/")
        return relative_path or None

    normalized_default_path = (default_path or "").strip()
    if normalized_default_path not in {"", "/"}:
        return None

    relative_path = normalized.lstrip("/")
    return relative_path or None


SFTP_PWD_PREFIX = "Remote working directory:"


def _sftp_working_directory(stdout: str) -> Optional[str]:
    """The absolute path sftp's pwd printed, or None if it printed none."""
    for line in (stdout or "").splitlines():
        if line.startswith(SFTP_PWD_PREFIX):
            cwd = line[len(SFTP_PWD_PREFIX) :].strip()
            if cwd.startswith("/") and not any(
                char in cwd for char in SFTP_BATCH_UNSAFE_CHARS
            ):
                return os.path.normpath(cwd)
    return None


def _run_sftp_batch(
    key_file: str, host: str, username: str, port: int, commands: List[str]
):
    """Run sftp batch commands. SFTP only, so restricted shells work too."""
    batch_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".sftp"
        ) as batch_f:
            batch_f.write("".join(f"{command}\n" for command in commands))
            batch_file = batch_f.name

        sftp_cmd = [
            "sftp",
            "-b",
            batch_file,
            *ssh_key_auth_args(key_file),
            "-P",
            str(port),
            *host_key_ssh_opts_for_host(host, port, username),
            "-o",
            "ConnectTimeout=10",
            "--",
            ssh_destination(username, host),
        ]
        return subprocess.run(sftp_cmd, capture_output=True, text=True, timeout=30)
    finally:
        if batch_file and os.path.exists(batch_file):
            try:
                os.unlink(batch_file)
            except Exception:
                pass


def _join_remote_path(base_path: str, name: str) -> str:
    if not base_path:
        return name
    return os.path.join(base_path, name)


def _remote_path_command_failed(result) -> bool:
    output = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
    return result.returncode != 0 or any(
        marker in output for marker in SSH_REMOTE_PATH_FAILURE_MARKERS
    )


def _remote_file_exists_error(result) -> bool:
    output = f"{result.stderr or ''}\n{result.stdout or ''}".lower()
    return "file exists" in output


@router.get("/browse", response_model=BrowseResponse)
async def browse_filesystem(
    path: str = Query("/local", description="Path to browse"),
    connection_type: str = Query("local", description="Connection type: local or ssh"),
    ssh_key_id: Optional[int] = Query(
        None, description="SSH key ID for remote browsing"
    ),
    host: Optional[str] = Query(None, description="SSH host"),
    username: Optional[str] = Query(None, description="SSH username"),
    port: int = Query(22, description="SSH port"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Browse filesystem directories.

    For local paths: browses the container's filesystem (including /local mount)
    For SSH paths: browses remote filesystem via SSH connection
    """
    try:
        if connection_type == "local":
            return await browse_local_filesystem(path, confine=_confined(current_user))
        elif connection_type == "ssh":
            if not all([ssh_key_id, host, username]):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.filesystem.sshParamsRequired"},
                )

            # Check if SSH connection has a default_path and use it when path is "/" or "/local"
            host, username, ssh_connection = _resolve_ssh_target(
                db, current_user, ssh_key_id, host, username, port
            )

            if (
                ssh_connection
                and ssh_connection.default_path
                and path in ["/", "/local"]
            ):
                logger.info(
                    "Using default_path from SSH connection",
                    ssh_key_id=ssh_key_id,
                    host=host,
                    default_path=ssh_connection.default_path,
                    original_path=path,
                )
                path = ssh_connection.default_path

            return await browse_ssh_filesystem(
                path, ssh_key_id, host, username, port, db
            )
        else:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.filesystem.invalidConnectionType"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error browsing filesystem", path=path, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to browse filesystem: {str(e)}"
        )


@router.get("/ssh-home")
async def ssh_home_directory(
    ssh_key_id: int = Query(..., description="SSH key ID"),
    host: str = Query(..., description="SSH host"),
    username: str = Query(..., description="SSH username"),
    port: int = Query(22, description="SSH port"),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The folder an SSH login lands in, or null when the machine does not say.

    Cheaper than browsing "/": no listing and no per-folder repository checks.
    """
    host, username, _ = _resolve_ssh_target(
        db, current_user, ssh_key_id, host, username, port
    )
    key_file = resolve_ssh_key_file_by_id(ssh_key_id, db)
    if not key_file:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.ssh.sshKeyNotFound"}
        )
    try:
        result = await asyncio.to_thread(
            _run_sftp_batch, key_file, host, username, port, ["pwd"]
        )
    except Exception as exc:
        # Only a prefill hint: a timeout, host-key lookup or target error
        # means "no suggestion", never a failed request.
        logger.warning("SSH home lookup failed", host=host, error=str(exc))
        return {"path": None}
    finally:
        os.unlink(key_file)
    if result.returncode != 0:
        return {"path": None}
    return {"path": _sftp_working_directory(result.stdout)}


async def browse_local_filesystem(path: str, confine: bool = True) -> BrowseResponse:
    """Browse local filesystem"""
    # Symlinks and ".." are resolved before the mount check. Ancestors of a
    # mount point (such as "/") list only the entries leading down to it.
    path = os.path.realpath(path)
    visible_entries = None
    if confine and not is_within_local_mount(path):
        visible_entries = mount_entries_below(path)
        if not visible_entries:
            raise HTTPException(
                status_code=403,
                detail={
                    "key": "backend.errors.filesystem.permissionDenied",
                    "params": {"path": path},
                },
            )

    # Check if path exists
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail={
                "key": "backend.errors.filesystem.pathNotFound",
                "params": {"path": path},
            },
        )

    # Check if path is a directory
    if not os.path.isdir(path):
        raise HTTPException(
            status_code=400,
            detail={
                "key": "backend.errors.filesystem.pathNotDirectory",
                "params": {"path": path},
            },
        )

    items = []

    try:
        # List directory contents
        entries = os.listdir(path)
        if visible_entries is not None:
            entries = [entry for entry in entries if entry in visible_entries]

        # Get mount points once for reuse
        mount_points = settings.get_local_mount_points()

        for entry in entries:
            try:
                full_path = os.path.join(path, entry)
                stat_info = os.stat(full_path)
                is_dir = os.path.isdir(full_path)

                # Check if directory is a Borg repository
                is_borg = False
                if is_dir:
                    is_borg = is_borg_repository(full_path)

                # Check if this path is a local mount point (host filesystem)
                # Only mark the mount point itself, not its children
                is_local = is_dir and full_path in mount_points

                item = FileSystemItem(
                    name=entry,
                    path=full_path,
                    is_directory=is_dir,
                    size=stat_info.st_size if not is_dir else None,
                    modified=serialize_datetime(
                        datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc)
                    ),
                    is_borg_repo=is_borg,
                    is_local_mount=is_local,
                    permissions=oct(stat_info.st_mode)[-3:],
                )
                items.append(item)
            except (PermissionError, OSError) as e:
                # Skip items we can't access
                logger.debug("Skipping inaccessible item", item=entry, error=str(e))
                continue

        # Sort items: local mounts first, then directories, then alphabetically
        items.sort(
            key=lambda x: (not x.is_local_mount, not x.is_directory, x.name.lower())
        )

        # Get parent path
        parent_path = os.path.dirname(path) if path != "/" else None

        # Check if current path is inside a local mount
        is_inside_mount = any(
            path == mp or path.startswith(mp + "/") for mp in mount_points
        )

        return BrowseResponse(
            current_path=path,
            items=items,
            parent_path=parent_path,
            is_inside_local_mount=is_inside_mount,
        )

    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail={
                "key": "backend.errors.filesystem.permissionDenied",
                "params": {"path": path},
            },
        )


async def browse_ssh_filesystem(
    path: str, ssh_key_id: int, host: str, username: str, port: int, db: Session
) -> BrowseResponse:
    """Browse remote filesystem via SSH"""
    import tempfile
    from app.config import settings

    # Get SSH key
    ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
    if not ssh_key:
        raise HTTPException(
            status_code=404, detail={"key": "backend.errors.ssh.sshKeyNotFound"}
        )

    # Decrypt private key
    private_key = decrypt_secret(ssh_key.private_key)

    # Ensure private key ends with newline
    if not private_key.endswith("\n"):
        private_key += "\n"

    # Create temporary key file
    temp_key_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(private_key)
            temp_key_file = f.name

        os.chmod(temp_key_file, 0o600)

        def run_sftp_listing(cd_path: Optional[str]):
            _validate_remote_path(cd_path)
            # Without a cd, sftp lists the login directory; pwd names it.
            logger.info("Browsing SSH path via SFTP", host=host, path=path)
            commands = [f'cd "{cd_path}"' if cd_path else "pwd", "ls -la"]
            return _run_sftp_batch(temp_key_file, host, username, port, commands)

        def has_sftp_listing_entries(stdout: str) -> bool:
            for line in stdout.strip().split("\n"):
                if (
                    not line
                    or line.startswith("sftp>")
                    or line.startswith("total")
                    or "Connecting to" in line
                ):
                    continue
                return True
            return False

        def sftp_listing_failed(result) -> bool:
            if result.returncode != 0:
                return True

            stderr = (result.stderr or "").lower()
            return any(
                marker in stderr for marker in SSH_REMOTE_PATH_FAILURE_MARKERS
            ) and not (result.stdout and has_sftp_listing_entries(result.stdout))

        ssh_connection = _get_matching_ssh_connection(
            db, ssh_key_id, host, username, port
        )
        connection_default_path = getattr(ssh_connection, "default_path", None)

        # Use SFTP for browsing (compatible with restricted shells like Hetzner Storage Box)
        # SFTP batch commands: ls -la shows detailed listing
        result = run_sftp_listing(None if path == "/" else path)
        effective_command_path = "" if path == "/" else path

        if path.startswith("/") and path != "/" and sftp_listing_failed(result):
            relative_path = _login_relative_remote_path_candidate(
                path, connection_default_path
            )
            if relative_path:
                logger.info(
                    "Retrying SFTP path relative to login directory",
                    host=host,
                    path=path,
                    relative_path=relative_path,
                    stderr=result.stderr[:500] if result.stderr else None,
                )
                retry_result = run_sftp_listing(relative_path)
                if not sftp_listing_failed(retry_result):
                    effective_command_path = relative_path
                result = retry_result

        if sftp_listing_failed(result):
            error_msg = (
                result.stderr.strip()
                if result.stderr
                else result.stdout.strip()
                if result.stdout
                else "Unknown error"
            )
            logger.error(
                "SFTP ls command failed",
                host=host,
                path=path,
                returncode=result.returncode,
                stderr=result.stderr[:500] if result.stderr else None,
                stdout=result.stdout[:500] if result.stdout else None,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to list remote directory '{path}': {error_msg or 'Permission denied or path not found'}",
            )

        # "/" lists the login directory (see #488), so report its real path.
        if path == "/":
            path = _sftp_working_directory(result.stdout) or path

        # Log raw output for debugging
        output_lines = result.stdout.strip().split("\n")
        logger.info(
            "SFTP ls output received",
            path=path,
            lines_count=len(output_lines),
            first_few_lines=output_lines[:5] if output_lines else [],
        )

        # Parse SFTP ls output
        items = []
        lines = result.stdout.strip().split("\n")
        seen_names = set()  # Track seen names to avoid duplicates

        for line in lines:
            # Skip SFTP prompts, commands echoed back, and total lines
            if (
                not line
                or line.startswith("sftp>")
                or line.startswith("total")
                or line.startswith(SFTP_PWD_PREFIX)
                or "Connecting to" in line
            ):
                continue

            try:
                # Parse ls -lA output
                # Format: drwxr-xr-x 2 user group 4096 Nov 26 10:30 name
                # or:     drwxr-xr-x 2 user group 4096 2023-11-26 name
                parts = line.split(None, 8)
                if len(parts) < 9:
                    logger.debug(
                        "Skipping malformed line", line=line, parts_count=len(parts)
                    )
                    continue

                permissions = parts[0]
                try:
                    size = int(parts[4])
                except (ValueError, IndexError):
                    logger.warning("Failed to parse size", line=line)
                    continue

                # The filename is everything after the 8th split
                # This handles filenames with spaces
                name = parts[8].strip()

                # For timestamp, we'll use current time as fallback since parsing varies
                timestamp = int(datetime.now().timestamp())

                # Skip . and ..
                if name in [".", ".."]:
                    continue

                # Skip empty names
                if not name:
                    logger.debug("Skipping empty name", line=line)
                    continue

                # Skip duplicates
                if name in seen_names:
                    logger.warning(
                        "Skipping duplicate entry", name=name, path=path, line=line
                    )
                    continue
                seen_names.add(name)

                is_dir = permissions.startswith("d")
                full_path = os.path.join(path, name)
                command_path = _join_remote_path(effective_command_path, name)

                # Check if directory is a Borg repository
                is_borg = False
                if is_dir:
                    is_borg = is_borg_repository_ssh(
                        host, username, temp_key_file, command_path, port
                    )

                item = FileSystemItem(
                    name=name,
                    path=full_path,
                    is_directory=is_dir,
                    size=size if not is_dir else None,
                    modified=serialize_datetime(
                        datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    ),
                    is_borg_repo=is_borg,
                    is_local_mount=False,  # SSH paths are not local mounts
                    permissions=permissions[1:] if len(permissions) > 1 else None,
                )
                items.append(item)
                logger.debug(
                    "Parsed SSH ls entry", name=name, is_dir=is_dir, path=full_path
                )
            except (ValueError, IndexError) as e:
                logger.debug("Failed to parse ls line", line=line, error=str(e))
                continue

        # Sort items: local mounts first, then directories, then alphabetically
        items.sort(
            key=lambda x: (not x.is_local_mount, not x.is_directory, x.name.lower())
        )

        # Get parent path
        parent_path = os.path.dirname(path) if path != "/" else None

        # Check if current path is inside a local mount
        mount_points = settings.get_local_mount_points()
        is_inside_mount = any(
            path == mp or path.startswith(mp + "/") for mp in mount_points
        )

        return BrowseResponse(
            current_path=path,
            items=items,
            parent_path=parent_path,
            is_inside_local_mount=is_inside_mount,
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail={"key": "backend.errors.filesystem.sshConnectionTimeout"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error browsing SSH filesystem",
            host=host,
            path=path,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to browse remote filesystem: {str(e) or 'Unknown error'}",
        )
    finally:
        # Clean up temporary key file
        if temp_key_file and os.path.exists(temp_key_file):
            try:
                os.unlink(temp_key_file)
            except Exception as e:
                logger.warning("Failed to delete temporary SSH key file", error=str(e))


@router.post("/validate-path")
async def validate_path(
    path: str = Query(..., description="Path to validate"),
    connection_type: str = Query("local", description="Connection type"),
    ssh_key_id: Optional[int] = Query(None),
    host: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    port: int = Query(22),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Validate if a path exists and is accessible.
    Returns info about the path including if it's a Borg repository.
    """
    try:
        if connection_type == "local":
            _require_local_mount_path(path, current_user)
            exists = os.path.exists(path)
            is_dir = os.path.isdir(path) if exists else False
            is_borg = is_borg_repository(path) if is_dir else False

            return {
                "exists": exists,
                "is_directory": is_dir,
                "is_borg_repo": is_borg,
                "path": path,
            }
        elif connection_type == "ssh":
            import tempfile

            if not all([ssh_key_id, host, username]):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.filesystem.sshParamsRequired"},
                )

            host, username, _ = _resolve_ssh_target(
                db, current_user, ssh_key_id, host, username, port
            )

            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
            if not ssh_key:
                raise HTTPException(
                    status_code=404, detail={"key": "backend.errors.ssh.sshKeyNotFound"}
                )

            # Decrypt private key
            private_key = decrypt_secret(ssh_key.private_key)

            # Ensure private key ends with newline
            if not private_key.endswith("\n"):
                private_key += "\n"

            # Create temporary key file
            temp_key_file = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                    f.write(private_key)
                    temp_key_file = f.name

                os.chmod(temp_key_file, 0o600)

                def run_ssh_stat(command_path: str):
                    # Check if path exists via SSH using 'stat' (compatible with restricted shells like Hetzner Storage Box)
                    # stat returns exit code 0 if path exists, non-zero if not
                    check_cmd = f"stat {shlex.quote(command_path)}"

                    ssh_cmd = [
                        "ssh",
                        *ssh_key_auth_args(temp_key_file),
                        "-p",
                        str(port),
                        *host_key_ssh_opts_for_host(host, port, username),
                        "-o",
                        "ConnectTimeout=5",
                        "--",
                        ssh_destination(username, host),
                        check_cmd,
                    ]

                    return subprocess.run(
                        ssh_cmd, capture_output=True, text=True, timeout=10
                    )

                ssh_connection = _get_matching_ssh_connection(
                    db, ssh_key_id, host, username, port
                )
                connection_default_path = getattr(ssh_connection, "default_path", None)
                command_path = path
                result = run_ssh_stat(command_path)
                retry_path = _login_relative_remote_path_candidate(
                    path, connection_default_path
                )
                if retry_path and result.returncode != 0:
                    retry_result = run_ssh_stat(retry_path)
                    if retry_result.returncode == 0:
                        command_path = retry_path
                    result = retry_result

                # Parse stat output to determine if path exists and is a directory
                exists = result.returncode == 0
                is_dir = False
                if exists and result.stdout:
                    # stat output contains file type info
                    # Look for "directory" in the output (works on Linux/BSD/restricted shells)
                    output_lower = result.stdout.lower()
                    is_dir = "directory" in output_lower or "dir" in output_lower
                is_borg = (
                    is_borg_repository_ssh(
                        host, username, temp_key_file, command_path, port
                    )
                    if is_dir
                    else False
                )

                return {
                    "exists": exists,
                    "is_directory": is_dir,
                    "is_borg_repo": is_borg,
                    "path": path,
                }
            finally:
                # Clean up temporary key file
                if temp_key_file and os.path.exists(temp_key_file):
                    try:
                        os.unlink(temp_key_file)
                    except Exception as e:
                        logger.warning(
                            "Failed to delete temporary SSH key file", error=str(e)
                        )
        else:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.filesystem.invalidConnectionType"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error validating path", path=path, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to validate path: {str(e)}"
        )


class CreateFolderRequest(BaseModel):
    path: str
    folder_name: str
    connection_type: str = "local"
    ssh_key_id: Optional[int] = None
    host: Optional[str] = None
    username: Optional[str] = None
    port: int = 22


@router.post("/create-folder")
async def create_folder(
    request: CreateFolderRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new folder in the specified path"""
    path = request.path
    folder_name = request.folder_name
    connection_type = request.connection_type
    ssh_key_id = request.ssh_key_id
    host = request.host
    username = request.username
    port = request.port
    try:
        # Sanitize folder name to prevent path traversal
        folder_name = folder_name.strip().replace("/", "").replace("..", "")
        if not folder_name:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.filesystem.invalidFolderName"},
            )

        full_path = os.path.join(path, folder_name)

        if connection_type == "local":
            _require_local_mount_path(full_path, current_user)
            # Create local folder
            try:
                os.makedirs(full_path, exist_ok=False)
                logger.info(
                    "Created local folder", path=full_path, user=current_user.username
                )
                return {
                    "success": True,
                    "path": full_path,
                    "message": "backend.success.filesystem.folderCreated",
                }
            except FileExistsError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.filesystem.folderAlreadyExists",
                        "params": {"name": folder_name},
                    },
                )
            except PermissionError:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "key": "backend.errors.filesystem.permissionDeniedCreateFolder"
                    },
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Failed to create folder: {str(e)}"
                )

        elif connection_type == "ssh":
            # Create folder via SFTP (works with restricted shells like Hetzner)
            if not all([ssh_key_id, host, username]):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.filesystem.sshConnectionDetailsRequired"
                    },
                )

            host, username, _ = _resolve_ssh_target(
                db, current_user, ssh_key_id, host, username, port
            )

            # Get SSH key
            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
            if not ssh_key:
                raise HTTPException(
                    status_code=404, detail={"key": "backend.errors.ssh.sshKeyNotFound"}
                )

            # Decrypt private key
            private_key = decrypt_secret(ssh_key.private_key)

            # Ensure private key ends with newline
            if not private_key.endswith("\n"):
                private_key += "\n"

            # Create temporary key file
            temp_key_file = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                    f.write(private_key)
                    temp_key_file = f.name
                os.chmod(temp_key_file, 0o600)

                def run_sftp_mkdir(command_path: str):
                    _validate_remote_path(command_path)
                    sftp_batch_file = None
                    try:
                        # Create SFTP batch file to create directory
                        with tempfile.NamedTemporaryFile(
                            mode="w", delete=False, suffix=".sftp"
                        ) as batch_f:
                            batch_f.write(f'mkdir "{command_path}"\n')
                            sftp_batch_file = batch_f.name

                        logger.info(
                            "Creating folder via SFTP", host=host, path=command_path
                        )

                        sftp_cmd = [
                            "sftp",
                            "-b",
                            sftp_batch_file,
                            *ssh_key_auth_args(temp_key_file),
                            "-P",
                            str(port),
                            *host_key_ssh_opts_for_host(host, port, username),
                            "-o",
                            "ConnectTimeout=10",
                            "--",
                            ssh_destination(username, host),
                        ]

                        return subprocess.run(
                            sftp_cmd, capture_output=True, text=True, timeout=30
                        )
                    finally:
                        if sftp_batch_file and os.path.exists(sftp_batch_file):
                            try:
                                os.unlink(sftp_batch_file)
                            except Exception:
                                pass

                ssh_connection = _get_matching_ssh_connection(
                    db, ssh_key_id, host, username, port
                )
                connection_default_path = getattr(ssh_connection, "default_path", None)
                result = run_sftp_mkdir(full_path)

                if _remote_path_command_failed(
                    result
                ) and not _remote_file_exists_error(result):
                    retry_path = _login_relative_remote_path_candidate(
                        full_path, connection_default_path
                    )
                    if retry_path:
                        retry_result = run_sftp_mkdir(retry_path)
                        result = retry_result

                if not _remote_path_command_failed(result):
                    logger.info("Created remote folder", host=host, path=full_path)
                    return {
                        "success": True,
                        "path": full_path,
                        "message": "backend.success.filesystem.folderCreated",
                    }
                elif _remote_file_exists_error(result):
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "key": "backend.errors.filesystem.folderAlreadyExists",
                            "params": {"name": folder_name},
                        },
                    )
                else:
                    error_msg = (
                        result.stderr.strip() if result.stderr else "Unknown error"
                    )
                    logger.error(
                        "Failed to create remote folder",
                        host=host,
                        path=full_path,
                        stderr=result.stderr[:500] if result.stderr else None,
                    )
                    raise HTTPException(
                        status_code=500, detail=f"Failed to create folder: {error_msg}"
                    )

            finally:
                # Clean up temporary files
                if temp_key_file and os.path.exists(temp_key_file):
                    try:
                        os.unlink(temp_key_file)
                    except Exception:
                        pass
        else:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.filesystem.invalidConnectionType"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error creating folder",
            path=path,
            folder_name=folder_name,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to create folder: {str(e)}"
        )
