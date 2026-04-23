"""Add notify_on_backup_warning column to notification_settings table."""

from sqlalchemy import text


def upgrade(connection):
    result = connection.execute(text("PRAGMA table_info(notification_settings)"))
    columns = [row[1] for row in result]

    if "notify_on_backup_warning" not in columns:
        connection.execute(
            text(
                """
                ALTER TABLE notification_settings
                ADD COLUMN notify_on_backup_warning BOOLEAN NOT NULL DEFAULT 0
                """
            )
        )
        print(
            "✓ Migration 093: Added notify_on_backup_warning column to notification_settings"
        )
    else:
        print(
            "⊘ Migration 093: notify_on_backup_warning already exists in notification_settings, skipping"
        )

    connection.commit()


def downgrade(connection):
    print("⚠ Migration 093 downgrade skipped")
    print("  SQLite does not support DROP COLUMN; notify_on_backup_warning will remain")
    connection.commit()
