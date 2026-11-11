"""User authentication looks the user up in a worker thread, once.

The dependencies are coroutines: a route often has several of them (the
router's policy check, then the handler's user), and as plain functions each
would wait for a worker thread of its own while the request already holds a
connection. Only the first lookup takes a thread; the others return the user
the request already has.

What the lookup hands to the handler must not make the handler query on the
event loop: a coroutine handler gets the user loaded, with the connection
still held for its own queries. A plain `def` handler runs in a worker, so
its session gives the connection back once the user is known.
"""

import asyncio
import collections
import inspect
import os
import time
import uuid
from contextlib import contextmanager

import anyio
import httpx
import pytest
from fastapi import Depends
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from starlette.requests import Request

from app.config import settings
from app.core import security
from app.core.authorization import authorize_request
from app.core.security import create_access_token, get_password_hash
from app.database.database import Base, get_db, register_utc_session_timezone
from app.database.models import ApiToken, User

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
RAW_TOKEN = "borgui_" + "u" * 32
DATABASES = [
    "sqlite",
    pytest.param(
        "postgresql",
        marks=pytest.mark.skipif(
            not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
        ),
    ),
]


CACHED_USER_DEPENDENCIES = [
    security.get_current_user,
    security.get_current_active_user,
    security.get_current_admin_user,
    authorize_request,
    security.require_role_dependency("admin"),
]
LOOKUP_DEPENDENCIES = [
    security.get_current_user,
    security.get_current_download_user,
    security.get_current_active_user,
    security.get_current_admin_user,
    security.get_current_download_admin_user,
    security.require_role_dependency("admin"),
    security.require_role_dependency("admin", allow_download_token=True),
]


def _dependency_id(dependency) -> str:
    return dependency.__qualname__


@pytest.mark.unit
@pytest.mark.parametrize("dependency", CACHED_USER_DEPENDENCIES, ids=_dependency_id)
async def test_a_dependency_takes_no_worker_thread_for_a_known_user(
    monkeypatch, dependency
):
    """FastAPI runs a plain function dependency in a worker thread. A route
    with two of them would wait for a second thread while it holds the
    connection of the first lookup."""
    assert inspect.iscoroutinefunction(dependency)

    def no_thread(*args, **kwargs):
        raise AssertionError("took a worker thread for a known user")

    monkeypatch.setattr(security.to_thread, "run_sync", no_thread)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/settings/cache/stats",
            "headers": [],
            "state": {},
        }
    )
    request.state.current_user = User(username="known", role="admin", is_active=True)
    await dependency(request, db=None)


@pytest.mark.unit
@pytest.mark.parametrize("dependency", LOOKUP_DEPENDENCIES, ids=_dependency_id)
async def test_the_user_lookup_runs_in_a_worker_thread(monkeypatch, dependency):
    looked_up_in = []

    def lookup(request, db, may_release):
        looked_up_in.append(_on_the_loop())
        return User(username="looked-up", role="admin", is_active=True)

    monkeypatch.setattr(security, "_load_current_user", lookup)
    monkeypatch.setattr(security, "_load_download_user", lookup)
    request = Request({"type": "http", "headers": [], "state": {}})
    await dependency(request, db=None)
    assert looked_up_in == [False]


def _on_the_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _create_user(db, username: str) -> int:
    user = User(username=username, email=f"{username}@example.org", role="admin")
    db.add(user)
    db.flush()
    db.add(
        ApiToken(
            user_id=user.id,
            name="burst",
            prefix=RAW_TOKEN[: security.API_TOKEN_PREFIX_LENGTH],
            token_hash=get_password_hash(RAW_TOKEN),
        )
    )
    db.commit()
    return user.id


def _headers(login: str, username: str) -> dict:
    if login == "proxy":
        return {"X-Forwarded-User": username}
    if login == "token":
        return {"Authorization": f"Bearer {RAW_TOKEN}"}
    return {"Authorization": f"Bearer {create_access_token({'sub': username})}"}


