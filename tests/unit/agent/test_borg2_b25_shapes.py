"""Command shapes and environment the agent gives Borg 2, against what
Borg 2.0.0b25 accepts (replayed against the real binary)."""

import json
import sys
import types

import pytest

from agent.borg_ui_agent import storage_usage
from agent.borg_ui_agent.backup import execute_backup_create_job
from agent.borg_ui_agent.repository_ops import (
    RepositoryOperationPayload,
    execute_repository_operation_job,
)

# One operation block that satisfies every job kind's required fields.
_OPERATION = {
    "encryption": "repokey-aes-ocb",
    "archive": "aid:0123456789abcdef",
    "predecessor": "aid:fedcba9876543210",
    "path": "etc",
    "file_path": "etc/hosts",
    "directory_path": "etc",
    "target": {"type": "temp"},
    "keep_daily": 7,
    "keep_within": "1d",
}

_BORG_JOB_KINDS = [
    "repository.init",
    "repository.info",
    "repository.rinfo",
    "repository.archive_info",
    "repository.delete_archive",
    "repository.break_lock",
    "repository.list_archives",
    "repository.list_archive_contents",
    "repository.diff",
    "repository.extract_archive_file",
    "repository.export_archive_tar",
    "repository.restore",
    "repository.check",
    "repository.compact",
    "repository.prune",
]


def _payload(job_kind: str, borg_version: int) -> RepositoryOperationPayload:
    return RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": job_kind,
            "repository": {
                "path": "ssh://borg@repo.example/backups/one",
                "borg_version": borg_version,
                "remote_path": "/opt/borg2/bin/borg",
            },
            "operation": dict(_OPERATION),
            "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
        }
    )


@pytest.mark.unit
@pytest.mark.parametrize("job_kind", _BORG_JOB_KINDS)
def test_borg2_remote_path_is_not_on_the_command_line(job_kind):
    """Borg 2.0.0b22 removed --remote-path: a command that carries it fails
    with "unrecognized arguments" before it reaches the repository."""
    payload = _payload(job_kind, 2)

    command = payload.build_command()

    assert "--remote-path" not in command
    assert "/opt/borg2/bin/borg" not in command
    assert payload.remote_path_env() == {"BORG_REMOTE_PATH": "/opt/borg2/bin/borg"}


@pytest.mark.unit
@pytest.mark.parametrize("job_kind", _BORG_JOB_KINDS)
def test_borg1_keeps_remote_path_on_the_command_line(job_kind):
    payload = _payload(job_kind, 1)
    if job_kind == "repository.init":
        payload = RepositoryOperationPayload.from_job_payload(
            {
                "schema_version": 1,
                "job_kind": job_kind,
                "repository": {
                    "path": "ssh://borg@repo.example/backups/one",
                    "borg_version": 1,
                    "remote_path": "/opt/borg2/bin/borg",
                },
                "operation": {"encryption": "repokey"},
            }
        )

    command = payload.build_command()

    assert command[command.index("--remote-path") + 1] == "/opt/borg2/bin/borg"
    assert payload.remote_path_env() == {}


class _Client:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


@pytest.mark.unit
@pytest.mark.parametrize("job_kind", ["repository.break_lock", "repository.rinfo"])
def test_borg2_operation_runs_with_remote_path_and_passphrase(monkeypatch, job_kind):
    """break-lock needs the key from 2.0.0b25 on (the lock is sealed with
    it), so it runs with the passphrase like every other operation; the
    remote Borg command reaches Borg 2 through the environment."""
    monkeypatch.setenv("BORG_REMOTE_PATH", "inherited")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return types.SimpleNamespace(returncode=0, stdout="{}", stderr="")

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            self.returncode = 0
            self.stdout = []
            self.stderr = []
            self.pid = 1

        def communicate(self, *args, **kwargs):
            return "{}", ""

        def wait(self, *args, **kwargs):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr("agent.borg_ui_agent.repository_ops.subprocess.run", fake_run)
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", FakePopen
    )

    execute_repository_operation_job(
        {
            "id": 11,
            "payload": {
                "schema_version": 1,
                "job_kind": job_kind,
                "repository": {
                    "path": "ssh://borg@repo.example/backups/one",
                    "borg_version": 2,
                    "remote_path": "/opt/borg2/bin/borg",
                },
                "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
            },
        },
        _Client(),
        should_cancel=None,
    )

    assert "--remote-path" not in captured["cmd"]
    assert captured["env"]["BORG_REMOTE_PATH"] == "/opt/borg2/bin/borg"
    assert captured["env"]["BORG_PASSPHRASE"] == "secret"


