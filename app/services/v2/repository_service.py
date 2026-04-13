"""Borg 2 repository operation helpers."""

from typing import Any, Dict, Optional

from app.core.borg2 import borg2
from app.database.database import SessionLocal  # Backward-compatible patch target for tests
from app.utils.fs import calculate_path_size_bytes
from app.utils.borg_env import ssh_key_borg_env


class RepositoryV2Service:
    async def initialize_repository(
        self,
        path: str,
        encryption: str,
        passphrase: Optional[str] = None,
        ssh_key_id: Optional[int] = None,
        remote_path: Optional[str] = None,
        init_timeout: int = 300,
    ) -> Dict[str, Any]:
        needs_custom_ssh_env = bool(ssh_key_id and path.startswith("ssh://"))
        with ssh_key_borg_env(path=path, passphrase=passphrase, ssh_key_id=ssh_key_id) as env:
            return await borg2.rcreate(
                repository=path,
                encryption=encryption,
                passphrase=passphrase,
                remote_path=remote_path,
            ) if not needs_custom_ssh_env else await borg2._run(
                [borg2.borg_cmd, "-r", path, "repo-create", "--encryption", encryption] +
                (["--remote-path", remote_path] if remote_path else []),
                timeout=init_timeout,
                env={"BORG_PASSPHRASE": passphrase, **env} if passphrase else env,
            )

    async def verify_repository(
        self,
        path: str,
        passphrase: Optional[str] = None,
        ssh_key_id: Optional[int] = None,
        remote_path: Optional[str] = None,
        timeout: int = 60,
        bypass_lock: bool = False,
    ) -> Dict[str, Any]:
        needs_custom_ssh_env = bool(ssh_key_id and path.startswith("ssh://"))
        with ssh_key_borg_env(path=path, passphrase=passphrase, ssh_key_id=ssh_key_id) as env:
            return await borg2.info_repo(
                repository=path,
                passphrase=passphrase,
                remote_path=remote_path,
                bypass_lock=bypass_lock,
                timeout=timeout,
            ) if not needs_custom_ssh_env else await borg2._run(
                [borg2.borg_cmd, "-r", path, "info", "--json"] +
                (["--remote-path", remote_path] if remote_path else []) +
                (["--bypass-lock"] if bypass_lock else []),
                timeout=timeout,
                env={"BORG_PASSPHRASE": passphrase, **env} if passphrase else env,
            )

    async def export_keyfile(self, repository, output_path: str) -> Dict[str, Any]:
        cmd = [borg2.borg_cmd, "-r", repository.path, "key", "export", output_path]
        if repository.remote_path:
            cmd.extend(["--remote-path", repository.remote_path])
        env = {"BORG_PASSPHRASE": repository.passphrase} if repository.passphrase else None
        return await borg2._run(cmd, timeout=30, env=env)

    async def calculate_total_size_bytes(
        self,
        repository,
        *,
        temp_key_file: Optional[str] = None,
        timeout: int = 30,
    ) -> int:
        """Return on-disk repository size for Borg 2 repositories."""
        if getattr(repository, "host", None):
            port = repository.port or 22
            username = repository.username or "borg"
            repo_ssh_url = (
                f"ssh://{username}@{repository.host}:{port}/{repository.path.lstrip('/')}"
            )
            return await calculate_path_size_bytes(
                [repo_ssh_url],
                timeout=timeout,
                key_file=temp_key_file,
            )

        return await calculate_path_size_bytes([repository.path], timeout=timeout)


repository_v2_service = RepositoryV2Service()
