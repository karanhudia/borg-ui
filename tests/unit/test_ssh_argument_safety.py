"""
Regression tests for SSH argument and remote command injection.

Every payload here is a real exploit string: a username that OpenSSH would
parse as an option, a path that breaks out of a double-quoted remote command,
or a newline that starts a local `!command` in an sftp batch file.
"""

from __future__ import annotations

import base64
import shlex
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import filesystem, ssh_keys
from app.database.models import SSHConnection, SSHKey
from app.utils import fs
from app.utils.ssh_host_validation import normalize_ssh_username, ssh_destination

PROXY_COMMAND_USER = "-oProxyCommand=touch /tmp/pwned"
QUOTE_BREAKOUT_PATH = '/srv/x"; touch /tmp/pwned; echo "'
SUBSHELL_PATH = "/srv/$(touch /tmp/pwned)"
SFTP_LOCAL_COMMAND_PATH = "/srv\n!touch /tmp/pwned"

ADMIN = SimpleNamespace(username="admin", is_admin=True)
VIEWER = SimpleNamespace(username="viewer", is_admin=False)


def _encrypt_private_key(secret_key: str, private_key: str) -> str:
    key = base64.urlsafe_b64encode(secret_key.encode()[:32])
    return Fernet(key).encrypt(private_key.encode()).decode()


@pytest.fixture
def stored_key(test_db, monkeypatch):
    secret_key = "a" * 32
    monkeypatch.setattr(filesystem.settings, "secret_key", secret_key, raising=False)
    monkeypatch.setattr(
        filesystem.settings.__class__, "get_local_mount_points", lambda self: []
    )
    key = SSHKey(
        name="stored",
        public_key="ssh-ed25519 AAAA",
        private_key=_encrypt_private_key(secret_key, "PRIVATE KEY"),
    )
    test_db.add(key)
    test_db.commit()
    test_db.refresh(key)
    return key


def _saved_connection(test_db, key, **fields):
    values = {"host": "example.com", "username": "borg", "port": 22}
    values.update(fields)
    connection = SSHConnection(ssh_key_id=key.id, **values)
    test_db.add(connection)
    test_db.commit()
    return connection


@pytest.mark.unit
class TestSshUsernameValidation:
    @pytest.mark.parametrize(
        "username",
        ["borg", "u123456", "u123456-sub1", "backup.user", "_svc", "Admin01"],
    )
    def test_accepts_real_usernames(self, username):
        assert normalize_ssh_username(f"  {username} ") == username

    @pytest.mark.parametrize(
        "username",
        [
            PROXY_COMMAND_USER,
            "-lroot",
            "root@evil.example",
            "borg\n-oProxyCommand=id",
            "a b",
            "x;id",
            "$(id)",
            "",
            "a" * 65,
        ],
    )
    def test_rejects_option_and_shell_payloads(self, username):
        with pytest.raises(ValueError):
            normalize_ssh_username(username)

    def test_destination_refuses_stored_option_payloads(self):
        with pytest.raises(ValueError):
            ssh_destination(PROXY_COMMAND_USER, "example.com")
        with pytest.raises(ValueError):
            ssh_destination("borg", "-oProxyCommand=id")
        assert ssh_destination("u123456-sub1", "u123456.your-storagebox.de") == (
            "u123456-sub1@u123456.your-storagebox.de"
        )

    @pytest.mark.parametrize(
        "schema, payload",
        [
            (ssh_keys.SSHConnectionTest, {"host": "example.com"}),
            (ssh_keys.SSHConnectionCreate, {"host": "example.com", "password": "x"}),
            (ssh_keys.SSHConnectionUpdate, {}),
            (ssh_keys.SSHQuickSetup, {"name": "k", "host": "example.com"}),
        ],
    )
    def test_schemas_reject_option_username(self, schema, payload):
        with pytest.raises(ValidationError):
            schema(username=PROXY_COMMAND_USER, **payload)


