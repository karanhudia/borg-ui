"""One-time upgrade of an existing database onto the Alembic baseline.

Both databases exist at the same time, so nothing is ever serialised: a fresh
baseline database is built, rows are copied across by column name, and the old
database is kept as the rollback. That the target may be Postgres instead of a
new SQLite file is not a special case -- it is the same code path with a
different URL, which is the whole reason Postgres costs so little here.

A database from before Alembic is first walked up the frozen legacy migration
ladder, on a throwaway copy, so the data transforms those migrations performed
(an interval turned into a cron expression, a timeout split in two) are already
done before the copy runs -- copying by column name cannot reproduce them. Any
user can upgrade straight from an old release to the latest; no manual stop on an
intermediate version is required.

Nothing is destroyed. The source is renamed, never deleted, and every deviation
between source and target is reported rather than silently absorbed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, event, inspect, text
from sqlalchemy.engine import Engine, make_url

from app.config import settings
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
    action: str  # "fresh" | "transferred" | "skipped" | "migrated"
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
    log.info("applying database migrations up to head")
    config = _alembic_config(url)
    if engine is None:
        command.upgrade(config, "head")
        return

    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()


def _has_legacy_schema(engine: Engine) -> bool:
    """Tables, but no Alembic bookkeeping — a database from before the cutover."""
    with engine.connect() as conn:
        names = set(inspect(conn).get_table_names())
    return bool(names) and "alembic_version" not in names


def ensure_schema() -> None:
    """Give the configured database its schema, if it has none.

    The application builds its own schema at startup however it is launched: a
    container entrypoint, `uvicorn app.main:app`, a test harness. Leaving this
    to the entrypoint alone would mean the app starts against an empty database
    whenever it is started any other way, and every request that touches the
    database fails.

    Cheap when there is nothing to do: one query for the recorded revision.

    A database that predates Alembic is deliberately left alone. Moving one onto
    the baseline copies every row and can change where the database lives, which
    is a one-time operation with a rollback (`python -m app.database.db_upgrade`)
    and not something to do behind a server that is already coming up.

    Safe to call from several processes at once. The entrypoint builds the
    schema once before gunicorn forks, so workers normally find it already
    there; but nothing guarantees that ordering when the app is started some
    other way, and losing the race must not take a worker down.
    """
    url = settings.database_url
    engine = _engine(url)
    try:
        if _is_at_head(engine):
            return

        if _has_legacy_schema(engine):
            log.error(
                "database predates Alembic and was left untouched; "
                "run 'python -m app.database.db_upgrade' to migrate it"
            )
            return

        log.info("no schema found at %s, building it", _safe_url(url))
        try:
            _upgrade_to_head(url, engine)
        except Exception:
            # Another process may be building the same schema. Only its own
            # failure is worth reporting, so wait for the build to finish
            # before deciding: a database mid-build is not yet at head, and
            # checking once would call a won race lost.
            if _await_head(engine):
                log.info("schema was built by another process")
                return
            raise
    finally:
        engine.dispose()


def _await_head(engine: Engine, attempts: int = 20, delay: float = 0.5) -> bool:
    """Whether the schema reaches head within roughly ten seconds."""
    for _ in range(attempts):
        if _is_at_head(engine):
            return True
        time.sleep(delay)
    return False


# Columns whose data an old migration moved elsewhere and then dropped. A legacy
# database is walked up the migration ladder (on a throwaway copy) before its rows
# are copied, so by the time the copy runs each of these is already gone and its
# data already lives in its new home. They stay listed here as the post-condition
# of that catch-up: if one is STILL present after the ladder ran, its transform did
# not take -- the ladder could not handle this database -- and copying forward would
# silently drop the data the column holds. That is the one case the upgrade refuses.
# (Columns a migration merely deprecated, or backfilled without dropping, are not
# here: their data survives the copy regardless, and the report still lists every
# dropped column for visibility. Add a row when a future data transform drops its
# source column.)
_TRANSFORM_SENTINELS: tuple[tuple[str, str, str], ...] = (
    (
        "repositories",
        "check_interval_days",
        "check schedules were stored as an interval and converted to a cron "
        "expression (migration 034); the interval column is gone from the current "
        "schema, so copying it forward would drop the schedule",
    ),
)


def _unresolved_transforms(columns: dict[str, set[str]]) -> list[str]:
    """Data transforms the migration ladder should have completed but did not.

    Pure over a {table: {columns}} view, so it is exercised without a database. A
    sentinel column still present means its transform never ran; empty means every
    transform this upgrade depends on is done and the rows are safe to copy.
    """
    reasons = []
    for table, column, why in _TRANSFORM_SENTINELS:
        if column in columns.get(table, set()):
            reasons.append(f"{table}.{column}: {why}")
    return reasons


def _snapshot_sqlite(source: Path, dest: Path) -> None:
    """A transactionally consistent copy of a live SQLite database.

    Not a file copy: a write-ahead log that has not been checkpointed would be left
    behind, silently copying a stale image of a database still in use. The online
    backup API reads a consistent snapshot and does not touch the source, which has
    to stay exactly as it was to serve as the rollback.
    """
    import sqlite3

    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(dest))
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()


def _remove_sqlite(path: Path) -> None:
    """Delete a SQLite file and any write-ahead sidecars beside it."""
    for p in (
        path,
        path.with_name(f"{path.name}-wal"),
        path.with_name(f"{path.name}-shm"),
    ):
        if p.exists():
            p.unlink()


def _require_transforms_applied(engine: Engine, failed_migrations: list[str]) -> None:
    """Refuse, loudly, if the catch-up left a data transform undone.

    The ladder is lenient -- a migration that raised was skipped -- so a run that
    finished is not proof the transforms took. This is that proof: it reads the
    caught-up copy and, if a sentinel column survived, stops before anything is
    copied. The source is untouched and remains the rollback.
    """
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    columns = {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table, _, _ in _TRANSFORM_SENTINELS
        if table in present
    }
    reasons = _unresolved_transforms(columns)
    if reasons:
        detail = "\n  - ".join(reasons)
        note = (
            f"\n  (legacy migrations that raised and were skipped: "
            f"{', '.join(failed_migrations)})"
            if failed_migrations
            else ""
        )
        raise RuntimeError(
            "The built-in catch-up could not bring this database up to the current "
            "schema; a data transformation did not complete, so copying it forward "
            f"would lose data:\n  - {detail}{note}\n"
            "This database is older than the automatic upgrade can handle."
        )


def _catch_up_source(source_path: Path, catch_up_path: Path) -> None:
    """Walk a pre-Alembic database up the legacy ladder, on a throwaway copy.

    Copying rows by column name cannot reproduce what the old migrations did to the
    data -- an interval became a cron expression, a timeout was split in two. So the
    ladder runs first, and on a copy, never the source: it rewrites tables, and the
    source must stay intact to be the rollback. Afterwards the transforms the copy
    step depends on must be done; if one is not, refuse before anything is copied.

    A source that already speaks Alembic is past the ladder: it is skipped. This
    only happens when an Alembic SQLite database is moved into a fresh Postgres --
    the target has no schema, so it is not the durable-fork "already upgraded" case
    -- and running the legacy ladder against an Alembic database is the very thing
    the target side forbids. The snapshot is still copied from; it just is not
    walked up a ladder it has already climbed.
    """
    from app.database.migrations import run_migrations

    _remove_sqlite(catch_up_path)  # a leftover from a run that died mid-catch-up
    _snapshot_sqlite(source_path, catch_up_path)

    # A plain engine, matching how these migrations ran at startup: several rebuild
    # a table with foreign keys switched off, and enforcing them here would break
    # the ladder on exactly the databases it exists to rescue.
    ladder_engine = create_engine(_sqlite_url(catch_up_path))
    try:
        with ladder_engine.connect() as conn:
            if inspect(conn).has_table("alembic_version"):
                return  # already on Alembic; the snapshot is copied from as-is
        failed = run_migrations(ladder_engine)
        _require_transforms_applied(ladder_engine, failed)
    except Exception:
        # The copy is scaffolding; a refused upgrade must not leave it behind to be
        # mistaken for unfinished work on the next boot. The source is untouched.
        _remove_sqlite(catch_up_path)
        raise
    finally:
        ladder_engine.dispose()


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

    # The durable fork. A database that already speaks Alembic is only ever moved
    # forward by Alembic -- never by the legacy ladder, however far behind it is.
    # This is the steady state, and the one correct path the moment a second
    # revision exists. Ask only where the target genuinely lives: for SQLite that is
    # the source file, and only if it exists -- connecting would otherwise create an
    # empty file and mask a fresh install.
    if to_postgres or source_path.exists():
        state = _alembic_state(final_url)
        if state == "head":
            log.info("database already at the current schema, nothing to do")
            return UpgradeReport(action="skipped", target_url=_safe_url(final_url))
        if state == "behind":
            log.info("database is on Alembic but behind head; applying revisions")
            _upgrade_to_head(final_url)
            return UpgradeReport(action="migrated", target_url=_safe_url(final_url))

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

    # Bring the source up the legacy ladder first, on a throwaway copy, so its data
    # is in the shape the baseline expects before a single row is copied. Refuses
    # here, source untouched, if a transform the copy depends on did not take.
    catch_up_path = source_path.with_name(
        f"{source_path.stem}_catchup{source_path.suffix}"
    )
    _catch_up_source(source_path, catch_up_path)
    source_engine = create_engine(_sqlite_url(catch_up_path))
    target_engine = _engine(target_url, disposable=not to_postgres)
    try:
        _upgrade_to_head(target_url, target_engine)

        report = _transfer(source_engine, target_engine)
        report.target_url = _safe_url(target_url)

        if to_postgres:
            report.sequences_reset = _reset_sequences(target_engine)
    finally:
        source_engine.dispose()
        target_engine.dispose()
        # The rollback is the untouched source; the caught-up copy was scaffolding.
        _remove_sqlite(catch_up_path)

    report.source_kept_at = _finalise(source_path, target_path, to_postgres)
    report.action = "transferred"
    return report


def _alembic_state(url: str) -> str | None:
    """Where an existing database stands relative to Alembic.

    ``None``     -- not Alembic-managed (no alembic_version): legacy, or empty.
    ``"head"``   -- managed and at the current revision: nothing to do.
    ``"behind"`` -- managed but older: apply the pending revisions, nothing else.

    The distinction the legacy ladder hangs on. It runs only for ``None``; a
    managed database, however far behind, is moved forward by Alembic alone. Once
    on Alembic, whatever SQLite file happens to sit in the data dir is irrelevant
    -- it may be a deliberately kept rollback -- because this asks the target that
    DATABASE_URL points at, which after a migration into Postgres IS Postgres.
    """
    engine = _engine(url)
    try:
        with engine.connect() as conn:
            if not inspect(conn).has_table("alembic_version"):
                return None
        return "head" if _is_at_head(engine) else "behind"
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
