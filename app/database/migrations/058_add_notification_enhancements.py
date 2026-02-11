"""
Migration 058: Add notification enhancement option

Adds one new column to notification_settings table:
- include_job_name_in_title: Include job/schedule name in notification titles

Feature: Add job name to notification titles for easier identification

Note: JSON data is automatically sent for json:// and jsons:// webhook URLs.
No database field needed - it's based on the service_url format.
"""

from sqlalchemy import text


def column_exists(db, table_name, column_name):
    """Check if a column exists in a table"""
    result = db.execute(text(f"PRAGMA table_info({table_name})"))
    columns = [row[1] for row in result.fetchall()]  # Column name is at index 1
    return column_name in columns


def upgrade(db):
    """Add notification enhancement option"""
    print("Running migration 058: Add notification enhancement option")

    try:
        # Add include_job_name_in_title column (idempotent)
        if not column_exists(db, "notification_settings", "include_job_name_in_title"):
            db.execute(text("""
                ALTER TABLE notification_settings
                ADD COLUMN include_job_name_in_title BOOLEAN NOT NULL DEFAULT FALSE
            """))
            print("  ✓ Added include_job_name_in_title column")
        else:
            print("  ℹ Column include_job_name_in_title already exists, skipping")

        db.commit()
        print("✓ Migration 058 completed successfully")

    except Exception as e:
        print(f"✗ Migration 058 failed: {e}")
        db.rollback()
        raise


def downgrade(db):
    """Remove notification enhancement option"""
    print("Running downgrade for migration 058")

    try:
        # Remove column
        db.execute(text("""
            ALTER TABLE notification_settings
            DROP COLUMN IF EXISTS include_job_name_in_title
        """))
        print("  ✓ Removed include_job_name_in_title column")

        db.commit()
        print("✓ Downgrade for migration 058 completed")

    except Exception as e:
        print(f"✗ Downgrade failed: {e}")
        db.rollback()
        raise
