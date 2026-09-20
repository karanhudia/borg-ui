"""Which output lines the agent stores as job log rows (agent 0.1.8).

A line that is reported as progress is not stored as a log line too, and a
machine-parsed kind logs one summary line instead of its JSON output.
"""

import json
import os
import sys

import pytest

from agent.borg_ui_agent import backup
from agent.borg_ui_agent.backup import execute_backup_create_job
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    _execute_restore_operation,
    _execute_short_repository_operation,
    _execute_streaming_repository_operation,
)

pytestmark = pytest.mark.unit


class RecordingClient:
    def __init__(self):
        self.logs: list[tuple[int, str, str]] = []
        self.progress: list[dict] = []
        self.completed: list[dict] = []
        self.failed: list[str] = []

    def send_log(self, job_id, *, sequence, stream, message):
        self.logs.append((sequence, stream, message))

    def send_progress(self, job_id, progress):
        self.progress.append(progress)

    def complete_job(self, job_id, *, result):
        self.completed.append(result)

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.failed.append(error_message)

    def cancel_job(self, job_id):
        raise AssertionError("not cancelled")

    def messages(self) -> list[str]:
        return [message for _, _, message in self.logs]

    def sequences(self) -> list[int]:
        return [sequence for sequence, _, _ in self.logs]


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
    """A command that prints `lines` on `stream` and exits `return_code`."""
    script = (
        "import sys\n"
        f"for line in {lines!r}:\n"
        f"    print(line, file=sys.{stream}, flush=True)\n"
        f"sys.exit({return_code})\n"
    )
    return [sys.executable, "-c", script]


def _percent(current, total=100, *, finished=False, info=None):
    return json.dumps(
        {
            "type": "progress_percent",
            "operation": 1,
            "msgid": "compact",
            "message": f"Compacting segments {current}%",
            "current": current,
            "total": total,
            "info": info,
            "finished": finished,
        }
    )


def _log_message(message, *, name="borg.archiver"):
    return json.dumps(
        {
            "type": "log_message",
            "levelname": "INFO",
            "name": name,
            "message": message,
        }
    )


def test_progress_lines_of_a_streamed_operation_are_not_log_rows():
    pruned = _log_message(
        "Pruning archive (1/1):                host-2026-01-01 "
        "Thu, 2026-01-01 00:00:00 [abc]",
        name="borg.output.list",
    )
    client = RecordingClient()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.prune"),
        client,
        _prints([_percent(10), pruned, _percent(50), "plain line", _percent(100)]),
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
    )

    assert result.status == "completed"
    assert client.messages() == [pruned, "plain line"]
    assert client.sequences() == [1, 2]
    assert client.progress == [
        {"progress_percent": 10.0},
        {"progress_percent": 50.0},
        {"progress_percent": 100.0},
    ]


def test_compact_statistics_are_parsed_with_progress_lines_in_between():
    stats = [
        _log_message(
            "Overall statistics, considering all 3 archives in this repository:"
        ),
        _log_message("Source data size was 1000 B in 4 files."),
        _log_message("Deduplicated size is 600 B."),
        _log_message("Deduplication factor is 1.67."),
        _log_message("Repository size is 300 B in 9 objects."),
        _log_message("Compression factor is 2.00."),
    ]
    client = RecordingClient()

    result = _execute_streaming_repository_operation(
        7,
        _payload("repository.compact", borg_version=2),
        client,
        _prints([_percent(50), *stats, _percent(100, finished=True)]),
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
        compact_stats=True,
    )

    assert result.status == "completed"
    assert client.completed[0]["stats"]["repository_size"] == 300
    assert client.messages() == stats
    assert client.sequences() == list(range(1, len(stats) + 1))
    assert client.progress == [{"progress_percent": 50.0}, {"progress_percent": 100.0}]


def test_progress_lines_of_a_restore_are_not_log_rows(tmp_path):
    warning = _log_message("file: Permission denied")
    client = RecordingClient()

    result = _execute_restore_operation(
        7,
        _payload(
            "repository.restore",
            operation={
                "archive": "a",
                "target": {"type": "path", "path": str(tmp_path)},
            },
        ),
        client,
        _prints([_percent(1, 4, info=["etc/hosts"]), warning, _percent(4, 4)]),
        dict(os.environ),
        initial_sequence=1,
        should_cancel=lambda: False,
    )

    assert result.status == "completed"
    assert client.logs == [(1, "stdout", warning)]
    # the file an extract is at travels with the progress, not in a log row
    assert client.progress == [
        {"progress_percent": 25.0, "current_file": "etc/hosts"},
        {"progress_percent": 100.0},
    ]


