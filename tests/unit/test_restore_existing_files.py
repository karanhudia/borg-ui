"""A restore chooses what happens to files already at its destination (#1261).

Borg 2.0.0b25 extracts only into an empty directory (exit 33 otherwise).
"refuse", the default, keeps that exact restore and refuses an occupied
destination before Borg runs; "continue" is chosen in the restore dialog and
writes into what is there with Borg's --continue, which skips a file that has
the archived type, mode, size and modification time. Restore checks, the
restore preview (--dry-run) and file downloads (--stdout) are not affected.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database.models import Operation, Repository


def _occupied(tmp_path):
    (tmp_path / "existing.txt").write_text("x")
    return str(tmp_path)


# -- server command ------------------------------------------------------------


@pytest.mark.unit
def test_only_a_restore_into_existing_files_passes_continue():
    from app.core.borg2 import borg2_extract_existing_files_flags

    assert borg2_extract_existing_files_flags("continue") == ["--continue"]
    assert borg2_extract_existing_files_flags("refuse") == []
    assert borg2_extract_existing_files_flags(None) == []


@pytest.mark.unit
def test_a_restore_into_existing_files_is_built_with_continue(monkeypatch, tmp_path):
    from app.core.borg2 import borg2_restore_target_refusal
    from app.services.v2.restore_service import restore_v2_service

    destination = _occupied(tmp_path)

    assert borg2_restore_target_refusal(destination, "continue") is None
    cmd = restore_v2_service.build_extract_command(
        "/repo",
        "aid:1",
        ["etc"],
        strip_components=1,
        destination=destination,
        existing_files="continue",
    )

    assert cmd[3:] == [
        "extract",
        "--log-json",
        "--umask",
        "0022",
        "--continue",
        "--strip-components",
        "1",
        "aid:1",
        "etc",
    ]


@pytest.mark.unit
def test_the_exact_restore_still_refuses_an_occupied_destination(monkeypatch, tmp_path):
    from app.core.borg_errors import RestoreRefused
    from app.services.v2.restore_service import restore_v2_service

    with pytest.raises(RestoreRefused):
        restore_v2_service.build_extract_command(
            "/repo", "aid:1", ["etc"], destination=_occupied(tmp_path)
        )


@pytest.mark.unit
def test_the_router_hands_the_choice_to_borg2_and_ignores_it_for_borg1(
    monkeypatch, tmp_path
):
    from app.core.borg_router import BorgRouter

    destination = _occupied(tmp_path)

    def build(borg_version):
        return BorgRouter(
            SimpleNamespace(borg_version=borg_version)
        ).build_restore_extract_command(
            repository_path="/repo",
            archive_name="a",
            paths=["etc"],
            destination=destination,
            existing_files="continue",
        )

    assert "--continue" in build(2)
    assert "--continue" not in build(1)


# -- route and executor ---------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("existing_files", [None, "refuse", "continue"])
def test_the_route_keeps_the_choice_with_the_operation(
    test_client: TestClient, admin_headers, test_db, existing_files
):
    repo = Repository(
        name="Repo", path="/repo", encryption="none", repository_type="local"
    )
    test_db.add(repo)
    test_db.commit()
    body = {
        "repository": repo.path,
        "repository_id": repo.id,
        "archive": "a",
        "paths": ["docs"],
        "destination": "/restore/target",
    }
    if existing_files:
        body["existing_files"] = existing_files

    with patch(
        "app.services.restore_service.restore_service.execute_restore",
        new=AsyncMock(return_value=None),
    ):
        response = test_client.post(
            "/api/restore/start", json=body, headers=admin_headers
        )

    assert response.status_code == 200, response.text
    operation = test_db.get(Operation, response.json()["job_id"])
    assert operation.params["existing_files"] == (existing_files or "refuse")


@pytest.mark.unit
def test_the_route_refuses_an_unknown_choice(
    test_client: TestClient, admin_headers, test_db
):
    response = test_client.post(
        "/api/restore/start",
        json={
            "repository": "/repo",
            "repository_id": 1,
            "archive": "a",
            "paths": [],
            "destination": "/restore/target",
            "existing_files": "overwrite",
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "expected"),
    [({}, "refuse"), ({"existing_files": "continue"}, "continue")],
)
async def test_the_executor_passes_the_choice_to_the_service(params, expected):
    from app.services.operations.executors import restore as executor

    repository = SimpleNamespace(
        path="/repo", repository_type="local", connection_id=None
    )
    operation = SimpleNamespace(id=1, status="completed", error_message=None)
    db = SimpleNamespace(
        get=lambda model, _id: repository if model is Repository else operation,
        expire_all=lambda: None,
    )
    ctx = SimpleNamespace(
        db=db,
        repository_id=1,
        operation_id=1,
        params={"paths": ["etc"], **params},
        cancelled=lambda: False,
    )
    facade = SimpleNamespace(
        archive="a",
        destination="/dest",
        repository_type="local",
        destination_type="local",
        destination_connection_id=None,
        nfiles=1,
        restored_size=1,
    )

    with (
        patch.object(executor, "RestoreJobFacade", return_value=facade),
        patch.object(executor, "cancel_watcher", new=AsyncMock()),
        patch(
            "app.services.restore_service.restore_service.execute_restore",
            new=AsyncMock(),
        ) as execute,
    ):
        await executor.run_restore(ctx)

    assert execute.await_args.kwargs["existing_files"] == expected


# -- agent delegation -------------------------------------------------------------


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeDB:
    def __init__(self, repository, agent):
        self._repository = repository
        self._agent = agent

    def query(self, model):
        return _FakeQuery(self._repository)

    def get(self, model, _id):
        return self._agent

    def commit(self):
        pass

    def close(self):
        pass


async def _delegate(monkeypatch, capabilities, existing_files, borg_version=2):
    from app.services import restore_service as module
    from app.services.restore_service import RestoreService

    job = SimpleNamespace(status="pending", error_message=None, completed_at=None)
    repository = SimpleNamespace(
        id=7, path="/agent/repo", agent_machine_id=3, borg_version=borg_version
    )
    agent = SimpleNamespace(capabilities=capabilities)
    monkeypatch.setattr(module, "SessionLocal", lambda: _FakeDB(repository, agent))
    monkeypatch.setattr(module, "resolve_restore_job", lambda db, job_id: job)
    queued = {}

    def queue(db, repo, *, job_kind, operation):
        queued["operation"] = operation
        raise HTTPException(status_code=409, detail={"key": "stop-here"})

    monkeypatch.setattr(
        "app.services.repository_executor.queue_agent_repository_operation_job",
        queue,
    )
    service = RestoreService()
    service._notify_agent_restore = AsyncMock()

    await service._execute_agent_restore(
        1, "/agent/repo", "a", "/dest", ["etc"], existing_files=existing_files
    )
    return job, queued.get("operation")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_agent_that_reads_the_choice_gets_it(monkeypatch):
    from app.services.restore_service import AGENT_RESTORE_EXISTING_FILES_CAPABILITY

    _job, operation = await _delegate(
        monkeypatch, [AGENT_RESTORE_EXISTING_FILES_CAPABILITY], "continue"
    )

    assert operation["target"] == {
        "type": "path",
        "path": "/dest",
        "existing_files": "continue",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_exact_restore_leaves_the_payload_as_it_was(monkeypatch):
    _job, operation = await _delegate(monkeypatch, [], "refuse")

    assert operation["target"] == {"type": "path", "path": "/dest"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_agent_from_before_0_1_17_is_not_asked_to_write_into_existing_files(
    monkeypatch,
):
    """It would ignore the choice and refuse with a message about empty
    directories; the restore says what is missing instead."""
    job, operation = await _delegate(monkeypatch, ["repository.restore"], "continue")

    assert operation is None
    assert job.status == "failed"
    assert json.loads(job.error_message) == {
        "key": "backend.errors.restore.agentCannotRestoreIntoExisting"
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg1_needs_no_new_agent_for_the_choice(monkeypatch):
    """Borg 1 writes into an occupied directory and ignores the choice, so
    an agent from before 0.1.17 serves it."""
    job, operation = await _delegate(
        monkeypatch, ["repository.restore"], "continue", borg_version=1
    )

    # queued for the agent (the stub stops it there), no upgrade demanded
    assert operation is not None
    assert "agentCannotRestoreIntoExisting" not in job.error_message


@pytest.mark.unit
def test_the_agent_reports_that_it_reads_the_choice():
    from agent.borg_ui_agent.runtime import DEFAULT_CAPABILITIES
    from app.services.restore_service import AGENT_RESTORE_EXISTING_FILES_CAPABILITY

    assert AGENT_RESTORE_EXISTING_FILES_CAPABILITY in DEFAULT_CAPABILITIES


# -- agent -----------------------------------------------------------------------


def _agent_restore(target: str, existing_files=None, borg_version: int = 2) -> dict:
    target_spec = {"type": "path", "path": target}
    if existing_files:
        target_spec["existing_files"] = existing_files
    return {
        "id": 21,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.restore",
            "repository": {"path": "/agent/repo", "borg_version": borg_version},
            "operation": {
                "archive": "aid:0123456789abcdef",
                "target": target_spec,
                "paths": ["etc/hosts"],
            },
            "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
        },
    }


def _run_agent_restore(monkeypatch, job):
    from agent.borg_ui_agent.repository_ops import execute_repository_operation_job

    captured = {}
    calls = []

    class FakePopen:
        returncode = 0
        pid = 1

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            self.stdout = iter(())

        def wait(self, *args, **kwargs):
            return 0

        def poll(self):
            return 0

    class Client:
        def __getattr__(self, name):
            def record(*args, **kwargs):
                calls.append((name, args, kwargs))
                return {}

            return record

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", FakePopen
    )
    execute_repository_operation_job(job, Client(), should_cancel=None)
    return captured.get("cmd"), calls


@pytest.mark.unit
def test_the_agent_writes_into_existing_files_when_asked(tmp_path, monkeypatch):
    cmd, calls = _run_agent_restore(
        monkeypatch, _agent_restore(_occupied(tmp_path), "continue")
    )

    assert cmd is not None and cmd[3] == "extract"
    assert "--continue" in cmd
    assert not [call for call in calls if call[0] == "fail_job"]


@pytest.mark.unit
def test_the_agent_still_refuses_an_occupied_destination_for_an_exact_restore(
    monkeypatch, tmp_path
):
    cmd, calls = _run_agent_restore(monkeypatch, _agent_restore(_occupied(tmp_path)))

    assert cmd is None
    failed = [call for call in calls if call[0] == "fail_job"]
    assert "Restore into existing files" in failed[0][2]["error_message"]


@pytest.mark.unit
def test_borg1_ignores_the_choice_on_the_agent(monkeypatch, tmp_path):
    cmd, _calls = _run_agent_restore(
        monkeypatch, _agent_restore(_occupied(tmp_path), "continue", borg_version=1)
    )

    assert cmd is not None and "--continue" not in cmd
