"""Helpers for Borg 2 archive browsing behavior."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.database.models import Repository, SystemSettings


def is_fast_browse_enabled(db: Session) -> bool:
    settings = db.query(SystemSettings).first()
    return bool(settings and getattr(settings, "borg2_fast_browse_beta_enabled", False))


def get_archive_root_depth(repo: Repository) -> int:
    if not repo.source_directories:
        return 1
    try:
        source_directories = json.loads(repo.source_directories)
    except (json.JSONDecodeError, TypeError):
        return 1

    depths = []
    for source_dir in source_directories:
        if not isinstance(source_dir, str):
            continue
        parts = [part for part in source_dir.strip("/").split("/") if part]
        if parts:
            depths.append(len(parts))

    return min(depths) if depths else 1


def get_browse_depth(repo: Repository, path: str) -> int:
    normalized_path = path.strip("/")
    path_depth = len([part for part in normalized_path.split("/") if part])
    return get_archive_root_depth(repo) + path_depth
