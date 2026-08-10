"""The pre-Alembic migration ladder, kept for one job: catching a legacy database up.

These 135 numbered files were the whole schema history before the Alembic cutover.
They are no longer run at startup -- the live schema is Alembic's baseline and every
new change is an Alembic revision. They are kept, frozen, for exactly one purpose:
a database from before Alembic is walked up this ladder once, on a throwaway copy,
so that the data transforms these migrations performed (an interval turned into a
cron expression, a timeout split in two, a connection backfilled) are already done
before its rows are copied onto the baseline. See app.database.db_upgrade.

Do not add to these files. New schema changes are Alembic revisions.
"""

import importlib
from pathlib import Path

import structlog
from sqlalchemy.engine import Engine

logger = structlog.get_logger()


def run_migrations(engine: Engine) -> list[str]:
    """Apply every legacy migration in order against ``engine``.

    Lenient on purpose, and it has to be: this reproduces what the startup runner
    did for years -- a migration that raises is rolled back, logged, and skipped
    rather than aborting the run. The schema this leaves is therefore the schema a
    long-lived install actually has, not a stricter one it never reached. The
    caller does not trust a clean run; it checks the post-conditions it depends on
    (that the data transforms took) and refuses if they did not.

    Returns the names of migrations that raised, so the caller can log them.
    """
    migrations_dir = Path(__file__).parent
    migration_files = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.py"))

    if not migration_files:
        logger.info("no legacy migration files found")
        return []

    logger.info(f"running {len(migration_files)} legacy migration(s)")

    failed: list[str] = []
    with engine.connect() as connection:
        for migration_file in migration_files:
            name = migration_file.stem
            try:
                module = importlib.import_module(f"app.database.migrations.{name}")
                if not hasattr(module, "upgrade"):
                    logger.warning(
                        f"migration {name} has no upgrade function, skipping"
                    )
                    continue
                module.upgrade(connection)
                connection.commit()
            except Exception as e:  # noqa: BLE001 -- match the historical runner
                logger.error(f"legacy migration failed: {name}", error=str(e))
                connection.rollback()
                failed.append(name)

    logger.info("legacy migration ladder complete")
    return failed
