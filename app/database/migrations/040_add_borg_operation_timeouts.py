"""
Migration 040: Add configurable timeouts for borg operations

Adds timeout fields to system_settings table to make borg operation timeouts configurable.
This is essential for large repositories where operations like 'borg info' can take
significantly longer than the default hardcoded timeouts (e.g., 166 minutes for cache building).
"""

from sqlalchemy import text

def upgrade(conn):
    """Add borg operation timeout columns to system_settings table"""
    # Check if columns already exist
    result = conn.execute(text("PRAGMA table_info(system_settings)"))
    columns = [row[1] for row in result]

    # Add borg_info_timeout (default 600 seconds = 10 minutes)
    if 'borg_info_timeout' not in columns:
        conn.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN borg_info_timeout INTEGER DEFAULT 600
        """))

    # Add borg_list_timeout (default 300 seconds = 5 minutes)
    if 'borg_list_timeout' not in columns:
        conn.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN borg_list_timeout INTEGER DEFAULT 300
        """))

    # Add borg_init_timeout (default 300 seconds = 5 minutes)
    if 'borg_init_timeout' not in columns:
        conn.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN borg_init_timeout INTEGER DEFAULT 300
        """))

    # Add borg_general_timeout (default 600 seconds = 10 minutes)
    if 'borg_general_timeout' not in columns:
        conn.execute(text("""
            ALTER TABLE system_settings
            ADD COLUMN borg_general_timeout INTEGER DEFAULT 600
        """))

    conn.commit()

def downgrade(conn):
    """Remove borg operation timeout columns from system_settings table"""
    # SQLite doesn't support DROP COLUMN directly in older versions
    # This is a simplified downgrade that may not work on all SQLite versions
    conn.execute(text("ALTER TABLE system_settings DROP COLUMN borg_info_timeout"))
    conn.execute(text("ALTER TABLE system_settings DROP COLUMN borg_list_timeout"))
    conn.execute(text("ALTER TABLE system_settings DROP COLUMN borg_init_timeout"))
    conn.execute(text("ALTER TABLE system_settings DROP COLUMN borg_general_timeout"))
    conn.commit()
