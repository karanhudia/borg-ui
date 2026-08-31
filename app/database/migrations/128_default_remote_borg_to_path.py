"""Use the remote PATH for SSH connections without a custom Borg binary."""

from sqlalchemy import text


def upgrade(connection):
    """Replace the legacy implicit Borg path with the PATH-resolved command."""
    columns = {
        row[1] for row in connection.execute(text("PRAGMA table_info(ssh_connections)"))
    }
    if "borg_binary_path" in columns:
        connection.execute(
            text(
                "UPDATE ssh_connections SET borg_binary_path = 'borg' "
                "WHERE borg_binary_path = '/usr/bin/borg'"
            )
        )


def downgrade(connection):
    print("✓ Downgrade skipped for migration 128 (data normalization)")
