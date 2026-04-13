"""
Unit tests for app.utils.ssh_utils.resolve_repo_ssh_key_file and
app.utils.ssh_utils.write_ssh_key_to_tempfile.

Tests cover:
 - connection_id path (new-style repos)
 - legacy ssh_key_id path (old-style repos)
 - no SSH key configured -> returns None
 - connection exists but has no ssh_key_id -> returns None
 - decrypted key gets trailing newline appended if missing
 - temp file has 0o600 permissions
"""

import base64
import os
import pytest
from unittest.mock import MagicMock, patch
from cryptography.fernet import Fernet

from app.database.models import Repository, SSHConnection, SSHKey


# ---------------------------------------------------------------------------
# Helpers (mirror the style used in test_ssh_key_in_maintenance_services.py)
# ---------------------------------------------------------------------------


def _make_encrypted_key(secret_key: str, trailing_newline: bool = True) -> str:
    """Return an encrypted fake private key using the app's encryption scheme."""
    encryption_key = secret_key.encode()[:32]
    cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
    fake_pem = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "fakekey\n"
        "-----END OPENSSH PRIVATE KEY-----"
    )
    if trailing_newline:
        fake_pem += "\n"
    return cipher.encrypt(fake_pem.encode()).decode()


def _make_repo(connection_id=None, ssh_key_id=None, repository_type="ssh"):
    repo = MagicMock(spec=Repository)
    repo.id = 1
    repo.path = "ssh://user@host:23/./borg-repo"
    repo.passphrase = None
    repo.remote_path = None
    repo.repository_type = repository_type
    repo.connection_id = connection_id
    repo.ssh_key_id = ssh_key_id
    return repo


def _make_ssh_key(secret_key: str, trailing_newline: bool = True) -> MagicMock:
    key = MagicMock(spec=SSHKey)
    key.id = 42
    key.private_key = _make_encrypted_key(secret_key, trailing_newline)
    return key


def _make_connection(ssh_key_id=None) -> MagicMock:
    conn = MagicMock(spec=SSHConnection)
    conn.id = 7
    conn.ssh_key_id = ssh_key_id
    return conn


