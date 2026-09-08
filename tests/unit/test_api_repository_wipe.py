from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository, RepositoryWipeJob, SystemSettings


def _create_repository(test_db, *, name: str = "Primary") -> Repository:
    repo = Repository(
        name=name,
        path=f"/tmp/{name.lower()}",
        encryption="none",
        repository_type="local",
        borg_version=1,
        archive_count=2,
        total_size="12 MB",
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestRepositoryWipeApi:
    def test_preview_requires_global_admin(
        self, test_client: TestClient, operator_headers, test_db
    ):
        repo = _create_repository(test_db)

        response = test_client.post(
            f"/api/repositories/{repo.id}/wipe-preview",
            json={"run_compact": True},
            headers=operator_headers,
        )

        assert response.status_code == 403
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.repo.adminAccessRequired"
        )

    def test_preview_returns_preview_payload(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        preview_payload = {
            "id": 44,
            "repository_id": repo.id,
            "status": "previewed",
            "phase": "preview",
            "archive_count": 2,
            "archive_fingerprint": "sha256:abc",
            "archives": [{"identity": "archive-a", "name": "archive-a"}],
            "blocked": False,
            "blocking_reason": None,
            "protected_archives": [],
            "run_compact": True,
            "dry_run_output": "Would delete archive-a",
            "has_logs": False,
        }

        with patch(
            "app.api.repositories.repository_wipe_service.create_preview",
            new=AsyncMock(return_value=preview_payload),
        ) as create_preview:
            response = test_client.post(
                f"/api/repositories/{repo.id}/wipe-preview",
                json={"run_compact": True},
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json() == preview_payload
        create_preview.assert_awaited_once()

    def test_execute_validates_preview_and_queues_the_wipe(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        job = SimpleNamespace(
            id=45,
            repository_id=repo.id,
            status="pending",
            phase="queued",
            started_at=None,
            completed_at=None,
            error_message=None,
            progress=0,
            progress_message="Queued",
            has_logs=False,
            archive_count=2,
            archive_fingerprint="sha256:abc",
            run_compact=True,
        )
        serialized = {
            "id": 45,
            "repository_id": repo.id,
            "status": "pending",
            "phase": "queued",
            "progress": 0,
            "progress_message": "Queued",
            "archive_count": 2,
            "archive_fingerprint": "sha256:abc",
            "run_compact": True,
            "has_logs": False,
        }

        def close_background_coroutine(coro):
            coro.close()
            return object()

        with (
            patch(
                "app.api.repositories.repository_wipe_service.start_execution",
                new=AsyncMock(return_value=job),
            ) as start_execution,
            patch(
                "app.api.repositories.repository_wipe_service.serialize_job",
                return_value=serialized,
            ),
            patch(
                "app.api.repositories.asyncio.create_task",
                side_effect=close_background_coroutine,
            ) as create_task,
        ):
            response = test_client.post(
                f"/api/repositories/{repo.id}/wipe",
                json={
                    "preview_id": 44,
                    "preview_fingerprint": "sha256:abc",
                    "confirmation_phrase": "WIPE Primary",
                    "understood": True,
                    "run_compact": True,
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json() == serialized
        start_execution.assert_awaited_once()
        # Phase 6: the confirm route only enqueues. The runner dispatches the
        # wipe (spec 7.1), so the route spawns nothing of its own.
        create_task.assert_not_called()

    def test_status_returns_logs_for_admin(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        job = RepositoryWipeJob(
            repository_id=repo.id,
            repository_path=repo.path,
            repository_name=repo.name,
            borg_version=1,
            status="completed",
            phase="completed",
            archive_count=2,
            archive_fingerprint="sha256:abc",
            run_compact=True,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100,
            has_logs=False,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/repositories/{repo.id}/wipe-jobs/{job.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == job.id
        assert body["status"] == "completed"
        assert body["repository_id"] == repo.id

    def test_status_applies_log_save_policy(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        settings = test_db.query(SystemSettings).first()
        if settings is None:
            settings = SystemSettings()
            test_db.add(settings)
        settings.log_save_policy = "failed_only"
        repo = _create_repository(test_db)
        log_file = tmp_path / "wipe.log"
        log_file.write_text("successful wipe log", encoding="utf-8")
        job = RepositoryWipeJob(
            repository_id=repo.id,
            repository_path=repo.path,
            repository_name=repo.name,
            borg_version=1,
            status="completed",
            phase="completed",
            archive_count=2,
            archive_fingerprint="sha256:abc",
            run_compact=True,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100,
            log_file_path=str(log_file),
            has_logs=True,
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/{repo.id}/wipe-jobs/{job.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["has_logs"] is False
        assert body["logs"] == ""

    def test_status_returns_error_message_when_policy_treats_it_as_log(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = test_db.query(SystemSettings).first()
        if settings is None:
            settings = SystemSettings()
            test_db.add(settings)
        settings.log_save_policy = "failed_only"
        repo = _create_repository(test_db)
        job = RepositoryWipeJob(
            repository_id=repo.id,
            repository_path=repo.path,
            repository_name=repo.name,
            borg_version=1,
            status="failed",
            phase="failed",
            archive_count=2,
            archive_fingerprint="sha256:abc",
            run_compact=True,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=40,
            error_message="Repository wipe failed before log file creation",
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/{repo.id}/wipe-jobs/{job.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["has_logs"] is True
        assert body["logs"] == "Repository wipe failed before log file creation"

    def test_cancel_preview_records_cancelled_audit_state(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        cancelled = {
            "id": 46,
            "repository_id": repo.id,
            "status": "cancelled",
            "phase": "cancelled",
            "progress": 0,
            "progress_message": "Wipe preview cancelled",
        }

        with (
            patch(
                "app.api.repositories.repository_wipe_service.cancel_preview",
                new=Mock(return_value=cancelled),
            ) as cancel_preview,
        ):
            response = test_client.post(
                f"/api/repositories/{repo.id}/wipe-jobs/46/cancel",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json() == cancelled
        cancel_preview.assert_called_once()


def _operation(test_db, repo, *, kind, status, run_id="run-1", params=None):
    from app.database.models import Operation
    from app.services.operations.vocab import category_for

    op = Operation(
        repository_id=repo.id,
        kind=kind,
        category=category_for(kind),
        status=status,
        trigger="manual",
        priority=0,
        run_id=run_id,
        params=params or {},
    )
    test_db.add(op)
    test_db.commit()
    test_db.refresh(op)
    return op


@pytest.mark.unit
class TestRepositoryWipeOperations:
    """Phase 6: wipe on the operations table (spec 6.2, 6.3, 7.1)."""

    def test_preview_is_rejected_while_a_check_operation_runs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        _operation(test_db, repo, kind="check", status="running")

        response = test_client.post(
            f"/api/repositories/{repo.id}/wipe-preview",
            json={"run_compact": True},
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.repo.operationAlreadyRunning"
        )

    def test_preview_is_rejected_while_a_check_operation_is_queued(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        _operation(test_db, repo, kind="check", status="queued")

        response = test_client.post(
            f"/api/repositories/{repo.id}/wipe-preview",
            json={"run_compact": True},
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.repo.operationAlreadyRunning"
        )

    def test_preview_is_rejected_while_a_wipe_operation_is_queued(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        _operation(test_db, repo, kind="wipe", status="queued")

        response = test_client.post(
            f"/api/repositories/{repo.id}/wipe-preview",
            json={"run_compact": True},
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"] == "backend.errors.repo.wipeAlreadyRunning"
        )

    def test_an_rclone_sync_operation_does_not_block_a_wipe(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """rclone_sync takes the rclone lock scope, not the repository lane
        (spec 7.2), so it is not a conflicting kind."""
        repo = _create_repository(test_db)
        _operation(test_db, repo, kind="rclone_sync", status="running")

        with (
            patch.object(
                __import__("app.core.borg_router", fromlist=["BorgRouter"]).BorgRouter,
                "list_archives",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = test_client.post(
                f"/api/repositories/{repo.id}/wipe-preview",
                json={"run_compact": True},
                headers=admin_headers,
            )

        assert response.status_code == 200

    def test_wipe_job_route_serves_an_operation(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.details import wipe_details

        repo = _create_repository(test_db)
        op = _operation(
            test_db,
            repo,
            kind="wipe",
            status="running",
            params={"preview_id": 1, "run_compact": True},
        )
        op.progress_percent = 75
        op.progress_message = "Compacting repository after wipe"
        details = wipe_details(test_db, op)
        details.phase = "compact"
        details.archive_count = 4
        details.archive_fingerprint = "sha256:abc"
        details.archive_manifest_json = '[{"identity": "a"}]'
        details.protected_archives_json = "[]"
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/{repo.id}/wipe-jobs/{op.id}",
            headers=admin_headers,
        )

        body = response.json()
        assert response.status_code == 200
        assert body["id"] == op.id
        assert body["status"] == "running"
        assert body["phase"] == "compact"
        assert body["progress"] == 75
        assert body["archive_count"] == 4
        assert body["archive_fingerprint"] == "sha256:abc"
        assert body["archives"] == [{"identity": "a"}]

    def test_wipe_job_route_still_serves_a_pre_phase_6_row(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        job = RepositoryWipeJob(
            repository_id=repo.id,
            status="completed",
            phase="completed",
            archive_count=2,
            archive_manifest_json="[]",
            protected_archives_json="[]",
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/repositories/{repo.id}/wipe-jobs/{job.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_cancelling_a_queued_wipe_operation_cancels_the_operation(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        op = _operation(
            test_db, repo, kind="wipe", status="queued", params={"preview_id": 1}
        )

        response = test_client.post(
            f"/api/repositories/{repo.id}/wipe-jobs/{op.id}/cancel",
            headers=admin_headers,
        )

        test_db.refresh(op)
        assert response.status_code == 200
        assert op.status == "cancelled"

    def test_cancelling_a_running_wipe_operation_is_refused(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repository(test_db)
        op = _operation(
            test_db, repo, kind="wipe", status="running", params={"preview_id": 1}
        )

        response = test_client.post(
            f"/api/repositories/{repo.id}/wipe-jobs/{op.id}/cancel",
            headers=admin_headers,
        )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.repo.wipeCannotCancelRunning"
        )

    def test_running_jobs_summary_reports_a_wipe_operation(
        self, test_client: TestClient, admin_headers, test_db
    ):
        from app.services.operations.details import wipe_details

        repo = _create_repository(test_db)
        op = _operation(
            test_db, repo, kind="wipe", status="running", params={"preview_id": 1}
        )
        wipe_details(test_db, op).phase = "delete"
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/{repo.id}/running-jobs", headers=admin_headers
        )

        body = response.json()
        assert response.status_code == 200
        assert body["has_running_jobs"] is True
        assert body["wipe_job"]["id"] == op.id
        assert body["wipe_job"]["status"] == "running"
        assert body["wipe_job"]["phase"] == "delete"
