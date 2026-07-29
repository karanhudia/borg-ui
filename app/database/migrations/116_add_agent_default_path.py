"""Add default browse paths to managed agent enrollment and machines."""

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
    if "default_path" not in _columns(db, "agent_enrollment_tokens"):
        db.execute(
            text("ALTER TABLE agent_enrollment_tokens ADD COLUMN default_path VARCHAR")
        )

    if "default_path" not in _columns(db, "agent_machines"):
        db.execute(text("ALTER TABLE agent_machines ADD COLUMN default_path VARCHAR"))

    db.commit()


def downgrade(db):
    db.commit()
