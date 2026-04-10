"""Borg 2 backup service.

Owns Borg 2-specific backup execution details so shared services do not need
to know Borg 2 command shapes or local repository layout assumptions.
"""

import json
import os
from typing import List, Optional

from app.core.borg2 import borg2
from app.database.models import Repository


class BackupV2Service:
    """Version-specific Borg 2 backup helpers and execution."""

    def validate_local_repository_access(self, repo: Repository) -> None:
        if not repo or repo.path.startswith("ssh://"):
            return

        if not os.path.isdir(repo.path):
            raise ValueError(
                json.dumps(
                    {
                        "key": "backend.errors.repo.repositoryDirNotExist",
                        "params": {"path": repo.path},
                    }
                )
            )

    def build_backup_create_command(
        self,
        repository_path: str,
        archive_name: str,
        compression: str,
        exclude_patterns: List[str],
        custom_flags: List[str],
    ) -> List[str]:
        cmd = [
            borg2.borg_cmd,
            "--show-rc",
            "--log-json",
            "-r",
            repository_path,
            "create",
            "--stats",
            "--compression",
            compression,
        ]
        for pattern in exclude_patterns:
            cmd.extend(["--exclude", pattern])
        cmd.extend(custom_flags)
        cmd.append(archive_name)
        return cmd

    def build_archive_info_command(self, repository_path: str, archive_name: str) -> List[str]:
        return [borg2.borg_cmd, "-r", repository_path, "info", "--json", archive_name]

    def build_repo_list_command(self, repository_path: str) -> List[str]:
        return [borg2.borg_cmd, "-r", repository_path, "repo-list", "--json"]

    def build_repo_info_command(self, repository_path: str) -> List[str]:
        return [borg2.borg_cmd, "-r", repository_path, "info", "--json"]

    async def run_backup(
        self,
        repo: Repository,
        source_paths: List[str],
        archive_name: Optional[str] = None,
    ) -> dict:
        return await borg2.create(
            repository=repo.path,
            source_paths=source_paths,
            compression=repo.compression or "lz4",
            archive_name=archive_name,
            passphrase=repo.passphrase,
            remote_path=repo.remote_path,
        )


backup_v2_service = BackupV2Service()
