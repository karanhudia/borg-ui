import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.agent_auth import AGENT_AUTH_HEADER, AGENT_TOKEN_PREFIX_LENGTH
from app.core.security import get_password_hash
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentJobLog,
    AgentMachine,
    BackupPlan,
    LicensingState,
    Operation,
    Repository,
)
from app.services.operations.executors import load_default_executors
from app.services.operations.backup_facade import resolve_backup_job
from app.database.models import BackupPlanRun
from tests.utils.operations import seed_job_operation


def _set_plan(test_db, plan: str) -> None:
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-agents")
        test_db.add(state)
    state.plan = plan
    state.status = "active"
    test_db.commit()


@pytest.fixture(autouse=True)
def _enable_paid_managed_agent_features(test_db):
    _set_plan(test_db, "pro")


def _create_enrollment_token(test_client: TestClient, admin_headers, name="agent"):
    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        json={"name": name, "expires_in_minutes": 60},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()


def _register_agent(
    test_client: TestClient,
    enrollment_token: str,
    name="laptop",
    capabilities: list[str] | None = None,
):
    response = test_client.post(
        "/api/agents/register",
        json={
            "enrollment_token": enrollment_token,
            "name": name,
            "hostname": "laptop.local",
            "os": "linux",
            "arch": "amd64",
            "agent_version": "0.1.1",
            "borg_versions": [
                {"major": 1, "version": "1.2.8", "path": "/usr/bin/borg"}
            ],
            "capabilities": capabilities or ["backup.create", "logs.stream"],
        },
    )
    assert response.status_code == 200
    return response.json()


def _agent_headers(agent_token: str) -> dict[str, str]:
    return {AGENT_AUTH_HEADER: f"Bearer {agent_token}"}


def _get_agent(test_db, agent_id: str) -> AgentMachine:
    agent = (
        test_db.query(AgentMachine).filter(AgentMachine.agent_id == agent_id).first()
    )
    assert agent is not None
    return agent


def _create_agent_job(test_db, agent: AgentMachine, status: str = "queued") -> AgentJob:
    now = datetime.now(timezone.utc)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status=status,
        payload={
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {"id": 7},
        },
        created_at=now,
        updated_at=now,
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)
    return job


@pytest.mark.unit
class TestAgentEnrollmentTokens:
    def test_create_enrollment_token_returns_full_token_once(
        self, test_client: TestClient, admin_headers
    ):
        data = _create_enrollment_token(test_client, admin_headers, "macbook setup")

        assert data["name"] == "macbook setup"
        assert data["token"].startswith("borgui_enroll_")
        assert data["token_prefix"] == data["token"][:AGENT_TOKEN_PREFIX_LENGTH]
        assert data["expires_at"].endswith("+00:00")
        assert data["created_at"].endswith("+00:00")

    def test_list_enrollment_tokens_hides_full_token(
        self, test_client: TestClient, admin_headers
    ):
        _create_enrollment_token(test_client, admin_headers)

        response = test_client.get(
            "/api/managed-machines/enrollment-tokens", headers=admin_headers
        )

        assert response.status_code == 200
        tokens = response.json()
        assert len(tokens) == 1
        assert "token" not in tokens[0]
        assert tokens[0]["token_prefix"].startswith("borgui_enroll_")

    def test_create_enrollment_token_requires_admin(
        self, test_client: TestClient, auth_headers
    ):
        response = test_client.post(
            "/api/managed-machines/enrollment-tokens",
            json={"name": "viewer token"},
            headers=auth_headers,
        )

        assert response.status_code == 403

    def test_revoke_enrollment_token_blocks_registration(
        self, test_client: TestClient, admin_headers
    ):
        enrollment = _create_enrollment_token(test_client, admin_headers)

        revoke = test_client.post(
            f"/api/managed-machines/enrollment-tokens/{enrollment['id']}/revoke",
            headers=admin_headers,
        )
        assert revoke.status_code == 204

        response = test_client.post(
            "/api/agents/register",
            json={"enrollment_token": enrollment["token"], "name": "laptop"},
        )
        assert response.status_code == 401


