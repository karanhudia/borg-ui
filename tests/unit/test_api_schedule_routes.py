from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.api.schedule as schedule_api
from app.database.models import (
    BackupJob,
    BackupPlan,
    BackupPlanRepository,
    Repository,
    RepositoryStorage,
    RcloneRemote,
    RcloneSyncJob,
    ScheduledJob,
    ScheduledJobRepository,
    SSHConnection,
)
from app.services.rclone_service import RcloneCommandResult


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        if tz is None:
            return fixed.replace(tzinfo=None)
        return fixed.astimezone(tz)


def _create_repo(test_db, name: str, path: str) -> Repository:
    repo = Repository(
        name=name, path=path, encryption="none", repository_type="local", mode="full"
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _create_schedule(
    test_db, name: str, cron_expression: str = "0 2 * * *", **kwargs
) -> ScheduledJob:
    schedule = ScheduledJob(
        name=name, cron_expression=cron_expression, enabled=True, **kwargs
    )
    test_db.add(schedule)
    test_db.commit()
    test_db.refresh(schedule)
    return schedule


@pytest.mark.unit
class TestScheduleRouteContracts:
    def test_list_schedules_includes_deduped_repository_ids(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo_a = _create_repo(test_db, "Repo A", "/repos/a")
        repo_b = _create_repo(test_db, "Repo B", "/repos/b")
        schedule = _create_schedule(test_db, "Nightly")
        test_db.add_all(
            [
                ScheduledJobRepository(
                    scheduled_job_id=schedule.id,
                    repository_id=repo_b.id,
                    execution_order=0,
                ),
                ScheduledJobRepository(
                    scheduled_job_id=schedule.id,
                    repository_id=repo_a.id,
                    execution_order=1,
                ),
            ]
        )
        test_db.commit()

        response = test_client.get("/api/schedule/", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        job = next(item for item in body["jobs"] if item["id"] == schedule.id)
        assert job["repository_ids"] == [repo_b.id, repo_a.id]

    def test_upcoming_jobs_returns_enabled_jobs_sorted_and_filtered(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(schedule_api, "datetime", _FixedDateTime)
        outside_window_hour = (_FixedDateTime.now(timezone.utc).hour + 2) % 24
        soon = _create_schedule(
            test_db, "Soon", cron_expression="*/15 * * * *", repository="/repos/a"
        )
        _create_schedule(
            test_db,
            "Outside Window",
            cron_expression=f"0 {outside_window_hour} * * *",
            repository="/repos/b",
        )
        disabled = _create_schedule(
            test_db, "Disabled", cron_expression="*/10 * * * *", repository="/repos/c"
        )
        disabled.enabled = False
        test_db.commit()

        response = test_client.get(
            "/api/schedule/upcoming-jobs?hours=1", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        names = [job["name"] for job in body["upcoming_jobs"]]
        assert "Soon" in names
        assert "Outside Window" not in names
        assert "Disabled" not in names
        assert body["upcoming_jobs"] == sorted(
            body["upcoming_jobs"], key=lambda item: item["next_run"]
        )
        assert any(
            job["id"] == soon.id and job["type"] == "schedule"
            for job in body["upcoming_jobs"]
        )

    def test_upcoming_jobs_includes_scheduled_backup_plans(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Plan Repo", "/repos/plan")
        plan = BackupPlan(
            name="Nightly Plan",
            enabled=True,
            source_type="local",
            source_directories='["/srv/project"]',
            exclude_patterns="[]",
            archive_name_template="{plan_name}-{repo_name}-{now}",
            compression="lz4",
            repository_run_mode="series",
            max_parallel_repositories=1,
            failure_behavior="continue",
            schedule_enabled=True,
            cron_expression="0 2 * * *",
            timezone="UTC",
            next_run=datetime.utcnow() + timedelta(minutes=30),
        )
        test_db.add(plan)
        test_db.flush()
        test_db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=1,
            )
        )
        test_db.commit()

        response = test_client.get(
            "/api/schedule/upcoming-jobs?hours=1", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        plan_job = next(
            job
            for job in body["upcoming_jobs"]
            if job["id"] == plan.id and job["type"] == "backup_plan"
        )
        assert plan_job["name"] == "Nightly Plan"
        assert plan_job["repository_ids"] == [repo.id]
        assert plan_job["cron_expression"] == "0 2 * * *"

    def test_update_schedule_rejects_duplicate_name(
        self, test_client: TestClient, admin_headers, test_db
    ):
        existing = _create_schedule(test_db, "Existing", repository="/repos/existing")
        target = _create_schedule(test_db, "Target", repository="/repos/target")

        response = test_client.put(
            f"/api/schedule/{target.id}",
            json={"name": existing.name},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"] == "backend.errors.schedule.jobNameExists"
        )

    def test_toggle_schedule_enable_recomputes_stale_next_run(
        self, test_client: TestClient, admin_headers, test_db
    ):
        schedule = _create_schedule(
            test_db, "Re-enable Me", repository="/repos/re-enable"
        )
        schedule.enabled = False
        schedule.next_run = datetime.now(timezone.utc) - timedelta(hours=12)
        test_db.commit()
        stale_next_run = schedule.next_run

        response = test_client.post(
            f"/api/schedule/{schedule.id}/toggle", headers=admin_headers
        )

        assert response.status_code == 200
        test_db.refresh(schedule)
        assert schedule.enabled is True
        assert schedule.next_run is not None
        assert schedule.next_run > stale_next_run

        due_jobs = (
            test_db.query(ScheduledJob)
            .filter(
                ScheduledJob.enabled == True,
                ScheduledJob.next_run <= datetime.now(timezone.utc),
            )
            .all()
        )
        assert schedule.id not in {job.id for job in due_jobs}

    def test_update_schedule_enable_recomputes_stale_next_run(
        self, test_client: TestClient, admin_headers, test_db
    ):
        schedule = _create_schedule(
            test_db, "Enable Via Update", repository="/repos/update-enable"
        )
        schedule.enabled = False
        schedule.next_run = datetime.now(timezone.utc) - timedelta(hours=6)
        test_db.commit()
        stale_next_run = schedule.next_run

        response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={"enabled": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(schedule)
        assert schedule.enabled is True
        assert schedule.next_run is not None
        assert schedule.next_run > stale_next_run

        due_jobs = (
            test_db.query(ScheduledJob)
            .filter(
                ScheduledJob.enabled == True,
                ScheduledJob.next_run <= datetime.now(timezone.utc),
            )
            .all()
        )
        assert schedule.id not in {job.id for job in due_jobs}

    def test_delete_schedule_nulls_backup_job_links(
        self, test_client: TestClient, admin_headers, test_db
    ):
        schedule = _create_schedule(test_db, "Delete Me", repository="/repos/delete-me")
        backup_job = BackupJob(
            repository="/repos/delete-me",
            status="completed",
            scheduled_job_id=schedule.id,
        )
        test_db.add(backup_job)
        test_db.commit()
        test_db.refresh(backup_job)

        response = test_client.delete(
            f"/api/schedule/{schedule.id}", headers=admin_headers
        )

        assert response.status_code == 200
        test_db.refresh(backup_job)
        assert backup_job.scheduled_job_id is None
        assert test_db.query(ScheduledJob).filter_by(id=schedule.id).first() is None

    def test_duplicate_schedule_copies_multi_repo_links_in_order(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo_a = _create_repo(test_db, "Repo A", "/repos/a")
        repo_b = _create_repo(test_db, "Repo B", "/repos/b")
        original = _create_schedule(
            test_db,
            "Original",
            repository="/repos/a",
            repository_id=repo_a.id,
            archive_name_template="{job_name}-{repo_name}",
            run_repository_scripts=True,
            run_prune_after=True,
            run_compact_after=True,
        )
        test_db.add_all(
            [
                ScheduledJobRepository(
                    scheduled_job_id=original.id,
                    repository_id=repo_b.id,
                    execution_order=0,
                ),
                ScheduledJobRepository(
                    scheduled_job_id=original.id,
                    repository_id=repo_a.id,
                    execution_order=1,
                ),
            ]
        )
        test_db.commit()

        response = test_client.post(
            f"/api/schedule/{original.id}/duplicate", headers=admin_headers
        )

        assert response.status_code == 200
        duplicated_id = response.json()["job"]["id"]
        duplicated = test_db.query(ScheduledJob).filter_by(id=duplicated_id).first()
        assert duplicated is not None
        assert duplicated.enabled is False
        assert duplicated.archive_name_template == "{job_name}-{repo_name}"
        assert duplicated.run_repository_scripts is True
        assert duplicated.run_prune_after is True
        assert duplicated.run_compact_after is True

        links = (
            test_db.query(ScheduledJobRepository)
            .filter_by(scheduled_job_id=duplicated_id)
            .order_by(ScheduledJobRepository.execution_order)
            .all()
        )
        assert [link.repository_id for link in links] == [repo_b.id, repo_a.id]

    def test_run_now_requires_configured_repositories(
        self, test_client: TestClient, admin_headers, test_db
    ):
        schedule = _create_schedule(test_db, "Empty")
        schedule.repository = None
        schedule.repository_id = None
        test_db.commit()

        response = test_client.post(
            f"/api/schedule/{schedule.id}/run-now", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.schedule.noRepositoriesConfigured"
        )

    def test_dispatch_due_schedule_uses_remote_direct_for_same_ssh_source_and_repo(
        self, test_db, monkeypatch
    ):
        from app.api.schedule import _dispatch_due_scheduled_job

        connection = SSHConnection(
            host="docker-host.example",
            username="backup",
            port=22,
            is_backup_source=True,
            borg_binary_path="/usr/local/bin/borg-wrapper",
        )
        test_db.add(connection)
        test_db.flush()
        repo = Repository(
            name="Remote Direct Repo",
            path="/repos/remote-direct",
            encryption="none",
            repository_type="ssh",
            connection_id=connection.id,
            source_ssh_connection_id=connection.id,
            source_directories='["/var/lib/docker/volumes/app"]',
        )
        test_db.add(repo)
        test_db.flush()
        schedule = _create_schedule(
            test_db,
            "Due Remote Direct",
            repository=repo.path,
            repository_id=repo.id,
        )

        monkeypatch.setattr(
            "app.api.schedule.execute_scheduled_backup_with_maintenance",
            lambda *args, **kwargs: object(),
        )

        class FakeTask:
            def add_done_callback(self, callback):
                self.callback = callback

        monkeypatch.setattr(
            "app.api.schedule.asyncio.create_task", lambda task: FakeTask()
        )
        monkeypatch.setattr(
            "app.api.schedule._track_scheduled_backup_task",
            lambda *args, **kwargs: None,
        )

        run_key = _dispatch_due_scheduled_job(
            test_db, schedule, datetime.now(timezone.utc)
        )

        assert run_key == f"backup:{test_db.query(BackupJob).one().id}"
        backup_job = test_db.query(BackupJob).one()
        assert backup_job.route_strategy == "remote_direct"
        assert backup_job.execution_mode == "remote_ssh"
        assert backup_job.source_ssh_connection_id == connection.id

    @pytest.mark.asyncio
    async def test_due_scheduled_rclone_mirror_records_failure_and_preserves_metadata(
        self, test_db, monkeypatch
    ):
        from app.services.rclone_mirror_scheduler import (
            run_due_scheduled_rclone_mirrors,
        )

        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
        repo = Repository(
            name="Mirror Repo",
            path="/repos/mirror",
            encryption="none",
            repository_type="local",
            mode="full",
        )
        test_db.add_all([remote, repo])
        test_db.commit()
        test_db.refresh(remote)
        test_db.refresh(repo)
        storage = RepositoryStorage(
            repository_id=repo.id,
            backend="rclone",
            rclone_remote_id=remote.id,
            rclone_remote_path="borg-ui/repositories/mirror",
            cache_path=repo.path,
            sync_policy="scheduled",
            sync_status="current",
            sync_direction="primary_to_remote",
            sync_cron_expression="*/15 * * * *",
            sync_timezone="UTC",
            next_scheduled_sync_at=now - timedelta(minutes=5),
        )
        test_db.add(storage)
        test_db.commit()
        monkeypatch.setattr(
            "app.services.rclone_repository_service.rclone_service.sync",
            AsyncMock(
                return_value=RcloneCommandResult(
                    success=False,
                    return_code=1,
                    stdout="",
                    stderr="remote unavailable",
                    command=["rclone", "sync"],
                    redacted_command="rclone sync <path> <path>",
                )
            ),
        )

        await run_due_scheduled_rclone_mirrors(test_db, now)

        test_db.refresh(repo)
        test_db.refresh(storage)
        sync_job = (
            test_db.query(RcloneSyncJob)
            .filter(
                RcloneSyncJob.repository_id == repo.id,
                RcloneSyncJob.triggered_by == "schedule",
            )
            .one()
        )
        assert repo.path == "/repos/mirror"
        assert storage.rclone_remote_path == "borg-ui/repositories/mirror"
        assert storage.sync_status == "failed"
        assert storage.last_sync_error == "remote unavailable"
        assert storage.last_scheduled_sync_at == now.replace(tzinfo=None)
        assert storage.next_scheduled_sync_at > now.replace(tzinfo=None)
        assert sync_job.triggered_by == "schedule"
        assert sync_job.status == "failed"
        assert sync_job.scheduled_for == now.replace(tzinfo=None) - timedelta(minutes=5)
        assert sync_job.error_text == "remote unavailable"
        assert sync_job.log_text == "remote unavailable"

    def test_dispatch_scheduled_rclone_mirror_claims_before_background_task(
        self, test_db, monkeypatch
    ):
        from app.services import rclone_mirror_scheduler

        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        remote = RcloneRemote(name="prod-s3", provider="s3", config_source="managed")
        repo = Repository(
            name="Mirror Repo",
            path="/repos/mirror",
            encryption="none",
            repository_type="local",
            mode="full",
        )
        test_db.add_all([remote, repo])
        test_db.commit()
        test_db.refresh(remote)
        test_db.refresh(repo)
        storage = RepositoryStorage(
            repository_id=repo.id,
            backend="rclone",
            rclone_remote_id=remote.id,
            rclone_remote_path="borg-ui/repositories/mirror",
            cache_path=repo.path,
            sync_policy="scheduled",
            sync_status="current",
            sync_direction="primary_to_remote",
            sync_cron_expression="*/15 * * * *",
            sync_timezone="UTC",
            next_scheduled_sync_at=now - timedelta(minutes=5),
        )
        test_db.add(storage)
        test_db.commit()
        created_coroutines = []

        class FakeTask:
            def add_done_callback(self, callback):
                callback(self)

        def fake_create_task(coro):
            created_coroutines.append(coro)
            coro.close()
            return FakeTask()

        monkeypatch.setattr(
            rclone_mirror_scheduler.asyncio,
            "create_task",
            fake_create_task,
        )

        dispatched = rclone_mirror_scheduler.dispatch_due_scheduled_rclone_mirrors(
            test_db, now
        )

        test_db.refresh(storage)
        assert dispatched == 1
        assert len(created_coroutines) == 1
        assert storage.last_scheduled_sync_at is None
        assert storage.next_scheduled_sync_at > now.replace(tzinfo=None)

    def test_validate_cron_returns_preview_for_valid_expression(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={
                "minute": "0",
                "hour": "*/6",
                "day_of_month": "*",
                "month": "*",
                "day_of_week": "1-5",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["cron_expression"] == "0 */6 * * 1-5"
        assert len(body["next_runs"]) == 10

    def test_validate_cron_returns_structured_failure_for_invalid_expression(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={
                "minute": "invalid",
                "hour": "*",
                "day_of_month": "*",
                "month": "*",
                "day_of_week": "*",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["cron_expression"] == "invalid * * * *"
        assert "Invalid cron expression" in body["error"]
