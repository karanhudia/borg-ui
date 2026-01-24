"""
Migration 057: Add Script Parameters Support

This migration adds parameter support to scripts and repository_scripts:
- Script.parameters: JSON array of parameter definitions
- RepositoryScript.parameter_values: JSON dict of parameter values (encrypted for password-type params)

Enables script parametrization with support for text and password-type parameters.
"""

from sqlalchemy import text

def upgrade(db):
    """Add script parameter columns"""
    print("Running migration 057: Add Script Parameters Support")

    try:
        # Check if columns already exist
        cursor = db.execute(text("PRAGMA table_info(scripts)"))
        scripts_columns = [row[1] for row in cursor.fetchall()]

        cursor = db.execute(text("PRAGMA table_info(repository_scripts)"))
        repository_scripts_columns = [row[1] for row in cursor.fetchall()]

        # Add parameters column to scripts table
        if 'parameters' not in scripts_columns:
            print("Adding parameters column to scripts table...")
            db.execute(text("""
                ALTER TABLE scripts ADD COLUMN parameters TEXT
            """))
            print("✓ Added parameters column")
        else:
            print("⊘ parameters column already exists in scripts table")

        # Add parameter_values column to repository_scripts table
        if 'parameter_values' not in repository_scripts_columns:
            print("Adding parameter_values column to repository_scripts table...")
            db.execute(text("""
                ALTER TABLE repository_scripts ADD COLUMN parameter_values TEXT
            """))
            print("✓ Added parameter_values column")
        else:
            print("⊘ parameter_values column already exists in repository_scripts table")

        db.commit()
        print("✓ Migration 057 completed successfully")

    except Exception as e:
        print(f"✗ Migration 057 failed: {str(e)}")
        db.rollback()
        raise


def downgrade(db):
    """Remove script parameter columns"""
    print("Running downgrade for migration 057: Remove Script Parameters Support")

    try:
        # SQLite doesn't support DROP COLUMN directly in older versions
        # We'll need to recreate the tables without these columns if needed
        print("⚠ Downgrade not implemented - SQLite limitations")
        print("  To remove these columns, you would need to recreate the tables")
        
    except Exception as e:
        print(f"✗ Downgrade 057 failed: {str(e)}")
        db.rollback()
        raise
