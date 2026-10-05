"""Borg 2 backup service.

Owns Borg 2-specific backup execution details so shared services do not need
to know Borg 2 command shapes or local repository layout assumptions.
"""

import json
import os
from typing import List, Optional

from app.core.borg2 import borg2, ensure_borg2_repository_url
from app.database.models import Repository
from app.utils.borg_env import effective_repository_remote_path
from app.utils.borg_flags import parse_borg_flags


class BackupV2Service:
    """Version-specific Borg 2 backup helpers and execution."""

    def validate_local_repository_access(self, repo: Repository) -> None:
        if not repo or repo.path.startswith(("ssh://", "rclone:")):
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
        upload_ratelimit_kib: Optional[int] = None,  # noqa: ARG002 - Borg 1 only
    ) -> List[str]:
        """Borg 2.0.0b22 removed --upload-ratelimit, so a repository's upload
        limit does not reach the command; the Borg 1 options among the custom
        flags are refused (ValueError) before Borg runs."""
        ensure_borg2_repository_url(repository_path, borg2.borg_cmd)
        cmd = [
            borg2.borg_cmd,
            "--progress",
            "--show-rc",
            "--log-json",
            "-r",
            repository_path,
            "create",
            "--stats",
            # The result document names the archive Borg made (its id): a
            # series shares the name, and the post-backup restore check
            # targets that exact archive (#1232).
            "--json",
            "--compression",
            compression,
        ]
        for pattern in exclude_patterns:
            cmd.extend(["--exclude", pattern])
        cmd.extend(parse_borg_flags(custom_flags, "create", 2))
        cmd.append(archive_name)
        return cmd

    def build_archive_info_command(
        self, repository_path: str, archive_name: str
    ) -> List[str]:
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
            remote_path=effective_repository_remote_path(repo),
        )


backup_v2_service = BackupV2Service()