@pytest.mark.unit
@pytest.mark.parametrize("login", ["jwt", "token", "proxy"])
def test_a_coroutine_handler_reads_the_user_without_a_query_on_the_loop(
    test_client, test_db, session_per_request, monkeypatch, login
):
    """Proxy login and the personal token stamp commit, which expires the
    user and gives the connection back. The handler would then load the user
    on the loop and wait there for a connection."""
    from app.main import app

    monkeypatch.setattr(settings, "disable_authentication", login == "proxy")
    username = f"loop-{login}"
    with session_per_request() as db:
        _create_user(db, username)

    async def probe(user: User = Depends(security.get_current_user)):
        return {"id": user.id, "username": user.username, "role": user.role}

    path = f"/api/__user_auth_probe_{uuid.uuid4().hex}"
    app.router.add_api_route(path, probe)
    app.router.routes.insert(0, app.router.routes.pop())
    engine = session_per_request.kw["bind"]
    on_the_loop: list = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if _on_the_loop():
            on_the_loop.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = test_client.get(path, headers=_headers(login, username))
    finally:
        event.remove(engine, "before_cursor_execute", record)
        app.router.routes[:] = [
            route for route in app.router.routes if getattr(route, "path", "") != path
        ]

    assert response.status_code == 200
    assert response.json()["username"] == username
    assert on_the_loop == []


@contextmanager
def _single_connection_sessions(database, test_db):
    """Sessions on a pool of one connection: SQLite (the test's database) or
    PostgreSQL (a schema of its own: other PostgreSQL tests drop `public`)."""
    if database == "sqlite":
        engine = create_engine(
            test_db.get_bind().url,
            poolclass=QueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=3,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        try:
            yield engine, sessionmaker(bind=engine, autoflush=False)
        finally:
            engine.dispose()
        return
    schema = f"user_auth_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        POSTGRES_URL,
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"options": f"-c search_path={schema}"},
    )
    register_utc_session_timezone(engine)
    try:
        Base.metadata.create_all(engine)
        yield engine, sessionmaker(bind=engine, autoflush=False)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


class _Route:
    def __init__(self, endpoint):
        self.endpoint = endpoint


def _plain_handler():
    pass


async def _coroutine_handler():
    pass


def _request(login: str, username: str, endpoint) -> Request:
    headers = [
        (name.lower().encode(), value.encode())
        for name, value in _headers(login, username).items()
    ]
    request = Request({"type": "http", "headers": headers, "state": {}})
    if endpoint is not None:
        request.scope["route"] = _Route(endpoint)
    return request


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize("login", ["jwt", "token", "proxy"])
@pytest.mark.parametrize(
    "authenticate", [security.get_current_user, security.get_current_download_user]
)
@pytest.mark.parametrize(
    ("endpoint", "keeps_connection"),
    [(_plain_handler, False), (_coroutine_handler, True), (None, True)],
    ids=["def-handler", "coroutine-handler", "route-unknown"],
)
def test_authentication_gives_its_connection_back_only_to_a_handler_in_a_worker(
    test_db, monkeypatch, database, login, authenticate, endpoint, keeps_connection
):
    monkeypatch.setattr(settings, "disable_authentication", login == "proxy")
    username = f"pool-{login}"
    with _single_connection_sessions(database, test_db) as (engine, sessions):
        with sessions() as setup:
            user_id = _create_user(setup, username)
        db = sessions()
        try:
            user = anyio.run(authenticate, _request(login, username, endpoint), db)
            assert engine.pool.checkedout() == (1 if keeps_connection else 0)

            # The user is loaded either way: reading it runs no query.
            statements: list = []
            event.listen(
                engine,
                "before_cursor_execute",
                lambda *args: statements.append(args[2]),
            )
            assert (user.id, user.username, user.role) == (user_id, username, "admin")
            assert statements == []

            # And what a handler writes through it is still written.
            user.full_name = "written after authentication"
            db.commit()
        finally:
            db.close()

        with sessions() as check:
            assert check.get(User, user_id).full_name == "written after authentication"


@pytest.mark.unit
def test_authentication_keeps_the_connection_of_a_session_with_unsaved_changes(
    test_db, monkeypatch
):
    """Giving the connection back rolls the session back. Whatever a caller
    has changed and not yet saved must survive the authentication."""
    monkeypatch.setattr(settings, "disable_authentication", False)
    with _single_connection_sessions("sqlite", test_db) as (engine, sessions):
        with sessions() as setup:
            user_id = _create_user(setup, "unsaved")
        db = sessions()
        try:
            other = User(username="unsaved-other", email="unsaved-other@example.org")
            db.add(other)
            anyio.run(
                security.get_current_user,
                _request("jwt", "unsaved", _plain_handler),
                db,
            )
            assert engine.pool.checkedout() == 1
            assert other in db.new
            db.commit()
        finally:
            db.close()

        with sessions() as check:
            assert check.get(User, user_id) is not None
            assert (
                check.query(User).filter(User.username == "unsaved-other").count() == 1
            )


