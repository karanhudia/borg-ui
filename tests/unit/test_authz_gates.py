"""Role gates on admin-only and operator-only routers.

Each gate is pinned both ways: the wrong role gets 403 and the right role
gets through the gate (any status other than 401/403).
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.permissions import REPOSITORY_ACTION_RULES
from app.core.security import create_access_token, get_password_hash
from app.database.models import (
    Operation,
    Repository,
    SSHConnection,
    User,
    UserRepositoryPermission,
)


def _user_headers(db, username, role, repo=None, repo_role=None):
    user = User(
        username=username,
        password_hash=get_password_hash("x"),
        is_active=True,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if repo is not None:
        db.add(
            UserRepositoryPermission(
                user_id=user.id,
                repository_id=repo.id,
                role=repo_role,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    token = create_access_token(data={"sub": user.username})
    return {"X-Borg-Authorization": f"Bearer {token}"}


def _repo(db, name="gate-repo"):
    repo = Repository(
        name=name, path=f"/backup/{name}", encryption="none", repository_type="local"
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def _assert_passes_gate(response):
    assert response.status_code not in (401, 403), response.text


@pytest.fixture
def mount_root(tmp_path, monkeypatch):
    root = tmp_path / "mnt"
    root.mkdir()
    monkeypatch.setattr(settings, "local_mount_points", str(root))
    return root


ADMIN_ONLY_ROUTES = [
    ("GET", "/api/notifications"),
    ("GET", "/api/notifications/1"),
    ("POST", "/api/notifications"),
    ("PUT", "/api/notifications/1"),
    ("DELETE", "/api/notifications/1"),
    ("POST", "/api/notifications/test"),
    ("POST", "/api/config/export/borgmatic"),
    ("POST", "/api/config/import/borgmatic"),
    ("GET", "/api/config/export/repositories"),
    ("GET", "/api/settings/cache/stats"),
    ("PUT", "/api/ssh-keys/connections/1"),
    ("DELETE", "/api/ssh-keys/connections/1"),
    ("POST", "/api/ssh-keys/connections/host-cleanup"),
    ("GET", "/api/ssh-keys/connections/host-audit"),
    ("POST", "/api/ssh-keys/connections/1/host-key/trust"),
    ("DELETE", "/api/ssh-keys/connections/1/host-key"),
    ("POST", "/api/ssh-keys/connections/1/redeploy"),
    ("POST", "/api/ssh-keys/connections/1/refresh-storage"),
    ("POST", "/api/ssh-keys/connections/1/diagnostics"),
    ("POST", "/api/ssh-keys/connections/1/test"),
    ("POST", "/api/ssh-keys/1/test-connection"),
]


@pytest.mark.unit
class TestAdminOnlyRoutes:
    @pytest.mark.parametrize("method,path", ADMIN_ONLY_ROUTES)
    def test_viewer_is_forbidden(
        self, test_client: TestClient, auth_headers, method, path
    ):
        response = test_client.request(method, path, headers=auth_headers, json={})
        assert response.status_code == 403

    @pytest.mark.parametrize("method,path", ADMIN_ONLY_ROUTES)
    def test_operator_is_forbidden(
        self, test_client: TestClient, operator_headers, method, path
    ):
        response = test_client.request(method, path, headers=operator_headers, json={})
        assert response.status_code == 403

    def test_admin_can_list_notifications(self, test_client, admin_headers):
        response = test_client.get("/api/notifications", headers=admin_headers)
        assert response.status_code == 200

    def test_admin_can_export_repositories(self, test_client, admin_headers):
        response = test_client.get(
            "/api/config/export/repositories", headers=admin_headers
        )
        assert response.status_code == 200

    def test_admin_can_read_cache_stats(self, test_client, admin_headers):
        response = test_client.get("/api/settings/cache/stats", headers=admin_headers)
        _assert_passes_gate(response)

    def test_admin_passes_ssh_connection_gate(self, test_client, admin_headers):
        response = test_client.delete(
            "/api/ssh-keys/connections/999999", headers=admin_headers
        )
        _assert_passes_gate(response)

    def test_viewer_keeps_read_access_to_ssh_listings(self, test_client, auth_headers):
        assert test_client.get("/api/ssh-keys", headers=auth_headers).status_code == 200
        assert (
            test_client.get(
                "/api/ssh-keys/connections", headers=auth_headers
            ).status_code
            == 200
        )


@pytest.mark.unit
class TestFilesystemGate:
    def test_viewer_cannot_browse(self, test_client, auth_headers, mount_root):
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": str(mount_root)},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_viewer_cannot_validate_or_create(
        self, test_client, auth_headers, mount_root
    ):
        assert (
            test_client.post(
                "/api/filesystem/validate-path",
                params={"path": str(mount_root)},
                headers=auth_headers,
            ).status_code
            == 403
        )
        assert (
            test_client.post(
                "/api/filesystem/create-folder",
                json={"path": str(mount_root), "folder_name": "x"},
                headers=auth_headers,
            ).status_code
            == 403
        )
        assert not (mount_root / "x").exists()

    def test_operator_can_browse_inside_mount(
        self, test_client, operator_headers, mount_root
    ):
        (mount_root / "photos").mkdir()
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": str(mount_root)},
            headers=operator_headers,
        )
        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["photos"]

    def test_browse_outside_mount_is_forbidden(
        self, test_client, operator_headers, mount_root, tmp_path
    ):
        outside = tmp_path / "outside"
        outside.mkdir()
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": str(outside)},
            headers=operator_headers,
        )
        assert response.status_code == 403

    def test_admin_is_not_confined_to_mounts(
        self, test_client, admin_headers, mount_root, tmp_path
    ):
        outside = tmp_path / "outside"
        outside.mkdir()
        browse = test_client.get(
            "/api/filesystem/browse",
            params={"path": str(outside)},
            headers=admin_headers,
        )
        validate = test_client.post(
            "/api/filesystem/validate-path",
            params={"path": str(outside)},
            headers=admin_headers,
        )
        assert browse.status_code == 200
        assert validate.status_code == 200
        assert validate.json()["exists"] is True

    def test_browse_traversal_above_mount_lists_only_the_mount(
        self, test_client, operator_headers, mount_root
    ):
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": f"{mount_root}/../"},
            headers=operator_headers,
        )
        # The parent of a mount point lists only the way back to the mount.
        assert response.status_code == 200
        assert [item["name"] for item in response.json()["items"]] == ["mnt"]

    def test_browse_symlink_escape_is_forbidden(
        self, test_client, operator_headers, mount_root, tmp_path
    ):
        outside = tmp_path / "secret"
        outside.mkdir()
        (mount_root / "link").symlink_to(outside)
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": str(mount_root / "link")},
            headers=operator_headers,
        )
        assert response.status_code == 403

    def test_browse_root_lists_only_mount_ancestors(
        self, test_client, operator_headers, mount_root
    ):
        response = test_client.get(
            "/api/filesystem/browse",
            params={"path": "/"},
            headers=operator_headers,
        )
        assert response.status_code == 200
        first_segment = str(mount_root).strip("/").split("/")[0]
        assert [item["name"] for item in response.json()["items"]] == [first_segment]

    def test_validate_path_outside_mount_is_forbidden(
        self, test_client, operator_headers, mount_root
    ):
        response = test_client.post(
            "/api/filesystem/validate-path",
            params={"path": "/etc"},
            headers=operator_headers,
        )
        assert response.status_code == 403

    def test_create_folder_outside_mount_is_forbidden(
        self, test_client, operator_headers, mount_root, tmp_path
    ):
        response = test_client.post(
            "/api/filesystem/create-folder",
            json={"path": str(tmp_path), "folder_name": "evil"},
            headers=operator_headers,
        )
        assert response.status_code == 403
        assert not (tmp_path / "evil").exists()

    def test_operator_can_create_folder_inside_mount(
        self, test_client, operator_headers, mount_root
    ):
        response = test_client.post(
            "/api/filesystem/create-folder",
            json={"path": str(mount_root), "folder_name": "new"},
            headers=operator_headers,
        )
        assert response.status_code == 200
        assert (mount_root / "new").is_dir()


def _restore_body(repo, destination, **extra):
    body = {
        "repository": repo.path,
        "repository_id": repo.id,
        "archive": "a",
        "paths": ["docs"],
        "destination": destination,
        "restore_layout": "contents_only",
    }
    body.update(extra)
    return body


@pytest.fixture
def no_restore_execution():
    with patch(
        "app.services.restore_service.restore_service.execute_restore",
        new=AsyncMock(return_value=None),
    ):
        yield


@pytest.mark.unit
class TestRestoreGate:
    def test_restore_action_requires_operator(self):
        assert REPOSITORY_ACTION_RULES["restore"] == "operator"

    def test_repo_viewer_cannot_start_or_preview(
        self, test_client, test_db, mount_root
    ):
        repo = _repo(test_db, "rg-view")
        headers = _user_headers(test_db, "rg-viewer", "viewer", repo, "viewer")
        body = _restore_body(repo, str(mount_root / "out"))
        assert (
            test_client.post(
                "/api/restore/start", json=body, headers=headers
            ).status_code
            == 403
        )
        assert (
            test_client.post(
                "/api/restore/preview", json=body, headers=headers
            ).status_code
            == 403
        )

    def test_repo_operator_can_start_inside_mount(
        self, test_client, test_db, mount_root, no_restore_execution
    ):
        repo = _repo(test_db, "rg-op")
        headers = _user_headers(test_db, "rg-operator", "operator", repo, "operator")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(repo, str(mount_root / "out")),
            headers=headers,
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("destination", ["/etc", "/app/restore", "/"])
    def test_destination_outside_mounts_is_forbidden(
        self, test_client, test_db, mount_root, destination
    ):
        repo = _repo(test_db, "rg-dest")
        headers = _user_headers(test_db, "rg-dest-op", "operator", repo, "operator")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(repo, destination),
            headers=headers,
        )
        assert response.status_code == 403

    def test_admin_can_restore_outside_mounts(
        self, test_client, test_db, admin_headers, mount_root, no_restore_execution
    ):
        repo = _repo(test_db, "rg-admin-out")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(repo, "/srv/restore"),
            headers=admin_headers,
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("destination", ["/app/restore", "/"])
    def test_admin_cannot_restore_into_the_app(
        self, test_client, test_db, admin_headers, mount_root, destination
    ):
        repo = _repo(test_db, "rg-admin-app")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(repo, destination),
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_original_location_restore_into_mount_is_allowed(
        self, test_client, test_db, admin_headers, mount_root, no_restore_execution
    ):
        repo = _repo(test_db, "rg-orig")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(
                repo,
                "/",
                paths=[str(mount_root / "docs").lstrip("/")],
                restore_layout="preserve_path",
            ),
            headers=admin_headers,
        )
        assert response.status_code == 200

    def test_original_location_restore_outside_mount_is_forbidden(
        self, test_client, test_db, admin_headers, mount_root
    ):
        repo = _repo(test_db, "rg-orig-out")
        headers = _user_headers(test_db, "rg-orig-op", "operator", repo, "operator")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(
                repo, "/", paths=["etc/cron.d"], restore_layout="preserve_path"
            ),
            headers=headers,
        )
        assert response.status_code == 403

    def test_data_dir_is_rejected_even_under_a_mount(
        self, test_client, test_db, admin_headers, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(settings, "local_mount_points", str(tmp_path))
        monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
        repo = _repo(test_db, "rg-data")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(repo, str(tmp_path / "data" / "ssh_keys")),
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_destination_connection_requires_global_operator(
        self, test_client, test_db, mount_root
    ):
        repo = _repo(test_db, "rg-conn")
        connection = SSHConnection(host="h.example", username="u", port=22)
        test_db.add(connection)
        test_db.commit()
        # A global viewer with a (legacy) operator grant on the repository.
        headers = _user_headers(test_db, "rg-conn-viewer", "viewer", repo, "operator")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(
                repo,
                "/srv/out",
                destination_type="ssh",
                destination_connection_id=connection.id,
            ),
            headers=headers,
        )
        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.restore.operatorAccessRequired"
        )

    def test_unknown_destination_connection_is_rejected(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db, "rg-conn-missing")
        response = test_client.post(
            "/api/restore/start",
            json=_restore_body(
                repo,
                "/srv/out",
                destination_type="ssh",
                destination_connection_id=999999,
            ),
            headers=admin_headers,
        )
        assert response.status_code == 404


def _restore_op(db, repo, status="running"):
    op = Operation(
        repository_id=repo.id if repo else None,
        kind="restore",
        category="restore",
        status=status,
        trigger="manual",
        priority=0,
        run_id=f"run-gate-{os.urandom(4).hex()}",
    )
    db.add(op)
    db.commit()
    return op


@pytest.mark.unit
class TestRestoreJobGate:
    def test_repo_viewer_cannot_cancel(self, test_client, test_db):
        repo = _repo(test_db, "rj-cancel")
        headers = _user_headers(test_db, "rj-viewer", "viewer", repo, "viewer")
        op = _restore_op(test_db, repo)
        response = test_client.post(f"/api/restore/cancel/{op.id}", headers=headers)
        assert response.status_code == 403
        test_db.expire_all()
        assert op.status == "running"

    def test_repo_operator_can_cancel(self, test_client, test_db):
        repo = _repo(test_db, "rj-cancel-op")
        headers = _user_headers(test_db, "rj-operator", "operator", repo, "operator")
        op = _restore_op(test_db, repo)
        with (
            patch(
                "app.api.restore.operation_runner.request_cancel",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.api.restore.restore_service.cancel_restore",
                new=AsyncMock(return_value=True),
            ),
        ):
            response = test_client.post(f"/api/restore/cancel/{op.id}", headers=headers)
        assert response.status_code == 200

    def test_orphaned_job_is_hidden_from_non_admins(self, test_client, test_db):
        headers = _user_headers(test_db, "rj-orphan", "operator")
        op = _restore_op(test_db, None)
        assert (
            test_client.get(f"/api/restore/status/{op.id}", headers=headers).status_code
            == 403
        )
        assert (
            test_client.post(
                f"/api/restore/cancel/{op.id}", headers=headers
            ).status_code
            == 403
        )
        jobs = test_client.get("/api/restore/jobs", headers=headers).json()["jobs"]
        assert op.id not in [job["id"] for job in jobs]

    def test_job_access_follows_repository_id_not_path(self, test_client, test_db):
        granted = _repo(test_db, "rj-granted")
        other = _repo(test_db, "rj-other")
        headers = _user_headers(test_db, "rj-path", "operator", granted, "operator")
        op = _restore_op(test_db, other)
        assert (
            test_client.get(f"/api/restore/status/{op.id}", headers=headers).status_code
            == 403
        )
        jobs = test_client.get("/api/restore/jobs", headers=headers).json()["jobs"]
        assert op.id not in [job["id"] for job in jobs]