@pytest.mark.unit
class TestRemoteCommandQuoting:
    def test_borg_repo_probe_quotes_path_and_ends_options(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            filesystem, "host_key_ssh_opts_for_host", lambda *a, **k: []
        )
        monkeypatch.setattr(
            filesystem.subprocess,
            "run",
            lambda cmd, **kwargs: (
                calls.append(cmd) or SimpleNamespace(returncode=1, stdout="", stderr="")
            ),
        )

        filesystem.is_borg_repository_ssh(
            "example.com", "borg", "/tmp/key", QUOTE_BREAKOUT_PATH
        )

        cmd = calls[0]
        assert cmd[-3:-1] == ["--", "borg@example.com"]
        assert shlex.split(cmd[-1]) == [
            "ls",
            f"{QUOTE_BREAKOUT_PATH}/config",
            f"{QUOTE_BREAKOUT_PATH}/data",
        ]

    @pytest.mark.asyncio
    async def test_validate_path_stat_quotes_path(
        self, test_db, stored_key, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            filesystem, "host_key_ssh_opts_for_host", lambda *a, **k: []
        )
        monkeypatch.setattr(
            filesystem.subprocess,
            "run",
            lambda cmd, **kwargs: (
                calls.append(cmd) or SimpleNamespace(returncode=1, stdout="", stderr="")
            ),
        )

        await filesystem.validate_path(
            path=SUBSHELL_PATH,
            connection_type="ssh",
            ssh_key_id=stored_key.id,
            host="example.com",
            username="borg",
            port=22,
            current_user=ADMIN,
            db=test_db,
        )

        # $() still expands inside double quotes, so only single quoting is safe.
        assert calls[0][-1] == f"stat {shlex.quote(SUBSHELL_PATH)}"
        assert calls[0][-3:-1] == ["--", "borg@example.com"]

    @pytest.mark.asyncio
    async def test_du_ssh_quotes_path(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"1", b"")
        with (
            patch.object(fs, "host_key_ssh_opts_for_path", return_value=[]),
            patch.object(
                fs.asyncio, "create_subprocess_exec", return_value=process
            ) as mock_exec,
        ):
            await fs._du_ssh(f"ssh://borg@example.com:22{SUBSHELL_PATH}", [], 5)

        remote = mock_exec.call_args.args[-1]
        assert shlex.split(remote)[:3] == ["du", "-sb", SUBSHELL_PATH]

    @pytest.mark.asyncio
    async def test_du_ssh_refuses_option_username(self):
        with patch.object(fs.asyncio, "create_subprocess_exec") as mock_exec:
            size = await fs._du_ssh(
                "ssh://-oProxyCommand=touch%20x@example.com:22/srv", [], 5
            )
        assert size is None
        mock_exec.assert_not_called()


@pytest.mark.unit
class TestSftpBatchInjection:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path", [SFTP_LOCAL_COMMAND_PATH, "/srv\r!id", '/srv"\n!id', "/srv\0x"]
    )
    async def test_browse_rejects_batch_breakout(self, test_db, stored_key, path):
        with patch.object(filesystem.subprocess, "run") as mock_run:
            with pytest.raises(HTTPException) as exc:
                await filesystem.browse_filesystem(
                    path=path,
                    connection_type="ssh",
                    ssh_key_id=stored_key.id,
                    host="example.com",
                    username="borg",
                    port=22,
                    current_user=ADMIN,
                    db=test_db,
                )
        assert exc.value.status_code == 400
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_browse_rejects_poisoned_saved_default_path(
        self, test_db, stored_key
    ):
        _saved_connection(test_db, stored_key, default_path=SFTP_LOCAL_COMMAND_PATH)
        with patch.object(filesystem.subprocess, "run") as mock_run:
            with pytest.raises(HTTPException) as exc:
                await filesystem.browse_filesystem(
                    path="/",
                    connection_type="ssh",
                    ssh_key_id=stored_key.id,
                    host="example.com",
                    username="borg",
                    port=22,
                    current_user=ADMIN,
                    db=test_db,
                )
        assert exc.value.status_code == 400
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "path, folder_name",
        [("/srv", 'new"\n!touch /tmp/pwned'), (SFTP_LOCAL_COMMAND_PATH, "new")],
    )
    async def test_create_folder_rejects_batch_breakout(
        self, test_db, stored_key, path, folder_name
    ):
        request = filesystem.CreateFolderRequest(
            path=path,
            folder_name=folder_name,
            connection_type="ssh",
            ssh_key_id=stored_key.id,
            host="example.com",
            username="borg",
        )
        with patch.object(filesystem.subprocess, "run") as mock_run:
            with pytest.raises(HTTPException) as exc:
                await filesystem.create_folder(
                    request=request, current_user=ADMIN, db=test_db
                )
        assert exc.value.status_code == 400
        mock_run.assert_not_called()


