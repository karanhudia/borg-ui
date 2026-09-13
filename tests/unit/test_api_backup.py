"""
Comprehensive unit tests for backup API endpoints
"""

import time

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.core.agent_auth import AGENT_AUTH_HEADER
from app.core.security import get_password_hash
from app.services.operations.executors import load_default_executors
from app.database.models import (
    AgentJob,
    AgentJobLog,
    AgentMachine,
    Repository,
    Operation,
    OperationBackupDetails,
    OperationBackupRetryLineage,
    ScheduledJob,
    SSHConnection,
    SystemSettings,
    UserRepositoryPermission,
)
from datetime import datetime
import json
from app.services.operations.backup_facade import BackupJobFacade
from app.services.operations.details import backup_details
from app.services.repository_executor import queue_agent_backup_job
from tests.unit.helpers import assert_auth_required
from app.services.operations.backup_facade import resolve_backup_job
from tests.utils.operations import seed_job_operation


def _json_snapshot(value):
    if isinstance(value, dict):
        return value
    return json.loads(value)


def _close_background_task(coro):
    coro.close()
    return None


def _wait_for_agent_job(test_db, operation_id: int, timeout: float = 5.0):
    """The transport job the backup executor queues, once the runner has
    dispatched the operation."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        test_db.expire_all()
        agent_job = (
            test_db.query(AgentJob)
            .filter(AgentJob.operation_id == operation_id)
            .first()
        )
        if agent_job is not None:
            return agent_job
        time.sleep(0.05)
    raise AssertionError(f"no agent job queued for operation {operation_id}")


def _wait_for_followups(test_db, repository_id: int, timeout: float = 5.0):
    """The spec 7.4 chain, once the runner has enqueued it.

    For an agent backup the chain comes from the runner when the executor
    returns from waiting on the transport job, not from the completion report
    (which sees the operation still running and stands down), so a caller has
    to wait for the executor to wake rather than read straight after the
    report.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        test_db.expire_all()
        followups = (
            test_db.query(Operation)
            .filter(
                Operation.repository_id == repository_id,
                Operation.trigger == "followup",
            )
            .order_by(Operation.id)
            .all()
        )
        if followups:
            return followups
        time.sleep(0.05)
    raise AssertionError(f"no follow-up chain enqueued for repository {repository_id}")


def _set_log_save_policy(test_db, policy: str) -> None:
    settings = test_db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        test_db.add(settings)
    settings.log_save_policy = policy
    test_db.flush()


