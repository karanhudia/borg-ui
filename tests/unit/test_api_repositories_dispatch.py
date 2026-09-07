from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, get_password_hash
from app.database.models import (
    Operation,
    Repository,
    SystemSettings,
    User,
    UserRepositoryPermission,
)


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

        # Phase 5: the route enqueues and the executor routes. BorgRouter is
        # called by `run_check` with the live repository row, so this asserts
        # the executor's routing rather than a dispatcher the route builds.
        from app.services.operations.executors import maintenance

        fake_router = Mock(check=AsyncMock())

        response = test_client.post(
            f"/api/repositories/{repo.id}/check",
            json={"max_duration": 120},
            headers=admin_headers,
        )

        assert response.status_code == 200
        operation_id = response.json()["job_id"]
        op = test_db.get(Operation, operation_id)
        assert op.kind == "check"
        assert op.params["max_duration"] == 120

        ctx = SimpleNamespace(
            db=test_db,
            operation=op,
            operation_id=op.id,
            repository_id=repo.id,
            kind="check",
            params=dict(op.params or {}),
            cancelled=lambda: False,
            log=lambda line: None,
        )
        with patch(
            "app.services.operations.executors.maintenance.BorgRouter",
            return_value=fake_router,
        ) as mock_router:
            await maintenance.run_check(ctx)

        mock_router.assert_called_once()
        routed_repo = mock_router.call_args.args[0]
        assert routed_repo.id == repo.id
        assert routed_repo.borg_version == repo.borg_version
        fake_router.check.assert_awaited_once_with(op.id)

    def test_check_route_accepts_guided_recovery_diagnosis_payload(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Broken Repo",
            path="/tmp/broken-repo",
            encryption="repokey",
            repository_type="local",
            borg_version=1,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            f"/api/repositories/{repo.id}/check",
            json={"max_duration": 0, "check_extra_flags": ""},
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["message"] == "backend.success.repo.checkJobStarted"

        op = test_db.get(Operation, body["job_id"])
        assert op.kind == "check"
        assert op.repository_id == repo.id
        # An empty flags string is normalised away, and spec 6.2 keeps the
        # inputs in params. `extra_flags` is dropped rather than stored as
        # None, so the service's own default still applies.
        assert op.params == {"max_duration": 0, "scheduled_check": False}

    @pytest.mark.asyncio
    async def test_compact_route_enqueues_and_the_executor_dispatches_through_borg_router(
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

        # Phase 5: the route enqueues and the executor routes. BorgRouter is
        # called by `run_compact` with the live repository row, so this
        # asserts the executor's routing rather than a dispatcher the route
        # builds.
        from app.services.operations.executors import maintenance

        response = test_client.post(
            f"/api/repositories/{repo.id}/compact",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        op = test_db.get(Operation, body["job_id"])
        assert op.kind == "compact"

        ctx = SimpleNamespace(
            db=test_db,
            operation=op,
            operation_id=op.id,
            repository_id=repo.id,
            kind="compact",
            params=dict(op.params or {}),
            cancelled=lambda: False,
            log=lambda line: None,
        )
        fake_router = Mock(compact=AsyncMock())
        with patch(
            "app.services.operations.executors.maintenance.BorgRouter",
            return_value=fake_router,
        ) as mock_router:
            await maintenance.run_compact(ctx)

        mock_router.assert_called_once()
        routed_repo = mock_router.call_args.args[0]
        assert routed_repo.id == repo.id
        assert routed_repo.borg_version == repo.borg_version
        fake_router.compact.assert_awaited_once_with(op.id)

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

    def test_prune_dry_run_response_includes_successful_log_output(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        repo = Repository(
            name="Repo Dry Run Logs",
            path="/tmp/repo-dry-run-logs",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        settings = SystemSettings(log_save_policy="failed_and_warnings")
        test_db.add_all([repo, settings])
        test_db.commit()
        test_db.refresh(repo)

        dry_run_logs = "\n".join(
            [
                '[stderr] {"type": "log_message", "message": "Keeping archive (rule: daily #1):            repo-2026-06-09      Tue, 2026-06-09 04:00:42 [abcdef0123456789]", "levelname": "INFO", "name": "borg.output.list"}',
                '[stderr] {"type": "log_message", "message": "Would prune:                                 repo-2026-06-08      Mon, 2026-06-08 22:24:37 [1234567890abcdef]", "levelname": "INFO", "name": "borg.output.list"}',
            ]
        )

        async def complete_prune_with_logs(job_id, *_args, **_kwargs):
            from app.services.operations.job_facade import MaintenanceJobFacade

            log_path = tmp_path / "prune-dry-run.log"
            log_path.write_text(dry_run_logs, encoding="utf-8")
            job = MaintenanceJobFacade(test_db, test_db.get(Operation, job_id))
            job.status = "completed"
            job.log_file_path = str(log_path)
            job.has_logs = True
            test_db.commit()

        fake_router = Mock(prune=AsyncMock(side_effect=complete_prune_with_logs))
        with patch("app.api.repositories.BorgRouter", return_value=fake_router):
            response = test_client.post(
                f"/api/repositories/{repo.id}/prune",
                json={"keep_daily": 3, "dry_run": True},
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["dry_run"] is True
        assert body["prune_result"]["success"] is True
        assert "Keeping archive (rule: daily #1)" in body["prune_result"]["stdout"]
        assert "Would prune:" in body["prune_result"]["stdout"]

    @pytest.mark.asyncio
    async def test_prune_route_enqueues_and_the_executor_dispatches_through_borg_router(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo Background Prune",
            path="/tmp/repo-background-prune",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Phase 5: the route enqueues and the executor routes. BorgRouter is
        # called by `run_prune` with the live repository row, so this asserts
        # the executor's routing rather than a dispatcher the route builds.
        from app.services.operations.executors import maintenance

        response = test_client.post(
            f"/api/repositories/{repo.id}/prune",
            json={
                "keep_hourly": 1,
                "keep_daily": 3,
                "keep_weekly": 2,
                "keep_monthly": 1,
                "keep_quarterly": 0,
                "keep_yearly": 0,
                "dry_run": False,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["message"] == "backend.success.repo.pruneJobStarted"
        op = test_db.get(Operation, body["job_id"])
        assert op.kind == "prune"
        assert op.params["keep_daily"] == 3

        ctx = SimpleNamespace(
            db=test_db,
            operation=op,
            operation_id=op.id,
            repository_id=repo.id,
            kind="prune",
            params=dict(op.params or {}),
            cancelled=lambda: False,
            log=lambda line: None,
        )
        fake_router = Mock(prune=AsyncMock())
        with patch(
            "app.services.operations.executors.maintenance.BorgRouter",
            return_value=fake_router,
        ) as mock_router:
            await maintenance.run_prune(ctx)

        mock_router.assert_called_once()
        routed_repo = mock_router.call_args.args[0]
        assert routed_repo.id == repo.id
        assert routed_repo.borg_version == repo.borg_version
        fake_router.prune.assert_awaited_once_with(op.id, 1, 3, 2, 1, 0, 0, False)

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

    def test_break_lock_route_allows_repository_operator_access(
        self, test_client: TestClient, test_db
    ):
        repo = Repository(
            name="Repo",
            path="/tmp/repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        user = User(
            username="repo-operator",
            password_hash=get_password_hash("pass"),
            is_active=True,
            role="operator",
        )
        test_db.add_all([repo, user])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(user)
        test_db.add(
            UserRepositoryPermission(
                user_id=user.id,
                repository_id=repo.id,
                role="operator",
                created_at=datetime.now(timezone.utc),
            )
        )
        test_db.commit()
        headers = {
            "X-Borg-Authorization": f"Bearer {create_access_token(data={'sub': user.username})}"
        }

        fake_router = Mock(break_lock=AsyncMock(return_value={"success": True}))
        with patch("app.api.repositories.BorgRouter", return_value=fake_router):
            response = test_client.post(
                f"/api/repositories/{repo.id}/break-lock",
                headers=headers,
            )

        assert response.status_code == 200
        fake_router.break_lock.assert_awaited_once()

    def test_break_lock_route_rejects_when_system_setting_disabled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Repo",
            path="/tmp/repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        settings = SystemSettings()
        settings.lock_breaking_enabled = False
        test_db.add_all([repo, settings])
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

        assert response.status_code == 403
        assert response.json()["detail"] == {
            "key": "backend.errors.repo.lockBreakingDisabled"
        }
        mock_router.assert_not_called()
        fake_router.break_lock.assert_not_awaited()

    def test_break_lock_route_requires_operator_access(
        self, test_client: TestClient, auth_headers, test_db
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
                headers=auth_headers,
            )

        assert response.status_code == 403
        mock_router.assert_not_called()
        fake_router.break_lock.assert_not_awaited()
