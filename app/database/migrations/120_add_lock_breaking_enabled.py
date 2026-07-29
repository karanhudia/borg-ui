"""Add lock_breaking_enabled to system settings."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def upgrade(db):
    if "lock_breaking_enabled" not in _columns(db, "system_settings"):
        db.execute(
            text(
                """
                ALTER TABLE system_settings
                ADD COLUMN lock_breaking_enabled BOOLEAN DEFAULT 1 NOT NULL
                """
            )
        )

    db.commit()


def downgrade(db):
    if "lock_breaking_enabled" in _columns(db, "system_settings"):
        if _bind(db).dialect.name == "sqlite":
            print(
                "SQLite downgrade does not remove system_settings.lock_breaking_enabled"
            )
        else:
            db.execute(
                text("ALTER TABLE system_settings DROP COLUMN lock_breaking_enabled")
            )
            db.commit()
