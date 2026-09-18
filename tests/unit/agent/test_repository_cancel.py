"""A cancelled repository operation ends its process on the agent even while
the process prints nothing (agent 0.1.7, `jobs.cancel`)."""

import os
import subprocess
import sys
import threading
import time

import pytest

from agent.borg_ui_agent import backup, repository_ops
from agent.borg_ui_agent.backup import execute_backup_create_job
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    _execute_restore_operation,
    _execute_short_repository_operation,
    _execute_streaming_repository_operation,
    _run_cancellable,
    execute_repository_operation_job,
)
from agent.borg_ui_agent.runtime import get_capabilities

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX"),
]

# Long enough that a test only passes when the cancel ended it.
SILENT = [sys.executable, "-c", "import time; time.sleep(30)"]


class RecordingClient:
    def __init__(self):
        self.calls: list[tuple] = []

    def send_log(self, job_id, *, sequence, stream, message):
        self.calls.append(("log", stream, message))

    def send_progress(self, job_id, progress):
        self.calls.append(("progress", progress))

    def complete_job(self, job_id, *, result):
        self.calls.append(("complete", result))

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.calls.append(("fail", error_message))

    def cancel_job(self, job_id):
        self.calls.append(("cancel", job_id))

    def kinds(self) -> list[str]:
        return [call[0] for call in self.calls]


def _payload(job_kind, operation=None):
    return RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": job_kind,
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": operation,
        }
    )


def _cancel_after(seconds):
    requested_at = time.monotonic() + seconds
    return lambda: time.monotonic() >= requested_at


def test_capability_is_advertised():
    assert "jobs.cancel" in get_capabilities()


def test_streaming_operation_is_cancelled_while_silent():
    client = RecordingClient()
    started = time.monotonic()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.check"),
        client,
        SILENT,
        dict(os.environ),
        initial_sequence=1,
        should_cancel=_cancel_after(0.2),
    )

    assert result.status == "canceled"
    assert time.monotonic() - started < 10
    assert client.kinds() == ["cancel"]


def test_streaming_operation_without_a_cancel_runs_to_its_end():
    client = RecordingClient()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.prune"),
        client,
        [sys.executable, "-c", "import time; time.sleep(1.2); print('done')"],
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
    )

    assert result.status == "completed"
    assert ("log", "stdout", "done") in client.calls
    assert "cancel" not in client.kinds()


def test_a_failing_cancel_check_is_not_a_cancel():
    """The polling runtime's check is a heartbeat; an unreachable server
    must not end the operation."""

    def unreachable():
        raise ConnectionError("server down")

    client = RecordingClient()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.compact"),
        client,
        [sys.executable, "-c", "import time; time.sleep(1.2)"],
        dict(os.environ),
        initial_sequence=1,
        should_cancel=unreachable,
    )

    assert result.status == "completed"


def test_restore_is_cancelled_while_silent(tmp_path):
    client = RecordingClient()
    started = time.monotonic()

    result = _execute_restore_operation(
        8,
        _payload(
            "repository.restore",
            {"archive": "a", "paths": [], "target": {"type": "temp"}},
        ),
        client,
        SILENT,
        dict(os.environ),
        initial_sequence=1,
        should_cancel=_cancel_after(0.2),
    )

    assert result.status == "canceled"
    assert time.monotonic() - started < 10
    assert client.kinds() == ["cancel"]


def test_delete_archive_is_cancelled():
    client = RecordingClient()
    started = time.monotonic()

    result = _execute_short_repository_operation(
        9,
        _payload("repository.delete_archive", {"archive": "a"}),
        client,
        SILENT,
        dict(os.environ),
        should_cancel=_cancel_after(0.2),
    )

    assert result.status == "canceled"
    assert time.monotonic() - started < 10
    assert client.kinds() == ["cancel"]


def test_delete_archive_without_a_cancel_reports_its_output():
    client = RecordingClient()

    result = _execute_short_repository_operation(
        9,
        _payload("repository.delete_archive", {"archive": "a"}),
        client,
        [sys.executable, "-c", "print('{\"ok\": true}')"],
        dict(os.environ),
        should_cancel=lambda: False,
    )

    assert result.status == "completed"
    complete = [call for call in client.calls if call[0] == "complete"]
    assert complete[0][1]["data"] == {"ok": True}


def test_cancellable_run_keeps_the_timeout():
    started = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        _run_cancellable(SILENT, dict(os.environ), lambda: False, timeout=0.5)

    assert time.monotonic() - started < 15


