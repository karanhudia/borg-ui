"""BorgRouter — version-aware routing for repository operations.

This is the single place in the backend where borg_version is checked and
operations are dispatched to the correct implementation.

v1 repos  →  app/core/borg.py  + existing v1 services
v2 repos  →  app/core/borg2.py + app/services/v2/

Never add borg_version checks directly inside v1 service code.
Use BorgRouter instead so the routing stays in one place.
"""

import structlog
from sqlalchemy.orm import Session
from typing import List, Optional

logger = structlog.get_logger()


class BorgRouter:
    def __init__(self, repo):
        self.repo = repo
        self.is_v2 = (repo.borg_version or 1) == 2

    def validate_local_repository_access(self) -> None:
        """Fail fast for clearly invalid local repository paths.

        For Borg 1, this preserves the historical `<repo>/config` file check.
        For Borg 2, avoid Borg 1 layout assumptions and only assert that the
        repository path exists as a directory.
        """
        if self.is_v2:
            from app.services.v2.backup_service import backup_v2_service

            backup_v2_service.validate_local_repository_access(self.repo)
            return

        import json
        import os

        if not self.repo or self.repo.path.startswith("ssh://"):
            return

        if not os.path.isdir(self.repo.path):
            raise ValueError(
                json.dumps(
                    {
                        "key": "backend.errors.repo.repositoryDirNotExist",
                        "params": {"path": self.repo.path},
                    }
                )
            )

        if self.is_v2:
            return

        config_path = os.path.join(self.repo.path, "config")
        if not os.path.isfile(config_path):
            raise ValueError(
                json.dumps(
                    {
                        "key": "backend.errors.repo.notValidBorgRepository",
                        "params": {"path": self.repo.path},
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
        """Build the version-aware archive creation command."""
        if self.is_v2:
            from app.services.v2.backup_service import backup_v2_service

            return backup_v2_service.build_backup_create_command(
                repository_path=repository_path,
                archive_name=archive_name,
                compression=compression,
                exclude_patterns=exclude_patterns,
                custom_flags=custom_flags,
            )

        cmd = [
            "borg",
            "create",
            "--progress",
            "--stats",
            "--show-rc",
            "--log-json",
            "--compression",
            compression,
        ]
        for pattern in exclude_patterns:
            cmd.extend(["--exclude", pattern])
        cmd.extend(custom_flags)
        cmd.append(f"{repository_path}::{archive_name}")
        return cmd

    def build_archive_info_command(
        self, repository_path: str, archive_name: str
    ) -> List[str]:
        if self.is_v2:
            from app.services.v2.backup_service import backup_v2_service

            return backup_v2_service.build_archive_info_command(
                repository_path, archive_name
            )
        return ["borg", "info", "--json", f"{repository_path}::{archive_name}"]

    def build_repo_list_command(self, repository_path: str) -> List[str]:
        if self.is_v2:
            from app.services.v2.backup_service import backup_v2_service

            return backup_v2_service.build_repo_list_command(repository_path)
        return ["borg", "list", "--json", repository_path]

    def build_repo_info_command(self, repository_path: str) -> List[str]:
        if self.is_v2:
            from app.services.v2.backup_service import backup_v2_service

            return backup_v2_service.build_repo_info_command(repository_path)
        return ["borg", "info", "--json", repository_path]

    def build_restore_extract_command(
        self,
        repository_path: str,
        archive_name: str,
        paths: List[str],
        remote_path: str = None,
        bypass_lock: bool = False,
        strip_components: Optional[int] = None,
    ) -> List[str]:
        if self.is_v2:
            from app.services.v2.restore_service import restore_v2_service

            return restore_v2_service.build_extract_command(
                repository_path=repository_path,
                archive_name=archive_name,
                paths=paths,
                remote_path=remote_path,
                bypass_lock=bypass_lock,
                strip_components=strip_components,
            )

        cmd = ["borg", "extract", "--progress", "--log-json"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        if bypass_lock:
            cmd.append("--bypass-lock")
        if strip_components:
            cmd.extend(["--strip-components", str(strip_components)])
        cmd.append(f"{repository_path}::{archive_name}")
        if paths:
            cmd.extend(paths)
        return cmd

    def build_break_lock_command(
        self, repository_path: str, remote_path: str = None
    ) -> List[str]:
        """Build the version-aware break-lock command."""
        if self.is_v2:
            from app.core.borg2 import borg2

            cmd = [borg2.borg_cmd, "-r", repository_path, "break-lock"]
            if remote_path:
                cmd.extend(["--remote-path", remote_path])
            return cmd

        cmd = ["borg", "break-lock"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.append(repository_path)
        return cmd

    def build_mount_command(
        self,
        repository_path: str,
        archive_name: str = None,
        mount_point: str = None,
        remote_path: str = None,
        bypass_lock: bool = False,
    ) -> List[str]:
        """Build the version-aware archive mount command."""
        if self.is_v2:
            from app.services.v2.mount_service import mount_v2_service

            return mount_v2_service.build_mount_command(
                repository_path=repository_path,
                archive_name=archive_name,
                mount_point=mount_point,
                remote_path=remote_path,
                bypass_lock=bypass_lock,
            )

        cmd = ["borg", "mount"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.append(
            f"{repository_path}::{archive_name}" if archive_name else repository_path
        )
        if mount_point:
            cmd.append(mount_point)
        cmd.extend(["-o", "allow_other", "-f"])
        if bypass_lock:
            cmd.append("--bypass-lock")
        return cmd

    def build_unmount_command(self, mount_point: str) -> List[str]:
        """Build the version-aware archive unmount command."""
        if self.is_v2:
            from app.core.borg2 import borg2

            return [borg2.borg_cmd, "umount", mount_point]
        return ["borg", "umount", mount_point]

    async def break_lock(self, env: dict = None) -> dict:
        """Break a repository lock via the version-appropriate implementation."""
        if self.is_v2:
            from app.core.borg2 import borg2

            kwargs = {
                "passphrase": self.repo.passphrase,
                "remote_path": self.repo.remote_path,
            }
            if env is not None:
                kwargs["env"] = env
            return await borg2.break_lock(self.repo.path, **kwargs)

        from app.core.borg import borg

        kwargs = {
            "remote_path": self.repo.remote_path,
            "passphrase": self.repo.passphrase,
        }
        if env is not None:
            kwargs["env"] = env
        return await borg.break_lock(self.repo.path, **kwargs)

    async def preview_restore(
        self, archive: str, paths: List[str], destination: str, env: dict = None
    ) -> dict:
        if self.is_v2:
            from app.services.v2.restore_service import restore_v2_service

            kwargs = {
                "repo": self.repo,
                "archive": archive,
                "paths": paths,
                "destination": destination,
            }
            if env is not None:
                kwargs["env"] = env
            return await restore_v2_service.preview_restore(**kwargs)

        from app.core.borg import borg

        kwargs = {
            "dry_run": True,
            "remote_path": self.repo.remote_path,
            "passphrase": self.repo.passphrase,
            "bypass_lock": self.repo.bypass_lock,
        }
        if env is not None:
            kwargs["env"] = env
        return await borg.extract_archive(
            self.repo.path, archive, paths, destination, **kwargs
        )

    async def list_archive_contents(
        self,
        archive: str,
        path: str = "",
        max_lines: int = 1_000_000,
        browse_depth: Optional[int] = None,
        env: dict = None,
    ) -> dict:
        if self.is_v2:
            from app.services.v2.restore_service import restore_v2_service

            kwargs = {
                "repo": self.repo,
                "archive": archive,
                "path": path,
                "max_lines": max_lines,
            }
            if browse_depth is not None:
                kwargs["browse_depth"] = browse_depth
            if env is not None:
                kwargs["env"] = env
            return await restore_v2_service.list_archive_contents(**kwargs)

        from app.core.borg import borg

        return await borg.list_archive_contents(
            self.repo.path,
            archive,
            path,
            remote_path=self.repo.remote_path,
            passphrase=self.repo.passphrase,
            max_lines=max_lines,
            bypass_lock=self.repo.bypass_lock,
            env=env,
        )

    async def update_stats(self, db: Session) -> bool:
        """Refresh archive count and size stats for this repository.

        v2: computes on-disk size via du and persists to repository.total_size.
        v1: delegates to the existing update_repository_stats helper.
        """
        from app.api.repositories import update_repository_stats

        return await update_repository_stats(self.repo, db)

    async def calculate_total_size_bytes(
        self,
        *,
        env: dict = None,
        info_timeout: int = 60,
        use_bypass_lock: bool = False,
        temp_key_file: str = None,
    ) -> int:
        """Return repository total size in bytes using the versioned implementation."""
        if self.is_v2:
            from app.services.v2.repository_service import repository_v2_service

            return await repository_v2_service.calculate_total_size_bytes(
                self.repo,
                temp_key_file=temp_key_file,
                timeout=30,
            )

        import json
        from app.core.borg import borg

        cmd = self.build_repo_info_command(self.repo.path)
        if self.repo.remote_path:
            cmd.extend(["--remote-path", self.repo.remote_path])
        if use_bypass_lock:
            cmd.append("--bypass-lock")

        info_result = await borg._execute_command(cmd, timeout=info_timeout, env=env)
        if not info_result["success"]:
            return 0

        info_data = json.loads(info_result["stdout"])
        cache = info_data.get("cache", {}).get("stats", {})
        return cache.get("unique_csize", 0) or 0

    async def check(self, job_id: int) -> None:
        """Run a repository integrity check.

        v2: delegates to the Borg 2 check service.
        v1: delegates to the existing check service.
        """
        if self.is_v2:
            from app.services.v2.check_service import check_v2_service

            await check_v2_service.execute_check(job_id, self.repo.id)
        else:
            from app.services.check_service import check_service

            await check_service.execute_check(job_id, self.repo.id)

    async def compact(self, job_id: int) -> None:
        """Run repository compaction through the version-aware service layer."""
        if self.is_v2:
            from app.services.v2.compact_service import compact_v2_service

            await compact_v2_service.execute_compact(job_id, self.repo.id)
        else:
            from app.services.compact_service import compact_service

            await compact_service.execute_compact(job_id, self.repo.id)

    async def prune(
        self,
        job_id: int,
        keep_hourly: int,
        keep_daily: int,
        keep_weekly: int,
        keep_monthly: int,
        keep_quarterly: int,
        keep_yearly: int,
        dry_run: bool = False,
    ) -> None:
        """Run repository pruning through the version-aware service layer."""
        if self.is_v2:
            from app.services.v2.prune_service import prune_v2_service

            await prune_v2_service.execute_prune(
                job_id=job_id,
                repository_id=self.repo.id,
                keep_hourly=keep_hourly,
                keep_daily=keep_daily,
                keep_weekly=keep_weekly,
                keep_monthly=keep_monthly,
                keep_quarterly=keep_quarterly,
                keep_yearly=keep_yearly,
                dry_run=dry_run,
            )
        else:
            from app.services.prune_service import prune_service

            await prune_service.execute_prune(
                job_id=job_id,
                repository_id=self.repo.id,
                keep_hourly=keep_hourly,
                keep_daily=keep_daily,
                keep_weekly=keep_weekly,
                keep_monthly=keep_monthly,
                keep_quarterly=keep_quarterly,
                keep_yearly=keep_yearly,
                dry_run=dry_run,
            )

    async def delete_archive(self, job_id: int, archive_name: str) -> None:
        """Delete an archive through the version-aware service layer."""
        if self.is_v2:
            from app.services.v2.delete_archive_service import delete_archive_v2_service

            await delete_archive_v2_service.execute_delete(
                job_id, self.repo.id, archive_name
            )
        else:
            from app.services.delete_archive_service import delete_archive_service

            await delete_archive_service.execute_delete(
                job_id, self.repo.id, archive_name
            )

    async def list_archives(self, env: dict = None) -> list:
        """Return the list of archives for this repository.

        Used as a version-aware guard before repository deletion.
        v2: calls borg2 list and parses the JSON archives array.
        v1: calls borg list and returns the archives list.
        """
        import json

        def _parse_archives_payload(payload) -> list:
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                archives = payload.get("archives")
                return archives if isinstance(archives, list) else []
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                except Exception:
                    return []
                return _parse_archives_payload(parsed)
            return []

        if self.is_v2:
            from app.core.borg2 import borg2

            result = await borg2.list_archives(
                self.repo.path,
                passphrase=self.repo.passphrase,
                remote_path=self.repo.remote_path,
                bypass_lock=self.repo.bypass_lock,
                env=env,
            )
            if not result["success"]:
                return []
            return _parse_archives_payload(result.get("stdout", "{}"))
        else:
            from app.core.borg import borg

            result = await borg.list_archives(
                self.repo.path,
                remote_path=self.repo.remote_path,
                passphrase=self.repo.passphrase,
                bypass_lock=self.repo.bypass_lock,
                env=env,
            )
            if not result["success"]:
                return []
            return _parse_archives_payload(result.get("stdout", ""))

    async def verify_repository(
        self, ssh_key_id: int = None, timeout: int = 60
    ) -> dict:
        """Verify repository accessibility through the version-aware service layer."""
        if self.is_v2:
            from app.services.v2.repository_service import repository_v2_service

            return await repository_v2_service.verify_repository(
                path=self.repo.path,
                passphrase=self.repo.passphrase,
                ssh_key_id=ssh_key_id,
                remote_path=self.repo.remote_path,
                timeout=timeout,
                bypass_lock=getattr(self.repo, "bypass_lock", False),
            )

        from app.services.repository_service import repository_service

        return await repository_service.verify_repository(
            path=self.repo.path,
            passphrase=self.repo.passphrase,
            ssh_key_id=ssh_key_id,
            remote_path=self.repo.remote_path,
            timeout=timeout,
            bypass_lock=getattr(self.repo, "bypass_lock", False),
        )

    async def initialize_repository(
        self, ssh_key_id: int = None, init_timeout: int = 300
    ) -> dict:
        """Initialize repository through the version-aware service layer."""
        if self.is_v2:
            from app.services.v2.repository_service import repository_v2_service

            return await repository_v2_service.initialize_repository(
                path=self.repo.path,
                encryption=self.repo.encryption,
                passphrase=self.repo.passphrase,
                ssh_key_id=ssh_key_id,
                remote_path=self.repo.remote_path,
                init_timeout=init_timeout,
            )

        from app.services.repository_service import repository_service

        return await repository_service.initialize_repository(
            path=self.repo.path,
            encryption=self.repo.encryption,
            passphrase=self.repo.passphrase,
            ssh_key_id=ssh_key_id,
            remote_path=self.repo.remote_path,
        )

    async def export_keyfile(self, output_path: str) -> dict:
        """Export the repository keyfile through the version-aware service layer."""
        if self.is_v2:
            from app.services.v2.repository_service import repository_v2_service

            return await repository_v2_service.export_keyfile(
                repository=self.repo,
                output_path=output_path,
            )

        from app.services.repository_service import repository_service

        return await repository_service.export_keyfile(
            repository=self.repo,
            output_path=output_path,
        )
