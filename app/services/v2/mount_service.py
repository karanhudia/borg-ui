"""Borg 2 mount helpers for shared mount orchestration."""

from typing import List, Optional

from app.core.borg2 import borg2, ensure_borg2_repository_url


class MountV2Service:
    """Build Borg 2 mount and unmount command shapes."""

    def build_mount_command(
        self,
        repository_path: str,
        archive_name: Optional[str] = None,
        mount_point: Optional[str] = None,
        remote_path: Optional[str] = None,  # noqa: ARG002 - BORG_REMOTE_PATH, see app/core/borg2.py
        bypass_lock: bool = False,  # noqa: ARG002 - Borg 1 only, see app/core/borg2.py
    ) -> List[str]:
        ensure_borg2_repository_url(repository_path)
        cmd = [borg2.borg_cmd, "-r", repository_path, "mount"]
        if archive_name:
            # Borg 2 mounts a single archive by filtering the repository target
            # down to exactly one archive; a trailing positional argument would
            # be interpreted as a path filter instead.
            cmd.extend(["-a", archive_name])
        if mount_point:
            cmd.append(mount_point)
        cmd.extend(["-o", "allow_other", "-f"])
        return cmd

    def build_unmount_command(self, mount_point: str) -> List[str]:
        return [borg2.borg_cmd, "umount", mount_point]


mount_v2_service = MountV2Service()
