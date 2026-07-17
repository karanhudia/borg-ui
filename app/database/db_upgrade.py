"""One-time upgrade of an existing database onto the Alembic baseline.

Both databases exist at the same time, so nothing is ever serialised: a fresh
baseline database is built, rows are copied across by column name, and the old
database is kept as the rollback. That the target may be Postgres instead of a
new SQLite file is not a special case -- it is the same code path with a
different URL, which is the whole reason Postgres costs so little here.

Nothing is destroyed. The source is renamed, never deleted, and every deviation
between source and target is reported rather than silently absorbed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, event, inspect, text
from sqlalchemy.engine import Engine, make_url

from app.database.database import Base
import app.database.models  # noqa: F401  (registers every table on Base)

BACKUP_SUFFIX = "_bak"
_CHUNK = 2000

log = logging.getLogger("borg_ui.db_upgrade")


@dataclass
class TableReport:
    name: str
    rows: int = 0
    dropped_columns: list[str] = field(default_factory=list)
    added_columns: list[str] = field(default_factory=list)
    orphans_cleared: dict[str, int] = field(default_factory=dict)


@dataclass
class UpgradeReport:
    action: str  # "fresh" | "transferred" | "skipped"
    target_url: str
    source_kept_at: Path | None = None
    tables: list[TableReport] = field(default_factory=list)
    sequences_reset: int = 0

    @property
    def rows(self) -> int:
        return sum(t.rows for t in self.tables)

    def lines(self) -> list[str]:
        out = [f"{self.action}: {self.rows} rows into {self.target_url}"]
        for t in self.tables:
            if t.dropped_columns:
                out.append(
                    f"  {t.name}: dropped column(s) not in the model: "
                    f"{', '.join(t.dropped_columns)}"
                )
            if t.added_columns:
                out.append(
                    f"  {t.name}: new column(s), left at their default: "
                    f"{', '.join(t.added_columns)}"
                )
            for col, n in t.orphans_cleared.items():
                out.append(
                    f"  {t.name}.{col}: {n} row(s) pointed at a row that no longer "
                    f"exists; cleared to NULL"
                )
        if self.source_kept_at:
            out.append(f"  previous database kept at {self.source_kept_at}")
        return out


def _alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _is_at_head(engine: Engine) -> bool:
    with engine.connect() as conn:
        if not inspect(conn).has_table("alembic_version"):
            return False
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(
        _alembic_config(str(engine.url))
    ).get_current_head()
    return current == head


def _self_referencing_columns(table) -> set[str]:
    return {
        fk.parent.name
        for fk in table.foreign_keys
        if fk.column.table.name == table.name
    }


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _engine(url: str, *, disposable: bool = False) -> Engine:
    """An engine that enforces foreign keys on either dialect.

    SQLite only enforces them when a connection asks it to, so a plain engine
    would happily write a reference to a row that does not exist -- the very
    corruption this transfer exists to clean up. Postgres always enforces, and
    the two paths must not disagree about what is a valid row.

    `disposable` marks the half-built target. Nothing survives a failure there:
    the file is deleted and the transfer starts over, so paying for durability
    while building it buys nothing -- and on NFS an fsync per statement is what
    the whole cost is. It is dropped only until the file takes the source's
    place; from then on the application opens it with its own settings, since
    synchronous is a property of the connection, not of the file.

    Set from the connect event, never mid-transaction: the pragma is a silent
    no-op inside a transaction.
    """
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if disposable:
                cur.execute("PRAGMA synchronous=OFF")
            cur.close()

    return engine


def _upgrade_to_head(url: str, engine: Engine | None = None) -> None:
    """Build the baseline schema.

    With an engine, the migration runs on its connection rather than one alembic
    opens for itself -- otherwise the target's pragmas would not apply to the
    schema build, which is 48 tables and 131 indexes and the slowest part of an
    upgrade over NFS.
    """
    log.info("building the baseline schema (48 tables, 131 indexes)")
    config = _alembic_config(url)
    if engine is None:
        command.upgrade(config, "head")
        return

    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()


def alembic_init(
    sqlite_db: str | Path,
    postgres_conn: str | None = None,
) -> UpgradeReport:
    """Bring `sqlite_db` onto the Alembic baseline.

    With `postgres_conn`, the rows land in Postgres and the SQLite file is kept
    as the rollback. Without it, they land in a new SQLite file which then takes
    the place of the old one -- same code path, so a SQLite upgrade is just as
    reversible as a Postgres one.
    """
    source_path = Path(sqlite_db)
    to_postgres = postgres_conn is not None

    # Where the database ends up living. In the SQLite case that is the source's
    # own path: the new file takes its place. So "already upgraded?" has to be
    # asked of this location, never of the temporary file -- after a successful
    # run the temporary file is gone, and asking it would migrate an already
    # migrated database on the next pod restart.
    final_url = postgres_conn if to_postgres else _sqlite_url(source_path)

    if _already_upgraded(final_url, source_path, to_postgres):
        log.info("database already at the current schema, nothing to do")
        return UpgradeReport(action="skipped", target_url=_safe_url(final_url))

    if not source_path.exists():
        # Fresh install: no rows to move, so the baseline is built where the
        # database belongs and there is nothing to swap.
        log.info("fresh install: creating the database at %s", _safe_url(final_url))
        _upgrade_to_head(final_url)
        return UpgradeReport(action="fresh", target_url=_safe_url(final_url))

    target_path = (
        None
        if to_postgres
        else source_path.with_name(f"{source_path.stem}_new{source_path.suffix}")
    )
    target_url = postgres_conn if to_postgres else _sqlite_url(target_path)

    log.info(
        "upgrading database: %s -> %s (this can take several minutes on a large "
        "database; the app will not start serving until it finishes)",
        source_path,
        _safe_url(target_url),
    )

    if target_path is not None and target_path.exists():
        # Only ever left behind by a run that died before the swap; it is a
        # temporary file by construction and never the rollback.
        target_path.unlink()

    target_engine = _engine(target_url, disposable=not to_postgres)
    source_engine = _engine(_sqlite_url(source_path))
    _upgrade_to_head(target_url, target_engine)

    report = _transfer(source_engine, target_engine)
    report.target_url = _safe_url(target_url)

    if to_postgres:
        report.sequences_reset = _reset_sequences(target_engine)

    source_engine.dispose()
    target_engine.dispose()

    report.source_kept_at = _finalise(source_path, target_path, to_postgres)
    report.action = "transferred"
    return report


def _already_upgraded(final_url: str, source_path: Path, to_postgres: bool) -> bool:
    """Decide by state whether there is anything left to do.

    Not by row count: a fresh install is legitimately empty, and treating empty
    as "not done" makes it re-migrate itself on every restart.
    """
    if to_postgres:
        # The target is Postgres and DATABASE_URL points at it, so it IS the
        # database. If it is at the current schema, the work is done -- whatever
        # SQLite file happens to sit in the data dir is irrelevant (it may be a
        # deliberately kept rollback). Only an un-migrated Postgres means transfer.
        engine = _engine(final_url)
        try:
            return _is_at_head(engine)
        finally:
            engine.dispose()

    # SQLite: the upgraded database has taken the source's place, so the source
    # path being stamped means the work is done -- rows or no rows.
    if not source_path.exists():
        return False
    engine = _engine(final_url)
    try:
        return _is_at_head(engine)
    finally:
        engine.dispose()


def _safe_url(url: str) -> str:
    return make_url(url).render_as_string(hide_password=True)


def _transfer(source: Engine, target: Engine) -> UpgradeReport:
    report = UpgradeReport(action="transferred", target_url="")

    log.info("transferring rows")
    reflected = MetaData()
    reflected.reflect(bind=source)

    with source.connect() as src, target.begin() as dst:
        deferred: list[tuple] = []

        # sorted_tables is topological: parents before children, which is what
        # Postgres requires -- it checks every foreign key at insert time.
        for table in Base.metadata.sorted_tables:
            source_table = reflected.tables.get(table.name)
            if source_table is None:
                continue

            tr = TableReport(name=table.name)
            source_cols = set(source_table.columns.keys())
            target_cols = set(table.columns.keys())
            tr.dropped_columns = sorted(source_cols - target_cols)
            tr.added_columns = sorted(target_cols - source_cols)

            common = [c for c in table.columns.keys() if c in source_cols]

            # A self-reference cannot be satisfied while the table is still being
            # filled: a row may point at one that does not exist yet. Insert NULL
            # and set it afterwards -- correct regardless of row order.
            self_refs = _self_referencing_columns(table) & set(common)
            for col in self_refs:
                if not table.columns[col].nullable:
                    raise RuntimeError(
                        f"{table.name}.{col} references its own table but is NOT NULL; "
                        "it cannot be transferred in two passes"
                    )

            cleared = _orphan_columns(src, table, common)
            tr.orphans_cleared = {c: n for c, n in cleared.items() if n}

            # Read through the reflected table, not raw SQL: SQLite keeps
            # datetimes as text, and only the column's type turns them back into
            # datetime objects. Postgres would accept the raw strings and cast
            # them itself, so this mistake is invisible there and fatal here.
            rows = src.execute(
                source_table.select().with_only_columns(
                    *[source_table.c[c] for c in common]
                )
            )
            stmt = table.insert()

            batch = []
            for row in rows:
                data = dict(zip(common, row))
                for col in cleared:
                    if (
                        data.get(col) is not None
                        and cleared[col]
                        and _is_orphan(src, table, col, data[col])
                    ):
                        data[col] = None
                pending = {c: data.pop(c) for c in self_refs if data.get(c) is not None}
                if pending:
                    deferred.append((table, data[_pk_name(table)], pending))
                for c in self_refs:
                    data[c] = None
                batch.append(data)
                tr.rows += 1
                if len(batch) >= _CHUNK:
                    dst.execute(stmt, batch)
                    batch = []
            if batch:
                dst.execute(stmt, batch)

            # Only the big tables are worth a line; agent_job_logs alone is ~90%
            # of a real database, so without this the log looks stalled on it.
            if tr.rows >= _CHUNK:
                log.info("  %s: %d rows", table.name, tr.rows)

            report.tables.append(tr)

        for table, pk_value, values in deferred:
            dst.execute(
                table.update()
                .where(table.c[_pk_name(table)] == pk_value)
                .values(**values)
            )

    return report


def _pk_name(table) -> str:
    return list(table.primary_key.columns)[0].name


def _orphan_columns(src, table, common: list[str]) -> dict[str, int]:
    """Count rows whose foreign key points at a row that is not there.

    SQLite only enforces foreign keys when the connection asks it to, so a
    database can hold references to rows that were deleted years ago. Postgres
    enforces them always and would reject those rows outright.
    """
    counts: dict[str, int] = {}
    for fk in table.foreign_keys:
        col = fk.parent.name
        if col not in common:
            continue
        parent_table = fk.column.table.name
        parent_col = fk.column.name
        if parent_table not in [t.name for t in Base.metadata.sorted_tables]:
            continue
        n = src.execute(
            text(
                f'SELECT COUNT(*) FROM "{table.name}" c '
                f'LEFT JOIN "{parent_table}" p ON p."{parent_col}" = c."{col}" '
                f'WHERE c."{col}" IS NOT NULL AND p."{parent_col}" IS NULL'
            )
        ).scalar()
        if n:
            if not table.columns[col].nullable:
                raise RuntimeError(
                    f"{table.name}.{col} has {n} row(s) pointing at a missing "
                    f'"{parent_table}" row, and the column is NOT NULL -- '
                    "cannot transfer without losing rows"
                )
            counts[col] = n
    return counts


def _is_orphan(src, table, col: str, value) -> bool:
    fk = next(fk for fk in table.foreign_keys if fk.parent.name == col)
    parent_table = fk.column.table.name
    parent_col = fk.column.name
    return not src.execute(
        text(f'SELECT 1 FROM "{parent_table}" WHERE "{parent_col}" = :v'), {"v": value}
    ).first()


def _reset_sequences(engine: Engine) -> int:
    """Postgres does not advance a sequence when ids are inserted explicitly.

    Without this the next insert without an id collides. SQLite needs no
    equivalent: it derives the next id from the data, and advances
    sqlite_sequence by itself. The asymmetry is why a SQLite-only test can never
    catch a missing setval.
    """
    n = 0
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            pk = list(table.primary_key.columns)
            if len(pk) != 1:
                continue
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:t, :c)"),
                {"t": table.name, "c": pk[0].name},
            ).scalar()
            if not seq:
                continue
            conn.execute(
                text(
                    f'SELECT setval(:s, COALESCE((SELECT MAX("{pk[0].name}") '
                    f'FROM "{table.name}"), 1))'
                ),
                {"s": seq},
            )
            n += 1
    return n


def upgrade_from_settings() -> UpgradeReport:
    """Bring the configured database up to date.

    The target is wherever the application is about to run: DATABASE_URL decides
    it, so there is no second switch to keep in sync. A SQLite URL means the file
    is upgraded in place (the new one takes its name); anything else means the
    rows move there and the SQLite file stays behind as the rollback.
    """
    from app.config import settings

    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite":
        return alembic_init(Path(url.database))
    return alembic_init(Path(settings.data_dir) / "borg.db", settings.database_url)


def _finalise(source_path: Path, target_path: Path | None, to_postgres: bool) -> Path:
    """Move the source aside, and in the SQLite case put the new file in its place.

    The source becomes the backup in both cases, so "the old file is still there
    and the target is empty" always means "not upgraded yet" -- one rule instead
    of two, and no way to re-import a stale snapshot over a live database.
    """
    backup = source_path.with_name(
        f"{source_path.stem}{BACKUP_SUFFIX}{source_path.suffix}"
    )
    if backup.exists():
        raise RuntimeError(
            f"{backup} already exists -- refusing to overwrite the rollback"
        )
    source_path.rename(backup)
    if not to_postgres:
        target_path.rename(source_path)
    return backup


if __name__ == "__main__":
    # Runs once from the entrypoint, before the application is imported. It
    # cannot live in the app: gunicorn forks several workers, each of which
    # would import it, and they would race each other over the same swap.
    #
    # Configure logging to stdout here rather than at import: this makes the
    # progress lines above visible in `kubectl logs`, and turns on alembic's own
    # "Running upgrade ->" output (its logging is otherwise never configured,
    # because the Config is built in code without an ini file). Without this the
    # pod is silent for the whole migration.
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [db-upgrade] %(message)s",
        stream=sys.stdout,
    )
    report = upgrade_from_settings()
    for line in report.lines():
        log.info(line)
