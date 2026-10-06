"""Borg 2 repository operation helpers."""

from typing import Any, Dict, Optional

from app.core.borg2 import (
    borg2,
    borg2_encryption_flags,
    borg2_remote_path_env,
    borg2_removed_encryption_refusal,
)
from app.database.database import SessionLocal  # noqa: F401
from app.utils.fs import calculate_path_size_bytes
from app.utils.borg_env import effective_repository_remote_path, ssh_key_borg_env


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
        refusal = borg2_removed_encryption_refusal(encryption)
        if refusal:
            return refusal
        needs_custom_ssh_env = bool(ssh_key_id and path.startswith("ssh://"))
        with ssh_key_borg_env(
            path=path, passphrase=passphrase, ssh_key_id=ssh_key_id
        ) as env:
            return (
                await borg2.rcreate(
                    repository=path,
                    encryption=encryption,
                    passphrase=passphrase,
                    remote_path=remote_path,
                )
                if not needs_custom_ssh_env
                else await borg2._run(
                    [
                        borg2.borg_cmd,
                        "-r",
                        path,
                        "repo-create",
                        *borg2_encryption_flags(encryption),
                    ],
                    timeout=init_timeout,
                    env={
                        **({"BORG_PASSPHRASE": passphrase} if passphrase else {}),
                        **env,
                        **borg2_remote_path_env(remote_path),
                    },
                )
            )

    async def verify_repository(
        self,
        path: str,
        passphrase: Optional[str] = None,
        ssh_key_id: Optional[int] = None,
        remote_path: Optional[str] = None,
        timeout: int = 60,
        bypass_lock: bool = False,  # Borg 1 only, see app/core/borg2.py
    ) -> Dict[str, Any]:
        needs_custom_ssh_env = bool(ssh_key_id and path.startswith("ssh://"))
        with ssh_key_borg_env(
            path=path, passphrase=passphrase, ssh_key_id=ssh_key_id
        ) as env:
            return (
                await borg2.info_repo(
                    repository=path,
                    passphrase=passphrase,
                    remote_path=remote_path,
                    bypass_lock=bypass_lock,
                    timeout=timeout,
                )
                if not needs_custom_ssh_env
                else await borg2._run(
                    [borg2.borg_cmd, "-r", path, "info", "--json"],
                    timeout=timeout,
                    env={
                        **({"BORG_PASSPHRASE": passphrase} if passphrase else {}),
                        **env,
                        **borg2_remote_path_env(remote_path),
                    },
                )
            )

    async def export_keyfile(self, repository, output_path: str) -> Dict[str, Any]:
        cmd = [borg2.borg_cmd, "-r", repository.path, "key", "export", output_path]
        env = borg2_remote_path_env(effective_repository_remote_path(repository))
        if repository.passphrase:
            env["BORG_PASSPHRASE"] = repository.passphrase
        return await borg2._run(cmd, timeout=30, env=env or None)

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
            repo_ssh_url = f"ssh://{username}@{repository.host}:{port}/{repository.path.lstrip('/')}"
            return await calculate_path_size_bytes(
                [repo_ssh_url],
                timeout=timeout,
                key_file=temp_key_file,
            )

        return await calculate_path_size_bytes([repository.path], timeout=timeout)


repository_v2_service = RepositoryV2Service()
