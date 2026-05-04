"""Borg 2 command wrapper.

This module is the exclusive home for all borg2 binary interactions.
It is intentionally separate from borg.py — no cross-imports between the two.

Key command differences from Borg 1:
  Repository lifecycle:
    borg  init  REPO            → borg2 rcreate REPO
    borg  info  REPO            → borg2 rinfo   REPO
    borg  delete REPO           → borg2 rdelete REPO

  Archive operations (same CLI shape, different binary):
    borg2 create   REPO::ARCHIVE  ...
    borg2 list     REPO            (list archives)
    borg2 list     REPO::ARCHIVE  (list archive contents)
    borg2 info     REPO::ARCHIVE
    borg2 extract  REPO::ARCHIVE  ...
    borg2 delete   REPO::ARCHIVE
    borg2 prune    REPO
    borg2 compact  REPO           (mandatory after delete/prune — space not freed automatically)
    borg2 check    REPO
    borg2 mount    REPO::ARCHIVE  MOUNTPOINT

  Encryption modes (borg 2 only):
    repokey-aes-ocb            (default — recommended)
    repokey-chacha20-poly1305
    keyfile-aes-ocb
    keyfile-chacha20-poly1305
    authenticated
    none
"""

import asyncio
import subprocess
import os
import structlog
from typing import Dict, List, Optional

from app.config import settings

logger = structlog.get_logger()

BORG2_ENCRYPTION_MODES = [
    "repokey-aes-ocb",
    "repokey-chacha20-poly1305",
    "keyfile-aes-ocb",
    "keyfile-chacha20-poly1305",
    "authenticated",
    "none",
]

DEFAULT_BORG2_BINARY = "borg2"


def _get_borg2_binary() -> str:
    """Resolve the borg2 binary path from system settings (falls back to 'borg2')."""
    try:
        from app.database.database import SessionLocal
        from app.database.models import SystemSettings

        db = SessionLocal()
        try:
            sys_settings = db.query(SystemSettings).first()
            if sys_settings and sys_settings.borg2_binary_path:
                return sys_settings.borg2_binary_path
        finally:
            db.close()
    except Exception:
        pass
    return DEFAULT_BORG2_BINARY


