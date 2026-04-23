from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository


@pytest.mark.unit
class TestRepositoryApiDispatch:
    @pytest.mark.asyncio
    async def test_check_route_dispatches_through_borg_router(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo",
            path="/tmp/repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        dispatched = {}
        fake_router = Mock(check=AsyncMock())

        def fake_start(db, repository, job_model, **kwargs):
            dispatched["dispatcher"] = kwargs["dispatcher"]
            return SimpleNamespace(id=11, repository_id=repository.id, status="pending")

        with (
            patch(
                "app.api.repositories.BorgRouter", return_value=fake_router
            ) as mock_router,
            patch(
                "app.api.repositories.start_background_maintenance_job",
                side_effect=fake_start,
            ),
        ):
            response = test_client.post(
                f"/api/repositories/{repo.id}/check",
                json={"max_duration": 120},
                headers=admin_headers,
            )
            await dispatched["dispatcher"](SimpleNamespace(id=99))

        assert response.status_code == 200
        mock_router.assert_called_once()
        routed_repo = mock_router.call_args.args[0]
        assert not isinstance(routed_repo, Repository)
        assert routed_repo.id == repo.id
        assert routed_repo.borg_version == repo.borg_version
        fake_router.check.assert_awaited_once_with(99)

    @pytest.mark.asyncio
    async def test_compact_route_dispatches_through_borg_router(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo",
            path="/tmp/repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        dispatched = {}
        fake_router = Mock(compact=AsyncMock())

        def fake_start(db, repository, job_model, **kwargs):
            dispatched["dispatcher"] = kwargs["dispatcher"]
            return SimpleNamespace(id=12, repository_id=repository.id, status="pending")

        with (
            patch(
                "app.api.repositories.BorgRouter", return_value=fake_router
            ) as mock_router,
            patch(
                "app.api.repositories.start_background_maintenance_job",
                side_effect=fake_start,
            ),
        ):
            response = test_client.post(
                f"/api/repositories/{repo.id}/compact",
                headers=admin_headers,
            )
            await dispatched["dispatcher"](SimpleNamespace(id=77))

        assert response.status_code == 200
        mock_router.assert_called_once()
        routed_repo = mock_router.call_args.args[0]
        assert not isinstance(routed_repo, Repository)
        assert routed_repo.id == repo.id
        assert routed_repo.borg_version == repo.borg_version
        fake_router.compact.assert_awaited_once_with(77)

    def test_prune_route_dispatches_through_borg_router(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo",
            path="/tmp/repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_router = Mock(prune=AsyncMock())
        with patch(
            "app.api.repositories.BorgRouter", return_value=fake_router
        ) as mock_router:
            response = test_client.post(
                f"/api/repositories/{repo.id}/prune",
                json={"keep_daily": 3, "dry_run": True},
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_router.assert_called_once()
        fake_router.prune.assert_awaited_once()

    def test_break_lock_route_dispatches_through_borg_router(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo",
            path="/tmp/repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        fake_router = Mock(break_lock=AsyncMock(return_value={"success": True}))
        with patch(
            "app.api.repositories.BorgRouter", return_value=fake_router
        ) as mock_router:
            response = test_client.post(
                f"/api/repositories/{repo.id}/break-lock",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["message"] == "backend.success.repo.lockBroken"
        mock_router.assert_called_once()
        fake_router.break_lock.assert_awaited_once()
