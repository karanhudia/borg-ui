"""
Migration 034: Add scheduled_prune field to prune_jobs

This migration adds the scheduled_prune field to track whether a prune job
was triggered manually or by the scheduler.
"""

from sqlalchemy import text

def upgrade(db):
    """Add scheduled_prune field to prune_jobs table"""
    print("Running migration 034: Add scheduled_prune field to prune_jobs")

    try:
        # Check if column already exists
        result = db.execute(text("PRAGMA table_info(prune_jobs)"))
        existing_columns = {row[1] for row in result}

        if 'scheduled_prune' not in existing_columns:
            # Add scheduled_prune column with default False (manual)
            db.execute(text("""
                ALTER TABLE prune_jobs
                ADD COLUMN scheduled_prune INTEGER DEFAULT 0 NOT NULL
            """))
            print("✓ Added scheduled_prune column with default 0 (manual)")

            # Update existing rows to be manual (False = 0)
            db.execute(text("""
                UPDATE prune_jobs
                SET scheduled_prune = 0
                WHERE scheduled_prune IS NULL
            """))
            print("✓ Set all existing prune jobs as manual")
        else:
            print("⊘ Column scheduled_prune already exists, skipping")

        db.commit()
        print("✓ Migration 034 completed successfully")

    except Exception as e:
        print(f"✗ Migration 034 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 034"""
    print("Running downgrade for migration 034")
    try:
        # SQLite doesn't support DROP COLUMN directly
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! The scheduled_prune column will remain in the table.")
        db.commit()
        print("✓ Downgrade noted for migration 034")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
