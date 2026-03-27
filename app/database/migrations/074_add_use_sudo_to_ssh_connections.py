"""Add use_sudo boolean column to ssh_connections table

When enabled, borg commands executed on remote hosts via SSH are prefixed
with sudo, allowing the SSH user to read directories it does not own.
Requires the SSH user to have passwordless sudo on the remote host.
"""
from sqlalchemy import text


def upgrade(connection):
    # Idempotency guard
    cols = [row[1] for row in connection.execute(text("PRAGMA table_info(ssh_connections)")).fetchall()]
    if "use_sudo" in cols:
        print("✓ use_sudo column already exists in ssh_connections — skipping migration 074")
        return
    connection.execute(text("ALTER TABLE ssh_connections ADD COLUMN use_sudo BOOLEAN NOT NULL DEFAULT 0"))
    print("✓ Added use_sudo column to ssh_connections")


def downgrade(connection):
    print("✓ Downgrade skipped — SQLite does not support DROP COLUMN on older versions")