@pytest.mark.unit
def test_borg2_backup_runs_with_the_remote_path_in_the_environment(monkeypatch):
    captured = {}

    class FakeProcess:
        returncode = 0
        pid = 1

        def __init__(self):
            self.stdout = iter(())
            self.stderr = iter(())

        def wait(self, *args, **kwargs):
            return 0

        def poll(self):
            return 0

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return FakeProcess()

    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", fake_popen)

    execute_backup_create_job(
        {
            "id": 12,
            "payload": {
                "job_kind": "backup.create",
                "repository": {
                    "path": "ssh://borg@repo.example/backups/one",
                    "borg_version": 2,
                    "remote_path": "/opt/borg2/bin/borg",
                },
                "archive_name": "series",
                "source_paths": ["/src"],
            },
        },
        _Client(),
    )

    assert "--remote-path" not in captured["cmd"]
    assert captured["env"]["BORG_REMOTE_PATH"] == "/opt/borg2/bin/borg"


def _fake_borg(monkeypatch, repository_class, key_factory):
    """Stand-ins for the borg modules the index script imports."""
    modules = {
        "borg": types.ModuleType("borg"),
        "borg.logger": types.ModuleType("borg.logger"),
        "borg.repository": types.ModuleType("borg.repository"),
        "borg.helpers": types.ModuleType("borg.helpers"),
        "borg.crypto": types.ModuleType("borg.crypto"),
        "borg.crypto.key": types.ModuleType("borg.crypto.key"),
    }
    modules["borg.logger"].setup_logging = lambda: None
    modules["borg.repository"].Repository = repository_class
    modules["borg.helpers"].Location = lambda url: url
    modules["borg.crypto.key"].key_factory = key_factory
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


class _Repository:
    def __init__(self, location, exclusive, lock):
        assert lock is False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.unit
def test_index_script_loads_the_key_where_the_index_is_sealed(monkeypatch, capsys):
    """Borg 2.0.0b25 seals the chunk index with the repository key. An
    unlocked open does not load the key, and reading the index without it
    raises KeyRequired: the size measurement found nothing."""
    loaded = []

    class SealedRepository(_Repository):
        key = None

        def list(self, limit=None, marker=None):
            if self.key is None:
                raise RuntimeError("KeyRequired")
            return [] if marker else [(b"a", 100), (b"b", 23)]

    def key_factory(repository):
        loaded.append(repository)
        repository.key = object()

    _fake_borg(monkeypatch, SealedRepository, key_factory)
    monkeypatch.setenv(storage_usage.REPOSITORY_URL_ENV, "/repo")

    exec(compile(storage_usage.INDEX_SUM_SCRIPT, "<index>", "exec"), {})

    assert len(loaded) == 1
    assert json.loads(capsys.readouterr().out) == {"objects": 2, "bytes": 123}


@pytest.mark.unit
def test_index_script_leaves_an_older_borg2_alone(monkeypatch, capsys):
    """Up to 2.0.0b24 the repository object has no key and key_factory wants
    a manifest: the script must not call it there."""

    class PlainRepository(_Repository):
        def list(self, limit=None, marker=None):
            return [] if marker else [(b"a", 7)]

    def key_factory(*args):
        raise AssertionError("key_factory must not be called")

    _fake_borg(monkeypatch, PlainRepository, key_factory)
    monkeypatch.setenv(storage_usage.REPOSITORY_URL_ENV, "/repo")

    exec(compile(storage_usage.INDEX_SUM_SCRIPT, "<index>", "exec"), {})

    assert json.loads(capsys.readouterr().out) == {"objects": 1, "bytes": 7}


