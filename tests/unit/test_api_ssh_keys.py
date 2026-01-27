"""
Unit tests for SSH keys API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


@pytest.mark.unit
class TestSSHKeysEndpoints:
    """Test SSH keys API endpoints"""

    def test_list_ssh_keys_empty(self, test_client: TestClient, admin_headers):
        """Test listing SSH keys when none exist"""
        response = test_client.get("/api/ssh-keys/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_ssh_keys_unauthorized(self, test_client: TestClient):
        """Test listing SSH keys without authentication"""
        response = test_client.get("/api/ssh-keys/")

        assert response.status_code in [401, 403, 404]

    def test_generate_ssh_key_missing_fields(self, test_client: TestClient, admin_headers):
        """Test generating SSH key with missing fields"""
        response = test_client.post(
            "/api/ssh-keys/generate",
            json={},
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_generate_ssh_key_invalid_type(self, test_client: TestClient, admin_headers):
        """Test generating SSH key with invalid key type"""
        response = test_client.post(
            "/api/ssh-keys/generate",
            json={
                "name": "test-key",
                "key_type": "invalid-type"
            },
            headers=admin_headers
        )

        assert response.status_code in [400, 403, 422]  # May return forbidden

    def test_upload_ssh_key_missing_fields(self, test_client: TestClient, admin_headers):
        """Test uploading SSH key with missing fields"""
        response = test_client.post(
            "/api/ssh-keys/upload",
            json={},
            headers=admin_headers
        )

        assert response.status_code in [405, 422]  # Validation error or method not allowed

    def test_get_ssh_key_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting non-existent SSH key"""
        response = test_client.get("/api/ssh-keys/nonexistent-key", headers=admin_headers)

        assert response.status_code in [404, 422]

    def test_delete_ssh_key_nonexistent(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent SSH key"""
        response = test_client.delete("/api/ssh-keys/nonexistent-key", headers=admin_headers)

        assert response.status_code in [404, 422]

    def test_get_ssh_public_key_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting public key for non-existent SSH key"""
        response = test_client.get(
            "/api/ssh-keys/nonexistent-key/public",
            headers=admin_headers
        )

        assert response.status_code in [404, 422]

    def test_test_ssh_connection_invalid(self, test_client: TestClient, admin_headers):
        """Test SSH connection with invalid parameters"""
        response = test_client.post(
            "/api/ssh-keys/test-connection",
            json={
                "host": "invalid-host",
                "key_name": "nonexistent-key"
            },
            headers=admin_headers
        )

        assert response.status_code in [404, 405]  # Not found or not implemented

    def test_import_ssh_key_missing_path(self, test_client: TestClient, admin_headers):
        """Test importing SSH key without providing private key path"""
        response = test_client.post(
            "/api/ssh-keys/import",
            json={
                "name": "imported-key"
            },
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_import_ssh_key_nonexistent_file(self, test_client: TestClient, admin_headers):
        """Test importing SSH key with non-existent file path"""
        response = test_client.post(
            "/api/ssh-keys/import",
            json={
                "name": "imported-key",
                "private_key_path": "/nonexistent/path/id_rsa"
            },
            headers=admin_headers
        )

        # Should return 404 or 400 depending on implementation
        assert response.status_code in [400, 404, 500]

    def test_test_existing_connection_nonexistent(self, test_client: TestClient, admin_headers):
        """Test testing non-existent connection"""
        response = test_client.post(
            "/api/ssh-keys/connections/999999/test",
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_test_existing_connection_unauthorized(self, test_client: TestClient):
        """Test testing connection without authentication"""
        response = test_client.post("/api/ssh-keys/connections/1/test")

        assert response.status_code in [401, 403]


@pytest.mark.unit
class TestRunDfCommand:
    """Test _run_df_command helper function"""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock SSH connection"""
        conn = MagicMock()
        conn.id = 1
        conn.host = "test-server.com"
        conn.username = "testuser"
        conn.port = 22
        conn.default_path = "/home"
        return conn

    @pytest.mark.asyncio
    async def test_english_df_output(self, mock_connection):
        """Test parsing standard English df output"""
        from app.api.ssh_keys import _run_df_command

        english_output = """Filesystem     1K-blocks      Used Available Use% Mounted on
/dev/sda1      102400000  51200000  51200000  50% /home"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(english_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(english_output.encode(), b"")):
                mock_process.communicate = AsyncMock(return_value=(english_output.encode(), b""))
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=True)

        assert result is not None
        assert result["total"] == 102400000 * 1024
        assert result["used"] == 51200000 * 1024
        assert result["available"] == 51200000 * 1024
        assert result["percent_used"] == 50.0
        assert result["filesystem"] == "/dev/sda1"
        assert result["mount_point"] == "/home"

    @pytest.mark.asyncio
    async def test_german_df_output(self, mock_connection):
        """Test parsing German df output (Dateisystem instead of Filesystem)"""
        from app.api.ssh_keys import _run_df_command

        german_output = """Dateisystem    1K-Blöcke   Benutzt Verfügbar Verw% Eingehängt auf
/dev/sda1      102400000  81920000  20480000  80% /home"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(german_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(german_output.encode(), b"")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=False)

        assert result is not None
        assert result["total"] == 102400000 * 1024
        assert result["used"] == 81920000 * 1024
        assert result["available"] == 20480000 * 1024
        assert result["percent_used"] == 80.0

    @pytest.mark.asyncio
    async def test_hetzner_storage_box_output(self, mock_connection):
        """Test parsing Hetzner Storage Box df output"""
        from app.api.ssh_keys import _run_df_command

        # Hetzner Storage Box typically shows large numbers for TB storage
        hetzner_output = """Filesystem           1K-blocks       Used  Available Use% Mounted on
u331525-sub1        10485760000 8665169920 1820590080  83% /home"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(hetzner_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(hetzner_output.encode(), b"")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=False)

        assert result is not None
        assert result["percent_used"] == 83.0
        # ~10TB total
        assert result["total"] == 10485760000 * 1024

    @pytest.mark.asyncio
    async def test_command_failure_returns_none(self, mock_connection):
        """Test that command failure returns None"""
        from app.api.ssh_keys import _run_df_command

        mock_process = AsyncMock()
        mock_process.returncode = 1  # Command failed
        mock_process.communicate = AsyncMock(return_value=(b"", b"Command not found"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"", b"Command not found")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_output_returns_none(self, mock_connection):
        """Test that empty output returns None"""
        from app.api.ssh_keys import _run_df_command

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"", b"")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_header_only_output_returns_none(self, mock_connection):
        """Test that output with only header returns None"""
        from app.api.ssh_keys import _run_df_command

        header_only = """Filesystem     1K-blocks      Used Available Use% Mounted on"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(header_only.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(header_only.encode(), b"")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_data_line_returns_none(self, mock_connection):
        """Test that malformed data line returns None"""
        from app.api.ssh_keys import _run_df_command

        malformed_output = """Filesystem     1K-blocks      Used Available Use% Mounted on
/dev/sda1      not_a_number  51200000  51200000  50% /home"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(malformed_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(malformed_output.encode(), b"")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=True)

        # Should skip the malformed line (second column isn't numeric)
        assert result is None

    @pytest.mark.asyncio
    async def test_insufficient_columns_returns_none(self, mock_connection):
        """Test that output with insufficient columns returns None"""
        from app.api.ssh_keys import _run_df_command

        short_output = """Filesystem     1K-blocks
/dev/sda1      102400000"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(short_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(short_output.encode(), b"")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_multiline_with_multiple_filesystems(self, mock_connection):
        """Test parsing when multiple filesystems are shown - should use first data line"""
        from app.api.ssh_keys import _run_df_command

        multi_fs_output = """Filesystem     1K-blocks      Used Available Use% Mounted on
/dev/sda1      102400000  51200000  51200000  50% /
/dev/sda2      204800000  102400000 102400000  50% /home"""

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(multi_fs_output.encode(), b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(multi_fs_output.encode(), b"")):
                result = await _run_df_command(mock_connection, "/tmp/key", "/", use_locale=True)

        assert result is not None
        # Should pick the first data line
        assert result["total"] == 102400000 * 1024
        assert result["mount_point"] == "/"

    @pytest.mark.asyncio
    async def test_uses_locale_prefix_when_specified(self, mock_connection):
        """Test that LC_ALL=C is added when use_locale=True"""
        from app.api.ssh_keys import _run_df_command

        captured_cmd = None

        async def capture_subprocess(*args, **kwargs):
            nonlocal captured_cmd
            captured_cmd = args
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=capture_subprocess):
            with patch("asyncio.wait_for", return_value=(b"", b"")):
                await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=True)

        assert captured_cmd is not None
        # The last argument should contain LC_ALL=C
        assert "LC_ALL=C" in captured_cmd[-1]

    @pytest.mark.asyncio
    async def test_no_locale_prefix_when_not_specified(self, mock_connection):
        """Test that LC_ALL=C is NOT added when use_locale=False"""
        from app.api.ssh_keys import _run_df_command

        captured_cmd = None

        async def capture_subprocess(*args, **kwargs):
            nonlocal captured_cmd
            captured_cmd = args
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=capture_subprocess):
            with patch("asyncio.wait_for", return_value=(b"", b"")):
                await _run_df_command(mock_connection, "/tmp/key", "/home", use_locale=False)

        assert captured_cmd is not None
        # The last argument should NOT contain LC_ALL=C
        assert "LC_ALL=C" not in captured_cmd[-1]
        assert "df -k" in captured_cmd[-1]


@pytest.mark.unit
class TestCollectStorageInfo:
    """Test collect_storage_info function with fallback logic"""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock SSH connection"""
        conn = MagicMock()
        conn.id = 1
        conn.host = "test-server.com"
        conn.username = "testuser"
        conn.port = 22
        conn.default_path = "/home"
        return conn

    @pytest.fixture
    def mock_ssh_key(self):
        """Create a mock SSH key with encrypted private key"""
        from cryptography.fernet import Fernet
        import base64
        from app.config import settings

        key = MagicMock()
        encryption_key = settings.secret_key.encode()[:32]
        cipher = Fernet(base64.urlsafe_b64encode(encryption_key))
        key.private_key = cipher.encrypt(b"fake-private-key\n").decode()
        return key

    @pytest.mark.asyncio
    async def test_success_on_first_attempt_with_locale(self, mock_connection, mock_ssh_key):
        """Test successful storage collection on first attempt (with LC_ALL=C)"""
        from app.api.ssh_keys import collect_storage_info

        english_output = """Filesystem     1K-blocks      Used Available Use% Mounted on
/dev/sda1      102400000  51200000  51200000  50% /home"""

        call_count = 0

        async def mock_run_df(conn, key_file, path, use_locale):
            nonlocal call_count
            call_count += 1
            if use_locale:  # First call with LC_ALL=C
                return {
                    "total": 102400000 * 1024,
                    "used": 51200000 * 1024,
                    "available": 51200000 * 1024,
                    "percent_used": 50.0,
                    "filesystem": "/dev/sda1",
                    "mount_point": "/home"
                }
            return None

        with patch("app.api.ssh_keys._run_df_command", side_effect=mock_run_df):
            with patch("tempfile.NamedTemporaryFile"):
                with patch("os.chmod"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.unlink"):
                            result = await collect_storage_info(mock_connection, mock_ssh_key)

        assert result is not None
        assert result["percent_used"] == 50.0
        assert call_count == 1  # Should succeed on first attempt

    @pytest.mark.asyncio
    async def test_fallback_to_plain_df_for_restricted_shell(self, mock_connection, mock_ssh_key):
        """Test fallback to plain df when LC_ALL=C fails (restricted shell like Hetzner)"""
        from app.api.ssh_keys import collect_storage_info

        call_count = 0

        async def mock_run_df(conn, key_file, path, use_locale):
            nonlocal call_count
            call_count += 1
            if use_locale:  # First call with LC_ALL=C fails
                return None
            else:  # Second call without locale succeeds
                return {
                    "total": 10485760000 * 1024,
                    "used": 8665169920 * 1024,
                    "available": 1820590080 * 1024,
                    "percent_used": 83.0,
                    "filesystem": "u331525-sub1",
                    "mount_point": "/home"
                }

        with patch("app.api.ssh_keys._run_df_command", side_effect=mock_run_df):
            with patch("tempfile.NamedTemporaryFile"):
                with patch("os.chmod"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.unlink"):
                            result = await collect_storage_info(mock_connection, mock_ssh_key)

        assert result is not None
        assert result["percent_used"] == 83.0
        assert call_count == 2  # Should have tried twice

    @pytest.mark.asyncio
    async def test_both_attempts_fail_returns_none(self, mock_connection, mock_ssh_key):
        """Test that None is returned when both attempts fail"""
        from app.api.ssh_keys import collect_storage_info

        call_count = 0

        async def mock_run_df(conn, key_file, path, use_locale):
            nonlocal call_count
            call_count += 1
            return None  # Both attempts fail

        with patch("app.api.ssh_keys._run_df_command", side_effect=mock_run_df):
            with patch("tempfile.NamedTemporaryFile"):
                with patch("os.chmod"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.unlink"):
                            result = await collect_storage_info(mock_connection, mock_ssh_key)

        assert result is None
        assert call_count == 2  # Should have tried both

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self, mock_connection, mock_ssh_key):
        """Test that timeout returns None gracefully"""
        from app.api.ssh_keys import collect_storage_info

        async def mock_run_df(conn, key_file, path, use_locale):
            raise asyncio.TimeoutError()

        with patch("app.api.ssh_keys._run_df_command", side_effect=mock_run_df):
            with patch("tempfile.NamedTemporaryFile"):
                with patch("os.chmod"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.unlink"):
                            result = await collect_storage_info(mock_connection, mock_ssh_key)

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_default_path_from_connection(self, mock_connection, mock_ssh_key):
        """Test that default_path from connection is used"""
        from app.api.ssh_keys import collect_storage_info

        captured_path = None

        async def mock_run_df(conn, key_file, path, use_locale):
            nonlocal captured_path
            captured_path = path
            return {"total": 1024, "used": 512, "available": 512, "percent_used": 50.0, "filesystem": "test", "mount_point": path}

        mock_connection.default_path = "/custom/path"

        with patch("app.api.ssh_keys._run_df_command", side_effect=mock_run_df):
            with patch("tempfile.NamedTemporaryFile"):
                with patch("os.chmod"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.unlink"):
                            await collect_storage_info(mock_connection, mock_ssh_key)

        assert captured_path == "/custom/path"

    @pytest.mark.asyncio
    async def test_uses_root_when_no_default_path(self, mock_connection, mock_ssh_key):
        """Test that / is used when no default_path is set"""
        from app.api.ssh_keys import collect_storage_info

        captured_path = None

        async def mock_run_df(conn, key_file, path, use_locale):
            nonlocal captured_path
            captured_path = path
            return {"total": 1024, "used": 512, "available": 512, "percent_used": 50.0, "filesystem": "test", "mount_point": path}

        mock_connection.default_path = None

        with patch("app.api.ssh_keys._run_df_command", side_effect=mock_run_df):
            with patch("tempfile.NamedTemporaryFile"):
                with patch("os.chmod"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.unlink"):
                            await collect_storage_info(mock_connection, mock_ssh_key)

        assert captured_path == "/"

    @pytest.mark.asyncio
    async def test_cleans_up_temp_key_file(self, mock_connection, mock_ssh_key):
        """Test that temporary key file is cleaned up even on failure"""
        from app.api.ssh_keys import collect_storage_info

        unlink_called = False

        def mock_unlink(path):
            nonlocal unlink_called
            unlink_called = True

        async def mock_run_df(conn, key_file, path, use_locale):
            raise Exception("Simulated error")

        with patch("app.api.ssh_keys._run_df_command", side_effect=mock_run_df):
            with patch("tempfile.NamedTemporaryFile"):
                with patch("os.chmod"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.unlink", side_effect=mock_unlink):
                            result = await collect_storage_info(mock_connection, mock_ssh_key)

        assert unlink_called
