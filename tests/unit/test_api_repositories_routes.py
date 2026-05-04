import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

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
    repo = Repository(
        name=name, path=path, encryption="none", repository_type="local", **kwargs
    )
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
        permission = UserRepositoryPermission(
            user_id=test_user.id, repository_id=allowed.id, role="viewer"
        )
        test_db.add(permission)
        test_db.commit()

        response = test_client.get("/api/repositories/", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert [repo["id"] for repo in body["repositories"]] == [allowed.id]

    def test_get_check_jobs_missing_repository_returns_empty_list(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.get(
            "/api/repositories/99999/check-jobs", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json() == {"jobs": []}

    def test_get_compact_jobs_missing_repository_returns_empty_list(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.get(
            "/api/repositories/99999/compact-jobs", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json() == {"jobs": []}

    def test_get_running_jobs_missing_repository_returns_empty_shape(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.get(
            "/api/repositories/99999/running-jobs", headers=admin_headers
        )

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

        response = test_client.get(
            f"/api/repositories/{repo.id}/running-jobs", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["has_running_jobs"] is True
        assert body["check_job"]["progress"] == 35
        assert body["compact_job"]["progress"] == 60
        assert body["prune_job"]["id"] is not None

    def test_get_check_job_status_reads_log_file(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")
        log_path = tmp_path / "check.log"
        log_path.write_text("first line\nsecond line\n", encoding="utf-8")
        job = CheckJob(
            repository_id=repo.id,
            status="completed",
            log_file_path=str(log_path),
            has_logs=True,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/repositories/check-jobs/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["logs"] == "first line\nsecond line\n"

    def test_get_compact_job_status_reads_log_file(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")
        log_path = tmp_path / "compact.log"
        log_path.write_text("compact output\n", encoding="utf-8")
        job = CompactJob(
            repository_id=repo.id,
            status="completed",
            log_file_path=str(log_path),
            has_logs=True,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/repositories/compact-jobs/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["logs"] == "compact output\n"

    def test_get_prune_job_status_reads_log_file(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")
        log_path = tmp_path / "prune.log"
        log_path.write_text("prune output\n", encoding="utf-8")
        job = PruneJob(
            repository_id=repo.id,
            status="completed",
            log_file_path=str(log_path),
            has_logs=True,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/repositories/prune-jobs/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["logs"] == "prune output\n"

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

    def test_get_check_schedule_reports_enabled_state(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(
            test_db,
            "Repo",
            "/repos/main",
            check_cron_expression="0 3 * * *",
            check_max_duration=120,
            notify_on_check_success=True,
            notify_on_check_failure=False,
        )

        response = test_client.get(
            f"/api/repositories/{repo.id}/check-schedule", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["check_cron_expression"] == "0 3 * * *"
        assert body["check_max_duration"] == 120
        assert body["notify_on_check_success"] is True

    def test_update_check_schedule_stores_timezone(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")

        response = test_client.put(
            f"/api/repositories/{repo.id}/check-schedule",
            json={
                "cron_expression": "0 2 * * *",
                "timezone": "Asia/Kolkata",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()["repository"]
        assert body["check_cron_expression"] == "0 2 * * *"
        assert body["check_timezone"] == "Asia/Kolkata"
        assert body["timezone"] == "Asia/Kolkata"


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

    def test_parse_borg_archive_time_treats_naive_values_as_utc(self):
        parsed = repositories_api._parse_borg_archive_time("2026-04-27T03:00:06.000000")

        assert parsed == datetime(2026, 4, 27, 3, 0, 6)

    def test_parse_borg_archive_time_converts_offset_values_to_utc(self):
        parsed = repositories_api._parse_borg_archive_time("2026-04-27T03:00:06-04:00")

        assert parsed == datetime(2026, 4, 27, 7, 0, 6)

    @pytest.mark.asyncio
    async def test_update_repository_stats_updates_archive_count_size_and_last_backup(
        self, test_db
    ):
        repo = _create_repo(
            test_db, "Repo", "/repos/main", passphrase="secret", bypass_lock=False
        )
        settings = SystemSettings(bypass_lock_on_list=True)
        test_db.add(settings)
        test_db.commit()

        list_payload = {
            "success": True,
            "stdout": '{"archives":[{"name":"old","time":"2024-01-01T10:00:00"},{"name":"new","time":"2024-02-01T12:00:00Z"}]}',
        }
        with (
            patch("app.api.repositories.resolve_repo_ssh_key_file", return_value=None),
            patch.object(
                repositories_api.BorgRouter,
                "list_archives",
                AsyncMock(return_value=list_payload["stdout"]),
            ) as mock_list,
            patch.object(
                repositories_api.BorgRouter,
                "calculate_total_size_bytes",
                AsyncMock(return_value=2097152),
            ) as mock_size,
        ):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is True
        assert repo.archive_count == 2
        assert repo.total_size == "2.00 MB"
        assert repo.last_backup == datetime(2024, 2, 1, 12, 0)
        mock_list.assert_awaited_once()
        assert mock_list.await_args.kwargs["env"]["TZ"] == "UTC"
        assert mock_list.await_args.kwargs["env"]["BORG_PASSPHRASE"] == "secret"
        assert mock_size.await_args.kwargs["use_bypass_lock"] is True
        assert mock_size.await_args.kwargs["env"]["BORG_PASSPHRASE"] == "secret"

    @pytest.mark.asyncio
    async def test_update_repository_stats_accepts_router_archive_lists(self, test_db):
        repo = _create_repo(
            test_db, "Repo", "/repos/main", passphrase="secret", bypass_lock=False
        )

        archives = [
            {"name": "old", "time": "2024-01-01T10:00:00"},
            {"name": "new", "time": "2024-02-01T12:00:00Z"},
        ]
        with (
            patch("app.api.repositories.resolve_repo_ssh_key_file", return_value=None),
            patch.object(
                repositories_api.BorgRouter,
                "list_archives",
                AsyncMock(return_value=archives),
            ) as mock_list,
            patch.object(
                repositories_api.borg,
                "_execute_command",
                AsyncMock(
                    return_value={
                        "success": True,
                        "stdout": '{"cache":{"stats":{"unique_csize": 1024}}}',
                        "stderr": "",
                        "return_code": 0,
                    }
                ),
            ),
        ):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is True
        assert repo.archive_count == 2
        assert repo.last_backup == datetime(2024, 2, 1, 12, 0)
        mock_list.assert_awaited_once()
        assert mock_list.await_args.kwargs["env"]["TZ"] == "UTC"

    @pytest.mark.asyncio
    async def test_update_repository_stats_chooses_latest_archive_by_utc_instant(
        self, test_db
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")

        archives = [
            {"name": "lexically-later", "time": "2024-02-01T15:30:00Z"},
            {"name": "actually-later", "time": "2024-02-01T11:00:00-05:00"},
        ]
        with (
            patch("app.api.repositories.resolve_repo_ssh_key_file", return_value=None),
            patch.object(
                repositories_api.BorgRouter,
                "list_archives",
                AsyncMock(return_value=archives),
            ),
            patch.object(
                repositories_api.BorgRouter,
                "calculate_total_size_bytes",
                AsyncMock(return_value=0),
            ),
        ):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is True
        assert repo.last_backup == datetime(2024, 2, 1, 16, 0)

    @pytest.mark.asyncio
    async def test_update_repository_stats_returns_false_on_unexpected_exception(
        self, test_db
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")

        with patch.object(
            repositories_api.BorgRouter,
            "list_archives",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is False

    @pytest.mark.asyncio
    async def test_update_repository_stats_uses_remote_path_and_ssh_key_env(
        self, test_db
    ):
        repo = Repository(
            name="Remote Repo",
            path="ssh://borg@example.com:22/backups/main",
            encryption="none",
            repository_type="ssh",
            remote_path="/usr/local/bin/borg1",
            passphrase="remote-secret",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with (
            patch(
                "app.api.repositories.resolve_repo_ssh_key_file",
                return_value="/tmp/test.key",
            ),
            patch.object(
                repositories_api.BorgRouter,
                "list_archives",
                AsyncMock(return_value='{"archives": []}'),
            ) as mock_list,
            patch.object(
                repositories_api.BorgRouter,
                "calculate_total_size_bytes",
                AsyncMock(return_value=1024),
            ) as mock_size,
            patch("app.api.repositories.os.path.exists", return_value=False),
        ):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is True
        mock_list.assert_awaited_once()
        assert mock_size.await_args.kwargs["env"]["BORG_RSH"].startswith("ssh ")
        assert not mock_size.await_args.kwargs["use_bypass_lock"]

    @pytest.mark.asyncio
    async def test_update_repository_stats_formats_v2_total_size_from_router(
        self, test_db
    ):
        repo = _create_repo(test_db, "Repo V2", "/repos/v2-main", borg_version=2)

        with (
            patch(
                "app.api.repositories.resolve_repo_ssh_key_file",
                return_value="/tmp/test.key",
            ),
            patch.object(
                repositories_api.BorgRouter,
                "list_archives",
                AsyncMock(
                    return_value=[{"name": "new", "start": "2024-02-01T12:00:00Z"}]
                ),
            ) as mock_list,
            patch.object(
                repositories_api.BorgRouter,
                "calculate_total_size_bytes",
                AsyncMock(return_value=4096),
            ) as mock_size,
            patch("app.api.repositories.os.path.exists", return_value=False),
        ):
            success = await repositories_api.update_repository_stats(repo, test_db)

        assert success is True
        assert repo.archive_count == 1
        assert repo.total_size == "4.00 KB"
        assert repo.last_backup == datetime(2024, 2, 1, 12, 0)
        mock_list.assert_awaited_once()
        mock_size.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_repo_metadata_routes_serialize_borg_commands_per_repository(
        self, test_db
    ):
        repo = Repository(
            name="Remote Repo",
            path="ssh://borg@example.com:22/backups/main",
            encryption="none",
            repository_type="ssh",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)
        state = {"active": 0, "max_active": 0}

        async def fake_run(*args, **kwargs):
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            await asyncio.sleep(0.05)
            state["active"] -= 1

            command_label = kwargs["command_label"]
            if "list" in command_label.lower():
                return b'{"archives":[]}'
            return b'{"repository":{},"cache":{},"encryption":{}}'

        with (
            patch.object(
                repositories_api,
                "_load_repository_with_access",
                return_value=repo,
            ),
            patch.object(
                repositories_api,
                "_resolve_bypass_lock",
                return_value=(False, "none"),
            ),
            patch.object(
                repositories_api,
                "get_operation_timeouts",
                return_value={"info_timeout": 30, "list_timeout": 30},
            ),
            patch.object(
                repositories_api.BorgRouter,
                "build_repo_list_command",
                return_value=["borg", "list"],
            ),
            patch.object(
                repositories_api.BorgRouter,
                "build_repo_info_command",
                return_value=["borg", "info"],
            ),
            patch.object(
                repositories_api,
                "_run_repository_command_with_retries",
                side_effect=fake_run,
            ),
        ):
            archives_result, info_result = await asyncio.gather(
                repositories_api.list_repository_archives(
                    repo.id, current_user=object(), db=test_db
                ),
                repositories_api.get_repository_info(
                    repo.id, current_user=object(), db=test_db
                ),
            )

        assert state["max_active"] == 1
        assert archives_result["archives"] == []
        assert info_result["info"]["repository"] == {}
