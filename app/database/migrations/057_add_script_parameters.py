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
        # Check SQLite version for DROP COLUMN support (added in SQLite 3.35.0)
        cursor = db.execute(text("SELECT sqlite_version()"))
        sqlite_version = cursor.fetchone()[0]
        major, minor, patch = map(int, sqlite_version.split('.'))

        if (major, minor) >= (3, 35):
            # SQLite 3.35+ supports DROP COLUMN
            print("Dropping parameters column from scripts table...")
            db.execute(text("ALTER TABLE scripts DROP COLUMN parameters"))
            print("✓ Dropped parameters column")

            print("Dropping parameter_values column from repository_scripts table...")
            db.execute(text("ALTER TABLE repository_scripts DROP COLUMN parameter_values"))
            print("✓ Dropped parameter_values column")

            db.commit()
            print("✓ Downgrade 057 completed successfully")
        else:
            print(f"⚠ SQLite version {sqlite_version} does not support DROP COLUMN")
            print("  Columns will remain in tables but are safe to ignore")
            print("  To fully remove: upgrade to SQLite 3.35+ or manually recreate tables")

    except Exception as e:
        print(f"✗ Downgrade 057 failed: {str(e)}")
        db.rollback()
        raise
