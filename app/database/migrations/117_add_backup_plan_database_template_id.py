"""Add database_template_id to backup_plans so the Source dialog can default
back to the Database tab on edit instead of treating database-backed plans as
plain file sources."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _table_exists(db, table_name: str) -> bool:
    return inspect(_bind(db)).has_table(table_name)


def _columns(db, table_name: str) -> set[str]:
    if not _table_exists(db, table_name):
        return set()
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def upgrade(db):
    if "database_template_id" not in _columns(db, "backup_plans"):
        db.execute(
            text("ALTER TABLE backup_plans ADD COLUMN database_template_id VARCHAR")
        )
    db.commit()


def downgrade(db):
    db.commit()
