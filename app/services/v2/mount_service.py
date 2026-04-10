"""Borg 2 mount helpers for shared mount orchestration."""

from typing import List, Optional

from app.core.borg2 import borg2


class MountV2Service:
    """Build Borg 2 mount and unmount command shapes."""

    def build_mount_command(
        self,
        repository_path: str,
        archive_name: Optional[str] = None,
        mount_point: Optional[str] = None,
        remote_path: Optional[str] = None,
        bypass_lock: bool = False,
    ) -> List[str]:
        cmd = [borg2.borg_cmd]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend(["-r", repository_path, "mount"])
        if mount_point:
            cmd.append(mount_point)
        if archive_name:
            cmd.append(f"aid:{archive_name}")
        cmd.extend(["-o", "allow_other", "-f"])
        if bypass_lock:
            cmd.append("--bypass-lock")
        return cmd

    def build_unmount_command(self, mount_point: str) -> List[str]:
        return [borg2.borg_cmd, "umount", mount_point]


mount_v2_service = MountV2Service()
