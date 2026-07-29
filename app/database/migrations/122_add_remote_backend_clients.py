"""Add database-backed remote backend clients."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _table_exists(db, table_name: str) -> bool:
    return inspect(_bind(db)).has_table(table_name)


def _timestamp_type(db) -> str:
    return "TIMESTAMP" if _bind(db).dialect.name == "postgresql" else "DATETIME"


def upgrade(db):
    if not _table_exists(db, "remote_backend_clients"):
        timestamp_type = _timestamp_type(db)
        db.execute(
            text(
                "CREATE TABLE remote_backend_clients ("
                "id VARCHAR PRIMARY KEY, "
                "name VARCHAR NOT NULL, "
                "api_base_url VARCHAR NOT NULL, "
                "web_base_url VARCHAR NOT NULL, "
                "health_status VARCHAR NOT NULL DEFAULT 'unknown', "
                f"health_checked_at {timestamp_type}, "
                "app_version VARCHAR, "
                "borg_version VARCHAR, "
                "borg2_version VARCHAR, "
                "health_error TEXT, "
                "compatibility VARCHAR NOT NULL DEFAULT 'unknown', "
                "compatibility_message TEXT, "
                f"created_at {timestamp_type} NOT NULL, "
                f"updated_at {timestamp_type} NOT NULL"
                ")"
            )
        )
    db.commit()


def downgrade(db):
    if _table_exists(db, "remote_backend_clients"):
        db.execute(text("DROP TABLE remote_backend_clients"))
    db.commit()
