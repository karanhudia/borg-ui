"""
Migration 029: Add Continue On Error to Repository Scripts

This migration adds the continue_on_error column to repository_scripts table
with a default value of True (1).
"""

from sqlalchemy import text

def upgrade(db):
    """Refactor continue_on_error column"""
    print("Running migration 029: Add Continue On Error to Repository Scripts")

    try:
        # 1. Ensure repository_scripts has continue_on_error with default True
        # We try to add it. If it fails due to duplicate, we ignore.
        try:
            db.execute(text("ALTER TABLE repository_scripts ADD COLUMN continue_on_error BOOLEAN DEFAULT 1"))
            print("✓ Added continue_on_error to repository_scripts table")
        except Exception as e:
            error_str = str(e).lower()
            if "duplicate column" in error_str or "already exists" in error_str:
                print("! Column continue_on_error already exists in repository_scripts")
            else:
                # Try to verify the column exists
                try:
                    db.execute(text("SELECT continue_on_error FROM repository_scripts LIMIT 1"))
                    print("✓ Verified column exists despite error")
                except:
                    print(f"✗ Column missing and add failed: {e}")
                    raise e
        
        # Ensure values are correct (Default 1 for NULL values)
        db.execute(text("UPDATE repository_scripts SET continue_on_error = 1 WHERE continue_on_error IS NULL"))
        print("✓ Updated existing repository_scripts entries to default continue_on_error=True")

        db.commit()
        print("✓ Migration 029 completed successfully")

    except Exception as e:
        print(f"✗ Migration 029 failed: {e}")
        db.rollback()
        raise

def downgrade(db):
    """No-op for this refactor mainly"""
    print("Running downgrade for migration 029 - No action taken")
