"""
Unit tests for repository-level RBAC enforcement.
"""
import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from app.database.models import User, Repository, UserRepositoryPermission
from app.core.security import check_repo_access, get_password_hash


def _make_user(db, username, role='viewer'):
    user = User(username=username, password_hash=get_password_hash('x'), is_active=True, role=role)
    db.add(user); db.commit(); db.refresh(user)
    return user


def _make_repo(db, name='test-repo'):
    repo = Repository(name=name, path=f'/backup/{name}', encryption='none')
    db.add(repo); db.commit(); db.refresh(repo)
    return repo


def _grant(db, user, repo, role):
    perm = UserRepositoryPermission(
        user_id=user.id, repository_id=repo.id, role=role,
        created_at=datetime.now(timezone.utc),
    )
    db.add(perm); db.commit()


@pytest.mark.unit
class TestCheckRepoAccess:

    def test_admin_always_passes_without_permission(self, test_db):
        """Admin bypasses per-repo check even with no explicit permission row."""
        admin = _make_user(test_db, 'adm_a1', role='admin')
        repo = _make_repo(test_db, 'adm-repo1')
        check_repo_access(test_db, admin, repo, 'operator')  # must not raise

    def test_viewer_with_viewer_permission_can_view(self, test_db):
        user = _make_user(test_db, 'vwr_b1', role='viewer')
        repo = _make_repo(test_db, 'vwr-repo1')
        _grant(test_db, user, repo, 'viewer')
        check_repo_access(test_db, user, repo, 'viewer')  # must not raise

    def test_viewer_blocked_from_operator_action(self, test_db):
        user = _make_user(test_db, 'vwr_c1', role='viewer')
        repo = _make_repo(test_db, 'vwr-repo2')
        _grant(test_db, user, repo, 'viewer')
        with pytest.raises(HTTPException) as exc:
            check_repo_access(test_db, user, repo, 'operator')
        assert exc.value.status_code == 403

    def test_operator_with_operator_permission_can_operate(self, test_db):
        user = _make_user(test_db, 'op_d1', role='operator')
        repo = _make_repo(test_db, 'op-repo1')
        _grant(test_db, user, repo, 'operator')
        check_repo_access(test_db, user, repo, 'operator')  # must not raise

    def test_wildcard_repository_role_grants_future_repo_access(self, test_db):
        user = _make_user(test_db, 'wildcard_op1', role='viewer')
        user.all_repositories_role = 'operator'
        test_db.commit()
        repo = _make_repo(test_db, 'wildcard-repo1')
        check_repo_access(test_db, user, repo, 'operator')  # must not raise

    def test_user_with_no_permission_blocked(self, test_db):
        """No permission row at all → 403 even for viewer-level action."""
        user = _make_user(test_db, 'np_e1', role='viewer')
        repo = _make_repo(test_db, 'np-repo1')
        with pytest.raises(HTTPException) as exc:
            check_repo_access(test_db, user, repo, 'viewer')
        assert exc.value.status_code == 403


@pytest.mark.unit
class TestRepositoriesFilter:

    def test_admin_sees_all_repos(self, test_client, test_db, admin_headers):
        """Admin gets all repositories regardless of permission rows."""
        _make_repo(test_db, 'filter-repo1')
        _make_repo(test_db, 'filter-repo2')
        response = test_client.get('/api/repositories/', headers=admin_headers)
        assert response.status_code == 200
        names = [r['name'] for r in response.json()['repositories']]
        assert 'filter-repo1' in names
        assert 'filter-repo2' in names

    def test_viewer_sees_only_permitted_repos(self, test_client, test_db):
        """Viewer only sees repos they have an explicit permission for."""
        from app.core.security import create_access_token
        user = _make_user(test_db, 'filter-vwr1', role='viewer')
        repo_a = _make_repo(test_db, 'filter-visible')
        _make_repo(test_db, 'filter-hidden')
        _grant(test_db, user, repo_a, 'viewer')

        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.get('/api/repositories/', headers=headers)
        assert response.status_code == 200
        names = [r['name'] for r in response.json()['repositories']]
        assert 'filter-visible' in names
        assert 'filter-hidden' not in names

    def test_viewer_with_no_permissions_sees_empty_list(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'filter-vwr2', role='viewer')
        _make_repo(test_db, 'filter-some-repo')

        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.get('/api/repositories/', headers=headers)
        assert response.status_code == 200
        assert response.json()['repositories'] == []

    def test_user_with_wildcard_role_sees_new_repositories(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'filter-vwr3', role='viewer')
        user.all_repositories_role = 'viewer'
        test_db.commit()
        _make_repo(test_db, 'filter-wildcard-visible')

        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.get('/api/repositories/', headers=headers)
        assert response.status_code == 200
        names = [r['name'] for r in response.json()['repositories']]
        assert 'filter-wildcard-visible' in names


