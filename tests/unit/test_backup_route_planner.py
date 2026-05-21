from types import SimpleNamespace

import pytest

from app.services.backup_route_planner import plan_repository_route


def repo(**overrides):
    values = {
        "id": 1,
        "name": "Repo",
        "path": "/repo",
        "repository_type": "local",
        "connection_id": None,
        "executor_type": "server",
        "execution_target": "local",
        "agent_machine_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def local_source(*paths):
    return {
        "source_type": "local",
        "source_ssh_connection_id": None,
        "agent_machine_id": None,
        "paths": list(paths) or ["/data"],
    }


def ssh_source(connection_id=1):
    return {
        "source_type": "remote",
        "source_ssh_connection_id": connection_id,
        "agent_machine_id": None,
        "paths": ["/remote"],
    }


def agent_source(agent_machine_id=10):
    return {
        "source_type": "agent",
        "source_ssh_connection_id": None,
        "agent_machine_id": agent_machine_id,
        "paths": ["/agent-data"],
    }


@pytest.mark.parametrize(
    "repository,sources,strategy,executor,agent_machine_id",
    [
        (repo(), [local_source()], "server_direct", "server", None),
        (
            repo(repository_type="ssh", connection_id=2, path="ssh://borg@host/repo"),
            [local_source()],
            "server_direct_borg_ssh",
            "server",
            None,
        ),
        (repo(), [ssh_source(3)], "server_sshfs_pull", "server", None),
        (
            repo(repository_type="ssh", connection_id=3),
            [ssh_source(3)],
            "remote_direct",
            "server",
            None,
        ),
        (
            repo(repository_type="ssh", connection_id=4),
            [ssh_source(3)],
            "server_sshfs_pull_then_borg_ssh",
            "server",
            None,
        ),
        (
            repo(executor_type="agent", execution_target="agent", agent_machine_id=10),
            [agent_source(10)],
            "agent_direct",
            "agent",
            10,
        ),
    ],
)
def test_plan_repository_route_supported_matrix(
    repository, sources, strategy, executor, agent_machine_id
):
    route = plan_repository_route(repository, sources)

    assert route.supported is True
    assert route.strategy == strategy
    assert route.executor == executor
    assert route.agent_machine_id == agent_machine_id
    assert route.reason_key is None


@pytest.mark.parametrize(
    "repository,sources,reason_key",
    [
        (
            repo(
                executor_type="agent",
                execution_target="agent",
                agent_machine_id=10,
                repository_type="ssh",
                connection_id=1,
            ),
            [agent_source(10)],
            "backend.errors.backupPlans.agentRepoSshTargetUnsupported",
        ),
        (
            repo(executor_type="agent", execution_target="agent", agent_machine_id=10),
            [local_source()],
            "backend.errors.backupPlans.serverSourceToAgentRepoUnsupported",
        ),
        (
            repo(executor_type="agent", execution_target="agent", agent_machine_id=10),
            [ssh_source(1)],
            "backend.errors.backupPlans.sshSourceToAgentRepoUnsupported",
        ),
        (
            repo(),
            [agent_source(10)],
            "backend.errors.backupPlans.agentSourceToServerRepoUnsupported",
        ),
        (
            repo(executor_type="agent", execution_target="agent", agent_machine_id=10),
            [agent_source(11)],
            "backend.errors.backupPlans.agentSourceMismatch",
        ),
        (
            repo(executor_type="agent", execution_target="agent", agent_machine_id=10),
            [agent_source(10), local_source()],
            "backend.errors.backupPlans.mixedAgentSourceUnsupported",
        ),
    ],
)
def test_plan_repository_route_unsupported_matrix(repository, sources, reason_key):
    route = plan_repository_route(repository, sources)

    assert route.supported is False
    assert route.strategy is None
    assert route.reason_key == reason_key
    assert route.display_params
