"""A failed Borg run reports Borg's last lines and whether a lock another
process holds ended it, in the failure report itself (agent 0.1.10, #1056)."""

import json
import os
import sys

import pytest

from agent.borg_ui_agent import backup
from agent.borg_ui_agent.backup import execute_backup_create_job
from agent.borg_ui_agent.failure_report import (
    FAILURE_KIND_LOCK_CONTENTION,
    FAILURE_KIND_OTHER,
    FAILURE_TAIL_CHARS,
    FAILURE_TAIL_LINES,
    failure_kind,
    failure_report,
    failure_tail,
    plain_line,
)
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    _execute_limited_output_repository_operation,
    _execute_restore_operation,
    _execute_short_repository_operation,
    _execute_streaming_repository_operation,
)

pytestmark = pytest.mark.unit

LOCK_LINE = "Failed to create/acquire the lock /repo/lock.exclusive (timeout)."


class RecordingClient:
    def __init__(self):
        self.failed: list[dict] = []
        self.completed: list[dict] = []

    def send_log(self, job_id, *, sequence, stream, message):
        pass

    def send_progress(self, job_id, progress):
        pass

    def complete_job(self, job_id, *, result):
        self.completed.append(result)

    def fail_job(self, job_id, *, error_message, return_code=None, **report):
        self.failed.append(
            {"error_message": error_message, "return_code": return_code, **report}
        )

    def cancel_job(self, job_id):
        raise AssertionError("not cancelled")


def _payload(job_kind, *, borg_version=1, operation=None):
    return RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": job_kind,
            "repository": {"path": "/agent/repo", "borg_version": borg_version},
            "operation": operation,
        }
    )


def _prints(lines, *, stream="stdout", return_code=0):
    script = (
        "import sys\n"
        f"for line in {lines!r}:\n"
        f"    print(line, file=sys.{stream}, flush=True)\n"
        f"sys.exit({return_code})\n"
    )
    return [sys.executable, "-c", script]


def _log_message(message, *, levelname="ERROR"):
    return json.dumps(
        {
            "type": "log_message",
            "levelname": levelname,
            "name": "borg.archiver",
            "message": message,
        }
    )


def _percent(current):
    return json.dumps(
        {
            "type": "progress_percent",
            "operation": 1,
            "msgid": "compact",
            "message": f"Compacting {current}%",
            "current": current,
            "total": 100,
            "finished": False,
        }
    )


# -- the report itself ---------------------------------------------------------


def test_a_log_json_line_reads_as_its_message_and_progress_reads_as_nothing():
    assert plain_line(_log_message(LOCK_LINE)) == LOCK_LINE
    assert plain_line(_percent(3)) is None
    # a progress step printed through the progress logger is no reason either
    step = json.dumps(
        {
            "type": "log_message",
            "levelname": "INFO",
            "name": "borg.output.progress",
            "message": "Saving chunks cache",
        }
    )
    assert plain_line(step) is None
    assert plain_line("plain text\n") == "plain text"
    # not one of borg's documents: kept as it is
    assert plain_line('{"unexpected": true}') == '{"unexpected": true}'
    assert plain_line("{not json") == "{not json"


def test_the_tail_is_bounded_in_lines_and_in_characters():
    lines = [f"line {index}" for index in range(FAILURE_TAIL_LINES + 10)]
    tail = failure_tail(lines)
    assert tail.splitlines() == lines[-FAILURE_TAIL_LINES:]

    # a single line beyond the bound is not sent: any cut through it could
    # leave a credential in a location unrecognisable to the redaction
    overlong = "x" * (FAILURE_TAIL_CHARS - 17) + " ssh://user:s3cret@host/repo"
    long_tail = failure_tail([overlong])
    assert "s3cret" not in long_tail
    assert long_tail == f"[a line of {len(overlong)} characters was left out]"
    # ... and the lines before it stay: the reason ahead of an oversized
    # traceback line is what the operator needs
    tail = failure_tail(["the reason", overlong, "PID: 4242  CWD: /"])
    assert tail == (
        f"the reason\n[a line of {len(overlong)} characters was left out]"
        "\nPID: 4242  CWD: /"
    )

    # the character bound cuts between lines, never through one: the
    # server redacts a location with credentials, and a cut through it
    # could take the scheme it is recognised by
    url_line = "Repository ssh://user:s3cret@host/repo does not exist."
    tail = failure_tail([url_line, "x" * 3000, "y" * 3000])
    assert tail == "y" * 3000
    tail = failure_tail([url_line, "x" * 2040, "y" * 2040])
    assert tail == "x" * 2040 + "\n" + "y" * 2040

    # empty lines and progress events are not part of what borg said
    assert failure_tail(["", _percent(1), "  ", "the reason"]) == "the reason"


