"""
Migration 050: Add source_ssh_connection_id to repositories table

This migration adds the source_ssh_connection_id field to the repositories table
to support pull-based backups where the data source is on a different machine
than the Borg UI server.
"""

from sqlalchemy import text

def upgrade(db):
    """Add source_ssh_connection_id to repositories table"""
    print("Running migration 050: Add source_ssh_connection_id to repositories")

    try:
        # Check if column already exists
        result = db.execute(text("PRAGMA table_info(repositories)"))
        columns = {row[1] for row in result}

        if 'source_ssh_connection_id' not in columns:
            db.execute(text("""
                ALTER TABLE repositories
                ADD COLUMN source_ssh_connection_id INTEGER
            """))
            print("✓ Added source_ssh_connection_id column to repositories")
        else:
            print("⊘ Column source_ssh_connection_id already exists in repositories")

        # Create index for faster lookups
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_repositories_source_ssh
                ON repositories(source_ssh_connection_id)
            """))
            print("✓ Created index idx_repositories_source_ssh")
        except Exception as e:
            print(f"⊘ Index idx_repositories_source_ssh may already exist: {e}")

        db.commit()
        print("✓ Migration 050 completed successfully")

    except Exception as e:
        print(f"✗ Migration 050 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 050"""
    print("Running downgrade for migration 050")
    try:
        # SQLite doesn't support DROP COLUMN directly
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! The source_ssh_connection_id column will remain in the repositories table.")
        db.commit()
        print("✓ Downgrade noted for migration 050")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
