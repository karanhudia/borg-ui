"""
Migration: Split hook_timeout into separate pre_hook_timeout and post_hook_timeout

Adds separate timeout fields for pre-backup and post-backup hooks to allow
independent timeout configuration for each.
"""

def upgrade(db):
    """Add separate pre_hook_timeout and post_hook_timeout columns"""
    cursor = db.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(repositories)")
    columns = [row[1] for row in cursor.fetchall()]

    # Add pre_hook_timeout if it doesn't exist
    if 'pre_hook_timeout' not in columns:
        cursor.execute("""
            ALTER TABLE repositories
            ADD COLUMN pre_hook_timeout INTEGER DEFAULT 300
        """)

        # Copy existing hook_timeout values to pre_hook_timeout
        cursor.execute("""
            UPDATE repositories
            SET pre_hook_timeout = COALESCE(hook_timeout, 300)
        """)
        print("✓ Added pre_hook_timeout column and migrated existing values")

    # Add post_hook_timeout if it doesn't exist
    if 'post_hook_timeout' not in columns:
        cursor.execute("""
            ALTER TABLE repositories
            ADD COLUMN post_hook_timeout INTEGER DEFAULT 300
        """)

        # Copy existing hook_timeout values to post_hook_timeout
        cursor.execute("""
            UPDATE repositories
            SET post_hook_timeout = COALESCE(hook_timeout, 300)
        """)
        print("✓ Added post_hook_timeout column and migrated existing values")

    db.commit()


def downgrade(db):
    """Remove separate timeout columns (SQLite doesn't support DROP COLUMN easily)"""
    print("⚠ Downgrade not supported for SQLite ALTER TABLE DROP COLUMN")
    print("  The pre_hook_timeout and post_hook_timeout columns will remain but be unused")
    print("  The original hook_timeout column will continue to work")
