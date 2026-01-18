"""
Migration 051: Add analytics_enabled to users table

This migration adds the analytics_enabled field to the users table
to allow users to opt-out of Matomo analytics tracking.
"""

from sqlalchemy import text

def upgrade(db):
    """Add analytics_enabled to users table"""
    print("Running migration 051: Add analytics_enabled to users")

    try:
        # Check if column already exists
        result = db.execute(text("PRAGMA table_info(users)"))
        columns = {row[1] for row in result}

        if 'analytics_enabled' not in columns:
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN analytics_enabled BOOLEAN DEFAULT 1
            """))
            print("✓ Added analytics_enabled column to users")
        else:
            print("⊘ Column analytics_enabled already exists in users")

        db.commit()
        print("✓ Migration 051 completed successfully")

    except Exception as e:
        print(f"✗ Migration 051 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 051"""
    print("Running downgrade for migration 051")
    try:
        # SQLite doesn't support DROP COLUMN directly
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! The analytics_enabled column will remain in the users table.")
        db.commit()
        print("✓ Downgrade noted for migration 051")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