@pytest.mark.unit
class TestAgentRegistrationAndHeartbeat:
    def test_register_agent_copies_enrollment_default_path_to_machine(
        self, test_client: TestClient, test_db, admin_headers
    ):
        enrollment = test_client.post(
            "/api/managed-machines/enrollment-tokens",
            json={
                "name": "odroid setup",
                "expires_in_minutes": 60,
                "default_path": " /home/karanhudia ",
            },
            headers=admin_headers,
        )
        assert enrollment.status_code == 201
        assert enrollment.json()["default_path"] == "/home/karanhudia"

        registered = _register_agent(test_client, enrollment.json()["token"])
        agent = _get_agent(test_db, registered["agent_id"])
        assert agent.default_path == "/home/karanhudia"

        response = test_client.get(
            "/api/managed-machines/agents", headers=admin_headers
        )
        assert response.status_code == 200
        assert response.json()[0]["default_path"] == "/home/karanhudia"

    def test_register_agent_consumes_enrollment_token_and_lists_machine(
        self, test_client: TestClient, test_db, admin_headers
    ):
        enrollment = _create_enrollment_token(test_client, admin_headers)

        registered = _register_agent(test_client, enrollment["token"])

        assert registered["agent_id"].startswith("agt_")
        assert registered["agent_token"].startswith("borgui_agent_")
        assert registered["poll_interval_seconds"] == 15
        assert registered["server_time"].endswith("+00:00")

        token_row = (
            test_db.query(AgentEnrollmentToken)
            .filter(AgentEnrollmentToken.id == enrollment["id"])
            .first()
        )
        assert token_row.used_at is not None

        response = test_client.get(
            "/api/managed-machines/agents", headers=admin_headers
        )
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["agent_id"] == registered["agent_id"]
        assert agents[0]["hostname"] == "laptop.local"
        assert agents[0]["status"] == "online"
        assert agents[0]["capabilities"] == ["backup.create", "logs.stream"]

    def test_enrollment_token_is_one_time_use(
        self, test_client: TestClient, admin_headers
    ):
        enrollment = _create_enrollment_token(test_client, admin_headers)
        _register_agent(test_client, enrollment["token"], name="first")

        response = test_client.post(
            "/api/agents/register",
            json={"enrollment_token": enrollment["token"], "name": "second"},
        )

        assert response.status_code == 401

    def test_expired_enrollment_token_is_rejected(
        self, test_client: TestClient, test_db
    ):
        raw_token = "borgui_enroll_expired-token"
        now = datetime.now(timezone.utc)
        token = AgentEnrollmentToken(
            name="expired",
            token_hash=get_password_hash(raw_token),
            token_prefix=raw_token[:AGENT_TOKEN_PREFIX_LENGTH],
            expires_at=now - timedelta(minutes=1),
            created_at=now - timedelta(minutes=2),
        )
        test_db.add(token)
        test_db.commit()

        response = test_client.post(
            "/api/agents/register",
            json={"enrollment_token": raw_token, "name": "expired-agent"},
        )

        assert response.status_code == 401

    def test_never_expiring_enrollment_token_registers_agent(
        self, test_client: TestClient, admin_headers
    ):
        enrollment = test_client.post(
            "/api/managed-machines/enrollment-tokens",
            json={"name": "permanent enrollment", "expires_never": True},
            headers=admin_headers,
        )
        assert enrollment.status_code == 201

        registered = _register_agent(test_client, enrollment.json()["token"])

        assert registered["agent_id"].startswith("agt_")

    def test_heartbeat_updates_agent_status(
        self, test_client: TestClient, test_db, admin_headers
    ):
        enrollment = _create_enrollment_token(test_client, admin_headers)
        registered = _register_agent(test_client, enrollment["token"])

        response = test_client.post(
            "/api/agents/heartbeat",
            json={
                "agent_id": registered["agent_id"],
                "hostname": "renamed.local",
                "agent_version": "0.1.1",
                "borg_versions": [
                    {"major": 2, "version": "2.0.0b10", "path": "/usr/local/bin/borg2"}
                ],
                "capabilities": ["backup.create", "backup.cancel"],
                "running_job_ids": [],
            },
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["poll_interval_seconds"] == 15
        assert data["cancel_job_ids"] == []

        agent = (
            test_db.query(AgentMachine)
            .filter(AgentMachine.agent_id == registered["agent_id"])
            .first()
        )
        assert agent.hostname == "renamed.local"
        assert agent.agent_version == "0.1.1"
        assert agent.status == "online"
        assert agent.last_seen_at is not None
        assert agent.capabilities == ["backup.create", "backup.cancel"]

    def test_heartbeat_requires_agent_token(self, test_client: TestClient):
        response = test_client.post(
            "/api/agents/heartbeat",
            json={"agent_id": "agt_missing"},
        )

        assert response.status_code == 401

    def test_heartbeat_rejects_agent_id_mismatch(
        self, test_client: TestClient, admin_headers
    ):
        enrollment = _create_enrollment_token(test_client, admin_headers)
        registered = _register_agent(test_client, enrollment["token"])

        response = test_client.post(
            "/api/agents/heartbeat",
            json={"agent_id": "agt_different"},
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 403

    def test_revoked_agent_cannot_heartbeat(
        self, test_client: TestClient, test_db, admin_headers
    ):
        enrollment = _create_enrollment_token(test_client, admin_headers)
        registered = _register_agent(test_client, enrollment["token"])
        agent = (
            test_db.query(AgentMachine)
            .filter(AgentMachine.agent_id == registered["agent_id"])
            .first()
        )

        revoke = test_client.post(
            f"/api/managed-machines/agents/{agent.id}/revoke",
            headers=admin_headers,
        )
        assert revoke.status_code == 204

        response = test_client.post(
            "/api/agents/heartbeat",
            json={"agent_id": registered["agent_id"]},
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 403

    def test_unregister_revokes_agent_token(
        self, test_client: TestClient, test_db, admin_headers
    ):
        enrollment = _create_enrollment_token(test_client, admin_headers)
        registered = _register_agent(test_client, enrollment["token"])

        response = test_client.post(
            "/api/agents/unregister",
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 204
        agent = _get_agent(test_db, registered["agent_id"])
        test_db.refresh(agent)
        assert agent.status == "revoked"

        heartbeat = test_client.post(
            "/api/agents/heartbeat",
            json={"agent_id": registered["agent_id"]},
            headers=_agent_headers(registered["agent_token"]),
        )
        assert heartbeat.status_code == 403


@pytest.mark.unit
class TestAgentJobTransport:
    def test_websocket_session_times_out_missing_hello(
        self, test_client: TestClient, admin_headers, monkeypatch
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
            capabilities=["session.commands"],
        )
        monkeypatch.setattr(
            "app.api.agents.AGENT_SESSION_HELLO_TIMEOUT_SECONDS",
            0.01,
        )

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with test_client.websocket_connect(
                "/api/agents/session",
                headers=_agent_headers(registered["agent_token"]),
            ) as websocket:
                websocket.receive_json()

        assert exc_info.value.code == 1008

    def test_websocket_session_hello_marks_agent_online_until_disconnect(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
            capabilities=["session.commands", "filesystem.browse"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        agent.status = "offline"
        test_db.commit()

        with test_client.websocket_connect(
            "/api/agents/session",
            headers=_agent_headers(registered["agent_token"]),
        ) as websocket:
            websocket.send_json(
                {
                    "type": "hello",
                    "agent_id": registered["agent_id"],
                    "hostname": "session-host.local",
                    "agent_version": "0.2.0",
                    "borg_versions": [
                        {
                            "major": 2,
                            "version": "2.0.0b10",
                            "path": "/usr/local/bin/borg2",
                        }
                    ],
                    "capabilities": ["session.commands", "filesystem.browse"],
                    "running_job_ids": [],
                }
            )

            assert websocket.receive_json()["type"] == "hello_ack"
            test_db.refresh(agent)
            assert agent.status == "online"
            assert agent.hostname == "session-host.local"
            assert agent.agent_version == "0.2.0"
            assert "filesystem.browse" in agent.capabilities

        test_db.refresh(agent)
        assert agent.status == "offline"

    def test_websocket_session_dispatches_durable_job_without_polling(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
            capabilities=["session.commands", "backup.create", "logs.stream"],
        )
        agent = _get_agent(test_db, registered["agent_id"])

        with test_client.websocket_connect(
            "/api/agents/session",
            headers=_agent_headers(registered["agent_token"]),
        ) as websocket:
            websocket.send_json(
                {
                    "type": "hello",
                    "agent_id": registered["agent_id"],
                    "hostname": "session-host.local",
                    "agent_version": "0.2.0",
                    "borg_versions": [],
                    "capabilities": [
                        "session.commands",
                        "backup.create",
                        "logs.stream",
                    ],
                    "running_job_ids": [],
                }
            )
            assert websocket.receive_json()["type"] == "hello_ack"

            queued = test_client.post(
                f"/api/managed-machines/agents/{agent.id}/backup-jobs",
                json={
                    "repository_path": "/backups/laptop",
                    "archive_name": "laptop-now",
                    "source_paths": ["/home/user/docs"],
                },
                headers=admin_headers,
            )

            assert queued.status_code == 201
            command = websocket.receive_json()
            assert command["type"] == "command"
            assert command["command"] == "backup.create"
            assert command["job_id"] == queued.json()["id"]
            assert command["payload"]["job_kind"] == "backup.create"
            websocket.send_json(
                {
                    "type": "log",
                    "command_id": command["command_id"],
                    "job_id": queued.json()["id"],
                    "sequence": "not-a-number",
                    "stream": "stderr",
                    "message": "still handled",
                }
            )

            polled = test_client.get(
                "/api/agents/jobs/poll",
                headers=_agent_headers(registered["agent_token"]),
            )
            assert polled.status_code == 200
            assert polled.json()["jobs"] == []

        log = (
            test_db.query(AgentJobLog)
            .filter(AgentJobLog.agent_job_id == queued.json()["id"])
            .one()
        )
        assert log.sequence == 0
        assert log.message == "still handled"

    def test_admin_can_queue_backup_job_and_agent_can_poll_it(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])

        queued = test_client.post(
            f"/api/managed-machines/agents/{agent.id}/backup-jobs",
            json={
                "repository_path": "/backups/laptop",
                "archive_name": "laptop-now",
                "source_paths": ["/home/user/docs"],
                "borg_version": 1,
                "compression": "zstd",
                "exclude_patterns": ["*.tmp"],
                "custom_flags": ["--one-file-system"],
                "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
            },
            headers=admin_headers,
        )

        assert queued.status_code == 201
        queued_job = queued.json()
        assert queued_job["agent_machine_id"] == agent.id
        assert queued_job["job_type"] == "backup"
        assert queued_job["status"] == "queued"
        assert queued_job["payload"] == {
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {
                "path": "/backups/laptop",
                "borg_version": 1,
            },
            "backup": {
                "archive_name": "laptop-now",
                "source_paths": ["/home/user/docs"],
                "compression": "zstd",
                "exclude_patterns": ["*.tmp"],
                "custom_flags": ["--one-file-system"],
            },
            "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
        }

        polled = test_client.get(
            "/api/agents/jobs/poll",
            headers=_agent_headers(registered["agent_token"]),
        )

        assert polled.status_code == 200
        jobs = polled.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["id"] == queued_job["id"]
        assert jobs[0]["payload"]["job_kind"] == "backup.create"

    def test_admin_cannot_queue_backup_job_for_revoked_agent(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        agent.status = "revoked"
        test_db.commit()

        response = test_client.post(
            f"/api/managed-machines/agents/{agent.id}/backup-jobs",
            json={
                "repository_path": "/backups/laptop",
                "archive_name": "laptop-now",
                "source_paths": ["/home/user/docs"],
            },
            headers=admin_headers,
        )

        assert response.status_code == 409

    def test_deleted_agent_cannot_poll_jobs(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        _create_agent_job(test_db, agent)

        delete = test_client.delete(
            f"/api/managed-machines/agents/{agent.id}",
            headers=admin_headers,
        )
        assert delete.status_code == 204

        response = test_client.get(
            "/api/agents/jobs/poll",
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 403

    def test_poll_only_returns_queued_jobs_for_authenticated_agent(
        self, test_client: TestClient, test_db, admin_headers
    ):
        first = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers, "first")["token"],
            name="first",
        )
        second = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers, "second")["token"],
            name="second",
        )
        first_agent = _get_agent(test_db, first["agent_id"])
        second_agent = _get_agent(test_db, second["agent_id"])
        first_job = _create_agent_job(test_db, first_agent)
        _create_agent_job(test_db, second_agent)
        _create_agent_job(test_db, first_agent, status="running")

        response = test_client.get(
            "/api/agents/jobs/poll",
            headers=_agent_headers(first["agent_token"]),
        )

        assert response.status_code == 200
        jobs = response.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["id"] == first_job.id
        assert jobs[0]["type"] == "backup"
        assert jobs[0]["payload"]["job_kind"] == "backup.create"

    def test_claim_start_progress_log_and_complete_job(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent)
        headers = _agent_headers(registered["agent_token"])

        claim = test_client.post(f"/api/agents/jobs/{job.id}/claim", headers=headers)
        assert claim.status_code == 200
        assert claim.json()["status"] == "claimed"

        repeated_claim = test_client.post(
            f"/api/agents/jobs/{job.id}/claim", headers=headers
        )
        assert repeated_claim.status_code == 200
        assert repeated_claim.json()["status"] == "claimed"

        start = test_client.post(
            f"/api/agents/jobs/{job.id}/start",
            json={},
            headers=headers,
        )
        assert start.status_code == 200
        assert start.json()["status"] == "running"

        progress = test_client.post(
            f"/api/agents/jobs/{job.id}/progress",
            json={
                "progress_percent": 42.5,
                "current_file": "/home/user/report.pdf",
                "original_size": 1024,
                "compressed_size": 512,
                "deduplicated_size": 128,
                "nfiles": 3,
                "backup_speed": 12.5,
                "total_expected_size": 4096,
                "estimated_time_remaining": 9,
            },
            headers=headers,
        )
        assert progress.status_code == 200

        log = test_client.post(
            f"/api/agents/jobs/{job.id}/logs",
            json={
                "sequence": 1,
                "stream": "stderr",
                "message": "Creating archive",
            },
            headers=headers,
        )
        assert log.status_code == 200
        assert log.json() == {"accepted": True, "duplicate": False}

        duplicate_log = test_client.post(
            f"/api/agents/jobs/{job.id}/logs",
            json={
                "sequence": 1,
                "stream": "stderr",
                "message": "Creating archive",
            },
            headers=headers,
        )
        assert duplicate_log.status_code == 200
        assert duplicate_log.json() == {"accepted": True, "duplicate": True}

        listed_logs = test_client.get(
            f"/api/managed-machines/agent-jobs/{job.id}/logs",
            headers=admin_headers,
        )
        assert listed_logs.status_code == 200
        logs = listed_logs.json()
        assert len(logs) == 1
        assert logs[0]["sequence"] == 1
        assert logs[0]["stream"] == "stderr"
        assert logs[0]["message"] == "Creating archive"

        complete = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={
                "result": {
                    "archive_name": "agent-archive",
                    "return_code": 0,
                }
            },
            headers=headers,
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed"

        test_db.refresh(job)
        assert job.status == "completed"
        assert job.progress_percent == 42.5
        assert job.current_file == "/home/user/report.pdf"
        assert job.result["archive_name"] == "agent-archive"
        assert (
            test_db.query(AgentJobLog)
            .filter(AgentJobLog.agent_job_id == job.id)
            .count()
            == 1
        )

        after_complete = test_client.post(
            f"/api/agents/jobs/{job.id}/progress",
            json={"progress_percent": 99},
            headers=headers,
        )
        assert after_complete.status_code == 409

    def test_warning_return_code_completes_with_warnings(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """Borg warning exit codes (legacy 1, modern 100-127) are not failures:
        the job and its linked backup job end completed_with_warnings, the
        archive name is still captured, and the warning is surfaced as the
        same i18n message server-side backups use."""
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")
        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="running"
        )
        test_db.commit()
        job.operation_id = backup_job.id
        test_db.commit()
        headers = _agent_headers(registered["agent_token"])

        complete = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={
                "result": {
                    "archive_name": "warned-archive",
                    "return_code": 1,
                }
            },
            headers=headers,
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed_with_warnings"

        test_db.refresh(job)
        test_db.refresh(backup_job)
        backup_job = resolve_backup_job(test_db, backup_job.id)
        assert job.status == "completed_with_warnings"
        assert "jobCompletedWithWarning" in (job.error_message or "")
        assert backup_job.status == "completed_with_warnings"
        assert backup_job.archive_name == "warned-archive"
        assert backup_job.progress == 100
        assert "backupCompletedWithWarning" in (backup_job.error_message or "")

        # A repeated report must stay idempotent for the new terminal status.
        repeated = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"return_code": 1}},
            headers=headers,
        )
        assert repeated.status_code == 200

    def test_completed_backup_job_enqueues_index_followups(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """A completed agent backup no longer writes last_backup itself; it
        enqueues the backup follow-up chain, and archive_sync derives the
        column from the listing (#933)."""
        load_default_executors()
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        repo = Repository(name="linked", path="/repo", encryption="none")
        test_db.add(repo)
        test_db.commit()
        job = _create_agent_job(test_db, agent, status="running")
        backup_job = seed_job_operation(
            test_db,
            "backup",
            repository="/repo",
            repository_id=repo.id,
            status="running",
        )
        test_db.commit()
        job.operation_id = backup_job.id
        test_db.commit()

        complete = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"archive_name": "a1", "return_code": 0}},
            headers=_agent_headers(registered["agent_token"]),
        )
        assert complete.status_code == 200

        test_db.refresh(repo)
        assert repo.last_backup is None
        ops = (
            test_db.query(Operation)
            .filter(Operation.repository_id == repo.id)
            .order_by(Operation.id)
            .all()
        )
        followups = [o for o in ops if o.id != backup_job.id]
        assert [o.kind for o in followups][:1] == ["archive_sync"]
        assert {o.trigger for o in followups} == {"followup"}

    def test_agent_job_links_a_backup_operation_and_cancels_it(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """An AgentJob transporting a backup operation is found through
        `operation_id`, and cancelling it while it is still queued writes
        `cancelled` on the operation."""
        from app.database.models import Operation
        from app.services.operations.backup_facade import BackupJobFacade
        from app.services.repository_executor import (
            cancel_agent_backup_job,
            get_agent_job_for_backup,
        )

        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        repo = Repository(name="linked", path="/repo", encryption="none")
        test_db.add(repo)
        test_db.commit()
        operation = Operation(
            repository_id=repo.id,
            kind="backup",
            category="backup",
            status="running",
            trigger="manual",
            priority=0,
            run_id="run-1",
            params={"executor": "agent"},
        )
        test_db.add(operation)
        test_db.commit()
        agent_job = _create_agent_job(test_db, agent, status="queued")
        agent_job.operation_id = operation.id
        test_db.commit()

        facade = BackupJobFacade(test_db, operation)
        assert get_agent_job_for_backup(test_db, facade).id == agent_job.id

        cancelled_job, _ = cancel_agent_backup_job(test_db, facade)
        test_db.commit()
        test_db.refresh(agent_job)
        test_db.refresh(operation)
        assert cancelled_job.id == agent_job.id
        assert agent_job.status == "canceled"
        assert operation.status == "cancelled"

    def test_failed_followup_enqueue_never_fails_the_backup(
        self, test_client: TestClient, test_db, admin_headers, monkeypatch
    ):
        """A flush failure inside the follow-up enqueue (here a colliding
        Operation id, the shape enqueue() produces) is undone in its own
        savepoint: the completion still succeeds and the terminal state of
        the agent job and the backup job is committed, with no chain rows."""
        from sqlalchemy.exc import IntegrityError

        load_default_executors()
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        repo = Repository(name="linked", path="/repo", encryption="none")
        test_db.add(repo)
        test_db.commit()
        from app.services.operations.enqueue import enqueue

        existing = enqueue(test_db, "stats", repository_id=repo.id)
        job = _create_agent_job(test_db, agent, status="running")
        backup_job = seed_job_operation(
            test_db,
            "backup",
            repository="/repo",
            repository_id=repo.id,
            status="running",
        )
        test_db.commit()
        job.operation_id = backup_job.id
        test_db.commit()
        seen = {}

        def colliding_enqueue(db, repository_id, **kwargs):
            db.add(
                Operation(
                    id=existing.id,
                    run_id=existing.run_id,
                    kind="archive_sync",
                    category="index",
                    status="queued",
                    trigger="followup",
                    repository_id=repository_id,
                )
            )
            try:
                db.flush()
            except IntegrityError as exc:
                seen["error"] = exc
                raise
            raise AssertionError("the colliding flush did not fail")

        monkeypatch.setattr(
            "app.api.agents.enqueue_backup_followups", colliding_enqueue
        )
        complete = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"archive_name": "a1", "return_code": 0}},
            headers=_agent_headers(registered["agent_token"]),
        )
        assert complete.status_code == 200, complete.text
        assert "error" in seen
        test_db.expire_all()
        assert test_db.get(AgentJob, job.id).status == "completed"
        assert resolve_backup_job(test_db, backup_job.id).status == "completed"
        assert resolve_backup_job(test_db, backup_job.id).archive_name == "a1"
        # The backup itself plus the one index row the colliding enqueue left.
        assert (
            test_db.query(Operation).filter(Operation.repository_id == repo.id).count()
            == 2
        )

    def test_modern_warning_range_counts_as_warning(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")
        headers = _agent_headers(registered["agent_token"])

        complete = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"return_code": 104}},
            headers=headers,
        )
        assert complete.status_code == 200
        test_db.refresh(job)
        assert job.status == "completed_with_warnings"

    def test_error_return_code_in_completion_report_fails_the_job(
        self, test_client: TestClient, test_db, admin_headers
    ):
        """A completion report carrying an explicit borg error code (2-99) is
        a failure - the server classifies, not the transport."""
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")
        headers = _agent_headers(registered["agent_token"])

        complete = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"return_code": 2}},
            headers=headers,
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "failed"

        test_db.refresh(job)
        assert job.status == "failed"
        assert "exited with code 2" in (job.error_message or "")

    @pytest.mark.parametrize("malformed", ["2", 2.0, True, [1]])
    def test_malformed_return_code_in_completion_report_fails_closed(
        self, test_client: TestClient, test_db, admin_headers, malformed
    ):
        """A completion report is only trusted with an int return code;
        anything else fails the job (and its linked backup job) instead of
        slipping past the classification as a success."""
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")
        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="running"
        )
        test_db.commit()
        job.operation_id = backup_job.id
        test_db.commit()
        headers = _agent_headers(registered["agent_token"])

        complete = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"return_code": malformed}},
            headers=headers,
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "failed"

        test_db.refresh(job)
        test_db.refresh(backup_job)
        backup_job = resolve_backup_job(test_db, backup_job.id)
        assert job.status == "failed"
        assert "malformed return code" in (job.error_message or "")
        assert backup_job.status == "failed"

    def test_repeated_complete_report_is_idempotent(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")
        headers = _agent_headers(registered["agent_token"])

        first = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"archive_name": "first-archive", "return_code": 0}},
            headers=headers,
        )
        second = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"archive_name": "retry-archive", "return_code": 0}},
            headers=headers,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["status"] == "completed"
        test_db.refresh(job)
        assert job.result == {"archive_name": "first-archive", "return_code": 0}

    def test_heartbeat_requeues_stale_claimed_job_not_running_on_agent(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        job = _create_agent_job(test_db, agent, status="claimed")
        job.claimed_at = stale_at
        job.updated_at = stale_at
        test_db.commit()

        response = test_client.post(
            "/api/agents/heartbeat",
            json={
                "agent_id": registered["agent_id"],
                "agent_version": "0.1.1",
                "borg_versions": [],
                "capabilities": ["backup.create"],
                "running_job_ids": [],
            },
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 200
        test_db.refresh(job)
        assert job.status == "queued"
        assert job.claimed_at is None

    def _create_repository_job(
        self, test_db, agent, *, job_kind, operation, stale_at
    ) -> AgentJob:
        job = AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status="running",
            payload={
                "schema_version": 1,
                "job_kind": job_kind,
                "repository": {"id": 7},
                "operation": operation,
            },
            created_at=stale_at,
            started_at=stale_at,
            updated_at=stale_at,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        return job

    def test_heartbeat_fails_stale_request_scoped_repository_job(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        job = self._create_repository_job(
            test_db,
            agent,
            job_kind="repository.extract_archive_file",
            operation={"archive": "a", "file_path": "f"},
            stale_at=stale_at,
        )

        response = test_client.post(
            "/api/agents/heartbeat",
            json={
                "agent_id": registered["agent_id"],
                "agent_version": "0.1.1",
                "borg_versions": [],
                "capabilities": ["backup.create"],
                "running_job_ids": [],
            },
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 200
        test_db.refresh(job)
        # No receiver for the timed-out download request -> fail, don't restart.
        assert job.status == "failed"
        assert "no client is waiting" in (job.error_message or "")

    def test_heartbeat_requeues_stale_durable_repository_job(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        job = self._create_repository_job(
            test_db,
            agent,
            job_kind="repository.check",
            operation={"maintenance_job": {"kind": "check", "id": 1}},
            stale_at=stale_at,
        )

        response = test_client.post(
            "/api/agents/heartbeat",
            json={
                "agent_id": registered["agent_id"],
                "agent_version": "0.1.1",
                "borg_versions": [],
                "capabilities": ["backup.create"],
                "running_job_ids": [],
            },
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 200
        test_db.refresh(job)
        # Durable maintenance op keeps its retry-on-reconnect behaviour.
        assert job.status == "queued"

    def test_heartbeat_requeues_stale_rclone_sync_job(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        # rclone_sync owns a durable RcloneSyncJob record and also runs after
        # backups, so it must be retried on reconnect, not failed.
        job = self._create_repository_job(
            test_db,
            agent,
            job_kind="repository.rclone_sync",
            operation={"rclone": {"remote_name": "r", "remote_path": "p"}},
            stale_at=stale_at,
        )

        response = test_client.post(
            "/api/agents/heartbeat",
            json={
                "agent_id": registered["agent_id"],
                "agent_version": "0.1.1",
                "borg_versions": [],
                "capabilities": ["backup.create"],
                "running_job_ids": [],
            },
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 200
        test_db.refresh(job)
        assert job.status == "queued"

    def test_upload_job_artifact_drops_body_without_consumer(
        self, test_client: TestClient, test_db, admin_headers
    ):
        # No download is waiting (relay channel not registered) -> the endpoint
        # drains the body and reports it was dropped, so the agent never blocks.
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/artifact",
            content=b"orphaned-bytes",
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 200
        assert response.json() == {"accepted": False, "size": 0}

    def test_agent_cannot_mutate_another_agents_job(
        self, test_client: TestClient, test_db, admin_headers
    ):
        first = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers, "first")["token"],
            name="first",
        )
        second = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers, "second")["token"],
            name="second",
        )
        second_agent = _get_agent(test_db, second["agent_id"])
        second_job = _create_agent_job(test_db, second_agent)

        response = test_client.post(
            f"/api/agents/jobs/{second_job.id}/claim",
            headers=_agent_headers(first["agent_token"]),
        )

        assert response.status_code == 404

    def test_fail_job_records_error_and_return_code(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/fail",
            json={"error_message": "borg exited with code 2", "return_code": 2},
            headers=_agent_headers(registered["agent_token"]),
        )

        assert response.status_code == 200
        test_db.refresh(job)
        assert job.status == "failed"
        assert job.error_message == "borg exited with code 2"
        assert job.result == {"return_code": 2}

    def test_admin_cancel_request_reaches_running_agent_via_heartbeat(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")

        cancel = test_client.post(
            f"/api/managed-machines/agent-jobs/{job.id}/cancel",
            headers=admin_headers,
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancel_requested"

        heartbeat = test_client.post(
            "/api/agents/heartbeat",
            json={"agent_id": registered["agent_id"], "running_job_ids": [job.id]},
            headers=_agent_headers(registered["agent_token"]),
        )
        assert heartbeat.status_code == 200
        assert heartbeat.json()["cancel_job_ids"] == [job.id]

        canceled = test_client.post(
            f"/api/agents/jobs/{job.id}/cancel",
            json={},
            headers=_agent_headers(registered["agent_token"]),
        )
        assert canceled.status_code == 200
        assert canceled.json()["status"] == "canceled"

    def test_admin_can_list_agent_jobs(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent)

        response = test_client.get(
            "/api/managed-machines/agent-jobs", headers=admin_headers
        )

        assert response.status_code == 200
        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["id"] == job.id


class TestAgentJobReaper:
    def _stale_running_job(self, test_db, test_client, admin_headers, status="running"):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status=status)
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        job.started_at = stale_at
        job.updated_at = stale_at
        test_db.commit()
        return job

    def test_reaps_stale_in_flight_job(self, test_client, test_db, admin_headers):
        from app.services.agent_job_reaper import reap_stale_agent_jobs

        job = self._stale_running_job(test_db, test_client, admin_headers)

        reaped = reap_stale_agent_jobs(test_db)

        assert reaped == 1
        test_db.refresh(job)
        assert job.status == "failed"
        assert job.completed_at is not None
        assert "orphaned" in (job.error_message or "")

    def test_spares_recently_active_job(self, test_client, test_db, admin_headers):
        from app.services.agent_job_reaper import reap_stale_agent_jobs

        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")  # updated_at = now

        reaped = reap_stale_agent_jobs(test_db)

        assert reaped == 0
        test_db.refresh(job)
        assert job.status == "running"

    def test_ignores_terminal_jobs(self, test_client, test_db, admin_headers):
        from app.services.agent_job_reaper import reap_stale_agent_jobs

        job = self._stale_running_job(
            test_db, test_client, admin_headers, status="completed"
        )

        reaped = reap_stale_agent_jobs(test_db)

        assert reaped == 0
        test_db.refresh(job)
        assert job.status == "completed"

    def test_fails_linked_backup_job(self, test_client, test_db, admin_headers):
        from app.services.agent_job_reaper import reap_stale_agent_jobs

        backup_job = seed_job_operation(
            test_db,
            "backup",
            repository="/repo",
            status="running",
        )
        test_db.commit()
        test_db.refresh(backup_job)

        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        # Link and stale-ify in a single commit; updated_at has an onupdate, so a
        # later separate commit would refresh the timestamp and un-stale the job.
        job.operation_id = backup_job.id
        job.started_at = stale_at
        job.updated_at = stale_at
        test_db.commit()

        reaped = reap_stale_agent_jobs(test_db)

        assert reaped == 1
        test_db.refresh(backup_job)
        assert backup_job.status == "failed"

    def test_does_not_overwrite_terminal_backup_job(
        self, test_client, test_db, admin_headers
    ):
        from app.services.agent_job_reaper import reap_stale_agent_jobs

        # An already-finished backup must not be flipped back to failed when its
        # AgentJob gets stale-reaped after the fact.
        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="completed"
        )
        test_db.commit()
        test_db.refresh(backup_job)

        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        job = _create_agent_job(test_db, agent, status="running")
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        job.operation_id = backup_job.id
        job.started_at = stale_at
        job.updated_at = stale_at
        test_db.commit()

        reap_stale_agent_jobs(test_db)

        test_db.refresh(backup_job)
        assert backup_job.status == "completed"


NOTIFIER_PATCH_TARGET = "app.services.agent_job_notifications.notification_service"


@pytest.mark.unit
class TestAgentJobNotifications:
    """Agent-executed jobs must fire the same user-facing notifications the
    server-side execution paths send from inside their services."""

    def _register(self, test_client, test_db, admin_headers):
        registered = _register_agent(
            test_client,
            _create_enrollment_token(test_client, admin_headers)["token"],
        )
        agent = _get_agent(test_db, registered["agent_id"])
        return agent, _agent_headers(registered["agent_token"])

    def _linked_backup_job(self, test_db, agent, *, agent_status="running"):
        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="running"
        )
        test_db.commit()
        test_db.refresh(backup_job)
        job = _create_agent_job(test_db, agent, status=agent_status)
        job.operation_id = backup_job.id
        test_db.commit()
        return job, backup_job

    def test_completed_backup_job_sends_success_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(test_db, agent)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            response = test_client.post(
                f"/api/agents/jobs/{job.id}/complete",
                json={"result": {"archive_name": "agent-archive", "return_code": 0}},
                headers=headers,
            )

        assert response.status_code == 200
        notifier.send_backup_success.assert_awaited_once()
        args = notifier.send_backup_success.await_args.args
        assert args[1] == "/repo"
        assert args[2] == "agent-archive"
        notifier.send_backup_warning.assert_not_awaited()
        notifier.send_backup_failure.assert_not_awaited()

    def test_warning_completion_sends_warning_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(test_db, agent)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            response = test_client.post(
                f"/api/agents/jobs/{job.id}/complete",
                json={"result": {"archive_name": "agent-archive", "return_code": 1}},
                headers=headers,
            )

        assert response.status_code == 200
        notifier.send_backup_warning.assert_awaited_once()
        notifier.send_backup_success.assert_not_awaited()

    def test_error_return_code_sends_failure_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(test_db, agent)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            response = test_client.post(
                f"/api/agents/jobs/{job.id}/complete",
                json={"result": {"return_code": 2}},
                headers=headers,
            )

        assert response.status_code == 200
        notifier.send_backup_failure.assert_awaited_once()
        args = notifier.send_backup_failure.await_args.args
        assert args[1] == "/repo"
        assert "borg exited with code 2" in args[2]
        assert args[3] == backup_job.id
        notifier.send_backup_success.assert_not_awaited()

    def test_failed_job_sends_failure_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(test_db, agent)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            response = test_client.post(
                f"/api/agents/jobs/{job.id}/fail",
                json={"error_message": "disk full", "return_code": 2},
                headers=headers,
            )

        assert response.status_code == 200
        notifier.send_backup_failure.assert_awaited_once()
        args = notifier.send_backup_failure.await_args.args
        assert args[2] == "disk full"

    def test_repeated_completion_does_not_duplicate_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(test_db, agent)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            for _ in range(2):
                response = test_client.post(
                    f"/api/agents/jobs/{job.id}/complete",
                    json={
                        "result": {"archive_name": "agent-archive", "return_code": 0}
                    },
                    headers=headers,
                )
                assert response.status_code == 200

        notifier.send_backup_success.assert_awaited_once()

    def test_first_start_report_sends_backup_start_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(
            test_db, agent, agent_status="claimed"
        )

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            for _ in range(2):
                response = test_client.post(
                    f"/api/agents/jobs/{job.id}/start",
                    json={},
                    headers=headers,
                )
                assert response.status_code == 200

        notifier.send_backup_start.assert_awaited_once()
        args = notifier.send_backup_start.await_args.args
        assert args[1] == "/repo"

    def _agent_check_job(self, test_db, agent, *, name="agent-check-repo"):
        repository = Repository(name=name, path=f"/{name}")
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)
        check_job = seed_job_operation(
            test_db, "check", repository_id=repository.id, status="running"
        )
        test_db.commit()
        test_db.refresh(check_job)
        now = datetime.now(timezone.utc)
        job = AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status="running",
            payload={
                "schema_version": 1,
                "job_kind": "repository.check",
                "repository": {"id": repository.id},
                "operation": {"maintenance_job": {"kind": "check", "id": check_job.id}},
            },
            created_at=now,
            updated_at=now,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)
        return job, check_job, repository

    def test_agent_check_completion_sends_check_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, check_job, repository = self._agent_check_job(test_db, agent)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            response = test_client.post(
                f"/api/agents/jobs/{job.id}/complete",
                json={"result": {"return_code": 0}},
                headers=headers,
            )

        assert response.status_code == 200
        notifier.send_check_completion.assert_awaited_once()
        kwargs = notifier.send_check_completion.await_args.kwargs
        assert kwargs["status"] == "completed"
        assert kwargs["repository_name"] == repository.name
        assert kwargs["check_type"] == "manual"

    def test_agent_check_failure_sends_check_notification(
        self, test_client, test_db, admin_headers
    ):
        agent, headers = self._register(test_client, test_db, admin_headers)
        job, check_job, repository = self._agent_check_job(
            test_db, agent, name="agent-check-repo-2"
        )

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            response = test_client.post(
                f"/api/agents/jobs/{job.id}/fail",
                json={"error_message": "check failed", "return_code": 2},
                headers=headers,
            )

        assert response.status_code == 200
        notifier.send_check_completion.assert_awaited_once()
        kwargs = notifier.send_check_completion.await_args.kwargs
        assert kwargs["status"] == "failed"
        assert kwargs["error_message"] == "check failed"

    async def test_notify_backup_job_finished_prefers_plan_name(self, test_db):
        from app.services.agent_job_notifications import notify_backup_job_finished

        plan = BackupPlan(name="nightly", source_directories="[]")
        test_db.add(plan)
        test_db.commit()
        test_db.refresh(plan)
        # An operation names its plan through the run, which is where the
        # facade reads `backup_plan_id` from.
        run = BackupPlanRun(backup_plan_id=plan.id, trigger="manual", status="running")
        test_db.add(run)
        test_db.commit()
        backup_job = resolve_backup_job(
            test_db,
            seed_job_operation(
                test_db,
                "backup",
                repository="/repo",
                status="failed",
                backup_plan_run_id=run.id,
                error_message="agent session lost",
            ).id,
        )

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            await notify_backup_job_finished(
                test_db, resolve_backup_job(test_db, backup_job.id)
            )

        notifier.send_backup_failure.assert_awaited_once()
        args = notifier.send_backup_failure.await_args.args
        assert args[2] == "agent session lost"
        assert args[4] == "nightly"

    async def test_notify_backup_job_finished_skips_cancelled(self, test_db):
        from app.services.agent_job_notifications import notify_backup_job_finished

        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="cancelled"
        )
        test_db.commit()

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            await notify_backup_job_finished(
                test_db, resolve_backup_job(test_db, backup_job.id)
            )

        notifier.send_backup_failure.assert_not_awaited()
        notifier.send_backup_success.assert_not_awaited()

    def test_reaper_collects_failed_backup_jobs_for_notification(
        self, test_client, test_db, admin_headers
    ):
        from app.services.agent_job_reaper import reap_stale_agent_jobs

        agent, _headers = self._register(test_client, test_db, admin_headers)
        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="running"
        )
        test_db.commit()
        test_db.refresh(backup_job)
        job = _create_agent_job(test_db, agent, status="running")
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        job.operation_id = backup_job.id
        job.started_at = stale_at
        job.updated_at = stale_at
        test_db.commit()

        failed_backup_job_ids: list[int] = []
        reaped = reap_stale_agent_jobs(
            test_db, failed_backup_job_ids=failed_backup_job_ids
        )

        assert reaped == 1
        assert failed_backup_job_ids == [backup_job.id]

    def test_reaper_does_not_collect_terminal_backup_jobs(
        self, test_client, test_db, admin_headers
    ):
        from app.services.agent_job_reaper import reap_stale_agent_jobs

        agent, _headers = self._register(test_client, test_db, admin_headers)
        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="completed"
        )
        test_db.commit()
        test_db.refresh(backup_job)
        job = _create_agent_job(test_db, agent, status="running")
        stale_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        job.operation_id = backup_job.id
        job.started_at = stale_at
        job.updated_at = stale_at
        test_db.commit()

        failed_backup_job_ids: list[int] = []
        reap_stale_agent_jobs(test_db, failed_backup_job_ids=failed_backup_job_ids)

        assert failed_backup_job_ids == []

    def test_stale_completion_report_cannot_double_finalize(
        self, test_client, test_db, admin_headers
    ):
        from sqlalchemy.orm import Session as SASession

        from app.api.agents import _complete_agent_job

        agent, _headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(test_db, agent)

        # A second session models the other transport holding a stale view of
        # the still-running job (its read transaction already closed, as after
        # a completed request cycle).
        stale_db = SASession(bind=test_db.get_bind(), expire_on_commit=False)
        try:
            stale_job = stale_db.query(AgentJob).filter(AgentJob.id == job.id).first()
            assert stale_job.status == "running"
            stale_db.commit()

            # The reaper (or the other transport) finalizes the job first.
            test_db.query(AgentJob).filter(AgentJob.id == job.id).update(
                {AgentJob.status: "failed", AgentJob.error_message: "reaped"},
                synchronize_session=False,
            )
            test_db.query(Operation).filter(Operation.id == backup_job.id).update(
                {Operation.status: "failed", Operation.error_message: "reaped"},
                synchronize_session=False,
            )
            test_db.commit()

            transitioned = _complete_agent_job(
                stale_job, stale_db, result={"archive_name": "late", "return_code": 0}
            )
            stale_db.commit()
            assert transitioned is False
        finally:
            stale_db.close()

        test_db.expire_all()
        assert (
            test_db.query(AgentJob).filter(AgentJob.id == job.id).first().status
            == "failed"
        )
        linked = test_db.get(Operation, backup_job.id)
        assert linked.status == "failed"
        assert linked.error_message == "reaped"

    def test_stale_start_report_does_not_claim_start_notification(
        self, test_client, test_db, admin_headers
    ):
        from sqlalchemy.orm import Session as SASession

        from app.api.agents import _mark_agent_job_started

        agent, _headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(
            test_db, agent, agent_status="claimed"
        )

        stale_db = SASession(bind=test_db.get_bind(), expire_on_commit=False)
        try:
            stale_job = stale_db.query(AgentJob).filter(AgentJob.id == job.id).first()
            stale_db.commit()

            first = _mark_agent_job_started(job, test_db)
            test_db.commit()
            assert first is not None

            second = _mark_agent_job_started(stale_job, stale_db)
            stale_db.commit()
            assert second is None
        finally:
            stale_db.close()

    def test_requeued_job_does_not_claim_the_start_notification_twice(
        self, test_client, test_db, admin_headers
    ):
        """A reconnect after a requeue must not notify a second time. The
        requeue clears `started_at`, so the claim hangs off its own marker."""
        from app.api.agents import _mark_agent_job_started, _requeue_stale_agent_jobs

        agent, _headers = self._register(test_client, test_db, admin_headers)
        job, _backup_job = self._linked_backup_job(
            test_db, agent, agent_status="claimed"
        )

        assert _mark_agent_job_started(job, test_db) is not None
        test_db.commit()

        stale_at = datetime.now(timezone.utc) - timedelta(hours=2)
        test_db.query(AgentJob).filter(AgentJob.id == job.id).update(
            {AgentJob.updated_at: stale_at, AgentJob.started_at: stale_at},
            synchronize_session=False,
        )
        test_db.commit()
        test_db.expire_all()
        job = test_db.query(AgentJob).filter(AgentJob.id == job.id).first()
        _requeue_stale_agent_jobs(
            test_db, agent, now=datetime.now(timezone.utc), running_job_ids=[]
        )
        test_db.commit()
        assert job.status == "queued"
        assert job.started_at is None

        assert _mark_agent_job_started(job, test_db) is None

    async def test_expired_object_reads_stay_inside_notification_boundary(
        self, test_db
    ):
        from app.services.agent_job_notifications import notify_backup_job_finished

        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="failed", error_message="x"
        )
        test_db.commit()
        facade = resolve_backup_job(test_db, backup_job.id)
        # Detached + expired: every attribute read raises, modeling a refresh
        # failure on the committed (expired) row after the job turned final.
        test_db.expire(backup_job)
        test_db.expunge(backup_job)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            await notify_backup_job_finished(test_db, facade)

        notifier.send_backup_failure.assert_not_awaited()

    async def test_notifier_failure_does_not_propagate(self, test_db):
        from app.services.agent_job_notifications import notify_backup_job_finished

        backup_job = seed_job_operation(
            test_db, "backup", repository="/repo", status="failed", error_message="x"
        )
        test_db.commit()
        test_db.refresh(backup_job)

        with patch(NOTIFIER_PATCH_TARGET, new_callable=AsyncMock) as notifier:
            notifier.send_backup_failure.side_effect = RuntimeError("boom")
            await notify_backup_job_finished(
                test_db, resolve_backup_job(test_db, backup_job.id)
            )

        notifier.send_backup_failure.assert_awaited_once()

    def test_stale_cancel_report_cannot_overwrite_terminal_state(
        self, test_client, test_db, admin_headers
    ):
        from sqlalchemy.orm import Session as SASession

        from app.api.agents import _cancel_agent_job

        agent, _headers = self._register(test_client, test_db, admin_headers)
        job, backup_job = self._linked_backup_job(test_db, agent)

        stale_db = SASession(bind=test_db.get_bind(), expire_on_commit=False)
        try:
            stale_job = stale_db.query(AgentJob).filter(AgentJob.id == job.id).first()
            stale_db.commit()

            test_db.query(AgentJob).filter(AgentJob.id == job.id).update(
                {AgentJob.status: "failed", AgentJob.error_message: "reaped"},
                synchronize_session=False,
            )
            test_db.query(Operation).filter(Operation.id == backup_job.id).update(
                {Operation.status: "failed", Operation.error_message: "reaped"},
                synchronize_session=False,
            )
            test_db.commit()

            _cancel_agent_job(stale_job, stale_db)
            stale_db.commit()
        finally:
            stale_db.close()

        test_db.expire_all()
        assert (
            test_db.query(AgentJob).filter(AgentJob.id == job.id).first().status
            == "failed"
        )
        assert test_db.get(Operation, backup_job.id).status == "failed"

    def _running_compact_operation(self, test_db, repository):
        operation = Operation(
            repository_id=repository.id,
            kind="compact",
            category="maintenance",
            status="running",
            trigger="manual",
            priority=10,
            run_id="run-compact",
        )
        test_db.add(operation)
        test_db.commit()
        return operation

    def _compact_agent_job(self, test_db, agent, repository, operation):
        now = datetime.now(timezone.utc)
        job = AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status="running",
            payload={
                "schema_version": 1,
                "job_kind": "repository.compact",
                "repository": {"id": repository.id},
                "operation": {
                    "maintenance_job": {"kind": "compact", "id": operation.id}
                },
            },
            created_at=now,
            updated_at=now,
        )
        test_db.add(job)
        test_db.commit()
        return job

    def _post_stats_line(self, test_client, headers, job, sequence, message):
        response = test_client.post(
            f"/api/agents/jobs/{job.id}/logs",
            json={
                "sequence": sequence,
                "stream": "stderr",
                "message": json.dumps(
                    {
                        "type": "log_message",
                        "levelname": "INFO",
                        "name": "borg.archiver.compact_cmd",
                        "message": message,
                    }
                ),
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text

    def test_agent_compact_completion_takes_stats_from_the_completion_report(
        self, test_client, test_db, admin_headers
    ):
        """An agent from release 0.1.4 parses its own `compact --stats`
        output and sends the statistics with its completion; they land on
        the operation's result and fill a size nothing has measured (#931).
        No log line is needed for that."""
        agent, headers = self._register(test_client, test_db, admin_headers)
        repository = Repository(
            name="agent-compact-repo", path="/agent-compact", borg_version=2
        )
        test_db.add(repository)
        test_db.commit()
        operation = self._running_compact_operation(test_db, repository)
        job = self._compact_agent_job(test_db, agent, repository, operation)
        stats = {
            "repository_size": 502_000,
            "compaction_saved": 0,
            "size_precision": "exact",
        }
        # stored as reported, so only the known fields in their shapes are
        reported = {
            **stats,
            "deduplication_factor": -1.5,
            "compression_factor": 2,
            "object_count": 1e300,
            "source_size": -1,
            "archive_count": True,
            "padding": "x" * 1000,
        }
        stats["compression_factor"] = 2.0

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"return_code": 0, "stats": reported}},
            headers=headers,
        )
        assert response.status_code == 200
        test_db.refresh(operation)
        test_db.refresh(repository)
        assert operation.status == "completed"
        assert operation.result["stats"] == stats
        assert repository.total_size == "490.23 KB"
        assert repository.total_size_source == "compact_stats"

        status = test_client.get(
            f"/api/repositories/compact-jobs/{operation.id}",
            headers=admin_headers,
        )
        assert status.status_code == 200, status.text
        assert status.json()["stats"]["repository_size"] == 502_000

    def test_agent_compact_report_with_a_figure_beyond_borgs_range(
        self, test_client, test_db, admin_headers
    ):
        """A `repository_size` no Borg printed (too large for a float) is not
        a statistics block: the completion goes through, the compact records
        no statistics, and a precision label that is not one of the two
        known values is dropped rather than trusted."""
        agent, headers = self._register(test_client, test_db, admin_headers)
        repository = Repository(
            name="agent-compact-huge",
            path="/agent-compact-huge",
            borg_version=2,
            total_size="keep",
            total_size_source="storage_used",
        )
        test_db.add(repository)
        test_db.commit()
        operation = self._running_compact_operation(test_db, repository)
        job = self._compact_agent_job(test_db, agent, repository, operation)

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={
                "result": {
                    "return_code": 0,
                    "stats": {
                        "repository_size": 10**400,
                        "compression_factor": 10**400,
                        "size_precision": "exact",
                    },
                }
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        test_db.refresh(operation)
        test_db.refresh(repository)
        assert operation.status == "completed"
        assert (operation.result or {}).get("stats") is None
        assert repository.total_size == "keep"

        # a label outside the known two counts as rounded: a store walk
        # stays; a factor that is not a finite number is dropped, not stored
        operation2 = self._running_compact_operation(test_db, repository)
        job2 = self._compact_agent_job(test_db, agent, repository, operation2)
        response = test_client.post(
            f"/api/agents/jobs/{job2.id}/complete",
            content=json.dumps(
                {
                    "result": {
                        "return_code": 0,
                        "stats": {
                            "repository_size": 5,
                            "deduplication_factor": 1e400,
                            "size_precision": "guess",
                        },
                    }
                }
            ),
            headers={**headers, "Content-Type": "application/json"},
        )
        assert response.status_code == 200, response.text
        test_db.refresh(operation2)
        test_db.refresh(repository)
        assert operation2.result["stats"] == {"repository_size": 5}
        assert repository.total_size == "keep"
        assert repository.total_size_source == "storage_used"
        status = test_client.get(
            f"/api/repositories/compact-jobs/{operation2.id}", headers=admin_headers
        )
        assert status.status_code == 200, status.text

    def test_agent_compact_completion_parses_the_log_when_the_report_has_no_stats(
        self, test_client, test_db, admin_headers
    ):
        """An agent that streamed the statistics lines but reported none
        (the build before the report carried them) still gets them parsed
        from the tail of its log at completion; a report whose `stats` is
        not a statistics block counts as none."""
        agent, headers = self._register(test_client, test_db, admin_headers)
        repository = Repository(
            name="agent-compact-log", path="/agent-compact-log", borg_version=2
        )
        test_db.add(repository)
        test_db.commit()
        operation = self._running_compact_operation(test_db, repository)
        job = self._compact_agent_job(test_db, agent, repository, operation)
        for sequence in range(1, 80):
            self._post_stats_line(
                test_client, headers, job, sequence, f"line {sequence}"
            )
        # two lines flushed in one frame land in one row
        frames = "\n".join(
            json.dumps({"type": "log_message", "levelname": "INFO", "message": m})
            for m in (
                "Repository size is 502000 B in 6 objects.",
                "Compaction saved 0 B.",
            )
        )
        response = test_client.post(
            f"/api/agents/jobs/{job.id}/logs",
            json={"sequence": 80, "stream": "stderr", "message": frames},
            headers=headers,
        )
        assert response.status_code == 200, response.text

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"return_code": 0, "stats": {"repository_size": "6"}}},
            headers=headers,
        )
        assert response.status_code == 200
        test_db.refresh(operation)
        test_db.refresh(repository)
        assert operation.status == "completed"
        assert operation.result["stats"]["repository_size"] == 502_000
        assert operation.result["stats"]["compaction_saved"] == 0
        assert repository.total_size == "490.23 KB"
        assert repository.total_size_source == "compact_stats"

    def test_agent_compact_completion_without_stats_records_none(
        self, test_client, test_db, admin_headers
    ):
        """Seen live: the agent's last log lines and its completion travel
        on different paths, and the completion can win by 150 ms. With no
        statistics in the report and none in the log yet, this compact
        records none and the size stays as it was; nothing re-reads the
        lines that arrive later."""
        agent, headers = self._register(test_client, test_db, admin_headers)
        repository = Repository(
            name="agent-compact-late",
            path="/agent-compact-late",
            borg_version=2,
            total_size="keep",
            total_size_source="storage_used",
        )
        test_db.add(repository)
        test_db.commit()
        operation = self._running_compact_operation(test_db, repository)
        job = self._compact_agent_job(test_db, agent, repository, operation)

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={"result": {"return_code": 0}},
            headers=headers,
        )
        assert response.status_code == 200
        self._post_stats_line(
            test_client, headers, job, 1, "Repository size is 502000 B in 6 objects."
        )
        test_db.refresh(operation)
        test_db.refresh(repository)
        assert operation.status == "completed"
        assert (operation.result or {}).get("stats") is None
        assert repository.total_size == "keep"
        assert repository.total_size_source == "storage_used"

    def test_agent_compact_report_for_a_borg1_repository_is_not_believed(
        self, test_client, test_db, admin_headers
    ):
        """Borg 1 compact prints no statistics; a report that carries some
        for a Borg 1 repository does not touch the size."""
        agent, headers = self._register(test_client, test_db, admin_headers)
        repository = Repository(
            name="agent-compact-borg1", path="/agent-compact-borg1", borg_version=1
        )
        test_db.add(repository)
        test_db.commit()
        operation = self._running_compact_operation(test_db, repository)
        job = self._compact_agent_job(test_db, agent, repository, operation)

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={
                "result": {
                    "return_code": 0,
                    "stats": {"repository_size": 5, "size_precision": "exact"},
                }
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        test_db.refresh(operation)
        test_db.refresh(repository)
        assert operation.status == "completed"
        assert (operation.result or {}).get("stats") is None
        assert repository.total_size is None

    def test_agent_compact_with_a_warning_exit_keeps_its_statistics(
        self, test_client, test_db, admin_headers
    ):
        """A compact that warned ran through: the operation ends
        `completed_with_warnings` and the statistics of its report are
        stored and acted on like those of a clean run."""
        agent, headers = self._register(test_client, test_db, admin_headers)
        repository = Repository(
            name="agent-compact-warn", path="/agent-compact-warn", borg_version=2
        )
        test_db.add(repository)
        test_db.commit()
        operation = self._running_compact_operation(test_db, repository)
        job = self._compact_agent_job(test_db, agent, repository, operation)

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={
                "result": {
                    "return_code": 1,
                    "status": "completed_with_warnings",
                    "stats": {"repository_size": 502_000, "size_precision": "exact"},
                }
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        test_db.refresh(operation)
        test_db.refresh(repository)
        assert operation.status == "completed_with_warnings"
        assert operation.result["stats"]["repository_size"] == 502_000
        assert repository.total_size == "490.23 KB"
        assert repository.last_compact is not None

    def test_agent_compact_statistics_keep_a_measured_size(
        self, test_client, test_db, admin_headers
    ):
        """The statistics always land on the operation; a size the chunk
        index measured is not replaced by the compact's pack file figure
        (the `stats` follow-up measures again after every compact)."""
        agent, headers = self._register(test_client, test_db, admin_headers)
        repository = Repository(
            name="agent-compact-measured",
            path="/agent-compact-measured",
            borg_version=2,
            total_size="7.00 GB",
            total_size_source="borg2_index",
        )
        test_db.add(repository)
        test_db.commit()
        operation = self._running_compact_operation(test_db, repository)
        job = self._compact_agent_job(test_db, agent, repository, operation)

        response = test_client.post(
            f"/api/agents/jobs/{job.id}/complete",
            json={
                "result": {
                    "return_code": 0,
                    "stats": {"repository_size": 5, "size_precision": "exact"},
                }
            },
            headers=headers,
        )
        assert response.status_code == 200
        test_db.refresh(operation)
        test_db.refresh(repository)
        assert operation.result["stats"]["repository_size"] == 5
        assert repository.total_size == "7.00 GB"
        assert repository.total_size_source == "borg2_index"


@pytest.mark.unit
class TestAgentTimezone:
    """The agent's reported IANA zone interprets borg's local-time archive
    timestamps; only resolvable names may be stored."""

    def _register_with_timezone(self, test_client, admin_headers, tz):
        enrollment = _create_enrollment_token(test_client, admin_headers)
        response = test_client.post(
            "/api/agents/register",
            json={
                "enrollment_token": enrollment["token"],
                "name": "tz-agent",
                "hostname": "tz.local",
                "os": "linux",
                "arch": "amd64",
                "agent_version": "0.1.1",
                "timezone": tz,
                "borg_versions": [],
                "capabilities": ["backup.create"],
            },
        )
        assert response.status_code == 200
        return response.json()

    def test_register_persists_valid_timezone(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = self._register_with_timezone(
            test_client, admin_headers, "Europe/Berlin"
        )

        agent = _get_agent(test_db, registered["agent_id"])
        assert agent.timezone == "Europe/Berlin"

    def test_register_drops_invalid_timezone(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = self._register_with_timezone(
            test_client, admin_headers, "Not/AZone"
        )

        agent = _get_agent(test_db, registered["agent_id"])
        assert agent.timezone is None

    def test_heartbeat_updates_timezone_but_keeps_it_on_omission(
        self, test_client: TestClient, test_db, admin_headers
    ):
        registered = self._register_with_timezone(
            test_client, admin_headers, "Europe/Berlin"
        )
        headers = _agent_headers(registered["agent_token"])

        heartbeat = {
            "agent_id": registered["agent_id"],
            "hostname": "tz.local",
            "agent_version": "0.1.1",
            "borg_versions": [],
            "capabilities": ["backup.create"],
            "running_job_ids": [],
        }

        # A heartbeat without a zone (old agent) must not erase the stored one.
        response = test_client.post(
            "/api/agents/heartbeat", json=heartbeat, headers=headers
        )
        assert response.status_code == 200
        agent = _get_agent(test_db, registered["agent_id"])
        assert agent.timezone == "Europe/Berlin"

        response = test_client.post(
            "/api/agents/heartbeat",
            json={**heartbeat, "timezone": "America/New_York"},
            headers=headers,
        )
        assert response.status_code == 200
        test_db.refresh(agent)
        assert agent.timezone == "America/New_York"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_waiter_returns_on_a_completion_with_warnings(
    test_client, test_db, admin_headers
):
    """An agent that ran a Borg command through with a warning exit reports
    a completion, which the server records as `completed_with_warnings`;
    the waiter of a delegated maintenance operation must return on it,
    not poll until the timeout."""
    from app.services.repository_executor import (
        wait_for_agent_repository_operation_job,
    )

    registered = _register_agent(
        test_client, _create_enrollment_token(test_client, admin_headers)["token"]
    )
    agent = _get_agent(test_db, registered["agent_id"])
    job = _create_agent_job(test_db, agent, status="completed_with_warnings")
    job.result = {"return_code": 1, "stats": {"repository_size": 5}}
    test_db.commit()

    result = await wait_for_agent_repository_operation_job(
        test_db, job.id, timeout_seconds=2, poll_interval_seconds=0.01
    )
    assert result["stats"] == {"repository_size": 5}

    job.status = "failed"
    job.error_message = "borg exited with code 2"
    test_db.commit()
    with pytest.raises(HTTPException) as excinfo:
        await wait_for_agent_repository_operation_job(
            test_db, job.id, timeout_seconds=2, poll_interval_seconds=0.01
        )
    assert excinfo.value.status_code == 502


@pytest.mark.unit
@pytest.mark.asyncio
async def test_script_and_backup_waiters_return_on_a_completion_with_warnings(
    test_client, test_db, admin_headers
):
    """The other waiters share the terminal set: a hook script or a backup
    whose agent job ended `completed_with_warnings` must not be polled
    forever."""
    from app.services.repository_executor import (
        wait_for_agent_backup_job,
        wait_for_agent_script_job,
    )

    registered = _register_agent(
        test_client, _create_enrollment_token(test_client, admin_headers)["token"]
    )
    agent = _get_agent(test_db, registered["agent_id"])
    script_job = _create_agent_job(test_db, agent, status="completed_with_warnings")
    script_job.result = {"return_code": 1}
    backup_job = seed_job_operation(
        test_db, "backup", repository="/repo", status="completed_with_warnings"
    )
    test_db.commit()
    agent_backup_job = _create_agent_job(
        test_db, agent, status="completed_with_warnings"
    )
    agent_backup_job.operation_id = backup_job.id
    test_db.commit()

    snapshot = await wait_for_agent_script_job(
        test_db, script_job.id, timeout_seconds=2, poll_interval_seconds=0.01
    )
    assert snapshot["status"] == "completed_with_warnings"
    assert snapshot["result"] == {"return_code": 1}

    status_value = await wait_for_agent_backup_job(
        test_db,
        agent_backup_job.id,
        backup_job.id,
        lambda: False,
        poll_interval_seconds=0.01,
    )
    assert status_value == "completed_with_warnings"
