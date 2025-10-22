"""
Database migrations package
Automatically discovers and runs numbered migration files
"""
import structlog
from pathlib import Path
from sqlalchemy import text
from app.database.database import engine

logger = structlog.get_logger()

def run_migrations():
    """
    Run all pending database migrations
    Discovers and executes all numbered migration files in order
    """
    migrations_dir = Path(__file__).parent
    migration_files = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.py"))

    if not migration_files:
        logger.info("No migration files found")
        return

    logger.info(f"Found {len(migration_files)} migration file(s)")

    with engine.connect() as connection:
        for migration_file in migration_files:
            migration_name = migration_file.stem
            module_name = f"app.database.migrations.{migration_name}"

            try:
                # Import the migration module
                import importlib
                migration_module = importlib.import_module(module_name)

                # Check if migration has upgrade function
                if not hasattr(migration_module, 'upgrade'):
                    logger.warning(f"Migration {migration_name} has no upgrade function, skipping")
                    continue

                logger.info(f"Running migration: {migration_name}")

                # Execute the upgrade function
                migration_module.upgrade(connection)
                connection.commit()

                logger.info(f" Migration completed: {migration_name}")

            except Exception as e:
                logger.error(f"Migration failed: {migration_name}", error=str(e))
                connection.rollback()
                # Continue with other migrations instead of failing completely
                continue

    logger.info("All migrations completed")
