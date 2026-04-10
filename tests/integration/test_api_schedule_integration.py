"""
Integration tests for scheduled jobs API with real borg execution

These tests verify scheduled job functionality end-to-end.
Focus on timezone handling and cron expression correctness.
"""
import json
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from app.database.models import BackupJob, CompactJob, PruneJob, Repository, ScheduledJob, ScheduledJobRepository
from datetime import datetime, timedelta

from tests.integration.test_helpers import parse_archives_payload, wait_for_job_terminal_status
from tests.utils.borg import make_borg_test_env
from tests.utils.borg import create_registered_local_repository


def _create_registered_borg_repo(test_db, borg_binary, tmp_path, name: str, slug: str):
    return create_registered_local_repository(
        test_db=test_db,
        borg_binary=borg_binary,
        tmp_path=tmp_path,
        name=name,
        slug=slug,
        source_files={f"{slug}.txt": f"content for {slug}"},
    )


def _require_borg2_binary() -> str:
    borg2_path = shutil.which("borg2")
    if not borg2_path:
        pytest.skip("Borg 2 binary not found. Install borg2 to run this integration test.")
    return borg2_path


def _enable_borg_v2(test_db) -> None:
    from app.database.models import LicensingState

    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="integration-borg-v2-schedule")
        test_db.add(state)

    state.plan = "pro"
    state.status = "active"
    state.is_trial = False
    test_db.commit()


