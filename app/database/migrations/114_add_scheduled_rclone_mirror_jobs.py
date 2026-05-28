"""Add scheduled rclone mirror metadata and job logs."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def _create_index_if_missing(db, index_name: str, ddl: str) -> None:
    if index_name not in {
        index["name"] for index in inspect(_bind(db)).get_indexes("repository_storage")
    }:
        db.execute(text(ddl))


def _drop_index_if_exists(db, table_name: str, index_name: str) -> None:
    if index_name in {
        index["name"] for index in inspect(_bind(db)).get_indexes(table_name)
    }:
        db.execute(text(f"DROP INDEX {index_name}"))


def _drop_column_if_exists(db, table_name: str, column_name: str) -> None:
    if column_name in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))


def upgrade(db):
    timestamp_type = (
        "TIMESTAMP" if _bind(db).dialect.name == "postgresql" else "DATETIME"
    )

    _add_column_if_missing(db, "repository_storage", "sync_cron_expression", "VARCHAR")
    _add_column_if_missing(
        db,
        "repository_storage",
        "sync_timezone",
        "VARCHAR NOT NULL DEFAULT 'UTC'",
    )
    _add_column_if_missing(
        db,
        "repository_storage",
        "last_scheduled_sync_at",
        timestamp_type,
    )
    _add_column_if_missing(
        db,
        "repository_storage",
        "next_scheduled_sync_at",
        timestamp_type,
    )
    _add_column_if_missing(
        db,
        "rclone_sync_jobs",
        "triggered_by",
        "VARCHAR NOT NULL DEFAULT 'manual'",
    )
    _add_column_if_missing(
        db,
        "rclone_sync_jobs",
        "scheduled_for",
        timestamp_type,
    )
    _add_column_if_missing(db, "rclone_sync_jobs", "log_text", "TEXT")
    _create_index_if_missing(
        db,
        "ix_repository_storage_next_scheduled_sync_at",
        "CREATE INDEX ix_repository_storage_next_scheduled_sync_at "
        "ON repository_storage (next_scheduled_sync_at)",
    )
    db.commit()


def downgrade(db):
    _drop_index_if_exists(
        db,
        "repository_storage",
        "ix_repository_storage_next_scheduled_sync_at",
    )
    _drop_column_if_exists(db, "rclone_sync_jobs", "log_text")
    _drop_column_if_exists(db, "rclone_sync_jobs", "scheduled_for")
    _drop_column_if_exists(db, "rclone_sync_jobs", "triggered_by")
    _drop_column_if_exists(db, "repository_storage", "next_scheduled_sync_at")
    _drop_column_if_exists(db, "repository_storage", "last_scheduled_sync_at")
    _drop_column_if_exists(db, "repository_storage", "sync_timezone")
    _drop_column_if_exists(db, "repository_storage", "sync_cron_expression")
    db.commit()
