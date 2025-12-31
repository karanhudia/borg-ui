"""
Migration 033: Add Log Management Settings

This migration adds log management configuration to system_settings:
- log_save_policy: Controls which jobs have logs saved (failed_only, failed_and_warnings, all_jobs)
- log_max_total_size_mb: Maximum total size of all log files in MB
- log_cleanup_on_startup: Whether to run log cleanup on application startup
"""

from sqlalchemy import text

def upgrade(db):
    """Add log management fields to system_settings table"""
    print("Running migration 033: Add Log Management Settings")

    try:
        # Check which columns already exist
        result = db.execute(text("PRAGMA table_info(system_settings)"))
        existing_columns = {row[1] for row in result}

        columns_to_add = {
            'log_save_policy': ('TEXT', "'failed_and_warnings'"),
            'log_max_total_size_mb': ('INTEGER', '500'),
            'log_cleanup_on_startup': ('INTEGER', '1')  # SQLite uses INTEGER for BOOLEAN (1=True, 0=False)
        }

        # Add only missing columns with defaults
        for column_name, (column_type, default_value) in columns_to_add.items():
            if column_name not in existing_columns:
                db.execute(text(f"""
                    ALTER TABLE system_settings
                    ADD COLUMN {column_name} {column_type} DEFAULT {default_value}
                """))
                print(f"✓ Added {column_name} column with default {default_value}")
            else:
                print(f"⊘ Column {column_name} already exists, skipping")

        # Update existing rows to ensure they have the default values
        # (in case they were NULL before)
        db.execute(text("""
            UPDATE system_settings
            SET log_save_policy = 'failed_and_warnings'
            WHERE log_save_policy IS NULL
        """))

        db.execute(text("""
            UPDATE system_settings
            SET log_max_total_size_mb = 500
            WHERE log_max_total_size_mb IS NULL
        """))

        db.execute(text("""
            UPDATE system_settings
            SET log_cleanup_on_startup = 1
            WHERE log_cleanup_on_startup IS NULL
        """))

        db.commit()
        print("✓ Migration 033 completed successfully")

    except Exception as e:
        print(f"✗ Migration 033 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 033"""
    print("Running downgrade for migration 033")
    try:
        # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
        # For now, we'll just print a message
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! To manually downgrade, you would need to:")
        print("!   1. Create a new system_settings table without these columns")
        print("!   2. Copy data from the old table")
        print("!   3. Drop the old table")
        print("!   4. Rename the new table")
        db.commit()
        print("✓ Downgrade noted for migration 033")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
