"""Borg 2 repository operation helpers."""

import os
import tempfile
from typing import Any, Dict, Optional

from app.core.borg2 import borg2
from app.database.database import SessionLocal
from app.database.models import SSHKey
from app.core.security import decrypt_secret


class RepositoryV2Service:
    def _get_ssh_env(self, path: str, ssh_key_id: Optional[int]) -> tuple[dict, Optional[str]]:
        if not ssh_key_id or not path.startswith("ssh://"):
            return {}, None

        db = SessionLocal()
        try:
            ssh_key = db.query(SSHKey).filter(SSHKey.id == ssh_key_id).first()
            if not ssh_key:
                raise ValueError(f"SSH key {ssh_key_id} not found")
            private_key = decrypt_secret(ssh_key.private_key)
        finally:
            db.close()

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as handle:
            handle.write(private_key)
            temp_path = handle.name
        os.chmod(temp_path, 0o600)

        ssh_opts = [
            "-i", temp_path,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "RequestTTY=no",
            "-o", "PermitLocalCommand=no",
        ]
        return {"BORG_RSH": f"ssh {' '.join(ssh_opts)}"}, temp_path

    async def initialize_repository(
        self,
        path: str,
        encryption: str,
        passphrase: Optional[str] = None,
        ssh_key_id: Optional[int] = None,
        remote_path: Optional[str] = None,
        init_timeout: int = 300,
    ) -> Dict[str, Any]:
        env, temp_key_file = self._get_ssh_env(path, ssh_key_id)
        try:
            return await borg2.rcreate(
                repository=path,
                encryption=encryption,
                passphrase=passphrase,
                remote_path=remote_path,
            ) if not env else await borg2._run(
                [borg2.borg_cmd, "-r", path, "repo-create", "--encryption", encryption] +
                (["--remote-path", remote_path] if remote_path else []),
                timeout=init_timeout,
                env={"BORG_PASSPHRASE": passphrase, **env} if passphrase else env,
            )
        finally:
            if temp_key_file and os.path.exists(temp_key_file):
                os.unlink(temp_key_file)

    async def verify_repository(
        self,
        path: str,
        passphrase: Optional[str] = None,
        ssh_key_id: Optional[int] = None,
        remote_path: Optional[str] = None,
        timeout: int = 60,
        bypass_lock: bool = False,
    ) -> Dict[str, Any]:
        env, temp_key_file = self._get_ssh_env(path, ssh_key_id)
        try:
            return await borg2.info_repo(
                repository=path,
                passphrase=passphrase,
                remote_path=remote_path,
                bypass_lock=bypass_lock,
                timeout=timeout,
            ) if not env else await borg2._run(
                [borg2.borg_cmd, "-r", path, "info", "--json"] +
                (["--remote-path", remote_path] if remote_path else []) +
                (["--bypass-lock"] if bypass_lock else []),
                timeout=timeout,
                env={"BORG_PASSPHRASE": passphrase, **env} if passphrase else env,
            )
        finally:
            if temp_key_file and os.path.exists(temp_key_file):
                os.unlink(temp_key_file)

    async def export_keyfile(self, repository, output_path: str) -> Dict[str, Any]:
        cmd = [borg2.borg_cmd, "-r", repository.path, "key", "export", output_path]
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])
        env = {"BORG_PASSPHRASE": repository.passphrase} if repository.passphrase else None
        return await borg2._run(cmd, timeout=30, env=env)


repository_v2_service = RepositoryV2Service()
