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
from agent.borg_ui_agent.runtime import AgentRuntime, get_capabilities


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
    paths = {"borg": "/usr/bin/borg", "borg2": "/usr/local/bin/borg2"}

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
        {"major": 1, "version": "1.2.8", "path": "/usr/bin/borg"},
        {"major": 2, "version": "2.0.0b10", "path": "/usr/local/bin/borg2"},
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
        agent_version="0.1.0",
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
        "--compression",
        "none",
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


class FakeStdout:
    def __init__(self, lines):
        self.lines = lines

    def __iter__(self):
        return iter(self.lines)


class FakeProcess:
    def __init__(self, lines, return_code):
        self.stdout = FakeStdout(lines)
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

    def fake_popen(cmd, stdout, stderr, text, env):
        popen_calls.append(
            {"cmd": cmd, "stdout": stdout, "stderr": stderr, "text": text, "env": env}
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
    assert any(call[0] == "send_progress" for call in client.calls)
    complete_call = [call for call in client.calls if call[0] == "complete_job"][0]
    assert complete_call[2]["archive_name"] == "archive"
    assert complete_call[2]["return_code"] == 0


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

    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.subprocess.Popen",
        lambda *args, **kwargs: process,
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
    assert process.terminated is True
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
