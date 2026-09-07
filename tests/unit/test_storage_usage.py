import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import storage_usage
from app.services.storage_usage import (
    SOURCE_BORG1_CACHE_STATS,
    SOURCE_BORG2_INDEX,
    SOURCE_STORAGE_USED,
    SizeResult,
    borg2_index_size,
    borg2_interpreter,
    measure_repository_size,
    rclone_remote_for,
    safe_url,
    store_target,
)


class FakeProcess:
    def __init__(
        self, returncode=0, stdout=b"", stderr=b"", hang=False, kill_raises=None
    ):
        self.returncode = returncode
        self._out = (stdout, stderr)
        self._hang = hang
        self._kill_raises = kill_raises
        self.killed = False
        self.waited = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(60)
        return self._out

    def kill(self):
        self.killed = True
        if self._kill_raises:
            raise self._kill_raises

    async def wait(self):
        self.waited = True
        return self.returncode


def _listing(payload, *, chunks=None):
    """A streamed `requests` response: the JSON body in one chunk, or the
    given chunks; records how many were read and whether it was closed."""
    pieces = [json.dumps(payload).encode()] if chunks is None else chunks
    state = {"read": 0, "closed": False}

    def iter_content(chunk_size=None):
        for piece in pieces:
            state["read"] += 1
            yield piece

    return SimpleNamespace(
        raise_for_status=lambda: None,
        iter_content=iter_content,
        close=lambda: state.__setitem__("closed", True),
        state=state,
    )


def _repo(borg_version=2, path="rest://borg@host/repos/repo", passphrase="x"):
    return SimpleNamespace(
        borg_version=borg_version,
        path=path,
        passphrase=passphrase,
        bypass_lock=False,
        ssh_key_id=None,
        remote_path=None,
    )


@pytest.mark.unit
def test_borg2_interpreter_is_the_python_next_to_a_venv_borg(tmp_path):
    bindir = tmp_path / "venv" / "bin"
    bindir.mkdir(parents=True)
    borg = bindir / "borg"
    borg.write_text("#!/bin/sh\n")
    borg.chmod(0o755)
    link = tmp_path / "borg2"
    link.symlink_to(borg)
    assert borg2_interpreter(str(link), {}) is None  # standalone: no python next to it
    python = bindir / "python"
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    # a python without pyvenv.cfg is a system interpreter: borg not importable
    assert borg2_interpreter(str(link), {}) is None
    (tmp_path / "venv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    assert borg2_interpreter(str(link), {}) == str(python)

    # the command on PATH may be a wrapper next to the system python (the
    # agent image); BORG2_BINARY in the environment points at the real one
    wrapper_dir = tmp_path / "usr" / "local" / "bin"
    wrapper_dir.mkdir(parents=True)
    for name in ("borg2", "python"):
        (wrapper_dir / name).write_text("#!/bin/sh\n")
        (wrapper_dir / name).chmod(0o755)
    assert borg2_interpreter(str(wrapper_dir / "borg2"), {}) is None
    assert borg2_interpreter(
        str(wrapper_dir / "borg2"), {"BORG2_BINARY": str(link)}
    ) == str(python)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg2_index_size_parses_the_script_output(monkeypatch):
    monkeypatch.setattr(
        storage_usage, "borg2_interpreter", lambda b, env=None: "/venv/bin/python"
    )
    spawn = AsyncMock(
        return_value=FakeProcess(
            stdout=json.dumps({"objects": 4, "bytes": 301284}).encode()
        )
    )
    monkeypatch.setattr(storage_usage.asyncio, "create_subprocess_exec", spawn)
    assert await borg2_index_size(
        "sftp://u:secret@h/r", borg2_binary="borg2", env={"A": "1"}
    ) == (301284, 4)
    args = spawn.call_args.args
    assert args[0] == "/venv/bin/python" and args[1] == "-c" and len(args) == 3
    # the URL (it may carry credentials) travels in the environment, not argv
    assert "secret" not in " ".join(args)
    assert (
        spawn.call_args.kwargs["env"]["BORG_UI_REPOSITORY_URL"] == "sftp://u:secret@h/r"
    )
    assert spawn.call_args.kwargs["env"]["A"] == "1"
    assert "lock=False" in args[2]
    # streamed in pages, never one list of every object
    assert "marker" in args[2] and "[size for" not in args[2]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_borg2_index_size_is_none_without_interpreter_or_on_failure(monkeypatch):
    monkeypatch.setattr(storage_usage, "borg2_interpreter", lambda b, env=None: None)
    assert await borg2_index_size("/r", borg2_binary="borg2") is None
    monkeypatch.setattr(
        storage_usage, "borg2_interpreter", lambda b, env=None: "/venv/bin/python"
    )
    monkeypatch.setattr(
        storage_usage.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProcess(returncode=2, stderr=b"LockTimeout")),
    )
    assert await borg2_index_size("/r", borg2_binary="borg2") is None


