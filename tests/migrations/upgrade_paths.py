"""Build a database at a release, upgrade it with the current code, check it.

A release's database is built by that release's own code, taken from its git
tag, in a subprocess (see build_release.py). The upgrade runs the current
entry point, `python -m app.database.db_upgrade`, also in a subprocess, the
way a container starts. The checks then read the result with the current
models.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import MetaData, and_, create_engine, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database.database import Base
import app.database.models  # noqa: F401  (registers every table on Base)

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = Path(__file__).with_name("build_release.py")

# Every release from this one on is tested; earlier ones only through the
# last release of each line before Alembic, which is what installs upgrading
# from that far back are running.
FIRST_RELEASE = (2, 3, 0)
LEGACY_RELEASES = ("v2.0.9", "v2.1.0", "v2.2.6")

# Set in CI, where a missing tag means a broken checkout, not a fork.
REQUIRE_TAGS_ENV = "BORG_TEST_REQUIRE_RELEASE_TAGS"
POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")

# Rows the upgrade moves to another table on purpose: the collapse revision
# (d0e1f2a3b4c5) folds each legacy job table into `operations`, keeping the
# old id in params["legacy_id"].
MOVED_TO_OPERATIONS = {
    "backup_jobs": "backup",
    "restore_jobs": "restore",
    "check_jobs": "check",
    "restore_check_jobs": "restore_check",
    "compact_jobs": "compact",
    "prune_jobs": "prune",
    "delete_archive_jobs": "delete_archive",
    "repository_wipe_jobs": "wipe",
    "rclone_sync_jobs": "rclone_sync",
    "package_install_jobs": "package_install",
}
# The retry lineage between legacy backup jobs moves with them.
MOVED_TABLES = {"backup_job_retry_lineage": "operation_backup_retry_lineage"}

# Values the upgrade rewrites on purpose because the seed's generated value
# is not one the application accepts.
REWRITTEN_VALUES = {
    # Legacy migration 110, rerun by the catch-up, maps anything but
    # 'server' or 'agent' to one of them.
    ("repositories", "executor_type"),
}


def _release_tags() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "tag", "--list", "v*"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return []
    return out


def _version(tag: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)  # no pre-releases
    return tuple(int(p) for p in match.groups()) if match else None


def releases() -> list[str]:
    """The releases to upgrade from, oldest first; empty without tags."""
    tags = _release_tags()
    current = sorted(
        (t for t in tags if (_version(t) or (0, 0, 0)) >= FIRST_RELEASE),
        key=_version,
    )
    if not current:
        return []
    return [t for t in LEGACY_RELEASES if t in tags] + current


def releases_before(revision: str) -> list[str]:
    """The releases that do not ship `revision`, so upgrading applies it."""
    found = []
    for tag in releases():
        files = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "ls-tree",
                "--name-only",
                tag,
                "app/database/alembic/versions/",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        if not any(Path(f).name.startswith(f"{revision}_") for f in files):
            found.append(tag)
    return found


def missing_releases() -> list[str]:
    tags = set(_release_tags())
    return [t for t in LEGACY_RELEASES if t not in tags]


def tags_required() -> bool:
    return os.getenv(REQUIRE_TAGS_ENV, "") not in ("", "0", "false")


def extract(tag: str, dest: Path) -> Path:
    """The release's `app` package, unpacked under `dest`."""
    tree = dest / tag
    if not (tree / "app").is_dir():
        archive = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", tag, "app"],
            check=True,
            capture_output=True,
        ).stdout
        tree.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tree, filter="data")
    return tree


def is_legacy(tree: Path) -> bool:
    return not (tree / "app" / "database" / "alembic").is_dir()


def reset_postgres(url: str) -> None:
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _run(args, *, cwd: Path, data_dir: Path, database_url: str) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(cwd),
        "DATA_DIR": str(data_dir),
        "DATABASE_URL": database_url,
        "SECRET_KEY": settings.secret_key,
    }
    result = subprocess.run(
        [sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-40:])
        raise AssertionError(f"{' '.join(args)} failed in {cwd}:\n{tail}")


@dataclass
class ReleaseDatabase:
    release: str
    legacy: bool
    data_dir: Path
    url: str
    # table -> [{"key": primary key, "refs": foreign keys, "values": the rest}]
    rows: dict[str, list[dict]] = field(default_factory=dict)
    added: dict[str, list[dict]] = field(default_factory=dict)
    orphans: list[dict] = field(default_factory=list)
    missing_tables: list[str] = field(default_factory=list)


def _encode(value):
    """Tag dates for build_release.py, which turns them back into objects."""
    if isinstance(value, datetime.datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, datetime.date):
        return {"__date__": value.isoformat()}
    raise TypeError(f"cannot pass {type(value).__name__} to a release build")