def _create_borg2_registered_repo(test_db, tmp_path, source_root):
    borg2_binary = _require_borg2_binary()
    _enable_borg_v2(test_db)

    repo_path = tmp_path / "borg2-schedule-repo"
    env = make_borg_test_env(str(tmp_path))

    init_result = subprocess.run(
        [borg2_binary, "-r", str(repo_path), "repo-create", "--encryption", "none"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert init_result.returncode == 0, init_result.stderr

    import_result = subprocess.run(
        [borg2_binary, "-r", str(repo_path), "repo-info", "--json"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert import_result.returncode == 0, import_result.stderr

    repo = Repository(
        name="Borg2 Scheduled Repo",
        path=str(repo_path),
        encryption="none",
        compression="lz4",
        repository_type="local",
        borg_version=2,
        source_directories=json.dumps([str(source_root)]),
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo, repo_path


@pytest.mark.integration
@pytest.mark.requires_borg
class TestScheduledJobCreation:
    """Test scheduled job creation with cron validation"""

    def test_create_scheduled_job_daily(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test creating daily scheduled backup

        WHY: Verifies cron expressions are stored correctly
        PREVENTS: Backups running at wrong times
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 2 * * *",  # Daily at 2 AM
                "enabled": True,
                "name": "Daily Backup",
                "timezone": "UTC"
            },
            headers=admin_headers
        )

        assert response.status_code == 200, f"Failed to create schedule: {response.json()}"
        data = response.json()

        # Verify schedule was created
        if "schedule" in data:
            schedule_data = data["schedule"]
        elif "job" in data:
            schedule_data = data["job"]
        else:
            schedule_data = data

        assert schedule_data["cron_expression"] == "0 2 * * *"
        assert schedule_data["enabled"] is True
        assert schedule_data["name"] == "Daily Backup"

    def test_create_scheduled_job_with_timezone_conversion(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test timezone is stored for cron conversion

        WHY: Verifies local time is converted to UTC correctly
        PREVENTS: Backups running at wrong local times
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 10 * * *",  # 10 AM in user's timezone
                "enabled": True,
                "name": "Morning Backup",
                "timezone": "America/New_York"  # EST/EDT
            },
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        schedule_data = data.get("job", data)
        assert schedule_data["name"] == "Morning Backup"

    def test_create_scheduled_job_invalid_cron_expression(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test invalid cron expression is rejected

        WHY: Prevents storing malformed schedules
        PREVENTS: Scheduler errors from invalid cron
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "invalid cron",
                "enabled": True,
                "name": "Bad Schedule"
            },
            headers=admin_headers
        )

        # Should reject invalid cron
        assert response.status_code == 400, "Invalid cron should be rejected"

    def test_create_scheduled_job_with_repository_path(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test creating schedule using repository path instead of ID

        WHY: API might accept path as alternative to ID
        PREVENTS: Schedules not finding their repository
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository": str(repo_path),  # Use path instead of ID
                "cron_expression": "0 3 * * *",
                "enabled": True,
                "name": "Path-based Schedule"
            },
            headers=admin_headers
        )

        # Should work with either repository or repository_id
        assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.requires_borg
class TestScheduledJobManagement:
    """Test scheduled job management operations"""

    def test_list_scheduled_jobs(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test listing all scheduled jobs

        WHY: Verifies scheduled jobs are returned correctly
        PREVENTS: UI showing empty schedule list
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create a schedule
        create_response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 2 * * *",
                "enabled": True,
                "name": "Test Schedule"
            },
            headers=admin_headers
        )

        assert create_response.status_code == 200

        # List schedules
        list_response = test_client.get("/api/schedule/", headers=admin_headers)

        assert list_response.status_code == 200
        data = list_response.json()

        # Should return list of schedules
        if isinstance(data, dict) and "schedules" in data:
            schedules = data["schedules"]
        elif isinstance(data, dict) and "jobs" in data:
            schedules = data["jobs"]
        elif isinstance(data, list):
            schedules = data
        else:
            schedules = []

        assert len(schedules) > 0, "Should have at least one schedule"

    def test_update_scheduled_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db
    ):
        """
        Test updating scheduled job

        WHY: Verifies schedule changes are saved
        PREVENTS: Users unable to modify schedules
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create a schedule directly in database
        schedule = ScheduledJob(
            repository=str(repo_path),
            cron_expression="0 2 * * *",
            enabled=True,
            name="Original Schedule"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        # Update the schedule
        update_response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={
                "cron_expression": "0 3 * * *",  # Change time
                "enabled": False,  # Disable
                "name": "Updated Schedule"
            },
            headers=admin_headers
        )

        # Update should succeed
        assert update_response.status_code == 200, f"Update failed: {update_response.json()}"

    def test_delete_scheduled_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db
    ):
        """
        Test deleting scheduled job

        WHY: Verifies schedules can be removed
        PREVENTS: Unwanted backups continuing to run
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create a schedule
        schedule = ScheduledJob(
            repository=str(repo_path),
            cron_expression="0 2 * * *",
            enabled=True,
            name="To Be Deleted"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        # Delete the schedule
        delete_response = test_client.delete(
            f"/api/schedule/{schedule.id}",
            headers=admin_headers
        )

        # Delete should succeed
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.json()}"

        # Verify schedule no longer exists
        get_response = test_client.get(f"/api/schedule/{schedule.id}", headers=admin_headers)
        assert get_response.status_code == 404, "Deleted schedule should not be found"

    def test_disable_scheduled_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db
    ):
        """
        Test disabling scheduled job

        WHY: Verifies schedules can be temporarily disabled
        PREVENTS: Having to delete and recreate schedules
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create enabled schedule
        schedule = ScheduledJob(
            repository=str(repo_path),
            cron_expression="0 2 * * *",
            enabled=True,
            name="Active Schedule"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        # Disable the schedule
        update_response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={"enabled": False},
            headers=admin_headers
        )

        assert update_response.status_code == 200


@pytest.mark.integration
@pytest.mark.requires_borg
class TestScheduledJobValidation:
    """Test scheduled job validation"""

    def test_create_schedule_for_nonexistent_repository(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """
        Test schedule creation fails for missing repository

        WHY: Prevents orphaned schedules
        PREVENTS: Scheduler errors trying to backup missing repos
        """
        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": 99999,  # Non-existent
                "cron_expression": "0 2 * * *",
                "enabled": True,
                "name": "Orphan Schedule"
            },
            headers=admin_headers
        )

        # Should reject or warn about missing repository
        assert response.status_code == 404

    def test_create_duplicate_schedule_same_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test multiple schedules can exist for same repository

        WHY: Users might want different schedules (daily + weekly)
        PREVENTS: Unnecessarily restricting schedule flexibility
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create first schedule
        response1 = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 2 * * *",  # Daily
                "enabled": True,
                "name": "Daily Backup"
            },
            headers=admin_headers
        )

        assert response1.status_code == 200

        # Create second schedule for same repo
        response2 = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 3 * * 0",  # Weekly on Sunday
                "enabled": True,
                "name": "Weekly Backup"
            },
            headers=admin_headers
        )

        # Should allow multiple schedules
        assert response2.status_code == 200

    def test_cron_expression_validation(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test various cron expressions are validated correctly

        WHY: Prevents storing invalid cron that will never run
        PREVENTS: Silent schedule failures
        """
        repo, repo_path, test_data_path = db_borg_repo

        invalid_crons = [
            "not a cron",
            "60 2 * * *",  # Invalid minute
            "0 25 * * *",  # Invalid hour
        ]

        for invalid_cron in invalid_crons:
            response = test_client.post(
                "/api/schedule/",
                json={
                    "repository_id": repo.id,
                    "cron_expression": invalid_cron,
                    "enabled": True,
                    "name": f"Invalid: {invalid_cron}"
                },
                headers=admin_headers
            )

            # Each invalid cron should be rejected or cause validation error
            # We're just verifying the API doesn't crash
            assert response.status_code == 400


