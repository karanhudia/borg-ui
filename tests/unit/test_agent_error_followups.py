"""Consumer-visible errors from agent browsing and Borg repository jobs."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.database.models import AgentJob, AgentJobLog, AgentMachine
from app.services.agent_connection_manager import (
    AgentCommandError,
    AgentCommandTimeout,
    AgentConnectionUnavailable,
    agent_connection_manager,
)
from app.services.agent_filesystem_service import browse_agent_filesystem
from app.services.repository_executor import wait_for_agent_repository_operation_job


@pytest.fixture
def machine(test_db):
    row = AgentMachine(
        name="browse",
        agent_id="followups",
        token_hash="x",
        token_prefix="x",
        status="online",
        capabilities=["filesystem.browse"],
    )
    test_db.add(row)
    test_db.commit()
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["result", "exception"])
@pytest.mark.parametrize(
    "code,status,key",
    [
        ("missing", 404, "pathNotFound"),
        ("unreadable", 403, "permissionDenied"),
        ("not_directory", 400, "pathNotDirectory"),
    ],
)
async def test_browse_known_codes_use_requested_path(
    test_db, machine, monkeypatch, transport, code, status, key
):
    error = {"code": code, "message": "agent resolved another path"}
    command = AsyncMock(return_value={"success": False, "error": error})
    if transport == "exception":
        command.side_effect = AgentCommandError(error["message"], error)
    monkeypatch.setattr(agent_connection_manager, "send_command", command)
    with pytest.raises(HTTPException) as caught:
        await browse_agent_filesystem(test_db, machine.id, path="~/original")
    assert caught.value.status_code == status
    assert caught.value.detail == {
        "key": f"backend.errors.filesystem.{key}",
        "params": {"path": "~/original"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [{}, {"code": "unknown"}, {"code": []}, "bad"])
@pytest.mark.parametrize("transport", ["result", "exception"])
async def test_browse_unknown_or_malformed_codes_stay_gateway_failures(
    test_db, machine, monkeypatch, error, transport
):
    command = AsyncMock(return_value={"success": False, "error": error})
    if transport == "exception":
        command.side_effect = AgentCommandError(
            "failed", error if isinstance(error, dict) else {}
        )
    monkeypatch.setattr(agent_connection_manager, "send_command", command)
    with pytest.raises(HTTPException) as caught:
        await browse_agent_filesystem(test_db, machine.id, path="/original")
    assert caught.value.status_code == 502
    assert caught.value.detail["key"] == "backend.errors.agents.filesystemBrowseFailed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status",
    [
        (AgentConnectionUnavailable("offline"), 409),
        (AgentCommandTimeout("timeout"), 504),
    ],
)
async def test_browse_transport_status_is_preserved(
    test_db, machine, monkeypatch, error, status
):
    monkeypatch.setattr(
        agent_connection_manager, "send_command", AsyncMock(side_effect=error)
    )
    with pytest.raises(HTTPException) as caught:
        await browse_agent_filesystem(test_db, machine.id, path="/original")
    assert caught.value.status_code == status


def failed_job(db, machine, *, kind="repository.info", code=2, tail=None):
    job = AgentJob(
        agent_machine_id=machine.id,
        job_type="repository",
        status="failed",
        payload={"job_kind": kind},
        error_message=f"{kind} exited with code {code}",
        result={
            "return_code": code,
            **({"stderr_tail": tail} if tail is not None else {}),
        },
    )
    db.add(job)
    db.commit()
    return job


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,code,tail,status",
    [
        ("repository.init", 10, "", 409),
        ("repository.init", 2, "A repository already exists at /repo.", 409),
        ("repository.info", 10, "A repository already exists at /repo.", 502),
        (
            "repository.init",
            2,
            "Error: the repository already exists check could not run",
            502,
        ),
        # A refusal fixed on the agent's host is not a gateway fault
        # (dashboard fd8a3e653ad160f1).
        ("repository.init", 2, "Permission denied", 422),
        (
            "repository.list_archives",
            72,
            "Failed to create/acquire the lock /mnt/r/lock.exclusive "
            "([Errno 13] Permission denied: '/mnt/r/lock.exclusive')",
            422,
        ),
        ("repository.init", 2, "", 502),
    ],
)
async def test_only_evidenced_init_conflicts_return_409(
    test_db, machine, kind, code, tail, status
):
    job = failed_job(test_db, machine, kind=kind, code=code, tail=tail)
    with pytest.raises(HTTPException) as caught:
        await wait_for_agent_repository_operation_job(test_db, job.id)
    assert caught.value.status_code == status
    if status == 409:
        assert caught.value.detail == {
            "key": "backend.errors.borg.repositoryAlreadyExists"
        }
    test_db.refresh(job)
    assert job.status == "failed"
    assert job.result["return_code"] == code


TRACEBACK = """Local Exception
Traceback (most recent call last):
  File "borg/archiver.py", line 1, in main
    open(path)
