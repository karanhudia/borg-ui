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


def _engine(url: str) -> Engine:
    """An engine that enforces foreign keys on either dialect.

    SQLite only enforces them when a connection asks it to, so a plain engine
    would happily write a reference to a row that does not exist -- the very
    corruption this transfer exists to clean up. Postgres always enforces, and
    the two paths must not disagree about what is a valid row.

    Set from the connect event, never mid-transaction: the pragma is a silent
    no-op inside a transaction.
    """
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


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
        return UpgradeReport(action="skipped", target_url=_safe_url(final_url))

    if not source_path.exists():
        # Fresh install: no rows to move, so the baseline is built where the
        # database belongs and there is nothing to swap.
        command.upgrade(_alembic_config(final_url), "head")
        return UpgradeReport(action="fresh", target_url=_safe_url(final_url))

    target_path = (
        None
        if to_postgres
        else source_path.with_name(f"{source_path.stem}_new{source_path.suffix}")
    )
    target_url = postgres_conn if to_postgres else _sqlite_url(target_path)

    if target_path is not None and target_path.exists():
        # Only ever left behind by a run that died before the swap; it is a
        # temporary file by construction and never the rollback.
        target_path.unlink()

    target_engine = _engine(target_url)
    source_engine = _engine(_sqlite_url(source_path))
    command.upgrade(_alembic_config(target_url), "head")

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
    if not to_postgres:
        # The upgraded database has taken the source's place, so the source path
        # being stamped means the work is done -- rows or no rows.
        if not source_path.exists():
            return False
        engine = _engine(final_url)
        try:
            return _is_at_head(engine)
        finally:
            engine.dispose()

    engine = _engine(final_url)
    try:
        if not _is_at_head(engine):
            return False
        if not source_path.exists():
            return True  # steady state: the source was consumed long ago
        # Postgres is ready and the old file is still here. Empty means a
        # transfer that never ran; populated means one that half-ran, or someone
        # put an old file back. The second is not ours to guess at.
        if _has_rows(engine):
            raise RuntimeError(
                f"{final_url.split('@')[-1]} already holds rows while {source_path} is "
                "still present. Either a previous transfer was interrupted after "
                "loading rows, or a database file was restored by hand. Refusing to "
                f"transfer on top of existing rows -- move {source_path} aside to "
                "confirm the Postgres database is the live one."
            )
        return False
    finally:
        engine.dispose()


def _safe_url(url: str) -> str:
    return make_url(url).render_as_string(hide_password=True)


def _has_rows(engine: Engine) -> bool:
    insp = inspect(engine)
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            if insp.has_table(table.name):
                if conn.execute(text(f'SELECT 1 FROM "{table.name}" LIMIT 1')).first():
                    return True
    return False


def _transfer(source: Engine, target: Engine) -> UpgradeReport:
    report = UpgradeReport(action="transferred", target_url="")

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
