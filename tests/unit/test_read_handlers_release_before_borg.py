"""A read handler holds no pooled connection while Borg runs.

A coroutine handler that takes the request's session keeps the connection of
its authentication: its own queries run on the event loop and must not wait
for one there. The handlers that then await Borg on the server kept it for as
long as Borg ran, and the downloads for as long as the client read. Thirty
such requests held the whole pool (10 + 20 in production), and every other
request waited behind them until the pool timeout.

They end their read before Borg runs, and what they read afterwards is read
in a thread: on the event loop, a wait for a connection would hold every
request of the process.
"""

import asyncio
import contextvars
import json
import os
import sys
import threading
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, event, inspect as sa_inspect, text
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.borg_router import BorgRouter
from app.database import database
from app.database.database import (
    Base,
    end_read_keeping_loaded,
    get_db,
    register_utc_session_timezone,
    run_transaction_off_loop,
)
from app.database.models import (
    LicensingState,
    Repository,
    SSHConnection,
    SSHKey,
    SystemSettings,
    User,
)

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
DATABASES = [
    "sqlite",
    pytest.param(
        "postgresql",
        marks=pytest.mark.skipif(
            not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
        ),
    ),
]
# Short enough that a request stuck until the pool timeout fails the test
# quickly, long enough for a free connection to be handed over in time.
POOL_TIMEOUT_SECONDS = 3
# No test depends on how long anything takes. A scenario that a regression
# leaves waiting for ever (a gate nobody opens) fails at this deadline.
SCENARIO_DEADLINE_SECONDS = 60
ARCHIVE_ID = "ab" * 32
SUDO_REMOTE_PATH = "sudo -n -H borg"

ARCHIVE = {
    "name": "nightly",
    "id": ARCHIVE_ID,
    "start": "2026-01-01T00:00:00",
    "time": "2026-01-01T00:00:00",
    "end": "2026-01-01T00:01:00",
    "stats": {"original_size": 10, "nfiles": 1},
    "nfiles": 1,
    "original_size": 10,
}
REPOSITORY_JSON = json.dumps(
    {
        "archives": [ARCHIVE],
        "repository": {"id": "r" * 64, "last_modified": "2026-01-01T00:00:00"},
        "encryption": {"mode": "repokey"},
        "cache": {},
    }
)
ITEM_LINE = json.dumps(
    {
        "path": "etc/hosts",
        "type": "-",
        "mode": "-rw-r--r--",
        "user": "root",
        "group": "root",
        "size": 3,
        "mtime": "2026-01-01T00:00:00",
        "healthy": True,
    }
)


