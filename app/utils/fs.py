"""Filesystem utilities shared across the application."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import structlog
from typing import Optional

from app.utils.ssh_host_keys import host_key_ssh_opts_for_path
from app.utils.ssh_utils import public_key_only_ssh_args, ssh_key_auth_args

logger = structlog.get_logger()


def active_mount_points() -> Optional[set[str]]:
    """Mount points visible to this process, or None when they cannot be read."""
    try:
        with open("/proc/self/mounts", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        # /proc escapes whitespace in paths as octal (\040 for a space).
        return {
            re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), parts[1])
            for parts in (line.split() for line in lines)
            if len(parts) >= 2
        }
    except OSError:
        pass

    # No /proc (macOS dev hosts): parse `mount`, "<source> on <point> (...)".
    try:
        result = subprocess.run(["mount"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    points = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if "on" in parts and parts.index("on") + 1 < len(parts):
            points.add(parts[parts.index("on") + 1])
    return points


def remove_tree_without_crossing_mounts(path: str) -> bool:
    """Delete a directory tree, never deleting through a mounted filesystem.

    shutil.rmtree follows directories into whatever is mounted on them, so an
    SSHFS/NFS/bind mount left under a temp root turns cleanup into deletion of
    the remote or host files behind it. This refuses the whole tree when the
    mount table shows anything mounted at or under ``path`` (or cannot be read),
    and while walking skips any directory on a different device than ``path``.
    Returns True when the tree is gone.
    """
    root = os.path.abspath(path)
    if not os.path.lexists(root):
        return True

    mount_points = active_mount_points()
    if mount_points is None:
        logger.error("Refusing to delete directory: mount table unavailable", path=root)
        return False
    candidates = {root, os.path.realpath(root)}
    mounted_inside = sorted(
        point
        for point in mount_points
        for candidate in candidates
        if point == candidate or point.startswith(candidate.rstrip("/") + "/")
    )
    if mounted_inside:
        logger.error(
            "Refusing to delete directory with a filesystem still mounted inside it",
            path=root,
            mount_points=mounted_inside,
        )
        return False

    try:
        root_stat = os.lstat(root)
    except OSError as e:
        logger.error("Refusing to delete unreadable directory", path=root, error=str(e))
        return False
    if not os.path.isdir(root) or os.path.islink(root):
        os.unlink(root)
        return True
    return _remove_same_device_tree(root, root_stat.st_dev)


def _remove_same_device_tree(directory: str, device: int) -> bool:
    # ponytail: recursive, fine for temp/staging roots; make it iterative if it
    # ever cleans trees deeper than Python's recursion limit.
    removed_all = True
    try:
        entries = list(os.scandir(directory))
    except OSError as e:
        logger.warning(
            "Could not list directory for cleanup", path=directory, error=str(e)
        )
        return False
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                if entry.stat(follow_symlinks=False).st_dev != device:
                    logger.error(
                        "Refusing to delete through a mounted filesystem",
                        path=entry.path,
                    )
                    removed_all = False
                elif not _remove_same_device_tree(entry.path, device):
                    removed_all = False
            else:
                os.unlink(entry.path)
        except OSError as e:
            logger.warning(
                "Could not delete path during cleanup", path=entry.path, error=str(e)
            )
            removed_all = False
    if removed_all:
        try:
            os.rmdir(directory)
        except OSError as e:
            logger.warning(
                "Could not delete directory during cleanup",
                path=directory,
                error=str(e),
            )
            return False
    return removed_all


async def calculate_path_size_bytes(
    paths: list[str],
    exclude_patterns: list[str] | None = None,
    timeout: int = 3600,
    key_file: str | None = None,
    key_files_by_ssh_target: dict[tuple[str, str, str], str] | None = None,
    login_relative_ssh_targets: set[tuple[str, str, str]] | None = None,
) -> int:
    """Calculate total size in bytes for a list of local or SSH paths using du.

    Supports:
      - Local paths (e.g. /mnt/backup)
      - SSH URLs  (e.g. ssh://user@host:port/path)

    Exclude patterns use the same format as Borg excludes.
    key_file: optional path to SSH private key for SSH paths.
    key_files_by_ssh_target: optional per-target SSH private keys keyed by
      (username, host, port).
    login_relative_ssh_targets: SSH targets where an empty/missing absolute du
      result may be retried relative to the SSH login directory.
    Returns 0 if all paths fail or the total is empty.
    """
    if exclude_patterns is None:
        exclude_patterns = []

    total_size = 0

    for path in paths:
        try:
            if path.startswith("ssh://"):
                path_key_file = key_file
                parsed = _parse_ssh_url(path)
                if not path_key_file and parsed and key_files_by_ssh_target:
                    username, host, port, _remote_path = parsed
                    path_key_file = key_files_by_ssh_target.get((username, host, port))
                login_relative_fallback = False
                if parsed and login_relative_ssh_targets:
                    username, host, port, _remote_path = parsed
                    login_relative_fallback = (
                        username,
                        host,
                        port,
                    ) in login_relative_ssh_targets
                path_size = await _du_ssh(
                    path,
                    exclude_patterns,
                    timeout,
                    key_file=path_key_file,
                    login_relative_fallback=login_relative_fallback,
                )
            else:
                path_size = await _du_local(path, exclude_patterns, timeout)

            if path_size is not None:
                total_size += path_size

        except asyncio.TimeoutError:
            logger.warning(
                "Timeout calculating directory size", path=path, timeout_seconds=timeout
            )
        except Exception as e:
            logger.warning("Error calculating directory size", path=path, error=str(e))

    return total_size


def _parse_ssh_url(path: str) -> Optional[tuple[str, str, str, str]]:
    match = re.match(r"ssh://([^@]+)@([^:]+):(\d+)(/.*)", path)
    if not match:
        return None
    return match.groups()


async def _du_local(
    path: str, exclude_patterns: list[str], timeout: int
) -> Optional[int]:
    cmd = ["du", "-s", "-B1"]
    for pattern in exclude_patterns:
        cmd.extend(["--exclude", pattern])
    cmd.append(path)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

    if process.returncode == 0:
        output = stdout.decode().strip()
        if output:
            return int(output.split("\t")[0])

    logger.warning("du failed for local path", path=path, stderr=stderr.decode())
    return None


async def _du_ssh(
    path: str,
    exclude_patterns: list[str],
    timeout: int,
    key_file: str | None = None,
    login_relative_fallback: bool = False,
) -> Optional[int]:
    parsed = _parse_ssh_url(path)
    if not parsed:
        logger.warning("Invalid SSH URL format", path=path)
        return None

    username, host, port, remote_path = parsed

    du_excludes = ""
    for pattern in exclude_patterns:
        safe_pattern = pattern.replace("'", "'\\''")
        du_excludes += f" --exclude='{safe_pattern}'"

    async def run_remote_du(command_remote_path: str):
        cmd = ["ssh"]
        if key_file:
            cmd.extend(ssh_key_auth_args(key_file))
        else:
            cmd.extend(public_key_only_ssh_args())
        cmd.extend(
            [
                *host_key_ssh_opts_for_path(path),
                "-o",
                "LogLevel=ERROR",
                "-o",
                "ConnectTimeout=10",
                "-p",
                port,
                f"{username}@{host}",
                f"du -sb{du_excludes} {command_remote_path} 2>/dev/null | cut -f1",
            ]
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

        output = stdout.decode().strip()
        if process.returncode == 0 and output and output.isdigit():
            return int(output), stderr
        return None, stderr

    path_size, stderr = await run_remote_du(remote_path)
    if path_size is not None:
        return path_size

    retry_remote_path = _login_relative_remote_path_candidate(remote_path)
    if login_relative_fallback and retry_remote_path:
        path_size, stderr = await run_remote_du(retry_remote_path)
        if path_size is not None:
            return path_size

    logger.warning("du failed for SSH path", path=path, stderr=stderr.decode())
    return None


def _login_relative_remote_path_candidate(remote_path: str) -> Optional[str]:
    normalized = (remote_path or "").strip()
    if not normalized.startswith("/") or normalized == "/":
        return None
    if normalized.startswith("/./"):
        relative_path = normalized.lstrip("/")
        return relative_path or None

    relative_path = normalized.lstrip("/")
    return relative_path or None
