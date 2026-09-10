"""Fleet upgrades are released in waves.

Every upgrading endpoint is briefly offline, so a fleet-wide request is not
dispatched at once: at most AGENT_UPGRADE_CONCURRENCY endpoints are in flight,
and a slot frees when one leaves "requested", by success or by timeout.
"""

from datetime import datetime, timezone

import pytest

from app.core.security import get_password_hash
from app.database.models import AgentMachine
from app.services.agent_connection_manager import AgentConnectionUnavailable
from app.services.agent_upgrades import release_agent_upgrade_waves


def _queued(test_db, name, *, target="0.1.3"):
    """An endpoint accepted into a fleet upgrade but not yet dispatched."""
    agent = AgentMachine(
        name=name,
        agent_id=f"agt_{name}",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        agent_version="0.1.2",
        capabilities=["self_upgrade"],
        upgrade_state="queued",
        upgrade_target_version=target,
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


@pytest.fixture
def sent(monkeypatch):
    calls = []

    async def fake_send_command(agent_id, **kwargs):
        calls.append(agent_id)
        return {"success": True}

    monkeypatch.setattr(
        "app.services.agent_upgrades.agent_connection_manager.send_command",
        fake_send_command,
    )
    return calls


@pytest.fixture
def cap(monkeypatch):
    def _set(value):
        monkeypatch.setattr(
            "app.services.agent_upgrades.AGENT_UPGRADE_CONCURRENCY", value
        )

    return _set


def _state(test_db, agent):
    return (
        test_db.query(AgentMachine)
        .filter(AgentMachine.id == agent.id)
        .one()
        .upgrade_state
    )


async def test_release_dispatches_at_most_the_concurrency_cap(test_db, sent, cap):
    cap(2)
    agents = [_queued(test_db, f"a{index}") for index in range(5)]

    dispatched = await release_agent_upgrade_waves(test_db)

    assert dispatched == 2
    assert len(sent) == 2
    assert [_state(test_db, agent) for agent in agents] == [
        "requested",
        "requested",
        "queued",
        "queued",
        "queued",
    ]


async def test_release_counts_in_flight_endpoints_against_the_cap(test_db, sent, cap):
    """A slot held by an endpoint already upgrading is not handed out twice."""
    cap(2)
    busy = _queued(test_db, "busy")
    busy.upgrade_state = "requested"
    busy.upgrade_requested_at = datetime.now(timezone.utc)
    test_db.commit()
    _queued(test_db, "waiting1")
    _queued(test_db, "waiting2")

    assert await release_agent_upgrade_waves(test_db) == 1
    assert len(sent) == 1


async def test_release_stamps_requested_at_only_on_dispatch(test_db, sent, cap):
    """A queued endpoint must not age towards the reaper's timeout."""
    cap(1)
    first = _queued(test_db, "first")
    waiting = _queued(test_db, "waiting")

    await release_agent_upgrade_waves(test_db)

    rows = {agent.id: agent for agent in test_db.query(AgentMachine).all()}
    assert rows[first.id].upgrade_requested_at is not None
    assert rows[waiting.id].upgrade_requested_at is None


async def test_release_marks_a_failed_dispatch_failed(test_db, monkeypatch, cap):
    """A dispatch that never reached the endpoint frees its slot again."""
    cap(1)

    async def fake_send_command(agent_id, **kwargs):
        raise AgentConnectionUnavailable("offline")

    monkeypatch.setattr(
        "app.services.agent_upgrades.agent_connection_manager.send_command",
        fake_send_command,
    )
    agent = _queued(test_db, "offline")

    await release_agent_upgrade_waves(test_db)

    row = test_db.query(AgentMachine).filter(AgentMachine.id == agent.id).one()
    assert row.upgrade_state == "failed"
    assert row.upgrade_requested_at is None


async def test_release_does_nothing_when_the_cap_is_full(test_db, sent, cap):
    cap(1)
    busy = _queued(test_db, "busy")
    busy.upgrade_state = "requested"
    busy.upgrade_requested_at = datetime.now(timezone.utc)
    test_db.commit()
    _queued(test_db, "waiting")

    assert await release_agent_upgrade_waves(test_db) == 0
    assert sent == []


async def test_reaper_tick_releases_the_next_wave(monkeypatch):
    """A slot freed by a success or a timeout starts the next endpoint with
    nobody watching, so the release runs on every reaper tick."""
    import asyncio

    from app.services import agent_job_reaper

    released = []

    async def fake_release(db):
        released.append(True)
        return 0

    monkeypatch.setattr(
        "app.services.agent_upgrades.release_agent_upgrade_waves", fake_release
    )
    monkeypatch.setattr(agent_job_reaper, "_reap_once", lambda ids=None: 0)

    task = asyncio.create_task(
        agent_job_reaper.start_agent_job_reaper(interval_seconds=0.01)
    )
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert released


async def test_the_whole_wave_is_claimed_before_anything_is_dispatched(
    test_db, monkeypatch, cap
):
    """Slots are accounted for before the first send, so a release that runs
    while this one is dispatching sees the cap as already full."""
    cap(2)
    seen_in_flight = []

    async def fake_send_command(agent_id, **kwargs):
        seen_in_flight.append(
            test_db.query(AgentMachine)
            .filter(AgentMachine.upgrade_state == "requested")
            .count()
        )
        return {"success": True}

    monkeypatch.setattr(
        "app.services.agent_upgrades.agent_connection_manager.send_command",
        fake_send_command,
    )
    for index in range(3):
        _queued(test_db, f"a{index}")

    await release_agent_upgrade_waves(test_db)

    assert seen_in_flight == [2, 2]
