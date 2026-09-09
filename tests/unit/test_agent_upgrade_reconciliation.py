"""The agent is killed by the thing it is reporting on, so the server owns the
outcome: success on re-entry with the target version, failure by timeout."""

from datetime import datetime, timedelta, timezone

from app.api.agents import resolve_agent_upgrade
from app.core.security import get_password_hash
from app.database.models import AgentMachine
from app.services.agent_job_reaper import reap_stale_agent_upgrades


def _requested(test_db, *, reported, requested_at):
    agent = AgentMachine(
        name="endpoint",
        agent_id="agt_recon",
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        agent_version=reported,
        upgrade_state="requested",
        upgrade_requested_at=requested_at,
        upgrade_target_version="0.1.3",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)
    return agent


def test_re_registering_on_the_target_version_clears_the_upgrade(test_db):
    agent = _requested(
        test_db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )
    agent.agent_version = "0.1.3"

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "idle"
    assert agent.upgrade_error is None
    assert agent.upgrade_requested_at is None


def test_re_registering_on_the_old_version_leaves_it_requested(test_db):
    agent = _requested(
        test_db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )

    resolve_agent_upgrade(agent)

    # The reinstall may still be mid flight. Only the timeout resolves it.
    assert agent.upgrade_state == "requested"


def test_an_idle_agent_is_untouched(test_db):
    agent = _requested(test_db, reported="0.1.3", requested_at=None)
    agent.upgrade_state = None

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state is None


def test_the_reaper_fails_a_stale_upgrade(test_db):
    agent = _requested(
        test_db,
        reported="0.1.2",
        requested_at=datetime.now(timezone.utc) - timedelta(seconds=1200),
    )

    assert reap_stale_agent_upgrades(test_db) == 1

    test_db.refresh(agent)
    assert agent.upgrade_state == "failed"
    assert agent.upgrade_error


def test_the_reaper_leaves_a_fresh_upgrade_alone(test_db):
    agent = _requested(
        test_db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )

    assert reap_stale_agent_upgrades(test_db) == 0

    test_db.refresh(agent)
    assert agent.upgrade_state == "requested"


def test_re_registering_on_the_target_version_clears_a_failed_upgrade(test_db):
    """The acknowledgement can be lost to the restart it announces, and the
    timeout is a guess, so the version the endpoint reports outranks both."""
    agent = _requested(
        test_db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )
    agent.upgrade_state = "failed"
    agent.upgrade_error = "The endpoint did not come back in time."
    agent.agent_version = "0.1.3"

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "idle"
    assert agent.upgrade_error is None


def test_a_failed_upgrade_on_the_old_version_stays_failed(test_db):
    agent = _requested(
        test_db, reported="0.1.2", requested_at=datetime.now(timezone.utc)
    )
    agent.upgrade_state = "failed"

    resolve_agent_upgrade(agent)

    assert agent.upgrade_state == "failed"


def test_the_reaper_loses_the_race_to_a_concurrent_success(test_db):
    """The endpoint can re-register between the reaper's read and its write.
    The conditional update makes the reaper lose that race rather than
    overwrite a resolved upgrade with a failure."""
    agent = _requested(
        test_db,
        reported="0.1.2",
        requested_at=datetime.now(timezone.utc) - timedelta(seconds=1200),
    )

    # Simulate the concurrent re-register landing after the reaper's read: the
    # row is already idle by the time the conditional update runs.
    test_db.query(AgentMachine).filter(AgentMachine.id == agent.id).update(
        {AgentMachine.upgrade_state: "idle"}, synchronize_session=False
    )
    test_db.commit()

    assert reap_stale_agent_upgrades(test_db) == 0

    test_db.expire_all()
    refreshed = test_db.query(AgentMachine).filter(AgentMachine.id == agent.id).one()
    assert refreshed.upgrade_state == "idle"
    assert refreshed.upgrade_error is None
