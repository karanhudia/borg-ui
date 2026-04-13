"""
Regression tests: SSH identity key must be passed via BORG_RSH for prune,
compact, and check operations (issue #354).

Backups correctly injected -i <key> into BORG_RSH; the three maintenance
services did not, causing borg to fall back to password auth and triggering
IP bans on providers that block repeated failed login attempts.
"""

import base64
import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from cryptography.fernet import Fernet

from app.database.models import (
    CheckJob,
    CompactJob,
    PruneJob,
    Repository,
    SSHConnection,
    SSHKey,
)
from app.services.check_service import CheckService
from app.services.compact_service import CompactService
from app.services.prune_service import PruneService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_encrypted_key(secret_key: str) -> str:
    """Return an encrypted fake private key using the app's encryption scheme."""
    encryption_key = secret_key.encode()[:32]
    cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
    fake_pem = (
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        "fakekey\n"
        "-----END OPENSSH PRIVATE KEY-----\n"
    )
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


def _make_ssh_key(secret_key: str) -> MagicMock:
    key = MagicMock(spec=SSHKey)
    key.id = 42
    key.private_key = _make_encrypted_key(secret_key)
    return key


def _make_connection(ssh_key_id: int) -> MagicMock:
    conn = MagicMock(spec=SSHConnection)
    conn.id = 7
    conn.ssh_key_id = ssh_key_id
    return conn


def _mock_process(returncode=0):
    proc = AsyncMock()
    proc.returncode = returncode
    proc.pid = 12345
    proc.stdout = AsyncMock()
    proc.stdout.__aiter__ = AsyncMock(return_value=iter([]))
    proc.stderr = AsyncMock()
    proc.stderr.__aiter__ = AsyncMock(return_value=iter([]))
    proc.wait = AsyncMock(return_value=returncode)
    return proc


# ---------------------------------------------------------------------------
# Shared assertion
# ---------------------------------------------------------------------------


def assert_borg_rsh_has_identity(captured_env: dict):
    """Assert that BORG_RSH contains an -i flag pointing to a key file."""
    borg_rsh = captured_env.get("BORG_RSH", "")
    assert "-i" in borg_rsh, (
        f"BORG_RSH does not contain -i (identity) flag: {borg_rsh!r}\n"
        "SSH key was not passed to borg — this is the regression from issue #354."
    )


# ---------------------------------------------------------------------------
# PruneService
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPruneServiceSSHKey:
    """PruneService must inject the SSH identity key into BORG_RSH."""

    @pytest.fixture
    def service(self):
        with patch("app.services.prune_service.settings") as mock_settings:
            mock_settings.data_dir = tempfile.mkdtemp()
            mock_settings.secret_key = "testsecretkey1234567890123456789"
            yield PruneService()

    @pytest.mark.asyncio
    async def test_ssh_key_via_connection_id_injected_into_borg_rsh(self, service):
        """BORG_RSH must include -i <key> when repo has connection_id with ssh_key."""
        secret = "testsecretkey1234567890123456789"
        ssh_key = _make_ssh_key(secret)
        connection = _make_connection(ssh_key_id=ssh_key.id)
        repo = _make_repo(connection_id=connection.id)
        job = MagicMock(spec=PruneJob)
        job.id = 1
        job.status = "pending"
        job.max_duration = None

        captured_env = {}

        def mock_query(model):
            m = MagicMock()
            if model == PruneJob:
                m.filter.return_value.first.return_value = job
            elif model == Repository:
                m.filter.return_value.first.return_value = repo
            elif model == SSHConnection:
                m.filter.return_value.first.return_value = connection
            elif model == SSHKey:
                m.filter.return_value.first.return_value = ssh_key
            return m

        mock_db = MagicMock()
        mock_db.query.side_effect = mock_query

        proc = _mock_process(returncode=0)

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return proc

        with patch("app.services.prune_service.SessionLocal", return_value=mock_db):
            with patch(
                "app.services.prune_service.asyncio.create_subprocess_exec",
                side_effect=fake_exec,
            ):
                with patch("app.services.prune_service.settings") as mock_settings:
                    mock_settings.data_dir = tempfile.mkdtemp()
                    mock_settings.secret_key = secret
                    with patch("app.utils.ssh_utils.settings") as ssh_utils_settings:
                        ssh_utils_settings.secret_key = secret
                        await service.execute_prune(
                            job_id=1,
                            repository_id=1,
                            keep_hourly=0,
                            keep_daily=7,
                            keep_weekly=4,
                            keep_monthly=6,
                            keep_quarterly=0,
                            keep_yearly=1,
                        )

        assert_borg_rsh_has_identity(captured_env)

    @pytest.mark.asyncio
    async def test_no_ssh_key_borg_rsh_has_no_identity_flag(self, service):
        """BORG_RSH must NOT contain -i when repo has no SSH key (local repo)."""
        repo = _make_repo(connection_id=None, ssh_key_id=None, repository_type="local")
        job = MagicMock(spec=PruneJob)
        job.id = 1
        job.status = "pending"

        captured_env = {}

        def mock_query(model):
            m = MagicMock()
            if model == PruneJob:
                m.filter.return_value.first.return_value = job
            elif model == Repository:
                m.filter.return_value.first.return_value = repo
            elif model in (SSHConnection, SSHKey):
                m.filter.return_value.first.return_value = None
            return m

        mock_db = MagicMock()
        mock_db.query.side_effect = mock_query

        proc = _mock_process(returncode=0)

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return proc

        with patch("app.services.prune_service.SessionLocal", return_value=mock_db):
            with patch(
                "app.services.prune_service.asyncio.create_subprocess_exec",
                side_effect=fake_exec,
            ):
                with patch("app.services.prune_service.settings") as mock_settings:
                    mock_settings.data_dir = tempfile.mkdtemp()
                    mock_settings.secret_key = "testsecretkey1234567890123456789"
                    await service.execute_prune(
                        job_id=1,
                        repository_id=1,
                        keep_hourly=0,
                        keep_daily=7,
                        keep_weekly=4,
                        keep_monthly=6,
                        keep_quarterly=0,
                        keep_yearly=1,
                    )

        borg_rsh = captured_env.get("BORG_RSH", "")
        assert "-i" not in borg_rsh


