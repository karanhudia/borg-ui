"""Add restore check notification triggers."""

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
        "notification_settings",
        "notify_on_restore_check_success",
        "BOOLEAN NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        db,
        "notification_settings",
        "notify_on_restore_check_failure",
        "BOOLEAN NOT NULL DEFAULT 1",
    )
    db.commit()
    logger.info("Migration 103_add_restore_check_notifications completed")


def downgrade(db):
    logger.warning(
        "Downgrade not supported for SQLite — restore check notification columns will remain"
    )
