from sqlalchemy import text

def upgrade(connection):
    """Add notify_on_backup_start column to notification_settings table

    This enables users to receive notifications when backups start,
    helping them avoid accidentally interrupting backups in progress.
    """

    # Check if column already exists in notification_settings (idempotent)
    result = connection.execute(text("PRAGMA table_info(notification_settings)"))
    columns = [row[1] for row in result]

    if 'notify_on_backup_start' not in columns:
        # Add notify_on_backup_start column to notification_settings
        connection.execute(text("""
            ALTER TABLE notification_settings ADD COLUMN notify_on_backup_start BOOLEAN NOT NULL DEFAULT 0
        """))

        print("✓ Migration 023: Added notify_on_backup_start column to notification_settings")
    else:
        print("⊘ Migration 023: notify_on_backup_start column already exists in notification_settings, skipping")

    connection.commit()

def downgrade(connection):
    """Remove notify_on_backup_start column from notification_settings table"""
    # SQLite doesn't support DROP COLUMN directly, would need to recreate table
    # For now, we'll just mark it as deprecated in a downgrade scenario
    print("⚠ Migration 023 downgrade: SQLite doesn't support DROP COLUMN")
    print("  The notify_on_backup_start column will remain but can be ignored")
    connection.commit()
