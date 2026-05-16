"""Add multi-source location JSON fields."""

from sqlalchemy import text


def _table_exists(db, table_name: str) -> bool:
    result = db.execute(
        text(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=:table_name
            """
        ),
        {"table_name": table_name},
    )
    return result.fetchone() is not None


def _columns(db, table_name: str) -> set[str]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    if _table_exists(db, table_name) and column_name not in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def upgrade(db):
    _add_column_if_missing(
        db,
        "repositories",
        "source_locations",
        "source_locations TEXT",
    )
    _add_column_if_missing(
        db,
        "backup_plans",
        "source_locations",
        "source_locations TEXT",
    )
    db.commit()


def downgrade(db):
    db.commit()