@pytest.mark.unit
def test_server_and_agent_run_the_same_index_script():
    from app.services import storage_usage as server_storage_usage

    assert storage_usage.INDEX_SUM_SCRIPT == server_storage_usage.INDEX_SUM_SCRIPT


@pytest.mark.unit
def test_borg2_refuses_the_removed_unencrypted_mode():
    """2.0.0b25 has no none-sha256 any more; the agent says so instead of
    handing repo-create a value it rejects with a usage message."""
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.init",
            "repository": {"path": "/agent/repo", "borg_version": 2},
            "operation": {"encryption": "none"},
        }
    )

    with pytest.raises(ValueError, match="2.0.0b25"):
        payload.build_command()


@pytest.mark.unit
def test_borg1_keeps_its_unencrypted_mode():
    payload = RepositoryOperationPayload.from_job_payload(
        {
            "schema_version": 1,
            "job_kind": "repository.init",
            "repository": {"path": "/agent/repo", "borg_version": 1},
            "operation": {"encryption": "none"},
        }
    )

    cmd = payload.build_command()

    assert cmd[cmd.index("--encryption") + 1] == "none"
    assert cmd[-1] == "/agent/repo"


def _B25(binary: str) -> str:
    return "2.0.0b25"


def _rest_payload(job_kind: str, borg_version: int = 2) -> dict:
    return {
        "schema_version": 1,
        "job_kind": job_kind,
        "repository": {
            "path": "rest://borg@repo.example/backups/one",
            "borg_version": borg_version,
        },
        "operation": dict(_OPERATION),
    }


@pytest.mark.unit
@pytest.mark.parametrize("job_kind", _BORG_JOB_KINDS)
def test_borg2_refuses_a_rest_url(monkeypatch, job_kind):
    """2.0.0b25 reads rest://user@host/path as the local directory
    ./rest:/user@host/path: repo-create and create succeed there (exit 0) and
    nothing reaches the repository server."""
    monkeypatch.setattr("agent.borg_ui_agent.backup.borg2_binary_version", _B25)
    payload = RepositoryOperationPayload.from_job_payload(_rest_payload(job_kind))

    with pytest.raises(ValueError, match="ssh://"):
        payload.build_command()


@pytest.mark.unit
def test_a_refused_rest_url_fails_the_job_without_running_borg(monkeypatch):
    def no_process(*args, **kwargs):
        raise AssertionError("borg must not run")

    monkeypatch.setattr("agent.borg_ui_agent.backup.borg2_binary_version", _B25)
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", no_process
    )
    monkeypatch.setattr("agent.borg_ui_agent.repository_ops.subprocess.run", no_process)
    client = _Client()

    result = execute_repository_operation_job(
        {"id": 3, "payload": _rest_payload("repository.init")}, client
    )

    assert result.status == "failed"
    assert "rest://" in result.message
    assert [call[0] for call in client.calls if call[0] == "fail_job"] == ["fail_job"]


@pytest.mark.unit
def test_a_borg2_backup_to_a_rest_url_fails_without_running_borg(monkeypatch):
    def no_process(*args, **kwargs):
        raise AssertionError("borg must not run")

    monkeypatch.setattr("agent.borg_ui_agent.backup.borg2_binary_version", _B25)
    monkeypatch.setattr("agent.borg_ui_agent.backup.subprocess.Popen", no_process)
    client = _Client()

    result = execute_backup_create_job(
        {
            "id": 4,
            "payload": {
                "job_kind": "backup.create",
                "repository": {
                    "path": "rest://borg@repo.example/backups/one",
                    "borg_version": 2,
                },
                "archive_name": "series",
                "source_paths": ["/src"],
            },
        },
        client,
    )

    assert result.status == "failed"
    assert "rest://" in result.message


