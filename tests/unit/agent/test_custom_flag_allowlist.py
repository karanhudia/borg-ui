"""The agent validates user supplied borg flags itself, whatever the server sent."""

import pytest

from agent.borg_ui_agent.backup import BackupCreatePayload
from agent.borg_ui_agent.repository_ops import RepositoryOperationPayload


def _backup_payload(custom_flags):
    return {
        "job_kind": "backup.create",
        "repository": {"path": "/backup/repo", "borg_version": 1},
        "backup": {
            "archive_name": "laptop",
            "source_paths": ["/src"],
            "custom_flags": custom_flags,
        },
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "custom_flags",
    [
        "--rsh='sh -c id'",
        "--remote-path=/tmp/evil",
        "--content-from-command -- id",
        "--stats; id",
        "--stats\nid",
        "/etc/shadow",
        ["--rsh=sh -c id"],
        ["--paths-from-command", "--", "id"],
        ["--stats", "id"],
    ],
)
def test_backup_payload_rejects_disallowed_custom_flags(custom_flags):
    with pytest.raises(ValueError):
        BackupCreatePayload.from_job_payload(_backup_payload(custom_flags))


@pytest.mark.unit
def test_backup_payload_keeps_allowed_custom_flags():
    payload = BackupCreatePayload.from_job_payload(
        _backup_payload("--one-file-system --filter AME")
    )

    assert payload.custom_flags == ["--one-file-system", "--filter=AME"]


@pytest.mark.unit
@pytest.mark.parametrize("borg_version", [1, 2])
@pytest.mark.parametrize(
    "extra_flags", ["--rsh='sh -c id'", "--verify-data; id", ["--verify-data", "id"]]
)
def test_repository_check_rejects_disallowed_extra_flags(borg_version, extra_flags):
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.check",
            "repository": {"path": "/backup/repo", "borg_version": borg_version},
            "operation": {"check_extra_flags": extra_flags},
        }
    )

    with pytest.raises(ValueError):
        payload.build_command()


@pytest.mark.unit
def test_repository_check_keeps_allowed_extra_flags():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.check",
            "repository": {"path": "/backup/repo", "borg_version": 1},
            "operation": {"check_extra_flags": "--verify-data"},
        }
    )

    assert "--verify-data" in payload.build_command()
