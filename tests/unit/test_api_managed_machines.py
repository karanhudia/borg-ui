from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentJobLog, AgentMachine


def _agent(test_db, **overrides):
    values = {
        "name": "Agent",
        "agent_id": "agt_filesystem",
        "token_hash": get_password_hash("borgui_agent_secret"),
        "token_prefix": "borgui_agent_secret"[:20],
        "status": "online",
        "capabilities": ["filesystem.browse"],
    }
    values.update(overrides)
    agent = AgentMachine(**values)
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


def _agent_job(test_db, agent: AgentMachine) -> AgentJob:
    now = datetime.now(timezone.utc)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="queued",
        payload={"schema_version": 1, "job_kind": "backup.create"},
        created_at=now,
        updated_at=now,
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)
    return job


def test_create_enrollment_token_accepts_days(test_client: TestClient, admin_headers):
    before = datetime.now(timezone.utc)

    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        json={"name": "pi setup", "expires_in_days": 7},
        headers=admin_headers,
    )

    assert response.status_code == 201
    expires_at = datetime.fromisoformat(response.json()["expires_at"])
    assert (
        before + timedelta(days=7)
        <= expires_at
        <= before + timedelta(days=7, seconds=5)
    )


def test_create_enrollment_token_accepts_never(test_client: TestClient, admin_headers):
    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        json={"name": "lab setup", "expires_never": True},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["expires_at"] is None


def test_create_enrollment_token_keeps_minutes_payload(
    test_client: TestClient, admin_headers
):
    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        json={"name": "short setup", "expires_in_minutes": 60},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["expires_at"] is not None


def test_create_enrollment_token_rejects_too_short_expiry(
    test_client: TestClient, admin_headers
):
    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        json={"name": "too short", "expires_in_minutes": 4},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_agent_filesystem_browse_endpoint_requires_capability(
    test_client: TestClient, admin_headers, test_db
):
    agent = _agent(test_db, capabilities=["backup.create"])

    response = test_client.get(
        f"/api/managed-machines/agents/{agent.id}/filesystem/browse?path=/",
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["key"] == "backend.errors.agents.capabilityMissing"


def test_agent_filesystem_browse_endpoint_returns_browse_result(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(test_db)
    calls = []

    async def fake_browse(
        db, agent_machine_id, *, path, include_hidden, timeout_seconds=15
    ):
        calls.append((agent_machine_id, path, include_hidden, timeout_seconds))
        return {"current_path": path, "parent_path": None, "items": []}

    monkeypatch.setattr(
        "app.api.managed_machines.browse_agent_filesystem",
        fake_browse,
    )

    response = test_client.get(
        f"/api/managed-machines/agents/{agent.id}/filesystem/browse"
        "?path=/home/pi&include_hidden=true",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "current_path": "/home/pi",
        "parent_path": None,
        "items": [],
    }
    assert calls == [(agent.id, "/home/pi", True, 15)]


def test_delete_agent_hides_it_from_list_and_keeps_job_logs(
    test_client: TestClient, admin_headers, test_db
):
    agent = _agent(test_db)
    job = _agent_job(test_db, agent)
    now = datetime.now(timezone.utc)
    test_db.add(
        AgentJobLog(
            agent_job_id=job.id,
            sequence=1,
            stream="stdout",
            message="still readable",
            created_at=now,
            received_at=now,
        )
    )
    test_db.commit()

    response = test_client.delete(
        f"/api/managed-machines/agents/{agent.id}",
        headers=admin_headers,
    )

    assert response.status_code == 204
    test_db.refresh(agent)
    assert agent.status == "deleted"
    assert agent.deleted_at is not None

    listed = test_client.get("/api/managed-machines/agents", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json() == []

    logs = test_client.get(
        f"/api/managed-machines/agent-jobs/{job.id}/logs",
        headers=admin_headers,
    )
    assert logs.status_code == 200
    assert logs.json()[0]["message"] == "still readable"
