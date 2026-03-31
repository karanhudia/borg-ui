"""Filesystem utilities shared across the application."""

from __future__ import annotations

import asyncio
import re
import structlog
from typing import Optional

logger = structlog.get_logger()


async def calculate_path_size_bytes(
    paths: list[str],
    exclude_patterns: list[str] | None = None,
    timeout: int = 3600,
) -> int:
    """Calculate total size in bytes for a list of local or SSH paths using du.

    Supports:
      - Local paths (e.g. /mnt/backup)
      - SSH URLs  (e.g. ssh://user@host:port/path)

    Exclude patterns use the same format as Borg excludes.
    Returns 0 if all paths fail or the total is empty.
    """
    if exclude_patterns is None:
        exclude_patterns = []

    total_size = 0

    for path in paths:
        try:
            if path.startswith("ssh://"):
                path_size = await _du_ssh(path, exclude_patterns, timeout)
            else:
                path_size = await _du_local(path, exclude_patterns, timeout)

            if path_size is not None:
                total_size += path_size

        except asyncio.TimeoutError:
            logger.warning("Timeout calculating directory size", path=path, timeout_seconds=timeout)
        except Exception as e:
            logger.warning("Error calculating directory size", path=path, error=str(e))

    return total_size


async def _du_local(path: str, exclude_patterns: list[str], timeout: int) -> Optional[int]:
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


async def _du_ssh(path: str, exclude_patterns: list[str], timeout: int) -> Optional[int]:
    match = re.match(r"ssh://([^@]+)@([^:]+):(\d+)(/.*)", path)
    if not match:
        logger.warning("Invalid SSH URL format", path=path)
        return None

    username, host, port, remote_path = match.groups()

    du_excludes = ""
    for pattern in exclude_patterns:
        safe_pattern = pattern.replace("'", "'\\''")
        du_excludes += f" --exclude='{safe_pattern}'"

    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=10",
        "-p", port,
        f"{username}@{host}",
        f"du -sb{du_excludes} {remote_path} 2>/dev/null | cut -f1",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

    if process.returncode == 0:
        output = stdout.decode().strip()
        if output and output.isdigit():
            return int(output)

    logger.warning("du failed for SSH path", path=path, stderr=stderr.decode())
    return None
