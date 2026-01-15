"""Add use_new_wizard field to system_settings for beta feature toggle"""

from sqlalchemy import text


def upgrade(connection):
    """Add use_new_wizard column to system_settings table"""
    # Check if column already exists (SQLite compatible)
    result = connection.execute(
        text("PRAGMA table_info(system_settings)")
    ).fetchall()

    column_names = [row[1] for row in result]

    if 'use_new_wizard' not in column_names:
        # Add use_new_wizard column (default false for stable)
        connection.execute(text(
            "ALTER TABLE system_settings ADD COLUMN use_new_wizard BOOLEAN DEFAULT 0 NOT NULL"
        ))

        print("✓ Added use_new_wizard column to system_settings table")
    else:
        print("✓ use_new_wizard column already exists in system_settings table")


def downgrade(connection):
    """Remove use_new_wizard column from system_settings table"""
    # SQLite doesn't support DROP COLUMN easily
    # For now, just acknowledge it can't be removed
    print("✓ Downgrade skipped - SQLite doesn't support DROP COLUMN")
