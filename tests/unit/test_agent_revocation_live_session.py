"""A revoked or deleted agent stays out, also while a session it opened
before the revocation is still connected.

The session authenticates once, at connect; afterwards its heartbeat used to
write `status = "online"` unconditionally, which undid the revocation and
made the agent's token valid again.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.agents import (
    AgentHeartbeatRequest,
    AgentSessionRevoked,
    _handle_agent_session_message,
    heartbeat,
)
from app.core.agent_auth import mark_agent_online, resolve_agent_from_token
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine

RAW_TOKEN = "borgui_agent_" + "r" * 43


def _create_agent(test_db, *, status="online") -> AgentMachine:
    agent = AgentMachine(
        name="Revocation Agent",
        agent_id="agt_revocation",
        token_hash=get_password_hash(RAW_TOKEN),
        token_prefix=RAW_TOKEN[:20],
        hostname="before.local",
        status=status,
        capabilities=["session.commands", "backup.create"],
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


def _set_status(test_db, agent: AgentMachine, value: str) -> None:
    """Commit a status change the way another request would: a plain UPDATE
    that leaves the caller's loaded object alone until it is expired."""
    test_db.query(AgentMachine).filter(AgentMachine.id == agent.id).update(
        {AgentMachine.status: value}, synchronize_session=False
    )
    test_db.commit()


def _status(test_db, agent: AgentMachine) -> str:
    test_db.expire_all()
    return test_db.get(AgentMachine, agent.id).status


def _headers() -> dict[str, str]:
    return {"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"}


def _hello() -> dict:
    return {
        "type": "hello",
        "agent_id": "agt_revocation",
        "hostname": "session.local",
        "agent_version": "0.2.0",
        "borg_versions": [],
        "capabilities": ["session.commands", "backup.create"],
        "running_job_ids": [],
    }


def _queue_undelivered_job(test_db, agent: AgentMachine) -> AgentJob:
    """A job queued long enough ago that the next heartbeat would send it."""
    queued_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    job = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="queued",
        payload={
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {"id": 7},
        },
        created_at=queued_at,
        updated_at=queued_at,
    )
    test_db.add(job)
    test_db.commit()
    test_db.refresh(job)
    return job


@pytest.mark.unit
@pytest.mark.parametrize("inactive", ["revoked", "disabled", "deleted"])
def test_mark_agent_online_leaves_an_inactive_agent_alone(test_db, inactive):
    agent = _create_agent(test_db, status=inactive)

    assert mark_agent_online(test_db, agent.id, agent.created_at) is False
    test_db.commit()

    assert _status(test_db, agent) == inactive


@pytest.mark.unit
def test_mark_agent_online_marks_an_offline_agent(test_db):
    agent = _create_agent(test_db, status="offline")

    assert mark_agent_online(test_db, agent.id, agent.created_at) is True
    test_db.commit()

    assert _status(test_db, agent) == "online"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("inactive", ["revoked", "deleted"])
async def test_session_heartbeat_does_not_undo_a_revocation(test_db, inactive):
    agent = _create_agent(test_db)
    _set_status(test_db, agent, inactive)

    with pytest.raises(AgentSessionRevoked):
        await _handle_agent_session_message(test_db, agent.id, {"type": "heartbeat"})

    assert _status(test_db, agent) == inactive
    with pytest.raises(HTTPException) as exc_info:
        resolve_agent_from_token(RAW_TOKEN, test_db)
    assert exc_info.value.status_code == 403


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_heartbeat_keeps_an_active_agent_online(test_db):
    agent = _create_agent(test_db, status="offline")

    await _handle_agent_session_message(test_db, agent.id, {"type": "heartbeat"})

    test_db.expire_all()
    current = test_db.get(AgentMachine, agent.id)
    assert current.status == "online"
    assert current.last_seen_at is not None