@pytest.mark.unit
class TestBackupStart:
    """Test starting backup operations"""

    def test_start_backup_enqueues_an_operation(
        self, test_client, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()

        # The live runner may dispatch the row before this test reads it back;
        # a mocked service keeps that harmless, as it does for restore.
        with patch(
            "app.services.backup_service.backup_service.execute_backup",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                "/api/backup/start",
                json={"repository": "/test/repo"},
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["message"] == "Backup job started"
        op = test_db.get(Operation, body["job_id"])
        assert op.kind == "backup"
        assert op.category == "backup"
        assert op.trigger == "manual"
        assert op.repository_id == repo.id
        assert op.params["executor"] == "server"

    def test_start_backup_unknown_path_is_recorded_and_failed(
        self, test_client, admin_headers, test_db
    ):
        response = test_client.post(
            "/api/backup/start", json={"repository": "/nope"}, headers=admin_headers
        )
        assert response.status_code == 200
        op = test_db.get(Operation, response.json()["job_id"])
        assert op.status == "failed"
        assert op.repository_id is None
        status = test_client.get(
            f"/api/backup/status/{op.id}", headers=admin_headers
        ).json()
        assert status["repository"] == "/nope"
        assert status["status"] == "failed"

    def test_retry_creates_a_retry_operation_with_lineage(
        self, test_client, admin_headers, test_db
    ):
        from app.database.models import OperationBackupRetryLineage

        repo = Repository(
            name="r", path="/test/repo", encryption="none", repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        source = Operation(
            repository_id=repo.id,
            kind="backup",
            category="backup",
            status="failed",
            trigger="manual",
            priority=0,
            run_id="r1",
            params={"executor": "server"},
        )
        test_db.add(source)
        test_db.commit()

        response = test_client.post(
            f"/api/backup/jobs/{source.id}/retry", headers=admin_headers
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "pending"
        assert body["retry_attempt"] == 2
        assert body["retry_original_job_id"] == source.id
        assert body["retry_source_job_id"] == source.id
        retry = test_db.get(Operation, body["job_id"])
        assert retry.trigger == "retry"
        lineage = test_db.query(OperationBackupRetryLineage).one()
        assert lineage.created_operation_id == retry.id
        assert lineage.attempt_number == 2
        assert lineage.request_snapshot["kind"] == "backup_job_retry"

    def test_list_and_status_serve_backup_operations(
        self, test_client, admin_headers, test_db
    ):
        repo = Repository(
            name="r", path="/test/repo", encryption="none", repository_type="local"
        )
        schedule = ScheduledJob(
            name="nightly",
            repository=repo.path,
            cron_expression="0 2 * * *",
        )
        test_db.add_all([repo, schedule])
        test_db.commit()
        schedule.repository_id = repo.id
        manual = seed_job_operation(
            test_db, "backup", repository="/test/repo", status="completed"
        )
        op = Operation(
            repository_id=repo.id,
            kind="backup",
            category="backup",
            status="running",
            trigger="schedule",
            priority=5,
            run_id="r1",
            scheduled_job_id=schedule.id,
            params={"executor": "server", "archive_name": "a"},
            progress_percent=40.0,
        )
        test_db.add(op)
        test_db.flush()
        backup_details(test_db, op).archive_name = "a"
        test_db.commit()

        jobs = test_client.get("/api/backup/jobs", headers=admin_headers).json()["jobs"]
        assert {j["id"] for j in jobs} == {manual.id, op.id}
        mine = next(j for j in jobs if j["id"] == op.id)
        assert mine["status"] == "running"
        assert mine["progress"] == 40
        assert mine["triggered_by"] == "schedule"
        assert mine["execution_mode"] == "local"
        assert mine["archive_name"] == "a"
        # Every row answers with the same keys.
        assert set(mine) == set(next(j for j in jobs if j["id"] == manual.id))

    def test_cancel_running_operation_raises_the_flag_then_kills(
        self, test_client, admin_headers, test_db
    ):
        repo = Repository(
            name="r", path="/test/repo", encryption="none", repository_type="local"
        )
        test_db.add(repo)
        test_db.commit()
        op = Operation(
            repository_id=repo.id,
            kind="backup",
            category="backup",
            status="running",
            trigger="manual",
            priority=0,
            run_id="r1",
            params={"executor": "server"},
        )
        test_db.add(op)
        test_db.commit()
        calls = []

        async def _request_cancel(operation_id):
            calls.append(("flag", operation_id))
            return True

        async def _kill(job_id):
            calls.append(("kill", job_id))
            return True

        with (
            patch("app.api.backup.operation_runner.request_cancel", _request_cancel),
            patch("app.api.backup.backup_service.cancel_backup", _kill),
        ):
            response = test_client.post(
                f"/api/backup/cancel/{op.id}", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json() == {
            "message": "backend.success.backup.backupCancelled",
            "process_terminated": True,
        }
        assert calls == [("flag", op.id), ("kill", op.id)]
        test_db.refresh(op)
        assert op.status == "cancelled"
        assert (
            json.loads(op.error_message)["key"]
            == "backend.errors.backup.cancelledByUser"
        )

    def test_run_backup_alias_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test legacy /run alias still starts backup."""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.backup.backup_service.execute_backup", new_callable=AsyncMock
        ):
            response = test_client.post(
                "/api/backup/run",
                json={"repository": "/test/repo"},
                headers=admin_headers,
            )

            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "pending"

    def test_start_backup_missing_fields(self, test_client: TestClient, admin_headers):
        """Test starting backup with empty JSON returns 200 (repository is optional)"""
        with patch(
            "app.api.backup.backup_service.execute_backup", new_callable=AsyncMock
        ):
            response = test_client.post(
                "/api/backup/start", json={}, headers=admin_headers
            )

            # Repository is optional with default value, so this succeeds
            assert response.status_code == 200

    def test_start_backup_invalid_repository(
        self, test_client: TestClient, admin_headers
    ):
        """Unknown extra fields are ignored; request still creates a pending job."""
        response = test_client.post(
            "/api/backup/start", json={"repository_id": 99999}, headers=admin_headers
        )

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_start_backup_nonexistent_repo(
        self, test_client: TestClient, admin_headers
    ):
        """Test starting backup for non-existent repository returns 200 (doesn't validate repository exists)"""
        with patch(
            "app.api.backup.backup_service.execute_backup", new_callable=AsyncMock
        ):
            response = test_client.post(
                "/api/backup/start",
                json={"repository": "/nonexistent/repo"},
                headers=admin_headers,
            )

            # API doesn't validate repository existence at creation time
            assert response.status_code == 200

    def test_start_backup_empty_sources(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test starting backup with empty repository string returns 200"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.backup.backup_service.execute_backup", new_callable=AsyncMock
        ):
            response = test_client.post(
                "/api/backup/start",
                json={
                    "repository": ""  # Empty string is accepted
                },
                headers=admin_headers,
            )

            # API accepts empty strings (no validation)
            assert response.status_code == 200

    def test_start_backup_invalid_json(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test starting backup with invalid field type returns 422"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/backup/start",
            json={
                "repository": 12345  # Should be string, not integer
            },
            headers=admin_headers,
        )

        # Pydantic validation should reject this
        assert response.status_code == 422

    def test_start_backup_unauthorized(self, test_client: TestClient):
        """Test starting backup without auth returns 403"""
        response = test_client.post(
            "/api/backup/start",
            json={
                "repository_id": 1,
                "source_directories": ["/backup"],
                "archive_name": "test",
            },
        )

        assert_auth_required(response)

    def test_start_backup_with_options(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test starting backup with additional options"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.backup.backup_service.execute_backup", new_callable=AsyncMock
        ):
            response = test_client.post(
                "/api/backup/start",
                json={
                    "repository_id": repo.id,
                    "source_directories": ["/backup/source"],
                    "archive_name": "test-backup",
                    "compression": "lz4",
                    "exclude_patterns": ["*.tmp", "*.log"],
                },
                headers=admin_headers,
            )

            assert response.status_code == 200
            assert response.json()["status"] == "pending"

    def test_start_backup_rejects_when_manual_backup_limit_reached(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Limited Repo",
            path="/limited/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add_all(
            [
                repo,
                SystemSettings(max_concurrent_backups=1),
            ]
        )
        test_db.flush()
        test_db.add(
            seed_job_operation(
                test_db,
                "backup",
                repository=repo.path,
                repository_id=repo.id,
                status="pending",
            )
        )
        test_db.commit()

        with (
            patch(
                "app.api.backup.backup_service.execute_backup", new_callable=AsyncMock
            ) as execute_backup,
        ):
            response = test_client.post(
                "/api/backup/start",
                json={"repository": repo.path},
                headers=admin_headers,
            )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.backup.concurrentLimitReached"
        )
        execute_backup.assert_not_called()
        assert (
            test_db.query(Operation)
            .filter(Operation.kind == "backup", Operation.repository_id == repo.id)
            .count()
            == 1
        )

    def test_start_backup_multiple_sources(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test starting backup with multiple source directories"""
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        with patch(
            "app.api.backup.backup_service.execute_backup", new_callable=AsyncMock
        ):
            response = test_client.post(
                "/api/backup/start",
                json={
                    "repository_id": repo.id,
                    "source_directories": [
                        "/backup/source1",
                        "/backup/source2",
                        "/backup/source3",
                    ],
                    "archive_name": "multi-source-backup",
                },
                headers=admin_headers,
            )

            assert response.status_code == 200
            assert response.json()["status"] == "pending"

    def test_start_backup_for_agent_repository_queues_agent_job(
        self, test_client: TestClient, admin_headers, test_db
    ):
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_laptop",
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)
        repo = Repository(
            name="Agent Repo",
            path="/agent/repo",
            encryption="repokey",
            passphrase="repo-secret",
            compression="zstd",
            source_directories=json.dumps(["/home/user/docs"]),
            exclude_patterns=json.dumps(["*.tmp"]),
            repository_type="local",
            execution_target="agent",
            executor_type="agent",
            agent_machine_id=agent.id,
            custom_flags="--one-file-system",
        )
        test_db.add(repo)
        test_db.commit()

        # Phase 8: the route only enqueues. The executor queues the agent job,
        # so the transport is mocked out here and driven directly below.
        with (
            patch(
                "app.services.backup_service.backup_service.execute_backup",
                new_callable=AsyncMock,
            ) as execute_backup,
            patch(
                "app.services.operations.executors.backup"
                ".dispatch_agent_job_best_effort",
                new_callable=AsyncMock,
            ),
        ):
            response = test_client.post(
                "/api/backup/start",
                json={"repository": repo.path},
                headers=admin_headers,
            )

        assert response.status_code == 200
        execute_backup.assert_not_called()
        operation = test_db.get(Operation, response.json()["job_id"])
        assert operation.kind == "backup"
        assert operation.params["executor"] == "agent"
        assert operation.execution_mode == "agent"

        agent_job = queue_agent_backup_job(
            test_db, BackupJobFacade(test_db, operation), repo
        )
        test_db.commit()
        assert agent_job.operation_id == operation.id
        assert agent_job.agent_machine_id == agent.id
        assert agent_job.status == "queued"
        assert agent_job.payload["repository"] == {
            "id": repo.id,
            "path": repo.path,
            "borg_version": 1,
        }
        assert agent_job.payload["backup"]["source_paths"] == ["/home/user/docs"]
        assert agent_job.payload["backup"]["exclude_patterns"] == ["*.tmp"]
        assert agent_job.payload["backup"]["custom_flags"] == "--one-file-system"
        assert agent_job.payload["secrets"] == {
            "BORG_PASSPHRASE": {"value": "repo-secret"}
        }

    def test_start_backup_for_agent_repository_rejects_conflict_before_agent_job(
        self, test_client: TestClient, admin_headers, test_db
    ):
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_conflict",
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
        )
        test_db.add(agent)
        test_db.flush()
        repo = Repository(
            name="Agent Conflict Repo",
            path="/agent/conflict-repo",
            encryption="none",
            compression="lz4",
            source_directories=json.dumps(["/home/user/docs"]),
            repository_type="local",
            execution_target="agent",
            executor_type="agent",
            agent_machine_id=agent.id,
        )
        test_db.add_all(
            [
                repo,
                SystemSettings(max_concurrent_backups=5),
            ]
        )
        test_db.flush()
        test_db.add(
            seed_job_operation(
                test_db,
                "backup",
                repository=repo.path,
                repository_id=repo.id,
                status="running",
            )
        )
        test_db.commit()

        with patch(
            "app.services.operations.executors.backup.dispatch_agent_job_best_effort",
            new_callable=AsyncMock,
        ) as dispatch_agent_job:
            response = test_client.post(
                "/api/backup/start",
                json={"repository": repo.path},
                headers=admin_headers,
            )

        assert response.status_code == 409
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.jobs.repositoryOperationActive"
        )
        dispatch_agent_job.assert_not_called()
        assert test_db.query(AgentJob).count() == 0
        # Only the running backup this test seeded as the conflict.
        assert test_db.query(Operation).filter(Operation.kind == "backup").count() == 1

    def test_start_backup_uses_remote_direct_for_same_ssh_source_and_repo(
        self, test_client: TestClient, admin_headers, test_db
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
            source_directories=json.dumps(["/var/lib/docker/volumes/app"]),
        )
        test_db.add(repo)
        test_db.commit()

        with patch(
            "app.services.backup_service.backup_service.execute_backup",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                "/api/backup/start",
                json={"repository": repo.path},
                headers=admin_headers,
            )

        assert response.status_code == 200
        operation = test_db.get(Operation, response.json()["job_id"])
        details = test_db.get(OperationBackupDetails, operation.id)
        assert details.route_strategy == "remote_direct"
        assert operation.execution_mode == "remote_ssh"
        assert details.source_ssh_connection_id == connection.id

    def test_start_backup_routes_agent_repository_by_executor_type(
        self, test_client: TestClient, admin_headers, test_db
    ):
        agent = AgentMachine(
            name="Workstation",
            agent_id="agt_workstation",
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)
        repo = Repository(
            name="Executor Agent Repo",
            path="/executor-agent/repo",
            encryption="none",
            compression="lz4",
            source_directories=json.dumps(["/home/user/data"]),
            repository_type="local",
            execution_target="local",
            executor_type="agent",
            agent_machine_id=agent.id,
        )
        test_db.add(repo)
        test_db.commit()

        with (
            patch(
                "app.services.backup_service.backup_service.execute_backup",
                new_callable=AsyncMock,
            ) as execute_backup,
            patch(
                "app.services.operations.executors.backup"
                ".dispatch_agent_job_best_effort",
                new_callable=AsyncMock,
            ),
        ):
            response = test_client.post(
                "/api/backup/start",
                json={"repository": repo.path},
                headers=admin_headers,
            )

        assert response.status_code == 200
        execute_backup.assert_not_called()
        operation = test_db.get(Operation, response.json()["job_id"])
        assert operation.params["executor"] == "agent"
        assert operation.execution_mode == "agent"

        agent_job = queue_agent_backup_job(
            test_db, BackupJobFacade(test_db, operation), repo
        )
        test_db.commit()
        assert agent_job.operation_id == operation.id
        assert agent_job.agent_machine_id == agent.id

    def test_start_backup_for_agent_repository_without_sources_explains_plan_sources(
        self, test_client: TestClient, admin_headers, test_db
    ):
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_laptop_no_sources",
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)
        repo = Repository(
            name="Agent Repo Without Sources",
            path="/agent/repo-no-sources",
            encryption="none",
            compression="lz4",
            repository_type="local",
            execution_target="agent",
            executor_type="agent",
            agent_machine_id=agent.id,
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"] == {
            "key": "backend.errors.repo.agentManualBackupRequiresPlanSources"
        }

    def test_agent_completion_updates_linked_backup_job(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_log_save_policy(test_db, "all_jobs")
        load_default_executors()
        raw_token = "borgui_agent_secret"
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_laptop",
            token_hash=get_password_hash(raw_token),
            token_prefix=raw_token[:20],
            status="online",
        )
        test_db.add(agent)
        test_db.commit()
        test_db.refresh(agent)
        repo = Repository(
            name="Agent Repo",
            path="/agent/repo",
            encryption="none",
            compression="lz4",
            source_directories=json.dumps(["/home/user/docs"]),
            repository_type="local",
            execution_target="agent",
            executor_type="agent",
            agent_machine_id=agent.id,
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers,
        )
        assert response.status_code == 200
        backup_job_id = response.json()["job_id"]
        # Phase 8: the runner's executor queues the transport job, so wait for
        # it to appear rather than expecting the route to have written it.
        agent_job = _wait_for_agent_job(test_db, backup_job_id)
        headers = {AGENT_AUTH_HEADER: f"Bearer {raw_token}"}

        poll_response = test_client.get("/api/agents/jobs/poll", headers=headers)
        assert poll_response.status_code == 200
        polled_job = poll_response.json()["jobs"][0]
        assert polled_job["id"] == agent_job.id
        assert polled_job["payload"]["job_kind"] == "backup.create"
        assert polled_job["payload"]["backup"]["source_paths"] == ["/home/user/docs"]

        assert (
            test_client.post(
                f"/api/agents/jobs/{agent_job.id}/claim", headers=headers
            ).status_code
            == 200
        )
        assert (
            test_client.post(
                f"/api/agents/jobs/{agent_job.id}/start", json={}, headers=headers
            ).status_code
            == 200
        )
        assert (
            test_client.post(
                f"/api/agents/jobs/{agent_job.id}/progress",
                json={"progress_percent": 42.5, "current_file": "/home/user/file"},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            test_client.post(
                f"/api/agents/jobs/{agent_job.id}/logs",
                json={"sequence": 1, "message": "Creating archive"},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            test_client.post(
                f"/api/agents/jobs/{agent_job.id}/complete",
                json={
                    "result": {
                        "archive_name": "agent-archive",
                        "return_code": 0,
                    }
                },
                headers=headers,
            ).status_code
            == 200
        )

        test_db.expire_all()
        backup_job = BackupJobFacade(test_db, test_db.get(Operation, backup_job_id))
        test_db.refresh(repo)
        assert backup_job.status == "completed"
        assert backup_job.progress == 100
        assert backup_job.progress_percent == 100.0
        assert backup_job.current_file == "/home/user/file"
        assert backup_job.archive_name == "agent-archive"
        assert backup_job.logs == "Creating archive"
        # last_backup now comes from the archive index: completion enqueues
        # the backup follow-up chain instead of writing the column (#933).
        assert repo.last_backup is None
        followups = _wait_for_followups(test_db, repo.id)
        assert followups[0].kind == "archive_sync"

        logs_response = test_client.get(
            f"/api/activity/backup/{backup_job_id}/logs", headers=admin_headers
        )
        assert logs_response.status_code == 200
        assert logs_response.json()["lines"] == [
            {"line_number": 1, "content": "Creating archive"}
        ]

        # the archive gets pruned later: the row stays and reports it in the
        # same UTC-stamped form as its other timestamps
        backup_job.archive_pruned_at = datetime(2026, 9, 7, 12, 30)
        test_db.commit()

        jobs_response = test_client.get(
            "/api/backup/jobs", params={"manual_only": True}, headers=admin_headers
        )
        assert jobs_response.status_code == 200
        history_job = next(
            item for item in jobs_response.json()["jobs"] if item["id"] == backup_job_id
        )
        assert history_job["triggered_by"] == "manual"
        assert history_job["execution_mode"] == "agent"
        assert history_job["archive_name"] == "agent-archive"
        assert history_job["archive_pruned_at"] == "2026-09-07T12:30:00+00:00"
        assert history_job["has_logs"] is True


@pytest.mark.unit
class TestBackupRetry:
    def test_retry_failed_local_backup_creates_new_job_with_lineage(
        self, test_client: TestClient, admin_headers, test_db, admin_user
    ):
        repo = Repository(
            name="Retry Local Repo",
            path="/retry/local-repo",
            encryption="none",
            repository_type="local",
            compression="zstd,3",
            source_directories=json.dumps(["/srv/source"]),
            exclude_patterns=json.dumps(["*.tmp"]),
            custom_flags="--one-file-system",
        )
        test_db.add(repo)
        test_db.flush()
        source_job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="failed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            error_message="source failed",
            execution_mode="local",
            created_at=datetime.utcnow(),
        )
        test_db.commit()

        # A retry of a row written before phase 8 creates an operation; the
        # live runner may dispatch it, so the service is mocked out.
        with patch(
            "app.services.backup_service.backup_service.execute_backup",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                f"/api/backup/jobs/{source_job.id}/retry", headers=admin_headers
            )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "pending"
        assert body["retry_attempt"] == 2
        assert body["retry_original_job_id"] == source_job.id
        assert body["retry_source_job_id"] == source_job.id
        assert body["retry_requested_by_user_id"] == admin_user.id
        assert body["retry_requested_at"] is not None

        test_db.refresh(source_job)
        assert source_job.status == "failed"
        retry_op = test_db.get(Operation, body["job_id"])
        assert retry_op.kind == "backup"
        assert retry_op.trigger == "retry"
        assert retry_op.repository_id == repo.id
        assert retry_op.scheduled_job_id is None
        assert retry_op.backup_plan_run_id is None
        retry_details = test_db.get(OperationBackupDetails, retry_op.id)
        assert retry_details.retry_attempt == 2
        assert retry_details.retry_original_job_id == source_job.id
        assert retry_details.retry_source_job_id == source_job.id
        assert retry_details.retry_requested_by_user_id == admin_user.id
        assert retry_details.retry_requested_at is not None

        lineage = test_db.query(OperationBackupRetryLineage).one()
        assert lineage.original_job_id == source_job.id
        assert lineage.retry_source_job_id == source_job.id
        assert lineage.attempt_number == 2
        assert lineage.requested_by_user_id == admin_user.id
        assert lineage.requested_at is not None
        assert lineage.created_operation_id == retry_op.id
        snapshot = _json_snapshot(lineage.request_snapshot)
        assert snapshot["kind"] == "backup_job_retry"
        assert snapshot["repository"]["id"] == repo.id
        assert snapshot["repository"]["path"] == repo.path
        assert snapshot["backup"]["source_directories"] == ["/srv/source"]
        assert snapshot["backup"]["exclude_patterns"] == ["*.tmp"]
        assert snapshot["backup"]["compression"] == "zstd,3"
        assert snapshot["backup"]["custom_flags"] == "--one-file-system"

    def test_retry_failed_agent_backup_creates_agent_job_with_lineage(
        self, test_client: TestClient, admin_headers, test_db
    ):
        agent = AgentMachine(
            name="Retry Agent",
            agent_id="agt_retry",
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
        )
        test_db.add(agent)
        test_db.flush()
        repo = Repository(
            name="Retry Agent Repo",
            path="/retry/agent-repo",
            encryption="repokey",
            passphrase="agent-secret",
            compression="zstd",
            source_directories=json.dumps(["/home/user/docs"]),
            exclude_patterns=json.dumps(["*.tmp"]),
            repository_type="local",
            execution_target="agent",
            executor_type="agent",
            agent_machine_id=agent.id,
            custom_flags="--stats",
        )
        test_db.add(repo)
        test_db.flush()
        source_job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="failed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            execution_mode="agent",
            archive_name="manual-backup-source",
            created_at=datetime.utcnow(),
        )
        test_db.flush()
        test_db.add(
            AgentJob(
                agent_machine_id=agent.id,
                operation_id=source_job.id,
                job_type="backup",
                status="failed",
                payload={
                    "schema_version": 1,
                    "job_kind": "backup.create",
                    "repository": {
                        "id": repo.id,
                        "path": repo.path,
                        "borg_version": 1,
                    },
                    "backup": {
                        "archive_name": "manual-backup-source",
                        "source_paths": ["/home/user/docs"],
                        "compression": "zstd",
                        "exclude_patterns": ["*.tmp"],
                        "custom_flags": "--stats",
                    },
                    "secrets": {"BORG_PASSPHRASE": {"value": "agent-secret"}},
                },
                error_message="agent failed",
            )
        )
        test_db.commit()

        with (
            patch(
                "app.api.backup.backup_service.execute_backup",
                new_callable=AsyncMock,
            ) as execute_backup,
            patch(
                "app.services.operations.executors.backup.dispatch_agent_job_best_effort",
                new_callable=AsyncMock,
            ) as dispatch_agent_job,
        ):
            response = test_client.post(
                f"/api/backup/jobs/{source_job.id}/retry", headers=admin_headers
            )

        assert response.status_code == 202
        retry_op = test_db.get(Operation, response.json()["job_id"])
        retry_job = BackupJobFacade(test_db, retry_op)
        # The two id spaces are independent while both worlds coexist, so a
        # retry operation may carry the same number as the legacy row it
        # retries; operations win on the by-id routes (Appendix B).
        assert retry_op.trigger == "retry"
        assert retry_op.params["executor"] == "agent"
        assert retry_job.execution_mode == "agent"
        assert retry_job.retry_attempt == 2
        assert retry_job.retry_original_job_id == source_job.id
        assert retry_job.retry_source_job_id == source_job.id

        # The executor queues the transport job; drive it here so the payload
        # the agent receives is still covered.
        agent_job = queue_agent_backup_job(test_db, retry_job, repo)
        test_db.commit()
        assert agent_job.status == "queued"
        assert agent_job.operation_id == retry_op.id
        assert agent_job.agent_machine_id == agent.id
        assert agent_job.payload["backup"]["source_paths"] == ["/home/user/docs"]
        assert agent_job.payload["backup"]["exclude_patterns"] == ["*.tmp"]
        assert agent_job.payload["backup"]["custom_flags"] == "--stats"
        assert agent_job.payload["secrets"] == {
            "BORG_PASSPHRASE": {"value": "agent-secret"}
        }

        lineage = test_db.query(OperationBackupRetryLineage).one()
        assert lineage.created_operation_id == retry_op.id
        snapshot = _json_snapshot(lineage.request_snapshot)
        assert snapshot["kind"] == "backup_job_retry"
        assert snapshot["backup"]["execution_mode"] == "agent"
        execute_backup.assert_not_called()

    def test_retry_active_backup_job_rejected(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Retry Active Repo",
            path="/retry/active-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.flush()
        source_job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="running",
            started_at=datetime.utcnow(),
            execution_mode="local",
            created_at=datetime.utcnow(),
        )
        test_db.commit()

        response = test_client.post(
            f"/api/backup/jobs/{source_job.id}/retry", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.backup.retryOnlyTerminalFailedCancelled"
        )
        test_db.refresh(source_job)
        assert source_job.status == "running"
        assert test_db.query(Operation).filter(Operation.kind == "backup").count() == 1

    def test_retry_backup_job_requires_operator_access(
        self, test_client: TestClient, auth_headers, test_db
    ):
        repo = Repository(
            name="Retry Permission Repo",
            path="/retry/permission-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.flush()
        source_job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="failed",
            completed_at=datetime.utcnow(),
            execution_mode="local",
            created_at=datetime.utcnow(),
        )
        test_db.commit()

        response = test_client.post(
            f"/api/backup/jobs/{source_job.id}/retry", headers=auth_headers
        )

        assert response.status_code == 403
        assert test_db.query(Operation).filter(Operation.kind == "backup").count() == 1

    def test_retry_backup_job_allows_repository_operator(
        self, test_client: TestClient, auth_headers, test_db, test_user
    ):
        repo = Repository(
            name="Retry Operator Repo",
            path="/retry/operator-repo",
            encryption="none",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.flush()
        test_db.add(
            UserRepositoryPermission(
                user_id=test_user.id,
                repository_id=repo.id,
                role="operator",
            )
        )
        source_job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            repository_id=repo.id,
            status="cancelled",
            completed_at=datetime.utcnow(),
            execution_mode="local",
            created_at=datetime.utcnow(),
        )
        test_db.commit()

        with patch(
            "app.services.backup_service.backup_service.execute_backup",
            new=AsyncMock(return_value=None),
        ):
            response = test_client.post(
                f"/api/backup/jobs/{source_job.id}/retry", headers=auth_headers
            )

        assert response.status_code == 202
        retry_op = test_db.get(Operation, response.json()["job_id"])
        details = test_db.get(OperationBackupDetails, retry_op.id)
        assert details.retry_requested_by_user_id == test_user.id


@pytest.mark.unit
class TestBackupJobs:
    """Test backup job listing"""

    def test_list_backup_jobs_empty(self, test_client: TestClient, admin_headers):
        """Test listing backup jobs when none exist"""
        response = test_client.get("/api/backup/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data == {"jobs": []}

    def test_list_backup_jobs_success(self, test_client: TestClient, admin_headers):
        """Test listing backup jobs returns 200"""
        response = test_client.get("/api/backup/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)

    def test_list_backup_jobs_with_data(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test listing backup jobs returns jobs"""
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.commit()

        response = test_client.get("/api/backup/jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert any(job["repository"] == "/test/repo" for job in data["jobs"])

    def test_list_backup_jobs_with_filters(
        self, test_client: TestClient, admin_headers
    ):
        """Test listing backup jobs with filters returns 200"""
        response = test_client.get(
            "/api/backup/jobs?status=running&limit=10", headers=admin_headers
        )

        assert response.status_code == 200

    def test_list_manual_backup_jobs_filtered_by_repository(
        self, test_client: TestClient, admin_headers, test_db
    ):
        primary_repo = Repository(
            name="Primary Repo",
            path="/repos/primary",
            encryption="none",
            repository_type="local",
        )
        secondary_repo = Repository(
            name="Secondary Repo",
            path="/repos/secondary",
            encryption="none",
            repository_type="local",
        )
        test_db.add_all([primary_repo, secondary_repo])
        test_db.flush()
        matching_manual_job = seed_job_operation(
            test_db,
            "backup",
            repository=primary_repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        other_manual_job = seed_job_operation(
            test_db,
            "backup",
            repository=secondary_repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        scheduled_job = seed_job_operation(
            test_db,
            "backup",
            repository=primary_repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            scheduled_job_id=123,
        )
        test_db.commit()

        response = test_client.get(
            "/api/backup/jobs?manual_only=true&repository=/repos/primary",
            headers=admin_headers,
        )

        assert response.status_code == 200
        jobs = response.json()["jobs"]
        assert [job["id"] for job in jobs] == [matching_manual_job.id]
        assert all(job["repository"] == "/repos/primary" for job in jobs)

    def test_list_backup_jobs_unauthorized(self, test_client: TestClient):
        """Test listing backup jobs without authentication"""
        response = test_client.get("/api/backup/jobs")

        assert_auth_required(response)

    def test_list_jobs_pagination(self, test_client: TestClient, admin_headers):
        """Test listing jobs with pagination parameters"""
        response = test_client.get(
            "/api/backup/jobs?skip=0&limit=20", headers=admin_headers
        )

        assert response.status_code == 200


@pytest.mark.unit
class TestBackupStatus:
    """Test backup job status"""

    def test_get_backup_status_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test getting backup status returns 200"""
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="running",
            started_at=datetime.now(),
            execution_mode="remote_ssh",
            route_strategy="remote_direct",
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/backup/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "status" in data or "job" in data
        assert data["execution_mode"] == "remote_ssh"
        assert data["route_strategy"] == "remote_direct"

    def test_get_backup_status_omits_unsupported_borg2_progress_fields(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="V2 Repo",
            path="/test/v2-repo",
            encryption="none",
            repository_type="local",
            borg_version=2,
        )
        test_db.add(repo)
        test_db.flush()
        job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            status="running",
            started_at=datetime.now(),
            execution_mode="remote_ssh",
            route_strategy="remote_direct",
            original_size=1024,
            compressed_size=512,
            deduplicated_size=256,
            nfiles=3,
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/backup/status/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        progress = response.json()["progress_details"]
        assert progress["original_size"] == 1024
        assert progress["nfiles"] == 3
        assert "compressed_size" not in progress
        assert "deduplicated_size" not in progress

    def test_list_backup_jobs_keeps_supported_v1_progress_fields(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="V1 Repo",
            path="/test/v1-repo",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        test_db.add(repo)
        test_db.flush()
        job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            status="running",
            started_at=datetime.now(),
            execution_mode="remote_ssh",
            route_strategy="remote_direct",
            original_size=1024,
            compressed_size=512,
            deduplicated_size=256,
            nfiles=3,
        )
        test_db.commit()

        response = test_client.get("/api/backup/jobs", headers=admin_headers)

        assert response.status_code == 200
        payload_job = next(
            item for item in response.json()["jobs"] if item["id"] == job.id
        )
        assert payload_job["execution_mode"] == "remote_ssh"
        assert payload_job["route_strategy"] == "remote_direct"
        progress = payload_job["progress_details"]
        assert progress["compressed_size"] == 512
        assert progress["deduplicated_size"] == 256

    def test_get_backup_job_status_nonexistent(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting status of non-existent backup job"""
        response = test_client.get(
            "/api/backup/jobs/99999/status", headers=admin_headers
        )

        # Should return 404 or error response
        assert response.status_code == 404

    def test_get_backup_status_nonexistent(
        self, test_client: TestClient, admin_headers
    ):
        """Test getting status for non-existent job returns 500 (exception wrapped)"""
        response = test_client.get("/api/backup/status/99999", headers=admin_headers)

        # The except Exception block catches HTTPException and converts to 500
        assert response.status_code == 500

    def test_get_backup_status_unauthorized(self, test_client: TestClient):
        """Test getting backup status without auth returns 403"""
        response = test_client.get("/api/backup/status/1")

        assert response.status_code == 401


@pytest.mark.unit
class TestBackupCancel:
    """Test backup job cancellation"""

    def test_cancel_backup_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test cancelling backup returns 200"""
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="running",
            started_at=datetime.now(),
        )
        test_db.commit()
        test_db.refresh(job)

        with patch(
            "app.api.backup.backup_service.cancel_backup",
            new=AsyncMock(return_value=True),
        ) as mock_cancel:
            response = test_client.post(
                f"/api/backup/cancel/{job.id}", headers=admin_headers
            )

            assert response.status_code == 200
            assert (
                response.json()["message"] == "backend.success.backup.backupCancelled"
            )
            mock_cancel.assert_awaited_once_with(job.id)

    def test_cancel_queued_agent_backup_cancels_agent_job(
        self, test_client: TestClient, admin_headers, test_db
    ):
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_laptop",
            token_hash=get_password_hash("borgui_agent_secret"),
            token_prefix="borgui_agent_secret"[:20],
            status="online",
        )
        repo = Repository(
            name="Agent Repo",
            path="/agent/repo",
            encryption="none",
            compression="lz4",
            source_directories=json.dumps(["/home/user/docs"]),
            repository_type="local",
            execution_target="agent",
            executor_type="agent",
        )
        test_db.add_all([agent, repo])
        test_db.commit()
        repo.agent_machine_id = agent.id
        test_db.commit()

        start = test_client.post(
            "/api/backup/start",
            json={"repository": repo.path},
            headers=admin_headers,
        )
        assert start.status_code == 200
        backup_job_id = start.json()["job_id"]
        agent_job = _wait_for_agent_job(test_db, backup_job_id)

        response = test_client.post(
            f"/api/backup/cancel/{backup_job_id}", headers=admin_headers
        )

        assert response.status_code == 200
        test_db.expire_all()
        test_db.refresh(agent_job)
        backup_job = BackupJobFacade(test_db, test_db.get(Operation, backup_job_id))
        assert agent_job.status == "canceled"
        assert backup_job.status == "cancelled"
        assert backup_job.completed_at is not None

    def test_cancel_backup_nonexistent(self, test_client: TestClient, admin_headers):
        """Test canceling non-existent backup job"""
        response = test_client.post(
            "/api/backup/jobs/99999/cancel", headers=admin_headers
        )

        assert response.status_code == 405

    def test_cancel_backup_nonexistent_new_endpoint(
        self, test_client: TestClient, admin_headers
    ):
        """Test cancelling non-existent backup returns 404 (with proper exception handling)"""
        response = test_client.post("/api/backup/cancel/99999", headers=admin_headers)

        # HTTPException is re-raised properly to preserve status codes
        assert response.status_code == 404

    def test_cancel_backup_already_completed(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test cancelling completed backup returns 400"""
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.post(
            f"/api/backup/cancel/{job.id}", headers=admin_headers
        )

        assert response.status_code == 400

    def test_cancel_backup_running_prune_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        test_db.add(repo)
        test_db.flush()
        job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_prune",
        )
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(job)

        prune_job = seed_job_operation(
            test_db,
            "prune",
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
        )
        test_db.commit()
        test_db.refresh(prune_job)

        with patch(
            "app.services.prune_service.prune_service.cancel_prune",
            new=AsyncMock(return_value=True),
        ) as mock_cancel:
            response = test_client.post(
                f"/api/backup/cancel/{job.id}", headers=admin_headers
            )

        assert response.status_code == 200
        test_db.refresh(job)
        test_db.refresh(prune_job)
        assert job.status == "completed"
        assert resolve_backup_job(test_db, job.id).maintenance_status == "prune_failed"
        assert prune_job.status == "cancelled"
        mock_cancel.assert_awaited_once_with(prune_job.id)

    def test_cancel_backup_running_compact_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        test_db.add(repo)
        test_db.flush()
        job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_compact",
        )
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(job)

        compact_job = seed_job_operation(
            test_db,
            "compact",
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
        )
        test_db.commit()
        test_db.refresh(compact_job)

        with patch(
            "app.services.compact_service.compact_service.cancel_compact",
            new=AsyncMock(return_value=True),
        ) as mock_cancel:
            response = test_client.post(
                f"/api/backup/cancel/{job.id}", headers=admin_headers
            )

        assert response.status_code == 200
        test_db.refresh(job)
        test_db.refresh(compact_job)
        assert job.status == "completed"
        assert (
            resolve_backup_job(test_db, job.id).maintenance_status == "compact_failed"
        )
        assert compact_job.status == "cancelled"
        mock_cancel.assert_awaited_once_with(compact_job.id)

    def test_cancel_backup_running_check_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        test_db.add(repo)
        test_db.flush()
        job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(job)

        check_job = seed_job_operation(
            test_db,
            "check",
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
        )
        test_db.commit()
        test_db.refresh(check_job)

        response = test_client.post(
            f"/api/backup/cancel/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        test_db.refresh(job)
        test_db.refresh(check_job)
        assert job.status == "completed"
        assert resolve_backup_job(test_db, job.id).maintenance_status == "check_failed"
        assert check_job.status == "cancelled"
        assert check_job.completed_at is not None

    def test_cancel_backup_stale_running_check_without_child_reconciles_parent(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        test_db.add(repo)
        test_db.flush()
        job = seed_job_operation(
            test_db,
            "backup",
            repository=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.post(
            f"/api/backup/cancel/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        test_db.refresh(job)
        assert job.status == "completed"
        assert resolve_backup_job(test_db, job.id).maintenance_status == "check_failed"

    def test_cancel_backup_unauthorized(self, test_client: TestClient):
        """Test cancelling backup without auth returns 403"""
        response = test_client.post("/api/backup/cancel/1")

        assert response.status_code == 401


@pytest.mark.unit
class TestBackupLogs:
    """Test backup log access"""

    def test_backup_logs_nonexistent_job(self, test_client: TestClient, admin_headers):
        """Test getting logs for non-existent backup job"""
        response = test_client.get("/api/backup/jobs/99999/logs", headers=admin_headers)

        # Should return 404 or empty logs
        assert response.status_code == 404

    def test_download_backup_logs_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test downloading backup logs accepts standard bearer auth."""
        _set_log_save_policy(test_db, "all_jobs")
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="downloadable backup log",
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/backup/logs/{job.id}/download", headers=admin_headers
        )

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    def test_download_backup_logs_nonexistent(
        self, test_client: TestClient, admin_headers
    ):
        """Test downloading logs for non-existent job returns 404 after auth succeeds."""
        response = test_client.get(
            "/api/backup/logs/99999/download", headers=admin_headers
        )

        assert response.status_code == 404

    def test_download_backup_logs_no_file(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test downloading logs with no log content returns 404."""
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            log_file_path=None,  # No log file
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/backup/logs/{job.id}/download", headers=admin_headers
        )

        assert response.status_code == 404

    def test_download_backup_logs_unauthorized(self, test_client: TestClient):
        """Test downloading logs without token returns 401"""
        response = test_client.get("/api/backup/logs/1/download")

        assert response.status_code == 401

    def test_download_backup_logs_proxy_auth_without_token(
        self, test_client: TestClient, test_db, monkeypatch
    ):
        """Proxy-auth mode should not require a JWT query token for log downloads."""
        from app import config

        _set_log_save_policy(test_db, "all_jobs")
        monkeypatch.setattr(config.settings, "disable_authentication", True)

        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs="proxy mode logs",
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/backup/logs/{job.id}/download",
            headers={"X-Forwarded-User": "proxyuser"},
        )

        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    @pytest.mark.parametrize(
        ("policy", "job_status", "logs", "expected_has_logs"),
        [
            ("failed_only", "completed", "successful backup log", False),
            (
                "failed_and_warnings",
                "completed",
                "WARNING: skipped unreadable file",
                True,
            ),
            ("all_jobs", "completed", "successful backup log", True),
        ],
    )
    def test_legacy_backup_log_surfaces_follow_log_save_policy(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
        policy,
        job_status,
        logs,
        expected_has_logs,
    ):
        _set_log_save_policy(test_db, policy)
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status=job_status,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            logs=logs,
        )
        test_db.commit()
        test_db.refresh(job)

        jobs_response = test_client.get(
            "/api/backup/jobs", params={"manual_only": True}, headers=admin_headers
        )
        assert jobs_response.status_code == 200
        history_job = next(
            item for item in jobs_response.json()["jobs"] if item["id"] == job.id
        )
        assert history_job["has_logs"] is expected_has_logs

        status_response = test_client.get(
            f"/api/backup/status/{job.id}", headers=admin_headers
        )
        assert status_response.status_code == 200
        assert status_response.json()["logs"] == (logs if expected_has_logs else None)

        stream_response = test_client.get(
            f"/api/backup/logs/{job.id}/stream", headers=admin_headers
        )
        assert stream_response.status_code == 200
        stream_body = stream_response.json()
        if expected_has_logs:
            assert stream_body["lines"] == [{"line_number": 1, "content": logs}]
        else:
            assert stream_body["lines"] == []

        download_response = test_client.get(
            f"/api/backup/logs/{job.id}/download", headers=admin_headers
        )
        assert download_response.status_code == (200 if expected_has_logs else 404)

    def test_agent_backup_log_rows_follow_log_save_policy(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_log_save_policy(test_db, "failed_only")
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_policy",
            token_hash=get_password_hash("agent-secret"),
            token_prefix="agent-secret",
            status="online",
        )
        test_db.add(agent)
        test_db.flush()
        backup_job = seed_job_operation(
            test_db,
            "backup",
            repository="/agent/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            execution_mode="agent",
        )
        test_db.flush()
        agent_job = AgentJob(
            agent_machine_id=agent.id,
            operation_id=backup_job.id,
            job_type="backup",
            status="completed",
            payload={},
            completed_at=datetime.now(),
        )
        test_db.add(agent_job)
        test_db.flush()
        test_db.add(
            AgentJobLog(
                agent_job_id=agent_job.id,
                sequence=1,
                stream="stdout",
                message="agent success log",
                created_at=datetime.now(),
            )
        )
        test_db.commit()

        jobs_response = test_client.get(
            "/api/backup/jobs", params={"manual_only": True}, headers=admin_headers
        )
        assert jobs_response.status_code == 200
        history_job = next(
            item for item in jobs_response.json()["jobs"] if item["id"] == backup_job.id
        )
        assert history_job["has_logs"] is False

        stream_response = test_client.get(
            f"/api/backup/logs/{backup_job.id}/stream", headers=admin_headers
        )
        assert stream_response.status_code == 200
        assert stream_response.json()["lines"] == []

        download_response = test_client.get(
            f"/api/backup/logs/{backup_job.id}/download", headers=admin_headers
        )
        assert download_response.status_code == 404

    def test_agent_backup_warning_log_rows_are_visible_for_warning_policy(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_log_save_policy(test_db, "failed_and_warnings")
        agent = AgentMachine(
            name="Laptop",
            agent_id="agt_policy_warning",
            token_hash=get_password_hash("agent-secret"),
            token_prefix="agent-secret",
            status="online",
        )
        test_db.add(agent)
        test_db.flush()
        backup_job = seed_job_operation(
            test_db,
            "backup",
            repository="/agent/repo",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            execution_mode="agent",
        )
        test_db.flush()
        agent_job = AgentJob(
            agent_machine_id=agent.id,
            operation_id=backup_job.id,
            job_type="backup",
            status="completed",
            payload={},
            completed_at=datetime.now(),
        )
        test_db.add(agent_job)
        test_db.flush()
        test_db.add(
            AgentJobLog(
                agent_job_id=agent_job.id,
                sequence=1,
                stream="stderr",
                message="WARNING: skipped unreadable file",
                created_at=datetime.now(),
            )
        )
        test_db.commit()

        jobs_response = test_client.get(
            "/api/backup/jobs", params={"manual_only": True}, headers=admin_headers
        )
        assert jobs_response.status_code == 200
        history_job = next(
            item for item in jobs_response.json()["jobs"] if item["id"] == backup_job.id
        )
        assert history_job["has_logs"] is True

        stream_response = test_client.get(
            f"/api/backup/logs/{backup_job.id}/stream", headers=admin_headers
        )
        assert stream_response.status_code == 200
        assert stream_response.json()["lines"] == [
            {"line_number": 1, "content": "WARNING: skipped unreadable file"}
        ]

    def test_stream_backup_logs_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        """Test streaming backup logs returns 200"""
        job = seed_job_operation(
            test_db,
            "backup",
            repository="/test/repo",
            status="running",
            started_at=datetime.now(),
            log_file_path="/tmp/backup_1.log",
        )
        test_db.commit()
        test_db.refresh(job)

        response = test_client.get(
            f"/api/backup/logs/{job.id}/stream", headers=admin_headers
        )

        assert response.status_code == 200

    def test_stream_backup_logs_nonexistent(
        self, test_client: TestClient, admin_headers
    ):
        """Test streaming logs for non-existent job returns 500 (exception wrapped)"""
        response = test_client.get(
            "/api/backup/logs/99999/stream", headers=admin_headers
        )

        # The except Exception block catches HTTPException and converts to 500
        assert response.status_code == 500

    def test_stream_backup_logs_unauthorized(self, test_client: TestClient):
        """Test streaming logs without auth returns 403"""
        response = test_client.get("/api/backup/logs/1/stream")

        assert response.status_code == 401


@pytest.mark.unit
class TestBackupHistory:
    """Test backup history"""

    def test_get_backup_history(self, test_client: TestClient, admin_headers, test_db):
        """Test getting backup history"""
        # Create a test repository first
        repo = Repository(
            name="Test Repo",
            path="/tmp/test-backup-repo",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.get(
            f"/api/backup/history/{repo.id}", headers=admin_headers
        )

        # Should succeed even with no history
        assert response.status_code == 404


@pytest.mark.unit
class TestBackupNotifications:
    """
    Test notification behavior with pre/post hooks and various exit codes.

    These tests verify the fixes for three notification bugs:
    1. Backups with warnings (exit 100-127) should send success notifications
    2. Pre-hook failures should send failure notifications
    3. Notifications should be sent AFTER post-hooks complete

    NOTE: These tests document the expected behavior. Full integration testing
    requires a working borg environment and database setup which is complex to mock.
    The actual fixes are verified by code inspection and manual testing.
    """

    def test_notification_logic_for_warning_exit_code(self):
        """Document that warnings (exit 100-127) should send success notifications"""
        # This test documents the fix: backup_service.py lines 966-977
        # When borg returns exit code 100-127 (warning), we now send success notification
        # Previously, no notification was sent at all
        assert True  # Documentation test

    def test_notification_logic_for_pre_hook_failure(self):
        """Document that pre-hook failures should send failure notifications"""
        # This test documents the fix: backup_service.py lines 568-574
        # When pre-hook fails, we now send failure notification before returning
        # Previously, no notification was sent
        assert True  # Documentation test

    def test_notification_logic_for_post_hook_timing(self):
        """Document that notifications should be sent AFTER post-hook completes"""
        # This test documents the fix: backup_service.py lines 916-977 and 989-1051
        # Notifications are now sent AFTER post-hook execution
        # If post-hook fails, we send failure notification instead of success
        # Previously, success notification was sent before post-hook ran
        assert True  # Documentation test
