import base64
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.borg_ui_agent import storage_usage
from agent.borg_ui_agent.repository_ops import (
    REPOSITORY_JOB_KINDS,
    RepositoryOperationPayload,
    execute_repository_operation_job,
    execute_storage_usage_job,
)
from agent.borg_ui_agent.runtime import DEFAULT_CAPABILITIES, JOB_HANDLERS
from app.services.job_admission import (
    AGENT_JOB_KIND_OPERATIONS,
    OPERATION_CLASS_REPOSITORY_OBSERVE,
    OPERATION_STORAGE_USAGE,
    operation_class_for,
)
from app.services.repository_executor import REPOSITORY_OPERATION_CAPABILITIES

JOB_KIND = "repository.storage_usage"


@pytest.mark.unit
def test_storage_usage_is_advertised_handled_and_admitted():
    assert JOB_KIND in REPOSITORY_JOB_KINDS
    assert JOB_KIND in DEFAULT_CAPABILITIES
    assert JOB_HANDLERS[JOB_KIND] is execute_storage_usage_job
    assert AGENT_JOB_KIND_OPERATIONS[JOB_KIND] == OPERATION_STORAGE_USAGE
    assert JOB_KIND in REPOSITORY_OPERATION_CAPABILITIES
    assert (
        operation_class_for(OPERATION_STORAGE_USAGE)
        == OPERATION_CLASS_REPOSITORY_OBSERVE
    )


@pytest.mark.unit
def test_borg2_compact_runs_with_stats():
    cmd = RepositoryOperationPayload(
        job_kind="repository.compact", repository_path="rest://borg@h/r", borg_version=2
    ).build_command()
    assert cmd[:3] == ["borg2", "-r", "rest://borg@h/r"]
    assert "--stats" in cmd and "--verbose" in cmd and "--log-json" in cmd


class _NullClient:
    def send_log(self, job_id, *, sequence, message, stream="stdout"):
        pass

    def send_progress(self, job_id, progress):
        pass

    def complete_job(self, job_id, *, result):
        pass

    def fail_job(self, job_id, *, error_message, return_code=None):
        pass


def _compact_env(monkeypatch, borg_version):
    """The environment the agent hands Borg for a compact job."""
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            self.returncode = 0
            self.stdout = []
            self.stderr = []
            self.pid = 1

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.subprocess.Popen", _FakePopen
    )
    monkeypatch.setattr(
        "agent.borg_ui_agent.repository_ops.compact_stats_supported",
        lambda binary: True,
    )
    job = {
        "id": 7,
        "payload": {
            "schema_version": 1,
            "job_kind": "repository.compact",
            "repository": {"path": "/agent/repo", "borg_version": borg_version},
        },
    }
    result = execute_repository_operation_job(job, _NullClient(), should_cancel=None)
    assert result.status in ("completed", "completed_with_warnings"), result
    return captured["env"]


@pytest.mark.unit
def test_borg2_compact_prints_exact_byte_counts(monkeypatch):
    """The server parses the --stats lines; an inherited BORG_UNITS=iec
    would print KiB values with no decimals. raw prints exact bytes."""
    monkeypatch.setenv("BORG_UNITS", "iec")
    assert _compact_env(monkeypatch, 2)["BORG_UNITS"] == "raw"
    # Borg 1 compact prints no statistics; nothing to normalize
    assert "BORG_UNITS" not in _compact_env(monkeypatch, 1) or (
        _compact_env(monkeypatch, 1)["BORG_UNITS"] == "iec"
    )


@pytest.mark.unit
def test_index_size_runs_the_script_with_the_venv_python(monkeypatch):
    monkeypatch.setattr(
        storage_usage, "borg2_interpreter", lambda b, env=None: "/venv/bin/python"
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"objects": 4, "bytes": 301284}), stderr=""
        )

    monkeypatch.setattr(storage_usage, "_run", fake_run)
    assert storage_usage.index_size(
        "rest://borg:secret@h/r", borg_binary="borg2", env={"A": "1"}, timeout=5
    ) == (301284, 4)
    cmd, kwargs = calls[0]
    assert cmd[0] == "/venv/bin/python" and cmd[1] == "-c" and len(cmd) == 3
    # the URL may carry credentials: environment, never argv
    assert "secret" not in " ".join(cmd)
    assert kwargs["env"]["BORG_UI_REPOSITORY_URL"] == "rest://borg:secret@h/r"
    assert kwargs["env"]["A"] == "1"
    assert "lock=False" in cmd[2]
    assert "marker" in cmd[2] and "[size for" not in cmd[2]

    monkeypatch.setattr(storage_usage, "borg2_interpreter", lambda b, env=None: None)
    assert (
        storage_usage.index_size("/r", borg_binary="borg2", env=None, timeout=5) is None
    )


