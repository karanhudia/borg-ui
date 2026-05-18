from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.models import Repository, RepositoryWipeJob


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

    def test_execute_validates_preview_and_starts_background_job(
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
                "app.api.repositories.asyncio.create_task", return_value=object()
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
        create_task.assert_called_once()

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
