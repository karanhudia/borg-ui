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
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_runtime_app_version, settings

logger = structlog.get_logger()

MANIFEST_FORMAT = 1
# Not "borg.db": the plan excludes every live borg.db by name.
SNAPSHOT_NAME = "borg-ui-db.sqlite"
# The key in use (SECRET_KEY wins over the .secret_key file), not the file.
SECRET_KEY_NAME = "secret-key"
WARNING_PREFIX = "Borg UI settings were not included in this snapshot"


class SelfBackupUnsupported(RuntimeError):
    """Self-backup copies SQLite only; Postgres installs back up their database
    with Postgres tools."""


def read_all_env(read_all: bool) -> dict[str, str]:
    """The flag the image's `borg` wrapper needs, besides the start-up marker,
    to run Borg with read-all access. Only the This machine plan sets it."""
    return {"BORG_UI_READ_ALL": "1"} if read_all else {}


def staging_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "self-backup" / "staging"


def self_backup_paths(data_dir: Path) -> list[str]:
    """What the system plan backs up for Borg UI itself. The staging folder is
    listed even before it exists; it is written before Borg starts."""
    paths = [str(staging_dir(data_dir))]
    for extra in (
        Path(settings.ssh_keys_dir),
        # Keyfile-mode repositories cannot be opened without these.
        Path(data_dir) / "borg_keys",
    ):
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


def _make_staging(staging: Path) -> None:
    """Owner-only: it holds a database copy and a config export."""
    staging.mkdir(parents=True, mode=0o700, exist_ok=True)
    staging.chmod(0o700)


def clear_staging(data_dir: Path) -> None:
    shutil.rmtree(staging_dir(data_dir), ignore_errors=True)


def clear_staging_at_startup() -> None:
    """A run cut short by a crash or restart leaves the database copy behind;
    nothing should find it until the next system run writes a fresh one."""
    clear_staging(Path(settings.data_dir))


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
    for name, collect in _REBUILD_COLLECTORS:
        try:
            if collect(host_root, out):
                written.append(name)
        except OSError as exc:  # shutil.Error is an OSError
            logger.info("Skipped rebuild input", input=name, error=str(exc))
    return written


def _dpkg(host_root: Path, out: Path) -> bool:
    return _copy_if_exists(host_root / "var/lib/dpkg/status", out / "dpkg-status")


def _apk(host_root: Path, out: Path) -> bool:
    return _copy_if_exists(
        host_root / "var/lib/apk/db/installed", out / "apk-installed"
    )


def _pacman(host_root: Path, out: Path) -> bool:
    pacman = host_root / "var/lib/pacman/local"
    if not pacman.is_dir():
        return False
    names = sorted(p.name for p in pacman.iterdir() if p.is_dir())
    (out / "pacman.txt").write_text("\n".join(names) + "\n")
    return True


def _rpm(host_root: Path, out: Path) -> bool:
    if not (shutil.which("rpm") and (host_root / "var/lib/rpm").is_dir()):
        return False
    listing = _run(["rpm", "-qa", "--root", str(host_root)])
    if listing is None:
        return False
    (out / "rpm.txt").write_text(listing)
    return True


def _crontabs(host_root: Path, out: Path) -> bool:
    return _copy_if_exists(host_root / "var/spool/cron", out / "crontabs")


def _systemd(host_root: Path, out: Path) -> bool:
    wants = sorted(
        f"{d.name}/{u.name}"
        for d in (host_root / "etc/systemd/system").glob("*.wants")
        for u in d.iterdir()
    )
    if not wants:
        return False
    (out / "systemd-enabled.txt").write_text("\n".join(wants) + "\n")
    return True


def _containers(_host_root: Path, out: Path) -> bool:
    if not shutil.which("docker"):
        return False
    ids = (_run(["docker", "ps", "-aq"]) or "").split()
    inspected = _run(["docker", "inspect", *ids]) if ids else None
    if inspected is None:
        return False
    (out / "containers.json").write_text(inspected)
    return True


_REBUILD_COLLECTORS = (
    ("dpkg-status", _dpkg),
    ("apk-installed", _apk),
    ("pacman.txt", _pacman),
    ("rpm.txt", _rpm),
    ("crontabs", _crontabs),
    ("systemd-enabled.txt", _systemd),
    ("containers.json", _containers),
)


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

    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise SelfBackupUnsupported("self-backup supports SQLite databases only")
    database = Path(url.database)
    staging = staging_dir(data_dir)
    clear_staging(data_dir)
    _make_staging(staging)
    _snapshot_sqlite(database, staging / SNAPSHOT_NAME)
    key_file = staging / SECRET_KEY_NAME
    key_file.write_text(settings.secret_key)
    key_file.chmod(0o600)
    export = _config_export(db)
    if export is not None:
        (staging / "config.export").write_bytes(export)
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
    # Last, so a host the app user cannot fully read never costs the database.
    collect_rebuild_inputs(host_root, staging)
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
        # The backup was queued with this folder as a source and refuses a
        # missing one; an empty folder lets the machine's files still go in.
        try:
            _make_staging(staging_dir(data_dir))
        except OSError:
            pass
        return f"{WARNING_PREFIX}: {exc}"
    return None