@pytest.mark.unit
def test_rclone_remote_for_sftp_and_rclone_urls():
    assert (
        rclone_remote_for("sftp://u1@box.example:23/./backups/repo")
        == ":sftp,host=box.example,user=u1,port=23:backups/repo"
    )
    assert (
        rclone_remote_for("sftp://u@h/abs/repo", key_file="/tmp/k")
        == ":sftp,host=h,user=u,key_file=/tmp/k:/abs/repo"
    )
    # an explicit port 0 is a port, not "no port": rclone must not fall
    # back to 22
    assert rclone_remote_for("sftp://u@h:0/./r") == ":sftp,host=h,user=u,port=0:r"
    assert rclone_remote_for("rclone:remote:bucket/repo") == "remote:bucket/repo"
    assert rclone_remote_for("/local/path") is None
    assert rclone_remote_for("s3:profile@bucket/path") is None
    # upper-case scheme, remote name kept as written (rclone remotes are
    # case-sensitive)
    assert rclone_remote_for("RCLONE:Remote:bucket/repo") == "Remote:bucket/repo"
    assert store_target("RCLONE:Remote:bucket/repo") == (
        "rclone",
        "RCLONE:Remote:bucket/repo",
    )


@pytest.mark.unit
def test_store_target_by_scheme():
    assert store_target("http://u:p@srv:8000/store") == (
        "http",
        "http://u:p@srv:8000/store",
    )
    assert store_target("sftp://u@h:23/./r") == ("rclone", "sftp://u@h:23/./r")
    assert store_target("rclone:remote:r") == ("rclone", "rclone:remote:r")
    # borgstore's rest://user@host/path runs the REST server over ssh behind
    # a forced command, so no shell command (du) reaches the files.
    assert store_target("rest://borg@host/repos/repo") == ("", None)
    assert store_target("rest://borg@host:2222/repos/repo") == ("", None)
    assert store_target("rest:///srv/store") == ("du", "/srv/store")
    assert store_target("ssh://u@h/r") == ("du", "ssh://u@h/r")
    assert store_target("/backups/repo") == ("du", "/backups/repo")
    assert store_target("s3:profile|k:s@endpoint/bucket") == ("", None)
    # schemes are case-insensitive, the target keeps the URL as written
    assert store_target("HTTP://srv/store") == ("http", "HTTP://srv/store")
    assert store_target("SFTP://u@h/./r") == ("rclone", "SFTP://u@h/./r")
    assert store_target("REST://borg@host/repos/repo") == ("", None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_storage_used_walks_the_rest_listing(monkeypatch):
    listings = {
        "http://u:p@srv/store/": [
            {"name": "config", "size": 582, "directory": False},
            {"name": "packs", "size": 0, "directory": True},
        ],
        "http://u:p@srv/store/packs/": [
            {"name": "aa", "size": 0, "directory": True},
        ],
        "http://u:p@srv/store/packs/aa/": [
            {"name": "obj1", "size": 300000, "directory": False},
            {"name": "obj2", "size": 2708, "directory": False},
        ],
    }
    seen = []

    def fake_get(
        url, auth=None, headers=None, timeout=None, allow_redirects=True, **kw
    ):
        assert allow_redirects is False and kw.get("stream") is True
        seen.append((url, auth, headers["Accept"]))
        key = url.replace("http://srv/", "http://u:p@srv/")
        return _listing(listings[key])

    with patch("requests.get", fake_get):
        assert await storage_usage.http_storage_used("http://u:p@srv/store") == 303290
    assert seen[0][1] == ("u", "p")
    assert seen[0][2] == "application/vnd.x.borgstore.rest.v1"
    assert seen[0][0] == "http://srv/store/"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_measure_borg1_reads_cache_stats_and_last_modified():
    repo = _repo(borg_version=1, path="/backups/repo")
    payload = {
        "cache": {"stats": {"unique_csize": 2048}},
        "repository": {"last_modified": "2026-09-05T12:29:48.000000"},
    }
    execute = AsyncMock(return_value={"success": True, "stdout": json.dumps(payload)})
    with patch("app.core.borg.borg._execute_command", execute):
        result = await measure_repository_size(
            repo, env={"A": "1"}, use_bypass_lock=True
        )
    assert result == SizeResult(
        bytes=2048,
        source=SOURCE_BORG1_CACHE_STATS,
        last_modified=datetime(2026, 9, 5, 12, 29, 48),
    )
    cmd = execute.call_args.args[0]
    assert cmd[:3] == ["borg", "info", "--json"] and "--bypass-lock" in cmd
    assert execute.call_args.kwargs["env"]["TZ"] == "UTC"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stats",
    [None, {}, {"unique_csize": None}, {"unique_csize": 0}, {"unique_csize": -1}]
    + [{"unique_csize": "2048"}, {"unique_csize": True}],
)
async def test_measure_borg1_without_a_usable_size_reports_no_source(stats):
    """`source` describes `bytes`; a size that is not a positive number
    yields neither, and a null `cache.stats` is not an error."""
    repo = _repo(borg_version=1, path="/backups/repo")
    payload = {
        "cache": {"stats": stats},
        "repository": {"last_modified": "2026-09-05T12:29:48.000000"},
    }
    execute = AsyncMock(return_value={"success": True, "stdout": json.dumps(payload)})
    with patch("app.core.borg.borg._execute_command", execute):
        result = await measure_repository_size(repo, env={})
    assert result == SizeResult(
        bytes=None, source=None, last_modified=datetime(2026, 9, 5, 12, 29, 48)
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_measure_borg2_prefers_the_index_and_keeps_last_modified(monkeypatch):
    repo = _repo()
    rinfo = AsyncMock(
        return_value={
            "success": True,
            "stdout": json.dumps(
                {"repository": {"last_modified": "2026-09-06T08:57:17.922941+00:00"}}
            ),
        }
    )
    index = AsyncMock(return_value=(301284, 4))
    used = AsyncMock(return_value=999)
    monkeypatch.setattr(storage_usage, "borg2_index_size", index)
    monkeypatch.setattr(storage_usage, "storage_used", used)
    with (
        patch("app.core.borg2.borg2.rinfo", rinfo),
        patch("app.core.borg2._get_borg2_binary", return_value="/opt/venv/bin/borg"),
    ):
        result = await measure_repository_size(repo, env={"BORG_RSH": "ssh"})
    assert result == SizeResult(
        bytes=301284,
        objects=4,
        source=SOURCE_BORG2_INDEX,
        last_modified=datetime(2026, 9, 6, 8, 57, 17, 922941),
    )
    assert index.call_args.kwargs["borg2_binary"] == "/opt/venv/bin/borg"
    assert index.call_args.kwargs["env"]["BORG_PASSPHRASE"] == "x"
    used.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_measure_borg2_falls_back_to_the_store_and_never_reports_zero(
    monkeypatch,
):
    repo = _repo()
    monkeypatch.setattr(storage_usage, "borg2_index_size", AsyncMock(return_value=None))
    used = AsyncMock(return_value=424242)
    monkeypatch.setattr(storage_usage, "storage_used", used)
    with (
        patch("app.core.borg2.borg2.rinfo", AsyncMock(return_value={"success": False})),
        patch("app.core.borg2._get_borg2_binary", return_value="borg2"),
    ):
        result = await measure_repository_size(repo, temp_key_file="/tmp/k")
    assert result == SizeResult(bytes=424242, source=SOURCE_STORAGE_USED)
    assert used.call_args.kwargs["key_file"] == "/tmp/k"
    assert used.call_args.kwargs["env"] is None

    monkeypatch.setattr(storage_usage, "storage_used", AsyncMock(return_value=None))
    with (
        patch("app.core.borg2.borg2.rinfo", AsyncMock(return_value={"success": False})),
        patch("app.core.borg2._get_borg2_binary", return_value="borg2"),
    ):
        assert await measure_repository_size(repo) == SizeResult()

    monkeypatch.setattr(
        storage_usage, "borg2_index_size", AsyncMock(return_value=(0, 0))
    )
    with (
        patch("app.core.borg2.borg2.rinfo", AsyncMock(return_value={"success": False})),
        patch("app.core.borg2._get_borg2_binary", return_value="borg2"),
    ):
        empty = await measure_repository_size(repo)
    assert empty.bytes is None and empty.source is None and empty.objects == 0


@pytest.mark.unit
def test_safe_url_redacts_credentials():
    assert safe_url("http://u:s3cr%40t@srv:8000/store") == "http://u:***@srv:8000/store"
    assert safe_url("sftp://u:s3cr%40t@box:23/./r") == "sftp://u:***@box:23/./r"
    assert safe_url("/backups/repo") == "/backups/repo"
    assert safe_url("sftp://box:23/./r") == "sftp://box:23/./r"
    # a userinfo without a password is the whole credential (Basic auth
    # sends it as the user name), so nothing of it survives
    assert safe_url("http://token@srv/store") == "http://***@srv/store"
    assert safe_url("sftp://u@box:23/./r") == "sftp://***@box:23/./r"
    assert "token" not in safe_url("HTTPS://token@srv/store")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_storage_used_decodes_credentials_and_tolerates_no_password():
    seen = []

    def fake_get(
        url, auth=None, headers=None, timeout=None, allow_redirects=True, **kw
    ):
        assert allow_redirects is False
        seen.append(auth)
        return _listing([])

    with patch("requests.get", fake_get):
        await storage_usage.http_storage_used("http://us%40er:p%40ss@srv/store")
        await storage_usage.http_storage_used("http://token@srv/store")
    assert seen == [("us@er", "p@ss"), ("token", "")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timed_out_children_are_killed(monkeypatch):
    """wait_for only cancels the wait; a timed-out borg or rclone must not
    keep running."""
    monkeypatch.setattr(
        storage_usage, "borg2_interpreter", lambda b, env=None: "/venv/bin/python"
    )
    hung = FakeProcess(hang=True)
    monkeypatch.setattr(
        storage_usage.asyncio, "create_subprocess_exec", AsyncMock(return_value=hung)
    )
    assert await borg2_index_size("/r", borg2_binary="borg2", timeout=0.01) is None
    assert hung.killed and hung.waited

    hung = FakeProcess(hang=True)
    monkeypatch.setattr(storage_usage.shutil, "which", lambda name: "/usr/bin/rclone")
    monkeypatch.setattr(
        storage_usage.asyncio, "create_subprocess_exec", AsyncMock(return_value=hung)
    )
    assert (
        await storage_usage.rclone_storage_used("sftp://u@h/./r", timeout=0.01) is None
    )
    assert hung.killed and hung.waited


@pytest.mark.unit
def test_rclone_remote_decodes_and_quotes_url_components():
    # percent-encoded user and path are decoded; values with rclone syntax
    # characters are quoted, quotes doubled
    assert (
        rclone_remote_for("sftp://us%40er@h/./dir%20one/repo")
        == ":sftp,host=h,user=us@er:dir one/repo"
    )
    assert (
        rclone_remote_for("sftp://a%2Cb@h/r", key_file='/k/my"key')
        == ':sftp,host=h,user="a,b",key_file="/k/my""key":/r'
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancelled_reads_kill_the_child(monkeypatch):
    monkeypatch.setattr(
        storage_usage, "borg2_interpreter", lambda b, env=None: "/venv/bin/python"
    )
    hung = FakeProcess(hang=True)
    monkeypatch.setattr(
        storage_usage.asyncio, "create_subprocess_exec", AsyncMock(return_value=hung)
    )
    task = asyncio.ensure_future(
        borg2_index_size("/r", borg2_binary="borg2", timeout=60)
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hung.killed and hung.waited


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancellation_survives_a_child_that_already_exited(monkeypatch):
    """`Process.kill()` raises ProcessLookupError once the child is gone;
    that must not turn the cancellation into an OSError that the index read
    reports as "failed to start" and then falls through to the store-level
    fallback on a task that was meant to stop."""
    monkeypatch.setattr(
        storage_usage, "borg2_interpreter", lambda b, env=None: "/venv/bin/python"
    )
    gone = FakeProcess(hang=True, kill_raises=ProcessLookupError())
    monkeypatch.setattr(
        storage_usage.asyncio, "create_subprocess_exec", AsyncMock(return_value=gone)
    )
    task = asyncio.ensure_future(
        borg2_index_size("/r", borg2_binary="borg2", timeout=60)
    )
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gone.killed and gone.waited


@pytest.mark.unit
def test_index_sum_script_compiles():
    """The child is always mocked in these tests; at least the script must
    parse, and it must read the URL from the documented variable."""
    compile(storage_usage.INDEX_SUM_SCRIPT, "<index>", "exec")
    assert storage_usage.REPOSITORY_URL_ENV in storage_usage.INDEX_SUM_SCRIPT


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("value,expected", [(4096, 4096), (0, None), (-1, None)])
async def test_du_storage_used_runs_du_and_never_reports_zero(value, expected):
    du = AsyncMock(return_value=value)
    with patch("app.utils.fs.calculate_path_size_bytes", du):
        assert (
            await storage_usage.du_storage_used(
                "ssh://u@h/r", key_file="/k", timeout=30
            )
            == expected
        )
    du.assert_awaited_once_with(["ssh://u@h/r"], timeout=30, key_file="/k")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_walk_stops_on_a_looping_listing(monkeypatch):
    """A listing whose directory entry points back at an ancestor must end
    in `unknown`, not in a RecursionError, and within a bounded number of
    requests."""
    seen = []

    def fake_get(
        url, auth=None, headers=None, timeout=None, allow_redirects=True, **kw
    ):
        seen.append(url)
        return _listing([{"name": "data", "directory": True}])

    with patch("requests.get", fake_get):
        assert await storage_usage.http_storage_used("http://srv/store") is None
    assert len(seen) == storage_usage.HTTP_WALK_MAX_DEPTH + 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_walk_stops_when_its_budget_is_spent(monkeypatch):
    # the deadline is taken at the first call, the first directory passes,
    # the second is past the budget; everything after that stays "late"
    # (asyncio reads the same clock, so it must never run dry)
    clock = {"now": 0.0}
    monkeypatch.setattr(storage_usage.time, "monotonic", lambda: clock["now"])
    seen = []

    def fake_get(
        url, auth=None, headers=None, timeout=None, allow_redirects=True, **kw
    ):
        seen.append((url, timeout))
        clock["now"] += 10  # a slow first listing spends the whole budget
        return _listing([{"name": "sub", "directory": True}])

    with patch("requests.get", fake_get):
        assert (
            await storage_usage.http_storage_used("http://srv/store", budget=5) is None
        )
    # one request, its socket timeout capped at the remaining budget
    assert seen == [("http://srv/store/", 5)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_walk_aborts_a_response_that_keeps_sending(monkeypatch):
    """requests' timeout is per socket operation: a server that keeps
    sending bytes never trips it. The walk checks the clock between chunks
    and closes the response once the budget is spent."""
    clock = {"now": 0.0}
    monkeypatch.setattr(storage_usage.time, "monotonic", lambda: clock["now"])

    def endless():
        while True:
            clock["now"] += 2
            yield b'[{"name": "x", "size": 1, "directory": false},'

    response = _listing(None, chunks=endless())

    with patch("requests.get", lambda *a, **kw: response):
        assert (
            await storage_usage.http_storage_used("http://srv/store", budget=5) is None
        )
    assert response.state["closed"] and response.state["read"] <= 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_walk_refuses_an_oversized_listing(monkeypatch):
    monkeypatch.setattr(storage_usage, "HTTP_LISTING_MAX_BYTES", 10)
    response = _listing([{"name": "x", "size": 1, "directory": False}])
    with patch("requests.get", lambda *a, **kw: response):
        assert await storage_usage.http_storage_used("http://srv/store") is None
    assert response.state["closed"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_walk_keeps_ipv6_brackets():
    seen = []

    def fake_get(
        url, auth=None, headers=None, timeout=None, allow_redirects=True, **kw
    ):
        assert allow_redirects is False
        seen.append(url)
        return _listing([{"name": "config", "size": 5, "directory": False}])

    with patch("requests.get", fake_get):
        assert (
            await storage_usage.http_storage_used("http://u:p@[2001:db8::1]:8000/store")
            == 5
        )
    assert seen == ["http://[2001:db8::1]:8000/store/"]
    # same for an explicit port 0: kept, no default-port fallback
    with patch("requests.get", fake_get):
        assert await storage_usage.http_storage_used("http://h:0/store") == 5
    assert seen[-1] == "http://h:0/store/"
    assert (
        safe_url("http://u:p@[2001:db8::1]:8000/store")
        == "http://u:***@[2001:db8::1]:8000/store"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rclone_fallback_runs_in_the_prepared_environment(monkeypatch):
    """The managed rclone.conf is only known through RCLONE_CONFIG on the
    prepared Borg environment; the fallback must not inherit the server
    process environment instead (F05)."""
    repo = _repo(path="rclone:managed:bucket/repo")
    env = {
        "RCLONE_CONFIG": "/managed/rclone.conf",
        "BORG_RSH": "ssh -i /k",
        "PATH": "/usr/bin",
    }
    monkeypatch.setattr(storage_usage, "borg2_index_size", AsyncMock(return_value=None))
    monkeypatch.setattr(storage_usage.shutil, "which", lambda name: "/usr/bin/rclone")
    spawn = AsyncMock(
        return_value=FakeProcess(
            stdout=json.dumps({"bytes": 4096, "count": 3}).encode()
        )
    )
    monkeypatch.setattr(storage_usage.asyncio, "create_subprocess_exec", spawn)
    with (
        patch("app.core.borg2.borg2.rinfo", AsyncMock(return_value={"success": False})),
        patch("app.core.borg2._get_borg2_binary", return_value="borg2"),
    ):
        result = await measure_repository_size(repo, env=env)
    assert result == SizeResult(bytes=4096, source=SOURCE_STORAGE_USED)
    assert spawn.call_args.args[:3] == ("/usr/bin/rclone", "size", "--json")
    assert spawn.call_args.args[3] == "managed:bucket/repo"
    # the whole prepared environment, not a subset and not the inherited one
    assert spawn.call_args.kwargs["env"] == env


@pytest.mark.unit
@pytest.mark.asyncio
async def test_storage_used_passes_the_environment_to_rclone_only(monkeypatch):
    rclone = AsyncMock(return_value=1)
    du = AsyncMock(return_value=2)
    http = AsyncMock(return_value=3)
    monkeypatch.setattr(storage_usage, "rclone_storage_used", rclone)
    monkeypatch.setattr(storage_usage, "du_storage_used", du)
    monkeypatch.setattr(storage_usage, "http_storage_used", http)
    env = {"RCLONE_CONFIG": "/managed/rclone.conf"}
    assert (
        await storage_usage.storage_used("sftp://u@h/./r", env=env, key_file="/k") == 1
    )
    assert rclone.call_args.kwargs == {"key_file": "/k", "env": env, "timeout": 600}
    assert await storage_usage.storage_used("/backups/repo", env=env) == 2
    assert "env" not in du.call_args.kwargs
    assert await storage_usage.storage_used("http://srv/store", env=env) == 3
    assert "env" not in http.call_args.kwargs


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("port", ["99999", "invalid"])
@pytest.mark.parametrize("scheme", ["http", "sftp", "rclone:x"])
async def test_invalid_port_is_unknown_not_an_exception(monkeypatch, port, scheme):
    """`urlsplit(...).port` raises for a port outside 0..65535 or a
    non-numeric one; that used to escape from the fallback (and again from
    safe_url while logging it). Such a URL is unmeasurable, and nothing is
    spawned against another endpoint."""
    spawn = AsyncMock()
    monkeypatch.setattr(storage_usage.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(storage_usage.shutil, "which", lambda name: "/usr/bin/rclone")
    if scheme == "rclone:x":
        url = "rclone:x:bucket/repo"  # no port to be wrong about
        assert storage_usage.valid_target(url)
        return
    url = f"{scheme}://review-user:review-secret@localhost:{port}/store"
    assert not storage_usage.valid_target(url)
    assert await storage_usage.storage_used(url) is None
    spawn.assert_not_awaited()
    assert rclone_remote_for(url) is None
    # logging the failure must not raise either, and must still redact
    assert safe_url(url) == f"{scheme}://review-user:***@localhost:{port}/store"
    with patch("requests.get") as get:
        assert await storage_usage.http_storage_used(url) is None
        get.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "HTTP://u:review-secret@localhost:99999/store",  # upper-case scheme
        "http://u:alpha@private-tail@localhost:99999/store",  # `@` in the password
        "http://u:review-secret@[broken:99999/store",  # does not parse at all
        "sftp://u:review-secret@localhost:invalid/./r",
    ],
)
async def test_redaction_never_leaks_or_raises_on_odd_urls(monkeypatch, url):
    """Logging a failure must not become the leak: no password fragment in
    the redacted text, no exception from the redaction, and an unparseable
    URL is unknown rather than measured."""
    monkeypatch.setattr(storage_usage.asyncio, "create_subprocess_exec", AsyncMock())
    redacted = safe_url(url)
    for fragment in ("review-secret", "alpha", "private-tail"):
        assert fragment not in redacted
    assert not storage_usage.valid_target(url)
    assert await storage_usage.storage_used(url) is None
    assert await storage_usage.http_storage_used(url) is None