def build_release(
    tag: str,
    trees: Path,
    work: Path,
    *,
    postgres_url: str | None = None,
    rows: dict | None = None,
) -> ReleaseDatabase:
    """A database built and seeded by release `tag`.

    Releases before Alembic only ever ran on SQLite; with `postgres_url` they
    are still built on SQLite, and the upgrade moves them into Postgres.
    """
    tree = extract(tag, trees)
    legacy = is_legacy(tree)
    data_dir = work / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    on_postgres = postgres_url is not None and not legacy
    if on_postgres:
        reset_postgres(postgres_url)
    url = postgres_url if on_postgres else f"sqlite:///{data_dir / 'borg.db'}"

    request = work / "request.json"
    manifest = work / "manifest.json"
    request.write_text(
        json.dumps({"rows": rows or {}, "orphans": legacy}, default=_encode)
    )
    _run(
        [
            str(BUILD_SCRIPT),
            "legacy" if legacy else "alembic",
            str(request),
            str(manifest),
        ],
        cwd=tree,
        data_dir=data_dir,
        database_url=url,
    )
    seeded = json.loads(manifest.read_text())
    return ReleaseDatabase(
        release=tag,
        legacy=legacy,
        data_dir=data_dir,
        url=url,
        rows=seeded["rows"],
        added=seeded["added"],
        orphans=seeded["orphans"],
        missing_tables=seeded["missing_tables"],
    )


def upgrade(
    database: ReleaseDatabase,
    *,
    postgres_url: str | None = None,
    code: Path = REPO_ROOT,
) -> str:
    """Run the current upgrade entry point; return the upgraded database's URL.

    `code` is the tree whose `app` package does the upgrade: the repository
    itself, or a copy carrying a deliberately broken change.
    """
    url = postgres_url or f"sqlite:///{database.data_dir / 'borg.db'}"
    if postgres_url and database.legacy:
        reset_postgres(postgres_url)
    _run(
        ["-m", "app.database.db_upgrade"],
        cwd=code,
        data_dir=database.data_dir,
        database_url=url,
    )
    return url


