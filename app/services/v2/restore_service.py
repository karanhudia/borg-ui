"""Borg 2 restore service.

Owns Borg 2-specific restore and archive-browsing semantics so shared restore
and browse code does not hardcode Borg 1 archive addressing.
"""

from typing import List, Optional

from app.core.borg2 import (
    borg2,
    borg2_extract_existing_files_flags,
    borg2_restore_target_refusal,
    ensure_borg2_repository_url,
)
from app.core.borg_errors import RestoreRefused
from app.database.models import Repository
from app.utils.borg_env import effective_repository_remote_path


class RestoreV2Service:
    def build_extract_command(
        self,
        repository_path: str,
        archive_name: str,
        paths: Optional[List[str]] = None,
        remote_path: Optional[str] = None,  # noqa: ARG002 - BORG_REMOTE_PATH, see app/core/borg2.py
        bypass_lock: bool = False,  # noqa: ARG002 - Borg 1 only, see app/core/borg2.py
        strip_components: Optional[int] = None,
        destination: Optional[str] = None,
        existing_files: Optional[str] = "refuse",
    ) -> List[str]:
        """`destination` is the directory the command will run in. Where it
        holds anything the restore is refused (RestoreRefused, see
        `borg2_restore_target_refusal`) unless `existing_files` is
        "continue", which writes into what is there. A caller that extracts
        into a directory of its own making leaves both out."""
        ensure_borg2_repository_url(repository_path)
        refusal = borg2_restore_target_refusal(destination, existing_files)
        if refusal:
            raise RestoreRefused(refusal)
        cmd = [
            borg2.borg_cmd,
            "-r",
            repository_path,
            "extract",
            "--log-json",
            "--umask",
            "0022",
        ]
        cmd.extend(borg2_extract_existing_files_flags(existing_files))
        if strip_components:
            cmd.extend(["--strip-components", str(strip_components)])
        cmd.append(archive_name)
        if paths:
            cmd.extend(paths)
        return cmd

    async def preview_restore(
        self,
        repo: Repository,
        archive: str,
        paths: List[str],
        destination: str,
        env: Optional[dict] = None,
    ) -> dict:
        kwargs = {
            "repository": repo.path,
            "archive": archive,
            "paths": paths,
            "destination": destination,
            "dry_run": True,
            "passphrase": repo.passphrase,
            "remote_path": effective_repository_remote_path(repo),
            "bypass_lock": repo.bypass_lock,
        }
        if env is not None:
            kwargs["env"] = env
        return await borg2.extract_archive(**kwargs)

    async def list_archive_contents(
        self,
        repo: Repository,
        archive: str,
        path: str = "",
        max_lines: int = 1_000_000,
        browse_depth: Optional[int] = None,
        env: Optional[dict] = None,
    ) -> dict:
        kwargs = {
            "repository": repo.path,
            "archive": archive,
            "path": path,
            "passphrase": repo.passphrase,
            "remote_path": effective_repository_remote_path(repo),
            "max_lines": max_lines,
            "bypass_lock": repo.bypass_lock,
        }
        if browse_depth is not None:
            kwargs["browse_depth"] = browse_depth
        if env is not None:
            kwargs["env"] = env
        return await borg2.list_archive_contents(**kwargs)


restore_v2_service = RestoreV2Service()