@pytest.mark.unit
def test_store_target_and_rclone_remote():
    assert storage_usage.store_target("rest://borg@host/store/repo") == ("", None)
    assert storage_usage.store_target("rest:///srv/store") == ("du", "/srv/store")
    assert storage_usage.store_target("sftp://u@h:23/./r") == (
        "rclone",
        "sftp://u@h:23/./r",
    )
    assert storage_usage.store_target("http://u:p@srv/store") == (
        "http",
        "http://u:p@srv/store",
    )
    assert storage_usage.store_target("s3:profile@bucket") == ("", None)
    assert (
        storage_usage.rclone_remote_for("sftp://us%40er@h:23/./dir%20one")
        == ":sftp,host=h,user=us@er,port=23:dir one"
    )
    # the scheme is case-insensitive, the text after it keeps its case
    assert storage_usage.store_target("HTTPS://srv/Store") == (
        "http",
        "HTTPS://srv/Store",
    )
    assert storage_usage.store_target("Rclone:Remote:Path") == (
        "rclone",
        "Rclone:Remote:Path",
    )
    assert storage_usage.store_target("REST://borg@host/r") == ("", None)
    assert storage_usage.store_target("S3:profile@bucket") == ("", None)
    assert storage_usage.rclone_remote_for("RCLONE:Remote:Path") == "Remote:Path"
    assert storage_usage.rclone_remote_for("SFTP://u@h/./r") == ":sftp,host=h,user=u:r"


@pytest.mark.unit
def test_measure_order_and_explicit_reasons(monkeypatch):
    monkeypatch.setattr(storage_usage, "index_size", lambda *a, **k: (301284, 4))
    assert storage_usage.measure(
        "rest://borg@h/r", borg_version=2, borg_binary="borg2"
    ) == {
        "bytes": 301284,
        "objects": 4,
        "source": "borg2_index",
    }
    monkeypatch.setattr(storage_usage, "index_size", lambda *a, **k: None)
    monkeypatch.setattr(
        storage_usage,
        "storage_used",
        lambda url, timeout, env=None, should_cancel=None: (424242, "rclone"),
    )
    assert storage_usage.measure(
        "sftp://u@h/r", borg_version=2, borg_binary="borg2"
    ) == {
        "bytes": 424242,
        "objects": None,
        "source": "storage_used",
        "tool": "rclone",
    }
    monkeypatch.setattr(
        storage_usage,
        "storage_used",
        lambda url, timeout, env=None, should_cancel=None: (None, ""),
    )
    result = storage_usage.measure(
        "rest://borg@h/r", borg_version=2, borg_binary="borg2"
    )
    assert result["bytes"] is None and result["reason"] == "unsupported_scheme"
    # an empty index is not an empty store: the store measurement follows,
    # and its failure reason is the result's reason
    monkeypatch.setattr(storage_usage, "index_size", lambda *a, **k: (0, 0))
    monkeypatch.setattr(
        storage_usage,
        "storage_used",
        lambda url, timeout, env=None, should_cancel=None: (2048, "du"),
    )
    assert storage_usage.measure("/r", borg_version=2, borg_binary="borg2") == {
        "bytes": 2048,
        "objects": None,
        "source": "storage_used",
        "tool": "du",
    }
    monkeypatch.setattr(
        storage_usage,
        "storage_used",
        lambda url, timeout, env=None, should_cancel=None: (None, "du"),
    )
    empty = storage_usage.measure("/r", borg_version=2, borg_binary="borg2")
    assert empty["bytes"] is None and empty["reason"] == "du_failed"
    assert storage_usage.measure("/r", borg_version=1, borg_binary="borg")[
        "reason"
    ] == ("borg1_uses_rinfo")


class FakeClient:
    def __init__(self):
        self.logs = []
        self.completed = None
        self.failed = None

    def send_log(self, job_id, *, sequence, message, stream="stdout"):
        self.logs.append((stream, message))

    def complete_job(self, job_id, *, result):
        self.completed = (job_id, result)

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.failed = (job_id, error_message)

    def cancel_job(self, job_id):
        self.cancelled = job_id


