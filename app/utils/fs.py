"""Filesystem utilities shared across the application."""

from __future__ import annotations

import asyncio
import re
import structlog
from typing import Optional

from app.utils.ssh_options import public_key_only_ssh_args, ssh_key_auth_args

logger = structlog.get_logger()


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
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
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