@pytest.mark.unit
@pytest.mark.parametrize(
    ("banner", "refused"),
    [
        ("borg2 2.0.0b25\n", True),
        ("borg2 2.0.0b26\n", True),
        ("borg 2.0.0\n", True),
        # an endpoint that manages its own Borg keeps its binary across an
        # agent upgrade, and these still speak rest://
        ("borg2 2.0.0b24\n", False),
        ("borg2 2.0.0b22\n", False),
        # nothing readable is not evidence of an old binary
        ("", True),
        ("borg 1.4.5\n", True),
    ],
)
def test_a_rest_url_is_refused_by_what_the_binary_reports(monkeypatch, banner, refused):
    from agent.borg_ui_agent import backup

    monkeypatch.setattr(backup, "_BINARY_VERSIONS", {})
    monkeypatch.setattr(
        backup.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(
            returncode=0, stdout=banner, stderr=""
        ),
    )
    payload = RepositoryOperationPayload.from_job_payload(
        _rest_payload("repository.list_archives")
    )

    if refused:
        with pytest.raises(ValueError, match="ssh://"):
            payload.build_command()
    else:
        assert payload.build_command()[:3] == [
            "borg2",
            "-r",
            "rest://borg@repo.example/backups/one",
        ]


@pytest.mark.unit
def test_the_binary_is_not_probed_for_other_urls(monkeypatch):
    from agent.borg_ui_agent import backup

    def no_probe(*args, **kwargs):
        raise AssertionError("no probe for a URL that is not rest://")

    monkeypatch.setattr(backup.subprocess, "run", no_probe)

    assert _payload("repository.list_archives", 2).build_command()[3] == "repo-list"


def _restore_job(target: str, borg_version: int = 2) -> dict:
    return {
        "id": 21,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.restore",
            "repository": {"path": "/agent/repo", "borg_version": borg_version},
            "operation": {
                "archive": "aid:0123456789abcdef",
                "target": {"type": "path", "path": target},
                "paths": ["etc/hosts"],
            },
            "secrets": {"BORG_PASSPHRASE": {"value": "secret"}},
        },
    }


def _run_restore(monkeypatch, job: dict) -> tuple[list[str] | None, _Client]:
    captured = {}

    class FakePopen:
        returncode = 0
        pid = 1

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            self.stdout = iter(())

        def wait(self, *args, **kwargs):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", FakePopen
    )
    client = _Client()
    execute_repository_operation_job(job, client, should_cancel=None)
    return captured.get("cmd"), client


@pytest.mark.unit
@pytest.mark.parametrize("occupied_by", ["unrelated.txt", ".hidden", "lost+found"])
def test_borg2_restore_into_an_occupied_directory_is_refused(
    monkeypatch, tmp_path, occupied_by
):
    """Borg 2.0.0b25 refuses a directory that is not empty (exit 33), the
    original location and a fresh filesystem with lost+found included. The
    agent says so before Borg runs; it does not reach for --continue, which
    skips a file that looks restored by type, mode, size and time."""
    monkeypatch.setattr("agent.borg_ui_agent.backup.borg2_binary_version", _B25)
    if occupied_by == "lost+found":
        (tmp_path / occupied_by).mkdir()
    else:
        (tmp_path / occupied_by).write_text("x")

    cmd, client = _run_restore(monkeypatch, _restore_job(str(tmp_path)))

    assert cmd is None, "Borg must not run"
    failed = [call for call in client.calls if call[0] == "fail_job"]
    assert len(failed) == 1
    message = failed[0][2]["error_message"]
    assert str(tmp_path) in message and "empty directory" in message
    assert not [call for call in client.calls if call[0] == "complete_job"]
    logs = [call[2] for call in client.calls if call[0] == "send_log"]
    assert any(log["stream"] == "stderr" and log["message"] == message for log in logs)


@pytest.mark.unit
def test_an_older_borg2_restores_into_an_occupied_directory(monkeypatch, tmp_path):
    """A machine that manages its own Borg keeps its binary across an agent
    upgrade. A Borg 2 before 2.0.0b25 extracts into a directory that holds
    files, so the agent does not take that away from it."""
    monkeypatch.setattr(
        "agent.borg_ui_agent.backup.borg2_binary_version", lambda _binary: "2.0.0b24"
    )
    (tmp_path / "existing.txt").write_text("x")

    cmd, client = _run_restore(monkeypatch, _restore_job(str(tmp_path)))

    assert cmd is not None and cmd[3] == "extract"
    assert "--continue" not in cmd
    assert not [call for call in client.calls if call[0] == "fail_job"]


