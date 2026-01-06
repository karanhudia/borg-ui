"""
Migration 041: Add Redis URL to System Settings

This migration adds redis_url column to system_settings table:
- redis_url: External Redis URL for connecting to remote Redis instances (nullable)
"""

from sqlalchemy import text

def upgrade(db):
    """Add redis_url field to system_settings table"""
    print("Running migration 041: Add Redis URL")

    try:
        # Check which columns already exist
        result = db.execute(text("PRAGMA table_info(system_settings)"))
        existing_columns = {row[1] for row in result}

        columns_to_add = {
            'redis_url': ('TEXT', 'NULL'),
        }

        # Add only missing columns
        for column_name, (column_type, default_value) in columns_to_add.items():
            if column_name not in existing_columns:
                db.execute(text(f"""
                    ALTER TABLE system_settings
                    ADD COLUMN {column_name} {column_type} DEFAULT {default_value}
                """))
                print(f"✓ Added {column_name} column")
            else:
                print(f"⊘ Column {column_name} already exists, skipping")

        db.commit()
        print("✓ Migration 041 completed successfully")

    except Exception as e:
        print(f"✗ Migration 041 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 041"""
    print("Running downgrade for migration 041")
    try:
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        db.commit()
        print("✓ Downgrade noted for migration 041")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
