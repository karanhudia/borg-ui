# tests/unit/test_api_permissions.py
"""
Unit tests for per-repository permission endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from app.database.models import User, Repository
from app.core.security import get_password_hash, create_access_token


def _make_repo(db, name="test-repo"):
    repo = Repository(name=name, path=f"/backup/{name}", encryption="none")
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def _make_user(db, username, role="viewer"):
    user = User(
        username=username,
        password_hash=get_password_hash("pass"),
        is_active=True,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.unit
class TestPermissions:
    def test_get_my_permissions_empty(self, test_client: TestClient, admin_headers):
        """Admin with no per-repo permissions returns empty list"""
        response = test_client.get(
            "/api/settings/permissions/me", headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_get_my_permission_scope_defaults_to_none(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.get(
            "/api/settings/permissions/me/scope", headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()["all_repositories_role"] is None

    def test_assign_permission(self, test_client: TestClient, test_db, admin_headers):
        """Admin can assign a role to a user for a repository"""
        user = _make_user(test_db, "viewer1")
        repo = _make_repo(test_db)

        response = test_client.post(
            f"/api/settings/users/{user.id}/permissions",
            json={"repository_id": repo.id, "role": "operator"},
            headers=admin_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "operator"
        assert data["repository_name"] == "test-repo"

    def test_assign_invalid_role_returns_422(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """Invalid role value is rejected"""
        user = _make_user(test_db, "viewer2")
        repo = _make_repo(test_db, "repo2")

        response = test_client.post(
            f"/api/settings/users/{user.id}/permissions",
            json={"repository_id": repo.id, "role": "superuser"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_assign_duplicate_permission_returns_409(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """Cannot assign a second permission for the same user+repo pair"""
        user = _make_user(test_db, "viewer3")
        repo = _make_repo(test_db, "repo3")

        test_client.post(
            f"/api/settings/users/{user.id}/permissions",
            json={"repository_id": repo.id, "role": "viewer"},
            headers=admin_headers,
        )
        response = test_client.post(
            f"/api/settings/users/{user.id}/permissions",
            json={"repository_id": repo.id, "role": "operator"},
            headers=admin_headers,
        )
        assert response.status_code == 409

    def test_update_permission(self, test_client: TestClient, test_db, admin_headers):
        """Admin can change a user's role on a repository"""
        user = _make_user(test_db, "viewer4")
        repo = _make_repo(test_db, "repo4")

        test_client.post(
            f"/api/settings/users/{user.id}/permissions",
            json={"repository_id": repo.id, "role": "viewer"},
            headers=admin_headers,
        )
        response = test_client.put(
            f"/api/settings/users/{user.id}/permissions/{repo.id}",
            json={"role": "operator"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["role"] == "operator"

    def test_remove_permission(self, test_client: TestClient, test_db, admin_headers):
        """Admin can remove a user's repository permission"""
        user = _make_user(test_db, "viewer5")
        repo = _make_repo(test_db, "repo5")

        test_client.post(
            f"/api/settings/users/{user.id}/permissions",
            json={"repository_id": repo.id, "role": "viewer"},
            headers=admin_headers,
        )
        response = test_client.delete(
            f"/api/settings/users/{user.id}/permissions/{repo.id}",
            headers=admin_headers,
        )
        assert response.status_code == 204

    def test_non_admin_cannot_manage_permissions(
        self, test_client: TestClient, test_db
    ):
        """Non-admin user gets 403 on admin-only permission endpoints"""
        viewer = _make_user(test_db, "viewer6")
        token = create_access_token(data={"sub": viewer.username})
        headers = {"Authorization": f"Bearer {token}"}

        response = test_client.get(
            f"/api/settings/users/{viewer.id}/permissions", headers=headers
        )
        assert response.status_code == 403

    def test_get_my_permissions_shows_assigned_repos(
        self, test_client: TestClient, test_db, admin_headers, admin_user
    ):
        """GET /settings/permissions/me returns the user's own permissions"""
        repo = _make_repo(test_db, "my-repo")
        test_client.post(
            f"/api/settings/users/{admin_user.id}/permissions",
            json={"repository_id": repo.id, "role": "operator"},
            headers=admin_headers,
        )

        response = test_client.get(
            "/api/settings/permissions/me", headers=admin_headers
        )
        assert response.status_code == 200
        perms = response.json()
        assert len(perms) == 1
        assert perms[0]["repository_name"] == "my-repo"
        assert perms[0]["role"] == "operator"
        assert perms[0]["created_at"].endswith("+00:00")

    def test_admin_can_set_user_wildcard_repository_role(
        self, test_client: TestClient, test_db, admin_headers
    ):
        user = _make_user(test_db, "viewer7")

        response = test_client.put(
            f"/api/settings/users/{user.id}/permissions/scope",
            json={"all_repositories_role": "viewer"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["all_repositories_role"] == "viewer"

    def test_admin_can_clear_user_wildcard_repository_role(
        self, test_client: TestClient, test_db, admin_headers
    ):
        user = _make_user(test_db, "viewer8")
        user.all_repositories_role = "operator"
        test_db.commit()

        response = test_client.put(
            f"/api/settings/users/{user.id}/permissions/scope",
            json={"all_repositories_role": None},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["all_repositories_role"] is None

    def test_admin_can_get_user_wildcard_repository_role(
        self, test_client: TestClient, test_db, admin_headers
    ):
        user = _make_user(test_db, "viewer9")
        user.all_repositories_role = "operator"
        test_db.commit()

        response = test_client.get(
            f"/api/settings/users/{user.id}/permissions/scope",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["all_repositories_role"] == "operator"

    def test_admin_cannot_set_user_wildcard_role_above_global_role(
        self, test_client: TestClient, test_db, admin_headers
    ):
        user = _make_user(test_db, "viewer10", role="viewer")

        response = test_client.put(
            f"/api/settings/users/{user.id}/permissions/scope",
            json={"all_repositories_role": "operator"},
            headers=admin_headers,
        )
        assert response.status_code == 422
