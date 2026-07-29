"""Add grouped source locations to repositories and backup plans."""

from sqlalchemy import text


def _columns(db, table_name: str) -> set[str]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _add_column_if_missing(db, table_name: str, column_name: str) -> None:
    if column_name not in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} TEXT"))


def upgrade(db):
    _add_column_if_missing(db, "repositories", "source_locations")
    _add_column_if_missing(db, "backup_plans", "source_locations")
    db.commit()


def downgrade(db):
    db.commit()