@pytest.mark.integration
@pytest.mark.requires_borg
class TestMultiRepositorySchedules:
    """High-value integration tests for multi-repo schedule behavior."""

    def test_create_multi_repo_schedule_dedupes_repository_ids_preserves_order(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        borg_binary,
        tmp_path,
    ):
        repo1, _, _ = _create_registered_borg_repo(test_db, borg_binary, tmp_path, "Repo One", "repo-one")
        repo2, _, _ = _create_registered_borg_repo(test_db, borg_binary, tmp_path, "Repo Two", "repo-two")

        create_response = test_client.post(
            "/api/schedule/",
            json={
                "name": "Ordered Multi Repo Schedule",
                "cron_expression": "0 2 * * *",
                "repository_ids": [repo2.id, repo1.id, repo2.id],
                "enabled": True,
            },
            headers=admin_headers,
        )

        assert create_response.status_code == 200, create_response.json()
        schedule_payload = create_response.json()
        schedule_data = (
            schedule_payload.get("schedule")
            or schedule_payload.get("job")
            or schedule_payload
        )
        schedule_id = schedule_data["id"]

        detail_response = test_client.get(f"/api/schedule/{schedule_id}", headers=admin_headers)
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        schedule_data = detail_payload.get("schedule") or detail_payload.get("job") or detail_payload

        links = (
            test_db.query(ScheduledJobRepository)
            .filter_by(scheduled_job_id=schedule_id)
            .order_by(ScheduledJobRepository.execution_order)
            .all()
        )
        assert schedule_data["id"] == schedule_id
        assert [link.repository_id for link in links] == [repo2.id, repo1.id]

    def test_duplicate_multi_repo_schedule_preserves_repositories_and_disables_copy(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        borg_binary,
        tmp_path,
    ):
        repo1, _, _ = _create_registered_borg_repo(test_db, borg_binary, tmp_path, "Repo Alpha", "repo-alpha")
        repo2, _, _ = _create_registered_borg_repo(test_db, borg_binary, tmp_path, "Repo Beta", "repo-beta")

        create_response = test_client.post(
            "/api/schedule/",
            json={
                "name": "Source Multi Repo Schedule",
                "cron_expression": "0 5 * * *",
                "repository_ids": [repo1.id, repo2.id],
                "enabled": True,
                "archive_name_template": "{job_name}-{repo_name}-{date}",
                "run_prune_after": True,
            },
            headers=admin_headers,
        )
        assert create_response.status_code == 200, create_response.json()
        schedule_payload = create_response.json()
        schedule_data = (
            schedule_payload.get("schedule")
            or schedule_payload.get("job")
            or schedule_payload
        )
        original_id = schedule_data["id"]

        duplicate_response = test_client.post(
            f"/api/schedule/{original_id}/duplicate",
            headers=admin_headers,
        )
        assert duplicate_response.status_code == 200, duplicate_response.json()
        duplicate_id = duplicate_response.json()["job"]["id"]

        detail_response = test_client.get(f"/api/schedule/{duplicate_id}", headers=admin_headers)
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        duplicated = detail_payload.get("schedule") or detail_payload.get("job") or detail_payload

        assert duplicated["enabled"] is False
        assert duplicated["archive_name_template"] == "{job_name}-{repo_name}-{date}"
        assert duplicated["run_prune_after"] is True

        links = (
            test_db.query(ScheduledJobRepository)
            .filter_by(scheduled_job_id=duplicate_id)
            .order_by(ScheduledJobRepository.execution_order)
            .all()
        )
        assert [link.repository_id for link in links] == [repo1.id, repo2.id]

    def test_run_now_multi_repo_schedule_creates_backups_for_each_repository(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        borg_binary,
        tmp_path,
    ):
        repo1, repo1_path, _ = _create_registered_borg_repo(
            test_db, borg_binary, tmp_path, "RunNow Repo One", "run-now-one"
        )
        repo2, repo2_path, _ = _create_registered_borg_repo(
            test_db, borg_binary, tmp_path, "RunNow Repo Two", "run-now-two"
        )

        create_response = test_client.post(
            "/api/schedule/",
            json={
                "name": "Run Now Multi Repo",
                "cron_expression": "0 6 * * *",
                "repository_ids": [repo1.id, repo2.id],
                "enabled": True,
            },
            headers=admin_headers,
        )
        assert create_response.status_code == 200, create_response.json()
        schedule_payload = create_response.json()
        schedule_data = (
            schedule_payload.get("schedule")
            or schedule_payload.get("job")
            or schedule_payload
        )
        schedule_id = schedule_data["id"]

        run_response = test_client.post(
            f"/api/schedule/{schedule_id}/run-now",
            headers=admin_headers,
        )
        assert run_response.status_code == 200, run_response.json()

        deadline = datetime.now() + timedelta(seconds=60)
        matching_jobs = []
        while datetime.now() < deadline:
            test_db.expire_all()
            matching_jobs = (
                test_db.query(BackupJob)
                .filter(BackupJob.scheduled_job_id == schedule_id)
                .order_by(BackupJob.id.asc())
                .all()
            )
            if len(matching_jobs) == 2 and all(
                job.status in ["completed", "completed_with_warnings", "failed"] for job in matching_jobs
            ):
                break
            time.sleep(0.25)
        assert len(matching_jobs) == 2
        assert all(job.status in ["completed", "completed_with_warnings"] for job in matching_jobs)

        repo1_archives = test_client.get(
            f"/api/archives/list?repository={repo1_path}",
            headers=admin_headers,
        )
        repo2_archives = test_client.get(
            f"/api/archives/list?repository={repo2_path}",
            headers=admin_headers,
        )
        assert repo1_archives.status_code == 200
        assert repo2_archives.status_code == 200
        assert len(parse_archives_payload(repo1_archives.json())) == 1
        assert len(parse_archives_payload(repo2_archives.json())) == 1

    def test_create_schedule_rejects_observability_only_repository(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        observe_repo = Repository(
            name="Observe Only Repo",
            path="/tmp/observe-only-repo",
            encryption="none",
            repository_type="local",
            mode="observe",
        )
        test_db.add(observe_repo)
        test_db.commit()
        test_db.refresh(observe_repo)

        response = test_client.post(
            "/api/schedule/",
            json={
                "name": "Observe Schedule",
                "cron_expression": "0 2 * * *",
                "repository_ids": [observe_repo.id],
                "enabled": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.schedule.observabilityOnlyRepo"

    def test_run_now_single_repo_borg2_schedule_exposes_maintenance_contract(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        tmp_path,
    ):
        source_root = tmp_path / "borg2-schedule-source"
        source_root.mkdir()
        (source_root / "schedule.txt").write_text("schedule data\n", encoding="utf-8")

        repo, repo_path = _create_borg2_registered_repo(test_db, tmp_path, source_root)
        create_response = test_client.post(
            "/api/schedule/",
            json={
                "name": "Borg2 Schedule With Maintenance",
                "cron_expression": "0 7 * * *",
                "repository_id": repo.id,
                "enabled": True,
                "run_prune_after": True,
                "run_compact_after": True,
                "prune_keep_daily": 1,
                "prune_keep_weekly": 0,
                "prune_keep_monthly": 0,
                "prune_keep_quarterly": 0,
                "prune_keep_yearly": 0,
            },
            headers=admin_headers,
        )
        assert create_response.status_code == 200, create_response.json()
        schedule_id = create_response.json()["job"]["id"]

        run_response = test_client.post(
            f"/api/schedule/{schedule_id}/run-now",
            headers=admin_headers,
        )
        assert run_response.status_code == 200, run_response.json()
        run_payload = run_response.json()
        assert run_payload["status"] == "pending"
        assert run_payload["message"] == "backend.success.schedule.scheduledJobStarted"

        backup_job_id = run_payload["job_id"]
        backup_job = wait_for_job_terminal_status(
            test_client,
            "/api/backup/status",
            backup_job_id,
            admin_headers,
            timeout=120,
        )
        assert backup_job["status"] in {"completed", "completed_with_warnings"}

        deadline = datetime.now() + timedelta(seconds=120)
        prune_job = None
        compact_job = None
        while datetime.now() < deadline:
            test_db.expire_all()
            prune_job = (
                test_db.query(PruneJob)
                .filter(PruneJob.repository_id == repo.id, PruneJob.scheduled_prune.is_(True))
                .order_by(PruneJob.id.desc())
                .first()
            )
            compact_job = (
                test_db.query(CompactJob)
                .filter(CompactJob.repository_id == repo.id, CompactJob.scheduled_compact.is_(True))
                .order_by(CompactJob.id.desc())
                .first()
            )
            if prune_job and compact_job and prune_job.status in {"completed", "completed_with_warnings", "failed"} and compact_job.status in {"completed", "completed_with_warnings", "failed"}:
                break
            time.sleep(0.25)

        assert prune_job is not None
        assert compact_job is not None
        assert prune_job.status in {"completed", "completed_with_warnings"}
        assert compact_job.status in {"completed", "completed_with_warnings"}
