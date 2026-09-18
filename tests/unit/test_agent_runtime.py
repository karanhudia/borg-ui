import base64
import json
import os
import queue
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.borg_ui_agent import __version__
from agent.borg_ui_agent.backup import (
    BackupCreatePayload,
    build_borg_env,
    execute_backup_create_job,
    parse_borg_progress,
)
from agent.borg_ui_agent.borg import detect_borg_binaries
from agent.borg_ui_agent.client import AGENT_AUTH_HEADER, AgentClient
from agent.borg_ui_agent.config import AgentConfig, load_config, save_config
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    RepositoryOperationResult,
    execute_repository_operation_job,
    _write_temp_rclone_config,
)
from agent.borg_ui_agent.runtime import AgentRuntime, get_capabilities


def _drain(outbox):
    """Return every frame a worker queued for the session thread."""
    frames = []
    while not outbox.empty():
        frames.append(outbox.get_nowait())
    return frames


class FakeWebSocket:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.closed = False
        self.pings = 0
        self.timeout = None
        self.send_timeouts = []

    def settimeout(self, timeout):
        self.timeout = timeout

    def send(self, payload):
        # The socket timeout bounds writes too, so record what was in force for
        # each one: a write must never run under the short recv poll interval.
        self.send_timeouts.append(self.timeout)
        self.sent.append(json.loads(payload))

    def recv(self):
        if not self.incoming:
            raise EOFError("closed")
        item = self.incoming.pop(0)
        if isinstance(item, BaseException):
            raise item
        return json.dumps(item)

    def ping(self):
        self.pings += 1

    def close(self):
        self.closed = True


class RecordingHttpClient:
    """Records the REST terminal-delivery calls the session makes (results,
    errors and cancels now go over the job API instead of the WebSocket)."""

    def __init__(self):
        self.completed = []
        self.failed = []
        self.canceled = []

    def complete_job(self, job_id, *, result):
        self.completed.append((job_id, result))
        return {"id": job_id, "status": "completed"}

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.failed.append((job_id, error_message, return_code))
        return {"id": job_id, "status": "failed"}

    def cancel_job(self, job_id):
        self.canceled.append(job_id)
        return {"id": job_id, "status": "canceled"}


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self.payload = payload or {}
        self.status_code = status_code
        self.text = text
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "json": json,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)


@pytest.fixture
def patch_session_platform(monkeypatch):
    """Stub the platform / borg detection the session runtime runs on hello."""
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])


@pytest.mark.unit
def test_save_and_load_config(tmp_path: Path):
    config_path = tmp_path / "agent" / "config.toml"
    config = AgentConfig(
        server_url="https://borgui.example.com/",
        agent_id="agt_123",
        agent_token="borgui_agent_secret",
        name="laptop",
    )

    written = save_config(config, config_path)
    loaded = load_config(written)

    assert loaded == AgentConfig(
        server_url="https://borgui.example.com",
        agent_id="agt_123",
        agent_token="borgui_agent_secret",
        name="laptop",
    )
    assert written.stat().st_mode & 0o777 == 0o600


@pytest.mark.unit
def test_detect_borg_binaries(monkeypatch):
    paths = {"borg": "/usr/bin/borg", "borg2": "/custom/bin/borg2"}

    def fake_which(name):
        return paths.get(name)

    def fake_run(command, check, capture_output, text, timeout):
        if command[0].endswith("borg2"):
            return SimpleNamespace(stdout="borg 2.0.0b10", stderr="")
        return SimpleNamespace(stdout="borg 1.2.8", stderr="")

    monkeypatch.setattr("agent.borg_ui_agent.borg.shutil.which", fake_which)
    monkeypatch.setattr("agent.borg_ui_agent.borg.subprocess.run", fake_run)

    detected = detect_borg_binaries()

    assert [binary.to_api_payload() for binary in detected] == [
        {
            "major": 1,
            "version": "1.2.8",
            "path": "/usr/bin/borg",
            "install_source": "system-package",
        },
        {
            "major": 2,
            "version": "2.0.0b10",
            "path": "/custom/bin/borg2",
            "install_source": "custom-path",
        },
    ]


@pytest.mark.unit
def test_agent_client_register_and_authenticated_request_headers():
    session = FakeSession(
        [
            FakeResponse({"agent_id": "agt_123", "agent_token": "secret"}),
            FakeResponse({"jobs": []}),
        ]
    )
    client = AgentClient(
        "https://borgui.example.com/",
        agent_token="borgui_agent_secret",
        session=session,
    )

    registered = client.register(
        enrollment_token="borgui_enroll_secret",
        name="laptop",
        hostname="laptop.local",
        os_name="linux",
        arch="amd64",
        agent_version="0.1.1",
        borg_versions=[],
        capabilities=["jobs.poll"],
    )
    jobs = client.poll_jobs()

    assert registered["agent_id"] == "agt_123"
    assert jobs == {"jobs": []}
    assert (
        session.requests[0]["url"] == "https://borgui.example.com/api/agents/register"
    )
    assert AGENT_AUTH_HEADER not in session.requests[0]["headers"]
    assert (
        session.requests[1]["url"]
        == "https://borgui.example.com/api/agents/jobs/poll?limit=1"
    )
    assert (
        session.requests[1]["headers"][AGENT_AUTH_HEADER]
        == "Bearer borgui_agent_secret"
    )


@pytest.mark.unit
def test_agent_client_retries_transient_report_failure():
    session = FakeSession(
        [
            FakeResponse({"error": "busy"}, status_code=503, text="busy"),
            FakeResponse({"id": 7, "status": "completed"}),
        ]
    )
    client = AgentClient(
        "https://borgui.example.com/",
        agent_token="borgui_agent_secret",
        session=session,
    )

    response = client.complete_job(7, result={"archive_name": "archive"})

    assert response == {"id": 7, "status": "completed"}
    assert [request["method"] for request in session.requests] == ["POST", "POST"]


@pytest.mark.unit
def test_backup_create_payload_builds_borg1_command():
    payload = BackupCreatePayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "backup.create",
            "repository": {
                "path": "/backup/repo",
                "borg_version": 1,
                "borg_binary": "/usr/bin/borg",
                "remote_path": "/usr/local/bin/borg",
            },
            "backup": {
                "archive_name": "laptop-2026-05-11",
                "source_paths": ["/home/user/docs"],
                "exclude_patterns": ["*.tmp"],
                "compression": "zstd",
                "custom_flags": "--one-file-system",
            },
            "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
        }
    )

    assert payload.environment == {"BORG_PASSPHRASE": "secret"}
    assert payload.build_command() == [
        "/usr/bin/borg",
        "create",
        "--progress",
        "--stats",
        "--json",
        "--show-rc",
        "--log-json",
        "--compression",
        "zstd",
        "--remote-path",
        "/usr/local/bin/borg",
        "--exclude",
        "*.tmp",
        "--one-file-system",
        "/backup/repo::laptop-2026-05-11",
        "/home/user/docs",
    ]


@pytest.mark.unit
def test_backup_create_payload_builds_borg2_command_from_flat_payload():
    payload = BackupCreatePayload.from_job_payload(
        {
            "job_kind": "backup.create",
            "borg_version": 2,
            "borg_binary": "borg2",
            "repository_path": "/backup/repo",
            "archive_name": "laptop",
            "source_paths": ["/src"],
            "compression": "none",
            "custom_flags": ["--list"],
            "upload_ratelimit_kib": 1536,
        }
    )

    assert payload.build_command() == [
        "borg2",
        "--progress",
        "--show-rc",
        "--log-json",
        "-r",
        "/backup/repo",
        "create",
        "--stats",
        "--json",
        "--compression",
        "none",
        "--upload-ratelimit",
        "1536",
        "--list",
        "laptop",
        "/src",
    ]


@pytest.mark.unit
def test_parse_borg_progress_frames():
    assert parse_borg_progress(
        '{"type":"archive_progress","original_size":1024,"compressed_size":512,'
        '"deduplicated_size":128,"nfiles":3,"path":"/src/file"}'
    ) == {
        "original_size": 1024,
        "compressed_size": 512,
        "deduplicated_size": 128,
        "nfiles": 3,
        "current_file": "/src/file",
    }
    assert parse_borg_progress('{"type":"progress_percent","current":2,"total":4}') == {
        "progress_percent": 50.0
    }
    assert parse_borg_progress("not-json") is None


class FakeRuntimeClient:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = []

    def heartbeat(self, **kwargs):
        self.calls.append(("heartbeat", kwargs))
        return {"cancel_job_ids": []}

    def poll_jobs(self, *, limit=1):
        self.calls.append(("poll_jobs", {"limit": limit}))
        return {"jobs": self.jobs}

    def claim_job(self, job_id):
        self.calls.append(("claim_job", job_id))
        return {"id": job_id, "status": "claimed"}

    def start_job(self, job_id):
        self.calls.append(("start_job", job_id))
        return {"id": job_id, "status": "running"}

    def send_log(self, job_id, *, sequence, message, stream="stdout"):
        self.calls.append(("send_log", job_id, sequence, stream, message))
        return {"accepted": True}

    def send_progress(self, job_id, progress):
        self.calls.append(("send_progress", job_id, progress))
        return {"id": job_id, "status": "running"}

    def complete_job(self, job_id, *, result):
        self.calls.append(("complete_job", job_id, result))
        return {"id": job_id, "status": "completed"}

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.calls.append(("fail_job", job_id, error_message, return_code))
        return {"id": job_id, "status": "failed"}


@pytest.mark.unit
def test_runtime_run_once_idles_when_no_jobs(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.detect_platform",
        lambda: {"hostname": "host", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.runtime.detect_borg_binaries", lambda: [])
    client = FakeRuntimeClient([])
    runtime = AgentRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        client=client,
    )

    result = runtime.run_once()

    assert result.job_id is None
    assert result.status == "idle"
    assert [call[0] for call in client.calls] == ["heartbeat", "poll_jobs"]


@pytest.mark.unit
def test_runtime_run_once_fails_unsupported_job(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.detect_platform",
        lambda: {"hostname": "host", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.runtime.detect_borg_binaries", lambda: [])
    client = FakeRuntimeClient(
        [{"id": 42, "type": "check", "payload": {"job_kind": "check.run"}}]
    )
    runtime = AgentRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        client=client,
    )

    result = runtime.run_once()

    assert result.job_id == 42
    assert result.status == "failed"
    assert [call[0] for call in client.calls] == [
        "heartbeat",
        "poll_jobs",
        "claim_job",
        "start_job",
        "send_log",
        "fail_job",
    ]


@pytest.mark.unit
def test_runtime_run_once_dispatches_backup_create(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.detect_platform",
        lambda: {"hostname": "host", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.runtime.detect_borg_binaries", lambda: [])

    executed_jobs = []

    def fake_execute(job, client, *, should_cancel=None):
        executed_jobs.append((job, client))
        assert callable(should_cancel)
        return SimpleNamespace(
            job_id=43,
            status="completed",
            return_code=0,
            message="borg create exited with code 0",
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.execute_backup_create_job", fake_execute
    )
    client = FakeRuntimeClient(
        [{"id": 43, "type": "backup", "payload": {"job_kind": "backup.create"}}]
    )
    runtime = AgentRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        client=client,
    )

    result = runtime.run_once()

    assert result.job_id == 43
    assert result.status == "completed"
    assert executed_jobs[0][0]["id"] == 43
    assert executed_jobs[0][1] is client
    assert [call[0] for call in client.calls] == [
        "heartbeat",
        "poll_jobs",
        "claim_job",
        "start_job",
    ]


@pytest.mark.unit
def test_runtime_run_once_dispatches_registered_structured_handler(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.detect_platform",
        lambda: {"hostname": "host", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.runtime.detect_borg_binaries", lambda: [])

    handled_jobs = []

    def fake_handler(job, client, *, should_cancel=None):
        handled_jobs.append((job, client, should_cancel))
        return SimpleNamespace(job_id=44, status="completed", message="info complete")

    import agent.borg_ui_agent.runtime as runtime_module

    monkeypatch.setitem(runtime_module.JOB_HANDLERS, "repository.info", fake_handler)
    client = FakeRuntimeClient(
        [{"id": 44, "type": "repository", "payload": {"job_kind": "repository.info"}}]
    )
    runtime = AgentRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        client=client,
    )

    result = runtime.run_once()

    assert result.job_id == 44
    assert result.status == "completed"
    assert handled_jobs[0][0]["id"] == 44
    assert handled_jobs[0][1] is client
    assert callable(handled_jobs[0][2])


@pytest.mark.unit
def test_runtime_advertises_repository_rclone_sync_capability():
    assert "repository.rclone_sync" in get_capabilities()


@pytest.mark.unit
def test_runtime_advertises_repository_init_capability_and_handler():
    import agent.borg_ui_agent.runtime as runtime_module

    assert "repository.init" in get_capabilities()
    assert "repository.init" in runtime_module.JOB_HANDLERS


@pytest.mark.unit
def test_runtime_advertises_diagnostics_capability():
    assert "diagnostics.run" in get_capabilities()


@pytest.mark.unit
def test_repository_init_payload_builds_borg1_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.init",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"encryption": "repokey"},
        }
    )

    command = payload.build_command()

    assert command == ["borg", "init", "--encryption", "repokey", "/agent/repo"]


@pytest.mark.unit
def test_repository_init_disables_the_store_cache(monkeypatch):
    """repo-create must not create/validate the shared pack cache — borgstore
    rejects a populated cache directory and borg misreports that as
    "repository already exists"."""
    monkeypatch.setenv("BORG_STORE_CACHE", "1")
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            self.returncode = 0
            self.stdout = []

        def wait(self):
            return 0

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", _FakePopen
    )

    class _Client:
        def send_log(self, job_id, *, sequence, message, stream="stdout"):
            pass

        def send_progress(self, job_id, progress):
            pass

        def complete_job(self, job_id, *, result):
            pass

        def fail_job(self, job_id, *, error_message, return_code=None):
            pass

    job = {
        "id": 7,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.init",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
            "operation": {"encryption": "repokey-aes-ocb"},
        },
    }

    result = execute_repository_operation_job(job, _Client(), should_cancel=None)

    assert result.status == "completed"
    assert captured["env"]["BORG_STORE_CACHE"] == ""


