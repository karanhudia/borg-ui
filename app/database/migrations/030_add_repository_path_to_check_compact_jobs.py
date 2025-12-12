"""
Migration 030: Add Repository Path to Check and Compact Jobs

This migration adds repository_path column to check_jobs and compact_jobs tables
to store the repository path at job creation time. This ensures we can display
the repository information even if the repository is deleted from the system later.
"""

from sqlalchemy import text

def upgrade(db):
    """Add repository_path column to check_jobs and compact_jobs"""
    print("Running migration 030: Add Repository Path to Check and Compact Jobs")

    try:
        # Add repository_path to check_jobs
        try:
            db.execute(text("ALTER TABLE check_jobs ADD COLUMN repository_path VARCHAR(255) NULL"))
            print("✓ Added repository_path column to check_jobs table")
        except Exception as e:
            error_str = str(e).lower()
            if "duplicate column" in error_str or "already exists" in error_str:
                print("! Column repository_path already exists in check_jobs")
            else:
                # Try to verify the column exists
                try:
                    db.execute(text("SELECT repository_path FROM check_jobs LIMIT 1"))
                    print("✓ Verified column exists in check_jobs despite error")
                except:
                    print(f"✗ Column missing and add failed in check_jobs: {e}")
                    raise e

        # Add repository_path to compact_jobs
        try:
            db.execute(text("ALTER TABLE compact_jobs ADD COLUMN repository_path VARCHAR(255) NULL"))
            print("✓ Added repository_path column to compact_jobs table")
        except Exception as e:
            error_str = str(e).lower()
            if "duplicate column" in error_str or "already exists" in error_str:
                print("! Column repository_path already exists in compact_jobs")
            else:
                # Try to verify the column exists
                try:
                    db.execute(text("SELECT repository_path FROM compact_jobs LIMIT 1"))
                    print("✓ Verified column exists in compact_jobs despite error")
                except:
                    print(f"✗ Column missing and add failed in compact_jobs: {e}")
                    raise e

        db.commit()
        print("✓ Migration 030 completed successfully")

    except Exception as e:
        print(f"✗ Migration 030 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 030"""
    print("Running downgrade for migration 030")
    try:
        db.execute(text("ALTER TABLE check_jobs DROP COLUMN repository_path"))
        db.execute(text("ALTER TABLE compact_jobs DROP COLUMN repository_path"))
        db.commit()
        print("✓ Successfully removed repository_path columns")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
