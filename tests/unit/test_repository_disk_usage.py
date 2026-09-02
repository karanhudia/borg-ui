import pytest

from app.core.security import get_password_hash
from app.database.models import AgentJob, AgentMachine, Repository
from agent.borg_ui_agent.repository_ops import (
    REPOSITORY_JOB_KINDS,
    RepositoryOperationPayload,
)
from agent.borg_ui_agent.runtime import DEFAULT_CAPABILITIES, JOB_HANDLERS
from app.services.job_admission import (
    AGENT_JOB_KIND_OPERATIONS,
    OPERATION_BACKUP,
    OPERATION_CLASS_REPOSITORY_OBSERVE,
    OPERATION_DISK_USAGE,
    ensure_repository_admission,
    operation_class_for,
)
from app.services.repository_executor import REPOSITORY_OPERATION_CAPABILITIES

JOB_KIND = "repository.disk_usage"


def _payload(repository_path):
    return RepositoryOperationPayload(
        job_kind=JOB_KIND,
        repository_path=repository_path,
        borg_version=2,
        operation={},
    )


@pytest.mark.unit
def test_disk_usage_measures_the_repository_in_bytes():
    # -b so the server formats the number itself rather than parsing a
    # human-readable suffix, and -- so a path starting with a dash cannot be
    # read as an option.
    cmd = _payload("/srv/borg/repo-example").build_command()
    assert cmd == ["du", "-sb", "--", "/srv/borg/repo-example"]


@pytest.mark.unit
def test_disk_usage_requires_a_repository_path():
    # Without a path du would measure the working directory and return a
    # plausible but wrong number.
    with pytest.raises(ValueError):
        _payload("").build_command()


@pytest.mark.unit
def test_disk_usage_is_advertised_and_handled_by_the_agent():
    # The server only offers a job kind the agent advertises, and only runs
    # one it has a handler for. Adding either alone is a silent no-op.
    assert JOB_KIND in REPOSITORY_JOB_KINDS
    assert JOB_KIND in DEFAULT_CAPABILITIES
    assert JOB_KIND in JOB_HANDLERS


@pytest.mark.unit
def test_disk_usage_is_admitted_and_dispatchable():
    # Missing from AGENT_JOB_KIND_OPERATIONS, admission raises KeyError.
    # Missing from REPOSITORY_OPERATION_CAPABILITIES, the server answers
    # 400 unsupportedJobKind before any agent is asked -- which reads as an
    # out-of-date agent even though the agent advertises the capability.
    assert AGENT_JOB_KIND_OPERATIONS[JOB_KIND] == OPERATION_DISK_USAGE
    assert JOB_KIND in REPOSITORY_OPERATION_CAPABILITIES


@pytest.mark.unit
def test_disk_usage_is_an_observation():
    # du stats the repository directory and never opens the repository, so it
    # holds no borg lock. It is not a plain read either: a read still has to
    # yield to a write, and there is nothing for this to yield to.
    assert (
        operation_class_for(OPERATION_DISK_USAGE)
        == OPERATION_CLASS_REPOSITORY_OBSERVE
    )


@pytest.mark.unit
def test_backup_can_queue_while_disk_usage_is_active(db_session):
    # A requested write conflicts with ANY active work, so before disk usage
    # became an observation an in-flight size check refused the backup behind
    # it with repositoryOperationActive. The stats refresh runs on a timer, so
    # that collision would land on scheduled backups at random.
    agent = AgentMachine(
        name="Agent",
        agent_id="agt_disk_usage",
        token_hash=get_password_hash("agent-secret"),
        token_prefix="agent-secret",
        status="online",
    )
    repo = Repository(
        name="RepoDiskUsage",
        path="/repos/disk-usage",
        encryption="none",
        repository_type="local",
        executor_type="agent",
    )
    db_session.add_all([agent, repo])
    db_session.flush()
    repo.agent_machine_id = agent.id
    db_session.add(
        AgentJob(
            agent_machine_id=agent.id,
            job_type="repository",
            status="queued",
            payload={
                "schema_version": 1,
                "job_kind": JOB_KIND,
                "repository": {"id": repo.id, "path": repo.path},
            },
        )
    )
    db_session.commit()

    # No exception: the backup is admitted.
    ensure_repository_admission(db_session, repo, OPERATION_BACKUP)
