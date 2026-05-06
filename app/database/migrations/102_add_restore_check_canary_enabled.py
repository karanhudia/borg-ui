"""Add explicit restore check canary source opt-in."""

from sqlalchemy import text
import structlog

logger = structlog.get_logger()


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    columns = [row[1] for row in db.execute(text(f"PRAGMA table_info({table_name})"))]
    if column_name not in columns:
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def upgrade(db):
    _add_column_if_missing(
        db,
        "repositories",
        "restore_check_canary_enabled",
        "BOOLEAN NOT NULL DEFAULT 0",
    )
    db.execute(
        text(
            """
            UPDATE repositories
            SET restore_check_canary_enabled = 1
            WHERE restore_check_cron_expression IS NOT NULL
              AND restore_check_cron_expression != ''
              AND COALESCE(restore_check_full_archive, 0) = 0
              AND (
                restore_check_paths IS NULL
                OR restore_check_paths = ''
                OR restore_check_paths = '[]'
              )
            """
        )
    )
    db.commit()
    logger.info("Migration 102_add_restore_check_canary_enabled completed")


def downgrade(db):
    logger.warning(
        "Downgrade not supported for SQLite — restore_check_canary_enabled will remain"
    )
