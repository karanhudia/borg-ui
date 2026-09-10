import asyncio
import re
from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import repositories as repositories_api
from tests.utils.operations import seed_job_operation
from app.database.models import (
    AgentJob,
    AgentMachine,
    BackupPlan,
    BackupPlanRun,
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


def _set_log_save_policy(test_db, policy: str) -> None:
    settings = test_db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        test_db.add(settings)
    settings.log_save_policy = policy
    test_db.flush()


@pytest.mark.unit
class TestRepositoryRouteContracts:
    def test_repositories_register_single_canonical_break_lock_route(self):
        break_lock_routes = [
            route
            for route in repositories_api.router.routes
            if getattr(route, "path", "").endswith("/break-lock")
            and "POST" in getattr(route, "methods", set())
        ]
        canonical_counts = Counter(
            re.sub(r"\{[^}]+\}", "{param}", route.path) for route in break_lock_routes
        )

        assert canonical_counts["/{param}/break-lock"] == 1
        assert [route.path for route in break_lock_routes] == ["/{repo_id}/break-lock"]

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
                seed_job_operation(
                    test_db,
                    "check",
                    repository_id=repo.id,
                    status="running",
                    progress=35,
                    progress_message="Checking segments",
                    started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                ),
                seed_job_operation(
                    test_db,
                    "compact",
                    repository_id=repo.id,
                    status="running",
                    progress=60,
                    progress_message="Compacting",
                    started_at=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
                ),
                seed_job_operation(
                    test_db,
                    "prune",
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

    def test_get_running_jobs_reports_repository_wipe_job(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Repo", "/repos/main")
        wipe_job = seed_job_operation(
            test_db,
            "wipe",
            repository_id=repo.id,
            repository_path=repo.path,
            repository_name=repo.name,
            borg_version=1,
            status="running",
            phase="delete",
            archive_count=2,
            archive_fingerprint="sha256:abc",
            run_compact=True,
            progress=35,
            progress_message="Deleting repository archives",
            started_at=datetime(2026, 1, 1, 12, 15, tzinfo=timezone.utc),
        )
        test_db.commit()

        response = test_client.get(
            f"/api/repositories/{repo.id}/running-jobs", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["has_running_jobs"] is True
        assert body["wipe_job"]["id"] == wipe_job.id
        assert body["wipe_job"]["progress"] == 35
        assert body["wipe_job"]["progress_message"] == "Deleting repository archives"

    def test_get_check_job_status_reads_log_file(
        self, test_client: TestClient, admin_headers, test_db, tmp_path
    ):
        _set_log_save_policy(test_db, "all_jobs")
        repo = _create_repo(test_db, "Repo", "/repos/main")
        log_path = tmp_path / "check.log"
        log_path.write_text("first line\nsecond line\n", encoding="utf-8")
        job = seed_job_operation(
            test_db,
            "check",
            repository_id=repo.id,
            status="completed",
            log_file_path=str(log_path),
            has_logs=True,
        )
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
        _set_log_save_policy(test_db, "all_jobs")
        repo = _create_repo(test_db, "Repo", "/repos/main")
        log_path = tmp_path / "compact.log"
        log_path.write_text("compact output\n", encoding="utf-8")
        job = seed_job_operation(
            test_db,
            "compact",
            repository_id=repo.id,
            status="completed",
            log_file_path=str(log_path),
            has_logs=True,
        )
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
        _set_log_save_policy(test_db, "all_jobs")
        repo = _create_repo(test_db, "Repo", "/repos/main")
        log_path = tmp_path / "prune.log"
        log_path.write_text("prune output\n", encoding="utf-8")
        job = seed_job_operation(
            test_db,
            "prune",
            repository_id=repo.id,
            status="completed",
            log_file_path=str(log_path),
            has_logs=True,
        )
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

    def test_parse_borg_archive_time_uses_the_given_zone_for_naive_values(self):
        # Borg emits naive local wall clock; the caller supplies the creating
        # machine's zone. EDT on this date is UTC-4.
        parsed = repositories_api._parse_borg_archive_time(
            "2026-04-27T03:00:06.000000", timezone_name="America/New_York"
        )

        assert parsed == datetime(2026, 4, 27, 7, 0, 6)

    @pytest.mark.skipif(
        not hasattr(__import__("time"), "tzset"), reason="requires POSIX tzset"
    )
    def test_parse_borg_archive_time_utc_zone_is_host_independent(self):
        # Server listings run borg under TZ=UTC (pinned in the wrappers), so
        # naive timestamps must parse as UTC no matter the server's own zone.
        import os
        import time

        old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Berlin"
        time.tzset()
        try:
            parsed = repositories_api._parse_borg_archive_time(
                "2026-07-01T03:00:00", timezone_name="UTC"
            )
        finally:
            if old_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old_tz
            time.tzset()

        assert parsed == datetime(2026, 7, 1, 3, 0, 0)

    def test_parse_borg_archive_time_pins_ambiguous_dst_wall_times_to_earlier(self):
        # Berlin's 2026 fall-back repeats 02:00-02:59 wall times on Oct 25.
        # Borg gives no disambiguator; the parser pins the EARLIER instant
        # (CEST, UTC+2) so recency is only ever understated, never overstated.
        parsed = repositories_api._parse_borg_archive_time(
            "2026-10-25T02:30:00", timezone_name="Europe/Berlin"
        )

        assert parsed == datetime(2026, 10, 25, 0, 30, 0)

    def test_parse_borg_archive_time_zone_handles_dst_per_archive_date(self):
        # The same zone resolves to different offsets on either side of the
        # DST switch - a fixed offset would misplace half the archives.
        summer = repositories_api._parse_borg_archive_time(
            "2026-07-01T03:00:00", timezone_name="Europe/Berlin"
        )
        winter = repositories_api._parse_borg_archive_time(
            "2026-01-15T03:00:00", timezone_name="Europe/Berlin"
        )

        assert summer == datetime(2026, 7, 1, 1, 0, 0)  # CEST, UTC+2
        assert winter == datetime(2026, 1, 15, 2, 0, 0)  # CET, UTC+1

    @pytest.mark.skipif(
        not hasattr(__import__("time"), "tzset"), reason="requires POSIX tzset"
    )
    def test_parse_borg_archive_time_falls_back_to_server_local_zone(self):
        import os
        import time

        old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/Berlin"
        time.tzset()
        try:
            no_zone = repositories_api._parse_borg_archive_time("2026-07-01T03:00:00")
            bad_zone = repositories_api._parse_borg_archive_time(
                "2026-07-01T03:00:00", timezone_name="Not/AZone"
            )
        finally:
            if old_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old_tz
            time.tzset()

        assert no_zone == datetime(2026, 7, 1, 1, 0, 0)
        assert bad_zone == datetime(2026, 7, 1, 1, 0, 0)

    def test_parse_borg_archive_time_rejects_out_of_range_epochs(self):
        assert repositories_api._parse_borg_archive_time(1e18) is None
        assert repositories_api._parse_borg_archive_time(-1e18) is None

    def test_parse_borg_archive_time_rejects_booleans(self):
        # bool is an int subclass - True must not parse as epoch 1.
        assert repositories_api._parse_borg_archive_time(True) is None
        assert repositories_api._parse_borg_archive_time(False) is None

    def test_parse_borg_archive_time_converts_offset_values_to_utc(self):
        parsed = repositories_api._parse_borg_archive_time("2026-04-27T03:00:06-04:00")

        assert parsed == datetime(2026, 4, 27, 7, 0, 6)

    def test_normalize_archive_listing_times_adds_an_explicit_utc_offset(self):
        # Naive strings read as browser-local in the frontend; the response
        # must carry the offset. Non-dict entries pass through untouched.
        archives = [{"name": "a", "time": "2026-07-01T03:00:00"}, "junk"]

        normalized = repositories_api._normalize_archive_listing_times(
            archives, timezone_name="UTC"
        )

        assert normalized[0]["time"] == "2026-07-01T03:00:00+00:00"
        assert normalized[1] == "junk"
        # The input listing is not mutated.
        assert archives[0]["time"] == "2026-07-01T03:00:00"

    def test_normalize_archive_listing_times_applies_the_agent_zone(self):
        # An old agent renders in its machine zone and reports that zone.
        archives = [{"name": "a", "start": "2026-07-01T03:00:00"}]

        normalized = repositories_api._normalize_archive_listing_times(
            archives, timezone_name="Europe/Berlin"
        )

        assert normalized[0]["start"] == "2026-07-01T01:00:00+00:00"

    def test_normalize_archive_listing_times_serializes_numeric_epochs(self):
        # Epoch 0 included - falsy but a valid time.
        archives = [{"name": "a", "time": 0}, {"name": "b", "start": 1767225600}]

        normalized = repositories_api._normalize_archive_listing_times(
            archives, timezone_name="UTC"
        )

        assert normalized[0]["time"] == "1970-01-01T00:00:00+00:00"
        assert normalized[1]["start"] == "2026-01-01T00:00:00+00:00"

    def test_normalize_archive_listing_times_keeps_out_of_range_epochs_raw(self):
        archives = [{"name": "a", "time": 1e18}]

        normalized = repositories_api._normalize_archive_listing_times(
            archives, timezone_name="UTC"
        )

        assert normalized[0]["time"] == 1e18

    def test_normalize_archive_listing_times_keeps_unparseable_strings(self):
        archives = [{"name": "a", "time": "not-a-timestamp"}]

        normalized = repositories_api._normalize_archive_listing_times(
            archives, timezone_name="UTC"
        )

        assert normalized[0]["time"] == "not-a-timestamp"

    @pytest.mark.asyncio
    async def test_borg1_repo_on_a_capable_agent_falls_back_to_disk_usage(
        self, test_db
    ):
        """A 0.1.4 agent answers storage_usage for Borg 1 with
        borg1_uses_rinfo; when rinfo carried no cache stats, du still runs."""
        agent = self._agent(test_db, ["repository.rinfo", "repository.storage_usage"])
        repo = _create_repo(
            test_db,
            "Borg1 Agent Repo",
            "/srv/repo",
            borg_version=1,
            agent_machine_id=agent.id,
        )
        wait_returns = [
            {"success": True, "stdout": '{"archives":[]}'},
            {"success": True, "stdout": "{}"},
            {
                "return_code": 0,
                "stdout": '{"bytes": null, "objects": null, "source": null, "reason": "borg1_uses_rinfo"}',
                "data": {
                    "bytes": None,
                    "objects": None,
                    "source": None,
                    "reason": "borg1_uses_rinfo",
                },
            },
            {"return_code": 0, "stdout": "4096\t/srv/repo\n"},
        ]

        async def fake_wait(db, job_id, **kwargs):
            return wait_returns.pop(0)

        with (
            patch("app.api.repositories.is_agent_executor", return_value=True),
            patch(
                "app.services.repository_executor.queue_agent_repository_operation_job",
                return_value=SimpleNamespace(id=1),
            ) as mock_queue,
            patch(
                "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
                new=AsyncMock(),
            ),
            patch(
                "app.services.repository_executor.wait_for_agent_repository_operation_job",
                new=fake_wait,
            ),
        ):
            assert (
                await repositories_api._update_agent_repository_stats(repo, test_db)
                is True
            )
        assert repo.total_size == "4.00 KB" and repo.total_size_source == "storage_used"
        assert [c.kwargs["job_kind"] for c in mock_queue.call_args_list][-2:] == [
            "repository.storage_usage",
            "repository.disk_usage",
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("before", "after", "cancel_sent"),
        [
            ("queued", "canceled", False),
            ("claimed", "cancel_requested", True),
            ("running", "cancel_requested", True),
            ("completed", "completed", False),
        ],
    )
    async def test_timed_out_storage_usage_job_is_released(
        self, test_db, before, after, cancel_sent
    ):
        """A 504 from the wait leaves the agent job where admission would
        count it as active work: queued jobs are cancelled, live ones get
        the cancel request, terminal ones stay."""
        agent = self._agent(test_db, ["repository.storage_usage"])
        job = AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status=before,
            payload={"job_kind": "repository.storage_usage"},
        )
        test_db.add(job)
        test_db.commit()
        with patch(
            "app.api.repositories.dispatch_agent_cancel_if_connected",
            new=AsyncMock(return_value=True),
        ) as cancel:
            await repositories_api._release_timed_out_agent_job(test_db, job.id)
        test_db.refresh(job)
        assert job.status == after
        assert cancel.await_count == (1 if cancel_sent else 0)
        if before == "queued":
            assert job.completed_at is not None and "Abandoned" in job.error_message

    @pytest.mark.asyncio
    async def test_storage_usage_wait_timeout_releases_the_job(self, test_db):
        """The stats refresh survives the 504 and releases the job it
        stopped waiting for."""
        from fastapi import HTTPException

        agent = self._agent(test_db, ["repository.rinfo", "repository.storage_usage"])
        repo = _create_repo(
            test_db,
            "Agent Repo",
            "rest://borg@h/store/repo",
            borg_version=2,
            agent_machine_id=agent.id,
        )
        wait_returns = [
            {"success": True, "stdout": '{"archives":[]}'},
            {
                "success": True,
                "stdout": '{"repository":{"last_modified":"2026-09-06T08:57:17+00:00"}}',
            },
            HTTPException(status_code=504, detail="timeout"),
        ]

        async def fake_wait(db, job_id, **kwargs):
            item = wait_returns.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        with (
            patch("app.api.repositories.is_agent_executor", return_value=True),
            patch(
                "app.services.repository_executor.queue_agent_repository_operation_job",
                return_value=SimpleNamespace(id=1),
            ),
            patch(
                "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
                new=AsyncMock(),
            ),
            patch(
                "app.services.repository_executor.wait_for_agent_repository_operation_job",
                new=fake_wait,
            ),
            patch(
                "app.api.repositories._release_timed_out_agent_job", new=AsyncMock()
            ) as release,
        ):
            assert (
                await repositories_api._update_agent_repository_stats(repo, test_db)
                is True
            )
        release.assert_awaited_once_with(test_db, 1)

    def _agent(self, test_db, capabilities):
        from app.core.security import get_password_hash

        agent = AgentMachine(
            name="m",
            agent_id="agt_m",
            token_hash=get_password_hash("t"),
            token_prefix="t",
            status="online",
            capabilities=capabilities,
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)
        return agent

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

    @pytest.mark.asyncio
    async def test_list_repository_archives_marks_manual_backup_plan_archive(
        self, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        plan = BackupPlan(
            name="Monthly Plan",
            enabled=True,
            source_type="local",
            source_directories='["/srv/project"]',
            exclude_patterns="[]",
            archive_name_template="{plan_name}-{repo_name}-{now}",
            compression="lz4",
            repository_run_mode="series",
            max_parallel_repositories=1,
            failure_behavior="continue",
            schedule_enabled=False,
            timezone="UTC",
        )
        test_db.add(plan)
        test_db.flush()
        run = BackupPlanRun(
            backup_plan_id=plan.id,
            trigger="manual",
            status="completed",
            started_at=datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 5, 15, 10, 5, tzinfo=timezone.utc),
        )
        test_db.add(run)
        test_db.flush()
        test_db.add(
            seed_job_operation(
                test_db,
                "backup",
                repository=repo.path,
                repository_id=repo.id,
                backup_plan_id=plan.id,
                backup_plan_run_id=run.id,
                archive_name="Monthly-Plan-Primary",
                status="completed",
                started_at=datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 5, 15, 10, 5, tzinfo=timezone.utc),
            )
        )
        test_db.commit()

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
                return_value={"list_timeout": 30},
            ),
            patch.object(
                repositories_api.BorgRouter,
                "build_repo_list_command",
                return_value=["borg", "list"],
            ),
            patch.object(
                repositories_api,
                "_run_repository_command_with_retries",
                new=AsyncMock(
                    return_value=b'{"archives":[{"name":"Monthly-Plan-Primary","start":"2026-05-15T10:00:00Z"}]}'
                ),
            ),
        ):
            result = await repositories_api.list_repository_archives(
                repo.id, current_user=object(), db=test_db
            )

        archive = result["archives"][0]
        assert archive["name"] == "Monthly-Plan-Primary"
        assert archive["triggered_by"] == "manual"
        assert archive["backup_plan_id"] == plan.id
        assert archive["backup_plan_run_id"] == run.id