@pytest.mark.unit
def test_borg2_compact_reports_its_statistics_in_the_completion(monkeypatch):
    """A Borg 2 compact runs with --stats under BORG_UNITS=raw; the agent
    parses the statistics from the tail of its own output and sends them
    with the completion report, so the server does not depend on the log
    lines that queue behind it."""
    from agent.borg_ui_agent import repository_ops

    monkeypatch.setattr(repository_ops, "compact_stats_supported", lambda binary: True)
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            self.returncode = 0
            # a long run: more lines than the tail keeps precede the
            # statistics, which Borg prints last and the tail therefore holds
            self.stdout = iter(
                ["Starting compaction / garbage collection...\n"]
                + [
                    f'{{"type": "progress_percent", "current": {i}}}\n'
                    for i in range(100)
                ]
                + [
                    '{"type": "log_message", "levelname": "INFO", "name": '
                    '"borg.archiver.compact_cmd", "message": '
                    '"Repository size is 502000 B in 6 objects."}\n',
                    "Compaction saved 0 B.\n",
                ]
                # progress frames that flush after the block still fit the tail
                + [
                    f'{{"type": "progress_percent", "finished": true, "n": {i}}}\n'
                    for i in range(50)
                ]
            )

        def wait(self):
            return 0

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", _FakePopen
    )

    class _Client:
        def send_log(self, job_id, *, sequence, message, stream="stdout"):
            pass

        def send_progress(self, job_id, progress):
            pass

        def complete_job(self, job_id, *, result):
            captured["result"] = result

        def fail_job(self, job_id, *, error_message, return_code=None):
            raise AssertionError(error_message)

    job = {
        "id": 7,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.compact",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
        },
    }

    result = execute_repository_operation_job(job, _Client(), should_cancel=None)

    assert result.status == "completed"
    assert "--stats" in captured["cmd"]
    assert captured["env"]["BORG_UNITS"] == "raw"
    assert captured["result"]["stats"] == {
        "repository_size": 502_000,
        "object_count": 6,
        "compaction_saved": 0,
        "size_precision": "exact",
    }


@pytest.mark.unit
def test_borg2_compact_without_the_flag_on_an_old_beta(monkeypatch):
    """Borg 2.0.0b15 added `compact --stats`; on an older beta the flag
    would fail the whole compact, so it is left out and nothing is parsed
    or reported."""
    from agent.borg_ui_agent import repository_ops

    monkeypatch.delenv("BORG_UNITS", raising=False)
    monkeypatch.setattr(repository_ops, "compact_stats_supported", lambda binary: False)
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            self.returncode = 0
            self.stdout = iter(["Repository size is 502000 B in 6 objects.\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", _FakePopen
    )

    class _Client:
        def send_log(self, job_id, *, sequence, message, stream="stdout"):
            pass

        def send_progress(self, job_id, progress):
            pass

        def complete_job(self, job_id, *, result):
            captured["result"] = result

        def fail_job(self, job_id, *, error_message, return_code=None):
            raise AssertionError(error_message)

    job = {
        "id": 9,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.compact",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
        },
    }

    result = execute_repository_operation_job(job, _Client(), should_cancel=None)

    assert result.status == "completed"
    assert "--stats" not in captured["cmd"]
    assert "BORG_UNITS" not in captured["env"]
    assert "stats" not in captured["result"]


@pytest.mark.unit
def test_compact_stats_support_is_probed_once_per_binary(monkeypatch):
    from agent.borg_ui_agent import repository_ops

    calls = []

    class _Probe:
        stdout = "borg2 2.0.0b14\n"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Probe()

    monkeypatch.setattr(repository_ops.subprocess, "run", fake_run)
    monkeypatch.setattr(repository_ops, "_COMPACT_STATS_SUPPORT", {})
    assert repository_ops.compact_stats_supported("/opt/borg2") is False
    assert repository_ops.compact_stats_supported("/opt/borg2") is False
    assert calls == [["/opt/borg2", "--version"]]

    # the file changed under the running agent (an in-place upgrade): probed again
    _Probe.stdout = "borg2 2.0.0b24\n"
    monkeypatch.setattr(repository_ops, "_binary_key", lambda binary: (binary, 2, 2))
    assert repository_ops.compact_stats_supported("/opt/borg2") is True
    assert len(calls) == 2

    def failing_run(cmd, **kwargs):
        raise OSError("no such binary")

    monkeypatch.setattr(repository_ops.subprocess, "run", failing_run)
    # unreadable: no flag this time (a wrong flag fails the whole compact),
    # and nothing is remembered
    assert repository_ops.compact_stats_supported("/opt/other") is False
    _Probe.stdout = "borg2 2.0.0b24\n"
    monkeypatch.setattr(repository_ops.subprocess, "run", fake_run)
    assert repository_ops.compact_stats_supported("/opt/other") is True


@pytest.mark.unit
def test_borg_warning_exit_completes_a_streamed_operation_with_warnings(monkeypatch):
    """A Borg warning code on a compact means the run went through: it
    completes with warnings like the short and backup paths, the server
    classifies the code, and the statistics stay. Every other streamed
    kind keeps failing on a non-zero exit."""
    from agent.borg_ui_agent import repository_ops

    monkeypatch.setattr(repository_ops, "compact_stats_supported", lambda binary: True)
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            self.returncode = 1
            self.stdout = iter(["Repository size is 502000 B in 6 objects.\n"])

        def wait(self):
            return 1

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", _FakePopen
    )

    class _Client:
        def send_log(self, job_id, *, sequence, message, stream="stdout"):
            pass

        def send_progress(self, job_id, progress):
            pass

        def complete_job(self, job_id, *, result):
            captured["result"] = result

        def fail_job(self, job_id, *, error_message, return_code=None):
            raise AssertionError(error_message)

    job = {
        "id": 10,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.compact",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
        },
    }

    result = execute_repository_operation_job(job, _Client(), should_cancel=None)

    assert result.status == "completed_with_warnings"
    assert result.return_code == 1
    assert captured["result"]["return_code"] == 1
    assert captured["result"]["status"] == "completed_with_warnings"
    assert captured["result"]["stats"]["repository_size"] == 502_000

    compact = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.compact",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
        }
    )
    assert repository_ops._warning_exit(compact, 1) is True
    assert repository_ops._warning_exit(compact, 100) is True
    assert repository_ops._warning_exit(compact, 2) is False
    # a check that exits 1 found consistency errors: still a failure
    for kind in ("repository.check", "repository.prune", "repository.rclone_sync"):
        assert repository_ops._warning_exit(SimpleNamespace(job_kind=kind), 1) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "borg_version, lines",
    [
        (1, ["compacting segments\n"]),
        (2, ["Starting compaction / garbage collection...\n"]),
    ],
    ids=["borg1", "borg2-without-the-lines"],
)
def test_compact_completion_carries_no_stats_key_without_them(
    monkeypatch, borg_version, lines
):
    """Borg 1 compact has no statistics; a Borg 2 run that printed none
    (a build that no longer does) reports none rather than an empty block,
    so the server falls back to its log parse for that one."""
    from agent.borg_ui_agent import repository_ops

    monkeypatch.setattr(repository_ops, "compact_stats_supported", lambda binary: True)
    monkeypatch.delenv("BORG_UNITS", raising=False)
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            self.returncode = 0
            self.stdout = iter(lines)

        def wait(self):
            return 0

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", _FakePopen
    )

    class _Client:
        def send_log(self, job_id, *, sequence, message, stream="stdout"):
            pass

        def send_progress(self, job_id, progress):
            pass

        def complete_job(self, job_id, *, result):
            captured["result"] = result

        def fail_job(self, job_id, *, error_message, return_code=None):
            raise AssertionError(error_message)

    job = {
        "id": 8,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.compact",
            "repository": {"path": "/agent/repo", "borg_version": borg_version},
        },
    }

    result = execute_repository_operation_job(job, _Client(), should_cancel=None)

    assert result.status == "completed"
    assert "stats" not in captured["result"]
    assert ("BORG_UNITS" in captured["env"]) == (borg_version == 2)


@pytest.mark.unit
def test_repository_rinfo_payload_builds_borg2_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.rinfo",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
        }
    )

    assert payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo2",
        "repo-info",
        "--json",
    ]


@pytest.mark.unit
def test_repository_list_archives_payload_builds_light_borg2_command():
    """The Borg 2 listing must restrict the JSON keys to name/id/time — the
    default key set makes repo-list read every archive's metadata, which
    borgstore serves as whole-pack loads on remote repositories."""
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.list_archives",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
        }
    )

    assert payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo2",
        "repo-list",
        "--json",
        "--format",
        "{name}{id}{time}",
    ]


@pytest.mark.unit
def test_repository_list_archives_payload_keeps_plain_borg1_command():
    """Borg 1's list --json reads the manifest only — no per-archive cost, so
    it stays untouched."""
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.list_archives",
            "repository": {"path": "/agent/repo", "borg_version": 1},
        }
    )

    assert payload.build_command() == [
        "borg",
        "list",
        "--json",
        "/agent/repo",
    ]


@pytest.mark.unit
def test_repository_archive_info_payload_builds_borg2_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.archive_info",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
            "operation": {"archive": "aid:deadbeef"},
        }
    )

    assert payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo2",
        "info",
        "--json",
        "aid:deadbeef",
    ]


@pytest.mark.unit
def test_repository_archive_info_payload_builds_borg1_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.archive_info",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"archive": "arch-1"},
        }
    )

    assert payload.build_command() == [
        "borg",
        "info",
        "--json",
        "/agent/repo::arch-1",
    ]


@pytest.mark.unit
def test_repository_init_payload_rejects_non_mapping_operation():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.init",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": ["not", "a", "mapping"],
        }
    )

    with pytest.raises(
        ValueError, match="repository.init requires operation.encryption"
    ):
        payload.build_command()


@pytest.mark.unit
def test_repository_init_payload_builds_borg2_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.init",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
            "operation": {"encryption": "repokey-aes-ocb"},
        }
    )

    command = payload.build_command()

    # Borg 2.0.0b22 takes the cipher and the key location separately; the server
    # still sends the combined mode name it stores.
    assert command == [
        "borg2",
        "-r",
        "/agent/repo2",
        "repo-create",
        "--encryption",
        "aes256-ocb",
        "--key-location",
        "repokey",
    ]


@pytest.mark.unit
def test_repository_init_payload_rejects_unknown_borg2_encryption_mode():
    """A mode the table does not know (a legacy blake2 name, a typo) must fail
    with the mode's name, mirroring the server — handed to repo-create it dies
    at argument parsing, which does not name the actual problem."""
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.init",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
            "operation": {"encryption": "repokey-blake2"},
        }
    )

    with pytest.raises(
        ValueError, match="unsupported Borg 2 encryption mode 'repokey-blake2'"
    ):
        payload.build_command()


@pytest.mark.unit
def test_borg1_prune_keeps_the_old_keep_within_spelling():
    """--keep-within was removed in Borg 2.0.0b22 only; Borg 1 never gained
    --keep, so the two majors part ways on this flag."""
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.prune",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"keep_daily": 7, "keep_within": "1d"},
        }
    )

    command = payload.build_command()

    assert "--keep-within=1d" in command
    assert "--keep" not in command


@pytest.mark.unit
def test_session_runtime_connects_with_websocket_url_and_sends_hello(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket([])
    connect_calls = []

    def fake_connect(url, *, header, timeout):
        connect_calls.append((url, header, timeout))
        return socket

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=fake_connect,
    )
    runtime.run_session(max_messages=0)

    assert connect_calls == [
        (
            "wss://borgui.example.com/api/agents/session",
            ["X-Borg-Agent-Authorization: Bearer secret"],
            30,
        )
    ]
    assert socket.sent[0] == {
        "type": "hello",
        "agent_id": "agt_123",
        "hostname": "host.local",
        "agent_version": __version__,
        "timezone": None,
        "borg_versions": [],
        "capabilities": get_capabilities(),
        "running_job_ids": [],
    }
    assert socket.closed is True


@pytest.mark.unit
def test_session_hello_reports_a_worker_still_registered_from_a_prior_session(
    patch_session_platform,
):
    """running_job_ids must reflect live workers, not just this session.

    _cancel_events lives on the AgentSessionRuntime instance (created once in
    __init__), not per-session, so a worker started before a reconnect is
    still registered here. If hello reported [] anyway, the server would
    treat the job as not-in-flight and requeue + redispatch it onto a fresh
    worker while the old one is still running — double execution of a
    durable operation. Simulate that surviving worker by registering its
    cancel event directly, the same way _handle_command does before running
    a handler.
    """
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket([])
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime._register_cancel(77)

    runtime.run_session(max_messages=0)

    assert socket.sent[0]["type"] == "hello"
    assert socket.sent[0]["running_job_ids"] == [77]