@pytest.mark.parametrize(
    ("return_code", "tail", "kind"),
    [
        (70, "", FAILURE_KIND_LOCK_CONTENTION),
        (71, "", FAILURE_KIND_LOCK_CONTENTION),
        (73, "", FAILURE_KIND_LOCK_CONTENTION),
        # LockFailed: the lock file cannot be created, waiting changes nothing
        (72, "", FAILURE_KIND_OTHER),
        # NotLocked / NotMyLock: no lock to wait for
        (74, "", FAILURE_KIND_OTHER),
        (75, "", FAILURE_KIND_OTHER),
        # legacy exit codes: Borg 1 says it in words
        (2, LOCK_LINE, FAILURE_KIND_LOCK_CONTENTION),
        (None, LOCK_LINE, FAILURE_KIND_LOCK_CONTENTION),
        # a modern code names the first error; a later timeout line does
        # not turn a lock file that could not be created into contention
        (72, LOCK_LINE, FAILURE_KIND_OTHER),
        (12, LOCK_LINE, FAILURE_KIND_OTHER),
        (
            2,
            "Failed to create/acquire the lock /repo/lock.exclusive "
            "([Errno 13] Permission denied: '/repo/lock.exclusive').",
            FAILURE_KIND_OTHER,
        ),
        (2, "Repository /repo does not exist.", FAILURE_KIND_OTHER),
        # "(timeout)" inside the path is not the reason at the line's end
        (
            2,
            "Failed to create/acquire the lock /backups/(timeout)/repo/"
            "lock.exclusive ([Errno 13] Permission denied).",
            FAILURE_KIND_OTHER,
        ),
        (2, f"usage: borg\n{LOCK_LINE}\nterminating", FAILURE_KIND_LOCK_CONTENTION),
        (None, "", FAILURE_KIND_OTHER),
        # Borg 2: a lock of the run's own, killed meanwhile - the same exit
        # code and line, but no run to wait for
        (
            73,
            f"{LOCK_LINE} Our lock was killed by another borg (it considered "
            "our lock stale) - there is no safe way to continue.",
            FAILURE_KIND_OTHER,
        ),
    ],
)
def test_lock_contention_by_exit_code_or_by_borgs_words(return_code, tail, kind):
    assert failure_kind(return_code, tail) == kind


def test_the_report_has_both_fields():
    assert failure_report(2, f"usage: borg\n{LOCK_LINE}\n") == {
        "stderr_tail": f"usage: borg\n{LOCK_LINE}",
        "failure_kind": FAILURE_KIND_LOCK_CONTENTION,
    }


def test_the_kind_survives_the_character_bound():
    """A lock line longer than the tail's character bound loses its head in
    the report, not its classification."""
    long_lock_line = (
        "Failed to create/acquire the lock /"
        + "d" * (FAILURE_TAIL_CHARS + 100)
        + "/lock.exclusive (timeout)."
    )
    report = failure_report(2, long_lock_line)
    assert report["failure_kind"] == FAILURE_KIND_LOCK_CONTENTION
    assert report["stderr_tail"].startswith("[a line of ")


# -- the executors report it ---------------------------------------------------


