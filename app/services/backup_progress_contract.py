"""Versioned backup progress contracts for UI-facing API payloads.

This module is the backend source of truth for which backup progress fields
are supported per Borg major version.

Observed contract in the live `borg-ui-web-dev` Borg 2 environment:
- Running `archive_progress` emits: `original_size`, `nfiles`, `path`,
  `hashing_time`, `chunking_time`, `files_stats`, `finished`
- Running `archive_progress` does not emit: `compressed_size`,
  `deduplicated_size`
- `borg2 info --json` for a completed archive exposes `stats.original_size`
  and `stats.nfiles`, but not machine-readable compressed or deduplicated sizes
  in this environment

Because of that, Borg 2 should not advertise `compressed_size` or
`deduplicated_size` in UI progress payloads until the backend has a verified
machine-readable source for them.
"""

from __future__ import annotations

from typing import Optional

from app.database.models import BackupJob, Repository

BACKUP_PROGRESS_FIELDS_BY_VERSION: dict[int, tuple[str, ...]] = {
    1: (
        "original_size",
        "compressed_size",
        "deduplicated_size",
        "nfiles",
        "current_file",
        "progress_percent",
        "backup_speed",
        "total_expected_size",
        "estimated_time_remaining",
    ),
    2: (
        "original_size",
        "nfiles",
        "current_file",
        "progress_percent",
        "backup_speed",
        "total_expected_size",
        "estimated_time_remaining",
    ),
}


def get_backup_progress_fields(repo: Optional[Repository]) -> tuple[str, ...]:
    borg_version = (repo.borg_version or 1) if repo else 1
    return BACKUP_PROGRESS_FIELDS_BY_VERSION.get(
        borg_version, BACKUP_PROGRESS_FIELDS_BY_VERSION[1]
    )


def serialize_backup_progress_details(job: BackupJob, repo: Optional[Repository]) -> dict:
    supported_fields = set(get_backup_progress_fields(repo))
    progress_details = {
        "current_file": job.current_file or "",
        "progress_percent": job.progress_percent or 0,
        "backup_speed": job.backup_speed or 0.0,
        "total_expected_size": job.total_expected_size or 0,
        "estimated_time_remaining": job.estimated_time_remaining or 0,
        "nfiles": job.nfiles or 0,
        "original_size": job.original_size or 0,
    }
    if "compressed_size" in supported_fields:
        progress_details["compressed_size"] = job.compressed_size or 0
    if "deduplicated_size" in supported_fields:
        progress_details["deduplicated_size"] = job.deduplicated_size or 0
    return progress_details