@pytest.mark.unit
def test_session_hello_reports_empty_list_when_idle(patch_session_platform):
    """The ordinary case: no worker registered, hello must still say so
    explicitly (not merely by omission) so the server's age-window skip for
    a "still running" job never fires spuriously."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket([])
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )

    runtime.run_session(max_messages=0)

    assert socket.sent[0]["running_job_ids"] == []


@pytest.mark.unit
def test_session_hello_stops_reporting_a_job_once_its_handler_finished(
    patch_session_platform,
):
    """A job id must drop out of running_job_ids once _unregister_cancel has
    run (the handler's finally, i.e. the worker is actually done) — otherwise
    a completed job would keep looking "still running" to the server forever
    and the requeue-on-hello recovery for a genuinely stranded job would
    never kick in for it."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket([])
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime._register_cancel(77)
    runtime._unregister_cancel(77)

    runtime.run_session(max_messages=0)

    assert socket.sent[0]["running_job_ids"] == []


@pytest.mark.unit
def test_session_loop_registers_cancel_before_worker_thread_starts(monkeypatch):
    """Registration must be a property of dispatch, not of thread timing.

    See _job_id_for_dispatch for the race. Park the worker at the very first
    thing _handle_command does, well before its own _register_cancel, so a
    regression to registering inside the worker leaves the id missing here.
    """
    from agent.borg_ui_agent.session import AgentSessionRuntime, SessionCommandClient

    worker_parked = threading.Event()
    release_worker = threading.Event()
    real_enqueue = SessionCommandClient.enqueue

    def blocking_enqueue(self, payload):
        # The command_ack enqueue is the first thing _handle_command does --
        # parking here reproduces "worker thread exists but has not reached
        # any registration call yet", the exact window the race lived in.
        if payload.get("type") == "command_ack":
            worker_parked.set()
            release_worker.wait(timeout=5)
        return real_enqueue(self, payload)

    def fake_handler(job, client, *, should_cancel=None):
        return SimpleNamespace(job_id=job["id"], status="completed", message="done")

    monkeypatch.setattr(SessionCommandClient, "enqueue", blocking_enqueue)
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler",
        lambda command: fake_handler if command == "backup.create" else None,
    )

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-race",
                "command": "backup.create",
                "job_id": 99,
                "payload": {},
            }
        ]
    )
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=RecordingHttpClient(),
    )

    session_thread = threading.Thread(
        target=runtime.run_session, kwargs={"max_messages": 1}
    )
    session_thread.start()
    try:
        # Wait for the worker to actually be running and parked at its first
        # instruction, rather than sleeping a fixed duration.
        assert worker_parked.wait(timeout=5)
        # The job id must already be visible to hello / the disconnect path
        # at this point -- registered by the session loop before the worker
        # thread was even started, not by the worker once it got around to it.
        assert runtime._running_job_ids() == [99]
    finally:
        release_worker.set()
        session_thread.join(timeout=5)

    # And it drops out again once the worker (and _handle_command's finally)
    # has actually finished.
    assert runtime._running_job_ids() == []


@pytest.mark.unit
def test_session_loop_does_not_register_non_job_commands(
    patch_session_platform, monkeypatch
):
    """filesystem.browse, cancel, and a job_id: None message all return early
    from _handle_command without ever calling _register_cancel. If the
    session loop registered every incoming command up front (the naive fix),
    these ids would sit in _cancel_events forever -- nothing unregisters
    them -- and hello would report phantom running jobs permanently, which
    would permanently defeat the requeue recovery this branch exists to
    provide. That is worse than the race being fixed."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-browse",
                "command": "filesystem.browse",
                "job_id": 201,
                "payload": {"path": "/"},
            },
            {
                "type": "command",
                "command_id": "cmd-cancel",
                "command": "cancel",
                "job_id": 202,
                "payload": {"job_id": 202},
            },
            {
                "type": "command",
                "command_id": "cmd-none",
                "command": "backup.create",
                "job_id": None,
                "payload": {},
            },
        ]
    )

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.browse_filesystem",
        lambda path, include_hidden=False: {
            "success": True,
            "current_path": path,
            "parent_path": "/",
            "items": [],
        },
    )

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=RecordingHttpClient(),
    )
    runtime.run_session(max_messages=3)

    assert runtime._cancel_events == {}
    assert runtime._running_job_ids() == []


@pytest.mark.unit
def test_session_loop_does_not_register_unsupported_command(patch_session_platform):
    """A command with no registered job handler also returns early from
    _handle_command (the unsupported_command path) without registering --
    the dispatch predicate the session loop uses must agree, or this id would
    leak into _cancel_events with nothing to ever remove it."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-unknown",
                "command": "totally.unknown",
                "job_id": 303,
                "payload": {},
            },
        ]
    )
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=RecordingHttpClient(),
    )
    runtime.run_session(max_messages=1)

    assert runtime._cancel_events == {}
    assert runtime._running_job_ids() == []


@pytest.mark.unit
@pytest.mark.parametrize("raw_job_id", [float("inf"), float("-inf"), "abc", [1]])
def test_session_loop_survives_an_uncastable_job_id(patch_session_platform, raw_job_id):
    """A job_id the cast chokes on must not take the session down with it.

    _job_id_for_dispatch runs on the session thread, so anything it raises
    unwinds run_session and forces a reconnect, where the same value inside
    _handle_command only fails that one worker. json.loads yields float("inf")
    for 1e400, and int(inf) raises OverflowError rather than ValueError, so
    catching only TypeError/ValueError left that shape live.
    """
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-bad-id",
                "command": "backup.create",
                "job_id": raw_job_id,
                "payload": {},
            },
        ]
    )
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=RecordingHttpClient(),
    )

    runtime.run_session(max_messages=1)

    assert runtime._cancel_events == {}
    assert runtime._running_job_ids() == []


@pytest.mark.unit
def test_session_loop_unregisters_after_job_command_completes(monkeypatch):
    """After a normal job command dispatched through the real session loop
    (register-before-start, not the direct _register_cancel call the other
    hello tests use) finishes, its id must be gone from _cancel_events --
    otherwise it would be reported by hello forever."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    def fake_handler(job, client, *, should_cancel=None):
        return SimpleNamespace(job_id=job["id"], status="completed", message="done")

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler",
        lambda command: fake_handler if command == "backup.create" else None,
    )

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-done",
                "command": "backup.create",
                "job_id": 404,
                "payload": {},
            }
        ]
    )
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=RecordingHttpClient(),
    )
    # Clean exit (max_messages reached) joins in-flight workers before
    # returning, so _handle_command's finally has already run by here.
    runtime.run_session(max_messages=1)

    assert runtime._cancel_events == {}
    assert runtime._running_job_ids() == []


@pytest.mark.unit
def test_session_runtime_sends_app_heartbeat_while_idle(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    # recv() raises a timeout first (idle) then yields a harmless message so the
    # bounded loop can exit; the idle branch must emit an app-level heartbeat.
    socket = FakeWebSocket([TimeoutError(), {"type": "noop"}])

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda url, *, header, timeout: socket,
    )
    runtime.run_session(max_messages=1)

    # hello first, then the idle heartbeat; the protocol ping is also sent.
    assert socket.sent[0]["type"] == "hello"
    assert {"type": "heartbeat"} in socket.sent
    assert socket.pings >= 1
    # Both writes ran under the full session timeout, not the recv poll interval.
    assert set(socket.send_timeouts) == {30}


@pytest.mark.unit
def test_session_delivers_result_over_rest_not_ws(patch_session_platform, monkeypatch):
    """Job results are delivered over the REST job API, never over the WebSocket,
    so a large result frame can't starve the keepalive and break the session."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-1",
                "command": "filesystem.browse",
                "job_id": 42,
                "payload": {"path": "/home"},
            },
        ]
    )
    http = RecordingHttpClient()

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.browse_filesystem",
        lambda path, include_hidden=False: {
            "success": True,
            "current_path": path,
            "parent_path": "/",
            "items": [],
        },
    )

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=http,
    )
    runtime.run_session(max_messages=1)

    # Result delivered over REST...
    assert len(http.completed) == 1
    assert http.completed[0][0] == 42
    assert http.completed[0][1]["success"] is True
    # ...and NOT over the WebSocket.
    assert all(frame.get("type") != "command_result" for frame in socket.sent)


@pytest.mark.unit
def test_session_command_client_delivers_error_over_rest():
    """A failed command reports via REST fail_job (with error_message/return_code
    preserved), not over the WebSocket."""
    from agent.borg_ui_agent.session import SessionCommandClient

    outbox = queue.Queue()
    http = RecordingHttpClient()
    client = SessionCommandClient(
        command_id="cmd-1", job_id=7, outbox=outbox, http_client=http
    )

    client.fail_job(7, error_message="boom", return_code=2)

    assert http.failed == [(7, "boom", 2)]
    assert all(
        json.loads(frame).get("type") != "command_error" for frame in _drain(outbox)
    )


@pytest.mark.unit
def test_session_terminal_rest_failure_is_swallowed():
    """If REST delivery raises, the worker must not crash: the failure is logged
    and swallowed, and the client still marks the job finished."""
    from agent.borg_ui_agent.session import SessionCommandClient

    class FailingHttpClient:
        def complete_job(self, job_id, *, result):
            raise RuntimeError("rest unreachable")

    outbox = queue.Queue()
    client = SessionCommandClient(
        command_id="cmd-1", job_id=9, outbox=outbox, http_client=FailingHttpClient()
    )

    client.complete_job(9, result={"ok": True})  # must not raise

    assert client.finished is True
    assert all(
        json.loads(frame).get("type") != "command_result" for frame in _drain(outbox)
    )


@pytest.mark.unit
def test_session_cancel_command_cancels_target_job_not_completes(
    patch_session_platform,
):
    """A cancel command must record the target job as canceled (REST /cancel),
    never completed — otherwise it races the worker's own cancel unwind."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-c",
                "command": "cancel",
                "job_id": 55,
                "payload": {"job_id": 55},
            },
        ]
    )
    http = RecordingHttpClient()

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=http,
    )
    runtime.run_session(max_messages=1)

    assert http.canceled == [55]
    assert http.completed == []


@pytest.mark.unit
def test_session_cancel_command_leaves_a_running_job_to_its_worker(
    patch_session_platform,
):
    """A worker that runs the job reports `canceled` once its process has
    ended; reporting it on the command would let the server hand the
    repository to other work while Borg still holds its lock."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-c",
                "command": "cancel",
                "job_id": 55,
                "payload": {"job_id": 55},
            },
        ]
    )
    http = RecordingHttpClient()

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=http,
    )
    event = runtime._register_cancel(55, command="repository.check")
    runtime.run_session(max_messages=1)

    assert event.is_set()
    assert http.canceled == []
    assert http.completed == []


