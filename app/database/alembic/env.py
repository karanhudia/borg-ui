import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

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


def _run(connection) -> None:
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

    # SQLite enforces foreign keys per connection, and the upgrade runner turns
    # them on for the connection it hands in. A batch rebuild is copy, DROP
    # TABLE, rename, and with the pragma on the DROP deletes through every ON
    # DELETE CASCADE that points at the table: the rebuild of backup_plans in
    # a4b5c6d7e8f9 emptied backup_plan_repositories on every pre-Alembic
    # upgrade (#860). Off for the whole run, as alembic's batch mode asks; the
    # transfer and the application turn it on for their own connections. Set
    # before the transaction opens, because inside one the pragma is a no-op.
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
