import pytest

from agent.borg_ui_agent.repository_ops import (
    REPOSITORY_JOB_KINDS,
    RepositoryOperationPayload,
)
from agent.borg_ui_agent.runtime import DEFAULT_CAPABILITIES, JOB_HANDLERS
from app.services.job_admission import (
    AGENT_JOB_KIND_OPERATIONS,
    OPERATION_CLASS_REPOSITORY_READ,
    OPERATION_DISK_USAGE,
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
def test_disk_usage_is_a_read_operation():
    # du opens nothing in the repository and takes no lock. Classed as a
    # write it would block a backup queued behind it with
    # repositoryOperationActive.
    assert operation_class_for(OPERATION_DISK_USAGE) == OPERATION_CLASS_REPOSITORY_READ
