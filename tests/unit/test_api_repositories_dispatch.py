from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository


@pytest.mark.unit
class TestRepositoryApiDispatch:
    def test_check_route_dispatches_through_borg_router(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(name="Repo", path="/tmp/repo", encryption="none", repository_type="local", borg_version=2)
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_router = Mock(check=AsyncMock())
        with patch("app.api.repositories.BorgRouter", return_value=fake_router) as mock_router, patch(
            "app.api.repositories.asyncio.create_task", return_value=object()
        ) as mock_create_task:
            response = test_client.post(
                f"/api/repositories/{repo.id}/check",
                json={"max_duration": 120},
                headers=admin_headers,
            )

            scheduled = mock_create_task.call_args.args[0]
            scheduled.close()

        assert response.status_code == 200
        mock_router.assert_called_once()
        fake_router.check.assert_called_once()

    def test_compact_route_dispatches_through_borg_router(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(name="Repo", path="/tmp/repo", encryption="none", repository_type="local", borg_version=2)
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_router = Mock(compact=AsyncMock())
        with patch("app.api.repositories.BorgRouter", return_value=fake_router) as mock_router, patch(
            "app.api.repositories.asyncio.create_task", return_value=object()
        ) as mock_create_task:
            response = test_client.post(
                f"/api/repositories/{repo.id}/compact",
                headers=admin_headers,
            )

            scheduled = mock_create_task.call_args.args[0]
            scheduled.close()

        assert response.status_code == 200
        mock_router.assert_called_once()
        fake_router.compact.assert_called_once()

    def test_prune_route_dispatches_through_borg_router(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(name="Repo", path="/tmp/repo", encryption="none", repository_type="local", borg_version=2)
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_router = Mock(prune=AsyncMock())
        with patch("app.api.repositories.BorgRouter", return_value=fake_router) as mock_router:
            response = test_client.post(
                f"/api/repositories/{repo.id}/prune",
                json={"keep_daily": 3, "dry_run": True},
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_router.assert_called_once()
        fake_router.prune.assert_awaited_once()

    def test_break_lock_route_dispatches_through_borg_router(self, test_client: TestClient, admin_headers, test_db):
        repo = Repository(name="Repo", path="/tmp/repo", encryption="none", repository_type="local", borg_version=2)
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_router = Mock(break_lock=AsyncMock(return_value={"success": True}))
        with patch("app.api.repositories.BorgRouter", return_value=fake_router) as mock_router:
            response = test_client.post(
                f"/api/repositories/{repo.id}/break-lock",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["message"] == "backend.success.repo.lockBroken"
        mock_router.assert_called_once()
        fake_router.break_lock.assert_awaited_once()
