"""Legacy Borg 1 repository operation helpers.

This service owns Borg 1 repository probing, initialization, and key export so
shared API handlers can delegate through BorgRouter instead of building Borg 1
commands inline.
"""

import asyncio
import os
from typing import Any, Dict, Optional

import structlog

from app.core.borg import borg
from app.database.database import SessionLocal
from app.database.models import SSHKey, SystemSettings
from app.core.security import decrypt_secret
from app.config import settings

logger = structlog.get_logger()


def _get_standard_ssh_opts(include_key_path: Optional[str] = None) -> list[str]:
    opts = []
    if include_key_path:
        opts.extend(["-i", include_key_path])
    opts.extend(
        [
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-o",
            "RequestTTY=no",
            "-o",
            "PermitLocalCommand=no",
        ]
    )
    return opts


def _setup_borg_env(base_env=None, passphrase: Optional[str] = None, ssh_opts: Optional[list[str]] = None):
    env = base_env.copy() if base_env else os.environ.copy()
    if passphrase:
        env["BORG_PASSPHRASE"] = passphrase
    env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
    env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"
    env["BORG_LOCK_WAIT"] = "180"
    env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"
    if ssh_opts:
        env["BORG_RSH"] = f"ssh {' '.join(ssh_opts)}"
    return env


def _get_operation_timeouts() -> dict:
    timeouts = {
        "info_timeout": settings.borg_info_timeout,
        "init_timeout": settings.borg_init_timeout,
    }
    db = SessionLocal()
    try:
        system_settings = db.query(SystemSettings).first()
        if system_settings:
            if system_settings.info_timeout:
                timeouts["info_timeout"] = system_settings.info_timeout
            if system_settings.init_timeout:
                timeouts["init_timeout"] = system_settings.init_timeout
    finally:
        db.close()
    return timeouts


class RepositoryService:
    async def verify_repository(
        self,
        path: str,
        passphrase: Optional[str] = None,
        ssh_key_id: Optional[int] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        temp_key_file = None
        try:
            env = os.environ.copy()
            if ssh_key_id and path.startswith("ssh://"):
                db = SessionLocal()
                try:
                    ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
                    if not ssh_key:
                        return {"success": False, "error": "SSH key not found"}

                    private_key = decrypt_secret(ssh_key.private_key)
                finally:
                    db.close()

                import tempfile

                with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
                    handle.write(private_key)
                    temp_key_file = handle.name

                os.chmod(temp_key_file, 0o600)
                env = _setup_borg_env(
                    base_env=env,
                    passphrase=passphrase,
                    ssh_opts=_get_standard_ssh_opts(include_key_path=temp_key_file),
                )
            else:
                env = _setup_borg_env(base_env=env, passphrase=passphrase)

            cmd = [borg.borg_cmd, "info"]
            if remote_path:
                cmd.extend(["--remote-path", remote_path])
            if bypass_lock:
                cmd.append("--bypass-lock")
            cmd.extend([path, "--json"])

            result = await borg._execute_command(
                cmd,
                timeout=timeout or _get_operation_timeouts()["info_timeout"],
                env=env,
            )
            if not result["success"]:
                return {
                    "success": False,
                    "error": result.get("stderr") or "Repository verification failed",
                }

            import json

            try:
                return {"success": True, "info": json.loads(result["stdout"])}
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse borg info output", error=str(exc))
                return {"success": False, "error": f"Failed to parse repository info: {exc}"}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Repository verification timed out"}
        except Exception as exc:
            logger.error("Failed to verify repository", path=path, error=str(exc))
            return {"success": False, "error": str(exc)}
        finally:
            if temp_key_file and os.path.exists(temp_key_file):
                os.unlink(temp_key_file)

    async def initialize_repository(
        self,
        path: str,
        encryption: str,
        passphrase: Optional[str] = None,
        ssh_key_id: Optional[int] = None,
        remote_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        temp_key_file = None
        try:
            test_process = await asyncio.create_subprocess_exec(
                borg.borg_cmd,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await test_process.communicate()
            if test_process.returncode != 0:
                raise FileNotFoundError("borg command not found")
            logger.info("Borg version check passed", version=stdout.decode().strip())

            cmd = [borg.borg_cmd, "init", "--encryption", encryption]
            if remote_path:
                cmd.extend(["--remote-path", remote_path])
            cmd.append(path)

            env = _setup_borg_env(passphrase=passphrase)
            if ssh_key_id and path.startswith("ssh://"):
                db = SessionLocal()
                try:
                    ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
                    if not ssh_key:
                        return {"success": False, "error": "SSH key not found"}

                    private_key = decrypt_secret(ssh_key.private_key)
                finally:
                    db.close()

                import tempfile

                with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
                    handle.write(private_key)
                    temp_key_file = handle.name

                os.chmod(temp_key_file, 0o600)
                env = _setup_borg_env(
                    passphrase=passphrase,
                    ssh_opts=_get_standard_ssh_opts(include_key_path=temp_key_file),
                )

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=_get_operation_timeouts()["init_timeout"],
            )
            return {
                "success": process.returncode == 0,
                "return_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
            }
        except (FileNotFoundError, OSError) as exc:
            logger.error("Borg not available", error=str(exc))
            return {"success": False, "error": f"Borg not available on this system: {exc}"}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Repository initialization timed out"}
        except Exception as exc:
            logger.error("Failed to initialize repository", path=path, error=str(exc))
            return {"success": False, "error": str(exc)}
        finally:
            if temp_key_file and os.path.exists(temp_key_file):
                os.unlink(temp_key_file)

    async def export_keyfile(self, repository, output_path: str) -> Dict[str, Any]:
        env = _setup_borg_env(passphrase=repository.passphrase)
        process = await asyncio.create_subprocess_exec(
            borg.borg_cmd,
            "key",
            "export",
            repository.path,
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        return {
            "success": process.returncode == 0,
            "return_code": process.returncode,
            "stdout": stdout.decode() if stdout else "",
            "stderr": stderr.decode() if stderr else "",
        }


repository_service = RepositoryService()