@pytest.mark.unit
def test_handler_reports_one_json_object():
    client = FakeClient()
    job = {
        "id": 7,
        "payload": {
            "job_kind": JOB_KIND,
            "repository": {"path": "rest://borg@h/r", "borg_version": 2},
            "operation": {"timeout_seconds": 45},
        },
    }
    with patch.object(
        storage_usage,
        "measure",
        return_value={"bytes": 301284, "objects": 4, "source": "borg2_index"},
    ) as measure:
        outcome = execute_storage_usage_job(job, client)
    assert outcome.status == "completed"
    assert measure.call_args.kwargs["borg_version"] == 2
    assert measure.call_args.kwargs["borg_binary"] == "borg2"
    # the server's wait budget bounds the measurement
    assert measure.call_args.kwargs["timeout"] == 45.0
    job_id, result = client.completed
    assert job_id == 7 and result["return_code"] == 0
    assert result["data"] == {"bytes": 301284, "objects": 4, "source": "borg2_index"}
    assert json.loads(result["stdout"]) == result["data"]


@pytest.mark.unit
def test_handler_lets_the_payload_remote_path_win_over_the_environment(monkeypatch):
    """The index step reaches Borg through its Python API, so the remote
    path travels as BORG_REMOTE_PATH; an inherited value must not win."""
    monkeypatch.setenv("BORG_REMOTE_PATH", "/usr/bin/borg-old")
    client = FakeClient()
    job = {
        "id": 8,
        "payload": {
            "job_kind": JOB_KIND,
            "repository": {
                "path": "ssh://u@h/./r",
                "borg_version": 2,
                "remote_path": "/opt/borg2/bin/borg",
            },
        },
    }
    with patch.object(
        storage_usage,
        "measure",
        return_value={"bytes": 1, "objects": 1, "source": "borg2_index"},
    ) as measure:
        execute_storage_usage_job(job, client)
    assert measure.call_args.kwargs["env"]["BORG_REMOTE_PATH"] == "/opt/borg2/bin/borg"


@pytest.mark.unit
def test_handler_defaults_the_timeout_without_a_server_budget():
    from agent.borg_ui_agent.repository_ops import _storage_usage_timeout

    assert _storage_usage_timeout(None) == 600.0
    assert _storage_usage_timeout({"timeout_seconds": "x"}) == 600.0
    assert _storage_usage_timeout({"timeout_seconds": 0}) == 600.0
    assert _storage_usage_timeout({"timeout_seconds": "30"}) == 30.0
    # a deadline must be finite; a malformed payload never reaches .get()
    assert _storage_usage_timeout({"timeout_seconds": "inf"}) == 600.0
    assert _storage_usage_timeout({"timeout_seconds": float("nan")}) == 600.0
    assert _storage_usage_timeout({"timeout_seconds": -5}) == 600.0
    assert _storage_usage_timeout(["timeout_seconds"]) == 600.0
    assert _storage_usage_timeout("60") == 600.0


@pytest.mark.unit
def test_store_tool_failures_are_logged_with_credentials_masked(monkeypatch, caplog):
    """rclone and du failures leave the same trace as a failed index script,
    passwords in URLs masked, so the job's `<tool>_failed` reason has a
    cause in the agent log."""
    failing = subprocess.CompletedProcess(
        ["x"], 3, stdout="", stderr="cannot reach sftp://u:secret@h/r: refused"
    )
    monkeypatch.setattr(storage_usage, "_run", lambda *a, **k: failing)
    monkeypatch.setattr(storage_usage.shutil, "which", lambda name: "/usr/bin/rclone")
    with caplog.at_level("WARNING", logger="agent.borg_ui_agent.storage_usage"):
        assert (
            storage_usage.rclone_storage_used("sftp://u:secret@h/r", timeout=5) is None
        )
        assert storage_usage.du_storage_used("/srv/repo", timeout=5) is None
        assert storage_usage.http_storage_used("http://u:secret@h/r", timeout=5) is None
    assert caplog.text.count("rc=3") == 3
    assert "sftp://u:***@h/r" in caplog.text and "secret" not in caplog.text