@pytest.fixture(scope="module")
def postgres_schema():
    """One schema for the module's PostgreSQL cases (other PostgreSQL tests
    drop `public`); every test adds repositories of its own to it."""
    if not POSTGRES_URL:
        yield None
        return
    schema = f"read_handlers_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        POSTGRES_URL, connect_args={"options": f"-c search_path={schema}"}
    )
    try:
        Base.metadata.create_all(engine)
        yield schema
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@contextmanager
def _pool(database, test_db, schema, size):
    """A production-style pool on the test's database (SQLite) or on the
    module's PostgreSQL schema."""
    if database == "sqlite":
        engine = create_engine(
            test_db.get_bind().url,
            poolclass=QueuePool,
            pool_size=size,
            max_overflow=0,
            pool_timeout=POOL_TIMEOUT_SECONDS,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    else:
        engine = create_engine(
            POSTGRES_URL,
            poolclass=QueuePool,
            pool_size=size,
            max_overflow=0,
            pool_timeout=POOL_TIMEOUT_SECONDS,
            connect_args={"options": f"-c search_path={schema}"},
        )
        register_utc_session_timezone(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _seed(db, password_hash, *, use_sudo=False):
    """An admin, a plan with Borg 2, and one repository of each kind the
    handlers tell apart. Returns plain values: the session is the test's."""
    tag = uuid.uuid4().hex[:8]
    if db.query(User).filter(User.username == "admin").first() is None:
        db.add(
            User(
                username="admin",
                password_hash=password_hash,
                is_active=True,
                role="admin",
            )
        )
    if db.query(LicensingState).first() is None:
        db.add(
            LicensingState(
                instance_id=f"read-handlers-{tag}",
                plan="pro",
                status="active",
                is_trial=False,
            )
        )
    if db.query(SystemSettings).first() is None:
        db.add(SystemSettings())
    key = SSHKey(
        name=f"key-{tag}",
        public_key="ssh-ed25519 AAAA test",
        private_key="written by the test's stand-in",
        key_type="ed25519",
        fingerprint=f"fp-{tag}",
    )
    db.add(key)
    db.flush()

    def connection(host, **fields):
        row = SSHConnection(
            host=host,
            username="borg",
            port=22,
            ssh_key_id=key.id,
            status="connected",
            use_sudo=use_sudo,
            **fields,
        )
        db.add(row)
        db.flush()
        return row

    def repository(name, **fields):
        row = Repository(
            name=f"{name}-{tag}", encryption="repokey", mode="full", **fields
        )
        db.add(row)
        db.flush()
        return SimpleNamespace(id=row.id, path=row.path, name=row.name)

    repositories = {
        "local1": repository(
            "local1",
            path=f"/repos/{tag}/local1",
            repository_type="local",
            borg_version=1,
        ),
        "local2": repository(
            "local2",
            path=f"/repos/{tag}/local2",
            repository_type="local",
            borg_version=2,
        ),
        "ssh1": repository(
            "ssh1",
            path=f"ssh://borg@one-{tag}.example:22/srv/repo",
            repository_type="ssh",
            borg_version=1,
            connection_id=connection(f"one-{tag}.example").id,
        ),
        "ssh2": repository(
            "ssh2",
            path=f"ssh://borg@two-{tag}.example:22/srv/repo",
            repository_type="ssh",
            borg_version=2,
            connection_id=connection(f"two-{tag}.example").id,
        ),
    }
    # From before host keys were verified: the key is pinned, and the session
    # committed, when the command's environment is built.
    for name, version in (("unpinned1", 1), ("unpinned2", 2)):
        unpinned = connection(f"{name}-{tag}.example", host_key_trust_on_first_use=True)
        repositories[name] = repository(
            name,
            path=f"ssh://borg@{name}-{tag}.example:22/srv/repo",
            repository_type="ssh",
            borg_version=version,
            connection_id=unpinned.id,
        )
        repositories[name].connection_id = unpinned.id
    repositories["agent1"] = repository(
        "agent1",
        path=f"/repos/{tag}/agent1",
        repository_type="local",
        borg_version=1,
        executor_type="agent",
    )
    # No connection of its own: found by its URL, as before connections
    # were linked.
    connection(f"legacy-{tag}.example")
    repositories["legacy1"] = repository(
        "legacy1",
        path=f"ssh://borg@legacy-{tag}.example:22/srv/repo",
        repository_type="ssh",
        borg_version=1,
    )
    db.commit()
    return repositories


class Borg:
    """Stands in for the Borg process: every start waits at a gate, with what
    the request's pool looked like when it got there."""

    def __init__(self, engine):
        self.engine = engine
        self.checked_out_at_start: list[int] = []
        self.commands: list[list[str]] = []
        self.environments: list[dict] = []
        self.arrived = asyncio.Event()
        self.open = asyncio.Event()
        # A tar export writes its first bytes, then waits for this file.
        self.tar_ends_with: str | None = None

    async def start(self, *command, **options):
        self.checked_out_at_start.append(self.engine.pool.checkedout())
        self.commands.append([str(part) for part in command])
        self.environments.append(dict(options.get("env") or {}))
        self.arrived.set()
        await self.open.wait()
        return await self._process(self.commands[-1], options.get("cwd"))

    async def _process(self, command, cwd):
        if "export-tar" in command and self.tar_ends_with:
            script = (
                "import os, sys, time; sys.stdout.write('tar '); sys.stdout.flush()\n"
                f"end = time.monotonic() + {SCENARIO_DEADLINE_SECONDS}\n"
                f"while not os.path.exists({self.tar_ends_with!r}):\n"
                "    if time.monotonic() > end: sys.exit(1)\n"
                "    time.sleep(0.01)\n"
                "sys.stdout.write('bytes')"
            )
        elif "export-tar" in command:
            script = "import sys; sys.stdout.write('tar bytes')"
        elif "extract" in command and "--dry-run" not in command:
            script = (
                "import os; os.makedirs('etc', exist_ok=True); "
                "open('etc/hosts', 'w').write('::1')"
            )
        elif "--json-lines" in command or "--format" in command:
            script = f"import sys; sys.stdout.write({ITEM_LINE!r})"
        else:
            script = f"import sys; sys.stdout.write({REPOSITORY_JSON!r})"
        return await REAL_SUBPROCESS_EXEC(
            sys.executable,
            "-c",
            script,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    def remote_paths(self) -> list:
        """The remote path every started command was given: Borg 1 takes it
        as an option, Borg 2 from its environment."""
        paths = []
        for command, environment in zip(self.commands, self.environments):
            if "--remote-path" in command:
                paths.append(command[command.index("--remote-path") + 1])
            else:
                paths.append(environment.get("BORG_REMOTE_PATH"))
        return paths


REAL_SUBPROCESS_EXEC = asyncio.create_subprocess_exec
IN_A_REQUEST = contextvars.ContextVar("in_a_request", default=False)


class Harness:
    def __init__(self, client, engine, headers, monkeypatch, key_dir):
        from app.main import app

        self.app = app
        self.client = client
        self.engine = engine
        self.headers = headers
        self.loop_thread = None
        self.loop_checkouts = 0
        self.loop_statements_after_borg: list[str] = []
        self.borg: Borg | None = None
        self.response_started: asyncio.Event | None = None
        self.requests: list[asyncio.Task] = []
        self.checked_out_at_response_start: list[int] = []
        self.checked_out_when_asking_for_a_thread: list[int] = []
        self.key_dir = key_dir
        self.key_files: list[str] = []

        @event.listens_for(engine, "checkout")
        def count(dbapi_connection, record, proxy):
            if threading.get_ident() == self.loop_thread:
                self.loop_checkouts += 1

        @event.listens_for(engine, "before_cursor_execute")
        def record(conn, cursor, statement, parameters, context, executemany):
            if (
                self.borg is not None
                and self.borg.commands
                and threading.get_ident() == self.loop_thread
            ):
                self.loop_statements_after_borg.append(statement)

        threads = database._OFF_LOOP_THREADS

        class WatchedThreads:
            """`run_off_loop`'s threads, noting what a request's pool held
            when the request asked for one: it then waits for the thread."""

            def submit(_self, function, *args):
                if IN_A_REQUEST.get():
                    self.checked_out_when_asking_for_a_thread.append(
                        engine.pool.checkedout()
                    )
                return threads.submit(function, *args)

        monkeypatch.setattr(database, "_OFF_LOOP_THREADS", WatchedThreads())

        async def start_borg(*command, **options):
            return await self.borg.start(*command, **options)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", start_borg)

        def write_key(ssh_key) -> str:
            path = os.path.join(self.key_dir, f"key-{uuid.uuid4().hex}")
            with open(path, "w") as key_file:
                key_file.write("private key")
            self.key_files.append(path)
            return path

        monkeypatch.setattr("app.utils.ssh_utils.write_ssh_key_to_tempfile", write_key)

        async def nothing_cached(*args, **kwargs):
            return None

        async def cached(*args, **kwargs):
            return True

        from app.services.cache_service import archive_cache

        monkeypatch.setattr(archive_cache, "get", nothing_cached)
        monkeypatch.setattr(archive_cache, "set", cached)

    def run(self, scenario):
        """`scenario(harness, client)` on the application's event loop."""

        async def on_the_loop():
            self.loop_thread = threading.get_ident()
            self.borg = Borg(self.engine)
            self.response_started = asyncio.Event()
            transport = httpx.ASGITransport(app=self._observed_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test", timeout=None
            ) as client:
                try:
                    return await asyncio.wait_for(
                        scenario(self, client), SCENARIO_DEADLINE_SECONDS
                    )
                finally:
                    # Nothing of a failed scenario stays behind.
                    self.borg.open.set()
                    for request in self.requests:
                        request.cancel()
                    await asyncio.gather(*self.requests, return_exceptions=True)

        return self.client.portal.call(on_the_loop)

    async def _observed_app(self, scope, receive, send):
        """The application, telling when a response's headers were sent:
        from then on a streamed body is in flight."""

        async def observing_send(message):
            if message["type"] == "http.response.start":
                self.checked_out_at_response_start.append(self.engine.pool.checkedout())
                self.response_started.set()
            await send(message)

        IN_A_REQUEST.set(True)
        await self.app(scope, receive, observing_send)

    def request(self, client, method, url, body=None):
        options = {"headers": self.headers}
        if body is not None:
            options["json"] = body
        request = asyncio.create_task(client.request(method, url, **options))
        self.requests.append(request)
        return request

    async def reaches_borg(self, *requests):
        """Wait until Borg was started; fail if a request ends first."""
        arrival = asyncio.create_task(self.borg.arrived.wait())
        try:
            await asyncio.wait(
                {arrival, *requests}, return_when=asyncio.FIRST_COMPLETED
            )
            ended = [request.result() for request in requests if request.done()]
            assert arrival.done(), f"ended before Borg ran: {_outcomes(ended)}"
        finally:
            arrival.cancel()

    async def let_borg_run(self, *requests):
        """Open the gate for every start, this one and the ones that follow
        it, and return the responses."""
        self.borg.open.set()
        return await asyncio.gather(*requests)

    def key_files_left(self) -> list[str]:
        return [path for path in self.key_files if os.path.exists(path)]


def _outcomes(responses) -> list:
    return [(response.status_code, response.text[:200]) for response in responses]


@pytest.fixture
def harness_factory(
    test_client,
    test_db,
    held_runner,
    admin_headers,
    fixture_password_hashes,
    postgres_schema,
    monkeypatch,
    tmp_path,
):
    """`harness_factory(database, size=4, use_sudo=False)` gives the harness
    and the seeded repositories."""
    from app.main import app

    open_pools = []

    def build(database, size=4, use_sudo=False):
        manager = _pool(database, test_db, postgres_schema, size)
        engine = manager.__enter__()
        open_pools.append(manager)
        factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        with factory() as setup:
            repositories = _seed(
                setup, fixture_password_hashes["admin123"], use_sudo=use_sudo
            )

        def per_request_session():
            db = factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = per_request_session
        key_dir = tmp_path / "keys"
        key_dir.mkdir(exist_ok=True)
        harness = Harness(test_client, engine, admin_headers, monkeypatch, str(key_dir))
        harness.sessions = factory
        return harness, repositories

    try:
        yield build
    finally:
        for manager in open_pools:
            manager.__exit__(None, None, None)


def _restore_preview(repository) -> dict:
    return {
        "repository": repository.path,
        "repository_id": repository.id,
        "archive": "nightly",
        "paths": ["etc"],
        "destination": "/tmp/restore-preview",
    }


def _borg1_routes(kind):
    """The Borg 1 routes, by path, for the repository of `kind`."""
    return [
        (kind, "GET", "/api/repositories/{id}", None),
        (kind, "GET", "/api/repositories/{id}/stats", None),
        (kind, "GET", "/api/repositories/{id}/info", None),
        (kind, "GET", "/api/repositories/{id}/archives/live", None),
        (kind, "POST", "/api/repositories/{id}/break-lock", None),
        (kind, "GET", "/api/archives/list?repository={path}", None),
        (kind, "GET", "/api/archives/nightly/info?repository={path}", None),
        (
            kind,
            "GET",
            "/api/archives/nightly/info?repository={path}&include_files=true",
            None,
        ),
        (kind, "GET", "/api/archives/nightly/contents?repository={path}", None),
        (
            kind,
            "GET",
            "/api/archives/download?repository={path}&archive=nightly"
            "&file_path=etc/hosts",
            None,
        ),
        (
            kind,
            "GET",
            "/api/archives/download-folder?repository={path}&archive=nightly"
            "&directory_path=etc",
            None,
        ),
        (kind, "GET", "/api/browse/{id}/nightly", None),
        (kind, "POST", "/api/restore/preview", _restore_preview),
    ]


def _borg2_routes(kind):
    archive = ARCHIVE_ID
    return [
        # the routes both Borg versions share
        (kind, "GET", "/api/repositories/{id}", None),
        (kind, "GET", "/api/repositories/{id}/info", None),
        (kind, "POST", "/api/repositories/{id}/break-lock", None),
        (kind, "GET", "/api/browse/{id}/nightly", None),
        (kind, "POST", "/api/restore/preview", _restore_preview),
        # Borg 2's own
        (kind, "GET", "/api/v2/repositories/{id}/info", None),
        (kind, "GET", "/api/v2/repositories/{id}/archives", None),
        (kind, "GET", "/api/v2/archives/list?repository={id}", None),
        (kind, "GET", f"/api/v2/archives/{archive}/info?repository={{id}}", None),
        (
            kind,
            "GET",
            f"/api/v2/archives/{archive}/info?repository={{id}}&include_files=true",
            None,
        ),
        (kind, "GET", f"/api/v2/archives/{archive}/contents?repository={{id}}", None),
        (
            kind,
            "GET",
            f"/api/v2/archives/download?repository={{id}}&archive={archive}"
            "&file_path=etc/hosts",
            None,
        ),
        (
            kind,
            "GET",
            f"/api/v2/archives/download-folder?repository={{id}}&archive={archive}"
            "&directory_path=etc",
            None,
        ),
    ]


ROUTES = (
    _borg1_routes("local1")
    + _borg1_routes("ssh1")
    + _borg2_routes("local2")
    + _borg2_routes("ssh2")
)
SSH_ROUTES = _borg1_routes("ssh1") + _borg1_routes("legacy1") + _borg2_routes("ssh2")
# The routes that take a repository's turn before they run Borg.
SERIALIZED_ROUTES = [
    ("local1", "GET", "/api/repositories/{id}/info", None),
    ("local1", "GET", "/api/repositories/{id}/archives/live", None),
    ("local2", "GET", "/api/v2/repositories/{id}/info", None),
    ("local2", "GET", "/api/v2/repositories/{id}/archives", None),
]


def _route_id(route) -> str:
    kind, method, path, _body = route
    return f"{kind} {method} {path}"


def _call(route, repositories):
    kind, method, path, body = route
    repository = repositories[kind]
    return (
        method,
        path.format(id=repository.id, path=repository.path),
        body(repository) if body else None,
    )


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize("route", ROUTES, ids=_route_id)
def test_a_read_handler_holds_no_connection_while_borg_runs(
    harness_factory, database, route
):
    harness, repositories = harness_factory(database)
    method, url, body = _call(route, repositories)

    async def scenario(harness, client):
        request = harness.request(client, method, url, body)
        await harness.reaches_borg(request)
        (response,) = await harness.let_borg_run(request)
        return response

    response = harness.run(scenario)

    assert response.status_code == 200, response.text
    # What is read after Borg is read in a thread: on the loop, a query waits
    # for a connection there, and every request with it.
    assert harness.loop_statements_after_borg == []
    assert harness.loop_checkouts == 0
    assert harness.key_files_left() == []
    assert harness.engine.pool.checkedout() == 0
    # A request that waits for a thread while it holds a connection, while
    # the threads wait for connections, waits until the pool timeout.
    assert set(harness.checked_out_when_asking_for_a_thread) <= {0}
    # Nor is one held while the answer is sent.
    assert harness.checked_out_at_response_start == [0]
    # At every start of Borg (some answers take two).
    assert harness.borg.checked_out_at_start == [0] * len(harness.borg.commands)


@pytest.mark.unit
@pytest.mark.parametrize("route", SSH_ROUTES, ids=_route_id)
def test_borg_is_given_the_remote_path_of_a_sudo_connection(harness_factory, route):
    """The remote path is looked up through the session. With the read ended
    before Borg runs, it is looked up before that, and is the same as ever:
    also for a repository whose connection is found by its URL."""
    harness, repositories = harness_factory("sqlite", use_sudo=True)
    method, url, body = _call(route, repositories)

    async def scenario(harness, client):
        request = harness.request(client, method, url, body)
        await harness.reaches_borg(request)
        (response,) = await harness.let_borg_run(request)
        return response

    response = harness.run(scenario)

    assert response.status_code == 200, response.text
    assert harness.borg.commands
    assert harness.borg.remote_paths() == [SUDO_REMOTE_PATH] * len(
        harness.borg.commands
    )
    assert harness.loop_statements_after_borg == []
    assert harness.borg.checked_out_at_start == [0] * len(harness.borg.commands)


@pytest.mark.unit
@pytest.mark.parametrize(
    "route", _borg1_routes("unpinned1") + _borg2_routes("unpinned2"), ids=_route_id
)
def test_a_commit_while_the_environment_is_built_leaves_nothing_for_the_loop(
    harness_factory, monkeypatch, tmp_path, route
):
    """A connection from before host keys were verified gets its key pinned
    when the command's environment is built, and that commit expires the
    repository and the user. They are loaded again before the read ends: not
    by the next read on the event loop, which would wait for a connection
    there and keep it while Borg runs."""
    from app.utils import ssh_host_keys

    host_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPinnedOnFirstUseByTheTest"
    monkeypatch.setattr(ssh_host_keys, "scan_host_key", lambda host, port=22: host_key)
    monkeypatch.setattr(
        ssh_host_keys, "known_hosts_dir", lambda: tmp_path / "known_hosts.d"
    )
    harness, repositories = harness_factory("sqlite")
    method, url, body = _call(route, repositories)

    async def scenario(harness, client):
        request = harness.request(client, method, url, body)
        await harness.reaches_borg(request)
        (response,) = await harness.let_borg_run(request)
        return response

    response = harness.run(scenario)

    assert response.status_code == 200, response.text
    with harness.sessions() as check:
        pinned = check.get(SSHConnection, repositories[route[0]].connection_id)
        assert pinned.known_host_key == host_key
    assert harness.loop_statements_after_borg == []
    assert harness.checked_out_at_response_start == [0]
    assert harness.borg.checked_out_at_start == [0] * len(harness.borg.commands)


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize("route", SERIALIZED_ROUTES, ids=_route_id)
def test_a_request_waiting_for_the_repositorys_turn_holds_no_connection(
    harness_factory, monkeypatch, database, route
):
    """Borg commands on one repository take turns. A request that waits for
    its turn kept the connection of its authentication meanwhile."""
    from app.services import repository_command_lock

    harness, repositories = harness_factory(database)
    method, url, body = _call(route, repositories)
    get_lock = repository_command_lock._get_lock
    asked_for_their_turn = 0
    both_asked = asyncio.Event()

    async def counted(*args, **kwargs):
        nonlocal asked_for_their_turn
        asked_for_their_turn += 1
        if asked_for_their_turn == 2:
            both_asked.set()
        return await get_lock(*args, **kwargs)

    monkeypatch.setattr(repository_command_lock, "_get_lock", counted)

    async def scenario(harness, client):
        first = harness.request(client, method, url, body)
        await harness.reaches_borg(first)
        second = harness.request(client, method, url, body)
        asked = asyncio.create_task(both_asked.wait())
        try:
            await asyncio.wait(
                {asked, first, second}, return_when=asyncio.FIRST_COMPLETED
            )
            ended = [request.result() for request in (first, second) if request.done()]
            assert asked.done(), f"ended before its turn: {_outcomes(ended)}"
        finally:
            asked.cancel()
        # One more turn of the loop: the second request is at the lock.
        await asyncio.sleep(0)
        waiting = (len(harness.borg.commands), harness.engine.pool.checkedout())
        return waiting, await harness.let_borg_run(first, second)

    waiting, responses = harness.run(scenario)

    assert [response.status_code for response in responses] == [200, 200]
    # One Borg running, one request waiting for its turn, no connection held.
    assert waiting == (1, 0)
    assert harness.loop_checkouts == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "path", ["/api/repositories/{id}/info", "/api/repositories/{id}/archives/live"]
)
def test_a_failed_environment_gives_its_connection_back_before_the_retry(
    harness_factory, monkeypatch, path
):
    """The command is tried again after a failure, a moment later and in
    another thread. The read that failed half way must not keep a
    connection through that wait."""
    from app.api import repositories as repositories_api

    harness, repositories = harness_factory("sqlite")
    repository = repositories["ssh1"]
    prepare = repositories_api._prepare_repository_borg_env
    attempts = []

    def failing_once(repo, db, **options):
        attempts.append(repo.id)
        if len(attempts) == 1:
            db.query(SSHConnection).count()
            raise OSError("no key file could be written")
        return prepare(repo, db, **options)

    monkeypatch.setattr(repositories_api, "_prepare_repository_borg_env", failing_once)
    sleep = asyncio.sleep
    held_while_waiting_to_retry = []

    async def short_retry_wait(delay, *args, **kwargs):
        if IN_A_REQUEST.get() and delay >= 1:
            held_while_waiting_to_retry.append(harness.engine.pool.checkedout())
            delay = 0
        return await sleep(delay, *args, **kwargs)

    monkeypatch.setattr(asyncio, "sleep", short_retry_wait)

    async def scenario(harness, client):
        request = harness.request(client, "GET", path.format(id=repository.id))
        await harness.reaches_borg(request)
        (response,) = await harness.let_borg_run(request)
        return response

    response = harness.run(scenario)

    assert response.status_code == 200, response.text
    assert len(attempts) == 2
    assert held_while_waiting_to_retry == [0]
    assert set(harness.checked_out_when_asking_for_a_thread) <= {0}
    assert harness.key_files_left() == []
    assert harness.borg.checked_out_at_start == [0]


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_more_requests_awaiting_borg_than_connections_leave_the_pool_free(
    harness_factory, database
):
    """The production exhaustion at a small scale: two connections, six
    repository details whose Borg takes its time, and a request that has
    nothing to do with them."""
    harness, repositories = harness_factory(database, size=2)
    repository = repositories["local1"]

    async def scenario(harness, client):
        details = [
            harness.request(client, "GET", f"/api/repositories/{repository.id}")
            for _ in range(6)
        ]
        while len(harness.borg.commands) < len(details):
            harness.borg.arrived.clear()
            await harness.reaches_borg(*details)
        unrelated = await client.get(
            f"/api/repositories/{repository.id}/storage", headers=harness.headers
        )
        held = harness.engine.pool.checkedout()
        return unrelated, held, await harness.let_borg_run(*details)

    unrelated, held, details = harness.run(scenario)

    assert unrelated.status_code == 200, unrelated.text
    assert held == 0
    assert [response.status_code for response in details] == [200] * 6
    assert harness.loop_checkouts == 0


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_a_download_holds_no_connection_while_the_client_reads(
    harness_factory, tmp_path, database
):
    """The session of a request is closed after its response was sent: a
    streamed download kept its connection until the client had it all."""
    harness, repositories = harness_factory(database)
    repository = repositories["local1"]
    rest_of_the_tar = tmp_path / "rest-of-the-tar"

    async def scenario(harness, client):
        harness.borg.tar_ends_with = str(rest_of_the_tar)
        harness.borg.open.set()
        download = harness.request(
            client,
            "GET",
            "/api/archives/download-folder"
            f"?repository={repository.path}&archive=nightly&directory_path=etc",
        )
        started = asyncio.create_task(harness.response_started.wait())
        await asyncio.wait({started, download}, return_when=asyncio.FIRST_COMPLETED)
        started.cancel()
        # The headers are out, and Borg has not written the rest yet.
        in_flight = not download.done()
        held = harness.engine.pool.checkedout()
        rest_of_the_tar.write_text("")
        return in_flight, held, await download

    in_flight, held, response = harness.run(scenario)

    assert (response.status_code, response.content) == (200, b"tar bytes")
    assert in_flight
    assert held == 0


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize(
    "path",
    ["/api/repositories/{id}/info", "/api/v2/repositories/{id}/info"],
)
def test_the_info_of_a_borg_2_repository_still_updates_its_stored_columns(
    harness_factory, database, path
):
    """Written after Borg ran, in a thread, through the request's session:
    the repository row it writes to was read before the read ended."""
    harness, repositories = harness_factory(database)
    repository = repositories["local2"]

    async def scenario(harness, client):
        request = harness.request(client, "GET", path.format(id=repository.id))
        await harness.reaches_borg(request)
        (response,) = await harness.let_borg_run(request)
        return response

    response = harness.run(scenario)

    assert response.status_code == 200, response.text
    with harness.sessions() as check:
        stored = check.get(Repository, repository.id)
        assert stored.archive_count == 1
        assert stored.last_backup is not None


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_the_repository_detail_answers_as_before(harness_factory, database):
    harness, repositories = harness_factory(database)
    repository = repositories["local1"]

    async def scenario(harness, client):
        request = harness.request(client, "GET", f"/api/repositories/{repository.id}")
        await harness.reaches_borg(request)
        (response,) = await harness.let_borg_run(request)
        return response

    answer = harness.run(scenario).json()

    assert answer["success"] is True
    detail = answer["repository"]
    assert (detail["id"], detail["name"], detail["path"]) == (
        repository.id,
        repository.name,
        repository.path,
    )
    assert detail["executor_type"] == "server"
    assert detail["stats"]["archive_count"] == 1
    assert detail["stats"]["last_modified"] is not None
    assert "storage" in detail and "index_pending_kinds" in detail


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_the_detail_of_an_agent_repository_waits_for_its_thread_without_a_connection(
    harness_factory, database
):
    """Its statistics are the stored ones, with no Borg call that would end
    the read. The answer is read in a thread all the same, and the request
    must not hold a connection while it waits for that thread."""
    harness, repositories = harness_factory(database)
    repository = repositories["agent1"]

    async def scenario(harness, client):
        return await client.get(
            f"/api/repositories/{repository.id}", headers=harness.headers
        )

    response = harness.run(scenario)

    assert response.status_code == 200, response.text
    assert response.json()["repository"]["executor_type"] == "agent"
    assert harness.borg.commands == []
    assert harness.checked_out_when_asking_for_a_thread == [0]
    assert harness.checked_out_at_response_start == [0]
    assert harness.loop_checkouts == 0


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_the_live_archive_list_answers_as_before(harness_factory, database):
    harness, repositories = harness_factory(database)
    repository = repositories["local1"]

    async def scenario(harness, client):
        request = harness.request(
            client, "GET", f"/api/repositories/{repository.id}/archives/live"
        )
        await harness.reaches_borg(request)
        (response,) = await harness.let_borg_run(request)
        return response

    answer = harness.run(scenario).json()

    assert answer["success"] is True
    assert [archive["name"] for archive in answer["archives"]] == ["nightly"]
    assert answer["repository"] == {
        "id": repository.id,
        "name": repository.name,
        "path": repository.path,
    }


@pytest.mark.unit
@pytest.mark.parametrize("route", SERIALIZED_ROUTES, ids=_route_id)
def test_an_unknown_repository_is_still_not_found(harness_factory, route):
    harness, repositories = harness_factory("sqlite")
    _kind, method, path, _body = route

    async def scenario(harness, client):
        return await client.request(
            method, path.format(id=987654), headers=harness.headers
        )

    response = harness.run(scenario)

    assert response.status_code == 404
    assert harness.borg.commands == []
    assert harness.loop_checkouts == 0


@pytest.mark.unit
@pytest.mark.parametrize("route", SERIALIZED_ROUTES, ids=_route_id)
def test_a_user_without_access_is_still_refused(
    harness_factory, test_db, auth_headers, route
):
    """The access check runs in the thread that reads the repository."""
    harness, repositories = harness_factory("sqlite")
    harness.headers = auth_headers
    method, url, body = _call(route, repositories)

    async def scenario(harness, client):
        return await client.request(method, url, headers=harness.headers)

    response = harness.run(scenario)

    assert response.status_code == 403
    assert harness.borg.commands == []
    assert harness.loop_checkouts == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "route",
    [
        ("ssh1", "GET", "/api/repositories/{id}/info", None),
        ("ssh2", "GET", "/api/v2/repositories/{id}/info", None),
        ("ssh2", "GET", "/api/v2/repositories/{id}/archives", None),
    ],
    ids=_route_id,
)
def test_a_cancelled_request_leaves_no_key_file_and_no_connection(
    harness_factory, monkeypatch, route
):
    """The environment of the command is read in a thread, which writes the
    repository's SSH key to a file. A request cancelled while that thread
    runs never gets the path, and the file is removed all the same."""
    harness, repositories = harness_factory("sqlite")
    method, url, body = _call(route, repositories)
    writing = threading.Event()
    may_finish = threading.Event()

    from app.utils import ssh_utils

    write_key = ssh_utils.write_ssh_key_to_tempfile

    def held_write(ssh_key):
        path = write_key(ssh_key)
        writing.set()
        assert may_finish.wait(timeout=30)
        return path

    monkeypatch.setattr(ssh_utils, "write_ssh_key_to_tempfile", held_write)

    async def scenario(harness, client):
        request = harness.request(client, method, url, body)
        while not writing.is_set():
            assert not request.done(), _outcomes([request.result()])
            await asyncio.sleep(0.005)
        request.cancel()
        # The cancelled request still waits for its thread.
        await asyncio.sleep(0)
        waited = not request.done()
        may_finish.set()
        with pytest.raises(asyncio.CancelledError):
            await request
        return waited

    waited = harness.run(scenario)

    assert waited
    assert harness.key_files and harness.key_files_left() == []
    assert harness.borg.commands == []
    assert harness.engine.pool.checkedout() == 0


@pytest.mark.unit
def test_archive_info_stays_with_the_agent_when_the_repository_moves_meanwhile(
    monkeypatch,
):
    """The wait for the agent's answer commits the session, and the
    repository is read again afterwards. One moved to the server meanwhile
    must not send the file listing to the server's Borg, whose remote path
    and environment this request never prepared."""
    from contextlib import ExitStack

    from app.api.v2 import archives as v2_archives

    repository = SimpleNamespace(
        id=1,
        path="/repos/agent",
        executor_type="agent",
        execution_target=None,
        passphrase=None,
        bypass_lock=False,
    )
    listed = []

    async def info(db, repo, archive, *, timeout_seconds):
        repo.executor_type = "server"
        return {"success": True, "stdout": json.dumps({"archives": [{"name": "a1"}]})}

    async def contents(db, repo, **kwargs):
        listed.append(kwargs["archive"])
        return {"success": True, "stdout": json.dumps({"path": "etc/hosts"})}

    async def server_borg(*args, **kwargs):
        raise AssertionError("the server's Borg was asked")

    monkeypatch.setattr(v2_archives, "_agent_archive_info_result", info)
    monkeypatch.setattr(v2_archives, "_agent_archive_contents_result", contents)
    monkeypatch.setattr(v2_archives, "_get_info_timeout", lambda db: 5)
    monkeypatch.setattr(v2_archives, "_get_list_timeout", lambda db: 5)
    monkeypatch.setattr(
        v2_archives, "agent_timezone_for_repository", lambda db, repo: "UTC"
    )
    monkeypatch.setattr(v2_archives.borg2, "list_archive_contents", server_borg)

    with ExitStack() as borg_env:
        answer = asyncio.run(
            v2_archives._archive_info(None, repository, "a1", True, 10, borg_env)
        )

    assert listed == ["a1"]
    assert [entry["path"] for entry in answer["info"]["files"]] == ["etc/hosts"]


@pytest.mark.unit
def test_the_router_looks_its_remote_path_up_once(monkeypatch):
    looked_up = []

    def look_up(repository):
        looked_up.append(repository)
        return "/opt/borg"

    monkeypatch.setattr(
        "app.core.borg_router.effective_repository_remote_path", look_up
    )
    repository = SimpleNamespace(path="/repos/one", borg_version=1)
    router = BorgRouter(repository)

    assert looked_up == []
    assert (router.remote_path(), router.remote_path()) == ("/opt/borg", "/opt/borg")
    assert looked_up == [repository]


@pytest.mark.unit
def test_the_router_keeps_a_remote_path_of_none(monkeypatch):
    looked_up = []
    monkeypatch.setattr(
        "app.core.borg_router.effective_repository_remote_path",
        lambda repository: looked_up.append(repository),
    )
    router = BorgRouter(SimpleNamespace(path="/repos/one", borg_version=1))

    assert (router.remote_path(), router.remote_path()) == (None, None)
    assert len(looked_up) == 1


@pytest.mark.unit
@pytest.mark.parametrize("method", ["preview_restore", "list_archive_contents"])
def test_the_borg_2_service_takes_the_remote_path_it_is_given(monkeypatch, method):
    """Otherwise it looks the path up itself, through the repository's
    session: during the Borg call of a request that ended its read."""
    from app.services.v2 import restore_service

    def no_lookup(repository):
        raise AssertionError("looked up again")

    calls = []

    async def borg2_call(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    monkeypatch.setattr(restore_service, "effective_repository_remote_path", no_lookup)
    monkeypatch.setattr(restore_service.borg2, "extract_archive", borg2_call)
    monkeypatch.setattr(restore_service.borg2, "list_archive_contents", borg2_call)
    repository = SimpleNamespace(path="/repos/two", passphrase=None, bypass_lock=False)
    arguments = {"repo": repository, "archive": "nightly", "remote_path": "/opt/borg2"}
    if method == "preview_restore":
        arguments.update(paths=["etc"], destination="/tmp/preview")

    asyncio.run(getattr(restore_service.restore_v2_service, method)(**arguments))

    assert [call["remote_path"] for call in calls] == ["/opt/borg2"]


@pytest.mark.unit
@pytest.mark.parametrize("method", ["preview_restore", "list_archive_contents"])
def test_the_borg_2_service_still_looks_the_remote_path_up_itself(monkeypatch, method):
    from app.services.v2 import restore_service

    calls = []

    async def borg2_call(**kwargs):
        calls.append(kwargs)
        return {"success": True}

    monkeypatch.setattr(
        restore_service, "effective_repository_remote_path", lambda repository: "sudo"
    )
    monkeypatch.setattr(restore_service.borg2, "extract_archive", borg2_call)
    monkeypatch.setattr(restore_service.borg2, "list_archive_contents", borg2_call)
    repository = SimpleNamespace(path="/repos/two", passphrase=None, bypass_lock=False)
    arguments = {"repo": repository, "archive": "nightly"}
    if method == "preview_restore":
        arguments.update(paths=["etc"], destination="/tmp/preview")

    asyncio.run(getattr(restore_service.restore_v2_service, method)(**arguments))

    assert [call["remote_path"] for call in calls] == ["sudo"]


def _single_request(test_db, postgres_schema, database):
    """A pool of one connection and a session on it, with a repository."""
    manager = _pool(database, test_db, postgres_schema, 1)
    engine = manager.__enter__()
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with sessions() as setup:
        row = Repository(
            name=f"helper-{uuid.uuid4().hex[:8]}",
            path=f"/repos/helper-{uuid.uuid4().hex[:8]}",
            encryption="none",
            repository_type="local",
        )
        setup.add(row)
        setup.commit()
        repository_id = row.id
    return manager, engine, sessions, repository_id


def _statements(engine) -> list:
    statements: list = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    return statements


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_work_off_the_loop_ends_its_read_and_keeps_what_the_loop_reads(
    test_db, postgres_schema, database
):
    manager, engine, sessions, repository_id = _single_request(
        test_db, postgres_schema, database
    )
    db = sessions()
    try:
        repository = db.get(Repository, repository_id)
        end_read_keeping_loaded(db, repository)
        threads = []

        def rename(name):
            threads.append(threading.get_ident())
            repository.name = name
            # Expires the repository: the loop would query for its name.
            db.commit()
            return db.query(Repository).count()

        async def on_the_loop():
            return await run_transaction_off_loop(
                db, rename, "renamed off the loop", keep=(repository,)
            )

        assert asyncio.run(on_the_loop()) >= 1
        assert threads != [threading.get_ident()]
        assert engine.pool.checkedout() == 0
        statements = _statements(engine)
        assert repository.name == "renamed off the loop"
        assert statements == []
    finally:
        db.close()
        manager.__exit__(None, None, None)


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_work_off_the_loop_that_fails_gives_its_connection_back(
    test_db, postgres_schema, database
):
    manager, engine, sessions, repository_id = _single_request(
        test_db, postgres_schema, database
    )
    db = sessions()
    try:

        def fail():
            db.get(Repository, repository_id)
            raise LookupError("after a query")

        async def on_the_loop():
            await run_transaction_off_loop(db, fail)

        with pytest.raises(LookupError):
            asyncio.run(on_the_loop())
        assert engine.pool.checkedout() == 0
    finally:
        db.close()
        manager.__exit__(None, None, None)


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
def test_a_kept_row_that_cannot_be_loaded_again_leaves_no_transaction_open(
    test_db, postgres_schema, database
):
    """The work deleted the row the caller wanted to keep: loading it again
    fails, after a query. That transaction ends in the thread as well."""
    manager, engine, sessions, repository_id = _single_request(
        test_db, postgres_schema, database
    )
    db = sessions()
    try:
        repository = db.get(Repository, repository_id)
        end_read_keeping_loaded(db, repository)

        def delete():
            # As another writer would: the session still holds the row.
            db.query(Repository).filter(Repository.id == repository_id).delete(
                synchronize_session=False
            )
            db.commit()

        async def on_the_loop():
            await run_transaction_off_loop(db, delete, keep=(repository,))

        with pytest.raises(InvalidRequestError):
            asyncio.run(on_the_loop())
        assert engine.pool.checkedout() == 0
    finally:
        db.close()
        manager.__exit__(None, None, None)


@pytest.mark.unit
def test_work_runs_in_the_callers_thread_on_a_pool_that_cannot_wait(test_db):
    """A pool of the tests keeps its connection in its thread. The work runs
    where it is called, and ends the same way."""
    assert not database.checkout_can_wait(test_db.get_bind())
    repository = Repository(name="inline", path="/repos/inline", encryption="none")
    test_db.add(repository)
    test_db.commit()
    threads = []

    def rename(name):
        threads.append(threading.get_ident())
        repository.name = name
        test_db.commit()
        return test_db.query(Repository).count()

    async def on_the_loop():
        return await run_transaction_off_loop(
            test_db, rename, "renamed inline", keep=(repository,)
        )

    assert asyncio.run(on_the_loop()) >= 1
    assert threads == [threading.get_ident()]
    statements = _statements(test_db.get_bind())
    assert repository.name == "renamed inline"
    assert statements == []

    def fail():
        test_db.query(Repository).count()
        raise LookupError("after a query")

    async def failing():
        await run_transaction_off_loop(test_db, fail)

    with pytest.raises(LookupError):
        asyncio.run(failing())
    assert sa_inspect(repository).expired


@pytest.mark.unit
def test_ending_a_read_leaves_an_instance_of_no_session_alone(test_db):
    """What a caller built itself, or read through another session: the
    rollback does not expire it, and it does not join this session."""
    unsaved = Repository(name="unsaved", path="/repos/unsaved")
    stored = Repository(name="stored", path="/repos/stored", encryption="none")
    test_db.add(stored)
    test_db.commit()
    test_db.refresh(stored)

    end_read_keeping_loaded(test_db, unsaved, stored)

    assert unsaved not in test_db
    assert stored in test_db
    assert (unsaved.name, stored.name) == ("unsaved", "stored")
