"""The agent's Borg 1 command lines carry --lock-wait: Borg 1.4 ignores
BORG_LOCK_WAIT and would give up on a held lock after 1 second (#1216)."""

import pytest

from agent.borg_ui_agent.backup import BackupCreatePayload
from agent.borg_ui_agent.repository_ops import RepositoryOperationPayload

pytestmark = pytest.mark.unit


def test_borg1_repository_operation_waits_for_the_lock(monkeypatch):
    monkeypatch.delenv("BORG_LOCK_WAIT", raising=False)
    payload = RepositoryOperationPayload(
        job_kind="repository.info", repository_path="/repo"
    )

    assert payload.build_command()[:4] == ["borg", "--lock-wait", "180", "info"]


def test_the_server_value_wins_over_the_agent_default(monkeypatch):
    monkeypatch.delenv("BORG_LOCK_WAIT", raising=False)
    payload = BackupCreatePayload(
        repository_path="/repo",
        archive_name="a",
        source_paths=["/src"],
        environment={"BORG_LOCK_WAIT": "30"},
    )

    assert payload.build_command()[:4] == ["borg", "--lock-wait", "30", "create"]


def test_borg2_keeps_the_environment_variable(monkeypatch):
    payload = RepositoryOperationPayload(
        job_kind="repository.info", repository_path="/repo", borg_version=2
    )

    assert "--lock-wait" not in payload.build_command()