# ---------------------------------------------------------------------------
# CompactService
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCompactServiceSSHKey:
    """CompactService must inject the SSH identity key into BORG_RSH."""

    @pytest.mark.asyncio
    async def test_ssh_key_via_connection_id_injected_into_borg_rsh(self):
        """BORG_RSH must include -i <key> when repo has connection_id with ssh_key."""
        secret = "testsecretkey1234567890123456789"
        ssh_key = _make_ssh_key(secret)
        connection = _make_connection(ssh_key_id=ssh_key.id)
        repo = _make_repo(connection_id=connection.id)
        job = MagicMock(spec=CompactJob)
        job.id = 1
        job.status = "pending"
        job.process_pid = None
        job.process_start_time = None

        captured_env = {}

        def mock_query(model):
            m = MagicMock()
            if model == CompactJob:
                m.filter.return_value.first.return_value = job
            elif model == Repository:
                m.filter.return_value.first.return_value = repo
            elif model == SSHConnection:
                m.filter.return_value.first.return_value = connection
            elif model == SSHKey:
                m.filter.return_value.first.return_value = ssh_key
            return m

        mock_db = MagicMock()
        mock_db.query.side_effect = mock_query

        proc = _mock_process(returncode=0)

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return proc

        with patch("app.services.compact_service.SessionLocal", return_value=mock_db):
            with patch(
                "app.services.compact_service.asyncio.create_subprocess_exec",
                side_effect=fake_exec,
            ):
                with patch("app.services.compact_service.settings") as mock_settings:
                    mock_settings.data_dir = tempfile.mkdtemp()
                    mock_settings.secret_key = secret
                    with patch("app.utils.ssh_utils.settings") as ssh_utils_settings:
                        ssh_utils_settings.secret_key = secret
                        service = CompactService()
                        await service.execute_compact(job_id=1, repository_id=1)

        assert_borg_rsh_has_identity(captured_env)

    @pytest.mark.asyncio
    async def test_legacy_ssh_key_id_injected_into_borg_rsh(self):
        """BORG_RSH must include -i <key> for legacy repos using ssh_key_id directly."""
        secret = "testsecretkey1234567890123456789"
        ssh_key = _make_ssh_key(secret)
        repo = _make_repo(
            connection_id=None, ssh_key_id=ssh_key.id, repository_type="ssh"
        )

        captured_env = {}
        job = MagicMock(spec=CompactJob)
        job.id = 1
        job.status = "pending"
        job.process_pid = None
        job.process_start_time = None

        def mock_query(model):
            m = MagicMock()
            if model == CompactJob:
                m.filter.return_value.first.return_value = job
            elif model == Repository:
                m.filter.return_value.first.return_value = repo
            elif model == SSHKey:
                m.filter.return_value.first.return_value = ssh_key
            return m

        mock_db = MagicMock()
        mock_db.query.side_effect = mock_query

        proc = _mock_process(returncode=0)

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return proc

        with patch("app.services.compact_service.SessionLocal", return_value=mock_db):
            with patch(
                "app.services.compact_service.asyncio.create_subprocess_exec",
                side_effect=fake_exec,
            ):
                with patch("app.services.compact_service.settings") as mock_settings:
                    mock_settings.data_dir = tempfile.mkdtemp()
                    mock_settings.secret_key = secret
                    with patch("app.utils.ssh_utils.settings") as ssh_utils_settings:
                        ssh_utils_settings.secret_key = secret
                        service = CompactService()
                        await service.execute_compact(job_id=1, repository_id=1)

        assert_borg_rsh_has_identity(captured_env)