@pytest.mark.unit
class TestRestoreProtection:

    def test_viewer_with_permission_can_restore(self, test_client, test_db):
        """Viewer with explicit permission can call preview (viewer-level action)."""
        from app.core.security import create_access_token
        from unittest.mock import patch, AsyncMock
        user = _make_user(test_db, 'rst-vwr1', role='viewer')
        repo = _make_repo(test_db, 'rst-repo1')
        _grant(test_db, user, repo, 'viewer')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        with patch('app.api.restore.borg.extract_archive', new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = {"success": True, "stdout": "", "stderr": ""}
            response = test_client.post(
                '/api/restore/preview',
                json={
                    "repository": repo.path,
                    "archive": "test-archive",
                    "paths": ["/"],
                    "destination": "/tmp/restore",
                    "repository_id": repo.id,
                },
                headers=headers,
            )
        assert response.status_code != 403

    def test_no_permission_cannot_restore(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'rst-np1', role='viewer')
        repo = _make_repo(test_db, 'rst-repo2')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.post(
            '/api/restore/preview',
            json={
                "repository": repo.path,
                "archive": "test-archive",
                "paths": ["/"],
                "destination": "/tmp/restore",
                "repository_id": repo.id,
            },
            headers=headers,
        )
        assert response.status_code == 403


@pytest.mark.unit
class TestBackupProtection:

    def test_operator_with_permission_can_start_backup(self, test_client, test_db):
        from app.core.security import create_access_token
        from unittest.mock import patch, AsyncMock
        user = _make_user(test_db, 'bkp-op1', role='operator')
        repo = _make_repo(test_db, 'bkp-repo1')
        _grant(test_db, user, repo, 'operator')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        with patch('asyncio.create_task'):
            response = test_client.post(
                '/api/backup/start',
                json={"repository": repo.path},
                headers=headers,
            )
        assert response.status_code != 403

    def test_viewer_cannot_start_backup(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'bkp-vwr1', role='viewer')
        repo = _make_repo(test_db, 'bkp-repo2')
        _grant(test_db, user, repo, 'viewer')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.post(
            '/api/backup/start',
            json={"repository": repo.path},
            headers=headers,
        )
        assert response.status_code == 403

    def test_no_permission_cannot_start_backup(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'bkp-np1', role='viewer')
        repo = _make_repo(test_db, 'bkp-repo3')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.post(
            '/api/backup/start',
            json={"repository": repo.path},
            headers=headers,
        )
        assert response.status_code == 403


@pytest.mark.unit
class TestArchiveProtection:

    def test_viewer_can_list_archives(self, test_client, test_db):
        from app.core.security import create_access_token
        from unittest.mock import patch, AsyncMock
        user = _make_user(test_db, 'arc-vwr1', role='viewer')
        repo = _make_repo(test_db, 'arc-repo1')
        _grant(test_db, user, repo, 'viewer')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        with patch('app.api.archives.borg.list_archives', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {"success": True, "stdout": "[]", "stderr": ""}
            response = test_client.get(
                f'/api/archives/list?repository={repo.path}',
                headers=headers,
            )
        assert response.status_code != 403

    def test_no_permission_cannot_list_archives(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'arc-np1', role='viewer')
        repo = _make_repo(test_db, 'arc-repo2')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.get(
            f'/api/archives/list?repository={repo.path}',
            headers=headers,
        )
        assert response.status_code == 403

    def test_viewer_cannot_delete_archive(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'arc-vwr2', role='viewer')
        repo = _make_repo(test_db, 'arc-repo3')
        _grant(test_db, user, repo, 'viewer')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.delete(
            f'/api/archives/some-archive?repository={repo.path}',
            headers=headers,
        )
        assert response.status_code == 403

    def test_operator_can_delete_archive(self, test_client, test_db):
        from app.core.security import create_access_token
        from unittest.mock import patch, AsyncMock
        user = _make_user(test_db, 'arc-op1', role='operator')
        repo = _make_repo(test_db, 'arc-repo4')
        _grant(test_db, user, repo, 'operator')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        with patch('asyncio.create_task'):
            response = test_client.delete(
                f'/api/archives/some-archive?repository={repo.path}',
                headers=headers,
            )
        assert response.status_code != 403


@pytest.mark.unit
class TestScheduleProtection:

    def test_operator_with_permission_can_create_schedule(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'sch-op1', role='operator')
        repo = _make_repo(test_db, 'sch-repo1')
        _grant(test_db, user, repo, 'operator')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.post(
            '/api/schedule/',
            json={
                "name": "test-schedule",
                "cron_expression": "0 2 * * *",
                "repository_ids": [repo.id],
            },
            headers=headers,
        )
        assert response.status_code != 403

    def test_viewer_cannot_create_schedule(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'sch-vwr1', role='viewer')
        repo = _make_repo(test_db, 'sch-repo2')
        _grant(test_db, user, repo, 'viewer')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.post(
            '/api/schedule/',
            json={
                "name": "test-schedule",
                "cron_expression": "0 2 * * *",
                "repository_ids": [repo.id],
            },
            headers=headers,
        )
        assert response.status_code == 403

    def test_no_permission_cannot_create_schedule(self, test_client, test_db):
        from app.core.security import create_access_token
        user = _make_user(test_db, 'sch-np1', role='viewer')
        repo = _make_repo(test_db, 'sch-repo3')
        token = create_access_token(data={"sub": user.username})
        headers = {"Authorization": f"Bearer {token}"}
        response = test_client.post(
            '/api/schedule/',
            json={
                "name": "test-schedule",
                "cron_expression": "0 2 * * *",
                "repository_ids": [repo.id],
            },
            headers=headers,
        )
        assert response.status_code == 403
