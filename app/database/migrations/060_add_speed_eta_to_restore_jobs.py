"""
Migration 060: Add speed and ETA tracking to restore jobs

Adds restore speed and ETA fields to restore_jobs table to match backup jobs.
This allows showing real-time restore speed (MB/s) and estimated time remaining.

Fields added:
- original_size: Total bytes to restore (from archive or selected paths)
- restored_size: Bytes restored so far (from borg progress)
- restore_speed: Current restore speed in MB/s (30-second moving average)
- estimated_time_remaining: Estimated seconds remaining

These fields enable the same progress display as backup jobs.
"""

from sqlalchemy import text


def upgrade(db):
    """Add speed and ETA tracking columns to restore jobs"""
    print("Running migration 060: Add speed and ETA tracking to restore jobs")

    try:
        # Add original_size column (total bytes to restore)
        db.execute(text("""
            ALTER TABLE restore_jobs
            ADD COLUMN original_size BIGINT DEFAULT 0
        """))
        print("  ✓ Added original_size column")

        # Add restored_size column (bytes restored so far)
        db.execute(text("""
            ALTER TABLE restore_jobs
            ADD COLUMN restored_size BIGINT DEFAULT 0
        """))
        print("  ✓ Added restored_size column")

        # Add restore_speed column (MB/s)
        db.execute(text("""
            ALTER TABLE restore_jobs
            ADD COLUMN restore_speed FLOAT DEFAULT 0.0
        """))
        print("  ✓ Added restore_speed column")

        # Add estimated_time_remaining column (seconds)
        db.execute(text("""
            ALTER TABLE restore_jobs
            ADD COLUMN estimated_time_remaining INTEGER DEFAULT 0
        """))
        print("  ✓ Added estimated_time_remaining column")

        db.commit()
        print("✓ Migration 060 completed successfully")

    except Exception as e:
        print(f"✗ Migration 060 failed: {e}")
        db.rollback()
        raise


def downgrade(db):
    """Remove speed and ETA tracking columns from restore jobs"""
    print("Running downgrade for migration 060")

    try:
        db.execute(text("""
            ALTER TABLE restore_jobs
            DROP COLUMN IF EXISTS original_size,
            DROP COLUMN IF EXISTS restored_size,
            DROP COLUMN IF EXISTS restore_speed,
            DROP COLUMN IF EXISTS estimated_time_remaining
        """))
        print("  ✓ Removed speed and ETA tracking columns")

        db.commit()
        print("✓ Downgrade for migration 060 completed")

    except Exception as e:
        print(f"✗ Downgrade failed: {e}")
        db.rollback()
        raise
