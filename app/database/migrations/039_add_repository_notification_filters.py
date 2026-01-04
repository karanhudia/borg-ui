"""
Migration 039: Add repository notification filters

Adds the ability to filter notifications to specific repositories.
Users can create multiple notification configs and select which repos each applies to.
"""

from sqlalchemy import text

def upgrade(conn):
    """Add repository notification filtering"""
    print("Running migration 039: Add repository notification filters")

    try:
        # 1. Add monitor_all_repositories field to notification_settings
        result = conn.execute(text("PRAGMA table_info(notification_settings)"))
        columns = [row[1] for row in result]

        if 'monitor_all_repositories' not in columns:
            conn.execute(text("""
                ALTER TABLE notification_settings
                ADD COLUMN monitor_all_repositories BOOLEAN DEFAULT TRUE
            """))
            print("  ✓ Added monitor_all_repositories to notification_settings")

        # 2. Create repository_notifications join table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS repository_notifications (
                notification_setting_id INTEGER NOT NULL,
                repository_id INTEGER NOT NULL,
                FOREIGN KEY (notification_setting_id) REFERENCES notification_settings (id) ON DELETE CASCADE,
                FOREIGN KEY (repository_id) REFERENCES repositories (id) ON DELETE CASCADE,
                PRIMARY KEY (notification_setting_id, repository_id)
            )
        """))
        print("  ✓ Created repository_notifications join table")

        conn.commit()
        print("✓ Migration 039 completed successfully")

    except Exception as e:
        print(f"✗ Migration 039 failed: {str(e)}")
        conn.rollback()
        raise

def downgrade(conn):
    """Remove repository notification filtering"""
    print("Running downgrade for migration 039")

    try:
        # Drop join table
        conn.execute(text("DROP TABLE IF EXISTS repository_notifications"))

        # Note: SQLite doesn't support DROP COLUMN, would need table recreation
        # Leaving monitor_all_repositories column for backwards compatibility

        conn.commit()
        print("✓ Downgrade 039 completed")

    except Exception as e:
        print(f"✗ Downgrade 039 failed: {str(e)}")
        conn.rollback()
        raise
