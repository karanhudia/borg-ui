from fastapi.testclient import TestClient

from app.core.security import get_password_hash
from app.database.models import AgentMachine


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