# ---------------------------------------------------------------------------
# Tests for resolve_repo_ssh_key_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveRepoSshKeyFile:
    """Tests for the shared resolve_repo_ssh_key_file utility function."""

    SECRET = "testsecretkey1234567890123456789"

    def _make_db(self, connection=None, ssh_key=None):
        """Build a mock db that returns the given objects for SSHConnection/SSHKey queries."""
        mock_db = MagicMock()

        def mock_query(model):
            m = MagicMock()
            if model == SSHConnection:
                m.filter.return_value.first.return_value = connection
            elif model == SSHKey:
                m.filter.return_value.first.return_value = ssh_key
            return m

        mock_db.query.side_effect = mock_query
        return mock_db

    def test_connection_id_path_returns_temp_file(self):
        """connection_id -> SSHConnection -> SSHKey -> temp file returned."""
        from app.utils.ssh_utils import resolve_repo_ssh_key_file

        ssh_key = _make_ssh_key(self.SECRET)
        connection = _make_connection(ssh_key_id=ssh_key.id)
        repo = _make_repo(connection_id=connection.id)
        db = self._make_db(connection=connection, ssh_key=ssh_key)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = resolve_repo_ssh_key_file(repo, db)

        try:
            assert result is not None
            assert os.path.exists(result)
        finally:
            if result and os.path.exists(result):
                os.unlink(result)

    def test_legacy_ssh_key_id_path_returns_temp_file(self):
        """legacy ssh_key_id (no connection_id, repository_type='ssh') -> temp file returned."""
        from app.utils.ssh_utils import resolve_repo_ssh_key_file

        ssh_key = _make_ssh_key(self.SECRET)
        repo = _make_repo(
            connection_id=None, ssh_key_id=ssh_key.id, repository_type="ssh"
        )
        db = self._make_db(ssh_key=ssh_key)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = resolve_repo_ssh_key_file(repo, db)

        try:
            assert result is not None
            assert os.path.exists(result)
        finally:
            if result and os.path.exists(result):
                os.unlink(result)

    def test_no_key_configured_returns_none(self):
        """Repo with no connection_id and no ssh_key_id -> returns None."""
        from app.utils.ssh_utils import resolve_repo_ssh_key_file

        repo = _make_repo(connection_id=None, ssh_key_id=None, repository_type="local")
        db = self._make_db()

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = resolve_repo_ssh_key_file(repo, db)

        assert result is None

    def test_connection_without_ssh_key_id_returns_none(self):
        """connection_id present but connection has no ssh_key_id -> returns None."""
        from app.utils.ssh_utils import resolve_repo_ssh_key_file

        connection = _make_connection(ssh_key_id=None)
        repo = _make_repo(connection_id=connection.id)
        db = self._make_db(connection=connection)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = resolve_repo_ssh_key_file(repo, db)

        assert result is None

    def test_decrypted_key_gets_trailing_newline(self):
        """If the decrypted key lacks a trailing newline, one is appended."""
        from app.utils.ssh_utils import resolve_repo_ssh_key_file

        # Key stored without trailing newline
        ssh_key = _make_ssh_key(self.SECRET, trailing_newline=False)
        repo = _make_repo(
            connection_id=None, ssh_key_id=ssh_key.id, repository_type="ssh"
        )
        db = self._make_db(ssh_key=ssh_key)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = resolve_repo_ssh_key_file(repo, db)

        try:
            assert result is not None
            with open(result, "r") as f:
                content = f.read()
            assert content.endswith("\n"), (
                "Trailing newline was not appended to the key file"
            )
        finally:
            if result and os.path.exists(result):
                os.unlink(result)

    def test_temp_file_has_0o600_permissions(self):
        """The temp key file must have 0o600 permissions."""
        from app.utils.ssh_utils import resolve_repo_ssh_key_file

        ssh_key = _make_ssh_key(self.SECRET)
        repo = _make_repo(
            connection_id=None, ssh_key_id=ssh_key.id, repository_type="ssh"
        )
        db = self._make_db(ssh_key=ssh_key)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = resolve_repo_ssh_key_file(repo, db)

        try:
            assert result is not None
            mode = oct(os.stat(result).st_mode & 0o777)
            assert mode == oct(0o600), f"Expected 0o600 permissions but got {mode}"
        finally:
            if result and os.path.exists(result):
                os.unlink(result)


# ---------------------------------------------------------------------------
# Tests for write_ssh_key_to_tempfile
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWriteSshKeyToTempfile:
    """Tests for the write_ssh_key_to_tempfile utility function."""

    SECRET = "testsecretkey1234567890123456789"

    def test_decrypts_and_writes_key(self):
        """Decrypts the SSHKey and writes to a readable temp file."""
        from app.utils.ssh_utils import write_ssh_key_to_tempfile

        ssh_key = _make_ssh_key(self.SECRET)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = write_ssh_key_to_tempfile(ssh_key)

        try:
            assert result is not None
            assert os.path.exists(result)
            with open(result) as f:
                content = f.read()
            assert "OPENSSH PRIVATE KEY" in content
        finally:
            if result and os.path.exists(result):
                os.unlink(result)

    def test_temp_file_has_0o600_permissions(self):
        """The written temp file must have 0o600 permissions."""
        from app.utils.ssh_utils import write_ssh_key_to_tempfile

        ssh_key = _make_ssh_key(self.SECRET)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = write_ssh_key_to_tempfile(ssh_key)

        try:
            mode = oct(os.stat(result).st_mode & 0o777)
            assert mode == oct(0o600)
        finally:
            if result and os.path.exists(result):
                os.unlink(result)

    def test_trailing_newline_appended_if_missing(self):
        """If the decrypted key has no trailing newline, one must be appended."""
        from app.utils.ssh_utils import write_ssh_key_to_tempfile

        ssh_key = _make_ssh_key(self.SECRET, trailing_newline=False)

        with patch("app.utils.ssh_utils.settings") as mock_settings:
            mock_settings.secret_key = self.SECRET
            result = write_ssh_key_to_tempfile(ssh_key)

        try:
            with open(result) as f:
                content = f.read()
            assert content.endswith("\n")
        finally:
            if result and os.path.exists(result):
                os.unlink(result)
