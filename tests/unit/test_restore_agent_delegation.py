"""Unit tests for server-side delegation of restores to managed agents."""

from __future__ import annotations

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import restore_service as restore_service_module
from app.services.job_admission import (
    OPERATION_CLASS_REPOSITORY_READ,
    OPERATION_RESTORE,
    READ_OPERATIONS,
    operation_class_for,
    operation_for_agent_job_kind,
)
from app.services.repository_executor import (
    REPOSITORY_OPERATION_CAPABILITIES,
    build_agent_repository_operation_payload,
)
from app.services.restore_check_service import RestoreCheckService
from app.services.restore_service import RestoreService


# --------------------------------------------------------------------------- #
# admission + payload wiring
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_repository_restore_maps_to_read_operation():
    assert operation_for_agent_job_kind("repository.restore") == OPERATION_RESTORE
    assert OPERATION_RESTORE in READ_OPERATIONS
    assert operation_class_for(OPERATION_RESTORE) == OPERATION_CLASS_REPOSITORY_READ


@pytest.mark.unit
def test_repository_restore_is_a_known_capability():
    assert "repository.restore" in REPOSITORY_OPERATION_CAPABILITIES


@pytest.mark.unit
def test_build_agent_restore_payload_carries_operation_and_secret():
    repo = SimpleNamespace(
        id=7, path="/agent/repo", borg_version=1, remote_path=None, passphrase="s3cret"
    )
    operation = {
        "archive": "arch",
        "paths": ["etc"],
        "target": {"type": "path", "path": "/dest"},
        "strip_components": 1,
    }

    payload = build_agent_repository_operation_payload(
        repo, "repository.restore", operation=operation
    )

    assert payload["job_kind"] == "repository.restore"
    assert payload["repository"]["path"] == "/agent/repo"
    assert payload["operation"]["archive"] == "arch"
    assert payload["operation"]["target"] == {"type": "path", "path": "/dest"}
    assert payload["secrets"]["BORG_PASSPHRASE"]["value"] == "s3cret"


# --------------------------------------------------------------------------- #
# ad-hoc restore terminal mapping
# --------------------------------------------------------------------------- #


def _restore_job_stub():
    return SimpleNamespace(
        status="running",
        error_message=None,
        logs=None,
        completed_at=None,
        progress_percent=None,
    )


def _apply_terminal(agent_job):
    service = RestoreService()
    service._collect_agent_job_logs = lambda db, agent_job_id: "agent logs"
    job = _restore_job_stub()
    service._apply_agent_restore_terminal(None, job, agent_job)
    return job


@pytest.mark.unit
def test_agent_restore_terminal_completed():
    job = _apply_terminal(
        SimpleNamespace(
            status="completed", result={"return_code": 0, "warning": False}, id=1
        )
    )
    assert job.status == "completed"
    assert job.progress_percent == 100.0
    assert job.logs == "agent logs"


@pytest.mark.unit
def test_agent_restore_terminal_completed_with_warnings():
    job = _apply_terminal(
        SimpleNamespace(
            status="completed", result={"return_code": 1, "warning": True}, id=1
        )
    )
    assert job.status == "completed_with_warnings"
    assert "restoreCompletedWithWarnings" in job.error_message


@pytest.mark.unit
def test_agent_restore_terminal_failed_records_exit_code():
    job = _apply_terminal(
        SimpleNamespace(
            status="failed", result={"return_code": 2}, error_message="boom", id=1
        )
    )
    assert job.status == "failed"
    assert "restoreFailedExitCode" in job.error_message


@pytest.mark.unit
def test_agent_restore_terminal_canceled():
    job = _apply_terminal(
        SimpleNamespace(status="canceled", result={}, error_message=None, id=1)
    )
    assert job.status == "cancelled"
    assert "cancelledByUser" in job.error_message


# --------------------------------------------------------------------------- #
# restore-check verdict mapping
# --------------------------------------------------------------------------- #


def _apply_check_result(result):
    service = RestoreCheckService()
    service._save_job_logs = lambda job, job_id, raw_logs: None
    job = SimpleNamespace(
        status="running",
        error_message=None,
        progress=15,
        progress_message="",
        completed_at=None,
    )
    repository = SimpleNamespace(last_restore_check=None)
    db = SimpleNamespace(commit=lambda: None)
    service._apply_agent_restore_check_result(
        db, job, 1, repository, result, raw_logs=[]
    )
    return job, repository


