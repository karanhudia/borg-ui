from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.api.schedule as schedule_api
from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    Repository,
    RepositoryStorage,
    RcloneRemote,
    Operation,
    OperationBackupDetails,
    OperationRcloneDetails,
    ScheduledJob,
    ScheduledJobRepository,
    SSHConnection,
)
from app.services.operations.backup_facade import BackupJobFacade
from app.services.rclone_service import RcloneCommandResult
from tests.utils.operations import seed_job_operation


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
    def test_create_availability_schedule_without_cron_expression(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repository = _create_repo(test_db, "Availability Repo", "/repos/availability")

        response = test_client.post(
            "/api/schedule/",
            json={
                "name": "Availability backup",
                "schedule_mode": "availability",
                "availability_check_interval_minutes": 30,
                "min_success_interval_minutes": 20 * 60,
                "cron_expression": None,
                "timezone": "UTC",
                "repository_id": repository.id,
                "enabled": True,
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        created = response.json()["job"]
        assert created["schedule_mode"] == "availability"
        assert created["cron_expression"] is None
        assert created["next_run"] is not None

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

    def test_update_schedule_clears_prune_keep_within(
        self, test_client: TestClient, admin_headers, test_db
    ):
        schedule = _create_schedule(
            test_db,
            "Keep Within",
            repository="/repos/keep-within",
            prune_keep_within="1d",
        )

        response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={"prune_keep_within": None},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        test_db.refresh(schedule)
        assert schedule.prune_keep_within is None

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
        backup_job = seed_job_operation(
            test_db,
            "backup",
            repository="/repos/delete-me",
            status="completed",
            scheduled_job_id=schedule.id,
        )
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

        operation = test_db.query(Operation).filter(Operation.kind == "backup").one()
        details = test_db.get(OperationBackupDetails, operation.id)
        assert run_key == f"backup:{operation.id}"
        assert operation.trigger == "schedule"
        assert operation.scheduled_job_id == schedule.id
        assert operation.params["archive_name"]
        assert details.route_strategy == "remote_direct"
        assert operation.execution_mode == "remote_ssh"
        assert details.source_ssh_connection_id == connection.id

    @pytest.mark.asyncio
    async def test_multi_repo_schedule_applies_backup_route_metadata(
        self, test_db, monkeypatch
    ):
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
        schedule = _create_schedule(test_db, "Due Remote Direct")
        test_db.add(
            ScheduledJobRepository(
                scheduled_job_id=schedule.id,
                repository_id=repo.id,
                execution_order=0,
            )
        )
        test_db.commit()

        # No runner runs in this unit test, so stand in for the verdict it
        # would write on the row the schedule enqueued.
        async def _complete(db, operation_id, **kwargs):
            operation = db.get(Operation, operation_id)
            operation.status = "completed"
            db.commit()
            return "completed"

        monkeypatch.setattr("app.api.schedule.wait_for_backup_operation", _complete)

        await schedule_api.execute_multi_repo_schedule(schedule, test_db)

        operation = test_db.query(Operation).filter(Operation.kind == "backup").one()
        details = test_db.get(OperationBackupDetails, operation.id)
        assert operation.scheduled_job_id == schedule.id
        assert details.route_strategy == "remote_direct"
        assert operation.execution_mode == "remote_ssh"
        assert details.source_ssh_connection_id == connection.id

    @pytest.mark.asyncio
    async def test_multi_repo_schedule_closes_the_prune_operation_when_the_step_raises(
        self, test_db, monkeypatch
    ):
        """The post-backup prune is an inline operation created `running`.
        When the router raises (an agent job refused by admission), the
        handler must close that row with the cause and record the failed
        step on the backup, or the row blocks the repository until a
        restart."""
        repo = _create_repo(test_db, "Prune Repo", "/repos/prune")
        schedule = _create_schedule(
            test_db,
            "Prune After",
            run_prune_after=True,
            prune_keep_daily=7,
            run_compact_after=True,
        )
        test_db.add(
            ScheduledJobRepository(
                scheduled_job_id=schedule.id,
                repository_id=repo.id,
                execution_order=0,
            )
        )
        test_db.commit()

        async def _complete(db, operation_id, **kwargs):
            operation = db.get(Operation, operation_id)
            operation.status = "completed"
            db.commit()
            return "completed"

        monkeypatch.setattr("app.api.schedule.wait_for_backup_operation", _complete)
        monkeypatch.setattr(
            "app.api.schedule.BorgRouter.prune",
            AsyncMock(side_effect=RuntimeError("agent prune failed: refused")),
        )

        await schedule_api.execute_multi_repo_schedule(schedule, test_db)

        test_db.expire_all()
        prune = test_db.query(Operation).filter(Operation.kind == "prune").one()
        assert prune.status == "failed"
        assert prune.error_message == "agent prune failed: refused"
        assert prune.completed_at is not None
        backup = test_db.query(Operation).filter(Operation.kind == "backup").one()
        assert BackupJobFacade(test_db, backup).maintenance_status == "prune_failed"
        # the compact does not run on a repository whose prune step raised
        assert test_db.query(Operation).filter(Operation.kind == "compact").count() == 0

    @pytest.mark.asyncio
    async def test_multi_repo_schedule_keeps_a_prune_its_agent_is_still_running(
        self, test_db, monkeypatch
    ):
        """The wait on an agent prune can give up (504) while the agent is
        still running it. The handler records the failed step but must not
        close the operation: the agent's report will, and until then the
        repository really is busy."""
        from app.core.security import get_password_hash
        from app.database.models import AgentJob, AgentMachine

        repo = _create_repo(test_db, "Slow Prune Repo", "/repos/slow-prune")
        agent = AgentMachine(
            name="Agent",
            agent_id="agt_slow_prune",
            token_hash=get_password_hash("secret"),
            token_prefix="secret",
            status="online",
        )
        test_db.add(agent)
        schedule = _create_schedule(
            test_db, "Slow Prune After", run_prune_after=True, prune_keep_daily=7
        )
        test_db.add(
            ScheduledJobRepository(
                scheduled_job_id=schedule.id,
                repository_id=repo.id,
                execution_order=0,
            )
        )
        test_db.commit()

        async def _complete(db, operation_id, **kwargs):
            operation = db.get(Operation, operation_id)
            operation.status = "completed"
            db.commit()
            return "completed"

        async def _timeout(self, job_id, *args, **kwargs):
            # The agent job for this operation exists and is running when
            # the server-side wait gives up.
            test_db.add(
                AgentJob(
                    agent_machine_id=agent.id,
                    job_type="repository",
                    status="running",
                    payload={
                        "job_kind": "repository.prune",
                        "operation": {
                            "maintenance_job": {
                                "kind": "prune",
                                "id": job_id,
                                "table": "operations",
                            }
                        },
                    },
                )
            )
            test_db.commit()
            raise RuntimeError(
                "agent prune failed: backend.errors.agents.repositoryOperationTimeout"
            )

        monkeypatch.setattr("app.api.schedule.wait_for_backup_operation", _complete)
        monkeypatch.setattr("app.api.schedule.BorgRouter.prune", _timeout)

        await schedule_api.execute_multi_repo_schedule(schedule, test_db)

        test_db.expire_all()
        prune = test_db.query(Operation).filter(Operation.kind == "prune").one()
        assert prune.status == "running"
        assert prune.error_message is None
        backup = test_db.query(Operation).filter(Operation.kind == "backup").one()
        assert BackupJobFacade(test_db, backup).maintenance_status == "prune_failed"

    @pytest.mark.asyncio
    async def test_multi_repo_schedule_closes_the_compact_operation_when_the_step_raises(
        self, test_db, monkeypatch
    ):
        repo = _create_repo(test_db, "Compact Repo", "/repos/compact")
        schedule = _create_schedule(test_db, "Compact After", run_compact_after=True)
        test_db.add(
            ScheduledJobRepository(
                scheduled_job_id=schedule.id,
                repository_id=repo.id,
                execution_order=0,
            )
        )
        test_db.commit()

        async def _complete(db, operation_id, **kwargs):
            operation = db.get(Operation, operation_id)
            operation.status = "completed"
            db.commit()
            return "completed"

        monkeypatch.setattr("app.api.schedule.wait_for_backup_operation", _complete)
        monkeypatch.setattr(
            "app.api.schedule.BorgRouter.compact",
            AsyncMock(side_effect=RuntimeError("agent compact failed: refused")),
        )

        await schedule_api.execute_multi_repo_schedule(schedule, test_db)

        test_db.expire_all()
        compact = test_db.query(Operation).filter(Operation.kind == "compact").one()
        assert compact.status == "failed"
        assert compact.error_message == "agent compact failed: refused"
        backup = test_db.query(Operation).filter(Operation.kind == "backup").one()
        assert BackupJobFacade(test_db, backup).maintenance_status == "compact_failed"

    @pytest.mark.asyncio
    async def test_single_repo_schedule_closes_the_prune_operation_when_the_step_raises(
        self, test_db, monkeypatch
    ):
        """The single-repository schedule path has its own post-backup
        handlers; they must close the inline operation the same way."""
        from app.services.operations.backup_facade import create_backup_operation

        repo = _create_repo(test_db, "Single Prune Repo", "/repos/single-prune")
        schedule = _create_schedule(
            test_db, "Single Prune After", run_prune_after=True, prune_keep_daily=7
        )
        backup_job = create_backup_operation(
            test_db,
            repo,
            trigger="schedule",
            executor="server",
            params={},
            scheduled_job_id=schedule.id,
        )
        backup_job.status = "completed"
        backup_job.completed_at = datetime.utcnow()
        test_db.commit()

        async def _completed(db, operation_id, **kwargs):
            return "completed"

        monkeypatch.setattr("app.api.schedule.wait_for_backup_operation", _completed)
        monkeypatch.setattr(
            "app.api.schedule.BorgRouter.prune",
            AsyncMock(side_effect=RuntimeError("agent prune failed: refused")),
        )

        await schedule_api.execute_scheduled_backup_with_maintenance(
            backup_job.id, repo.path, schedule.id
        )

        test_db.expire_all()
        prune = test_db.query(Operation).filter(Operation.kind == "prune").one()
        assert prune.status == "failed"
        assert prune.error_message == "agent prune failed: refused"
        assert prune.completed_at is not None
        backup = test_db.get(Operation, backup_job.id)
        assert BackupJobFacade(test_db, backup).maintenance_status == "prune_failed"

    def test_dispatch_due_multi_repo_schedule_defers_for_active_repository_work(
        self, test_db, monkeypatch
    ):
        from app.api.schedule import _dispatch_due_scheduled_job

        repo = _create_repo(test_db, "Repo A", "/repos/a")
        schedule = _create_schedule(
            test_db,
            "Busy Multi",
            next_run=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        original_next_run = schedule.next_run
        test_db.add(
            ScheduledJobRepository(
                scheduled_job_id=schedule.id,
                repository_id=repo.id,
                execution_order=0,
            )
        )
        test_db.add(
            seed_job_operation(
                test_db,
                "backup",
                repository=repo.path,
                repository_id=repo.id,
                status="running",
                scheduled_job_id=schedule.id,
            )
        )
        test_db.commit()

        def fail_create_task(coro):
            coro.close()
            raise AssertionError("multi-repo schedule task should not start")

        monkeypatch.setattr("app.api.schedule.asyncio.create_task", fail_create_task)

        run_key = _dispatch_due_scheduled_job(
            test_db, schedule, datetime.now(timezone.utc)
        )

        test_db.refresh(schedule)
        assert run_key is None
        assert schedule.last_run is None
        assert schedule.next_run == original_next_run

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
        # Phase 6: the scheduler only queues. The runner starts the sync, and
        # the executor records the outcome and the storage failure, so this
        # test now pins the queued row and the schedule bookkeeping only.
        operation = (
            test_db.query(Operation)
            .filter(
                Operation.repository_id == repo.id,
                Operation.kind == "rclone_sync",
                Operation.trigger == "schedule",
            )
            .one()
        )
        details = test_db.get(OperationRcloneDetails, operation.id)
        assert repo.path == "/repos/mirror"
        assert storage.rclone_remote_path == "borg-ui/repositories/mirror"
        assert storage.next_scheduled_sync_at > now.replace(tzinfo=None)
        assert operation.status == "queued"
        assert details.operation == "sync"
        assert details.direction == "primary_to_remote"
        assert details.scheduled_for == now.replace(tzinfo=None) - timedelta(minutes=5)

    def test_dispatch_scheduled_rclone_mirror_queues_one_run_per_slot(
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
        dispatched = rclone_mirror_scheduler.dispatch_due_scheduled_rclone_mirrors(
            test_db, now
        )

        test_db.refresh(storage)
        operation = (
            test_db.query(Operation)
            .filter(
                Operation.kind == "rclone_sync",
                Operation.repository_id == repo.id,
            )
            .one()
        )
        assert dispatched == 1
        assert operation.status == "queued"
        assert operation.trigger == "schedule"
        assert storage.last_scheduled_sync_at is None
        assert storage.next_scheduled_sync_at > now.replace(tzinfo=None)

        # A second tick over the same slot must not queue a duplicate.
        second = rclone_mirror_scheduler.dispatch_due_scheduled_rclone_mirrors(
            test_db, now
        )
        assert second == 0
        assert (
            test_db.query(Operation).filter(Operation.kind == "rclone_sync").count()
            == 1
        )

    def test_dispatch_scheduled_rclone_mirror_skips_a_repository_still_in_flight(
        self, test_db, monkeypatch
    ):
        """The pre-phase-6 scheduler skipped a storage whose sync task was still
        running. A queued or running scheduled run is the same signal now: the
        slot stays due and is picked up once that run has finished."""
        from app.services import rclone_mirror_scheduler
        from app.services.operations.details import rclone_details
        from app.services.operations.enqueue import enqueue

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
        due_at = now - timedelta(minutes=5)
        storage = RepositoryStorage(
            repository_id=repo.id,
            backend="rclone",
            rclone_remote_id=remote.id,
            rclone_remote_path="borg-ui/repositories/mirror",
            cache_path=repo.path,
            sync_policy="scheduled",
            sync_status="syncing",
            sync_direction="primary_to_remote",
            sync_cron_expression="*/15 * * * *",
            sync_timezone="UTC",
            next_scheduled_sync_at=due_at,
        )
        test_db.add(storage)
        earlier = enqueue(
            test_db,
            "rclone_sync",
            repository_id=repo.id,
            trigger="schedule",
            commit=False,
        )
        earlier.status = "running"
        rclone_details(test_db, earlier).scheduled_for = due_at - timedelta(minutes=15)
        test_db.commit()

        dispatched = rclone_mirror_scheduler.dispatch_due_scheduled_rclone_mirrors(
            test_db, now
        )

        test_db.refresh(storage)
        assert dispatched == 0
        assert (
            test_db.query(Operation).filter(Operation.kind == "rclone_sync").count()
            == 1
        )
        assert storage.next_scheduled_sync_at == due_at.replace(tzinfo=None)

    def test_dispatch_scheduled_rclone_mirror_keeps_the_slot_when_enqueue_fails(
        self, test_db, monkeypatch
    ):
        """The schedule advance and the new operation commit together: if the
        enqueue raises, the slot is still due on the next tick and no mirror
        run is lost."""
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
        due_at = now - timedelta(minutes=5)
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
            next_scheduled_sync_at=due_at,
        )
        test_db.add(storage)
        test_db.commit()

        def _explode(*args, **kwargs):
            raise RuntimeError("database locked")

        monkeypatch.setattr(rclone_mirror_scheduler, "enqueue", _explode)

        with pytest.raises(RuntimeError, match="database locked"):
            rclone_mirror_scheduler.dispatch_due_scheduled_rclone_mirrors(test_db, now)

        test_db.rollback()
        test_db.refresh(storage)
        assert storage.next_scheduled_sync_at == due_at.replace(tzinfo=None)
        assert (
            test_db.query(Operation).filter(Operation.kind == "rclone_sync").count()
            == 0
        )

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
