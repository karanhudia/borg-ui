"""Issue #1430: more than one SSH key, chosen per connection."""

import subprocess
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api import ssh_keys as ssh_keys_api
from app.core.security import encrypt_secret
from app.database.models import SSHConnection, SSHKey


def _keygen(tmp_path, name="key"):
    path = tmp_path / name
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", str(path)], check=True
    )
    return path


def _add_key(test_db, name, *, system=False):
    key = SSHKey(
        name=name,
        key_type="ed25519",
        public_key=f"ssh-ed25519 AAAA{name}",
        private_key=encrypt_secret("-----BEGIN OPENSSH PRIVATE KEY-----\nx\n"),
        is_system_key=system,
        is_active=True,
    )
    test_db.add(key)
    test_db.commit()
    test_db.refresh(key)
    return key


def _add_connection(test_db, key, host="box.example.com"):
    conn = SSHConnection(
        host=host, username="u", port=22, ssh_key_id=key.id, status="connected"
    )
    test_db.add(conn)
    test_db.commit()
    test_db.refresh(conn)
    return conn


def test_generate_extra_key_alongside_system_key(
    test_client: TestClient, admin_headers, test_db
):
    _add_key(test_db, "system", system=True)

    response = test_client.post(
        "/api/ssh-keys/generate",
        json={"name": "extra", "key_type": "ed25519", "system_key": False},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.json()
    assert response.json()["ssh_key"]["is_system_key"] is False
    assert test_db.query(SSHKey).filter(SSHKey.is_system_key.is_(True)).count() == 1


def test_generate_still_refuses_second_system_key(
    test_client: TestClient, admin_headers, test_db
):
    _add_key(test_db, "system", system=True)

    response = test_client.post(
        "/api/ssh-keys/generate",
        json={"name": "again", "key_type": "ed25519"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]["key"] == "backend.errors.ssh.systemKeyAlreadyExists"
    )


def test_import_extra_key_does_not_deploy_to_ssh_home(
    test_client: TestClient, admin_headers, test_db, tmp_path
):
    _add_key(test_db, "system", system=True)
    key_path = _keygen(tmp_path)

    with patch.object(ssh_keys_api.subprocess, "run") as run:
        response = test_client.post(
            "/api/ssh-keys/import",
            json={
                "name": "borgmatic",
                "private_key_path": str(key_path),
                "system_key": False,
            },
            headers=admin_headers,
        )

    assert response.status_code == 200, response.json()
    assert response.json()["ssh_key"]["is_system_key"] is False
    run.assert_not_called()


def test_redeploy_uses_the_connections_own_key(
    test_client: TestClient, admin_headers, test_db
):
    _add_key(test_db, "system", system=True)
    extra = _add_key(test_db, "extra")
    conn = _add_connection(test_db, extra)

    with patch.object(
        ssh_keys_api,
        "deploy_ssh_key_with_copy_id",
        AsyncMock(return_value={"success": True}),
    ) as deploy:
        response = test_client.post(
            f"/api/ssh-keys/connections/{conn.id}/redeploy",
            json={"password": "pw"},
            headers=admin_headers,
        )

    assert response.status_code == 200, response.json()
    assert deploy.await_args.kwargs["ssh_key"].id == extra.id
    test_db.refresh(conn)
    assert conn.ssh_key_id == extra.id


def test_update_connection_changes_key_and_resets_status(
    test_client: TestClient, admin_headers, test_db
):
    system = _add_key(test_db, "system", system=True)
    extra = _add_key(test_db, "extra")
    conn = _add_connection(test_db, system)

    response = test_client.put(
        f"/api/ssh-keys/connections/{conn.id}",
        json={"ssh_key_id": extra.id},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.json()
    test_db.refresh(conn)
    assert conn.ssh_key_id == extra.id
    assert conn.status == "unknown"


def test_update_connection_with_same_key_keeps_status(
    test_client: TestClient, admin_headers, test_db
):
    system = _add_key(test_db, "system", system=True)
    conn = _add_connection(test_db, system)

    response = test_client.put(
        f"/api/ssh-keys/connections/{conn.id}",
        json={"ssh_key_id": system.id, "port": 2222},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.json()
    test_db.refresh(conn)
    assert conn.status == "connected"


def test_update_connection_with_unknown_key_is_404(
    test_client: TestClient, admin_headers, test_db
):
    system = _add_key(test_db, "system", system=True)
    conn = _add_connection(test_db, system)

    response = test_client.put(
        f"/api/ssh-keys/connections/{conn.id}",
        json={"ssh_key_id": 987654},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["key"] == "backend.errors.ssh.sshKeyNotFound"
    test_db.refresh(conn)
    assert conn.ssh_key_id == system.id


def test_delete_extra_key_in_use_is_refused(
    test_client: TestClient, admin_headers, test_db
):
    extra = _add_key(test_db, "extra")
    _add_connection(test_db, extra, host="a.example.com")
    _add_connection(test_db, extra, host="b.example.com")

    response = test_client.delete(f"/api/ssh-keys/{extra.id}", headers=admin_headers)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["key"] == "backend.errors.ssh.keyInUse"
    assert sorted(detail["params"]["connections"]) == [
        "u@a.example.com:22",
        "u@b.example.com:22",
    ]
    assert test_db.query(SSHKey).filter(SSHKey.id == extra.id).first() is not None


def test_delete_system_key_in_use_keeps_connections(
    test_client: TestClient, admin_headers, test_db
):
    system = _add_key(test_db, "system", system=True)
    conn = _add_connection(test_db, system)

    response = test_client.delete(f"/api/ssh-keys/{system.id}", headers=admin_headers)

    assert response.status_code == 200, response.json()
    test_db.refresh(conn)
    assert conn.ssh_key_id is None
    assert conn.status == "failed"
