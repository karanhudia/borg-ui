"""An endpoint runs at least the server's own Borg 2 (#1306).

Borg 2 betas change the repository format and the command line at short
intervals, so a Borg 2 job is refused before it is queued for an endpoint
whose Borg 2 is older than the one the server ships (its pin), or that
reports none. The check sits where every repository job for an agent is
validated, so no job kind can pass it by.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.borg_binaries import CURRENT_VERSIONS
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, LicensingState, Repository
from app.services.repository_executor import (
    BORGLESS_REPOSITORY_JOB_KINDS,
    REPOSITORY_OPERATION_CAPABILITIES,
    queue_agent_backup_job,
    queue_agent_repository_operation_job,
    validate_agent_backup_repository,
)

SERVER_BORG2 = CURRENT_VERSIONS["2"]
OLDER_BORG2 = "2.0.0b24"


def _agent(db, *borg_versions, agent_id="agt_borg2_minimum"):
    agent = AgentMachine(
        name="Endpoint",
        agent_id=agent_id,
        token_hash=get_password_hash("borgui_agent_secret"),
        token_prefix="borgui_agent_secret"[:20],
        status="online",
        capabilities=sorted(REPOSITORY_OPERATION_CAPABILITIES | {"backup.create"}),
        borg_versions=list(borg_versions),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _repository(db, agent, borg_version=2, name="Endpoint repository"):
    repository = Repository(
        name=name,
        path="/agent/repo",
        encryption="repokey-aes-ocb",
        compression="lz4",
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=agent.id,
        repository_type="local",
        borg_version=borg_version,
        source_directories='["/data"]',
    )
    db.add(repository)
    db.commit()
    db.refresh(repository)
    return repository


@pytest.fixture
def pro_plan(test_db):
    """Managed agents are a paid feature."""
    state = LicensingState(instance_id="test-instance-borg2-minimum")
    state.plan = "pro"
    state.status = "active"
    test_db.add(state)
    test_db.commit()


def _borg(major, version):
    return {"major": major, "version": version, "path": f"/usr/local/bin/borg{major}"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "job_kind",
    sorted(REPOSITORY_OPERATION_CAPABILITIES - BORGLESS_REPOSITORY_JOB_KINDS),
)
def test_every_borg2_repository_job_is_refused_on_an_older_borg2(db_session, job_kind):
    agent = _agent(db_session, _borg(1, "1.4.5"), _borg(2, OLDER_BORG2))
    repository = _repository(db_session, agent)

    with pytest.raises(HTTPException) as raised:
        queue_agent_repository_operation_job(db_session, repository, job_kind=job_kind)

    assert raised.value.status_code == 400
    assert raised.value.detail == {
        "key": "backend.errors.repo.agentBorg2TooOld",
        "params": {
            "version": OLDER_BORG2,
            "minimum": SERVER_BORG2,
            "flags": "--reinstall --borg-version both --borg-source server",
        },
    }
    assert db_session.query(AgentJob).count() == 0


@pytest.mark.unit
def test_a_borg2_job_is_refused_on_an_endpoint_without_borg2(db_session):
    agent = _agent(db_session, _borg(1, "1.4.5"))
    repository = _repository(db_session, agent)

    with pytest.raises(HTTPException) as raised:
        queue_agent_repository_operation_job(
            db_session, repository, job_kind="repository.list_archives"
        )

    assert raised.value.detail == {"key": "backend.errors.repo.agentBorg2Unavailable"}


@pytest.mark.unit
@pytest.mark.parametrize("version", [SERVER_BORG2, "2.0.0b26", "2.0.0"])
def test_a_borg2_job_is_queued_on_the_servers_borg2_or_newer(db_session, version):
    agent = _agent(db_session, _borg(2, version))
    repository = _repository(db_session, agent)

    job = queue_agent_repository_operation_job(
        db_session, repository, job_kind="repository.list_archives"
    )

    assert job.status == "queued"


@pytest.mark.unit
@pytest.mark.parametrize("job_kind", sorted(BORGLESS_REPOSITORY_JOB_KINDS))
def test_a_job_that_runs_no_borg_does_not_ask_for_borg2(db_session, job_kind):
    """An rclone copy or a `du` of a Borg 2 repository runs no Borg."""
    agent = _agent(db_session, _borg(2, OLDER_BORG2))
    repository = _repository(db_session, agent)
    operation = (
        {"rclone_config": "[r]\ntype = local\n", "destination": "r:copy"}
        if job_kind == "repository.rclone_sync"
        else None
    )

    job = queue_agent_repository_operation_job(
        db_session, repository, job_kind=job_kind, operation=operation
    )

    assert job.status == "queued"


@pytest.mark.unit
def test_a_borg1_job_ignores_the_endpoints_borg2(db_session):
    agent = _agent(db_session, _borg(1, "1.4.5"), _borg(2, OLDER_BORG2))
    repository = _repository(db_session, agent, borg_version=1)

    job = queue_agent_repository_operation_job(
        db_session, repository, job_kind="repository.list_archives"
    )

    assert job.status == "queued"


@pytest.mark.unit
def test_a_borg2_backup_is_refused_on_an_older_borg2(db_session):
    agent = _agent(db_session, _borg(2, OLDER_BORG2))
    repository = _repository(db_session, agent)

    with pytest.raises(HTTPException) as raised:
        validate_agent_backup_repository(db_session, repository)

    assert raised.value.detail["key"] == "backend.errors.repo.agentBorg2TooOld"
    assert raised.value.detail["params"]["flags"] == (
        "--reinstall --borg-version 2 --borg-source server"
    )

    class _BackupRow:
        id = None

    with pytest.raises(HTTPException):
        queue_agent_backup_job(db_session, _BackupRow(), repository)
    assert db_session.query(AgentJob).count() == 0


@pytest.mark.unit
def test_the_raw_backup_job_route_refuses_an_older_borg2(
    test_client: TestClient, admin_headers, test_db, pro_plan
):
    agent = _agent(test_db, _borg(2, OLDER_BORG2))
    payload = {
        "repository_path": "/backups/laptop",
        "archive_name": "laptop-now",
        "source_paths": ["/home/user/docs"],
    }

    refused = test_client.post(
        f"/api/managed-machines/agents/{agent.id}/backup-jobs",
        json={**payload, "borg_version": 2},
        headers=admin_headers,
    )
    assert refused.status_code == 400
    assert refused.json()["detail"]["key"] == "backend.errors.repo.agentBorg2TooOld"
    assert test_db.query(AgentJob).count() == 0

    with patch(
        "app.api.managed_machines.dispatch_agent_job_best_effort",
        new=AsyncMock(return_value=False),
    ):
        queued = test_client.post(
            f"/api/managed-machines/agents/{agent.id}/backup-jobs",
            json={**payload, "borg_version": 1},
            headers=admin_headers,
        )
    assert queued.status_code == 201


@pytest.mark.unit
def test_the_agent_list_marks_an_older_borg2(
    test_client: TestClient, admin_headers, test_db, pro_plan
):
    _agent(test_db, _borg(2, OLDER_BORG2), agent_id="agt_old")
    _agent(test_db, _borg(2, SERVER_BORG2), agent_id="agt_current")
    _agent(test_db, _borg(1, "1.4.5"), agent_id="agt_borg1")

    response = test_client.get("/api/managed-machines/agents", headers=admin_headers)

    assert response.status_code == 200
    by_id = {agent["agent_id"]: agent for agent in response.json()}
    assert by_id["agt_old"]["borg2_below_minimum"] is True
    assert by_id["agt_current"]["borg2_below_minimum"] is False
    assert by_id["agt_borg1"]["borg2_below_minimum"] is False
    assert {agent["borg2_minimum_version"] for agent in by_id.values()} == {
        SERVER_BORG2
    }


@pytest.mark.unit
def test_the_borg2_binary_counts_where_borg_is_a_borg2_too(db_session):
    """The agent runs `borg2` for a Borg 2 job; a `borg` on PATH that also
    reports major 2 does not stand in for it, whichever comes first."""
    agent = _agent(
        db_session,
        {"major": 2, "version": SERVER_BORG2, "path": "/usr/bin/borg"},
        {"major": 2, "version": OLDER_BORG2, "path": "/usr/local/bin/borg2"},
    )
    repository = _repository(db_session, agent)

    with pytest.raises(HTTPException) as raised:
        queue_agent_repository_operation_job(
            db_session, repository, job_kind="repository.list_archives"
        )
    assert raised.value.detail["params"]["version"] == OLDER_BORG2


@pytest.mark.unit
def test_a_borg_that_is_a_borg2_does_not_count(db_session):
    """Without a `borg2` every Borg 2 job fails on the endpoint ("No such
    file or directory"), whatever version its `borg` reports."""
    agent = _agent(
        db_session, {"major": 2, "version": SERVER_BORG2, "path": "/opt/borg/bin/borg"}
    )
    repository = _repository(db_session, agent)

    with pytest.raises(HTTPException) as raised:
        queue_agent_repository_operation_job(
            db_session, repository, job_kind="repository.list_archives"
        )
    assert raised.value.detail == {"key": "backend.errors.repo.agentBorg2Unavailable"}


@pytest.mark.unit
def test_the_raw_backup_route_checks_the_binary_it_names(
    test_client: TestClient, admin_headers, test_db, pro_plan
):
    agent = _agent(
        test_db,
        {"major": 2, "version": OLDER_BORG2, "path": "/usr/local/bin/borg2"},
        {"major": 2, "version": SERVER_BORG2, "path": "/opt/borg2-new/bin/borg"},
    )
    payload = {
        "repository_path": "/backups/laptop",
        "archive_name": "laptop-now",
        "source_paths": ["/home/user/docs"],
        "borg_version": 2,
    }

    with patch(
        "app.api.managed_machines.dispatch_agent_job_best_effort",
        new=AsyncMock(return_value=False),
    ):
        named = test_client.post(
            f"/api/managed-machines/agents/{agent.id}/backup-jobs",
            json={**payload, "borg_binary": "/opt/borg2-new/bin/borg"},
            headers=admin_headers,
        )
        default = test_client.post(
            f"/api/managed-machines/agents/{agent.id}/backup-jobs",
            json=payload,
            headers=admin_headers,
        )

        unreported = test_client.post(
            f"/api/managed-machines/agents/{agent.id}/backup-jobs",
            json={**payload, "borg_binary": "/srv/tools/borg2-build"},
            headers=admin_headers,
        )

    assert named.status_code == 201
    # a binary the agent did not report has no known version to refuse
    assert unreported.status_code == 201
    assert default.status_code == 400
    assert default.json()["detail"]["key"] == "backend.errors.repo.agentBorg2TooOld"


@pytest.mark.unit
def test_naming_the_default_borg2_still_needs_a_reported_one(db_session):
    """`borg2` named explicitly is the default binary, not an unknown one:
    without a reported Borg 2 it is refused as unavailable."""
    from app.services.repository_executor import require_agent_borg2

    agent = _agent(db_session, _borg(1, "1.4.5"))

    with pytest.raises(HTTPException) as raised:
        require_agent_borg2(agent, "borg2")
    assert raised.value.detail == {"key": "backend.errors.repo.agentBorg2Unavailable"}
    # a binary the agent did not report is not checked
    require_agent_borg2(agent, "/srv/tools/borg2-build")
