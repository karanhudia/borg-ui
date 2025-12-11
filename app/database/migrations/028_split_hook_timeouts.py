"""
Migration: Split hook_timeout into separate pre_hook_timeout and post_hook_timeout

Adds separate timeout fields for pre-backup and post-backup hooks to allow
independent timeout configuration for each.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add separate pre_hook_timeout and post_hook_timeout columns"""
    # Check if columns already exist
    result = connection.execute(text("PRAGMA table_info(repositories)"))
    columns = [row[1] for row in result]

    # Add pre_hook_timeout if it doesn't exist
    if 'pre_hook_timeout' not in columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN pre_hook_timeout INTEGER DEFAULT 300
        """))

        # Copy existing hook_timeout values to pre_hook_timeout
        connection.execute(text("""
            UPDATE repositories
            SET pre_hook_timeout = COALESCE(hook_timeout, 300)
        """))
        print("✓ Added pre_hook_timeout column and migrated existing values")
    else:
        print("⊘ pre_hook_timeout column already exists, skipping")

    # Add post_hook_timeout if it doesn't exist
    if 'post_hook_timeout' not in columns:
        connection.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN post_hook_timeout INTEGER DEFAULT 300
        """))

        # Copy existing hook_timeout values to post_hook_timeout
        connection.execute(text("""
            UPDATE repositories
            SET post_hook_timeout = COALESCE(hook_timeout, 300)
        """))
        print("✓ Added post_hook_timeout column and migrated existing values")
    else:
        print("⊘ post_hook_timeout column already exists, skipping")

    connection.commit()


def downgrade(connection):
    """Remove separate timeout columns (SQLite doesn't support DROP COLUMN easily)"""
    print("⚠ Downgrade not supported for SQLite ALTER TABLE DROP COLUMN")
    print("  The pre_hook_timeout and post_hook_timeout columns will remain but be unused")
    print("  The original hook_timeout column will continue to work")
