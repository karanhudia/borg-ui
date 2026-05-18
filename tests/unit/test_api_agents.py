from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.agent_auth import AGENT_AUTH_HEADER, AGENT_TOKEN_PREFIX_LENGTH
from app.core.security import get_password_hash
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentJobLog,
    AgentMachine,
)


def _create_enrollment_token(test_client: TestClient, admin_headers, name="agent"):
    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        json={"name": name, "expires_in_minutes": 60},
        headers=admin_headers,
    )
    assert response.status_code == 201
    return response.json()


def _register_agent(test_client: TestClient, enrollment_token: str, name="laptop"):
    response = test_client.post(
        "/api/agents/register",
        json={
            "enrollment_token": enrollment_token,
            "name": name,
            "hostname": "laptop.local",
            "os": "linux",
            "arch": "amd64",
            "agent_version": "0.1.0",
            "borg_versions": [
                {"major": 1, "version": "1.2.8", "path": "/usr/bin/borg"}
            ],
            "capabilities": ["backup.create", "logs.stream"],
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
