from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.core.agent_constants import (
    AGENT_FILESYSTEM_BROWSE_MAX_ITEMS,
    AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS,
    DEFAULT_AGENT_POLL_INTERVAL_SECONDS,
)
from app.core.agent_auth import AGENT_AUTH_HEADER
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentJobLog, AgentMachine
from app.services.agent_connection_manager import agent_connection_manager


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


def _agent_headers(agent: AgentMachine) -> dict[str, str]:
    return {AGENT_AUTH_HEADER: "Bearer borgui_agent_secret"}


def _send_session_hello(websocket, agent: AgentMachine) -> None:
    websocket.send_json(
        {
            "type": "hello",
            "agent_id": agent.agent_id,
            "hostname": agent.hostname or "agent.local",
            "agent_version": "0.2.0",
            "borg_versions": [],
            "capabilities": ["session.commands", "filesystem.browse"],
            "running_job_ids": [],
        }
    )
    assert websocket.receive_json()["type"] == "hello_ack"


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
    assert calls == [
        (agent.id, "/home/pi", True, AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS)
    ]


def test_agent_filesystem_browse_endpoint_waits_longer_than_default_agent_poll_interval(
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
        f"/api/managed-machines/agents/{agent.id}/filesystem/browse?path=/home/pi",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert calls[0][3] > DEFAULT_AGENT_POLL_INTERVAL_SECONDS


def test_agent_filesystem_browse_uses_live_session_without_agent_job(
    test_client: TestClient, admin_headers, test_db
):
    agent = _agent(test_db, hostname="nas.local")

    with test_client.websocket_connect(
        "/api/agents/session", headers=_agent_headers(agent)
    ) as websocket:
        _send_session_hello(websocket, agent)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda: test_client.get(
                    f"/api/managed-machines/agents/{agent.id}/filesystem/browse",
                    params={"path": "/home/pi", "include_hidden": "true"},
                    headers=admin_headers,
                )
            )

            command = websocket.receive_json()
            assert command["type"] == "command"
            assert command["command"] == "filesystem.browse"
            assert command["job_id"] is None
            assert command["payload"] == {
                "path": "/home/pi",
                "include_hidden": True,
                "max_items": AGENT_FILESYSTEM_BROWSE_MAX_ITEMS,
            }

            websocket.send_json(
                {
                    "type": "command_result",
                    "command_id": command["command_id"],
                    "result": {
                        "success": True,
                        "current_path": "/home/pi",
                        "parent_path": "/home",
                        "items": [
                            {
                                "name": "docs",
                                "path": "/home/pi/docs",
                                "type": "directory",
                                "size": 0,
                                "modified_at": 1.0,
                                "hidden": False,
                            }
                        ],
                    },
                }
            )
            response = future.result(timeout=2)

    assert response.status_code == 200
    assert response.json()["current_path"] == "/home/pi"
    assert response.json()["items"][0]["name"] == "docs"
    assert any(
        log["message"] == "Command completed"
        and log["command_id"] == command["command_id"]
        for log in agent_connection_manager.list_logs(agent.id)
    )
    assert (
        test_db.query(AgentJob).filter(AgentJob.agent_machine_id == agent.id).count()
        == 0
    )


def test_agent_filesystem_browse_times_out_when_session_does_not_answer(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(test_db, hostname="nas.local")
    monkeypatch.setattr(
        "app.api.managed_machines.AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS",
        0.05,
    )

    with test_client.websocket_connect(
        "/api/agents/session", headers=_agent_headers(agent)
    ) as websocket:
        _send_session_hello(websocket, agent)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda: test_client.get(
                    f"/api/managed-machines/agents/{agent.id}/filesystem/browse",
                    params={"path": "/slow"},
                    headers=admin_headers,
                )
            )

            assert websocket.receive_json()["command"] == "filesystem.browse"
            response = future.result(timeout=2)

    assert response.status_code == 504
    assert (
        response.json()["detail"]["key"]
        == "backend.errors.agents.filesystemBrowseTimeout"
    )


def test_agent_filesystem_browse_truncates_oversized_session_result(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(test_db, hostname="nas.local")
    monkeypatch.setattr("app.core.agent_constants.AGENT_FILESYSTEM_BROWSE_MAX_ITEMS", 2)
    monkeypatch.setattr(
        "app.services.agent_filesystem_service.AGENT_FILESYSTEM_BROWSE_MAX_ITEMS", 2
    )

    with test_client.websocket_connect(
        "/api/agents/session", headers=_agent_headers(agent)
    ) as websocket:
        _send_session_hello(websocket, agent)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda: test_client.get(
                    f"/api/managed-machines/agents/{agent.id}/filesystem/browse",
                    params={"path": "/many"},
                    headers=admin_headers,
                )
            )

            command = websocket.receive_json()
            websocket.send_json(
                {
                    "type": "command_result",
                    "command_id": command["command_id"],
                    "result": {
                        "success": True,
                        "current_path": "/many",
                        "parent_path": "/",
                        "items": [
                            {
                                "name": "a",
                                "path": "/many/a",
                                "type": "file",
                                "size": 1,
                                "modified_at": 1.0,
                                "hidden": False,
                            },
                            {
                                "name": "b",
                                "path": "/many/b",
                                "type": "file",
                                "size": 1,
                                "modified_at": 1.0,
                                "hidden": False,
                            },
                            {
                                "name": "c",
                                "path": "/many/c",
                                "type": "file",
                                "size": 1,
                                "modified_at": 1.0,
                                "hidden": False,
                            },
                        ],
                    },
                }
            )
            response = future.result(timeout=2)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["a", "b"]
    assert response.json()["items_truncated"] is True


def test_list_agent_logs_returns_recent_session_entries(
    test_client: TestClient, admin_headers, test_db
):
    agent = _agent(test_db, hostname="nas.local")
    agent_connection_manager.append_log(
        agent.id,
        level="info",
        stream="session",
        command_id="cmd-visible",
        message="Agent session connected",
    )

    response = test_client.get(
        f"/api/managed-machines/agents/{agent.id}/logs",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert any(
        log["message"] == "Agent session connected"
        and log["command_id"] == "cmd-visible"
        and log["level"] == "info"
        for log in response.json()
    )


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
