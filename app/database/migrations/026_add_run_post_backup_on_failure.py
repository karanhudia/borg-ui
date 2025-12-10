"""
Migration 026: Add run_post_backup_on_failure to repositories

This migration adds a flag to control whether post-backup scripts run on failure.
Fixes issue #85 where post-backup scripts don't run when backups fail.
"""

def upgrade(db):
    """Add run_post_backup_on_failure column to repositories table"""
    print("Running migration 026: Add run_post_backup_on_failure to repositories")

    try:
        # Check if column already exists
        cursor = db.execute("PRAGMA table_info(repositories)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'run_post_backup_on_failure' not in columns:
            # Add the new column with default False for backward compatibility
            db.execute("""
                ALTER TABLE repositories
                ADD COLUMN run_post_backup_on_failure BOOLEAN DEFAULT 0 NOT NULL
            """)
            db.commit()
            print("✓ Added run_post_backup_on_failure column to repositories (default: False)")
        else:
            print("✓ Column run_post_backup_on_failure already exists, skipping")

    except Exception as e:
        print(f"✗ Migration 026 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Remove run_post_backup_on_failure column"""
    print("Running downgrade for migration 026")

    try:
        # SQLite doesn't support DROP COLUMN directly in older versions
        # We need to recreate the table without the column
        cursor = db.execute("PRAGMA table_info(repositories)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'run_post_backup_on_failure' in columns:
            print("⚠️  Downgrade would require table recreation. Skipping for safety.")
            print("   If needed, manually remove the column or restore from backup.")
        else:
            print("✓ Column run_post_backup_on_failure doesn't exist, nothing to do")

    except Exception as e:
        print(f"✗ Downgrade failed: {e}")
        raise
