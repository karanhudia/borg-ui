from app.database.models import AgentMachine


def test_agent_machine_has_upgrade_tracking_columns(test_db):
    agent = AgentMachine(
        name="node-1",
        agent_id="agt_test_upgrade_columns",
        token_hash="x",
        token_prefix="agt_test",
        status="online",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    assert agent.desired_agent_version is None
    assert agent.desired_borg_version is None
    assert agent.upgrade_state is None
    assert agent.upgrade_requested_at is None
    assert agent.upgrade_target_version is None
    assert agent.upgrade_error is None

    agent.desired_agent_version = "0.1.2"
    agent.desired_borg_version = "2"
    test_db.commit()
    test_db.refresh(agent)
    assert agent.desired_agent_version == "0.1.2"
    assert agent.desired_borg_version == "2"
