import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from alembic.ddl.sqlite import SQLiteImpl
from sqlalchemy import create_engine, event, inspect, pool

# Alembic runs env.py as a script, so the application package is not importable
# unless the repository root is on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.config import settings  # noqa: E402
from app.database.database import (  # noqa: E402
    Base,
    register_failing_row_withholding,
    register_utc_session_timezone,
)
import app.database.models  # noqa: E402,F401  (registers every table on Base)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


class ResumableSQLiteImpl(SQLiteImpl):
    """Lets a revision an older release left half-applied run to its end.

    Up to 2.4.8 SQLite DDL was committed statement by statement (see `_run`),
    so a boot that died inside a revision kept that revision's leading tables,
    indexes and columns without its version bump, and every later boot failed
    on "already exists" / "duplicate column" (dashboard 845116f75ba79586,
    e9d33421b6cb1d9b). Only DDL ahead of a revision's first row write could
    persist that way, and each such statement is whole or absent, so skipping
    what is already there finishes the revision. Here once, for every revision
    past and future, instead of a guard in each. Declaring the dialect is what
    registers it with Alembic.
    """

    __dialect__ = "sqlite"

    def _inspector(self):
        return inspect(self.connection)

    def create_table(self, table, **kw):
        if self._inspector().has_table(table.name):
            if not table.name.startswith("_alembic_tmp_"):
                for index in table.indexes:
                    self.create_index(index)
                return
            # A batch rebuild's scratch copy. The rebuild died before its
            # copy committed, so the original is intact: start it over.
            super().drop_table(table)
        super().create_table(table, **kw)

    def drop_table(self, table, **kw):
        if self._inspector().has_table(table.name):
            super().drop_table(table, **kw)

    def create_index(self, index, **kw):
        if index.name not in self._index_names():
            super().create_index(index, **kw)

    def drop_index(self, index, **kw):
        if index.name in self._index_names():
            super().drop_index(index, **kw)

    def add_column(self, table_name, column, **kw):
        existing = {c["name"] for c in self._inspector().get_columns(table_name)}
        if column.name not in existing:
            super().add_column(table_name, column, **kw)

    def _index_names(self):
        # sqlite_master, not the inspector: reflection skips expression
        # indexes, and SQLite index names are unique across the database.
        return set(
            self.connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).scalars()
        )


def _database_url() -> str:
    """Migrate whatever the application itself will run against.

    Reading the URL from settings rather than alembic.ini keeps a single source
    of truth; a URL configured in the ini would be a second one, free to drift.
    """
    return config.get_main_option("sqlalchemy.url") or settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        engine = create_engine(
            _database_url(), poolclass=pool.NullPool, hide_parameters=True
        )
        # Data backfills in migrations write under the same naive-UTC
        # convention as the application - same session-zone pin.
        register_utc_session_timezone(engine)
        register_failing_row_withholding(engine)
        with engine.connect() as connection:
            _run(connection)
    else:
        _run(connectable)


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things; batch mode turns an alter into a
        # table rebuild there and into a plain ALTER on Postgres, so one
        # migration body serves both.
        render_as_batch=True,
        compare_type=True,
        compare_server_default=True,
    )


def _run(connection) -> None:
    if connection.dialect.name != "sqlite":
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    # SQLite enforces foreign keys per connection, and the upgrade runner turns
    # them on for the connection it hands in. A batch rebuild is copy, DROP
    # TABLE, rename, and with the pragma on the DROP deletes through every ON
    # DELETE CASCADE that points at the table: the rebuild of backup_plans in
    # a4b5c6d7e8f9 emptied backup_plan_repositories on every pre-Alembic
    # upgrade (#860). Off for the whole run, as alembic's batch mode asks; the
    # transfer and the application turn it on for their own connections. Set
    # on the driver connection with no transaction open, because inside one
    # the pragma is a silent no-op.
    if connection.in_transaction():
        connection.commit()
    driver = connection.connection.dbapi_connection
    driver.execute("PRAGMA foreign_keys=OFF")

    # The sqlite3 module opens a transaction only ahead of a row write, so
    # DDL was committed statement by statement: a boot that died inside a
    # revision (container stopped, disk full, I/O error) kept half of it
    # without the version bump, and no later boot could get past it. Taking
    # transaction control from the driver and emitting BEGIN ourselves (the
    # SQLAlchemy recipe) puts each revision and its version bump in one real
    # transaction: it lands whole or not at all.
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    previous_isolation = driver.isolation_level
    driver.isolation_level = None
    event.listen(connection, "begin", _begin)
    try:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()
    finally:
        event.remove(connection, "begin", _begin)
        driver.isolation_level = previous_isolation


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