# ---------------------------------------------------------------------------
# CheckService
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckServiceSSHKey:
    """CheckService must inject the SSH identity key into BORG_RSH."""

    @pytest.mark.asyncio
    async def test_ssh_key_via_connection_id_injected_into_borg_rsh(self):
        """BORG_RSH must include -i <key> when repo has connection_id with ssh_key."""
        secret = "testsecretkey1234567890123456789"
        ssh_key = _make_ssh_key(secret)
        connection = _make_connection(ssh_key_id=ssh_key.id)
        repo = _make_repo(connection_id=connection.id)
        job = MagicMock(spec=CheckJob)
        job.id = 1
        job.status = "pending"
        job.max_duration = None
        job.process_pid = None
        job.process_start_time = None

        captured_env = {}

        def mock_query(model):
            m = MagicMock()
            if model == CheckJob:
                m.filter.return_value.first.return_value = job
            elif model == Repository:
                m.filter.return_value.first.return_value = repo
            elif model == SSHConnection:
                m.filter.return_value.first.return_value = connection
            elif model == SSHKey:
                m.filter.return_value.first.return_value = ssh_key
            return m

        mock_db = MagicMock()
        mock_db.query.side_effect = mock_query

        proc = _mock_process(returncode=0)

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return proc

        with patch("app.services.check_service.SessionLocal", return_value=mock_db):
            with patch(
                "app.services.check_service.asyncio.create_subprocess_exec",
                side_effect=fake_exec,
            ):
                with patch("app.services.check_service.settings") as mock_settings:
                    mock_settings.data_dir = tempfile.mkdtemp()
                    mock_settings.secret_key = secret
                    with patch("app.utils.ssh_utils.settings") as ssh_utils_settings:
                        ssh_utils_settings.secret_key = secret
                        with patch("app.services.check_service.NotificationService"):
                            service = CheckService()
                            await service.execute_check(job_id=1, repository_id=1)

        assert_borg_rsh_has_identity(captured_env)

    @pytest.mark.asyncio
    async def test_legacy_ssh_key_id_injected_into_borg_rsh(self):
        """BORG_RSH must include -i <key> for legacy repos using ssh_key_id directly."""
        secret = "testsecretkey1234567890123456789"
        ssh_key = _make_ssh_key(secret)
        repo = _make_repo(
            connection_id=None, ssh_key_id=ssh_key.id, repository_type="ssh"
        )
        job = MagicMock(spec=CheckJob)
        job.id = 1
        job.status = "pending"
        job.max_duration = None
        job.process_pid = None
        job.process_start_time = None

        captured_env = {}

        def mock_query(model):
            m = MagicMock()
            if model == CheckJob:
                m.filter.return_value.first.return_value = job
            elif model == Repository:
                m.filter.return_value.first.return_value = repo
            elif model == SSHKey:
                m.filter.return_value.first.return_value = ssh_key
            return m

        mock_db = MagicMock()
        mock_db.query.side_effect = mock_query

        proc = _mock_process(returncode=0)

        async def fake_exec(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return proc

        with patch("app.services.check_service.SessionLocal", return_value=mock_db):
            with patch(
                "app.services.check_service.asyncio.create_subprocess_exec",
                side_effect=fake_exec,
            ):
                with patch("app.services.check_service.settings") as mock_settings:
                    mock_settings.data_dir = tempfile.mkdtemp()
                    mock_settings.secret_key = secret
                    with patch("app.utils.ssh_utils.settings") as ssh_utils_settings:
                        ssh_utils_settings.secret_key = secret
                        with patch("app.services.check_service.NotificationService"):
                            service = CheckService()
                            await service.execute_check(job_id=1, repository_id=1)

        assert_borg_rsh_has_identity(captured_env)