@pytest.mark.unit
def test_index_failure_is_logged_with_credentials_masked(monkeypatch, caplog):
    """A failed index script leaves a trace (the store step that follows
    reports only its own reason), without the password Borg prints in
    its location."""
    monkeypatch.setattr(
        storage_usage, "borg2_interpreter", lambda b, env=None: sys.executable
    )
    monkeypatch.setattr(
        storage_usage,
        "INDEX_SUM_SCRIPT",
        "import os, sys; print('cannot open', os.environ['BORG_UI_REPOSITORY_URL'], file=sys.stderr); sys.exit(3)",
    )
    with caplog.at_level("WARNING", logger="agent.borg_ui_agent.storage_usage"):
        assert (
            storage_usage.index_size(
                "https://u:secret@h/store", borg_binary="borg2", env=None, timeout=30
            )
            is None
        )
    assert "rc=3" in caplog.text
    assert "https://u:***@h/store" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.unit
def test_handler_fails_the_job_on_bad_payload_or_error():
    client = FakeClient()
    execute_storage_usage_job({"id": 1, "payload": {"job_kind": JOB_KIND}}, client)
    assert client.failed[0] == 1 and "repository.path" in client.failed[1]
    client = FakeClient()
    job = {
        "id": 2,
        "payload": {
            "job_kind": JOB_KIND,
            "repository": {"path": "/r", "borg_version": 2},
        },
    }
    with patch.object(storage_usage, "measure", side_effect=RuntimeError("boom")):
        outcome = execute_storage_usage_job(job, client)
    assert outcome.status == "failed" and client.failed[0] == 2


@pytest.mark.unit
def test_cancellation_ends_a_running_child_and_the_job():
    """should_cancel is polled while a child runs; the child is ended and the
    job reported cancelled instead of completing later."""
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 1  # first poll runs, the next cancels

    started = time.monotonic()
    with pytest.raises(storage_usage.Cancelled):
        storage_usage._run(["sleep", "30"], timeout=60, should_cancel=should_cancel)
    assert time.monotonic() - started < 10

    # between steps: nothing is started once cancelled
    with pytest.raises(storage_usage.Cancelled):
        storage_usage.measure(
            "/r", borg_version=2, borg_binary="borg2", should_cancel=lambda: True
        )

    client = FakeClient()
    job = {
        "id": 9,
        "payload": {
            "job_kind": JOB_KIND,
            "repository": {"path": "/r", "borg_version": 2},
        },
    }
    with patch.object(storage_usage, "measure", side_effect=storage_usage.Cancelled()):
        outcome = execute_storage_usage_job(job, client, should_cancel=lambda: True)
    assert outcome.status == "canceled"
    assert client.cancelled == 9 and client.completed is None and client.failed is None


def _fake_response(listing, status_code=200):
    body = json.dumps(listing).encode()
    return SimpleNamespace(
        status_code=status_code,
        raise_for_status=lambda: None,
        iter_content=lambda chunk_size: (
            body[i : i + chunk_size] for i in range(0, len(body), chunk_size)
        ),
        close=lambda: None,
    )


@pytest.mark.unit
def test_http_walk_keeps_ipv6_brackets_and_decodes_credentials():
    seen = []

    def fake_get(url, auth=None, headers=None, timeout=None, **kwargs):
        seen.append((url, auth, headers["Accept"], kwargs))
        return _fake_response([{"name": "config", "size": 5, "directory": False}])

    with patch("requests.get", fake_get):
        assert (
            storage_usage._http_walk(
                "http://us%40er:p%40ss@[2001:db8::1]:8000/store", 5
            )
            == 5
        )
    assert seen == [
        (
            "http://[2001:db8::1]:8000/store/",
            ("us@er", "p@ss"),
            "application/vnd.x.borgstore.rest.v1",
            # never follow a redirect (credentials and walk would move to
            # another origin); stream so one listing can be capped
            {"allow_redirects": False, "stream": True},
        )
    ]


@pytest.mark.unit
def test_http_walk_refuses_a_redirect():
    """Same guard as the server walk: a store answering 3xx ends the walk
    instead of carrying the credentials to wherever it points."""

    def fake_get(url, **kwargs):
        return _fake_response([], status_code=302)

    with patch("requests.get", fake_get), pytest.raises(RuntimeError, match="redirect"):
        storage_usage._http_walk("http://u:p@srv/store", 5)