class Borg2Interface:
    """Interface for interacting with the Borg 2 CLI.

    One global instance is created at module level (`borg2`).
    The binary path is resolved once from system settings at startup.
    """

    _validated = False
    _cached_version: Optional[str] = None
    _cached_system_info: Optional[Dict] = None

    def __init__(self):
        self.borg_cmd = _get_borg2_binary()
        if not Borg2Interface._validated:
            self._validate_installation()
            Borg2Interface._validated = True

    def _validate_installation(self):
        """Validate that the borg2 binary is accessible."""
        try:
            result = subprocess.run(
                [self.borg_cmd, "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                logger.info("Borg2 found", version=result.stdout.strip())
            else:
                logger.warning(
                    "Borg2 binary returned non-zero on --version", cmd=self.borg_cmd
                )
        except (FileNotFoundError, OSError):
            logger.warning(
                "Borg2 not available — v2 repositories will not be usable",
                cmd=self.borg_cmd,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Borg2 --version timed out", cmd=self.borg_cmd)

    # ── Internal execution helpers ─────────────────────────────────────────────

    def _base_env(self, extra: Optional[Dict] = None) -> Dict:
        """Build the base environment variables shared by all borg2 commands."""
        env = os.environ.copy()
        env["BORG_LOCK_WAIT"] = "20"
        env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"
        env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
        env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
        ssh_opts = [
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
        ]
        env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"
        if extra:
            env.update(extra)
        return env

    async def _run(
        self,
        cmd: List[str],
        timeout: int = 3600,
        cwd: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Execute a borg2 command and capture output."""
        logger.info("Executing borg2 command", command=" ".join(cmd), cwd=cwd)
        exec_env = self._base_env(env)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            result = {
                "return_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
                "success": process.returncode == 0,
            }
            if result["success"]:
                logger.info("Borg2 command succeeded", command=" ".join(cmd))
            else:
                logger.error(
                    "Borg2 command failed",
                    command=" ".join(cmd),
                    return_code=process.returncode,
                    stderr=result["stderr"],
                )
            return result
        except asyncio.TimeoutError:
            logger.error(
                "Borg2 command timed out", command=" ".join(cmd), timeout=timeout
            )
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": f"Timed out after {timeout}s",
                "success": False,
            }
        except Exception as e:
            logger.error(
                "Borg2 command execution failed", command=" ".join(cmd), error=str(e)
            )
            return {"return_code": -1, "stdout": "", "stderr": str(e), "success": False}

    async def _run_streaming(
        self,
        cmd: List[str],
        max_lines: int = 1_000_000,
        timeout: int = 3600,
        cwd: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Execute a borg2 command with line-by-line streaming (prevents OOM on large outputs)."""
        logger.info(
            "Executing borg2 command (streaming)",
            command=" ".join(cmd),
            max_lines=max_lines,
        )
        exec_env = self._base_env(env)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
            )
            stdout_lines = []
            line_count = 0
            line_count_exceeded = False
            start_time = asyncio.get_event_loop().time()

            async for line in process.stdout:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    process.kill()
                    await process.wait()
                    return {
                        "return_code": -1,
                        "stdout": "\n".join(stdout_lines),
                        "stderr": f"Timed out after {timeout}s (read {line_count:,} lines)",
                        "success": False,
                        "line_count_exceeded": False,
                        "lines_read": line_count,
                    }
                line_count += 1
                if line_count > max_lines:
                    line_count_exceeded = True
                    process.kill()
                    await process.wait()
                    break
                stdout_lines.append(line.decode("utf-8", errors="replace").rstrip("\n"))

            stderr_data = await process.stderr.read()
            stderr = (
                stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
            )
            if process.returncode is None:
                await process.wait()

            return {
                "return_code": process.returncode,
                "stdout": "\n".join(stdout_lines),
                "stderr": stderr,
                "success": process.returncode == 0 and not line_count_exceeded,
                "line_count_exceeded": line_count_exceeded,
                "lines_read": line_count,
            }
        except Exception as e:
            logger.error(
                "Borg2 streaming command failed", command=" ".join(cmd), error=str(e)
            )
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False,
                "line_count_exceeded": False,
                "lines_read": 0,
            }

    # ── Repository lifecycle ───────────────────────────────────────────────────

    async def rcreate(
        self,
        repository: str,
        encryption: str = "repokey-aes-ocb",
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
    ) -> Dict:
        """Create (initialise) a new Borg 2 repository.

        Replaces `borg init` — borg2 uses `rcreate` for this.
        """
        cmd = [
            self.borg_cmd,
            "-r",
            repository,
            "repo-create",
            "--encryption",
            encryption,
        ]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        env = {"BORG_PASSPHRASE": passphrase} if passphrase else {}
        return await self._run(cmd, timeout=300, env=env or None)

    async def rinfo(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
        strip_components: Optional[int] = None,
    ) -> Dict:
        """Get repository-level metadata only (no archive stats).

        Returns encryption, repository ID/location — but no per-archive stats.
        Prefer info_repo() when you need storage statistics.
        Note: borg2 repo-info does not support --bypass-lock.
        """
        cmd = [self.borg_cmd, "-r", repository, "repo-info", "--json"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, timeout=60, env=exec_env or None)

    async def info_repo(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        timeout: int = 600,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Get info for all archives in a repository (per-archive stats).

        Unlike rinfo (repo-info), this returns an 'archives' array where each entry
        has stats.original_size and stats.nfiles. This is the borg2 equivalent of
        `borg info REPO --json` in borg1.
        """
        cmd = [self.borg_cmd, "-r", repository, "info", "--json"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if bypass_lock:
            cmd.append("--bypass-lock")
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, timeout=timeout, env=exec_env or None)

    async def rdelete(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
    ) -> Dict:
        """Delete an entire repository.

        Replaces `borg delete REPO` — borg2 uses `rdelete` for repo-level deletion.
        """
        cmd = [self.borg_cmd, "-r", repository, "repo-delete", "--force"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        env = {"BORG_PASSPHRASE": passphrase} if passphrase else {}
        return await self._run(cmd, timeout=300, env=env or None)

    # ── Archive listing & info ─────────────────────────────────────────────────

    async def list_archives(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
    ) -> Dict:
        """List archives in a repository (same CLI as borg1 but different binary).
        Note: borg2 repo-list does not support --bypass-lock.
        """
        cmd = [self.borg_cmd, "-r", repository, "repo-list", "--json"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None)

    async def info_archive(
        self,
        repository: str,
        archive: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Get information about a specific archive."""
        cmd = [self.borg_cmd, "-r", repository, "info", "--json", archive]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if bypass_lock:
            cmd.append("--bypass-lock")
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None)

    async def list_archive_contents(
        self,
        repository: str,
        archive: str,
        path: str = "",
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        max_lines: int = 1_000_000,
        bypass_lock: bool = False,
        browse_depth: Optional[int] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """List contents of an archive with streaming to prevent OOM."""
        cmd = [self.borg_cmd, "-r", repository, "list", "--json-lines"]
        if browse_depth is not None:
            cmd.extend(["--depth", str(browse_depth)])
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if bypass_lock:
            cmd.append("--bypass-lock")
        if strip_components:
            cmd.extend(["--strip-components", str(strip_components)])
        cmd.append(archive)
        if path:
            cmd.append(path.strip("/"))
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run_streaming(cmd, max_lines=max_lines, env=exec_env or None)

    # ── Backup operations ──────────────────────────────────────────────────────

    async def create(
        self,
        repository: str,
        source_paths: List[str],
        compression: str = "lz4",
        archive_name: Optional[str] = None,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
    ) -> Dict:
        """Create a new archive (backup)."""
        if not repository:
            return {
                "success": False,
                "error": "Repository is required",
                "stdout": "",
                "stderr": "",
            }
        if not source_paths:
            return {
                "success": False,
                "error": "Source paths are required",
                "stdout": "",
                "stderr": "",
            }

        if not archive_name:
            archive_name = "{hostname}-{now}"
        cmd = [
            self.borg_cmd,
            "-r",
            repository,
            "create",
            "--compression",
            compression,
            "--stats",
            "--json",
            archive_name,
        ]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend(source_paths)
        env = {"BORG_PASSPHRASE": passphrase} if passphrase else {}
        return await self._run(cmd, timeout=settings.backup_timeout, env=env or None)

    async def extract_archive(
        self,
        repository: str,
        archive: str,
        paths: List[str],
        destination: str,
        dry_run: bool = False,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Extract files from an archive."""
        cmd = [self.borg_cmd, "-r", repository, "extract"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if dry_run:
            cmd.append("--dry-run")
        if bypass_lock:
            cmd.append("--bypass-lock")
        cmd.append(archive)
        if paths:
            cmd.extend(paths)
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(
            cmd, timeout=settings.backup_timeout, cwd=destination, env=exec_env or None
        )

    async def delete_archive(
        self,
        repository: str,
        archive: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Delete a single archive.

        Note: in Borg 2, space is NOT freed automatically after delete.
        Call compact() afterwards to reclaim disk space.
        """
        cmd = [self.borg_cmd, "-r", repository, "delete", archive]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None)

    async def prune_archives(
        self,
        repository: str,
        keep_hourly: int = 0,
        keep_daily: int = 7,
        keep_weekly: int = 4,
        keep_monthly: int = 6,
        keep_quarterly: int = 0,
        keep_yearly: int = 1,
        dry_run: bool = False,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
    ) -> Dict:
        """Prune old archives.

        Note: in Borg 2, space is NOT freed automatically after prune.
        Call compact() afterwards to reclaim disk space.
        """
        cmd = [self.borg_cmd, "-r", repository, "prune"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if keep_hourly > 0:
            cmd.extend(["--keep-hourly", str(keep_hourly)])
        if keep_daily > 0:
            cmd.extend(["--keep-daily", str(keep_daily)])
        if keep_weekly > 0:
            cmd.extend(["--keep-weekly", str(keep_weekly)])
        if keep_monthly > 0:
            cmd.extend(["--keep-monthly", str(keep_monthly)])
        if keep_quarterly > 0:
            cmd.extend(["--keep-3monthly", str(keep_quarterly)])
        if keep_yearly > 0:
            cmd.extend(["--keep-yearly", str(keep_yearly)])
        cmd.append("--list")
        if dry_run:
            cmd.append("--dry-run")
        env = {"BORG_PASSPHRASE": passphrase} if passphrase else {}
        return await self._run(cmd, env=env or None)

    async def compact(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Compact repository to free space.

        In Borg 2 this step is REQUIRED after delete/prune — space is not freed
        automatically unlike Borg 1. This is by design to allow faster deletes.
        """
        cmd = [self.borg_cmd, "-r", repository, "compact"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None)

    async def check_repository(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Check repository integrity."""
        cmd = [self.borg_cmd, "-r", repository, "check"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, env=exec_env or None)

    async def break_lock(
        self,
        repository: str,
        passphrase: Optional[str] = None,
        remote_path: Optional[str] = None,
        env: Optional[Dict] = None,
    ) -> Dict:
        """Break a stale lock on a repository."""
        logger.warning("Breaking stale borg2 lock", repository=repository)
        cmd = [self.borg_cmd, "-r", repository, "break-lock"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        exec_env = env.copy() if env else {}
        if passphrase:
            exec_env["BORG_PASSPHRASE"] = passphrase
        return await self._run(cmd, timeout=30, env=exec_env or None)

    # ── Version & system info ──────────────────────────────────────────────────

    def get_version(self) -> str:
        """Return the borg2 version string (synchronous, for startup checks)."""
        try:
            result = subprocess.run(
                [self.borg_cmd, "--version"], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else "Unknown"
        except Exception as e:
            logger.error("Failed to get borg2 version", error=str(e))
            return "Unknown"

    async def get_system_info(self) -> Dict:
        """Get borg2 system information (cached after first call)."""
        try:
            if Borg2Interface._cached_system_info is not None:
                return Borg2Interface._cached_system_info

            version_result = await self._run([self.borg_cmd, "--version"])
            if not version_result["success"]:
                Borg2Interface._cached_system_info = None  # don't cache failures
                return {
                    "success": False,
                    "error": version_result.get("stderr", "binary not found"),
                }

            version = version_result["stdout"].strip()
            Borg2Interface._cached_system_info = {
                "success": True,
                "borg_version": version,
                "binary": self.borg_cmd,
            }
            logger.info("Cached borg2 system info", version=version)
            return Borg2Interface._cached_system_info
        except Exception as e:
            logger.error("Failed to get borg2 system info", error=str(e))
            return {"success": False, "error": str(e)}


# Global instance — mirrors the `borg` singleton in borg.py
borg2 = Borg2Interface()
