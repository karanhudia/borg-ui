"""Add storage snapshot fields to rclone remotes."""

from sqlalchemy import inspect, text


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def upgrade(db):
    existing = _columns(db, "rclone_remotes")
    columns_to_add = {
        "storage_total": "BIGINT",
        "storage_used": "BIGINT",
        "storage_available": "BIGINT",
        "storage_percent_used": "REAL",
        "last_storage_check": "TIMESTAMP",
    }

    for column_name, column_type in columns_to_add.items():
        if column_name not in existing:
            db.execute(
                text(
                    f"""
                    ALTER TABLE rclone_remotes
                    ADD COLUMN {column_name} {column_type} NULL
                    """
                )
            )

    db.commit()


def downgrade(db):
    existing = _columns(db, "rclone_remotes")
    if _bind(db).dialect.name == "sqlite":
        print("SQLite downgrade does not remove rclone_remotes storage columns")
        return

    for column_name in (
        "last_storage_check",
        "storage_percent_used",
        "storage_available",
        "storage_used",
        "storage_total",
    ):
        if column_name in existing:
            db.execute(text(f"ALTER TABLE rclone_remotes DROP COLUMN {column_name}"))

    db.commit()
