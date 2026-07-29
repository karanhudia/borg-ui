"""Add rclone OAuth provider credentials to system settings."""

from sqlalchemy import inspect, text


RCLONE_OAUTH_COLUMNS = {
    "google_drive_oauth_client_id": "VARCHAR",
    "google_drive_oauth_client_secret_encrypted": "VARCHAR",
    "onedrive_oauth_client_id": "VARCHAR",
    "onedrive_oauth_client_secret_encrypted": "VARCHAR",
}


def _bind(db):
    return db.get_bind() if hasattr(db, "get_bind") else db


def _columns(db, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(_bind(db)).get_columns(table_name)}


def upgrade(db):
    existing_columns = _columns(db, "system_settings")
    for column_name, ddl in RCLONE_OAUTH_COLUMNS.items():
        if column_name not in existing_columns:
            db.execute(
                text(f"ALTER TABLE system_settings ADD COLUMN {column_name} {ddl}")
            )
    db.commit()


def downgrade(db):
    # SQLite migrations in this project are additive; leave columns in place.
    db.commit()
