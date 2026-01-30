"""
Migration 059: Add use_sftp_mode to SSH connections

Adds use_sftp_mode column to ssh_connections table to control whether
ssh-copy-id uses SFTP mode (-s flag) during key deployment.

Background:
- SFTP mode is required by some servers (Hetzner Storage Box)
- SFTP mode breaks other servers (Synology NAS, older SSH servers)
- This flag allows per-connection configuration

Default: True (maintains current behavior for backward compatibility)
Users can disable for Synology NAS and other systems that don't support SFTP mode.
"""

from sqlalchemy import text


def upgrade(db):
    """Add use_sftp_mode column to SSH connections"""
    print("Running migration 059: Add use_sftp_mode to SSH connections")

    try:
        # Add use_sftp_mode column (default True for backward compatibility)
        db.execute(text("""
            ALTER TABLE ssh_connections
            ADD COLUMN use_sftp_mode BOOLEAN NOT NULL DEFAULT TRUE
        """))
        print("  ✓ Added use_sftp_mode column (default: TRUE)")

        db.commit()
        print("✓ Migration 059 completed successfully")

    except Exception as e:
        print(f"✗ Migration 059 failed: {e}")
        db.rollback()
        raise


def downgrade(db):
    """Remove use_sftp_mode column from SSH connections"""
    print("Running downgrade for migration 059")

    try:
        db.execute(text("""
            ALTER TABLE ssh_connections
            DROP COLUMN IF EXISTS use_sftp_mode
        """))
        print("  ✓ Removed use_sftp_mode column")

        db.commit()
        print("✓ Downgrade for migration 059 completed")

    except Exception as e:
        print(f"✗ Downgrade failed: {e}")
        db.rollback()
        raise
