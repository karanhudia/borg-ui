"""
Migration 010: Add backup hooks to repositories table

This migration adds pre/post backup script hooks to allow users to run
custom scripts before and after backups (e.g., wake up NAS, cleanup, etc).
"""

from sqlalchemy import text

def upgrade(connection):
    """Add backup hook columns to repositories table"""

    # Check if columns exist
    result = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='repositories'
    """))

    table_sql = result.fetchone()[0] if result.fetchone() else ""

    columns_to_add = []

    if 'pre_backup_script' not in table_sql:
        columns_to_add.append(('pre_backup_script', 'TEXT'))

    if 'post_backup_script' not in table_sql:
        columns_to_add.append(('post_backup_script', 'TEXT'))

    if 'hook_timeout' not in table_sql:
        columns_to_add.append(('hook_timeout', 'INTEGER DEFAULT 300'))

    if 'continue_on_hook_failure' not in table_sql:
        columns_to_add.append(('continue_on_hook_failure', 'INTEGER DEFAULT 0'))

    # Add columns
    for column_name, column_type in columns_to_add:
        connection.execute(text(f"""
            ALTER TABLE repositories ADD COLUMN {column_name} {column_type}
        """))
        print(f"  Added column: repositories.{column_name}")

    if not columns_to_add:
        print("  Skipped (exists): All hook columns already exist")

    print("✓ Migration 010: Added backup hooks to repositories")

def downgrade(connection):
    """Remove backup hook columns from repositories table"""

    # SQLite doesn't support DROP COLUMN easily, would need table recreation
    # For now, we'll just set them to NULL
    connection.execute(text("""
        UPDATE repositories SET
            pre_backup_script = NULL,
            post_backup_script = NULL,
            hook_timeout = 300,
            continue_on_hook_failure = 0
    """))

    print("✓ Migration 010 rolled back: Reset backup hook columns to defaults")
