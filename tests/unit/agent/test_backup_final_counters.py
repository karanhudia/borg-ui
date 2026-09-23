"""A backup's final counters travel with its completion (agent 0.1.9, #1125).

Borg reports `archive_progress` at most once a second and its last one
carries no counters, so the progress reports never hold the final figures;
`borg create --json` prints them as `archive.stats`.
"""

import json
import sys

import pytest

from agent.borg_ui_agent import backup
from agent.borg_ui_agent.backup import execute_backup_create_job

pytestmark = pytest.mark.unit

# As `borg create --progress --json --log-json` (Borg 1.4.5) printed them
EARLY_PROGRESS = json.dumps(
    {
        "original_size": 0,
        "compressed_size": 0,
        "deduplicated_size": 0,
        "nfiles": 0,
        "path": "src",
        "type": "archive_progress",
        "finished": False,
    }
)
FINISHED = json.dumps({"type": "archive_progress", "finished": True})


class RecordingClient:
    def __init__(self):
        self.progress: list[dict] = []
        self.completed: list[dict] = []

    def send_log(self, job_id, *, sequence, stream, message):
        pass

    def send_progress(self, job_id, progress):
        self.progress.append(progress)

    def complete_job(self, job_id, *, result):
        self.completed.append(result)

    def fail_job(self, job_id, *, error_message, return_code=None):
        raise AssertionError(error_message)

    def cancel_job(self, job_id):
        raise AssertionError("not cancelled")


def _borg_create(stdout: str, *, return_code=0):
    """A command that reports progress on stderr, then prints `stdout`."""
    script = (
        "import sys\n"
        f"for line in {[EARLY_PROGRESS, FINISHED]!r}:\n"
        "    print(line, file=sys.stderr, flush=True)\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({return_code})\n"
    )
    return [sys.executable, "-c", script]


def _run(monkeypatch, stdout: str, *, return_code=0) -> RecordingClient:
    monkeypatch.setattr(
        backup.BackupCreatePayload,
        "build_command",
        lambda self: _borg_create(stdout, return_code=return_code),
    )
    client = RecordingClient()
    execute_backup_create_job(
        {
            "id": 11,
            "payload": {
                "job_kind": "backup.create",
                "repository_path": "/repo",
                "archive_name": "host-{now}",
                "source_paths": ["/src"],
            },
        },
        client,
    )
    return client


def _document(stats) -> str:
    return json.dumps({"archive": {"name": "host-2026-09-23", "stats": stats}})


def test_the_completion_carries_the_final_counters(monkeypatch):
    stats = {
        "compressed_size": 600009,
        "deduplicated_size": 600009,
        "nfiles": 3,
        "original_size": 600000,
    }

    client = _run(monkeypatch, _document(stats))

    # what the progress reports said last is not what the archive holds
    assert client.progress[-1] == {"progress_percent": 100.0}
    assert client.completed[0]["archive_name"] == "host-2026-09-23"
    assert client.completed[0]["archive_stats"] == stats


def test_a_warning_run_carries_them_too(monkeypatch):
    client = _run(monkeypatch, _document({"nfiles": 2}), return_code=1)

    assert client.completed[0]["return_code"] == 1
    assert client.completed[0]["archive_stats"] == {"nfiles": 2}


def test_only_the_counters_borg_reported_are_carried(monkeypatch):
    """Borg 2 has no compressed or deduplicated size in `archive.stats`."""
    stats = {
        "original_size": 600000,
        "nfiles": 3,
        "hashing_time": 0.01,
        "compressed_size": "600009",
        "deduplicated_size": True,
    }

    client = _run(monkeypatch, _document(stats))

    assert client.completed[0]["archive_stats"] == {
        "original_size": 600000,
        "nfiles": 3,
    }


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "not json",
        json.dumps(["archive"]),
        json.dumps({"archive": {"name": "host-2026-09-23"}}),
        _document({"hashing_time": 0.01}),
    ],
)
def test_no_counters_no_key(monkeypatch, stdout):
    client = _run(monkeypatch, stdout)

    assert "archive_stats" not in client.completed[0]