@pytest.mark.unit
def test_http_walk_bounds_depth_and_listing_size():
    """A listing that nests forever (or points back at an ancestor) and a
    listing larger than a directory can be both end the walk; the outer
    process deadline is not the only bound."""
    endless = [{"name": "d", "size": 0, "directory": True}]

    def deep(url, **kwargs):
        return _fake_response(endless)

    with patch("requests.get", deep), pytest.raises(RuntimeError, match="deeper"):
        storage_usage._http_walk("http://srv/store", 5, max_depth=3)

    big = [{"name": f"obj{i}", "size": 1, "directory": False} for i in range(200)]

    def large(url, **kwargs):
        return _fake_response(big)

    with patch("requests.get", large), pytest.raises(RuntimeError, match="larger"):
        storage_usage._http_walk("http://srv/store", 5, max_listing_bytes=1000)
    with patch("requests.get", large):
        assert storage_usage._http_walk("http://srv/store", 5) == 200


class _StoreHandler(BaseHTTPRequestHandler):
    """A borgstore REST server listing: three levels, basic auth required."""

    listings = {
        "/store/": [
            {"name": "config", "size": 582, "directory": False},
            {"name": "packs", "size": 0, "directory": True},
        ],
        "/store/packs/": [{"name": "aa", "size": 0, "directory": True}],
        "/store/packs/aa/": [
            {"name": "obj1", "size": 300000, "directory": False},
            {"name": "obj2", "size": 2708, "directory": False},
        ],
    }
    requests_seen: list = []

    def do_GET(self):
        self.requests_seen.append(
            (self.path, self.headers.get("Authorization"), self.headers.get("Accept"))
        )
        expected = "Basic " + base64.b64encode(b"u:p").decode()
        if self.headers.get("Authorization") != expected:
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(self.listings[self.path]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def store_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StoreHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _StoreHandler.requests_seen = []
    try:
        yield f"127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.unit
def test_http_walk_runs_in_a_child_against_a_real_listing(store_server):
    """The walk is a child process (so it can be ended); this drives the
    real child, with credentials passed through the environment, against
    a local REST listing."""
    seen_cmds = []
    real_run = storage_usage._run

    def spy_run(cmd, **kwargs):
        seen_cmds.append((cmd, kwargs))
        return real_run(cmd, **kwargs)

    with patch.object(storage_usage, "_run", spy_run):
        used = storage_usage.http_storage_used(
            f"http://u:p@{store_server}/store", timeout=30
        )
    assert used == 303290
    cmd, kwargs = seen_cmds[0]
    assert cmd[0] == sys.executable and cmd[1] == "-c"
    assert "u:p@" not in " ".join(cmd)  # credentials never on the command line
    assert kwargs["env"]["BORG_UI_STORE_URL"] == f"http://u:p@{store_server}/store"
    assert kwargs["timeout"] == 30
    assert [path for path, _, _ in _StoreHandler.requests_seen] == [
        "/store/",
        "/store/packs/",
        "/store/packs/aa/",
    ]
    assert all(
        accept == "application/vnd.x.borgstore.rest.v1"
        for _, _, accept in _StoreHandler.requests_seen
    )

    # a failed walk (wrong credentials) is None, not an exception
    assert (
        storage_usage.http_storage_used(f"http://u:x@{store_server}/store", timeout=30)
        is None
    )


def _pid_is_gone(pid, wait=5.0):
    """Gone means no such process, or a zombie awaiting its reaper."""
    import psutil

    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        time.sleep(0.05)
    return False


@pytest.mark.unit
def test_cancelled_http_walk_has_ended_its_child_when_cancel_returns(
    monkeypatch, tmp_path
):
    """Cancellation during a blocked walk returns only after the child is
    gone: the process, not a thread abandoned on its socket."""
    pid_file = tmp_path / "pid"
    monkeypatch.setattr(storage_usage, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(
        storage_usage,
        "_http_walk_command",
        lambda: ["sh", "-c", f"echo $$ > {shlex.quote(str(pid_file))}; exec sleep 30"],
    )
    # the child creates the file before it writes the pid: wait for content
    started = lambda: (
        pid_file.read_text().strip().isdigit() if pid_file.exists() else False
    )  # noqa: E731
    t0 = time.monotonic()
    with pytest.raises(storage_usage.Cancelled):
        storage_usage.http_storage_used(
            "http://srv/store", timeout=60, should_cancel=started
        )
    assert time.monotonic() - t0 < 10
    assert _pid_is_gone(int(pid_file.read_text()), wait=0.5)


@pytest.mark.unit
def test_ending_a_child_ends_its_descendants_too(monkeypatch, tmp_path):
    """Borg spawns ssh or rclone; rclone spawns nothing, but the group kill
    must reach every descendant. A child that ignores SIGTERM proves the
    SIGKILL fallback; its grandchild proves the group."""
    pid_file = tmp_path / "grandchild"
    monkeypatch.setattr(storage_usage, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(storage_usage, "TERMINATE_GRACE_SECONDS", 0.3)
    cmd = [
        "sh",
        "-c",
        f"trap '' TERM; sleep 30 & echo $! > {shlex.quote(str(pid_file))}; sleep 30; wait",
    ]
    # end the group only once the grandchild's pid is on disk: a deadline
    # could fire before the shell writes it, leaving nothing to check
    t0 = time.monotonic()
    with pytest.raises(storage_usage.Cancelled):
        storage_usage._run(
            cmd,
            timeout=30,
            should_cancel=lambda: (
                pid_file.exists() and pid_file.read_text().strip().isdigit()
            ),
        )
    assert time.monotonic() - t0 < 10
    assert _pid_is_gone(int(pid_file.read_text()))


@pytest.mark.unit
def test_measure_spreads_one_budget_over_its_steps(monkeypatch):
    seen = {}

    def slow_index(url, *, borg_binary, env, timeout, should_cancel=None):
        seen["index_timeout"] = timeout
        time.sleep(0.15)
        return None

    def fallback(url, *, timeout, env=None, should_cancel=None):
        seen["fallback_timeout"] = timeout
        return (1, "du")

    monkeypatch.setattr(storage_usage, "index_size", slow_index)
    monkeypatch.setattr(storage_usage, "storage_used", fallback)
    result = storage_usage.measure("/r", borg_version=2, borg_binary="borg2", timeout=1)
    assert result["bytes"] == 1
    assert seen["index_timeout"] <= 1
    assert 0 < seen["fallback_timeout"] <= 0.9

    # the budget spent on the index step leaves nothing for the fallback
    seen.clear()
    result = storage_usage.measure(
        "/r", borg_version=2, borg_binary="borg2", timeout=0.1
    )
    assert result["reason"] == "timeout" and "fallback_timeout" not in seen


@pytest.mark.unit
def test_rclone_fallback_runs_in_the_job_environment(monkeypatch):
    """The server sends RCLONE_CONFIG (and other rclone variables) with the
    job; the agent process environment may carry a different one."""
    monkeypatch.setenv("RCLONE_CONFIG", "/etc/rclone/agent.conf")
    monkeypatch.setattr(storage_usage, "index_size", lambda *a, **k: None)
    monkeypatch.setattr(storage_usage.shutil, "which", lambda name: "/usr/bin/rclone")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"bytes": 77}), stderr=""
        )

    monkeypatch.setattr(storage_usage, "_run", fake_run)
    job_env = {"RCLONE_CONFIG": "/job/rclone.conf", "BORG_RSH": "ssh -i /k"}
    result = storage_usage.measure(
        "rclone:managed:bucket/repo", borg_version=2, borg_binary="borg2", env=job_env
    )
    assert result == {
        "bytes": 77,
        "objects": None,
        "source": "storage_used",
        "tool": "rclone",
    }
    cmd, kwargs = calls[-1]
    assert cmd[:3] == ["/usr/bin/rclone", "size", "--json"]
    assert kwargs["env"] is job_env
    assert kwargs["env"]["RCLONE_CONFIG"] == "/job/rclone.conf"