def test_a_backup_stores_the_file_listing_but_not_its_progress(monkeypatch):
    archive_progress = json.dumps(
        {
            "type": "archive_progress",
            "original_size": 10,
            "compressed_size": 5,
            "deduplicated_size": 2,
            "nfiles": 1,
            "path": "src/a",
        }
    )
    # `create --list`: the listing the operator asked for, and the current file
    listed = json.dumps({"type": "file_status", "status": "A", "path": "src/a"})
    summary = _log_message("Archive name: archive")
    monkeypatch.setattr(
        backup.BackupCreatePayload,
        "build_command",
        lambda self: _prints([archive_progress, listed, summary], stream="stderr"),
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

    assert result.status == "completed"
    assert client.messages()[1:] == [listed, summary]
    assert client.sequences() == [0, 1, 2]
    assert client.progress == [
        {
            "original_size": 10,
            "compressed_size": 5,
            "deduplicated_size": 2,
            "nfiles": 1,
            "current_file": "src/a",
        },
        {"current_file": "src/a"},
    ]


@pytest.mark.parametrize(
    ("job_kind", "document", "summary"),
    [
        (
            "repository.list_archives",
            {"archives": [{"name": "a"}, {"name": "b"}], "repository": {}},
            "list_archives: 2 archives, rc 0",
        ),
        ("repository.info", {"repository": {"id": "x"}}, None),
        ("repository.rinfo", {"repository": {"id": "x"}}, None),
        ("repository.archive_info", {"archives": [{"name": "a"}]}, None),
    ],
)
def test_a_machine_parsed_kind_logs_a_summary(job_kind, document, summary):
    stdout = json.dumps(document, indent=4)
    client = RecordingClient()

    result = _execute_short_repository_operation(
        7, _payload(job_kind), client, _prints([stdout]), dict(os.environ)
    )

    assert result.status == "completed"
    name = job_kind.removeprefix("repository.")
    expected = summary or f"{name}: {len(stdout) + 1} characters of JSON, rc 0"
    assert client.logs == [(1, "stdout", expected)]
    # the server still gets the output itself, in the completion report
    assert client.completed[0]["stdout"] == stdout + "\n"
    assert client.completed[0]["data"] == document


def test_only_a_parsed_success_is_summarized():
    """What Borg printed stays in the log where the server or an operator
    needs it: a failed run (the server builds its error message from these
    rows), output that did not parse, and a warning's stderr."""
    listing = json.dumps({"archives": []})
    payload = _payload("repository.list_archives")

    failed = RecordingClient()
    script = (
        "import sys\n"
        "print('usage: borg list: invalid choice')\n"
        "print('Repository /agent/repo does not exist.', file=sys.stderr)\n"
        "sys.exit(2)\n"
    )
    _execute_short_repository_operation(
        7, payload, failed, [sys.executable, "-c", script], dict(os.environ)
    )
    assert failed.logs == [
        (1, "stdout", "usage: borg list: invalid choice"),
        (2, "stderr", "Repository /agent/repo does not exist."),
    ]
    assert failed.failed == ["repository.list_archives exited with code 2"]

    unparsed = RecordingClient()
    _execute_short_repository_operation(
        7, payload, unparsed, _prints(["not json"]), dict(os.environ)
    )
    assert unparsed.logs == [(1, "stdout", "not json")]

    warned = RecordingClient()
    script = (
        "import sys\n"
        f"print({listing!r})\n"
        "print('Warning: something', file=sys.stderr)\n"
        "sys.exit(1)\n"
    )
    result = _execute_short_repository_operation(
        7, payload, warned, [sys.executable, "-c", script], dict(os.environ)
    )
    assert result.status == "completed_with_warnings"
    assert warned.logs == [
        (1, "stdout", "list_archives: 0 archives, rc 1"),
        (2, "stderr", "Warning: something"),
    ]


def test_other_short_kinds_keep_their_output():
    """Only the kinds whose output the server parses are summarized; an
    archive delete's output is the transcript."""
    passing = RecordingClient()
    _execute_short_repository_operation(
        7,
        _payload("repository.list_archives"),
        passing,
        _prints([json.dumps({"archives": []})]),
        dict(os.environ),
    )
    assert passing.messages() == ["list_archives: 0 archives, rc 0"]

    client = RecordingClient()
    _execute_short_repository_operation(
        7,
        _payload("repository.delete_archive", operation={"archive": "a"}),
        client,
        _prints([json.dumps({"deleted": "a"})]),
        dict(os.environ),
    )
    assert client.messages() == [json.dumps({"deleted": "a"})]
