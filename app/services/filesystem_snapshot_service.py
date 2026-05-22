from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Any

DEFAULT_SNAPSHOT_STAGING_ROOT = "/var/tmp/borg-ui/snapshots"
SNAPSHOT_PROVIDERS = {"btrfs", "zfs"}


@dataclass(frozen=True)
class PreparedFilesystemSnapshot:
    provider: str
    source_path: str
    backup_path: str
    create_commands: list[list[str]]
    cleanup_commands: list[list[str]]
    cleanup_paths: list[str]


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _clean_absolute_path(value: Any, *, field_name: str) -> str:
    path = _clean_string(value)
    if not path.startswith("/"):
        raise ValueError(f"{field_name} snapshot path must be absolute")
    return posixpath.normpath(path)


def normalize_snapshot_config(
    value: Any,
    *,
    source_type: str,
) -> dict[str, Any] | None:
    if value in (None, "", False):
        return None
    if not isinstance(value, dict):
        raise ValueError("snapshot config must be an object")

    provider = _clean_string(value.get("provider")).lower()
    if provider not in SNAPSHOT_PROVIDERS:
        raise ValueError("Unsupported snapshot provider")
    if source_type != "local":
        raise ValueError("Snapshot source locations require local source paths")

    recursive = bool(value.get("recursive", False))
    if provider == "btrfs":
        staging_path = value.get("staging_path") or DEFAULT_SNAPSHOT_STAGING_ROOT
        return {
            "provider": "btrfs",
            "staging_path": _clean_absolute_path(staging_path, field_name="btrfs"),
            "recursive": recursive,
        }

    dataset = _clean_string(value.get("dataset"))
    mountpoint = _clean_absolute_path(value.get("mountpoint"), field_name="zfs")
    if not dataset:
        raise ValueError("zfs snapshot dataset is required")
    return {
        "provider": "zfs",
        "dataset": dataset,
        "mountpoint": mountpoint,
        "recursive": recursive,
    }


def _safe_path_name(path: str) -> str:
    stripped = path.rstrip("/")
    if not stripped:
        return "root"
    basename = posixpath.basename(stripped) or "root"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", basename).strip(".-")
    return safe or "source"


def _btrfs_snapshot_path(
    *, staging_path: str, job_id: int, source_path: str, index: int
) -> tuple[str, str]:
    job_root = posixpath.join(staging_path, f"job-{job_id}")
    snapshot_path = posixpath.join(job_root, f"{index}-{_safe_path_name(source_path)}")
    return job_root, snapshot_path


def _zfs_relative_path(source_path: str, mountpoint: str) -> str:
    normalized_source = posixpath.normpath(source_path)
    normalized_mountpoint = posixpath.normpath(mountpoint)
    if normalized_source == normalized_mountpoint:
        return ""
    prefix = normalized_mountpoint.rstrip("/") + "/"
    if not normalized_source.startswith(prefix):
        raise ValueError(f"{source_path} is not under zfs mountpoint {mountpoint}")
    return normalized_source[len(prefix) :]


def _command_with_recursive(command: list[str], recursive: bool) -> list[str]:
    if not recursive:
        return command
    return [command[0], command[1], "-r", *command[2:]]


def build_filesystem_snapshot_plans(
    source_locations: list[dict[str, Any]],
    *,
    job_id: int,
) -> list[PreparedFilesystemSnapshot]:
    plans: list[PreparedFilesystemSnapshot] = []
    for location_index, location in enumerate(source_locations):
        snapshot = location.get("snapshot")
        if not snapshot:
            continue
        normalized = normalize_snapshot_config(
            snapshot,
            source_type=str(location.get("source_type") or "local"),
        )
        if not normalized:
            continue

        paths = [
            posixpath.normpath(str(path).strip())
            for path in location.get("paths") or []
            if str(path).strip()
        ]
        provider = normalized["provider"]
        if provider == "btrfs":
            for path_index, source_path in enumerate(paths):
                plan_index = len(plans)
                job_root, snapshot_path = _btrfs_snapshot_path(
                    staging_path=normalized["staging_path"],
                    job_id=job_id,
                    source_path=source_path,
                    index=plan_index,
                )
                plans.append(
                    PreparedFilesystemSnapshot(
                        provider="btrfs",
                        source_path=source_path,
                        backup_path=snapshot_path,
                        create_commands=[
                            [
                                "btrfs",
                                "subvolume",
                                "snapshot",
                                "-r",
                                source_path,
                                snapshot_path,
                            ]
                        ],
                        cleanup_commands=[
                            ["btrfs", "subvolume", "delete", snapshot_path]
                        ],
                        cleanup_paths=[job_root],
                    )
                )
            continue

        snapshot_name = f"borg-ui-{job_id}-{location_index}"
        snapshot_ref = f"{normalized['dataset']}@{snapshot_name}"
        create_command = _command_with_recursive(
            ["zfs", "snapshot", snapshot_ref],
            normalized["recursive"],
        )
        cleanup_command = _command_with_recursive(
            ["zfs", "destroy", snapshot_ref],
            normalized["recursive"],
        )
        for path_index, source_path in enumerate(paths):
            relative_path = _zfs_relative_path(source_path, normalized["mountpoint"])
            backup_path = posixpath.join(
                normalized["mountpoint"],
                ".zfs",
                "snapshot",
                snapshot_name,
                relative_path,
            )
            plans.append(
                PreparedFilesystemSnapshot(
                    provider="zfs",
                    source_path=source_path,
                    backup_path=backup_path,
                    create_commands=[create_command] if path_index == 0 else [],
                    cleanup_commands=[cleanup_command] if path_index == 0 else [],
                    cleanup_paths=[],
                )
            )

    return plans
