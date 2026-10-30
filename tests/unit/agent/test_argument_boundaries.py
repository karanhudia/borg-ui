"""Agent command registry guards archive, stdout destination and paths together."""

import pytest

from agent.borg_ui_agent.backup import BackupCreatePayload
from agent.borg_ui_agent.repository_ops import RepositoryOperationPayload


BUILDERS = [
    "archive_info",
    "delete_archive",
    "list_archive_contents",
    "diff",
    "extract_archive_file",
    "export_archive_tar",
    "restore",
]


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_batch_delete_operand_boundary(major):
    archives = ["daily", "aid:0123456789abcdef"]
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.delete_archives",
            "repository": {"path": "/repo", "borg_version": major},
            "operation": {"archives": archives},
        }
    )
    commands = payload.delete_archives_commands()
    assert [archive for archive, _ in commands] == archives
    for archive, command in commands:
        assert command.count("--") == 1
        assert command[command.index("--") + 1 :] == [
            archive if major == 2 else f"/repo::{archive}"
        ]
    assert payload.build_command() == commands[0][1]


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_batch_delete_rejects_option_shaped_selector(major):
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.delete_archives",
            "repository": {"path": "/repo", "borg_version": major},
            "operation": {"archives": ["daily", "--review-sentinel"]},
        }
    )
    with pytest.raises(ValueError):
        payload.delete_archives_commands()


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize("kind", BUILDERS)
@pytest.mark.parametrize("paths", [[], ["folder with spaces/file"]])
def test_repository_operand_boundary(major, kind, paths):
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": f"repository.{kind}",
            "repository": {"path": "/repo", "borg_version": major},
            "operation": {
                "archive": "daily",
                "predecessor": None,
                "path": "/folder with spaces/",
                "file_path": "/folder with spaces/file",
                "directory_path": "/folder with spaces/",
                "paths": paths,
                "strip_components": 1,
            },
        }
    )
    cmd = payload.build_command()
    operand = "daily" if major == 2 else "/repo::daily"
    assert cmd.count("--") == 1
    assert cmd[cmd.index("--") + 1] == operand
    if kind == "export_archive_tar":
        assert cmd[cmd.index("--") + 1 :] == [operand, "-", "folder with spaces"]


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_backup_operand_boundary(major):
    payload = BackupCreatePayload.from_job_payload(
        {
            "repository": {"path": "/repo", "borg_version": major},
            "backup": {
                "archive_name": "daily",
                "source_paths": ["source with spaces"],
                "custom_flags": ["--one-file-system"],
            },
        }
    )
    cmd = payload.build_command()
    assert cmd.count("--") == 1
    assert cmd.index("--one-file-system") < cmd.index("--")
    assert cmd[cmd.index("--") + 1 :] == [
        "daily" if major == 2 else "/repo::daily",
        "source with spaces",
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [
        ("archive", "--sentinel"),
        ("file_path", "/-sentinel/"),
        ("directory_path", "/-sentinel/"),
        ("paths", ["--sentinel"]),
    ],
)
def test_agent_rejects_invalid_operands(field, value):
    kind = {
        "archive": "archive_info",
        "file_path": "extract_archive_file",
        "directory_path": "export_archive_tar",
        "paths": "restore",
    }[field]
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": f"repository.{kind}",
            "repository": {"path": "/repo", "borg_version": 2},
            "operation": {"archive": "daily", field: value},
        }
    )
    with pytest.raises(ValueError):
        payload.build_command()


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [
        ("archive_name", "--sentinel"),
        ("source_paths", ["--sentinel"]),
        ("source_paths", ["ssh://host"]),
    ],
)
def test_agent_rejects_invalid_backup_operands(field, value):
    with pytest.raises(ValueError):
        BackupCreatePayload.from_job_payload(
            {
                "repository": {"path": "/repo", "borg_version": 2},
                "backup": {
                    "archive_name": "daily",
                    "source_paths": ["/source"],
                    field: value,
                },
            }
        ).build_command()


@pytest.mark.unit
@pytest.mark.parametrize("kind", BUILDERS)
@pytest.mark.parametrize("archive", ["daily", "aid:0123456789abcdef"])
def test_agent_keeps_normal_and_aid_selectors(kind, archive):
    cmd = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": f"repository.{kind}",
            "repository": {"path": "/repo", "borg_version": 2},
            "operation": {
                "archive": archive,
                "predecessor": None,
                "file_path": "folder/file",
                "directory_path": "folder",
            },
        }
    ).build_command()
    assert cmd[cmd.index("--") + 1] == archive


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_agent_rejects_disallowed_custom_flags(major):
    with pytest.raises(ValueError):
        BackupCreatePayload.from_job_payload(
            {
                "repository": {"path": "/repo", "borg_version": major},
                "backup": {
                    "archive_name": "daily",
                    "source_paths": ["/source"],
                    "custom_flags": ["--remote-path=sentinel"],
                },
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize("kind", [*BUILDERS, "backup"])
def test_agent_execution_keeps_operands_after_boundary(monkeypatch, major, kind):
    import io
    import subprocess
    from unittest.mock import MagicMock
    from agent.borg_ui_agent.backup import execute_backup_create_job
    from agent.borg_ui_agent.repository_ops import execute_repository_operation_job

    commands = []

    def run(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            "{}" if kwargs.get("text") else b"{}",
            "" if kwargs.get("text") else b"",
        )

    def popen(cmd, **kwargs):
        commands.append(cmd)
        process = MagicMock()
        process.returncode = 0
        process.poll.return_value = 0
        process.wait.return_value = 0
        process.stdout = io.StringIO("{}") if kwargs.get("text") else io.BytesIO(b"{}")
        process.stderr = io.StringIO("") if kwargs.get("text") else io.BytesIO(b"")
        return process

    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setattr("subprocess.Popen", popen)
    payload = {"repository": {"path": "/repo", "borg_version": major}}
    if kind == "backup":
        payload.update(
            job_kind="backup.create",
            backup={"archive_name": "daily", "source_paths": ["source with spaces"]},
        )
        execute_backup_create_job({"id": 42, "payload": payload}, MagicMock())
    else:
        payload.update(
            job_kind=f"repository.{kind}",
            operation={
                "archive": "daily",
                "predecessor": None,
                "file_path": "folder/file",
                "directory_path": "folder",
                "paths": [],
                "target": {"type": "temp"},
            },
        )
        execute_repository_operation_job({"id": 42, "payload": payload}, MagicMock())
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.count("--") == 1
    assert cmd[cmd.index("--") + 1] == ("daily" if major == 2 else "/repo::daily")


@pytest.mark.unit
def test_agent_borg1_archive_listing_closes_options():
    cmd = RepositoryOperationPayload(
        "repository.list_archives", "/repo"
    ).build_command()
    assert cmd[-3:] == ["--json", "--", "/repo"]


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize("paths", [[], ["folder with spaces/file"]])
def test_agent_restore_dry_run_closes_options(major, paths):
    cmd = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.restore_dry_run",
            "repository": {"path": "/repo", "borg_version": major},
            "operation": {"archive": "daily", "paths": paths},
        }
    ).build_command()
    operand = "daily" if major == 2 else "/repo::daily"
    assert cmd.count("--") == 1
    assert cmd.index("--dry-run") < cmd.index("--")
    assert cmd[cmd.index("--") + 1 :] == [operand, *paths]


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_direct_delete_helper_rejects_option_shaped_selector(major):
    payload = RepositoryOperationPayload(
        "repository.delete_archive", "/repo", borg_version=major
    )
    with pytest.raises(ValueError):
        payload.delete_archive_command("--sentinel")
