"""
Migration 032: Add Storage and Mount Point to SSH Connections

This migration adds:
- mount_point: Logical mount point for remote machines (e.g., /hetzner)
- storage fields: Total, used, available space and percentage tracking
"""

from sqlalchemy import text

def upgrade(db):
    """Add mount_point and storage fields to ssh_connections table"""
    print("Running migration 032: Add Storage and Mount Point to SSH Connections")

    try:
        # Check which columns already exist
        result = db.execute(text("PRAGMA table_info(ssh_connections)"))
        existing_columns = {row[1] for row in result}

        columns_to_add = {
            'mount_point': 'TEXT',
            'storage_total': 'BIGINT',
            'storage_used': 'BIGINT',
            'storage_available': 'BIGINT',
            'storage_percent_used': 'REAL',
            'last_storage_check': 'TIMESTAMP'
        }

        # Add only missing columns
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                db.execute(text(f"""
                    ALTER TABLE ssh_connections
                    ADD COLUMN {column_name} {column_type}
                """))
                print(f"✓ Added {column_name} column")
            else:
                print(f"⊘ Column {column_name} already exists, skipping")

        db.commit()
        print("✓ Migration 032 completed successfully")

    except Exception as e:
        print(f"✗ Migration 032 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 032"""
    print("Running downgrade for migration 032")
    try:
        # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
        # For now, we'll just print a message
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        db.commit()
        print("✓ Downgrade noted for migration 032")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
