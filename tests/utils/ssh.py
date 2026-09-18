"""SSH rows a test can point a repository or a connection at.

The shared test database enforces foreign keys the way production does, so a
`connection_id` or `ssh_key_id` has to name a row that exists.
"""

from app.database.models import SSHConnection, SSHKey


def ssh_key(db, *, name: str = "test-key", **fields) -> SSHKey:
    key = SSHKey(name=name, public_key="ssh-ed25519 AAAA", private_key="", **fields)
    db.add(key)
    db.flush()
    return key


def ssh_connection(
    db, *, host: str = "example.com", username: str = "borg", port: int = 22, **fields
) -> SSHConnection:
    connection = SSHConnection(host=host, username=username, port=port, **fields)
    db.add(connection)
    db.flush()
    return connection
