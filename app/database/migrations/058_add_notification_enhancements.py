"""
Migration 058: Add notification enhancement option

Adds one new column to notification_settings table:
- include_job_name_in_title: Include job/schedule name in notification titles

Feature: Add job name to notification titles for easier identification

Note: JSON data is automatically sent for json:// and jsons:// webhook URLs.
No database field needed - it's based on the service_url format.
"""

from sqlalchemy import text


def upgrade(db):
    """Add notification enhancement option"""
    print("Running migration 058: Add notification enhancement option")

    try:
        # Add include_job_name_in_title column
        # Default False for existing records (no surprise changes)
        db.execute(text("""
            ALTER TABLE notification_settings
            ADD COLUMN include_job_name_in_title BOOLEAN NOT NULL DEFAULT FALSE
        """))
        print("  ✓ Added include_job_name_in_title column")

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