@pytest.mark.unit
def test_cancel_ends_a_descendant_that_outlives_its_parent(monkeypatch, tmp_path):
    """The inverse of the test above (review 0043): the child exits on
    SIGTERM, the descendant ignores it. The child's exit proves nothing
    about the group, so the sweep must still reach the descendant."""
    pid_file = tmp_path / "descendant.pid"
    descendant = (
        "import os, signal, time, pathlib;"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()));"
        "time.sleep(30)"
    )
    parent = (
        "import subprocess, sys, time;"
        f"subprocess.Popen([sys.executable, '-c', {descendant!r}]);"
        "time.sleep(30)"
    )
    monkeypatch.setattr(storage_usage, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(storage_usage, "TERMINATE_GRACE_SECONDS", 0.3)
    try:
        t0 = time.monotonic()
        with pytest.raises(storage_usage.Cancelled):
            storage_usage._run(
                [sys.executable, "-c", parent],
                timeout=30,
                should_cancel=lambda: (
                    pid_file.exists() and pid_file.read_text().strip().isdigit()
                ),
            )
        assert time.monotonic() - t0 < 10
        assert _pid_is_gone(int(pid_file.read_text()), wait=0.5)
    finally:
        if pid_file.exists() and pid_file.read_text().strip().isdigit():
            try:
                os.kill(int(pid_file.read_text()), 9)
            except ProcessLookupError:
                pass


@pytest.mark.unit
def test_proc_stat_parser_separates_live_members_from_zombies():
    live = storage_usage._stat_is_live
    # pid (comm) state ppid pgrp session ...
    assert live("42 (rclone) S 1 8 8 0 -1 4194560 0", 8)
    assert live("42 (a (weird) name) R 1 8 8 0 -1", 8)
    assert not live("42 (rclone) Z 1 8 8 0 -1", 8)
    assert not live("42 (rclone) X 1 8 8 0 -1", 8)
    assert not live("42 (rclone) S 1 9 9 0 -1", 8)  # another group
    assert not live("garbage", 8)


@pytest.mark.unit
def test_group_cleanup_is_bounded_when_only_zombies_remain(monkeypatch):
    """After SIGKILL nothing in the group can keep working; a zombie that
    its adopter never reaps (review 0048, container without init) must not
    block the cancellation. Simulated: the group keeps looking alive."""
    monkeypatch.setattr(storage_usage, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(storage_usage, "TERMINATE_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(storage_usage, "_group_live", lambda pgid: True)
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        storage_usage._run(["sleep", "30"], timeout=0.1)
    assert time.monotonic() - t0 < 2


@pytest.mark.unit
def test_cleanup_returns_when_the_child_never_becomes_waitable(monkeypatch):
    """CR follow-up: SIGKILL is not delivered to a child in uninterruptible
    sleep, so a wait without timeout would block the cancellation forever.
    Fault injection at the Popen boundary: timed waits expire, an untimed
    wait would sleep for a long time."""

    class Unwaitable:
        pid = 12345

        def poll(self):
            return None

        def wait(self, timeout=None):
            if timeout is None:
                time.sleep(10)
                return 0
            time.sleep(timeout)
            raise subprocess.TimeoutExpired("unwaitable", timeout)

    monkeypatch.setattr(storage_usage, "TERMINATE_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(storage_usage, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(storage_usage, "_signal_group", lambda process, sig: None)
    monkeypatch.setattr(storage_usage, "_group_live", lambda pgid: False)
    t0 = time.monotonic()
    storage_usage._end_group(Unwaitable())
    assert time.monotonic() - t0 < 1


@pytest.mark.unit
@pytest.mark.parametrize("port", ["99999", "invalid"])
@pytest.mark.parametrize("scheme", ["http", "sftp"])
def test_invalid_port_is_unknown_and_spawns_nothing(monkeypatch, port, scheme):
    calls = []
    monkeypatch.setattr(storage_usage, "_run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(storage_usage.shutil, "which", lambda name: "/usr/bin/rclone")
    url = f"{scheme}://u:secret@localhost:{port}/store"
    assert not storage_usage.valid_target(url)
    assert storage_usage.storage_used(url, timeout=5) == (
        None,
        storage_usage.INVALID_URL,
    )
    assert storage_usage.rclone_remote_for(url) is None
    assert calls == []
    monkeypatch.setattr(storage_usage, "index_size", lambda *a, **k: None)
    result = storage_usage.measure(url, borg_version=2, borg_binary="borg2")
    assert result["reason"] == "invalid_url" and result["bytes"] is None


@pytest.mark.unit
def test_interpreter_is_the_venv_python_behind_the_wrapper(tmp_path):
    """The agent image puts a bash wrapper `borg2` in /usr/local/bin next to
    the system python (seen live: the index step failed silently and the
    size fell through to a fallback that does not exist for rest://).
    BORG2_BINARY in the job environment points at the venv binary."""
    venv = tmp_path / "opt" / "venv"
    (venv / "bin").mkdir(parents=True)
    for name in ("borg", "python"):
        (venv / "bin" / name).write_text("#!/bin/sh\n")
        (venv / "bin" / name).chmod(0o755)
    current = tmp_path / "opt" / "current-borg"
    current.symlink_to(venv / "bin" / "borg")
    wrapper_dir = tmp_path / "usr" / "local" / "bin"
    wrapper_dir.mkdir(parents=True)
    for name in ("borg2", "python"):
        (wrapper_dir / name).write_text("#!/bin/sh\n")
        (wrapper_dir / name).chmod(0o755)

    # no pyvenv.cfg anywhere: neither directory is a venv
    assert storage_usage.borg2_interpreter(str(wrapper_dir / "borg2"), {}) is None
    (venv / "pyvenv.cfg").write_text("home = /usr/local/bin\n")
    # the wrapper's neighbour is the system python and stays rejected
    assert storage_usage.borg2_interpreter(str(wrapper_dir / "borg2"), {}) is None
    # BORG2_BINARY (a symlink into the venv) wins; the python path is the
    # venv's own, not the realpath of its symlink
    assert storage_usage.borg2_interpreter(
        str(wrapper_dir / "borg2"), {"BORG2_BINARY": str(current)}
    ) == str(venv / "bin" / "python")


@pytest.mark.unit
def test_set_repository_size_writes_the_four_columns_together():
    """Every size writer goes through one helper, so the formatted string,
    the number, the source and the time never disagree."""
    from datetime import datetime
    from types import SimpleNamespace

    from app.services.storage_usage import set_repository_size

    repo = SimpleNamespace(
        total_size=None,
        total_size_bytes=None,
        total_size_source=None,
        total_size_measured_at=None,
    )
    before = datetime.utcnow()
    set_repository_size(repo, 2048, "borg2_index")
    assert repo.total_size == "2.00 KB"
    assert repo.total_size_bytes == 2048
    assert repo.total_size_source == "borg2_index"
    assert repo.total_size_measured_at >= before

    at = datetime(2026, 1, 1, 12, 0, 0)
    set_repository_size(repo, 0, "compact_stats", measured_at=at)
    assert repo.total_size == "0.00 B"
    assert repo.total_size_bytes == 0
    assert repo.total_size_source == "compact_stats"
    assert repo.total_size_measured_at == at


@pytest.mark.unit
def test_stored_size_bytes_is_the_one_rule_every_reader_applies():
    from types import SimpleNamespace

    from app.services.storage_usage import bytes_from_formatted, stored_size_bytes

    assert (
        stored_size_bytes(
            SimpleNamespace(total_size="2.19 GB", total_size_bytes=2_350_000_000)
        )
        == 2_350_000_000
    )
    assert (
        stored_size_bytes(SimpleNamespace(total_size="1.00 KB", total_size_bytes=None))
        == 1024
    )
    assert (
        stored_size_bytes(SimpleNamespace(total_size="Unknown", total_size_bytes=None))
        is None
    )
    assert (
        stored_size_bytes(SimpleNamespace(total_size=None, total_size_bytes=None))
        is None
    )
    assert bytes_from_formatted("2.40 TB") == 2_638_827_906_662
    # the shapes older releases wrote
    assert bytes_from_formatted("1.5GB") == 1_610_612_736
    assert bytes_from_formatted("1 GiB") == 1_073_741_824
    assert bytes_from_formatted("4096") == 4096
    assert bytes_from_formatted("512 b") == 512
    assert bytes_from_formatted("NaN KB") is None
    assert bytes_from_formatted("-1.00 KB") is None
    assert bytes_from_formatted("1.00 XB") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "text_value",
    [
        "2.40 TB",
        "490.23 KB",
        "0.00 B",
        "1.5GB",
        "1 GiB",
        "4096",
        "512 b",
        "Unknown",
        "N/A",
        "",
        None,
        "-1 KB",
        "1.00 XB",
    ],
)
def test_the_migration_backfill_parses_like_the_service(text_value):
    """The backfill carries its own copy of the parser (a migration imports
    no app code); the two must agree, or `measured_at is None` stops
    meaning what the docstrings say."""
    import importlib.util
    from pathlib import Path

    from app.services import storage_usage
    from app.services.storage_usage import bytes_from_formatted

    versions = Path(__file__).resolve().parents[2] / "app/database/alembic/versions"
    path = next(versions.glob("a9b8c7d6e5f4_*.py"))
    spec = importlib.util.spec_from_file_location("size_bytes_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.bytes_from_formatted(text_value) == bytes_from_formatted(text_value)
    # a widened service pattern must be widened in the copy as well; the
    # table above cannot know a shape added later
    assert module._SIZE_TEXT.pattern == storage_usage._SIZE_TEXT.pattern
    assert module._SIZE_TEXT.flags == storage_usage._SIZE_TEXT.flags
    assert module._SIZE_UNITS == storage_usage._SIZE_UNITS