@pytest.mark.unit
def test_borg2_restore_into_an_empty_directory_is_a_plain_extract(
    monkeypatch, tmp_path
):
    cmd, _client = _run_restore(monkeypatch, _restore_job(str(tmp_path)))

    assert cmd[3] == "extract"
    assert "--continue" not in cmd


@pytest.mark.unit
def test_borg1_restore_into_an_occupied_directory_runs(monkeypatch, tmp_path):
    (tmp_path / "existing.txt").write_text("x")

    cmd, client = _run_restore(monkeypatch, _restore_job(str(tmp_path), 1))

    assert cmd is not None and "--continue" not in cmd
    assert not [call for call in client.calls if call[0] == "fail_job"]


@pytest.mark.unit
def test_borg2_restore_check_extracts_into_its_own_empty_directory(monkeypatch):
    job = _restore_job("/unused")
    job["payload"]["operation"]["target"] = {"type": "temp"}

    cmd, client = _run_restore(monkeypatch, job)

    assert cmd is not None and "--continue" not in cmd
    assert not [call for call in client.calls if call[0] == "fail_job"]


@pytest.mark.unit
@pytest.mark.parametrize("variable", ["BORG_RSH", "BORGSTORE_RSH"])
def test_the_agent_writes_the_port_into_a_remote_shell_it_was_given(
    monkeypatch, variable
):
    """Borg 2 adds the port of the URL only to the ssh command it builds
    itself; with a remote shell in the environment `ssh://host:2222/path`
    would connect to port 22."""
    monkeypatch.delenv("BORG_RSH", raising=False)
    monkeypatch.delenv("BORGSTORE_RSH", raising=False)
    monkeypatch.setenv(variable, "ssh -i /etc/agent/key")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        return types.SimpleNamespace(returncode=0, stdout="{}", stderr="")

    class FakePopen:
        returncode = 0
        pid = 1

        def __init__(self, cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            self.stdout = []
            self.stderr = []

        def communicate(self, *args, **kwargs):
            return "{}", ""

        def wait(self, *args, **kwargs):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr("agent.borg_ui_agent.repository_ops.subprocess.run", fake_run)
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", FakePopen
    )

    execute_repository_operation_job(
        {
            "id": 31,
            "payload": {
                "schema_version": 1,
                "job_kind": "repository.rinfo",
                "repository": {
                    "path": "ssh://borg@repo.example:2222/backups/one",
                    "borg_version": 2,
                },
            },
        },
        _Client(),
        should_cancel=None,
    )

    assert captured["env"][variable] == "ssh -i /etc/agent/key -p 2222"


@pytest.mark.unit
def test_an_agent_without_a_remote_shell_leaves_the_port_to_borg(monkeypatch):
    from agent.borg_ui_agent.backup import env_with_repository_port

    env = {"PATH": "/usr/bin"}

    assert env_with_repository_port(
        env, "ssh://borg@repo.example:2222/backups/one"
    ) == {"PATH": "/usr/bin"}


@pytest.mark.unit
def test_the_refusal_reads_the_subcommand_not_a_word_that_reads_like_it(
    monkeypatch, tmp_path
):
    """Only an extract is refused, and it is told by its place in the
    command: a repository named `extract` does not make a listing one."""
    from agent.borg_ui_agent.repository_ops import _restore_target_refusal

    monkeypatch.setattr("agent.borg_ui_agent.backup.borg2_binary_version", _B25)
    (tmp_path / "existing.txt").write_text("x")
    payload = types.SimpleNamespace(borg_version=2, borg_cmd="borg2")

    assert _restore_target_refusal(
        ["borg2", "-r", "extract", "extract", "aid:1"], payload, str(tmp_path)
    )
    assert (
        _restore_target_refusal(
            ["borg2", "-r", "extract", "repo-list", "--json"], payload, str(tmp_path)
        )
        is None
    )
