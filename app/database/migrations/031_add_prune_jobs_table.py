"""
Migration 031: Add PruneJob Table

This migration creates the prune_jobs table to track scheduled and manual
prune operations, allowing them to appear in the activity feed with logs.
"""

from sqlalchemy import text

def upgrade(db):
    """Create prune_jobs table"""
    print("Running migration 031: Add PruneJob Table")

    try:
        # Create prune_jobs table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS prune_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id INTEGER NOT NULL,
                repository_path VARCHAR(255),
                status VARCHAR(50) DEFAULT 'pending',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                logs TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (repository_id) REFERENCES repositories(id)
            )
        """))
        print("✓ Created prune_jobs table")

        db.commit()
        print("✓ Migration 031 completed successfully")

    except Exception as e:
        print(f"✗ Migration 031 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 031"""
    print("Running downgrade for migration 031")
    try:
        db.execute(text("DROP TABLE IF EXISTS prune_jobs"))
        db.commit()
        print("✓ Successfully dropped prune_jobs table")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