def test_a_short_operation_reports_borgs_stderr():
    client = RecordingClient()

    result = _execute_short_repository_operation(
        7,
        _payload("repository.list_archives"),
        client,
        _prints([LOCK_LINE], stream="stderr", return_code=2),
        dict(os.environ),
    )

    assert result.status == "failed"
    assert client.failed == [
        {
            "error_message": "repository.list_archives exited with code 2",
            "return_code": 2,
            "stderr_tail": LOCK_LINE,
            "failure_kind": FAILURE_KIND_LOCK_CONTENTION,
        }
    ]


def test_a_short_operation_falls_back_to_stdout_for_an_argument_error():
    client = RecordingClient()

    _execute_short_repository_operation(
        7,
        _payload("repository.init", borg_version=2),
        client,
        _prints(
            ["usage: borg2 repo-create", "error: invalid choice: 'x'"],
            return_code=2,
        ),
        dict(os.environ),
    )

    assert client.failed[0]["stderr_tail"] == (
        "usage: borg2 repo-create\nerror: invalid choice: 'x'"
    )
    assert client.failed[0]["failure_kind"] == FAILURE_KIND_OTHER


def test_a_limited_output_operation_reports_borgs_stderr():
    client = RecordingClient()

    _execute_limited_output_repository_operation(
        7,
        _payload("repository.list_archive_contents", operation={"archive": "a"}),
        client,
        _prints([LOCK_LINE], stream="stderr", return_code=73),
        dict(os.environ),
    )

    assert client.failed[0]["stderr_tail"] == LOCK_LINE
    assert client.failed[0]["failure_kind"] == FAILURE_KIND_LOCK_CONTENTION


def test_a_streamed_operation_reports_the_decoded_tail():
    client = RecordingClient()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.prune"),
        client,
        _prints([_percent(10), _log_message(LOCK_LINE), _percent(20)], return_code=2),
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
    )

    assert result.status == "failed"
    assert client.failed[0]["stderr_tail"] == LOCK_LINE
    assert client.failed[0]["failure_kind"] == FAILURE_KIND_LOCK_CONTENTION


def test_progress_events_after_the_error_do_not_push_it_out():
    """Borg prints dozens of progress events between two messages; the
    reason must not fall out of the bounded tail behind them."""
    client = RecordingClient()

    _execute_streaming_repository_operation(
        7,
        _payload("repository.compact", borg_version=2),
        client,
        _prints(
            [_log_message(LOCK_LINE), *(_percent(i) for i in range(100))],
            return_code=73,
        ),
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
        compact_stats=True,
    )

    assert client.failed[0]["stderr_tail"] == LOCK_LINE
    assert client.failed[0]["failure_kind"] == FAILURE_KIND_LOCK_CONTENTION


def test_a_restore_reports_the_decoded_tail(tmp_path):
    client = RecordingClient()

    _execute_restore_operation(
        7,
        _payload(
            "repository.restore",
            operation={
                "archive": "a",
                "target": {"type": "path", "path": str(tmp_path)},
            },
        ),
        client,
        _prints([_log_message("Archive a does not exist")], return_code=2),
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
    )

    assert client.failed[0]["stderr_tail"] == "Archive a does not exist"
    assert client.failed[0]["failure_kind"] == FAILURE_KIND_OTHER


def test_a_backup_reports_the_decoded_tail(monkeypatch):
    monkeypatch.setattr(
        backup.BackupCreatePayload,
        "build_command",
        lambda self: _prints(
            [_percent(5), _log_message(LOCK_LINE)], stream="stderr", return_code=73
        ),
    )
    client = RecordingClient()

    result = execute_backup_create_job(
        {
            "id": 11,
            "payload": {
                "job_kind": "backup.create",
                "repository_path": "/repo",
                "archive_name": "archive",
                "source_paths": ["/src"],
            },
        },
        client,
    )

    assert result.status == "failed"
    assert client.failed == [
        {
            "error_message": "borg create exited with code 73",
            "return_code": 73,
            "stderr_tail": LOCK_LINE,
            "failure_kind": FAILURE_KIND_LOCK_CONTENTION,
        }
    ]
