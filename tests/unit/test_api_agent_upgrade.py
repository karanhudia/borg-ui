"""POST /managed-machines/agents/upgrade.

Validation runs over the whole request before any job is created: a partial
success that reports as a full one is the failure mode to avoid.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, LicensingState
from app.services.agent_connection_manager import AgentConnectionUnavailable


@pytest.fixture(autouse=True)
def _enable_paid_managed_agent_features(test_db):
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-agent-upgrade")
        test_db.add(state)
    state.plan = "pro"
    state.status = "active"
    test_db.commit()


def _agent(test_db, **overrides):
    values = {
        "name": "endpoint",
        "agent_id": "agt_upgrade",
        "token_hash": get_password_hash("borgui_agent_secret"),
        "token_prefix": "borgui_agent_secret"[:20],
        "status": "online",
        "agent_version": "0.1.2",
        "capabilities": ["self_upgrade"],
    }
    values.update(overrides)
    agent = AgentMachine(**values)
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


@pytest.fixture
def served_version(monkeypatch):
    monkeypatch.setattr(
        "app.api.managed_machines.agent_package_version", lambda: "0.1.3"
    )


@pytest.fixture
def sent_commands(monkeypatch):
    sent = []

    async def fake_send_command(agent_id, **kwargs):
        sent.append((agent_id, kwargs["command"]))
        return {"success": True}

    monkeypatch.setattr(
        "app.api.managed_machines.agent_connection_manager.send_command",
        fake_send_command,
    )
    return sent


def test_upgrade_queues_a_job_and_marks_the_agent_requested(
    test_client: TestClient, test_db, admin_headers, served_version, sent_commands
):
    agent = _agent(test_db)

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["state"] == "requested"
    job = test_db.query(AgentJob).filter(AgentJob.id == result["job_id"]).one()
    assert job.job_type == "agent_upgrade"
    assert job.status == "completed"
    test_db.refresh(agent)
    assert agent.upgrade_state == "requested"
    assert agent.upgrade_target_version == "0.1.3"
    assert agent.upgrade_requested_at is not None
    assert sent_commands == [(agent.id, "agent.upgrade")]


def test_upgrade_rejects_a_pin_this_server_can_no_longer_serve(
    test_client: TestClient, test_db, admin_headers, served_version
):
    """A pin outlives a server upgrade, and the installer can only install what
    this server serves, so the reinstall could never reach the pinned version."""
    agent = _agent(test_db, desired_agent_version="0.1.1")

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.agents.upgradeTargetUnavailable"
    )
    assert test_db.query(AgentJob).count() == 0


def test_upgrade_targets_a_pinned_version_over_the_served_one(
    test_client: TestClient, test_db, admin_headers, served_version, sent_commands
):
    agent = _agent(test_db, desired_agent_version="0.1.3")

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    test_db.refresh(agent)
    assert agent.upgrade_target_version == "0.1.3"


def test_upgrade_rejects_the_whole_request_when_one_agent_is_unsupported(
    test_client: TestClient, test_db, admin_headers, served_version
):
    ok = _agent(test_db, agent_id="agt_ok")
    bad = _agent(test_db, agent_id="agt_bad", name="old", capabilities=["jobs.poll"])

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [ok.id, bad.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]["key"] == "backend.errors.agents.upgradeUnsupported"
    )
    assert test_db.query(AgentJob).count() == 0


def test_upgrade_rejects_an_unpinned_agent_when_the_server_serves_no_wheel(
    test_client: TestClient, test_db, admin_headers, monkeypatch
):
    monkeypatch.setattr("app.api.managed_machines.agent_package_version", lambda: None)
    agent = _agent(test_db)

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.agents.upgradeTargetUnavailable"
    )
    assert test_db.query(AgentJob).count() == 0


def test_upgrade_rejects_an_unknown_agent(
    test_client: TestClient, test_db, admin_headers, served_version
):
    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [4242]},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert test_db.query(AgentJob).count() == 0


def test_duplicate_ids_create_one_job(
    test_client: TestClient, test_db, admin_headers, served_version, sent_commands
):
    agent = _agent(test_db)

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id, agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert test_db.query(AgentJob).count() == 1
    assert sent_commands == [(agent.id, "agent.upgrade")]


def test_a_second_request_returns_the_in_flight_upgrade(
    test_client: TestClient, test_db, admin_headers, served_version, sent_commands
):
    agent = _agent(test_db)
    body = {"agent_machine_ids": [agent.id]}

    first = test_client.post(
        "/api/managed-machines/agents/upgrade", json=body, headers=admin_headers
    )
    second = test_client.post(
        "/api/managed-machines/agents/upgrade", json=body, headers=admin_headers
    )

    assert first.json()["results"][0]["job_id"] == second.json()["results"][0]["job_id"]
    assert test_db.query(AgentJob).count() == 1
    assert sent_commands == [(agent.id, "agent.upgrade")]


def test_an_offline_agent_fails_its_job_and_reports_failed(
    test_client: TestClient, test_db, admin_headers, served_version, monkeypatch
):
    async def fake_send_command(agent_id, **kwargs):
        raise AgentConnectionUnavailable("offline")

    monkeypatch.setattr(
        "app.api.managed_machines.agent_connection_manager.send_command",
        fake_send_command,
    )
    agent = _agent(test_db)

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["state"] == "failed"
    test_db.refresh(agent)
    assert agent.upgrade_state == "failed"
    assert agent.upgrade_error
    job = test_db.query(AgentJob).one()
    assert job.status == "failed"


def test_upgrade_beyond_the_cap_leaves_the_rest_queued(
    test_client: TestClient,
    test_db,
    admin_headers,
    served_version,
    sent_commands,
    monkeypatch,
):
    monkeypatch.setattr("app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 2)
    agents = [_agent(test_db, agent_id=f"agt_{index}") for index in range(4)]

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id for agent in agents]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [result["state"] for result in results] == [
        "requested",
        "requested",
        "queued",
        "queued",
    ]
    # A queued endpoint has no job yet: the job is created at dispatch.
    assert [result["job_id"] for result in results[2:]] == [None, None]
    assert len(sent_commands) == 2


def test_a_queued_endpoint_is_not_queued_twice(
    test_client: TestClient,
    test_db,
    admin_headers,
    served_version,
    sent_commands,
    monkeypatch,
):
    """Idempotent under a double click, exactly as an in-flight one is."""
    monkeypatch.setattr("app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 0)
    agent = _agent(test_db)
    body = {"agent_machine_ids": [agent.id]}

    test_client.post(
        "/api/managed-machines/agents/upgrade", json=body, headers=admin_headers
    )
    response = test_client.post(
        "/api/managed-machines/agents/upgrade", json=body, headers=admin_headers
    )

    assert response.json()["results"][0]["state"] == "queued"
    assert test_db.query(AgentJob).count() == 0
    assert sent_commands == []


def test_a_queued_endpoint_does_not_age_towards_the_timeout(
    test_client: TestClient,
    test_db,
    admin_headers,
    served_version,
    sent_commands,
    monkeypatch,
):
    """The reaper times out from upgrade_requested_at, and time spent waiting
    for a wave is not time the endpoint has failed to come back."""
    monkeypatch.setattr("app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", 0)
    agent = _agent(test_db)

    test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [agent.id]},
        headers=admin_headers,
    )

    test_db.refresh(agent)
    assert agent.upgrade_state == "queued"
    assert agent.upgrade_requested_at is None
    assert agent.upgrade_target_version == "0.1.3"


def test_a_rejected_request_queues_nothing(
    test_client: TestClient, test_db, admin_headers, served_version
):
    """Validation still runs over the whole request before anything is written."""
    ok = _agent(test_db, agent_id="agt_ok")
    bad = _agent(test_db, agent_id="agt_bad", name="old", capabilities=["jobs.poll"])

    response = test_client.post(
        "/api/managed-machines/agents/upgrade",
        json={"agent_machine_ids": [ok.id, bad.id]},
        headers=admin_headers,
    )

    assert response.status_code == 422
    test_db.refresh(ok)
    assert ok.upgrade_state is None
