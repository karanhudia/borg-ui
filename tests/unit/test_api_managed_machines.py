from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.core.agent_constants import (
    AGENT_FILESYSTEM_BROWSE_MAX_ITEMS,
    AGENT_FILESYSTEM_BROWSE_TIMEOUT_SECONDS,
    DEFAULT_AGENT_POLL_INTERVAL_SECONDS,
)
from app.core.agent_auth import AGENT_AUTH_HEADER
from app.core.security import get_password_hash
from app.database.models import (
    AgentEnrollmentToken,
    AgentJob,
    AgentJobLog,
    AgentMachine,
    LicensingState,
    SystemSettings,
)
from app.services.agent_connection_manager import (
    AgentCommandTimeout,
    AgentConnectionUnavailable,
    agent_connection_manager,
)


def _set_plan(test_db, plan: str) -> None:
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-managed-machines")
        test_db.add(state)
    state.plan = plan
    state.status = "active"
    test_db.commit()


def _set_log_save_policy(test_db, policy: str) -> None:
    settings = test_db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        test_db.add(settings)
    settings.log_save_policy = policy
    test_db.flush()


@pytest.fixture(autouse=True)
def _enable_paid_managed_agent_features(test_db):
    _set_plan(test_db, "pro")


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


def test_managed_machine_admin_list_api_remains_readable_without_pro_plan(
    test_client: TestClient, admin_headers, test_db
):
    agent = _agent(test_db, name="Edge Pi", hostname="edge-pi.local")
    job = _agent_job(test_db, agent)
    token = AgentEnrollmentToken(
        name="existing token",
        token_hash=get_password_hash("borgui_enroll_existing"),
        token_prefix="borgui_enroll_existing"[:20],
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(token)
    test_db.commit()
    _set_plan(test_db, "community")

    agents_response = test_client.get(
        "/api/managed-machines/agents", headers=admin_headers
    )
    tokens_response = test_client.get(
        "/api/managed-machines/enrollment-tokens", headers=admin_headers
    )
    jobs_response = test_client.get(
        "/api/managed-machines/agent-jobs", headers=admin_headers
    )

    assert agents_response.status_code == 200
    assert agents_response.json()[0]["id"] == agent.id
    assert agents_response.json()[0]["hostname"] == "edge-pi.local"
    assert tokens_response.status_code == 200
    assert tokens_response.json()[0]["id"] == token.id
    assert jobs_response.status_code == 200
    assert jobs_response.json()[0]["id"] == job.id


def test_managed_machine_admin_write_api_requires_pro_plan(
    test_client: TestClient, admin_headers, test_db
):
    _set_plan(test_db, "community")

    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        json={"name": "pi setup", "expires_in_days": 7},
        headers=admin_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["feature"] == "managed_agents"


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


def test_list_agents_reports_active_session_as_online(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(test_db, status="offline")
    monkeypatch.setattr(
        agent_connection_manager,
        "is_connected",
        lambda agent_machine_id: agent_machine_id == agent.id,
    )

    response = test_client.get("/api/managed-machines/agents", headers=admin_headers)

    assert response.status_code == 200
    listed = response.json()
    assert listed[0]["id"] == agent.id
    assert listed[0]["status"] == "online"
    test_db.refresh(agent)
    assert agent.status == "online"


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


def test_agent_scripts_lists_published_scripts(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(test_db, agent_id="agt_scripts", capabilities=["script.run"])

    async def fake_send_command(agent_machine_id, *, command, **kwargs):
        assert command == "agent.list_scripts"
        return {
            "scripts": [
                {"name": "pre-db-dump.sh", "description": "Dump DB"},
                {"name": "post-notify.sh"},
                {"bad": "no name"},
            ]
        }

    monkeypatch.setattr(agent_connection_manager, "send_command", fake_send_command)

    response = test_client.get(
        f"/api/managed-machines/agents/{agent.id}/scripts", headers=admin_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent_online"] is True
    assert data["scripts"] == [
        {"name": "pre-db-dump.sh", "description": "Dump DB"},
        {"name": "post-notify.sh"},
    ]


def test_agent_scripts_returns_empty_when_offline(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(test_db, agent_id="agt_offline", capabilities=["script.run"])

    async def fake_send_command(*args, **kwargs):
        raise AgentConnectionUnavailable("offline")

    monkeypatch.setattr(agent_connection_manager, "send_command", fake_send_command)

    response = test_client.get(
        f"/api/managed-machines/agents/{agent.id}/scripts", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {"scripts": [], "agent_online": False}


def test_agent_diagnostics_uses_live_session_without_agent_job(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    seen_commands = []
    agent = _agent(
        test_db,
        hostname="nas.local",
        agent_id="agt_diagnostics",
        agent_version="0.4.0",
        borg_versions=[{"major": 1, "version": "1.2.8", "path": "/usr/bin/borg"}],
        last_seen_at=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
        capabilities=["session.commands", "diagnostics.run"],
    )

    async def fake_send_command(
        agent_machine_id,
        *,
        command,
        payload,
        timeout_seconds,
        job_id=None,
        wait_for_result=True,
    ):
        seen_commands.append(
            {
                "agent_machine_id": agent_machine_id,
                "command": command,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "job_id": job_id,
                "wait_for_result": wait_for_result,
            }
        )
        return {
            "success": True,
            "session": {"status": "success", "elapsed_ms": 12},
        }

    monkeypatch.setattr(agent_connection_manager, "send_command", fake_send_command)

    response = test_client.post(
        f"/api/managed-machines/agents/{agent.id}/diagnostics",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == {
        "id": agent.id,
        "name": "Agent",
        "agent_id": "agt_diagnostics",
        "hostname": "nas.local",
        "status": "online",
        "last_seen_at": data["agent"]["last_seen_at"],
        "agent_version": "0.4.0",
        "borg_versions": [{"major": 1, "version": "1.2.8", "path": "/usr/bin/borg"}],
        "capabilities": ["session.commands", "diagnostics.run"],
        "last_error": None,
    }
    assert data["agent"]["last_seen_at"] == "2026-06-03T14:00:00+00:00"
    assert data["session"] == {"status": "success", "elapsed_ms": 12}
    assert data["tcp"] is None
    assert seen_commands == [
        {
            "agent_machine_id": agent.id,
            "command": "diagnostics.run",
            "payload": {},
            "timeout_seconds": 5.0,
            "job_id": None,
            "wait_for_result": True,
        }
    ]
    assert (
        test_db.query(AgentJob).filter(AgentJob.agent_machine_id == agent.id).count()
        == 0
    )


def test_agent_diagnostics_returns_failed_tcp_result(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    seen_payloads = []
    agent = _agent(
        test_db,
        hostname="nas.local",
        agent_id="agt_diagnostics_tcp",
        capabilities=["session.commands", "diagnostics.run"],
    )

    async def fake_send_command(
        agent_machine_id,
        *,
        command,
        payload,
        timeout_seconds,
        job_id=None,
        wait_for_result=True,
    ):
        seen_payloads.append(payload)
        return {
            "success": True,
            "session": {"status": "success", "elapsed_ms": 10},
            "tcp": {
                "target": {
                    "host": "postgres.internal",
                    "port": 5432,
                    "timeout_seconds": 3.0,
                },
                "status": "failed",
                "elapsed_ms": 4,
                "error": "connection_refused",
                "message": "Connection refused",
            },
        }

    monkeypatch.setattr(agent_connection_manager, "send_command", fake_send_command)

    response = test_client.post(
        f"/api/managed-machines/agents/{agent.id}/diagnostics",
        json={
            "target": {
                "host": "postgres.internal",
                "port": 5432,
                "timeout_seconds": 3,
            }
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session"]["status"] == "success"
    assert seen_payloads == [
        {
            "target": {
                "host": "postgres.internal",
                "port": 5432,
                "timeout_seconds": 3.0,
            }
        }
    ]
    assert data["tcp"] == {
        "target": {
            "host": "postgres.internal",
            "port": 5432,
            "timeout_seconds": 3.0,
        },
        "status": "failed",
        "elapsed_ms": 4,
        "error": "connection_refused",
        "message": "Connection refused",
    }


def test_agent_diagnostics_reports_offline_agent(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(
        test_db,
        hostname="nas.local",
        agent_id="agt_diagnostics_offline",
        status="offline",
        capabilities=["session.commands", "diagnostics.run"],
    )

    async def fake_send_command(*args, **kwargs):
        raise AgentConnectionUnavailable("Agent does not have an active session")

    monkeypatch.setattr(agent_connection_manager, "send_command", fake_send_command)

    response = test_client.post(
        f"/api/managed-machines/agents/{agent.id}/diagnostics",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["agent"]["status"] == "offline"
    assert data["session"] == {
        "status": "offline",
        "elapsed_ms": None,
        "error": "agent_offline",
        "message": "Agent does not have an active session",
    }
    assert data["tcp"] is None


def test_agent_diagnostics_reports_session_timeout(
    test_client: TestClient, admin_headers, test_db, monkeypatch
):
    agent = _agent(
        test_db,
        hostname="nas.local",
        agent_id="agt_diagnostics_timeout",
        capabilities=["session.commands", "diagnostics.run"],
    )

    async def fake_send_command(*args, **kwargs):
        raise AgentCommandTimeout("diagnostics.run")

    monkeypatch.setattr(agent_connection_manager, "send_command", fake_send_command)

    response = test_client.post(
        f"/api/managed-machines/agents/{agent.id}/diagnostics",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["session"] == {
        "status": "timeout",
        "elapsed_ms": None,
        "error": "agent_timeout",
        "message": "Agent did not return diagnostics before the timeout",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"target": {"host": "", "port": 5432, "timeout_seconds": 3}},
        {"target": {"host": "bad host", "port": 5432, "timeout_seconds": 3}},
        {"target": {"host": "bad-.internal", "port": 5432, "timeout_seconds": 3}},
        {"target": {"host": "postgres.internal", "port": 0, "timeout_seconds": 3}},
        {"target": {"host": "postgres.internal", "port": 65536, "timeout_seconds": 3}},
        {"target": {"host": "postgres.internal", "port": 5432, "timeout_seconds": 0}},
    ],
)
def test_agent_diagnostics_rejects_invalid_tcp_target(
    test_client: TestClient, admin_headers, test_db, payload
):
    agent = _agent(
        test_db,
        hostname="nas.local",
        agent_id="agt_diagnostics_invalid",
        capabilities=["session.commands", "diagnostics.run"],
    )

    response = test_client.post(
        f"/api/managed-machines/agents/{agent.id}/diagnostics",
        json=payload,
        headers=admin_headers,
    )

    assert response.status_code == 422


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
    job.status = "failed"
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


def test_agent_job_logs_apply_log_save_policy(
    test_client: TestClient, admin_headers, test_db
):
    _set_log_save_policy(test_db, "failed_only")
    agent = _agent(test_db)
    job = _agent_job(test_db, agent)
    job.status = "completed"
    now = datetime.now(timezone.utc)
    test_db.add(
        AgentJobLog(
            agent_job_id=job.id,
            sequence=1,
            stream="stdout",
            message="successful agent log",
            created_at=now,
            received_at=now,
        )
    )
    test_db.commit()

    response = test_client.get(
        f"/api/managed-machines/agent-jobs/{job.id}/logs",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == []


def test_agent_job_logs_keep_running_logs_visible(
    test_client: TestClient, admin_headers, test_db
):
    _set_log_save_policy(test_db, "failed_only")
    agent = _agent(test_db)
    job = _agent_job(test_db, agent)
    job.status = "running"
    now = datetime.now(timezone.utc)
    test_db.add(
        AgentJobLog(
            agent_job_id=job.id,
            sequence=1,
            stream="stdout",
            message="live agent log",
            created_at=now,
            received_at=now,
        )
    )
    test_db.commit()

    response = test_client.get(
        f"/api/managed-machines/agent-jobs/{job.id}/logs",
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()[0]["message"] == "live agent log"
