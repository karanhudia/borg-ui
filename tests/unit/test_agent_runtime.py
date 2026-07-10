import base64
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.borg_ui_agent.backup import (
    BackupCreatePayload,
    execute_backup_create_job,
    parse_borg_progress,
)
from agent.borg_ui_agent.borg import detect_borg_binaries
from agent.borg_ui_agent.client import AGENT_AUTH_HEADER, AgentClient
from agent.borg_ui_agent.config import AgentConfig, load_config, save_config
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    execute_repository_operation_job,
    _write_temp_rclone_config,
)
from agent.borg_ui_agent.runtime import AgentRuntime, get_capabilities


class FakeWebSocket:
    def __init__(self, incoming):
        self.incoming = list(incoming)
        self.sent = []
        self.closed = False
        self.pings = 0

    def send(self, payload):
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

    assert command == [
        "borg2",
        "-r",
        "/agent/repo2",
        "repo-create",
        "--encryption",
        "repokey-aes-ocb",
    ]


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
        "agent_version": "0.1.1",
        "borg_versions": [],
        "capabilities": get_capabilities(),
        "running_job_ids": [],
    }
    assert socket.closed is True


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

    runtime = AgentSessionRuntime(
        AgentConfig("https://borgui.example.com", "agt_123", "secret"),
        connect=lambda *args, **kwargs: socket,
    )
    runtime.run_session(max_messages=1)

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
    assert socket.sent[5]["type"] == "command_result"
    assert socket.sent[5]["result"] == {"archive_name": "archive"}


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
            "operation": {"keep_daily": 7, "keep_within": "1d", "dry_run": True},
        }
    )

    assert info_payload.build_command() == ["borg", "info", "--json", "/agent/repo"]
    assert prune_payload.build_command() == [
        "borg2",
        "-r",
        "/agent/repo",
        "prune",
        "--progress",
        "--stats",
        "--show-rc",
        "--log-json",
        "--keep-daily",
        "7",
        "--keep-within=1d",
        "--dry-run",
    ]


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
    assert popen_calls[0]["kwargs"]["start_new_session"] is True
    assert any(call[0] == "send_progress" for call in client.calls)
    complete_call = [call for call in client.calls if call[0] == "complete_job"][0]
    # No --json document on stdout -> fall back to the requested archive name.
    assert complete_call[2]["archive_name"] == "archive"
    assert complete_call[2]["return_code"] == 0


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

    def kill(self):
        raise AssertionError("process should terminate cleanly")

    def wait(self, timeout=None):
        return self.return_code


@pytest.mark.unit
def test_execute_backup_create_job_cancels_running_process(monkeypatch):
    process = CancelableProcess(["first line\n", "second line\n"], -15)
    killed_groups = []

    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.subprocess.Popen",
        lambda *args, **kwargs: process,
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
        should_cancel=lambda: True,
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