def test_only_delete_archive_takes_the_cancellable_short_path(monkeypatch):
    seen: dict[str, object] = {}

    def fake_short(job_id, payload, client, cmd, env, *, should_cancel=None):
        seen[payload.job_kind] = should_cancel
        return repository_ops.RepositoryOperationResult(
            job_id=job_id, status="completed"
        )

    monkeypatch.setattr(
        repository_ops, "_execute_short_repository_operation", fake_short
    )
    check = threading.Event().is_set

    for job_kind, operation in (
        ("repository.delete_archive", {"archive": "a"}),
        ("repository.info", None),
    ):
        execute_repository_operation_job(
            {
                "id": 1,
                "payload": {
                    "schema_version": 1,
                    "job_kind": job_kind,
                    "repository": {"path": "/agent/repo", "borg_version": 1},
                    "operation": operation,
                },
            },
            RecordingClient(),
            should_cancel=check,
        )

    assert seen == {"repository.delete_archive": check, "repository.info": None}


def test_a_job_cancelled_before_it_starts_runs_nothing(monkeypatch):
    """A fast archive delete would be done before the first poll."""

    def no_process(*args, **kwargs):
        raise AssertionError("no process may start")

    monkeypatch.setattr(repository_ops.subprocess, "Popen", no_process)
    monkeypatch.setattr(repository_ops.subprocess, "run", no_process)
    client = RecordingClient()

    result = execute_repository_operation_job(
        {
            "id": 10,
            "payload": {
                "schema_version": 1,
                "job_kind": "repository.delete_archive",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "a"},
            },
        },
        client,
        should_cancel=lambda: True,
    )

    assert result.status == "canceled"
    assert client.kinds() == ["log", "cancel"]


def _backup_job(job_id):
    return {
        "id": job_id,
        "payload": {
            "job_kind": "backup.create",
            "repository_path": "/repo",
            "archive_name": "archive",
            "source_paths": ["/src"],
        },
    }


def test_a_silent_backup_is_cancelled(monkeypatch):
    """borg create waiting on a lock or a stalled store prints nothing; the
    cancel must reach it all the same."""
    monkeypatch.setattr(
        backup.BackupCreatePayload, "build_command", lambda self: SILENT
    )
    client = RecordingClient()
    started = time.monotonic()

    result = execute_backup_create_job(
        _backup_job(11), client, should_cancel=_cancel_after(0.2)
    )

    assert result.status == "canceled"
    assert time.monotonic() - started < 10
    assert ("cancel", 11) in client.calls


def test_a_backup_cancelled_before_it_starts_runs_nothing(monkeypatch):
    def no_process(*args, **kwargs):
        raise AssertionError("no process may start")

    monkeypatch.setattr(backup.subprocess, "Popen", no_process)
    client = RecordingClient()

    result = execute_backup_create_job(
        _backup_job(12), client, should_cancel=lambda: True
    )

    assert result.status == "canceled"
    assert client.kinds() == ["log", "cancel"]


def test_a_cancel_that_lands_during_the_start_log_stops_the_start(monkeypatch):
    """The start log may wait on the server; a cancel that arrives meanwhile
    must still keep a fast delete from running."""

    def no_process(*args, **kwargs):
        raise AssertionError("no process may start")

    monkeypatch.setattr(repository_ops.subprocess, "Popen", no_process)
    requested = {"yes": False}

    class SlowLogClient(RecordingClient):
        def send_log(self, job_id, *, sequence, stream, message):
            super().send_log(job_id, sequence=sequence, stream=stream, message=message)
            requested["yes"] = True  # the cancel lands while this was waiting

    client = SlowLogClient()

    result = execute_repository_operation_job(
        {
            "id": 13,
            "payload": {
                "schema_version": 1,
                "job_kind": "repository.delete_archive",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "a"},
            },
        },
        client,
        should_cancel=lambda: requested["yes"],
    )

    assert result.status == "canceled"


def test_a_cancel_answered_after_the_process_ended_ends_nothing():
    """A slow cancel check (a heartbeat) may answer after the process was
    reaped; its pid may belong to another process by then."""
    import threading
    from unittest.mock import Mock

    from agent.borg_ui_agent.cancel import start_cancel_poller

    class EndsDuringTheCheck:
        returncode = None

        def poll(self):
            return self.returncode

    process = EndsDuringTheCheck()
    answered = threading.Event()

    def slow_check():
        process.returncode = 0  # ended and reaped while the server answered
        answered.set()
        return True

    terminate = Mock()
    done = threading.Event()

    cancelled = start_cancel_poller(process, slow_check, done, terminate)
    assert answered.wait(5)
    time.sleep(0.2)
    done.set()

    terminate.assert_not_called()
    assert not cancelled.is_set()


def test_a_silent_operation_reports_a_keepalive(monkeypatch):
    """The server reaps a job without activity; a reaped one could no longer
    be cancelled while Borg runs on."""
    from agent.borg_ui_agent import cancel

    monkeypatch.setattr(cancel, "KEEPALIVE_SECONDS", 0.1)
    client = RecordingClient()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.compact"),
        client,
        [sys.executable, "-c", "import time; time.sleep(0.6)"],
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
    )

    assert result.status == "completed"
    assert ("progress", {}) in client.calls