@pytest.mark.unit
def test_open_session_is_closed_when_the_agent_is_revoked(
    test_client: TestClient, test_db
):
    agent = _create_agent(test_db, status="offline")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with test_client.websocket_connect(
            "/api/agents/session", headers=_headers()
        ) as websocket:
            websocket.send_json(_hello())
            assert websocket.receive_json()["type"] == "hello_ack"
            assert _status(test_db, agent) == "online"

            # Without the fix the heartbeat hands this job to the revoked agent
            # (and the receive below returns it) instead of closing the session.
            job = _queue_undelivered_job(test_db, agent)
            _set_status(test_db, agent, "revoked")
            websocket.send_json({"type": "heartbeat"})
            websocket.receive_json()

    assert exc_info.value.code == 1008
    assert _status(test_db, agent) == "revoked"
    test_db.expire_all()
    assert test_db.get(AgentJob, job.id).status == "queued"


@pytest.mark.unit
def test_revocation_during_the_hello_wait_wins(test_client: TestClient, test_db):
    agent = _create_agent(test_db, status="offline")

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with test_client.websocket_connect(
            "/api/agents/session", headers=_headers()
        ) as websocket:
            # The token was accepted at connect; the revocation lands before
            # the hello.
            _set_status(test_db, agent, "revoked")
            websocket.send_json(_hello())
            websocket.receive_json()

    assert exc_info.value.code == 1008
    assert _status(test_db, agent) == "revoked"


@pytest.mark.unit
def test_rest_heartbeat_authenticated_before_a_revocation_is_refused(test_db):
    agent = _create_agent(test_db)
    # Resolved by the dependency, then revoked before the handler writes
    current_agent = resolve_agent_from_token(RAW_TOKEN, test_db)
    _set_status(test_db, agent, "revoked")

    with pytest.raises(HTTPException) as exc_info:
        heartbeat(
            AgentHeartbeatRequest(agent_id="agt_revocation", hostname="after.local"),
            current_agent=current_agent,
            db=test_db,
        )

    assert exc_info.value.status_code == 403
    test_db.expire_all()
    current = test_db.get(AgentMachine, agent.id)
    assert current.status == "revoked"
    assert current.hostname == "before.local"


@pytest.mark.unit
def test_any_session_message_after_a_revocation_is_refused(
    test_client: TestClient, test_db
):
    """A revoked agent that stops sending heartbeats is closed by whatever it
    sends next, before the message is applied."""
    agent = _create_agent(test_db, status="offline")
    claimed_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    claimed = AgentJob(
        agent_machine_id=agent.id,
        job_type="backup",
        status="claimed",
        payload={"schema_version": 1, "job_kind": "backup.create"},
        created_at=claimed_at,
        claimed_at=claimed_at,
        updated_at=claimed_at,
    )
    test_db.add(claimed)
    test_db.commit()

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with test_client.websocket_connect(
            "/api/agents/session", headers=_headers()
        ) as websocket:
            hello = _hello()
            hello["running_job_ids"] = [claimed.id]
            websocket.send_json(hello)
            assert websocket.receive_json()["type"] == "hello_ack"

            # Without the per-message check the start report is applied, and
            # without any check the heartbeat hands this job out.
            queued = _queue_undelivered_job(test_db, agent)
            _set_status(test_db, agent, "revoked")
            websocket.send_json({"type": "job_started", "job_id": claimed.id})
            websocket.send_json({"type": "heartbeat"})
            websocket.receive_json()

    assert exc_info.value.code == 1008
    test_db.expire_all()
    assert test_db.get(AgentJob, claimed.id).status == "claimed"
    assert test_db.get(AgentJob, claimed.id).started_at is None
    assert test_db.get(AgentJob, queued.id).status == "queued"
    assert _status(test_db, agent) == "revoked"


@pytest.mark.unit
def test_agent_list_does_not_undo_a_revocation(
    test_client: TestClient, test_db, admin_headers, monkeypatch
):
    """The list marks a connected offline agent online; a revocation that
    lands after the list was read must stand."""
    agent = _create_agent(test_db, status="offline")

    def connected_then_revoked(agent_machine_id):
        _set_status(test_db, agent, "revoked")
        return True

    monkeypatch.setattr(
        "app.api.managed_machines.agent_connection_manager.is_connected",
        connected_then_revoked,
    )
    response = test_client.get("/api/managed-machines/agents", headers=admin_headers)

    assert response.status_code == 200
    listed = {item["agent_id"]: item for item in response.json()}
    assert listed["agt_revocation"]["status"] == "revoked"
    assert _status(test_db, agent) == "revoked"
