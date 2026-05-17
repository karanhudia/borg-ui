"""Add advanced check flag storage for repository and plan checks."""

from sqlalchemy import text


def _columns(db, table_name: str) -> set[str]:
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def upgrade(db):
    _add_column_if_missing(
        db,
        "repositories",
        "check_extra_flags",
        "check_extra_flags TEXT",
    )
    _add_column_if_missing(
        db,
        "backup_plans",
        "check_extra_flags",
        "check_extra_flags TEXT",
    )
    _add_column_if_missing(
        db,
        "check_jobs",
        "extra_flags",
        "extra_flags TEXT",
    )
    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave columns in place.
    db.commit()
