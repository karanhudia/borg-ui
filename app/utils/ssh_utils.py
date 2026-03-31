"""Shared SSH key resolution for borg repository operations."""
import base64
import os
import tempfile
from typing import Optional

import structlog
from cryptography.fernet import Fernet

from app.config import settings
from app.database.models import SSHConnection, SSHKey

logger = structlog.get_logger()


def resolve_repo_ssh_key_file(repository, db) -> Optional[str]:
    """Decrypt and write the SSH private key for a repository to a temporary file.

    Supports both the new connection_id path and the legacy ssh_key_id path.

    Args:
        repository: Repository model instance (must have connection_id,
                    repository_type, and ssh_key_id attributes).
        db: SQLAlchemy database session.

    Returns:
        Path to a temporary file containing the decrypted private key
        (permissions 0o600), or None if no SSH key is configured.
        The caller is responsible for deleting the file via os.unlink().
    """
    ssh_key = None

    if repository.connection_id:
        connection = db.query(SSHConnection).filter(
            SSHConnection.id == repository.connection_id
        ).first()
        if connection and connection.ssh_key_id:
            ssh_key = db.query(SSHKey).filter(SSHKey.id == connection.ssh_key_id).first()
    elif getattr(repository, "repository_type", None) == "ssh" and getattr(repository, "ssh_key_id", None):
        ssh_key = db.query(SSHKey).filter(SSHKey.id == repository.ssh_key_id).first()

    if not ssh_key:
        return None

    return write_ssh_key_to_tempfile(ssh_key)


def write_ssh_key_to_tempfile(ssh_key) -> str:
    """Decrypt an SSHKey and write it to a temporary file with 0o600 permissions.

    Args:
        ssh_key: SSHKey model instance with an encrypted ``private_key`` field.

    Returns:
        Path to the temporary file. The caller must delete it via os.unlink()
        after use.
    """
    encryption_key = settings.secret_key.encode()[:32]
    cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
    private_key = cipher.decrypt(ssh_key.private_key.encode()).decode()

    if not private_key.endswith("\n"):
        private_key += "\n"

    fd, temp_key_file = tempfile.mkstemp(suffix=".key", text=True)
    try:
        os.chmod(temp_key_file, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(private_key)
    except Exception:
        os.close(fd)
        raise

    return temp_key_file