@pytest.mark.unit
class TestFilesystemSshTarget:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "host, username",
        [("example.com", PROXY_COMMAND_USER), ("-oProxyCommand=id", "borg")],
    )
    async def test_browse_rejects_option_injection(
        self, test_db, stored_key, host, username
    ):
        with patch.object(filesystem.subprocess, "run") as mock_run:
            with pytest.raises(HTTPException) as exc:
                await filesystem.browse_filesystem(
                    path="/srv",
                    connection_type="ssh",
                    ssh_key_id=stored_key.id,
                    host=host,
                    username=username,
                    port=22,
                    current_user=ADMIN,
                    db=test_db,
                )
        assert exc.value.status_code == 400
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_admin_cannot_use_key_against_unsaved_target(
        self, test_db, stored_key
    ):
        _saved_connection(test_db, stored_key)
        with patch.object(filesystem.subprocess, "run") as mock_run:
            with pytest.raises(HTTPException) as exc:
                await filesystem.validate_path(
                    path="/srv",
                    connection_type="ssh",
                    ssh_key_id=stored_key.id,
                    host="attacker.example",
                    username="borg",
                    port=22,
                    current_user=VIEWER,
                    db=test_db,
                )
        assert exc.value.status_code == 403
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_admin_can_use_saved_connection(
        self, test_db, stored_key, monkeypatch
    ):
        _saved_connection(test_db, stored_key)
        monkeypatch.setattr(
            filesystem, "host_key_ssh_opts_for_host", lambda *a, **k: []
        )
        monkeypatch.setattr(
            filesystem.subprocess,
            "run",
            lambda cmd, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
        )
        payload = await filesystem.validate_path(
            path="/srv",
            connection_type="ssh",
            ssh_key_id=stored_key.id,
            host="example.com",
            username="borg",
            port=22,
            current_user=VIEWER,
            db=test_db,
        )
        assert payload["exists"] is False


@pytest.mark.unit
class TestStoredUsernameDefenseInDepth:
    @pytest.fixture(autouse=True)
    def _key_material(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ssh_keys, "decrypt_secret", lambda value: "KEY")
        monkeypatch.setattr(
            ssh_keys.settings, "ssh_keys_dir", str(tmp_path), raising=False
        )
        monkeypatch.setattr(ssh_keys, "host_key_ssh_opts", lambda *a, **k: [])

    @pytest.mark.asyncio
    async def test_connection_test_never_runs_ssh_with_option_username(self):
        key = SimpleNamespace(id=1, private_key="x", public_key="y")
        with patch.object(ssh_keys.asyncio, "create_subprocess_exec") as mock_exec:
            result = await ssh_keys.test_ssh_key_connection(
                key, "example.com", PROXY_COMMAND_USER, 22
            )
        assert result["success"] is False
        mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_copy_id_never_runs_with_option_username(self):
        key = SimpleNamespace(id=1, private_key="x", public_key="y")
        with patch.object(ssh_keys.asyncio, "create_subprocess_exec") as mock_exec:
            result = await ssh_keys.deploy_ssh_key_with_copy_id(
                key, "example.com", PROXY_COMMAND_USER, "pw"
            )
        assert result["success"] is False
        mock_exec.assert_not_called()