@pytest.mark.unit
def test_a_dropped_session_does_not_cancel_running_jobs(patch_session_platform):
    """A dropped socket is not a cancel: the cancel poller would otherwise end
    a silent Borg on every proxy hiccup."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket([ConnectionError("proxy dropped the socket")])
    http = RecordingHttpClient()
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=http,
    )
    event = runtime._register_cancel(57, command="repository.check")

    with pytest.raises(ConnectionError):
        runtime.run_session(max_messages=1)

    assert not event.is_set()
    assert http.canceled == []


@pytest.mark.unit
def test_session_cancel_command_records_a_job_whose_worker_ignores_cancel(
    patch_session_platform,
):
    """A listing does not stop on cancel; the cancel is recorded as before
    rather than ending as a completion nobody asked for."""
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-c",
                "command": "cancel",
                "job_id": 56,
                "payload": {"job_id": 56},
            },
        ]
    )
    http = RecordingHttpClient()

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=http,
    )
    event = runtime._register_cancel(56, command="repository.list_archives")
    runtime.run_session(max_messages=1)

    assert event.is_set()
    assert http.canceled == [56]


@pytest.mark.unit
def test_session_runtime_handles_ephemeral_filesystem_browse(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-1",
                "command": "filesystem.browse",
                "job_id": None,
                "payload": {"path": "/home", "include_hidden": True, "max_items": 10},
            }
        ]
    )

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.browse_filesystem",
        lambda path, include_hidden=False: {
            "success": True,
            "current_path": path,
            "parent_path": "/",
            "items": [{"name": "docs"}],
        },
    )

    runtime = AgentSessionRuntime(
        AgentConfig("http://borgui.local:8080/base", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime.run_session(max_messages=1)

    assert socket.sent[1] == {
        "type": "command_ack",
        "command_id": "cmd-1",
        "job_id": None,
    }
    assert socket.sent[2] == {
        "type": "command_result",
        "command_id": "cmd-1",
        "job_id": None,
        "result": {
            "success": True,
            "current_path": "/home",
            "parent_path": "/",
            "items": [{"name": "docs"}],
        },
    }


@pytest.mark.unit
def test_session_runtime_handles_diagnostics_without_tcp_target(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-diagnostics",
                "command": "diagnostics.run",
                "job_id": None,
                "payload": {},
            }
        ]
    )
    monotonic_values = iter([10.0, 10.012])

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime.run_session(max_messages=1)

    assert socket.sent[1] == {
        "type": "command_ack",
        "command_id": "cmd-diagnostics",
        "job_id": None,
    }
    assert socket.sent[2] == {
        "type": "command_result",
        "command_id": "cmd-diagnostics",
        "job_id": None,
        "result": {
            "success": True,
            "session": {"status": "success", "elapsed_ms": 12},
        },
    }


@pytest.mark.unit
def test_session_runtime_handles_diagnostics_tcp_success(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-diagnostics-tcp",
                "command": "diagnostics.run",
                "job_id": None,
                "payload": {
                    "target": {
                        "host": "postgres.internal",
                        "port": 5432,
                        "timeout_seconds": 1.5,
                    }
                },
            }
        ]
    )
    opened = []
    monotonic_values = iter([20.0, 20.1, 20.35, 20.4])

    def fake_open_tcp_connection(host, port, timeout_seconds):
        opened.append((host, port, timeout_seconds))

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.session._open_tcp_connection",
        fake_open_tcp_connection,
        raising=False,
    )

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime.run_session(max_messages=1)

    assert opened == [("postgres.internal", 5432, 1.5)]
    assert socket.sent[2]["result"] == {
        "success": True,
        "session": {"status": "success", "elapsed_ms": 400},
        "tcp": {
            "target": {
                "host": "postgres.internal",
                "port": 5432,
                "timeout_seconds": 1.5,
            },
            "status": "success",
            "elapsed_ms": 250,
        },
    }


@pytest.mark.unit
def test_session_runtime_handles_diagnostics_tcp_failure(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-diagnostics-tcp-failed",
                "command": "diagnostics.run",
                "job_id": None,
                "payload": {
                    "target": {
                        "host": "postgres.internal",
                        "port": 5432,
                        "timeout_seconds": 1.5,
                    }
                },
            }
        ]
    )
    monotonic_values = iter([30.0, 30.2, 30.24, 30.3])

    def fake_open_tcp_connection(host, port, timeout_seconds):
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.session._open_tcp_connection",
        fake_open_tcp_connection,
        raising=False,
    )

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime.run_session(max_messages=1)

    assert socket.sent[2]["result"] == {
        "success": True,
        "session": {"status": "success", "elapsed_ms": 300},
        "tcp": {
            "target": {
                "host": "postgres.internal",
                "port": 5432,
                "timeout_seconds": 1.5,
            },
            "status": "failed",
            "elapsed_ms": 40,
            "error": "connection_refused",
            "message": "Connection refused",
        },
    }


@pytest.mark.unit
def test_session_runtime_reports_durable_job_events(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-2",
                "command": "backup.create",
                "job_id": 77,
                "payload": {"job_kind": "backup.create"},
            }
        ]
    )

    def fake_handler(job, client, *, should_cancel=None):
        assert job["id"] == 77
        assert job["payload"] == {"job_kind": "backup.create"}
        client.start_job(77)
        client.send_log(77, sequence=1, stream="stdout", message="running")
        client.send_progress(77, {"progress_percent": 25, "current_file": "/src"})
        client.complete_job(77, result={"archive_name": "archive"})
        return SimpleNamespace(job_id=77, status="completed", message="complete")

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler",
        lambda command: fake_handler if command == "backup.create" else None,
    )

    http = RecordingHttpClient()
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=http,
    )
    runtime.run_session(max_messages=1)

    # Control + telemetry frames stay on the WebSocket...
    assert socket.sent[1]["type"] == "command_ack"
    assert socket.sent[2]["type"] == "job_started"
    assert socket.sent[3] == {
        "type": "log",
        "command_id": "cmd-2",
        "job_id": 77,
        "sequence": 1,
        "stream": "stdout",
        "message": "running",
    }
    assert socket.sent[4]["type"] == "progress"
    assert socket.sent[4]["progress_percent"] == 25
    # ...the terminal result goes over REST.
    assert http.completed == [(77, {"archive_name": "archive"})]
    assert all(frame.get("type") != "command_result" for frame in socket.sent)


@pytest.mark.unit
def test_session_runtime_writes_the_socket_from_one_thread_only(monkeypatch):
    """Single-writer invariant: only the session thread may touch the socket.

    An ssl.SSLSocket is not thread-safe and websocket-client guards send and recv
    with separate locks, so a worker sending while the session loop reads corrupts
    the TLS state and kills a wss:// session mid-write.
    """
    from agent.borg_ui_agent.session import AgentSessionRuntime

    class ThreadRecordingWebSocket(FakeWebSocket):
        def __init__(self, incoming):
            super().__init__(incoming)
            self.sender_threads = set()

        def send(self, payload):
            self.sender_threads.add(threading.get_ident())
            super().send(payload)

    socket = ThreadRecordingWebSocket(
        [
            {
                "type": "command",
                "command_id": "cmd-3",
                "command": "backup.create",
                "job_id": 88,
                "payload": {},
            }
        ]
    )

    worker_threads = []

    def fake_handler(job, client, *, should_cancel=None):
        worker_threads.append(threading.get_ident())
        client.start_job(88)
        client.send_log(88, sequence=1, stream="stdout", message="running")
        client.send_progress(88, {"progress_percent": 50})
        return SimpleNamespace(job_id=88, status="completed", message="done")

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.get_job_handler",
        lambda command: fake_handler if command == "backup.create" else None,
    )

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
        http_client=RecordingHttpClient(),
    )
    runtime.run_session(max_messages=1)

    # The handler really did run off-thread, and none of its frames were written
    # by it -- every send came from the session thread.
    assert worker_threads and worker_threads[0] != threading.get_ident()
    assert socket.sender_threads == {threading.get_ident()}
    # The frames still arrive, in order.
    assert [frame["type"] for frame in socket.sent] == [
        "hello",
        "command_ack",
        "job_started",
        "log",
        "progress",
    ]
    # The recv loop shortens the socket timeout so queued frames are not held
    # back for the full connect timeout...
    assert socket.timeout == 1.0
    # ...but the timeout also bounds writes, so *every* write -- hello and
    # keepalive included, not just a large flushed result -- runs under the full
    # session timeout. A one-second budget on a slow link would kill the session.
    assert set(socket.send_timeouts) == {30}


@pytest.mark.unit
def test_session_runtime_sends_ping_on_idle_recv_timeout(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    socket = FakeWebSocket(
        [
            TimeoutError("idle"),
            {
                "type": "command",
                "command_id": "cmd-1",
                "command": "filesystem.browse",
                "job_id": None,
                "payload": {"path": "/home"},
            },
        ]
    )

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.browse_filesystem",
        lambda path, include_hidden=False: {
            "success": True,
            "current_path": path,
            "parent_path": "/",
            "items": [],
        },
    )

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime.run_session(max_messages=1)

    assert socket.pings == 1
    # Idle recv timeout now emits an app-level heartbeat before the ping, so the
    # command handshake follows it.
    assert socket.sent[0]["type"] == "hello"
    assert socket.sent[1] == {"type": "heartbeat"}
    assert socket.sent[2]["type"] == "command_ack"
    assert socket.sent[3]["type"] == "command_result"


@pytest.mark.unit
def test_session_runtime_reconnects_with_backoff(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    attempts = []
    sleeps = []

    def failing_connect(*args, **kwargs):
        attempts.append((args, kwargs))
        raise OSError("server unavailable")

    monkeypatch.setattr(
        "agent.borg_ui_agent.session.detect_platform",
        lambda: {"hostname": "host.local", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.session.detect_borg_binaries", lambda: [])

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=failing_connect,
        sleep=sleeps.append,
    )

    runtime.run_forever(
        max_iterations=3,
        initial_backoff_seconds=1,
        max_backoff_seconds=8,
    )

    assert len(attempts) == 3
    assert sleeps == [1, 2, 4]


@pytest.mark.unit
def test_session_runtime_resets_backoff_after_healthy_session(monkeypatch):
    from agent.borg_ui_agent.session import AgentSessionRuntime

    sleeps = []
    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: FakeWebSocket([]),
        sleep=sleeps.append,
    )

    outcomes = [RuntimeError("short"), RuntimeError("healthy"), RuntimeError("short")]

    def fake_run_session():
        raise outcomes.pop(0)

    times = iter([0, 1, 10, 80, 100, 101])
    monkeypatch.setattr(runtime, "run_session", fake_run_session)
    monkeypatch.setattr(
        "agent.borg_ui_agent.session.time.monotonic", lambda: next(times)
    )

    runtime.run_forever(
        max_iterations=3,
        initial_backoff_seconds=4,
        max_backoff_seconds=8,
    )

    assert sleeps == [4, 4, 8]


@pytest.mark.unit
def test_runtime_run_forever_uses_websocket_session(monkeypatch):
    from agent.borg_ui_agent import session as session_module

    calls = []

    class FakeSessionRuntime:
        def __init__(self, config):
            calls.append(("init", config))

        def run_forever(
            self,
            *,
            max_iterations=None,
            initial_backoff_seconds=1,
            max_backoff_seconds=60,
        ):
            calls.append(
                (
                    "run_forever",
                    max_iterations,
                    initial_backoff_seconds,
                    max_backoff_seconds,
                )
            )

    monkeypatch.setattr(session_module, "AgentSessionRuntime", FakeSessionRuntime)
    config = AgentConfig("https://borgui.example.com", "agt_123", "secret")

    AgentRuntime(config).run_forever(
        max_iterations=2,
        initial_backoff_seconds=3,
        max_backoff_seconds=9,
    )

    assert calls == [
        ("init", config),
        ("run_forever", 2, 3, 9),
    ]


@pytest.mark.unit
def test_repository_rclone_sync_payload_builds_agent_owned_command(tmp_path: Path):
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.rclone_sync",
            "repository": {"path": "/agent/repositories/app"},
            "operation": {
                "rclone": {
                    "remote_name": "prod-s3",
                    "remote_path": "borg-ui/repositories/app",
                    "config": {"type": "s3", "provider": "AWS"},
                    "extra_flags": ["--fast-list"],
                }
            },
        }
    )

    command = payload.build_command(rclone_config_path=str(tmp_path / "rclone.conf"))

    assert command == [
        "rclone",
        "--config",
        str(tmp_path / "rclone.conf"),
        "sync",
        "/agent/repositories/app",
        "prod-s3:borg-ui/repositories/app",
        "--fast-list",
    ]


@pytest.mark.unit
def test_repository_rclone_sync_removes_temp_config_when_command_build_fails(
    tmp_path: Path, monkeypatch
):
    config_path = tmp_path / "rclone.conf"
    config_path.write_text("[prod-s3]\ntype = s3\n", encoding="utf-8")

    def fake_write_temp_config(_payload):
        return str(config_path)

    def fail_build_command(self, *, rclone_config_path=None):
        assert rclone_config_path == str(config_path)
        raise ValueError("rclone remote_path is required")

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops._write_temp_rclone_config",
        fake_write_temp_config,
    )
    monkeypatch.setattr(
        RepositoryOperationPayload,
        "build_command",
        fail_build_command,
    )
    client = FakeRuntimeClient([])

    result = execute_repository_operation_job(
        {
            "id": 88,
            "payload": {
                "schema_version": 1,
                "job_kind": "repository.rclone_sync",
                "repository": {"path": "/agent/repositories/app"},
                "operation": {
                    "rclone": {
                        "remote_name": "prod-s3",
                        "remote_path": "borg-ui/repositories/app",
                        "config": {"type": "s3"},
                    }
                },
            },
        },
        client,
    )

    assert result.status == "failed"
    assert not config_path.exists()


@pytest.mark.unit
def test_rinfo_and_archive_info_use_the_stdout_capturing_executor(monkeypatch):
    # info/list_archives/rinfo/archive_info must run through the short-operation
    # path so their JSON stdout is captured in the job result; the streaming
    # path drops stdout (which broke stats/encryption refresh for agent repos).
    routed = []

    def fake_short(job_id, payload, client, cmd, env, *, should_cancel=None):
        routed.append(payload.job_kind)
        return RepositoryOperationResult(job_id=job_id, status="completed")

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops._execute_short_repository_operation",
        fake_short,
    )
    client = FakeRuntimeClient([])

    for job_kind, operation in (
        ("repository.rinfo", None),
        ("repository.archive_info", {"archive": "aid:deadbeef"}),
        ("repository.delete_archive", {"archive": "aid:deadbeef"}),
        ("repository.break_lock", None),
    ):
        execute_repository_operation_job(
            {
                "id": 1,
                "payload": {
                    "schema_version": 1,
                    "job_kind": job_kind,
                    "repository": {"path": "/agent/repo", "borg_version": 2},
                    "operation": operation,
                },
            },
            client,
        )

    assert routed == [
        "repository.rinfo",
        "repository.archive_info",
        "repository.delete_archive",
        "repository.break_lock",
    ]


@pytest.mark.unit
def test_repository_break_lock_payload_builds_borg2_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.break_lock",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
        }
    )

    assert payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo2",
        "break-lock",
    ]


@pytest.mark.unit
def test_repository_break_lock_payload_builds_borg1_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.break_lock",
            "repository": {"path": "/agent/repo", "borg_version": 1},
        }
    )

    assert payload.build_command() == [
        "borg",
        "break-lock",
        "/agent/repo",
    ]


@pytest.mark.unit
def test_repository_delete_archive_payload_builds_borg2_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.delete_archive",
            "repository": {"path": "/agent/repo2", "borg_version": 2},
            "operation": {"archive": "aid:deadbeef"},
        }
    )

    assert payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo2",
        "delete",
        "aid:deadbeef",
    ]


@pytest.mark.unit
def test_repository_delete_archive_payload_builds_borg1_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.delete_archive",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"archive": "arch-1"},
        }
    )

    assert payload.build_command() == [
        "borg",
        "delete",
        "/agent/repo::arch-1",
    ]


@pytest.mark.unit
def test_repository_rclone_sync_removes_partial_temp_config_when_write_fails(
    tmp_path: Path, monkeypatch
):
    partial_config_path = tmp_path / "partial-rclone.conf"
    closed = False

    class FailingTempConfig:
        name = str(partial_config_path)

        def __init__(self):
            self._handle = partial_config_path.open("w", encoding="utf-8")

        def write(self, text):
            self._handle.write(text)
            self._handle.flush()
            raise OSError("disk full")

        def close(self):
            nonlocal closed
            closed = True
            self._handle.close()

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.tempfile.NamedTemporaryFile",
        lambda *args, **kwargs: FailingTempConfig(),
    )
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.rclone_sync",
            "repository": {"path": "/agent/repositories/app"},
            "operation": {
                "rclone": {
                    "remote_name": "prod-s3",
                    "remote_path": "borg-ui/repositories/app",
                    "config": {"type": "s3"},
                }
            },
        }
    )

    with pytest.raises(OSError, match="disk full"):
        _write_temp_rclone_config(payload)

    assert closed is True
    assert not partial_config_path.exists()


@pytest.mark.unit
def test_runtime_advertises_and_dispatches_filesystem_browse(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.detect_platform",
        lambda: {"hostname": "host", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.runtime.detect_borg_binaries", lambda: [])

    handled_jobs = []

    def fake_handler(job, client, *, should_cancel=None):
        handled_jobs.append((job, client, should_cancel))
        return SimpleNamespace(job_id=45, status="completed", message="browse complete")

    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.execute_filesystem_browse_job", fake_handler
    )
    assert "filesystem.browse" in get_capabilities()

    client = FakeRuntimeClient(
        [{"id": 45, "type": "filesystem", "payload": {"job_kind": "filesystem.browse"}}]
    )
    runtime = AgentRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        client=client,
    )

    result = runtime.run_once()

    assert result.job_id == 45
    assert result.status == "completed"
    assert handled_jobs[0][0]["id"] == 45


@pytest.mark.unit
def test_runtime_advertises_and_dispatches_repository_operation(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.detect_platform",
        lambda: {"hostname": "host", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr("agent.borg_ui_agent.runtime.detect_borg_binaries", lambda: [])

    handled_jobs = []

    def fake_handler(job, client, *, should_cancel=None):
        handled_jobs.append((job, client, should_cancel))
        return SimpleNamespace(job_id=46, status="completed", message="info complete")

    monkeypatch.setattr(
        "agent.borg_ui_agent.runtime.execute_repository_operation_job", fake_handler
    )
    assert "repository.info" in get_capabilities()
    assert "repository.prune" in get_capabilities()

    client = FakeRuntimeClient(
        [{"id": 46, "type": "repository", "payload": {"job_kind": "repository.info"}}]
    )
    runtime = AgentRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        client=client,
    )

    result = runtime.run_once()

    assert result.job_id == 46
    assert result.status == "completed"
    assert handled_jobs[0][0]["id"] == 46


@pytest.mark.unit
def test_repository_operation_payload_builds_agent_local_commands():
    info_payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.info",
            "repository": {"path": "/agent/repo", "borg_version": 1},
        }
    )
    prune_payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.prune",
            "repository": {"path": "/agent/repo", "borg_version": 2},
            "operation": {
                "keep_daily": 7,
                "keep_quarterly": 3,
                "keep_within": "1d",
                "dry_run": True,
            },
        }
    )
    prune_v1_payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.prune",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"keep_daily": 7, "keep_quarterly": 3},
        }
    )

    assert info_payload.build_command() == ["borg", "info", "--json", "/agent/repo"]
    # Borg 2 prune: no --stats, quarterly -> --keep-3monthly.
    assert prune_payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo",
        "prune",
        "--list",
        "--progress",
        "--show-rc",
        "--log-json",
        "--keep-daily",
        "7",
        "--keep-3monthly",
        "3",
        "--keep",
        "1d",
        "--dry-run",
    ]
    # Borg 1 prune keeps --stats; quarterly is --keep-3monthly on borg1 too
    # (borg 1.4 has no --keep-quarterly), and the repo path comes last.
    assert prune_v1_payload.build_command() == [
        "borg",
        "prune",
        "--list",
        "--progress",
        "--stats",
        "--show-rc",
        "--log-json",
        "--keep-daily",
        "7",
        "--keep-3monthly",
        "3",
        "/agent/repo",
    ]

    # Zero retentions must not be emitted (matches server-side `> 0`): a payload
    # with keep_hourly=0/keep_quarterly=0 yields no --keep-hourly / --keep-3monthly.
    prune_zero_payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.prune",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"keep_hourly": 0, "keep_daily": 7, "keep_quarterly": 0},
        }
    )
    zero_cmd = prune_zero_payload.build_command()
    assert "--keep-hourly" not in zero_cmd
    assert "--keep-3monthly" not in zero_cmd
    assert "--keep-quarterly" not in zero_cmd
    assert zero_cmd.count("--keep-daily") == 1


@pytest.mark.unit
def test_repository_archive_contents_payload_builds_agent_list_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.list_archive_contents",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"archive": "archive-1", "max_lines": 1000},
        }
    )
    v2_payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.list_archive_contents",
            "repository": {"path": "/agent/v2-repo", "borg_version": 2},
            "operation": {"archive": "archive-2", "path": "home/user"},
        }
    )

    assert "repository.list_archive_contents" in get_capabilities()
    assert payload.build_command() == [
        "borg",
        "list",
        "/agent/repo::archive-1",
        "--json-lines",
    ]
    assert v2_payload.build_command() == [
        "borg2",
        "-r",
        "/agent/v2-repo",
        "list",
        "--json-lines",
        "archive-2",
        "home/user",
    ]


@pytest.mark.unit
def test_repository_extract_file_payload_builds_agent_extract_stdout_command():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.extract_archive_file",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {
                "archive": "archive-1",
                "file_path": "/docs/report.txt",
            },
        }
    )
    v2_payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.extract_archive_file",
            "repository": {"path": "/agent/v2-repo", "borg_version": 2},
            "operation": {
                "archive": "archive-2",
                "file_path": "docs/report.txt",
            },
        }
    )

    assert "repository.extract_archive_file" in get_capabilities()
    assert payload.build_command() == [
        "borg",
        "extract",
        "--stdout",
        "/agent/repo::archive-1",
        "docs/report.txt",
    ]
    assert v2_payload.build_command() == [
        "borg2",
        "-r",
        "/agent/v2-repo",
        "extract",
        "--stdout",
        "archive-2",
        "docs/report.txt",
    ]


@pytest.mark.unit
def test_repository_export_tar_payload_builds_streaming_tar_commands():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.export_archive_tar",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {
                "archive": "archive-1",
                "directory_path": "/docs/Projects",
                "strip_components": 1,
            },
        }
    )
    v2_payload = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.export_archive_tar",
            "repository": {"path": "/agent/v2-repo", "borg_version": 2},
            "operation": {
                "archive": "aid:archive-2",
                "directory_path": "docs/Projects",
                "strip_components": 1,
            },
        }
    )

    assert "repository.export_archive_tar" in get_capabilities()
    assert payload.build_command() == [
        "borg",
        "export-tar",
        "--strip-components",
        "1",
        "/agent/repo::archive-1",
        "-",
        "--",
        "docs/Projects",
    ]
    assert v2_payload.build_command() == [
        "borg2",
        "-r",
        "/agent/v2-repo",
        "export-tar",
        "--strip-components",
        "1",
        "aid:archive-2",
        "-",
        "--",
        "docs/Projects",
    ]


@pytest.mark.unit
def test_repository_extract_file_job_returns_base64_content(monkeypatch):
    def fake_run(cmd, *, capture_output, env, timeout):
        assert cmd == [
            "borg",
            "extract",
            "--stdout",
            "/agent/repo::archive-1",
            "docs/report.txt",
        ]
        assert capture_output is True
        assert env["BORG_PASSPHRASE"] == "secret"
        assert timeout == 300
        return SimpleNamespace(returncode=0, stdout=b"\x00hello\n", stderr=b"")

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.run",
        fake_run,
    )
    client = FakeRuntimeClient([])

    result = execute_repository_operation_job(
        {
            "id": 91,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "archive-1",
                    "file_path": "docs/report.txt",
                },
                "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
            },
        },
        client,
    )

    complete_call = [call for call in client.calls if call[0] == "complete_job"][0]
    assert result.status == "completed"
    assert complete_call[2]["success"] is True
    assert complete_call[2]["stdout"] == ""
    assert complete_call[2]["content_base64"] == base64.b64encode(
        b"\x00hello\n"
    ).decode("ascii")


@pytest.mark.unit
def test_machine_parsed_repository_operations_run_under_tz_utc(monkeypatch):
    import os

    seen_env = {}

    def fake_run(cmd, *, text, capture_output, env, timeout):
        seen_env.update(env)
        return SimpleNamespace(returncode=0, stdout='{"archives":[]}', stderr="")

    monkeypatch.setattr("agent.borg_ui_agent.repository_ops.subprocess.run", fake_run)
    monkeypatch.setenv("TZ", "Europe/Berlin")
    client = FakeRuntimeClient([])

    result = execute_repository_operation_job(
        {
            "id": 92,
            "payload": {
                "job_kind": "repository.list_archives",
                "repository": {"path": "/agent/repo", "borg_version": 1},
            },
        },
        client,
    )

    # The server parses these timestamps with the reported zone ("UTC"), so
    # the listing must really render in UTC - even with TZ set on the machine.
    assert result.status == "completed"
    assert seen_env["TZ"] == "UTC"

    seen_env.clear()
    result = execute_repository_operation_job(
        {
            "id": 93,
            "payload": {
                "job_kind": "repository.break_lock",
                "repository": {"path": "/agent/repo", "borg_version": 1},
            },
        },
        client,
    )

    # Non-parsed operations keep the machine zone untouched.
    assert result.status == "completed"
    assert seen_env.get("TZ") == os.environ.get("TZ")


@pytest.mark.unit
def test_repository_extract_file_streams_artifact_when_delivery_requested(monkeypatch):
    uploaded = {}

    class _FakeStdout:
        def __init__(self, data):
            self._data = data
            self._done = False

        def read(self, *args):
            if self._done:
                return b""
            self._done = True
            return self._data

        def close(self):
            pass

    def fake_popen(cmd, **kwargs):
        assert cmd[:3] == ["borg", "extract", "--stdout"]
        return SimpleNamespace(
            stdout=_FakeStdout(b"\x00filebytes"),
            stderr=SimpleNamespace(read=lambda: b""),
            wait=lambda: 0,
            poll=lambda: 0,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )

    class _StreamingClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            uploaded["job_id"] = job_id
            uploaded["bytes"] = data.read()
            return {"accepted": True, "size": len(uploaded["bytes"])}

    client = _StreamingClient([])

    result = execute_repository_operation_job(
        {
            "id": 91,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "archive-1",
                    "file_path": "docs/report.txt",
                    "delivery": "artifact",
                },
                "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
            },
        },
        client,
    )

    assert result.status == "completed"
    assert uploaded["job_id"] == 91
    assert uploaded["bytes"] == b"\x00filebytes"
    complete_call = [c for c in client.calls if c[0] == "complete_job"][0]
    assert complete_call[2]["artifact"] is True
    assert "content_base64" not in complete_call[2]


@pytest.mark.unit
def test_repository_extract_file_streaming_cancels_a_wedged_borg(monkeypatch):
    # The watchdog must terminate borg on cancellation so a stalled process
    # (upload read blocked) does not pin the worker.
    terminated = threading.Event()

    class _BlockingStdout:
        def read(self, *args):
            terminated.wait(timeout=5)  # unblocks when borg is "terminated"
            return b""

        def close(self):
            terminated.set()

    process = SimpleNamespace(
        stdout=_BlockingStdout(),
        stderr=SimpleNamespace(read=lambda: b""),
        pid=4321,
        poll=lambda: -15 if terminated.is_set() else None,
        wait=lambda *a, **k: -15,
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", lambda *a, **k: process
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.os.getpgid", lambda pid: 9999
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.os.killpg",
        lambda pgid, sig: terminated.set(),
    )

    class _CancelClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            data.read()  # blocks until borg is terminated
            return {}

        def cancel_job(self, job_id):
            self.calls.append(("cancel_job", job_id))
            return {"id": job_id, "status": "canceled"}

    client = _CancelClient([])

    result = execute_repository_operation_job(
        {
            "id": 93,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "a", "file_path": "f", "delivery": "artifact"},
            },
        },
        client,
        should_cancel=lambda: True,
    )

    assert result.status == "canceled"
    assert ("cancel_job", 93) in client.calls


@pytest.mark.unit
def test_repository_extract_file_falls_back_to_base64_without_upload(monkeypatch):
    # delivery=artifact requested, but a client without upload_artifact (e.g. an
    # older transport) must still work via the base64 path.
    def fake_run(cmd, *, capture_output, env, timeout):
        return SimpleNamespace(returncode=0, stdout=b"data", stderr=b"")

    monkeypatch.setattr("agent.borg_ui_agent.repository_ops.subprocess.run", fake_run)
    client = FakeRuntimeClient([])  # no upload_artifact attribute

    result = execute_repository_operation_job(
        {
            "id": 92,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "a", "file_path": "f", "delivery": "artifact"},
            },
        },
        client,
    )

    assert result.status == "completed"
    complete_call = [c for c in client.calls if c[0] == "complete_job"][0]
    assert complete_call[2]["content_base64"] == base64.b64encode(b"data").decode(
        "ascii"
    )


class FakeStream:
    """Doubles as an iterable line stream (stderr) or a readable blob (stdout)."""

    def __init__(self, lines=None, data=""):
        self.lines = lines or []
        self._data = data

    def __iter__(self):
        return iter(self.lines)

    def read(self):
        return self._data


class FakeProcess:
    # `lines` are the stderr progress/log lines borg streams; `stdout_data` is
    # the final `borg create --json` result document (with the resolved name).
    def __init__(self, lines, return_code, stdout_data=""):
        self.stderr = FakeStream(lines=lines)
        self.stdout = FakeStream(data=stdout_data)
        self.return_code = return_code

    def wait(self):
        return self.return_code


class BackupClient:
    def __init__(self):
        self.calls = []

    def send_log(self, job_id, *, sequence, message, stream="stdout"):
        self.calls.append(("send_log", job_id, sequence, stream, message))
        return {"accepted": True}

    def send_progress(self, job_id, progress):
        self.calls.append(("send_progress", job_id, progress))
        return {"id": job_id, "status": "running"}

    def complete_job(self, job_id, *, result):
        self.calls.append(("complete_job", job_id, result))
        return {"id": job_id, "status": "completed"}

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.calls.append(("fail_job", job_id, error_message, return_code))
        return {"id": job_id, "status": "failed"}

    def cancel_job(self, job_id):
        self.calls.append(("cancel_job", job_id))
        return {"id": job_id, "status": "canceled"}


@pytest.mark.unit
def test_execute_backup_create_job_completes_successfully(monkeypatch):
    popen_calls = []

    def fake_popen(cmd, stdout, stderr, text, env, **kwargs):
        popen_calls.append(
            {
                "cmd": cmd,
                "stdout": stdout,
                "stderr": stderr,
                "text": text,
                "env": env,
                "kwargs": kwargs,
            }
        )
        return FakeProcess(
            [
                '{"type":"archive_progress","original_size":1024,"nfiles":1,'
                '"path":"/src/file"}\n',
                '{"type":"archive_progress","finished":true}\n',
            ],
            0,
        )

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fake_popen)
    client = BackupClient()

    result = execute_backup_create_job(
        {
            "id": 7,
            "payload": {
                "job_kind": "backup.create",
                "repository_path": "/repo",
                "archive_name": "archive",
                "source_paths": ["/src"],
                "environment": {"BORG_PASSPHRASE": {"value": "secret"}},
            },
        },
        client,
    )

    assert result.status == "completed"
    assert popen_calls[0]["cmd"][-2:] == ["/repo::archive", "/src"]
    assert popen_calls[0]["env"]["BORG_PASSPHRASE"] == "secret"
    # Unencrypted repos must not stall the non-interactive agent on borg's
    # "previously unknown unencrypted repository [yN]" prompt (issue #741).
    assert popen_calls[0]["env"]["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] == "yes"
    assert popen_calls[0]["kwargs"]["start_new_session"] is True
    assert any(call[0] == "send_progress" for call in client.calls)
    complete_call = [call for call in client.calls if call[0] == "complete_job"][0]
    # No --json document on stdout -> fall back to the requested archive name.
    assert complete_call[2]["archive_name"] == "archive"
    assert complete_call[2]["return_code"] == 0


@pytest.mark.unit
def test_execute_backup_create_job_warning_exit_completes_with_warnings(monkeypatch):
    """rc=1 (borg warning: file changed, path missing) still produced an
    archive: the agent completes the job with the return code instead of
    failing it, and the server derives completed_with_warnings from that."""

    def fake_popen(cmd, stdout, stderr, text, env, **kwargs):
        return FakeProcess(
            ['{"type":"archive_progress","finished":true}\n'],
            1,
        )

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fake_popen)
    client = BackupClient()

    result = execute_backup_create_job(
        {
            "id": 8,
            "payload": {
                "job_kind": "backup.create",
                "repository_path": "/repo",
                "archive_name": "archive",
                "source_paths": ["/src"],
            },
        },
        client,
    )

    assert result.status == "completed_with_warnings"
    assert result.return_code == 1
    complete_calls = [call for call in client.calls if call[0] == "complete_job"]
    assert len(complete_calls) == 1
    assert complete_calls[0][2]["return_code"] == 1
    assert all(call[0] != "fail_job" for call in client.calls)


@pytest.mark.unit
def test_execute_backup_create_job_error_exit_still_fails(monkeypatch):
    """rc=2 (borg error) keeps the failure semantics untouched."""

    def fake_popen(cmd, stdout, stderr, text, env, **kwargs):
        return FakeProcess([], 2)

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fake_popen)
    client = BackupClient()

    result = execute_backup_create_job(
        {
            "id": 9,
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
    assert any(call[0] == "fail_job" for call in client.calls)
    assert all(call[0] != "complete_job" for call in client.calls)


@pytest.mark.unit
def test_build_borg_env_sets_noninteractive_access_defaults(monkeypatch):
    # borg 1.x and 2 both prompt "[yN]" on first access to an unknown
    # unencrypted (or relocated) repository. The agent runs borg
    # non-interactively, so without these flags every operation on such a repo
    # hangs and the UI shows empty stats (0 archives / N/A / never) -> #741.
    monkeypatch.delenv("BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK", raising=False)
    monkeypatch.delenv("BORG_RELOCATED_REPO_ACCESS_IS_OK", raising=False)

    env = build_borg_env()

    assert env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] == "yes"
    assert env["BORG_RELOCATED_REPO_ACCESS_IS_OK"] == "yes"


@pytest.mark.unit
def test_build_borg_env_overrides_win_but_container_setting_is_kept(monkeypatch):
    # A per-job override (e.g. the passphrase) is layered last and wins.
    env = build_borg_env({"BORG_PASSPHRASE": "secret"})
    assert env["BORG_PASSPHRASE"] == "secret"
    assert env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] == "yes"

    # An explicit container-level setting is respected over the default.
    monkeypatch.setenv("BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK", "no")
    env = build_borg_env()
    assert env["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] == "no"


@pytest.mark.unit
def test_build_borg_env_asks_for_modern_exit_codes(monkeypatch):
    # The server asks borg for the modern codes on every path it runs itself.
    # An agent's Borg 1 must speak the same vocabulary, or the same failure
    # reads as a specific code from the server and a bare legacy 2 from an
    # agent. `is_warning_return_code` already accepts 100-127.
    monkeypatch.delenv("BORG_EXIT_CODES", raising=False)

    assert build_borg_env()["BORG_EXIT_CODES"] == "modern"

    monkeypatch.setenv("BORG_EXIT_CODES", "legacy")
    assert build_borg_env()["BORG_EXIT_CODES"] == "legacy"


@pytest.mark.unit
def test_build_borg_env_enables_the_pack_cache_with_a_bounded_size(monkeypatch):
    """Borg 2.0.0b23's pack cache downloads each pack once instead of
    re-transferring it on every listing; borg puts it under its own cache
    directory. An empty container-level BORG_STORE_CACHE disables it."""
    monkeypatch.delenv("BORG_STORE_CACHE", raising=False)
    monkeypatch.delenv("BORG_PACK_CACHE_SIZE", raising=False)

    env = build_borg_env()

    assert env["BORG_STORE_CACHE"] == "1"
    assert env["BORG_PACK_CACHE_SIZE"] == str(2 * 1024**3)

    monkeypatch.setenv("BORG_STORE_CACHE", "")
    env = build_borg_env()
    assert env["BORG_STORE_CACHE"] == ""


@pytest.mark.unit
def test_execute_backup_create_job_reports_resolved_archive_name(monkeypatch):
    # borg expands placeholders like {now:...} itself; the resolved name comes
    # back on stdout as the --json document's archive.name. The agent must report
    # that resolved name, not the template it requested.
    json_document = json.dumps(
        {
            "archive": {
                "name": "m3s02-2026-07-06-1783316999",
                "id": "c46ef96c",
                "stats": {"nfiles": 1},
            },
            "repository": {"location": "/repo"},
        }
    )

    def fake_popen(cmd, stdout, stderr, text, env, **kwargs):
        return FakeProcess(
            ['{"type":"archive_progress","finished":true}\n'],
            0,
            stdout_data=json_document,
        )

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fake_popen)
    client = BackupClient()

    result = execute_backup_create_job(
        {
            "id": 12,
            "payload": {
                "job_kind": "backup.create",
                "repository_path": "/repo",
                "archive_name": "m3s02-{now:%Y-%m-%d-%s}",
                "source_paths": ["/src"],
            },
        },
        client,
    )

    assert result.status == "completed"
    complete_call = [call for call in client.calls if call[0] == "complete_job"][0]
    assert complete_call[2]["archive_name"] == "m3s02-2026-07-06-1783316999"


@pytest.mark.unit
def test_execute_backup_create_job_reports_failure(monkeypatch):
    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.subprocess.Popen",
        lambda *args, **kwargs: FakeProcess(["fatal error\n"], 2),
    )
    client = BackupClient()

    result = execute_backup_create_job(
        {
            "id": 8,
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
    assert result.return_code == 2
    assert ("fail_job", 8, "borg create exited with code 2", 2) in client.calls


@pytest.mark.unit
def test_execute_backup_create_job_fails_invalid_payload_without_spawning(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Popen should not be called for invalid payload")

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fail_if_called)
    client = BackupClient()

    result = execute_backup_create_job(
        {
            "id": 9,
            "payload": {
                "job_kind": "backup.create",
                "archive_name": "archive",
                "source_paths": ["/src"],
            },
        },
        client,
    )

    assert result.status == "failed"
    assert result.return_code is None
    assert "Invalid backup.create payload" in result.message
    assert client.calls[-1][0] == "fail_job"
    assert client.calls[-1][1] == 9


@pytest.mark.unit
def test_execute_backup_create_job_reports_spawn_failure(monkeypatch):
    def fake_popen(*args, **kwargs):
        raise FileNotFoundError("borg")

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fake_popen)
    client = BackupClient()

    result = execute_backup_create_job(
        {
            "id": 10,
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
    assert result.return_code is None
    assert "Failed to start borg create" in result.message
    assert client.calls[-1][0] == "fail_job"
    assert client.calls[-1][1] == 10


class CancelableProcess(FakeProcess):
    def __init__(self, lines, return_code):
        super().__init__(lines, return_code)
        self.pid = 4321
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def poll(self):
        # running until the cancel ends it
        return None

    def kill(self):
        raise AssertionError("process should terminate cleanly")

    def wait(self, timeout=None):
        return self.return_code


@pytest.mark.unit
def test_execute_backup_create_job_cancels_running_process(monkeypatch):
    process = CancelableProcess(["first line\n", "second line\n"], -15)
    killed_groups = []
    started = []

    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.subprocess.Popen",
        lambda *args, **kwargs: started.append(True) or process,
    )
    monkeypatch.setattr("agent.borg_ui_agent.backup.os.getpgid", lambda pid: 9876)
    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.os.killpg",
        lambda pgid, sig: killed_groups.append((pgid, sig)),
    )
    client = BackupClient()

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
        # not before the start: the cancel arrives once borg has started
        should_cancel=lambda: bool(started),
    )

    assert result.status == "canceled"
    assert result.return_code == -15
    assert killed_groups
    assert killed_groups[0][0] == 9876
    assert ("cancel_job", 11) in client.calls


@pytest.mark.unit
def test_runtime_capabilities_include_backup_cancel():
    assert "backup.cancel" in get_capabilities()


@pytest.mark.unit
def test_cli_register_saves_config(monkeypatch, tmp_path: Path, capsys):
    from agent.borg_ui_agent import cli

    config_path = tmp_path / "config.toml"

    class FakeClient:
        def __init__(self, server_url):
            self.server_url = server_url

        def register(self, **kwargs):
            assert self.server_url == "https://borgui.example.com"
            assert kwargs["enrollment_token"] == "borgui_enroll_secret"
            return {"agent_id": "agt_cli", "agent_token": "borgui_agent_cli"}

    monkeypatch.setattr(
        cli,
        "detect_platform",
        lambda: {"hostname": "host", "os": "linux", "arch": "amd64"},
    )
    monkeypatch.setattr(cli, "detect_borg_binaries", lambda: [])
    monkeypatch.setattr(cli, "AgentClient", FakeClient)

    exit_code = cli.main(
        [
            "--config",
            str(config_path),
            "register",
            "--server",
            "https://borgui.example.com",
            "--token",
            "borgui_enroll_secret",
            "--name",
            "cli-agent",
        ]
    )

    assert exit_code == 0
    assert "Registered agt_cli" in capsys.readouterr().out
    assert load_config(config_path) == AgentConfig(
        server_url="https://borgui.example.com",
        agent_id="agt_cli",
        agent_token="borgui_agent_cli",
        name="cli-agent",
    )


@pytest.mark.unit
def test_cli_unregister_revokes_agent_and_removes_config(
    monkeypatch, tmp_path: Path, capsys
):
    from agent.borg_ui_agent import cli

    config_path = save_config(
        AgentConfig(
            server_url="https://borgui.example.com",
            agent_id="agt_cli",
            agent_token="borgui_agent_cli",
            name="cli-agent",
        ),
        tmp_path / "config.toml",
    )
    calls = []

    class FakeClient:
        def __init__(self, config):
            self.config = config

        @classmethod
        def from_config(cls, config):
            calls.append(("from_config", config))
            return cls(config)

        def unregister(self):
            calls.append(("unregister", self.config.agent_id))
            return {}

    monkeypatch.setattr(cli, "AgentClient", FakeClient)

    exit_code = cli.main(["--config", str(config_path), "unregister"])

    assert exit_code == 0
    assert not config_path.exists()
    assert calls == [
        (
            "from_config",
            AgentConfig(
                server_url="https://borgui.example.com",
                agent_id="agt_cli",
                agent_token="borgui_agent_cli",
                name="cli-agent",
            ),
        ),
        ("unregister", "agt_cli"),
    ]
    assert "Unregistered agt_cli" in capsys.readouterr().out


class TestReportedTimezone:
    def test_reports_utc_regardless_of_machine_zone(self, monkeypatch):
        from agent.borg_ui_agent.borg import detect_platform

        # The reported zone is the one borg renders machine-parsed output in,
        # which the agent pins to UTC - not the machine's own zone.
        monkeypatch.setenv("TZ", "Europe/Berlin")

        assert detect_platform()["timezone"] == "UTC"


@pytest.mark.unit
def test_repository_diff_payload_builds_diff_and_listing_commands():
    # The argv the server's history index runs for its own repositories
    # (app/core/borg.py diff_archives / list_archive_lines and the Borg 2
    # twins): a predecessor means a diff, none means the full listing of
    # the first archive in a series.
    assert "repository.diff" in get_capabilities()

    diff_v1 = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.diff",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"archive": "daily-2", "predecessor": "daily-1"},
        }
    )
    assert diff_v1.build_command() == [
        "borg",
        "diff",
        "--json-lines",
        "--",
        "/agent/repo::daily-1",
        "daily-2",
    ]

    listing_v1 = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.diff",
            "repository": {
                "path": "/agent/repo",
                "borg_version": 1,
                "remote_path": "/opt/borg",
            },
            "operation": {"archive": "daily-1", "predecessor": None},
        }
    )
    assert listing_v1.build_command() == [
        "borg",
        "list",
        "--remote-path",
        "/opt/borg",
        "--json-lines",
        "--",
        "/agent/repo::daily-1",
    ]

    diff_v2 = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.diff",
            "repository": {"path": "/agent/v2-repo", "borg_version": 2},
            "operation": {"archive": "aid:b2", "predecessor": "aid:a1"},
        }
    )
    assert diff_v2.build_command() == [
        "borg2",
        "-r",
        "/agent/v2-repo",
        "diff",
        "--json-lines",
        "--",
        "aid:a1",
        "aid:b2",
    ]

    listing_v2 = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.diff",
            "repository": {"path": "/agent/v2-repo", "borg_version": 2},
            "operation": {"archive": "aid:a1", "predecessor": None},
        }
    )
    assert listing_v2.build_command() == [
        "borg2",
        "-r",
        "/agent/v2-repo",
        "list",
        "--json-lines",
        "--",
        "aid:a1",
    ]

    # An archive named like an option is still an archive.
    odd = RepositoryOperationPayload.from_job_payload(
        {
            "job_kind": "repository.diff",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"archive": "--help", "predecessor": "daily-1"},
        }
    )
    assert odd.build_command()[-3:] == ["--", "/agent/repo::daily-1", "--help"]


@pytest.mark.unit
def test_repository_diff_rejects_a_blank_or_missing_predecessor():
    # A blank or a missing predecessor is a payload error, not a request
    # for the full listing: silently listing would store every path as
    # added on top of an indexed predecessor. The full listing is asked
    # for with an explicit null.
    for operation in ({"archive": "daily-2", "predecessor": "  "}, {"archive": "d"}):
        payload = RepositoryOperationPayload.from_job_payload(
            {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": operation,
            }
        )
        with pytest.raises(ValueError, match="predecessor"):
            payload.build_command()


class _ChunkedStdout:
    def __init__(self, data):
        self._data = data
        self._done = False

    def read(self, *args):
        if self._done:
            return b""
        self._done = True
        return self._data

    def close(self):
        pass


class _ArtifactClient(FakeRuntimeClient):
    def __init__(self, jobs):
        super().__init__(jobs)
        self.uploaded = {}

    def upload_artifact(self, job_id, data):
        self.uploaded["job_id"] = job_id
        self.uploaded["bytes"] = data.read()
        return {"accepted": True, "size": len(self.uploaded["bytes"])}


def _run_diff_job_with_return_code(monkeypatch, return_code, *, stderr=b""):
    seen = {}

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["env"] = kwargs["env"]
        return SimpleNamespace(
            stdout=_ChunkedStdout(b'{"path": "a", "change": "added"}\n'),
            stderr=SimpleNamespace(read=lambda: stderr),
            wait=lambda: return_code,
            poll=lambda: return_code,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )
    monkeypatch.setenv("TZ", "Europe/Berlin")
    client = _ArtifactClient([])
    result = execute_repository_operation_job(
        {
            "id": 97,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
                "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
            },
        },
        client,
    )
    return result, client, seen


@pytest.mark.unit
def test_repository_diff_streams_the_listing_as_an_artifact(monkeypatch):
    # The listing goes over the artifact upload whether or not the server
    # asked for it: a large archive's diff runs to tens of megabytes, which
    # the WebSocket result must never carry. The server parses timestamps
    # out of it, so it renders in UTC like the other machine-parsed kinds.
    result, client, seen = _run_diff_job_with_return_code(monkeypatch, 0)

    assert result.status == "completed"
    assert seen["cmd"][:4] == ["borg", "diff", "--json-lines", "--"]
    assert seen["env"]["TZ"] == "UTC"
    assert seen["env"]["BORG_PASSPHRASE"] == "secret"
    assert client.uploaded["job_id"] == 97
    assert client.uploaded["bytes"] == b'{"path": "a", "change": "added"}\n'
    complete_call = [c for c in client.calls if c[0] == "complete_job"][0]
    assert complete_call[2] == {
        "return_code": 0,
        "command": seen["cmd"],
        "artifact": True,
    }
    assert not [c for c in client.calls if c[0] == "fail_job"]


@pytest.mark.unit
def test_repository_diff_completes_with_warnings_on_a_borg_warning(monkeypatch):
    # rc 1 is Borg's warning: the listing was produced in full and the
    # server's history index accepts it (its BORG_OK_EXIT_CODES). Failing
    # the job here would throw away a complete diff and burn one of the
    # archive's bounded retries for nothing.
    result, client, seen = _run_diff_job_with_return_code(
        monkeypatch, 1, stderr=b"file changed while we backed it up\n"
    )

    assert result.status == "completed_with_warnings"
    assert result.return_code == 1
    assert client.uploaded["job_id"] == 97
    complete_call = [c for c in client.calls if c[0] == "complete_job"][0]
    assert complete_call[2]["return_code"] == 1
    assert complete_call[2]["artifact"] is True
    stderr_logs = [c for c in client.calls if c[0] == "send_log" and c[3] == "stderr"]
    assert stderr_logs and "file changed" in stderr_logs[-1][4]
    assert not [c for c in client.calls if c[0] == "fail_job"]


@pytest.mark.unit
def test_repository_diff_fails_on_a_borg_error(monkeypatch):
    result, client, _ = _run_diff_job_with_return_code(
        monkeypatch, 2, stderr=b"Failed to create/acquire the lock\n"
    )

    assert result.status == "failed"
    assert result.return_code == 2
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert fail_call[3] == 2
    assert not [c for c in client.calls if c[0] == "complete_job"]


@pytest.mark.unit
def test_repository_extract_file_still_fails_on_a_borg_warning(monkeypatch):
    # The warning tolerance is the diff job's alone: a file served with a
    # warning may be incomplete, and a download must not pretend otherwise.
    def fake_popen(cmd, **kwargs):
        return SimpleNamespace(
            stdout=_ChunkedStdout(b"partial"),
            stderr=SimpleNamespace(read=lambda: b"warning\n"),
            wait=lambda: 1,
            poll=lambda: 1,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )
    client = _ArtifactClient([])

    result = execute_repository_operation_job(
        {
            "id": 98,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "archive-1",
                    "file_path": "docs/report.txt",
                    "delivery": "artifact",
                },
            },
        },
        client,
    )

    assert result.status == "failed"
    assert [c for c in client.calls if c[0] == "fail_job"]


@pytest.mark.unit
def test_repository_diff_fails_when_the_server_dropped_the_upload(monkeypatch):
    # The artifact route answers 200 with `accepted: false` when no consumer
    # is registered for the job or it left mid-stream. For a download that
    # is a person who closed the tab; for a listing it is a job that did
    # not happen, and a `completed` row would read as a delivered one.
    def fake_popen(cmd, **kwargs):
        return SimpleNamespace(
            stdout=_ChunkedStdout(b'{"path": "a", "change": "added"}\n'),
            stderr=SimpleNamespace(read=lambda: b""),
            wait=lambda: 0,
            poll=lambda: 0,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )

    class _DroppingClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            data.read()
            return {"accepted": False, "size": 0}

    client = _DroppingClient([])

    result = execute_repository_operation_job(
        {
            "id": 99,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "failed"
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "not delivered" in fail_call[2]
    assert not [c for c in client.calls if c[0] == "complete_job"]


@pytest.mark.unit
def test_repository_diff_fails_without_an_explicit_delivery_confirmation(monkeypatch):
    # Fail closed: the transport returns {} for a bodyless answer (a proxy
    # that swallowed the body, say), and only the server's explicit yes
    # says a consumer took the listing.
    def fake_popen(cmd, **kwargs):
        return SimpleNamespace(
            stdout=_ChunkedStdout(b'{"path": "a", "change": "added"}\n'),
            stderr=SimpleNamespace(read=lambda: b""),
            wait=lambda: 0,
            poll=lambda: 0,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )

    class _SilentClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            data.read()
            return {}

    client = _SilentClient([])

    result = execute_repository_operation_job(
        {
            "id": 108,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "failed"
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "did not confirm" in fail_call[2]
    assert not [c for c in client.calls if c[0] == "complete_job"]


@pytest.mark.unit
def test_repository_diff_keeps_borgs_reason_when_the_consumer_gave_up(monkeypatch):
    # borg failed before writing a byte (a held lock), the consumer's
    # first-byte timeout expired and the upload came back rejected: the
    # job fails as not delivered, and the lock error must still reach the
    # log, or the operator retries blind against the same lock.
    def fake_popen(cmd, **kwargs):
        return SimpleNamespace(
            stdout=_ChunkedStdout(b""),
            stderr=SimpleNamespace(read=lambda: b"Failed to create/acquire the lock\n"),
            wait=lambda: 2,
            poll=lambda: 2,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )

    class _DroppingClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            data.read()
            return {"accepted": False, "size": 0}

    client = _DroppingClient([])

    result = execute_repository_operation_job(
        {
            "id": 109,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "failed"
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "not delivered" in fail_call[2] and "code 2" in fail_call[2]
    stderr_logs = [c for c in client.calls if c[0] == "send_log" and c[3] == "stderr"]
    assert stderr_logs and "acquire the lock" in stderr_logs[-1][4]


@pytest.mark.unit
def test_streaming_keepalive_never_holds_the_watchdog(monkeypatch):
    # On the polling transport a keepalive is an HTTP request with retries.
    # It runs on its own thread, so a server that does not answer cannot
    # delay a cancellation by the length of those retries.
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.STREAM_KEEPALIVE_SECONDS", 0.1
    )
    terminated = threading.Event()
    killed = _watchdog_process(monkeypatch, terminated, _StallingStdout(terminated))
    cancel_at = time.monotonic() + 0.2

    class _HangingClient(_ArtifactClient):
        def send_progress(self, job_id, progress):
            self.calls.append(("send_progress", job_id, progress))
            time.sleep(3)  # the retries of an unreachable server
            return {"id": job_id, "status": "running"}

        def cancel_job(self, job_id):
            self.calls.append(("cancel_job", job_id))
            return {"id": job_id, "status": "canceled"}

    client = _HangingClient([])
    started = time.monotonic()

    result = execute_repository_operation_job(
        {
            "id": 110,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
        should_cancel=lambda: time.monotonic() >= cancel_at,
    )

    assert result.status == "canceled"
    assert killed.is_set()
    assert [c for c in client.calls if c[0] == "send_progress"]
    # Cancelled within about a poll tick of the request; joining the
    # hanging keepalive would have taken the verdict past its 3 s sleep,
    # which started no later than the first keepalive tick at 0.1 s.
    assert time.monotonic() - started < 3.0


@pytest.mark.unit
def test_streaming_watchdog_survives_a_failing_cancel_check(monkeypatch):
    # The cancel check may ask the server and fail while it is unreachable.
    # The watchdog must go on: it enforces the deadline too, and with the
    # keepalive reporting the job alive, a dead watchdog would leave a job
    # that nothing can stop any more. A later answer still cancels.
    terminated = threading.Event()
    killed = _watchdog_process(monkeypatch, terminated, _StallingStdout(terminated))
    answers = iter([RuntimeError("heartbeat failed"), RuntimeError("again"), True])

    def should_cancel():
        answer = next(answers, True)
        if isinstance(answer, Exception):
            raise answer
        return answer

    class _CancelClient(_ArtifactClient):
        def cancel_job(self, job_id):
            self.calls.append(("cancel_job", job_id))
            return {"id": job_id, "status": "canceled"}

    client = _CancelClient([])

    result = execute_repository_operation_job(
        {
            "id": 111,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
        should_cancel=should_cancel,
    )

    assert result.status == "canceled"
    assert killed.is_set()
    assert ("cancel_job", 111) in client.calls


@pytest.mark.unit
def test_activity_reader_pads_a_silent_pipe_with_blank_lines():
    # A diff's upload carries nothing while borg compares unchanged paths;
    # a proxy in front of the server may cut an idle request body. Padding
    # keeps bytes flowing without counting as activity or as output.
    from agent.borg_ui_agent.repository_ops import _ActivityTrackingReader

    read_fd, write_fd = os.pipe()
    # Buffered like a Popen pipe: a buffered read(n) would block until n
    # bytes arrived, so the reader must not go through it.
    stream = os.fdopen(read_fd, "rb")
    try:
        reader = _ActivityTrackingReader(stream, pad_idle_seconds=0.05)
        before = reader.last_activity

        assert reader.read(8192) == b"\n"
        assert reader.bytes_read == 0
        assert reader.last_activity == before

        # A flush that ends inside a record: the partial line is held back,
        # the silence that follows is padded at a line boundary.
        os.write(write_fd, b'{"path": "a')
        assert reader.read(8192) == b"\n"
        assert reader.bytes_read == 11

        os.write(write_fd, b'"}\n{"path": "b"}\n{"pa')
        assert reader.read(8192) == b'{"path": "a"}\n{"path": "b"}\n'
        assert reader.bytes_read == 11 + 21
        assert reader.last_activity > before

        # End of output: the tail goes out as it is, then the empty read.
        os.close(write_fd)
        write_fd = None
        assert reader.read(8192) == b'{"pa'
        assert reader.read(8192) == b""
        # A whole-output read would take one batch of lines for the whole
        # listing: refused rather than served short.
        with pytest.raises(ValueError, match="size"):
            reader.read()
    finally:
        stream.close()
        if write_fd is not None:
            os.close(write_fd)

    # Without padding the reader blocks on the read, as the extract needs.
    plain = _ActivityTrackingReader(_ChunkedStdout(b"x"))
    assert plain.read() == b"x"
    assert plain.read() == b""


@pytest.mark.unit
def test_repository_diff_streams_through_a_padding_reader(monkeypatch):
    seen = {}

    class _Reader:
        def __init__(self, stream, *, pad_idle_seconds=None):
            seen["pad"] = pad_idle_seconds
            self._stream = stream
            self.last_activity = time.monotonic()
            self.bytes_read = 0

        def read(self, *args):
            return self._stream.read(*args)

        def close(self):
            self._stream.close()

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops._ActivityTrackingReader", _Reader
    )

    def fake_popen(cmd, **kwargs):
        return SimpleNamespace(
            stdout=_ChunkedStdout(b""),
            stderr=SimpleNamespace(read=lambda: b""),
            wait=lambda: 0,
            poll=lambda: 0,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )

    execute_repository_operation_job(
        {
            "id": 112,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        _ArtifactClient([]),
    )
    assert seen["pad"] == 30

    execute_repository_operation_job(
        {
            "id": 113,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "archive-1",
                    "file_path": "docs/report.txt",
                    "delivery": "artifact",
                },
            },
        },
        _ArtifactClient([]),
    )
    # An extract's bytes are the file: never padded.
    assert seen["pad"] is None


@pytest.mark.unit
def test_repository_diff_budget_ignores_a_boolean_timeout():
    from agent.borg_ui_agent.repository_ops import _operation_timeout_seconds

    assert _operation_timeout_seconds({"timeout_seconds": True}, 5.0) == 5.0


@pytest.mark.unit
def test_streaming_deadline_does_not_wait_for_a_blocked_cancel_check(monkeypatch):
    # On the polling transport the cancel check is a heartbeat request
    # with retries; one that hangs on an unreachable server must not hold
    # the deadline.
    terminated = threading.Event()
    killed = _watchdog_process(monkeypatch, terminated, _StallingStdout(terminated))
    entered = threading.Event()

    def should_cancel():
        entered.set()
        time.sleep(3)
        return False

    client = _ArtifactClient([])
    started = time.monotonic()

    # The poller's first tick (0.5 s) enters the hanging check; the
    # deadline (0.8 s) is due on the watchdog's second tick while the
    # check still hangs.
    result = execute_repository_operation_job(
        {
            "id": 114,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "daily-2",
                    "predecessor": "daily-1",
                    "timeout_seconds": 0.8,
                },
            },
        },
        client,
        should_cancel=should_cancel,
    )

    assert result.status == "failed"
    assert entered.is_set()
    assert killed.is_set()
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "stopped by the watchdog: ran longer than 0.8s" in fail_call[2]
    assert time.monotonic() - started < 3.0


@pytest.mark.unit
def test_repository_diff_ends_borg_when_the_server_rejects_the_upload(monkeypatch):
    # The consumer left mid-stream: the server answers the upload early
    # with `accepted: false` while borg is still comparing unchanged paths.
    # Closing stdout ends borg only at its next write, so the agent ends it.
    terminated = threading.Event()
    killed = _watchdog_process(monkeypatch, terminated, _StallingStdout(terminated))

    class _RejectingClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            return {"accepted": False, "size": 0}

    client = _RejectingClient([])
    started = time.monotonic()

    result = execute_repository_operation_job(
        {
            "id": 115,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "failed"
    assert killed.is_set()
    assert time.monotonic() - started < 5
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "not delivered" in fail_call[2]


@pytest.mark.unit
def test_repository_extract_file_completes_when_the_downloader_left(monkeypatch):
    # The download keeps its contract: a consumer that left is not the
    # agent's failure, and nothing reads the job's verdict afterwards.
    def fake_popen(cmd, **kwargs):
        return SimpleNamespace(
            stdout=_ChunkedStdout(b"filebytes"),
            stderr=SimpleNamespace(read=lambda: b""),
            wait=lambda: 0,
            poll=lambda: 0,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )

    class _DroppingClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            data.read()
            return {"accepted": False, "size": 0}

    client = _DroppingClient([])

    result = execute_repository_operation_job(
        {
            "id": 100,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "archive-1",
                    "file_path": "docs/report.txt",
                    "delivery": "artifact",
                },
            },
        },
        client,
    )

    assert result.status == "completed"


@pytest.mark.unit
def test_repository_diff_fails_when_the_upload_breaks(monkeypatch):
    # borg has already exited here; the terminate finds nothing to end.
    def fake_popen(cmd, **kwargs):
        return SimpleNamespace(
            stdout=_ChunkedStdout(b'{"path": "a", "change": "added"}\n'),
            stderr=SimpleNamespace(read=lambda: b""),
            wait=lambda: 0,
            poll=lambda: 0,
            returncode=0,
        )

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", fake_popen
    )

    class _BrokenClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            raise RuntimeError("connection reset")

    client = _BrokenClient([])

    result = execute_repository_operation_job(
        {
            "id": 101,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "failed"
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "upload failed" in fail_call[2] and "connection reset" in fail_call[2]
    assert not [c for c in client.calls if c[0] == "complete_job"]


class _StallingStdout:
    """Blocks in read() until the watchdog terminates the process, then
    ends the stream; `data` is served after `delay` seconds when the
    watchdog has not struck by then."""

    def __init__(self, terminated, *, delay=None, data=b""):
        self._terminated = terminated
        self._delay = delay
        self._data = data
        self._served = False

    def read(self, *args):
        if self._served:
            return b""
        if self._delay is not None and not self._terminated.wait(timeout=self._delay):
            self._served = True
            return self._data
        self._terminated.wait(timeout=5)
        return b""

    def close(self):
        self._terminated.set()


def _watchdog_process(monkeypatch, terminated, stdout, *, stderr=b""):
    """A fake borg whose stdout is `stdout`. `terminated` unblocks the
    stdout (the helper closes it after the upload; the watchdog's kill
    sets it too); `killed` records only the watchdog's kill and decides
    the exit code, so a run the watchdog left alone exits 0."""
    killed = threading.Event()

    def _kill(pgid, sig):
        killed.set()
        terminated.set()

    process = SimpleNamespace(
        stdout=stdout,
        stderr=SimpleNamespace(read=lambda: stderr),
        pid=4321,
        poll=lambda: -15 if killed.is_set() else None,
        wait=lambda *a, **k: -15 if killed.is_set() else 0,
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", lambda *a, **k: process
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.os.getpgid", lambda pid: 9999
    )
    monkeypatch.setattr("agent.borg_ui_agent.repository_ops.os.killpg", _kill)
    return killed


@pytest.mark.unit
def test_repository_diff_is_not_killed_for_stdout_silence(monkeypatch):
    # `borg diff --json-lines` prints a line per changed path and nothing
    # while it compares unchanged ones, so stdout silence says nothing
    # about a diff. The extract's idle bound must not apply to it: with
    # that bound far below the silence, the listing still completes, and
    # an extract under the same silence is stalled as before.
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.STREAM_EXTRACT_IDLE_SECONDS", 0.05
    )
    terminated = threading.Event()
    killed = _watchdog_process(
        monkeypatch,
        terminated,
        _StallingStdout(terminated, delay=1.2, data=b'{"path": "a"}\n'),
    )
    client = _ArtifactClient([])

    result = execute_repository_operation_job(
        {
            "id": 102,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "completed"
    assert client.uploaded["bytes"] == b'{"path": "a"}\n'
    assert not killed.is_set()

    terminated = threading.Event()
    killed = _watchdog_process(
        monkeypatch,
        terminated,
        _StallingStdout(terminated, delay=1.2, data=b"filebytes"),
    )
    client = _ArtifactClient([])

    result = execute_repository_operation_job(
        {
            "id": 103,
            "payload": {
                "job_kind": "repository.extract_archive_file",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "archive-1",
                    "file_path": "docs/report.txt",
                    "delivery": "artifact",
                },
            },
        },
        client,
    )

    assert result.status == "failed"
    assert killed.is_set()
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "stopped by the watchdog: no output for 0.05s" in fail_call[2]


@pytest.mark.unit
def test_repository_diff_is_bounded_by_the_server_budget(monkeypatch):
    # No idle bound does not mean no bound: the payload's timeout_seconds
    # (the server's wait budget) caps the run, and the agent's own
    # generous default caps it without one, so a wedged borg cannot pin
    # the worker for good.
    terminated = threading.Event()
    killed = _watchdog_process(
        monkeypatch,
        terminated,
        _StallingStdout(terminated),
        stderr=b"Remote: connection stalled\n",
    )
    client = _ArtifactClient([])

    result = execute_repository_operation_job(
        {
            "id": 104,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {
                    "archive": "daily-2",
                    "predecessor": "daily-1",
                    "timeout_seconds": 0.2,
                },
            },
        },
        client,
    )

    assert result.status == "failed"
    assert killed.is_set()
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "stopped by the watchdog: ran longer than 0.2s" in fail_call[2]
    # Whatever borg said before it was ended is the operator's lead.
    stderr_logs = [c for c in client.calls if c[0] == "send_log" and c[3] == "stderr"]
    assert stderr_logs and "connection stalled" in stderr_logs[-1][4]


@pytest.mark.unit
def test_repository_diff_default_budget_is_an_hour():
    from agent.borg_ui_agent.repository_ops import (
        STREAM_DIFF_MAX_SECONDS,
        _operation_timeout_seconds,
    )

    assert STREAM_DIFF_MAX_SECONDS == 3600
    assert (
        _operation_timeout_seconds({"timeout_seconds": "x"}, STREAM_DIFF_MAX_SECONDS)
        == STREAM_DIFF_MAX_SECONDS
    )
    assert _operation_timeout_seconds({"timeout_seconds": 90}, 5.0) == 90.0


@pytest.mark.unit
def test_repository_diff_is_cancelled_through_the_watchdog(monkeypatch):
    terminated = threading.Event()
    killed = _watchdog_process(monkeypatch, terminated, _StallingStdout(terminated))

    class _CancelClient(_ArtifactClient):
        def cancel_job(self, job_id):
            self.calls.append(("cancel_job", job_id))
            return {"id": job_id, "status": "canceled"}

    client = _CancelClient([])

    result = execute_repository_operation_job(
        {
            "id": 105,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
        should_cancel=lambda: True,
    )

    assert result.status == "canceled"
    assert killed.is_set()
    assert ("cancel_job", 105) in client.calls
    assert not [c for c in client.calls if c[0] in ("complete_job", "fail_job")]


@pytest.mark.unit
def test_streaming_jobs_keep_the_server_informed_while_silent(monkeypatch):
    # Nothing reaches the job row while a stream runs (logs and the result
    # come at the end, the heartbeat only lists the job), and the server
    # reaps an in-flight job after 15 minutes without activity. The
    # watchdog reports a progress keepalive meanwhile; a keepalive that
    # fails to send is dropped, not fatal.
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.STREAM_KEEPALIVE_SECONDS", 0.3
    )
    terminated = threading.Event()
    killed = _watchdog_process(
        monkeypatch,
        terminated,
        _StallingStdout(terminated, delay=1.4, data=b'{"path": "a"}\n'),
    )

    class _FlakyClient(_ArtifactClient):
        def send_progress(self, job_id, progress):
            self.calls.append(("send_progress", job_id, progress))
            if len([c for c in self.calls if c[0] == "send_progress"]) == 1:
                raise RuntimeError("socket closed")
            return {"id": job_id, "status": "running"}

    client = _FlakyClient([])

    result = execute_repository_operation_job(
        {
            "id": 106,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "completed"
    assert not killed.is_set()
    keepalives = [c for c in client.calls if c[0] == "send_progress"]
    assert len(keepalives) >= 2
    # A sign of life only: no field of the progress schema is a fact
    # about a stream.
    assert all(c[1] == 106 and c[2] == {} for c in keepalives)


@pytest.mark.unit
def test_repository_diff_ends_borg_when_the_upload_breaks_mid_silence(monkeypatch):
    # Closing stdout ends borg only at its next write, and a diff comparing
    # unchanged paths may not write for a long time: without a terminate the
    # worker would sit in process.wait() until the deadline.
    terminated = threading.Event()
    killed = _watchdog_process(monkeypatch, terminated, _StallingStdout(terminated))

    class _BrokenClient(FakeRuntimeClient):
        def upload_artifact(self, job_id, data):
            raise RuntimeError("connection reset")

    client = _BrokenClient([])
    started = time.monotonic()

    result = execute_repository_operation_job(
        {
            "id": 107,
            "payload": {
                "job_kind": "repository.diff",
                "repository": {"path": "/agent/repo", "borg_version": 1},
                "operation": {"archive": "daily-2", "predecessor": "daily-1"},
            },
        },
        client,
    )

    assert result.status == "failed"
    assert killed.is_set()
    assert time.monotonic() - started < 5
    fail_call = [c for c in client.calls if c[0] == "fail_job"][0]
    assert "upload failed" in fail_call[2]


@pytest.mark.unit
def test_a_keepalive_reaches_the_server_over_rest_after_the_session_dropped():
    """The worker survives a dropped socket; its progress keepalive must
    still land, or the reaper fails a job that is running."""
    from agent.borg_ui_agent.session import SessionCommandClient

    class RestClient:
        def __init__(self):
            self.progress = []
            self.logs = []

        def send_progress(self, job_id, progress):
            self.progress.append((job_id, progress))

        def send_log(self, job_id, *, sequence, stream, message):
            self.logs.append((job_id, sequence, stream, message))

    rest = RestClient()
    closing = threading.Event()
    closing.set()
    client = SessionCommandClient(
        command_id="cmd-1",
        job_id=77,
        outbox=queue.Queue(),
        closing=closing,
        artifact_uploader=None,
        http_client=rest,
        http_lock=threading.Lock(),
    )
    client.started = True

    client.send_progress(77, {})
    client.send_log(77, sequence=3, stream="stdout", message="still going")

    assert rest.progress == [(77, {})]
    assert rest.logs == [(77, 3, "stdout", "still going")]
