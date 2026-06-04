"""Add rclone sync job operation discriminator."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def _sqlite_supports_drop_column(db) -> bool:
    version = db.execute(text("SELECT sqlite_version()")).scalar() or "0.0.0"
    return tuple(int(part) for part in version.split(".")[:3]) >= (3, 35, 0)


def _drop_column_if_exists(db, table_name: str, column_name: str) -> None:
    if column_name in _columns(db, table_name):
        if _bind(db).dialect.name == "sqlite" and not _sqlite_supports_drop_column(db):
            print(
                f"SQLite version does not support DROP COLUMN; "
                f"{table_name}.{column_name} will remain"
            )
            return
        db.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))


def upgrade(db):
    _add_column_if_missing(
        db,
        "rclone_sync_jobs",
        "operation",
        "VARCHAR NOT NULL DEFAULT 'sync'",
    )
    db.commit()


def downgrade(db):
    _drop_column_if_exists(db, "rclone_sync_jobs", "operation")
    db.commit()
