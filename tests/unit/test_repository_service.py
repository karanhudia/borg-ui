import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import encrypt_secret
from app.database.models import Repository, SSHConnection, SSHKey
from app.services.repository_service import RepositoryService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_repository_uses_borg_info_json_command():
    with patch(
        "app.services.repository_service.borg._execute_command",
        new=AsyncMock(
            return_value={"success": True, "stdout": '{"archives":[]}', "stderr": ""}
        ),
    ) as mock_execute:
        result = await RepositoryService().verify_repository(
            path="/tmp/repo",
            passphrase="secret",
            remote_path="/usr/bin/borg",
            bypass_lock=True,
            timeout=12,
        )

    assert result == {"success": True, "info": {"archives": []}}
    mock_execute.assert_awaited_once_with(
        [
            "borg",
            "info",
            "--remote-path",
            "/usr/bin/borg",
            "--bypass-lock",
            "/tmp/repo",
            "--json",
        ],
        timeout=12,
        env=mock_execute.await_args.kwargs["env"],
    )
    env = mock_execute.await_args.kwargs["env"]
    assert env["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_keyfile_uses_borg_key_export_shape():
    repository = type("Repo", (), {"path": "/tmp/repo", "passphrase": "secret"})()

    process = type(
        "Proc",
        (),
        {
            "returncode": 0,
            "communicate": AsyncMock(return_value=(b"", b"")),
        },
    )()

    with patch(
        "app.services.repository_service.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as mock_exec:
        result = await RepositoryService().export_keyfile(repository, "/tmp/repo.key")

    assert result["success"] is True
    args = mock_exec.await_args.args
    assert args[:5] == ("borg", "key", "export", "/tmp/repo", "/tmp/repo.key")


def _fake_key_export(seen):
    """A `borg key export` process that records the environment it ran with
    and, while it runs, the SSH key it was given, then writes the key to the
    output path."""

    async def create_subprocess_exec(*args, env=None, **kwargs):
        seen["args"] = args
        seen["env"] = env

        async def communicate(input=None):
            rsh = (env.get("BORG_RSH") or "").split()
            if "-i" in rsh:
                key_file = rsh[rsh.index("-i") + 1]
                with open(key_file, "rb") as handle:
                    seen["key"] = handle.read()
                seen["key_file"] = key_file
            with open(args[4], "wb") as handle:
                handle.write(b"BORG_KEY exported")
            return b"", b""

        return SimpleNamespace(returncode=0, communicate=communicate)

    return create_subprocess_exec


@pytest.mark.unit
def test_keyfile_download_of_an_ssh_repository_uses_its_connection_key(
    test_client: TestClient, admin_headers, test_db
):
    """`borg key export` opens the repository, so on an ssh:// repository it
    runs with the SSH key, the pinned host key and the remote path of the
    repository's connection; the default key of the server's user may not be
    authorised there."""
    ssh_key = SSHKey(
        name="repo-key",
        public_key="ssh-ed25519 AAAA",
        private_key=encrypt_secret("connection-private-key"),
        key_type="ed25519",
    )
    test_db.add(ssh_key)
    test_db.commit()
    connection = SSHConnection(
        ssh_key_id=ssh_key.id,
        host="example.com",
        username="borg",
        port=2222,
        known_host_key="[example.com]:2222 ssh-ed25519 AAAAHOSTKEY",
        use_sudo=True,
        borg_binary_path="/usr/local/bin/borg",
    )
    test_db.add(connection)
    test_db.commit()
    repo = Repository(
        name="Borg 1 SSH Keyfile Repo",
        path="ssh://borg@example.com:2222/backups/repo",
        encryption="keyfile",
        compression="lz4",
        repository_type="ssh",
        connection_id=connection.id,
        borg_version=1,
        has_keyfile=True,
        passphrase="secret",
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    seen = {}
    with patch(
        "app.services.repository_service.asyncio.create_subprocess_exec",
        new=_fake_key_export(seen),
    ):
        response = test_client.get(
            f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
        )

    assert response.status_code == 200
    assert response.content == b"BORG_KEY exported"
    assert seen["args"][1:4] == ("key", "export", repo.path)
    assert seen["key"].strip() == b"connection-private-key"
    assert not os.path.exists(seen["key_file"])
    assert "-o StrictHostKeyChecking=yes" in seen["env"]["BORG_RSH"]
    assert seen["env"]["BORG_REMOTE_PATH"] == "sudo -n -H /usr/local/bin/borg"
    assert seen["env"]["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
def test_keyfile_download_of_a_local_repository_keeps_its_environment(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    """A local repository has no connection: the export runs with the
    passphrase and no remote shell, as before."""
    # The export copies the server's environment; keep the shell's out.
    monkeypatch.delenv("BORG_RSH", raising=False)
    monkeypatch.delenv("BORG_REMOTE_PATH", raising=False)
    repo = Repository(
        name="Borg 1 Local Keyfile Repo",
        path="/tmp/borg1-local-keyfile-repo",
        encryption="keyfile",
        compression="lz4",
        repository_type="local",
        borg_version=1,
        has_keyfile=True,
        passphrase="secret",
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)

    seen = {}
    with patch(
        "app.services.repository_service.asyncio.create_subprocess_exec",
        new=_fake_key_export(seen),
    ):
        response = test_client.get(
            f"/api/repositories/{repo.id}/keyfile", headers=admin_headers
        )

    assert response.status_code == 200
    assert response.content == b"BORG_KEY exported"
    assert seen["args"][1:4] == ("key", "export", repo.path)
    assert "BORG_RSH" not in seen["env"]
    assert "BORG_REMOTE_PATH" not in seen["env"]
    assert seen["env"]["BORG_PASSPHRASE"] == "secret"
