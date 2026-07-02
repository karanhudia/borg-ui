"""Add Borg prune keep-within retention fields."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def _add_column_if_missing(db, table_name: str, column_name: str) -> None:
    if column_name not in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} VARCHAR"))


def _drop_column_if_present(db, table_name: str, column_name: str) -> None:
    if column_name not in _columns(db, table_name):
        return
    if _bind(db).dialect.name == "sqlite":
        version = db.execute(text("SELECT sqlite_version()")).scalar() or "0.0.0"
        supports_drop = tuple(int(part) for part in version.split(".")[:3]) >= (
            3,
            35,
            0,
        )
        if not supports_drop:
            raise RuntimeError(
                "SQLite does not support DROP COLUMN; "
                f"{table_name}.{column_name} was not removed"
            )
    db.execute(text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))


def upgrade(db):
    _add_column_if_missing(db, "scheduled_jobs", "prune_keep_within")
    _add_column_if_missing(db, "backup_plans", "prune_keep_within")
    db.commit()


def downgrade(db):
    _drop_column_if_present(db, "scheduled_jobs", "prune_keep_within")
    _drop_column_if_present(db, "backup_plans", "prune_keep_within")
    db.commit()
