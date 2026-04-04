from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import repositories as repositories_api
from app.database.models import (
    CheckJob,
    CompactJob,
    PruneJob,
    Repository,
    SSHConnection,
    SystemSettings,
    UserRepositoryPermission,
)


def _create_repo(test_db, name: str, path: str, **kwargs) -> Repository:
    repo = Repository(name=name, path=path, encryption="none", repository_type="local", **kwargs)
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestRepositoryRouteContracts:
    def test_get_repositories_filters_to_explicit_permissions(
        self, test_client: TestClient, auth_headers, test_db, test_user
    ):
        allowed = _create_repo(test_db, "Allowed", "/repos/allowed")
        _create_repo(test_db, "Denied", "/repos/denied")
        permission = UserRepositoryPermission(user_id=test_user.id, repository_id=allowed.id, role="viewer")
        test_db.add(permission)
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert [repo["id"] for repo in body["repositories"]] == [allowed.id]

    def test_get_check_jobs_missing_repository_returns_empty_list(self, test_client: TestClient, admin_headers):
        response = test_client.get("/api/repositories/99999/check-jobs", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == {"jobs": []}

    def test_get_compact_jobs_missing_repository_returns_empty_list(self, test_client: TestClient, admin_headers):
        response = test_client.get("/api/repositories/99999/compact-jobs", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == {"jobs": []}

    def test_get_running_jobs_missing_repository_returns_empty_shape(self, test_client: TestClient, admin_headers):
        response = test_client.get("/api/repositories/99999/running-jobs", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == repositories_api._empty_running_jobs_response()

    def test_get_running_jobs_returns_all_running_maintenance_jobs(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")
        test_db.add_all(
            [
                CheckJob(
                    repository_id=repo.id,
                    status="running",
                    progress=35,
                    progress_message="Checking segments",
                    started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                ),
                CompactJob(
                    repository_id=repo.id,
                    status="running",
                    progress=60,
                    progress_message="Compacting",
                    started_at=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
                ),
                PruneJob(
                    repository_id=repo.id,
                    status="running",
                    started_at=datetime(2026, 1, 1, 12, 10, tzinfo=timezone.utc),
                ),
            ]
        )
        test_db.commit()

        response = test_client.get(f"/api/repositories/{repo.id}/running-jobs", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["has_running_jobs"] is True
        assert body["check_job"]["progress"] == 35
        assert body["compact_job"]["progress"] == 60
        assert body["prune_job"]["id"] is not None

    def test_get_check_job_status_reads_log_file(self, test_client: TestClient, admin_headers, test_db, tmp_path):
        repo = _create_repo(test_db, "Repo", "/repos/main")
        log_path = tmp_path / "check.log"
        log_path.write_text("first line\nsecond line\n", encoding="utf-8")
        job = CheckJob(repository_id=repo.id, status="completed", log_file_path=str(log_path), has_logs=True)
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(f"/api/repositories/check-jobs/{job.id}", headers=admin_headers)

        assert response.status_code == 200
        assert response.json()["logs"] == "first line\nsecond line\n"

    def test_update_check_schedule_disables_cron_and_clears_next_run(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(
            test_db,
            "Repo",
            "/repos/main",
            check_cron_expression="0 1 * * *",
            next_scheduled_check=datetime(2026, 1, 2, 1, 0),
        )

        response = test_client.put(
            f"/api/repositories/{repo.id}/check-schedule",
            json={"cron_expression": ""},
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()["repository"]
        assert body["check_cron_expression"] is None
        assert body["next_scheduled_check"] is None

    def test_get_check_schedule_reports_enabled_state(self, test_client: TestClient, admin_headers, test_db):
        repo = _create_repo(
            test_db,
            "Repo",
            "/repos/main",
            check_cron_expression="0 3 * * *",
            check_max_duration=120,
            notify_on_check_success=True,
            notify_on_check_failure=False,
        )

        response = test_client.get(f"/api/repositories/{repo.id}/check-schedule", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["check_cron_expression"] == "0 3 * * *"
        assert body["check_max_duration"] == 120
        assert body["notify_on_check_success"] is True


@pytest.mark.unit
class TestRepositoryHelperContracts:
    def test_get_connection_details_returns_expected_fields(self, test_db):
        connection = SSHConnection(
            host="example.com",
            username="borg",
            port=2222,
            ssh_key_id=7,
            ssh_path_prefix="/volume1",
        )
        test_db.add(connection)
        test_db.commit()
        test_db.refresh(connection)

        details = repositories_api.get_connection_details(connection.id, test_db)

        assert details == {
            "host": "example.com",
            "username": "borg",
            "port": 2222,
            "ssh_key_id": 7,
            "ssh_path_prefix": "/volume1",
        }

    @pytest.mark.asyncio
    async def test_update_repository_stats_updates_archive_count_size_and_last_backup(self, test_db):
        repo = _create_repo(test_db, "Repo", "/repos/main", passphrase="secret", bypass_lock=False)
        settings = SystemSettings(bypass_lock_on_list=True)
        test_db.add(settings)
        test_db.commit()

        list_payload = {
            "success": True,
            "stdout": '{"archives":[{"name":"old","time":"2024-01-01T10:00:00"},{"name":"new","time":"2024-02-01T12:00:00Z"}]}',
        }
        process = Mock()
        process.returncode = 0
        process.communicate = AsyncMock(
            return_value=(
                b'{"cache":{"stats":{"unique_csize": 2097152}}}',
                b"",
            )
        )

        with patch.object(repositories_api.borg, "list_archives", AsyncMock(return_value=list_payload)) as mock_list, patch(
            "app.api.repositories.asyncio.create_subprocess_exec",
            AsyncMock(return_value=process),
        ):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is True
        assert repo.archive_count == 2
        assert repo.total_size == "2.00 MB"
        assert repo.last_backup == datetime(2024, 2, 1, 12, 0)
        mock_list.assert_awaited_once()
        assert mock_list.await_args.kwargs["bypass_lock"] is True

    @pytest.mark.asyncio
    async def test_update_repository_stats_returns_false_on_unexpected_exception(self, test_db):
        repo = _create_repo(test_db, "Repo", "/repos/main")

        with patch.object(repositories_api.borg, "list_archives", AsyncMock(side_effect=RuntimeError("boom"))):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is False
