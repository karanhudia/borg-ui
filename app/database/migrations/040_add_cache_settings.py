"""
Migration 040: Add Cache Settings

This migration adds cache configuration to system_settings:
- cache_ttl_minutes: Time to live for cached archives in minutes (default 120 = 2 hours)
- cache_max_size_mb: Maximum cache size in megabytes (default 2048 = 2GB)
"""

from sqlalchemy import text

def upgrade(db):
    """Add cache settings fields to system_settings table"""
    print("Running migration 040: Add Cache Settings")

    try:
        # Check which columns already exist
        result = db.execute(text("PRAGMA table_info(system_settings)"))
        existing_columns = {row[1] for row in result}

        columns_to_add = {
            'cache_ttl_minutes': ('INTEGER', '120'),  # 2 hours default
            'cache_max_size_mb': ('INTEGER', '2048')  # 2GB default
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
            SET cache_ttl_minutes = 120
            WHERE cache_ttl_minutes IS NULL
        """))

        db.execute(text("""
            UPDATE system_settings
            SET cache_max_size_mb = 2048
            WHERE cache_max_size_mb IS NULL
        """))

        db.commit()
        print("✓ Migration 040 completed successfully")

    except Exception as e:
        print(f"✗ Migration 040 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 040"""
    print("Running downgrade for migration 040")
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
        print("✓ Downgrade noted for migration 040")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
