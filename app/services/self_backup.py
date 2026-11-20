"""Borg UI's own state, staged for the "This machine" plan to back up.

Before each run of the system plan, a consistent copy of the database, a
borgmatic-style config export and a manifest are written to a staging folder.
The archive takes that folder, the secret key and the SSH keys; the live
database files are never backed up (they are excluded by name).
"""

import json
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_runtime_app_version, resolve_secret_key_file, settings

logger = structlog.get_logger()

MANIFEST_FORMAT = 1
WARNING_PREFIX = "Borg UI settings were not included in this snapshot"


class SelfBackupUnsupported(RuntimeError):
    """Self-backup copies SQLite only; Postgres installs back up their database
    with Postgres tools."""


def staging_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "self-backup" / "staging"


def self_backup_paths(data_dir: Path) -> list[str]:
    """What the system plan backs up for Borg UI itself. The staging folder is
    listed even before it exists; it is written before Borg starts."""
    paths = [str(staging_dir(data_dir))]
    for extra in (resolve_secret_key_file(str(data_dir)), Path(settings.ssh_keys_dir)):
        if extra.exists():
            paths.append(str(extra))
    return paths


def with_self_backup_paths(
    source_directories: list[str],
    source_locations: list[dict[str, Any]],
    extra: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    directories = [
        *source_directories,
        *[p for p in extra if p not in source_directories],
    ]
    locations = [dict(location) for location in source_locations]
    local = next((loc for loc in locations if loc.get("source_type") == "local"), None)
    if local is None:
        locations.append({"source_type": "local", "paths": list(extra)})
    else:
        paths = list(local.get("paths") or [])
        local["paths"] = [*paths, *[p for p in extra if p not in paths]]
    return directories, locations


def clear_staging(data_dir: Path) -> None:
    shutil.rmtree(staging_dir(data_dir), ignore_errors=True)


def _copy_if_exists(src: Path, dest: Path) -> bool:
    if src.is_dir():
        shutil.copytree(src, dest, symlinks=True)
        return True
    if src.is_file():
        shutil.copy2(src, dest)
        return True
    return False


def _run(args: list[str]) -> Optional[str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def collect_rebuild_inputs(host_root: Optional[Path], staging: Path) -> list[str]:
    """What a later rebuild needs to put the host back: package lists, cron
    tables, enabled services and container definitions. Whatever is missing
    is skipped."""
    if host_root is None:
        return []
    out = staging / "rebuild"
    out.mkdir(parents=True, exist_ok=True)
    written = []
    if _copy_if_exists(host_root / "var/lib/dpkg/status", out / "dpkg-status"):
        written.append("dpkg-status")
    if _copy_if_exists(host_root / "var/lib/apk/db/installed", out / "apk-installed"):
        written.append("apk-installed")
    pacman = host_root / "var/lib/pacman/local"
    if pacman.is_dir():
        (out / "pacman.txt").write_text(
            "\n".join(sorted(p.name for p in pacman.iterdir() if p.is_dir())) + "\n"
        )
        written.append("pacman.txt")
    if shutil.which("rpm") and (host_root / "var/lib/rpm").is_dir():
        listing = _run(["rpm", "-qa", "--root", str(host_root)])
        if listing is not None:
            (out / "rpm.txt").write_text(listing)
            written.append("rpm.txt")
    if _copy_if_exists(host_root / "var/spool/cron", out / "crontabs"):
        written.append("crontabs")
    wants = sorted(
        f"{d.name}/{u.name}"
        for d in (host_root / "etc/systemd/system").glob("*.wants")
        for u in d.iterdir()
    )
    if wants:
        (out / "systemd-enabled.txt").write_text("\n".join(wants) + "\n")
        written.append("systemd-enabled.txt")
    if shutil.which("docker"):
        ids = (_run(["docker", "ps", "-aq"]) or "").split()
        inspected = _run(["docker", "inspect", *ids]) if ids else None
        if inspected is not None:
            (out / "containers.json").write_text(inspected)
            written.append("containers.json")
    return written


def _config_export(db: Session) -> Optional[bytes]:
    from app.services.borgmatic_service import (
        BorgmaticExportService,
        build_borgmatic_export_artifact,
    )

    configs = BorgmaticExportService(db).export_all_repositories(
        repository_ids=None, include_schedules=True
    )
    if not configs:
        return None
    return build_borgmatic_export_artifact(configs).content


def write_staging(
    db: Session,
    data_dir: Path,
    *,
    app_version: str,
    alembic_revision: str,
    hostname: str,
    host_root: Optional[Path] = None,
) -> list[str]:
    """Fill the staging folder from scratch. Returns the paths Borg backs up."""
    from app.database.db_upgrade import _snapshot_sqlite

    if not settings.database_url.startswith("sqlite"):
        raise SelfBackupUnsupported("self-backup supports SQLite databases only")
    database = Path(settings.database_url.replace("sqlite:///", "", 1))
    staging = staging_dir(data_dir)
    clear_staging(data_dir)
    staging.mkdir(parents=True)
    _snapshot_sqlite(database, staging / "borg.db")
    export = _config_export(db)
    if export is not None:
        (staging / "config.export").write_bytes(export)
    collect_rebuild_inputs(host_root, staging)
    (staging / "manifest.json").write_text(
        json.dumps(
            {
                "format": MANIFEST_FORMAT,
                "borg_ui_version": app_version,
                "alembic_revision": alembic_revision,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "hostname": hostname,
            },
            indent=2,
        )
    )
    return self_backup_paths(data_dir)


def _alembic_revision(db: Session) -> str:
    try:
        return (
            db.execute(text("select version_num from alembic_version")).scalar() or ""
        )
    except Exception:
        db.rollback()
        return ""


def run_self_backup_step(db: Session) -> Optional[str]:
    """The system plan's built-in pre-backup step. Never fails the run: a
    snapshot without Borg UI's settings still protects the machine's files,
    so a problem here is a warning."""
    from app.services.this_machine import _host_root

    data_dir = Path(settings.data_dir)
    try:
        write_staging(
            db,
            data_dir,
            app_version=get_runtime_app_version(),
            alembic_revision=_alembic_revision(db),
            hostname=socket.gethostname(),
            host_root=_host_root(),
        )
    except Exception as exc:
        logger.warning("Self-backup staging failed", error=str(exc))
        clear_staging(data_dir)
        return f"{WARNING_PREFIX}: {exc}"
    return None
