"""
Migration 043: Add log_file_path and has_logs fields to check_jobs

This migration adds the log_file_path and has_logs fields to track log files
for check jobs, matching the pattern used by backup, prune, and compact jobs.
"""

from sqlalchemy import text

def upgrade(db):
    """Add log_file_path and has_logs fields to check_jobs table"""
    print("Running migration 043: Add log_file_path and has_logs to check_jobs")

    try:
        # Check if columns already exist
        result = db.execute(text("PRAGMA table_info(check_jobs)"))
        existing_columns = {row[1] for row in result}

        if 'log_file_path' not in existing_columns:
            # Add log_file_path column
            db.execute(text("""
                ALTER TABLE check_jobs
                ADD COLUMN log_file_path TEXT
            """))
            print("✓ Added log_file_path column")
        else:
            print("⊘ Column log_file_path already exists, skipping")

        if 'has_logs' not in existing_columns:
            # Add has_logs column with default False
            db.execute(text("""
                ALTER TABLE check_jobs
                ADD COLUMN has_logs INTEGER DEFAULT 0 NOT NULL
            """))
            print("✓ Added has_logs column with default 0")

            # Mark existing jobs with logs field populated as having logs
            db.execute(text("""
                UPDATE check_jobs
                SET has_logs = 1
                WHERE logs IS NOT NULL AND logs != ''
            """))
            print("✓ Marked existing jobs with logs as has_logs=1")
        else:
            print("⊘ Column has_logs already exists, skipping")

        db.commit()
        print("✓ Migration 043 completed successfully")

    except Exception as e:
        print(f"✗ Migration 043 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 043"""
    print("Running downgrade for migration 043")
    try:
        # SQLite doesn't support DROP COLUMN directly
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! The log_file_path and has_logs columns will remain in the table.")
        db.commit()
        print("✓ Downgrade noted for migration 043")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
