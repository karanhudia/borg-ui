"""
Migration 052: Add analytics_consent_given to users table

This migration adds the analytics_consent_given field to track whether
the user has seen and responded to the analytics consent banner.
Changes analytics from opt-out to opt-in model.
"""

from sqlalchemy import text

def upgrade(db):
    """Add analytics_consent_given to users table"""
    print("Running migration 052: Add analytics_consent_given to users")

    try:
        # Check if column already exists
        result = db.execute(text("PRAGMA table_info(users)"))
        columns = {row[1] for row in result}

        if 'analytics_consent_given' not in columns:
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN analytics_consent_given BOOLEAN DEFAULT 0
            """))
            print("✓ Added analytics_consent_given column to users")
        else:
            print("⊘ Column analytics_consent_given already exists in users")

        db.commit()
        print("✓ Migration 052 completed successfully")

    except Exception as e:
        print(f"✗ Migration 052 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """Downgrade migration 052"""
    print("Running downgrade for migration 052")
    try:
        print("! Note: SQLite doesn't support DROP COLUMN. Manual intervention required if needed.")
        print("! The analytics_consent_given column will remain in the users table.")
        db.commit()
        print("✓ Downgrade noted for migration 052")
    except Exception as e:
        print(f"! Error during downgrade: {e}")
        db.rollback()
        raise
