"""
Migration 011: Add must_change_password to users table

This migration adds a must_change_password flag to enforce password changes
on first login or after password reset by admin.
"""

from sqlalchemy import text

def upgrade(connection):
    """Add must_change_password column to users table"""

    # Check if column exists
    result = connection.execute(text("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND name='users'
    """))

    row = result.fetchone()
    table_sql = row[0] if row else ""

    if 'must_change_password' not in table_sql:
        # Add the column
        connection.execute(text("""
            ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0
        """))
        print("  Added column: users.must_change_password")

        # Set must_change_password=1 for existing admin user with default password
        # This is a one-time update for security during migration
        connection.execute(text("""
            UPDATE users
            SET must_change_password = 1
            WHERE username = 'admin'
        """))
        print("  Updated existing admin user to require password change")
    else:
        print("  Skipped (exists): must_change_password column already exists")

    print("✓ Migration 011: Added must_change_password to users")

def downgrade(connection):
    """Remove must_change_password column from users table"""

    # SQLite doesn't support DROP COLUMN easily, would need table recreation
    # For now, we'll just set all values to 0 (no password change required)
    connection.execute(text("""
        UPDATE users SET must_change_password = 0
    """))

    print("✓ Migration 011 rolled back: Reset must_change_password to 0 for all users")