@pytest.mark.unit
def test_a_proxy_login_stops_when_a_retry_would_save_the_same_user(
    test_db, monkeypatch
):
    """The fallback email is taken by another account: re-reading cannot
    change what the login tries to save, so it fails after one attempt
    instead of retrying forever."""
    monkeypatch.setattr(settings, "disable_authentication", True)
    test_db.add(User(username="someone-else", email="taken@proxy.local"))
    test_db.commit()

    attempts: list = []

    def count_attempt(session, flush_context, instances):
        attempts.append(1)
        if len(attempts) > 2:
            raise RuntimeError("the login retried a save that cannot succeed")

    sessions = sessionmaker(bind=test_db.get_bind(), autoflush=False)
    db = sessions()
    event.listen(db, "before_flush", count_attempt)
    try:
        with pytest.raises(IntegrityError):
            security.get_current_user_proxy(_request("proxy", "taken", None), db)
    finally:
        db.close()

    assert len(attempts) == 1


def _burst(
    test_client, test_db, monkeypatch, path: str, headers: dict, count: int, json=None
):
    """`count` parallel GETs (POSTs of `json`, if given) with two worker
    threads and two connections, the runner on the same pool. Returns the
    outcome per status code."""
    from app.main import app

    engine = create_engine(
        test_db.get_bind().url,
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=3,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    factory = sessionmaker(bind=engine, autoflush=False)

    def per_request_session():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = per_request_session
    monkeypatch.setattr("app.database.database.SessionLocal", factory)
    real_verify_token = security.verify_token

    def slow_verify_token(token):
        time.sleep(0.05)
        return real_verify_token(token)

    monkeypatch.setattr(security, "verify_token", slow_verify_token)

    async def burst():
        limiter = anyio.to_thread.current_default_thread_limiter()
        tokens = limiter.total_tokens
        limiter.total_tokens = 2
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test", timeout=None
            ) as client:
                if json is None:
                    requests = [client.get(path, headers=headers) for _ in range(count)]
                else:
                    requests = [
                        client.post(path, headers=headers, json=json)
                        for _ in range(count)
                    ]
                return await asyncio.gather(*requests, return_exceptions=True)
        finally:
            limiter.total_tokens = tokens

    try:
        results = test_client.portal.call(burst)
    finally:
        engine.dispose()
    return collections.Counter(
        getattr(result, "status_code", type(result).__name__) for result in results
    )


@pytest.mark.unit
def test_a_burst_on_a_route_with_two_user_dependencies_succeeds(
    test_client, test_db, monkeypatch
):
    """`/api/settings/cache/stats` has the router's policy check and the
    handler's user, and queries on the loop. Two worker threads, two
    connections, eight requests: had each dependency waited for a thread of
    its own while the request held its connection, they would wait for each
    other until the pool timeout."""
    test_db.add(User(username="burst-admin", email="burst@example.org", role="admin"))
    test_db.commit()
    outcomes = _burst(
        test_client,
        test_db,
        monkeypatch,
        "/api/settings/cache/stats",
        _headers("jwt", "burst-admin"),
        8,
    )
    assert outcomes == {200: 8}


@pytest.mark.unit
def test_a_burst_on_a_route_that_queries_before_the_user_lookup_succeeds(
    test_client, test_db, monkeypatch
):
    """A plain dependency before the user, such as a feature check, leaves
    the request holding a connection when the lookup starts. Had the lookup
    then waited for a shared worker thread, the threads waiting for
    connections and the requests holding them would wait for each other."""
    from app.main import app

    test_db.add(User(username="burst-reader", email="reader@example.org"))
    test_db.commit()

    def query_first(db=Depends(get_db)):
        db.query(User).first()

    async def handler(user: User = Depends(security.get_current_user)):
        return {"id": user.id}

    path = f"/api/__query_then_user_{uuid.uuid4().hex}"
    app.router.add_api_route(path, handler, dependencies=[Depends(query_first)])
    app.router.routes.insert(0, app.router.routes.pop())
    try:
        outcomes = _burst(
            test_client,
            test_db,
            monkeypatch,
            path,
            _headers("jwt", "burst-reader"),
            8,
        )
    finally:
        app.router.routes[:] = [
            route for route in app.router.routes if getattr(route, "path", "") != path
        ]
    assert outcomes == {200: 8}


