"""The agent's `repository.diff` job: advertised by the agent, registered
on the server, admitted as read work. The history index executor that
dispatches it is a separate change; until then nothing queues the job."""

import pytest
from fastapi import HTTPException

from agent.borg_ui_agent.repository_ops import (
    REPOSITORY_JOB_KINDS,
    execute_repository_operation_job,
)
from agent.borg_ui_agent.runtime import DEFAULT_CAPABILITIES, get_job_handler
from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Repository
from app.services.job_admission import (
    AGENT_JOB_KIND_OPERATIONS,
    OPERATION_CLASS_REPOSITORY_READ,
    OPERATION_REPOSITORY_DIFF,
    TRANSIENT_READ_OPERATIONS,
    operation_class_for,
)
from app.services.repository_executor import (
    REPOSITORY_OPERATION_CAPABILITIES,
    build_agent_repository_operation_payload,
    queue_agent_repository_operation_job,
)

JOB_KIND = "repository.diff"


@pytest.mark.unit
def test_diff_is_advertised_and_handled_by_the_agent():
    # The server only offers a job kind the agent advertises, and only runs
    # one it has a handler for. Adding either alone is a silent no-op.
    assert JOB_KIND in REPOSITORY_JOB_KINDS
    assert JOB_KIND in DEFAULT_CAPABILITIES
    assert get_job_handler(JOB_KIND) is execute_repository_operation_job


@pytest.mark.unit
def test_diff_is_admitted_and_dispatchable():
    # Missing from AGENT_JOB_KIND_OPERATIONS, admission raises KeyError.
    # Missing from REPOSITORY_OPERATION_CAPABILITIES, the server answers
    # 400 unsupportedJobKind before any agent is asked, which reads as an
    # out-of-date agent even though the agent advertises the capability.
    assert AGENT_JOB_KIND_OPERATIONS[JOB_KIND] == OPERATION_REPOSITORY_DIFF
    assert JOB_KIND in REPOSITORY_OPERATION_CAPABILITIES


@pytest.mark.unit
def test_diff_is_a_read_that_writes_wait_for():
    # A diff opens the repository like a contents listing does and runs for
    # about as long, so a prune must not start beside it, and admission
    # must not wait it out the way it waits out a listing or an info.
    assert operation_class_for(OPERATION_REPOSITORY_DIFF) == (
        OPERATION_CLASS_REPOSITORY_READ
    )
    assert OPERATION_REPOSITORY_DIFF not in TRANSIENT_READ_OPERATIONS


@pytest.mark.unit
def test_diff_payload_carries_the_archive_pair():
    repository = Repository(
        id=7,
        name="Repo",
        path="/repos/diff",
        encryption="none",
        repository_type="local",
        executor_type="agent",
        borg_version=2,
        passphrase="secret",
    )

    payload = build_agent_repository_operation_payload(
        repository,
        JOB_KIND,
        operation={"archive": "aid:b2", "predecessor": "aid:a1"},
    )

    assert payload["job_kind"] == JOB_KIND
    assert payload["repository"] == {"id": 7, "path": "/repos/diff", "borg_version": 2}
    assert payload["operation"] == {"archive": "aid:b2", "predecessor": "aid:a1"}
    assert payload["secrets"] == {"BORG_PASSPHRASE": {"value": "secret"}}


def _agent_repository(db_session, capabilities):
    agent = AgentMachine(
        name="Agent",
        agent_id="agt_diff",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
        capabilities=capabilities,
    )
    repo = Repository(
        name="RepoDiff",
        path="/repos/diff",
        encryption="none",
        repository_type="local",
        executor_type="agent",
    )
    db_session.add_all([agent, repo])
    db_session.flush()
    repo.agent_machine_id = agent.id
    db_session.commit()
    return agent, repo


@pytest.mark.unit
def test_diff_queues_only_for_an_agent_that_advertises_it(db_session):
    # An agent from before this job kind keeps reporting the capabilities it
    # has; the server refuses the job instead of queueing one the agent
    # would reject as unsupported.
    agent, repo = _agent_repository(db_session, ["repository.list_archives"])

    with pytest.raises(HTTPException) as refused:
        queue_agent_repository_operation_job(
            db_session,
            repo,
            job_kind=JOB_KIND,
            operation={"archive": "daily-2", "predecessor": "daily-1"},
        )

    assert refused.value.status_code == 409
    assert refused.value.detail["key"] == "backend.errors.agents.capabilityMissing"
    assert refused.value.detail["params"] == {"capability": JOB_KIND}
    assert db_session.query(AgentJob).count() == 0

    agent.capabilities = ["repository.list_archives", JOB_KIND]
    db_session.commit()

    job = queue_agent_repository_operation_job(
        db_session,
        repo,
        job_kind=JOB_KIND,
        operation={"archive": "daily-2", "predecessor": "daily-1"},
    )

    assert job.status == "queued"
    assert job.agent_machine_id == agent.id
    assert job.payload["job_kind"] == JOB_KIND
    assert job.payload["operation"] == {
        "archive": "daily-2",
        "predecessor": "daily-1",
    }