@pytest.mark.unit
def test_restore_check_verified_sets_last_restore_check():
    job, repository = _apply_check_result(
        {"verification": {"status": "verified", "verified_files": ["a"]}}
    )
    assert job.status == "completed"
    assert repository.last_restore_check is not None


@pytest.mark.unit
def test_restore_check_needs_backup():
    job, repository = _apply_check_result(
        {"verification": {"status": "needs_backup", "message": "run a backup"}}
    )
    assert job.status == "needs_backup"
    assert repository.last_restore_check is None


@pytest.mark.unit
def test_restore_check_mismatch_fails():
    job, repository = _apply_check_result(
        {"verification": {"status": "failed", "message": "hash mismatch"}}
    )
    assert job.status == "failed"
    assert repository.last_restore_check is None


@pytest.mark.unit
def test_restore_check_full_archive_without_verify_completes():
    job, repository = _apply_check_result({"return_code": 0, "warning": False})
    assert job.status == "completed"
    assert repository.last_restore_check is not None


# --------------------------------------------------------------------------- #
# agent restore wait: bounded, and notifications
# --------------------------------------------------------------------------- #


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeDB:
    def __init__(self, restore_job, agent_job):
        self._restore_job = restore_job
        self._agent_job = agent_job
        self.commits = 0

    def expire_all(self):
        pass

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "RestoreJob":
            return _FakeQuery(self._restore_job)
        if name == "AgentJob":
            return _FakeQuery(self._agent_job)
        return _FakeQuery(None)

    def commit(self):
        self.commits += 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_await_agent_restore_fails_when_never_claimed(monkeypatch):
    """A restore whose agent never claims the job must fail, not hang."""
    restore_job = SimpleNamespace(
        status="running",
        error_message=None,
        completed_at=None,
        progress_percent=None,
        current_file=None,
        nfiles=None,
        original_size=None,
        id=1,
        repository="/repo",
        archive="arch",
        destination="/dest",
    )
    agent_job = SimpleNamespace(
        status="queued",
        progress_percent=None,
        current_file=None,
        nfiles=None,
        original_size=None,
        id=5,
        result={},
        error_message=None,
    )
    db = _FakeDB(restore_job, agent_job)
    # started_at = 0, then the first poll observes elapsed > the claim timeout.
    # Derive the clock from the actual constant so the test stays correct if the
    # timeout changes. Patch only the module-local `time` name; never exhaust it.
    threshold = restore_service_module._AGENT_RESTORE_CLAIM_TIMEOUT_SECONDS
    clock = itertools.chain([0.0, threshold + 1], itertools.repeat(threshold + 200))
    monkeypatch.setattr(
        restore_service_module,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock)),
    )

    service = RestoreService()
    service._notify_agent_restore = AsyncMock()

    await service._await_agent_restore_job(db, 1, 5)

    assert restore_job.status == "failed"
    # The agent job is terminalized too, so it can't be claimed and run later.
    assert agent_job.status == "failed"
    service._notify_agent_restore.assert_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notify_agent_restore_dispatches_success_and_failure(monkeypatch):
    calls = {}

    async def _success(*args, **kwargs):
        calls["success"] = args

    async def _failure(*args, **kwargs):
        calls["failure"] = args

    monkeypatch.setattr(
        restore_service_module.notification_service,
        "send_restore_success",
        _success,
    )
    monkeypatch.setattr(
        restore_service_module.notification_service,
        "send_restore_failure",
        _failure,
    )
    service = RestoreService()

    await service._notify_agent_restore(
        None,
        SimpleNamespace(
            status="completed",
            repository="/repo",
            archive="arch",
            destination="/dest",
            id=1,
        ),
    )
    assert "success" in calls and calls["success"][1:4] == ("/repo", "arch", "/dest")

    await service._notify_agent_restore(
        None,
        SimpleNamespace(
            status="failed",
            repository="/repo",
            archive="arch",
            destination="/dest",
            id=1,
        ),
    )
    assert "failure" in calls