@pytest.mark.unit
def test_a_burst_of_token_creations_succeeds_off_the_loop(
    test_client, test_db, monkeypatch
):
    """Creating a token hashes it, commits and reads the row again. On the
    loop, the hashing holds every other request, and the read after the
    commit waits there for a connection the other requests hold."""
    from app.api import tokens

    test_db.add(User(username="burst-tokens", email="tokens@example.org"))
    test_db.commit()
    hashed_on_the_loop = []
    real_hash = tokens.get_password_hash

    def record_hash(value):
        hashed_on_the_loop.append(_on_the_loop())
        return real_hash(value)

    monkeypatch.setattr(tokens, "get_password_hash", record_hash)
    outcomes = _burst(
        test_client,
        test_db,
        monkeypatch,
        "/api/settings/tokens",
        _headers("jwt", "burst-tokens"),
        8,
        json={"name": "burst"},
    )
    assert outcomes == {201: 8}
    assert hashed_on_the_loop == [False] * 8


@pytest.mark.unit
@pytest.mark.parametrize("has_queried", [False, True])
async def test_only_a_request_holding_a_connection_takes_a_thread_of_its_own(
    test_db, monkeypatch, has_queried
):
    """The shared worker threads bound how many lookups run at once. Only a
    request that already holds a connection bypasses them."""
    limiters = []

    async def record(load, request, db, may_release, limiter=None):
        limiters.append(limiter)
        return User(username="looked-up", role="admin", is_active=True)

    monkeypatch.setattr(security.to_thread, "run_sync", record)
    db = sessionmaker(bind=test_db.get_bind(), autoflush=False)()
    try:
        if has_queried:
            db.query(User).first()
        await security.get_current_user(
            Request({"type": "http", "headers": [], "state": {}}), db
        )
    finally:
        db.close()

    (limiter,) = limiters
    if has_queried:
        assert limiter is not None and limiter.total_tokens == 1
    else:
        assert limiter is None


@pytest.mark.unit
async def test_a_request_looks_its_user_up_once(monkeypatch):
    lookups = []

    def lookup(request, db, may_release):
        lookups.append(request)
        return User(username="looked-up", role="admin", is_active=True)

    monkeypatch.setattr(security, "_load_current_user", lookup)
    request = Request({"type": "http", "headers": [], "state": {}})
    first = await security.get_current_user(request, db=None)
    assert await security.get_current_admin_user(request, db=None) is first
    assert len(lookups) == 1


@pytest.mark.unit
def test_authentication_keeps_a_transaction_that_began_before_it(test_db, monkeypatch):
    """What an earlier dependency wrote and flushed is not in `db.new`, and
    a rollback would drop it. Only a lookup that began the transaction gives
    the connection back."""
    monkeypatch.setattr(settings, "disable_authentication", False)
    with _single_connection_sessions("sqlite", test_db) as (engine, sessions):
        with sessions() as setup:
            _create_user(setup, "flushed")
        db = sessions()
        try:
            db.add(User(username="flushed-other", email="flushed-other@example.org"))
            db.flush()
            anyio.run(
                security.get_current_user,
                _request("jwt", "flushed", _plain_handler),
                db,
            )
            assert engine.pool.checkedout() == 1
            db.commit()
        finally:
            db.close()

        with sessions() as check:
            assert (
                check.query(User).filter(User.username == "flushed-other").count() == 1
            )


@pytest.mark.unit
@pytest.mark.parametrize("database", DATABASES)
@pytest.mark.parametrize("login", ["proxy", "token"])
def test_a_login_that_commits_after_an_earlier_query_gives_the_connection_back(
    test_db, monkeypatch, database, login
):
    """An earlier dependency queried, so the lookup starts inside its
    transaction. The proxy login and the token stamp commit, which ends that
    transaction: nothing of it is left to keep, and a plain `def` handler
    must not hold the connection while it waits for a worker thread."""
    monkeypatch.setattr(settings, "disable_authentication", login == "proxy")
    username = f"after-query-{login}"
    with _single_connection_sessions(database, test_db) as (engine, sessions):
        with sessions() as setup:
            user_id = _create_user(setup, username)
        db = sessions()
        try:
            db.query(User).first()
            user = anyio.run(
                security.get_current_user,
                _request(login, username, _plain_handler),
                db,
            )
            assert engine.pool.checkedout() == 0
            assert (user.id, user.username) == (user_id, username)
        finally:
            db.close()


@pytest.mark.unit
def test_ending_authentication_keeps_unsaved_changes(test_db):
    """A rollback would drop what the session has added and not yet saved,
    however the lookup came to be allowed to give the connection back."""
    sessions = sessionmaker(bind=test_db.get_bind(), autoflush=False)
    with sessions() as setup:
        _create_user(setup, "pending")
    db = sessions()
    try:
        user = db.query(User).filter(User.username == "pending").one()
        other = User(username="pending-other", email="pending-other@example.org")
        db.add(other)
        security._end_authentication(
            _request("jwt", "pending", _plain_handler), db, user, True
        )
        assert other in db.new
    finally:
        db.close()
