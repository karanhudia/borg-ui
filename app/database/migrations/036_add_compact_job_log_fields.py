"""
Migration 036: Add log_file_path, has_logs, and scheduled_compact fields to compact_jobs

This migration adds the log_file_path, has_logs, and scheduled_compact fields to track
log files and trigger type for compact jobs, matching the pattern used by backup/prune jobs.
"""

from sqlalchemy import text

def upgrade(db):
    """Add log_file_path, has_logs, and scheduled_compact fields to compact_jobs table"""
    print("Running migration 036: Add log fields and scheduled_compact to compact_jobs")

    try:
        # Check if columns already exist
        result = db.execute(text("PRAGMA table_info(compact_jobs)"))
        existing_columns = {row[1] for row in result}

        if 'log_file_path' not in existing_columns:
            # Add log_file_path column
            db.execute(text("""
                ALTER TABLE compact_jobs
                ADD COLUMN log_file_path TEXT
            """))
            print("✓ Added log_file_path column")
        else:
            print("⊘ Column log_file_path already exists, skipping")

        if 'has_logs' not in existing_columns:
            # Add has_logs column with default False
            db.execute(text("""
                ALTER TABLE compact_jobs
                ADD COLUMN has_logs INTEGER DEFAULT 0 NOT NULL
            """))
            print("✓ Added has_logs column with default 0")

            # Mark existing jobs with logs field populated as having logs
            db.execute(text("""
                UPDATE compact_jobs
                SET has_logs = 1
                WHERE logs IS NOT NULL AND logs != ''
            """))
            print("✓ Marked existing jobs with logs as has_logs=1")
        else:
            print("⊘ Column has_logs already exists, skipping")

        if 'scheduled_compact' not in existing_columns:
            # Add scheduled_compact column with default False (manual)
            db.execute(text("""
                ALTER TABLE compact_jobs
                ADD COLUMN scheduled_compact INTEGER DEFAULT 0 NOT NULL
            """))
            print("✓ Added scheduled_compact column with default 0 (manual)")

            # Set all existing jobs as manual (False = 0)
            db.execute(text("""
                UPDATE compact_jobs
                SET scheduled_compact = 0
                WHERE scheduled_compact IS NULL
            """))
            print("✓ Set all existing compact jobs as manual")
        else:
            print("⊘ Column scheduled_compact already exists, skipping")

        db.commit()
        print("✓ Migration 036 completed successfully")

    except Exception as e:
        print(f"✗ Migration 036 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 036"""
    print("Running downgrade for migration 036")
    try:
        # SQLite doesn't support DROP COLUMN directly
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! The log_file_path, has_logs, and scheduled_compact columns will remain in the table.")
        db.commit()
        print("✓ Downgrade noted for migration 036")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
