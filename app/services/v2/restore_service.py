"""Borg 2 restore service.

Owns Borg 2-specific restore and archive-browsing semantics so shared restore
and browse code does not hardcode Borg 1 archive addressing.
"""

from typing import List, Optional

from app.core.borg2 import borg2
from app.database.models import Repository


class RestoreV2Service:
    def build_extract_command(
        self,
        repository_path: str,
        archive_name: str,
        paths: Optional[List[str]] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
    ) -> List[str]:
        cmd = [borg2.borg_cmd, "-r", repository_path, "extract", "--log-json", archive_name]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if bypass_lock:
            cmd.append("--bypass-lock")
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
            "remote_path": repo.remote_path,
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
        env: Optional[dict] = None,
    ) -> dict:
        kwargs = {
            "repository": repo.path,
            "archive": archive,
            "path": path,
            "passphrase": repo.passphrase,
            "remote_path": repo.remote_path,
            "max_lines": max_lines,
            "bypass_lock": repo.bypass_lock,
        }
        if env is not None:
            kwargs["env"] = env
        return await borg2.list_archive_contents(**kwargs)


restore_v2_service = RestoreV2Service()