def test_a_failing_check_after_a_line_does_not_orphan_borg():
    """The per-line check is a heartbeat as well: one that fails must not
    unwind the worker and leave Borg running without its poller."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("server down")
        return True

    client = RecordingClient()
    started = time.monotonic()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.check"),
        client,
        [
            sys.executable,
            "-c",
            "import time; print('segment 1', flush=True); time.sleep(30)",
        ],
        dict(os.environ),
        initial_sequence=1,
        should_cancel=flaky,
    )

    assert result.status == "canceled"
    assert time.monotonic() - started < 10


def test_an_interrupted_delete_ends_borg(monkeypatch):
    """`subprocess.run` ended its child on an interruption; the cancellable
    run must too, borg being in a session of its own."""
    started = []
    real_popen = subprocess.Popen

    class InterruptedPopen(real_popen):
        def communicate(self, *args, timeout=None, **kwargs):
            if timeout is not None:
                started.append(self)
                raise KeyboardInterrupt
            return super().communicate(*args, **kwargs)

    monkeypatch.setattr(repository_ops.subprocess, "Popen", InterruptedPopen)

    with pytest.raises(KeyboardInterrupt):
        _run_cancellable(SILENT, dict(os.environ), lambda: False, timeout=300)

    assert started[0].poll() is not None


def test_a_failed_report_does_not_leave_borg_running(monkeypatch):
    """A log upload that fails (the server answering 503) unwinds the
    worker; Borg must be ended, not left holding the repository."""
    started = []
    real_popen = subprocess.Popen

    class RecordingPopen(real_popen):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            started.append(self)

    monkeypatch.setattr(repository_ops.subprocess, "Popen", RecordingPopen)

    class FailingLogClient(RecordingClient):
        def send_log(self, job_id, *, sequence, stream, message):
            raise ConnectionError("503 Service Unavailable")

    with pytest.raises(ConnectionError):
        _execute_streaming_repository_operation(
            7,
            _payload("repository.check"),
            FailingLogClient(),
            [
                sys.executable,
                "-c",
                "import time; print('segment 1', flush=True); time.sleep(30)",
            ],
            dict(os.environ),
            initial_sequence=1,
            should_cancel=lambda: False,
        )

    assert started[0].poll() is not None


def test_a_child_that_ignores_sigterm_is_killed_with_its_group(monkeypatch):
    """A wrapper's child that ignores SIGTERM keeps the output pipe open:
    after the grace the whole group goes, and the worker gets its verdict."""
    from agent.borg_ui_agent import cancel

    monkeypatch.setattr(cancel, "KILL_GROUP_AFTER_SECONDS", 0.5)
    wrapper = (
        "import subprocess, time; "
        "subprocess.Popen(['sh', '-c', 'trap \"\" TERM; exec sleep 30']); "
        "time.sleep(30)"
    )
    client = RecordingClient()
    started = time.monotonic()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.compact"),
        client,
        [sys.executable, "-c", wrapper],
        dict(os.environ),
        initial_sequence=1,
        should_cancel=_cancel_after(0.2),
    )

    assert result.status == "canceled"
    assert time.monotonic() - started < 15


def test_an_empty_process_group_is_not_signalled(monkeypatch):
    """An empty group's pid may already belong to a new process."""
    import signal as signal_module

    from agent.borg_ui_agent import cancel

    sent = []

    def killpg(pgid, sig):
        sent.append(sig)
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(cancel.os, "killpg", killpg)

    class Reaped:
        pid = 4242

    cancel.kill_process_group(Reaped())

    assert signal_module.SIGKILL not in sent


def test_an_injected_session_is_not_the_upload_session():
    """A streaming upload on the shared session would hold the cancel
    check for as long as the command runs."""
    from unittest.mock import Mock

    from agent.borg_ui_agent.client import AgentClient

    shared = Mock()
    client = AgentClient("https://server", "token", session=shared)

    assert client.session is shared
    assert client.upload_session is not shared


def test_a_cancel_answered_after_borg_finished_keeps_its_result():
    """The per-line check may ask the server; Borg finishing meanwhile is
    its verdict, not a cancel of work already done."""
    import subprocess as sp

    client = RecordingClient()
    ended = []

    def late_check():
        # answers only once the process is gone
        proc = ended[0]
        proc.wait(timeout=10)
        return True

    real_popen = sp.Popen

    def popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        ended.append(proc)
        return proc

    import unittest.mock as mock

    with mock.patch.object(repository_ops.subprocess, "Popen", popen):
        result = _execute_streaming_repository_operation(
            7,
            _payload("repository.compact"),
            client,
            [sys.executable, "-c", "print('done', flush=True)"],
            dict(os.environ),
            initial_sequence=1,
            should_cancel=late_check,
        )

    assert result.status == "completed"
    assert "cancel" not in client.kinds()