def copy_code(dest: Path) -> Path:
    """A copy of the current `app` package, to plant a broken change in."""
    shutil.copytree(
        REPO_ROOT / "app",
        dest / "app",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return dest


# --- checks ------------------------------------------------------------------


def _reflect(engine) -> MetaData:
    with warnings.catch_warnings():
        # SQLite reflection cannot describe expression indexes; not needed here.
        warnings.filterwarnings("ignore", "Skipped unsupported reflection")
        metadata = MetaData()
        metadata.reflect(bind=engine)
    return metadata


def _find(conn, table, key: dict):
    clause = and_(*(table.c[name] == value for name, value in key.items()))
    return conn.execute(select(table).where(clause)).first()


def _legacy_operations(conn, kind: str) -> dict[int, dict]:
    """Operations the collapse made from legacy job rows, by the old id."""
    operations = Base.metadata.tables["operations"]
    found = {}
    for row in conn.execute(select(operations).where(operations.c.kind == kind)):
        params = row._mapping["params"]
        if isinstance(params, str):
            params = json.loads(params)
        if params and "legacy_id" in params:
            found[int(params["legacy_id"])] = dict(row._mapping)
    return found


def _legacy_id(key: dict) -> int:
    return int(next(iter(key.values())))


def _count(conn, name: str) -> int:
    return conn.execute(text(f'SELECT COUNT(*) FROM "{name}"')).scalar()


def _seeded(database: ReleaseDatabase):
    """(table, row) for every generated and added row that is not an orphan."""
    orphans = {
        (o["table"], json.dumps(o["key"], sort_keys=True)) for o in database.orphans
    }
    for source in (database.rows, database.added):
        for name, rows in source.items():
            for row in rows:
                if (name, json.dumps(row["key"], sort_keys=True)) not in orphans:
                    yield name, row


def lost_rows(database: ReleaseDatabase, url: str) -> list[str]:
    """Every row the release database was seeded with that the upgrade lost."""
    engine = create_engine(url)
    upgraded = _reflect(engine)
    lost = []
    moved = {}
    try:
        with engine.connect() as conn:
            for name, row in _seeded(database):
                key = row["key"]
                table = upgraded.tables.get(name)
                if table is not None and _find(conn, table, key) is not None:
                    continue
                if name in MOVED_TO_OPERATIONS:
                    if name not in moved:
                        moved[name] = _legacy_operations(
                            conn, MOVED_TO_OPERATIONS[name]
                        )
                    if _legacy_id(key) in moved[name]:
                        continue
                elif name in MOVED_TABLES:
                    seeded = sum(1 for n, _ in _seeded(database) if n == name)
                    if _count(conn, MOVED_TABLES[name]) >= seeded:
                        continue
                lost.append(f"{name} {key}")
    finally:
        engine.dispose()
    return lost


def _current_row(conn, upgraded: MetaData, name: str, key: dict):
    """The row as the application reads it: through the model's column types
    where the table has a model, so an encrypted value comes back decrypted."""
    table = Base.metadata.tables.get(name)
    if table is None or name not in upgraded.tables:
        table = upgraded.tables.get(name)
    if table is None:
        return None
    found = _find(conn, table, key)
    return dict(found._mapping) if found is not None else None


def _same(recorded, now) -> bool:
    if isinstance(now, (datetime.date, bytes)):
        return str(now) == recorded  # the manifest holds them as text
    return now == recorded


def changed_references(database: ReleaseDatabase, url: str) -> list[str]:
    """Foreign keys of surviving rows that no longer point where they did.

    Every seeded reference points at a row that exists, so an upgrade has no
    reason to clear or move it; a cascade through a table rebuild does both.
    A legacy job row is compared with the operation it became, on the
    references both have.
    """
    return _changed(database, url, "refs")


def changed_values(database: ReleaseDatabase, url: str) -> list[str]:
    """Other values of surviving rows that read back differently."""
    return _changed(database, url, "values")


def _changed(database: ReleaseDatabase, url: str, part: str) -> list[str]:
    engine = create_engine(url)
    upgraded = _reflect(engine)
    changed = []
    moved = {}
    try:
        with engine.connect() as conn:
            for name, row in _seeded(database):
                try:
                    now = _current_row(conn, upgraded, name, row["key"])
                except Exception:  # reported by unreadable_tables
                    conn.rollback()
                    continue
                if now is None and name in MOVED_TO_OPERATIONS:
                    if part != "refs":
                        continue  # the operation stores them differently
                    if name not in moved:
                        moved[name] = _legacy_operations(
                            conn, MOVED_TO_OPERATIONS[name]
                        )
                    now = moved[name].get(_legacy_id(row["key"]))
                if now is None:
                    continue  # reported by lost_rows
                for column, value in row[part].items():
                    if (name, column) in REWRITTEN_VALUES:
                        continue
                    if column in now and not _same(value, now[column]):
                        changed.append(
                            f"{name}.{column} {row['key']}: {value!r} -> {now[column]!r}"
                        )
    finally:
        engine.dispose()
    return changed


def mishandled_orphans(database: ReleaseDatabase, url: str) -> list[str]:
    """Orphans the upgrade kept dangling, or dropped although they could stay.

    A row whose pointer is optional keeps the row and loses the pointer; a
    row whose pointer is required cannot be kept and is dropped.
    """
    engine = create_engine(url)
    upgraded = _reflect(engine)
    wrong = []
    try:
        with engine.connect() as conn:
            for orphan in database.orphans:
                name, column, key = orphan["table"], orphan["column"], orphan["key"]
                table = upgraded.tables.get(name)
                row = _find(conn, table, key) if table is not None else None
                if row is None and name in MOVED_TO_OPERATIONS:
                    moved = _legacy_operations(conn, MOVED_TO_OPERATIONS[name])
                    if _legacy_id(key) in moved:
                        continue  # moved; the collapse clears dangling pointers
                if row is None and name in MOVED_TABLES:
                    continue
                if row is None:
                    if orphan["nullable"]:
                        wrong.append(f"{name}.{column} {key}: dropped")
                elif column in row._mapping and row._mapping[column] is not None:
                    wrong.append(f"{name}.{column} {key}: still dangling")
    finally:
        engine.dispose()
    return wrong


def dangling_references(url: str) -> list[str]:
    """Foreign keys pointing at nothing. Postgres refuses them on insert."""
    engine = create_engine(url)
    try:
        if engine.dialect.name != "sqlite":
            return []
        with engine.connect() as conn:
            return [
                str(tuple(r)) for r in conn.exec_driver_sql("PRAGMA foreign_key_check")
            ]
    finally:
        engine.dispose()


def unreadable_tables(url: str) -> list[str]:
    """Tables whose rows the current models cannot load.

    Loading every entity runs each column's result processing, so a value
    the application could not read -- a plaintext secret in an encrypted
    column, a malformed date -- fails here as it would in a request.
    """
    engine = create_engine(url)
    problems = []
    try:
        for mapper in Base.registry.mappers:
            with Session(engine) as session:
                try:
                    session.scalars(select(mapper.class_)).all()
                except Exception as exc:  # reported with the model it broke
                    problems.append(
                        f"{mapper.class_.__name__}: {type(exc).__name__}: {exc}"
                    )
    finally:
        engine.dispose()
    return problems


def assert_upgrade_kept_the_data(database: ReleaseDatabase, url: str) -> None:
    problems = {
        "lost rows": lost_rows(database, url),
        "changed references": changed_references(database, url),
        "changed values": changed_values(database, url),
        "mishandled orphans": mishandled_orphans(database, url),
        "dangling references": dangling_references(url),
        "unreadable tables": unreadable_tables(url),
    }
    report = [
        f"{kind}:\n  " + "\n  ".join(items) for kind, items in problems.items() if items
    ]
    assert not report, f"upgrade from {database.release}:\n" + "\n".join(report)