OSError: [Errno 5] Input/output error: 'ssh://user:s3cret@host/repo'

Platform: Linux host 6.1.0 x86_64
Borg: 1.4.1 Python: CPython 3.11.2
PID: 123 CWD: /private
sys.argv: ['borg', '--token=footer-secret']
SSH_ORIGINAL_COMMAND: BORG_PASSPHRASE=footer-secret
terminating with error status, rc 2"""


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("split", [False, True])
async def test_traceback_uses_exception_without_platform_or_secrets(
    test_db, machine, legacy, split
):
    job = failed_job(test_db, machine, tail=None if legacy else TRACEBACK)
    if legacy:
        messages = TRACEBACK.splitlines() if split else [TRACEBACK]
        for seq, message in enumerate(messages, 1):
            test_db.add(
                AgentJobLog(
                    agent_job_id=job.id,
                    sequence=seq,
                    stream="stderr",
                    message=message,
                    created_at=datetime.utcnow(),
                )
            )
        test_db.commit()
    with pytest.raises(HTTPException) as caught:
        await wait_for_agent_repository_operation_job(test_db, job.id)
    reason = caught.value.detail["params"]["reason"]
    assert "OSError: [Errno 5] Input/output error" in reason
    assert "s3cret" not in reason
    assert "footer-secret" not in reason
    assert "Platform:" not in reason
    assert "Local Exception" not in reason


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_large_diagnostics_are_bounded_after_redaction(test_db, machine, legacy):
    tail = "OSError: " + "x" * 6000 + " ssh://user:s3cret@host/repo"
    job = failed_job(test_db, machine, tail=None if legacy else tail)
    if legacy:
        test_db.add(
            AgentJobLog(
                agent_job_id=job.id,
                sequence=1,
                stream="stderr",
                message=tail,
                created_at=datetime.utcnow(),
            )
        )
        test_db.commit()
    with pytest.raises(HTTPException) as caught:
        await wait_for_agent_repository_operation_job(test_db, job.id)
    reason = caught.value.detail["params"]["reason"]
    assert len(reason) <= 4096
    assert "s3cret" not in reason


@pytest.mark.asyncio
async def test_real_repeated_borg_init_conflict_preserves_repository(
    test_db, machine, tmp_path
):
    import os
    import shutil
    import subprocess

    borg = shutil.which("borg")
    if borg is None:
        pytest.skip("Borg is not installed")
    repo = tmp_path / "repository"
    env = {**os.environ, "BORG_EXIT_CODES": "modern"}
    first = subprocess.run(
        [borg, "init", "--encryption=none", str(repo)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    config = (repo / "config").read_bytes()
    sentinel = repo / "preserve-me"
    sentinel.write_bytes(b"existing repository data")
    duplicate = subprocess.run(
        [borg, "init", "--encryption=none", str(repo)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert duplicate.returncode != 0
    assert f"A repository already exists at {repo}." in duplicate.stderr
    job = failed_job(
        test_db,
        machine,
        kind="repository.init",
        code=duplicate.returncode,
        tail=duplicate.stderr,
    )
    with pytest.raises(HTTPException) as caught:
        await wait_for_agent_repository_operation_job(test_db, job.id)
    assert caught.value.status_code == 409
    assert (repo / "config").read_bytes() == config
    assert sentinel.read_bytes() == b"existing repository data"


@pytest.mark.asyncio
async def test_legacy_lock_reason_survives_trailing_progress(test_db, machine):
    job = failed_job(test_db, machine, code=73)
    for sequence, message in enumerate(
        [
            "Failed to create/acquire the lock /repo/lock.exclusive (timeout).",
            "Remote process exited",
            "Platform: Linux host",
        ],
        1,
    ):
        test_db.add(
            AgentJobLog(
                agent_job_id=job.id,
                sequence=sequence,
                stream="stderr",
                message=message,
                created_at=datetime.utcnow(),
            )
        )
    test_db.commit()
    with pytest.raises(HTTPException) as caught:
        await wait_for_agent_repository_operation_job(test_db, job.id)
    assert caught.value.detail["params"]["reason"].endswith(
        "Failed to create/acquire the lock /repo/lock.exclusive (timeout)."
    )
    assert caught.value.detail["lock_contention"] is True


def test_incomplete_traceback_never_promotes_indented_source_to_reason():
    from app.services.repository_executor import _tail_reason_line

    assert (
        _tail_reason_line(
            "Local Exception\nTraceback (most recent call last):\n  token: sensitive_source\nPlatform: Linux",
            lock_contention=False,
        )
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "pre_exception", ["OSError: [Errno 5] Input/output error\n", ""]
)
async def test_borg2_reporting_boilerplate_never_replaces_exception(
    test_db, machine, legacy, pre_exception
):
    tail = (
        "Local Exception\nError:\n"
        + pre_exception
        + "If reporting bugs, please include the following:\n"
        + "Traceback (most recent call last):\n"
        + '  File "borg/archiver.py", line 1, in main\n'
        + "    open(path)\n"
        + "OSError: [Errno 5] Input/output error\nPlatform: Linux host\n"
        + "sys.argv: ['borg', '--token=footer-secret']"
    )
    job = failed_job(test_db, machine, tail=None if legacy else tail)
    if legacy:
        for sequence, message in enumerate(tail.splitlines(), 1):
            test_db.add(
                AgentJobLog(
                    agent_job_id=job.id,
                    sequence=sequence,
                    stream="stderr",
                    message=message,
                    created_at=datetime.utcnow(),
                )
            )
        test_db.commit()
    with pytest.raises(HTTPException) as caught:
        await wait_for_agent_repository_operation_job(test_db, job.id)
    assert caught.value.detail["params"]["reason"] == (
        "repository.info exited with code 2: OSError: [Errno 5] Input/output error"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("exception", ["AssertionError", "MemoryError"])
async def test_message_free_traceback_exception_reaches_waiter(
    test_db, machine, legacy, exception
):
    tail = f'Traceback (most recent call last):\n  File "borg/archiver.py", line 1, in main\n    assert valid\n{exception}\nPlatform: Linux host'
    job = failed_job(test_db, machine, tail=None if legacy else tail)
    if legacy:
        test_db.add(
            AgentJobLog(
                agent_job_id=job.id,
                sequence=1,
                stream="stderr",
                message=tail,
                created_at=datetime.utcnow(),
            )
        )
        test_db.commit()
    with pytest.raises(HTTPException) as caught:
        await wait_for_agent_repository_operation_job(test_db, job.id)
    assert (
        caught.value.detail["params"]["reason"]
        == f"repository.info exited with code 2: {exception}"
    )


@pytest.mark.parametrize(
    "exception", ["AssertionError", "MemoryError", "borg.custom.CustomError"]
)
def test_message_free_exception_is_available_to_restore_preview_parser(exception):
    from app.services.repository_executor import _tail_reason_line

    assert (
        _tail_reason_line(
            f'Traceback (most recent call last):\n  File "borg/archiver.py", line 1, in main\n{exception}\nPlatform: Linux host',
            lock_contention=False,
        )
        == exception
    )
