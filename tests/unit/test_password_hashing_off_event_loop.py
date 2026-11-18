"""Password checks and hashing must not hold the event loop.

A bcrypt comparison or hash takes about 175 ms at the default cost. In a
coroutine handler it ran on the loop, and every other request of the process
waited for it.

A stand-in for `verify_password` or `get_password_hash` stops at a gate until
the test opens it, and /health must answer meanwhile. With the call back on
the loop, the gate runs out after HOLD_SECONDS and the test fails instead of
hanging. No test depends on how long anything takes.

The routes write (rate-limit buckets, auth events, users, tokens), so they run
on SQLite and, with BORG_TEST_POSTGRES_URL set, on PostgreSQL.
"""

import asyncio
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker

import app.api.auth as auth
import app.api.managed_machines as managed_machines
import app.api.settings as settings_api
from app.config import settings
from app.core import security
from app.core.security import (
    create_access_token,
    create_login_challenge_token,
    encrypt_secret,
)
from app.core.totp import _hotp, generate_totp_secret, hash_recovery_code
from app.database.database import Base, get_db, register_utc_session_timezone
from app.database.models import (
    AgentEnrollmentToken,
    AuthEvent,
    AuthRateLimitBucket,
    LicensingState,
    User,
)

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
PASSWORD = "admin123"
NEW_PASSWORD = "a-new-password-1"
RESET_PASSWORD = "a-reset-password-2"
RECOVERY_CODE = "ABCD-EFGH-JKLM"
# Long enough for a request to arrive, short enough that a call held on the
# loop fails the test instead of hanging it.
HOLD_SECONDS = 5


@contextmanager
def _postgres_sessions():
    """A schema of its own: the other PostgreSQL tests drop `public`."""
    schema = f"password_hashing_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        POSTGRES_URL, connect_args={"options": f"-c search_path={schema}"}
    )
    register_utc_session_timezone(engine)
    try:
        Base.metadata.create_all(engine)
        yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
            ),
        ),
    ]
)
def database(request, test_client, session_per_request):
    """The session factory of the database the requests of this test use: for
    the test's setup and assertions, one session per request for the app."""
    if request.param == "sqlite":
        yield session_per_request
        return

    from app.main import app

    with _postgres_sessions() as sessions:

        def override_get_db():
            db = sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        with patch("app.database.database.SessionLocal", sessions):
            yield sessions


@pytest.fixture
def admin(database, fixture_password_hashes):
    with database() as db:
        db.add(
            User(
                username="admin",
                email="admin@example.org",
                password_hash=fixture_password_hashes[PASSWORD],
                is_active=True,
                role="admin",
            )
        )
        db.add(
            User(
                username="target",
                email="target@example.org",
                password_hash=fixture_password_hashes[PASSWORD],
                is_active=True,
                role="viewer",
            )
        )
        db.add(
            LicensingState(
                instance_id="test-password-hashing", plan="pro", status="active"
            )
        )
        db.commit()
    return {"Authorization": f"Bearer {create_access_token({'sub': 'admin'})}"}


def _patch_everywhere(monkeypatch, name: str, replacement) -> None:
    """In `security` and in every handler module that imported the name, so
    that the stand-in is called on the code before this change as well."""
    for module in (security, auth, settings_api, managed_machines):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, replacement)


class Gate:
    """Stops the first call that reaches it until the test opens it."""

    def __init__(self) -> None:
        self.reached = threading.Event()
        self.opened_in_time: list[bool] = []
        self._opened = threading.Event()
        self._lock = threading.Lock()
        self._taken = False

    def hold(self) -> None:
        with self._lock:
            if self._taken:
                return
            self._taken = True
        self.reached.set()
        self.opened_in_time.append(self._opened.wait(HOLD_SECONDS))

    def open(self) -> None:
        self._opened.set()


@contextmanager
def _held_request(gate: Gate, send):
    """Runs `send` in a thread until it reaches `gate`; the gate is opened
    and the thread joined again whatever the test does meanwhile."""
    request = threading.Thread(target=send)
    request.start()
    try:
        assert gate.reached.wait(HOLD_SECONDS), "the request never reached the gate"
        yield
    finally:
        gate.open()
        request.join(HOLD_SECONDS * 2)
    assert not request.is_alive()


def _enable_totp(database) -> str:
    secret = generate_totp_secret()
    with database() as db:
        user = db.query(User).filter(User.username == "admin").one()
        user.totp_secret_encrypted = encrypt_secret(secret)
        user.totp_enabled = True
        user.totp_recovery_codes_hashes = json.dumps(
            [hash_recovery_code(RECOVERY_CODE)]
        )
        db.commit()
    return secret


def _target_id(database) -> int:
    with database() as db:
        return db.query(User).filter(User.username == "target").one().id


def _connections_in_use(database):
    """Connections checked out of the pool of the requests' engine; None where
    the tests' engine has no pool that could run out."""
    pool = getattr(database.kw.get("bind"), "pool", None)
    return pool.checkedout() if isinstance(pool, QueuePool) else None


# (case id, function held, request: path, keyword arguments, status, user
# whose password is then NEW_PASSWORD)
ROUTES = [
    (
        "login",
        "verify_password",
        lambda database: (
            "/api/auth/login",
            {"data": {"username": "admin", "password": PASSWORD}},
            200,
            None,
        ),
    ),
    (
        "totp-setup",
        "verify_password",
        lambda database: (
            "/api/auth/totp/setup",
            {"json": {"current_password": PASSWORD}},
            200,
            None,
        ),
    ),
    (
        "totp-disable",
        "verify_password",
        lambda database: (
            "/api/auth/totp/disable",
            {
                "json": {
                    "current_password": PASSWORD,
                    "code": _hotp(_enable_totp(database), int(time.time()) // 30),
                }
            },
            200,
            None,
        ),
    ),
    (
        "passkey-options",
        "verify_password",
        lambda database: (
            "/api/auth/passkeys/register/options",
            {"json": {"current_password": PASSWORD}},
            200,
            None,
        ),
    ),
    (
        "auth-change-password-check",
        "verify_password",
        lambda database: (
            "/api/auth/change-password",
            {"json": {"current_password": PASSWORD, "new_password": NEW_PASSWORD}},
            200,
            "admin",
        ),
    ),
    (
        "auth-change-password-hash",
        "get_password_hash",
        lambda database: (
            "/api/auth/change-password",
            {"json": {"current_password": PASSWORD, "new_password": NEW_PASSWORD}},
            200,
            "admin",
        ),
    ),
    (
        "auth-create-user",
        "get_password_hash",
        lambda database: (
            "/api/auth/users",
            {"json": {"username": "created", "password": NEW_PASSWORD}},
            200,
            "created",
        ),
    ),
    (
        "settings-create-user",
        "get_password_hash",
        lambda database: (
            "/api/settings/users",
            {
                "json": {
                    "username": "created",
                    "password": NEW_PASSWORD,
                    "email": "created@example.org",
                }
            },
            200,
            "created",
        ),
    ),
    (
        "settings-reset-password",
        "get_password_hash",
        lambda database: (
            f"/api/settings/users/{_target_id(database)}/reset-password",
            {"json": {"new_password": NEW_PASSWORD}},
            200,
            "target",
        ),
    ),
    (
        "settings-change-password-check",
        "verify_password",
        lambda database: (
            "/api/settings/change-password",
            {"json": {"current_password": PASSWORD, "new_password": NEW_PASSWORD}},
            200,
            "admin",
        ),
    ),
    (
        "settings-change-password-hash",
        "get_password_hash",
        lambda database: (
            "/api/settings/change-password",
            {"json": {"current_password": PASSWORD, "new_password": NEW_PASSWORD}},
            200,
            "admin",
        ),
    ),
    (
        "enrollment-token",
        "get_password_hash",
        lambda database: (
            "/api/managed-machines/enrollment-tokens",
            {"json": {"name": "agent", "expires_in_minutes": 60}},
            201,
            None,
        ),
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("held", "route"),
    [(held, route) for _, held, route in ROUTES],
    ids=[case for case, _, _ in ROUTES],
)
def test_the_loop_answers_while_a_password_is_checked_or_hashed(
    test_client, database, admin, monkeypatch, held, route
):
    path, request_kwargs, expected_status, changed_user = route(database)
    gate = Gate()
    real = getattr(security, held)

    def held_call(*args):
        gate.hold()
        return real(*args)

    _patch_everywhere(monkeypatch, held, held_call)

    outcomes: list = []

    def send() -> None:
        try:
            response = test_client.post(path, headers=admin, **request_kwargs)
            outcomes.append(response.status_code)
        except Exception as exc:
            outcomes.append(repr(exc))

    with _held_request(gate, send):
        health = test_client.get("/health")
        in_use = _connections_in_use(database)

    assert health.status_code == 200
    # The call was still held when /health came back: it did not need the
    # call to end first.
    assert gate.opened_in_time == [True]
    assert outcomes == [expected_status]
    # Nor does the request hold a pooled connection while it waits, except a
    # login, whose thread checks the password of the user it has just read.
    if in_use is not None:
        assert in_use == (1 if path == "/api/auth/login" else 0)
    if changed_user is not None:
        with database() as db:
            user = db.query(User).filter(User.username == changed_user).one()
            assert security.verify_password(NEW_PASSWORD, user.password_hash)


@pytest.mark.unit
def test_password_logins_take_turns_from_the_rate_limit_check_to_the_record(
    test_client, database, admin, monkeypatch
):
    """On the loop, a login ran from its rate-limit check to the record of
    its failure without a break, so a burst of guesses was cut off after
    `max_attempts`. With the password check in a thread, the logins of a
    burst would all pass the check first, and each would get its answer."""
    max_attempts = 3
    logins = 6
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", max_attempts)

    lock = threading.Lock()
    asked = [0]
    all_asked = threading.Event()
    real_turn = auth._password_login_turn

    class CountedTurn:
        """The login's turn, counting the logins that asked for one."""

        def __init__(self) -> None:
            self._turn = real_turn()

        async def __aenter__(self):
            with lock:
                asked[0] += 1
                if asked[0] == logins:
                    all_asked.set()
            await self._turn.acquire()

        async def __aexit__(self, *exc_info):
            self._turn.release()

    monkeypatch.setattr(auth, "_password_login_turn", CountedTurn)

    checks = {"calls": 0, "inside": 0, "most_at_once": 0}
    all_asked_in_time: list[bool] = []
    real_verify = security.verify_password

    def counted_check(plain, hashed):
        with lock:
            checks["calls"] += 1
            checks["inside"] += 1
            checks["most_at_once"] = max(checks["most_at_once"], checks["inside"])
            first = checks["calls"] == 1
        try:
            if first:
                # Every other login is waiting for its turn by now, or, had
                # they no turns to wait for, checking its password as well.
                all_asked_in_time.append(all_asked.wait(HOLD_SECONDS))
            return real_verify(plain, hashed)
        finally:
            with lock:
                checks["inside"] -= 1

    _patch_everywhere(monkeypatch, "verify_password", counted_check)

    def guess(number: int):
        response = test_client.post(
            "/api/auth/login",
            data={"username": "admin", "password": f"wrong-{number}"},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=logins) as pool:
        codes = sorted(pool.map(guess, range(logins)))

    assert all_asked_in_time == [True]
    assert checks["most_at_once"] == 1
    assert checks["calls"] == max_attempts
    assert codes == [401] * (max_attempts - 1) + [429] * (logins - max_attempts + 1)
    with database() as db:
        buckets = db.query(AuthRateLimitBucket).all()
        assert sorted(bucket.failure_count for bucket in buckets) == [max_attempts] * 2
        assert all(bucket.locked_until is not None for bucket in buckets)
        events = sorted(event.event_type for event in db.query(AuthEvent).all())
        assert events == ["local_login_failed"] * (max_attempts - 1) + [
            "local_login_rate_limited"
        ]


CREATIONS = [
    pytest.param(
        "/api/auth/users",
        {"username": "twin", "password": NEW_PASSWORD},
        auth,
        "_resolve_legacy_role",
        {
            "username": "backend.errors.auth.usernameAlreadyRegistered",
            "email": "backend.errors.auth.emailAlreadyRegistered",
        },
        id="auth",
    ),
    pytest.param(
        "/api/settings/users",
        {"username": "twin", "password": NEW_PASSWORD, "email": None},
        settings_api,
        "default_repository_role_for_global_role",
        {
            "username": "backend.errors.settings.usernameAlreadyExists",
            "email": "backend.errors.settings.emailAlreadyExists",
        },
        id="settings",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "body", "module", "between_check_and_insert", "refused_keys"),
    CREATIONS,
)
def test_two_creations_take_turns_from_their_checks_to_their_insert(
    test_client,
    database,
    admin,
    monkeypatch,
    path,
    body,
    module,
    between_check_and_insert,
    refused_keys,
):
    """Two creations of one username hash at the same time. The first past
    its checks waits there until the second either waits for its turn or,
    with no turns, is past its own checks as well; the latter fails."""
    both_hashing = threading.Barrier(2, timeout=HOLD_SECONDS)
    real_hash = security.get_password_hash
    real_between = getattr(module, between_check_and_insert)
    real_turn = module.user_creation_turn
    second_ready = threading.Event()
    released_by: list[str] = []
    count_lock = threading.Lock()
    counts = {"turns": 0, "checked": 0}

    def ready(by: str) -> None:
        if not second_ready.is_set():
            released_by.append(by)
            second_ready.set()

    class WatchedTurn:
        def __enter__(self):
            with count_lock:
                counts["turns"] += 1
                if counts["turns"] == 2:
                    ready("the second waiting for its turn")
            return real_turn.__enter__()

        def __exit__(self, *exc):
            return real_turn.__exit__(*exc)

    def meeting_hash(password):
        both_hashing.wait()
        return real_hash(password)

    def after_the_check(*args, **kwargs):
        with count_lock:
            counts["checked"] += 1
            first = counts["checked"] == 1
            if not first:
                ready("the second past its checks")
        if first:
            assert second_ready.wait(HOLD_SECONDS), "the second request never came"
        return real_between(*args, **kwargs)

    _patch_everywhere(monkeypatch, "get_password_hash", meeting_hash)
    monkeypatch.setattr(module, between_check_and_insert, after_the_check)
    monkeypatch.setattr(module, "user_creation_turn", WatchedTurn())

    def create(_):
        try:
            return test_client.post(path, headers=admin, json=body)
        except Exception as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, range(2)))

    assert released_by == ["the second waiting for its turn"]
    codes = sorted(str(getattr(r, "status_code", r)) for r in responses)
    assert codes == ["200", "400"]
    refused = next(r for r in responses if r.status_code == 400)
    assert refused.json()["detail"]["key"] == refused_keys["username"]
    with database() as db:
        assert db.query(User).filter(User.username == "twin").count() == 1


@pytest.mark.unit
@pytest.mark.parametrize("taken", ["username", "email"])
@pytest.mark.parametrize(
    ("path", "body", "module", "between_check_and_insert", "refused_keys"),
    CREATIONS,
)
def test_a_creation_is_refused_when_an_update_took_its_name_after_the_checks(
    test_client,
    database,
    admin,
    monkeypatch,
    path,
    body,
    module,
    between_check_and_insert,
    refused_keys,
    taken,
):
    """Account updates do not take the creations' turn: one that takes the
    username or email between a creation's checks and its insert makes the
    insert fail on the unique key, which answers as the check would have."""
    body = {**body, "email": "twin@example.com"}
    real_between = getattr(module, between_check_and_insert)

    def update_after_the_check(*args, **kwargs):
        with database() as db:
            target = db.query(User).filter(User.username == "target").one()
            if taken == "username":
                target.username = body["username"]
            else:
                target.email = body["email"]
            db.commit()
        return real_between(*args, **kwargs)

    monkeypatch.setattr(module, between_check_and_insert, update_after_the_check)

    response = test_client.post(path, headers=admin, json=body)

    assert response.status_code == 400
    assert response.json()["detail"]["key"] == refused_keys[taken]
    with database() as db:
        assert db.query(User).filter(User.email == body["email"]).count() == (
            1 if taken == "email" else 0
        )
        assert db.query(User).filter(User.username == body["username"]).count() == (
            1 if taken == "username" else 0
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "body", "changed_user"),
    [
        (
            "/api/auth/users",
            {"username": "created", "password": NEW_PASSWORD},
            "created",
        ),
        (
            "/api/settings/users",
            {"username": "created", "password": NEW_PASSWORD, "email": None},
            "created",
        ),
        (
            "/api/settings/users/{target}/reset-password",
            {"new_password": NEW_PASSWORD},
            "target",
        ),
    ],
    ids=["auth-create", "settings-create", "settings-reset"],
)
def test_an_admin_request_answers_when_its_admin_was_deleted_while_it_hashed(
    test_client, database, admin, monkeypatch, path, body, changed_user
):
    """The commit expires the admin who sent the request; read again after
    it, a deleted admin would turn a done change into an error."""
    path = path.format(target=_target_id(database))
    real_hash = security.get_password_hash

    def hash_while_deleting(password):
        if password == NEW_PASSWORD:
            with database() as db:
                db.delete(db.query(User).filter(User.username == "admin").one())
                db.commit()
        return real_hash(password)

    _patch_everywhere(monkeypatch, "get_password_hash", hash_while_deleting)

    response = test_client.post(path, headers=admin, json=body)

    assert response.status_code == 200
    with database() as db:
        user = db.query(User).filter(User.username == changed_user).one()
        assert security.verify_password(NEW_PASSWORD, user.password_hash)


@pytest.mark.unit
def test_a_reset_answers_not_found_when_its_user_was_deleted_meanwhile(
    test_client, database, admin, monkeypatch
):
    """The reset runs in a thread, so a deletion can commit while it writes.
    The user is deleted when the reset takes its timestamp: on the code
    before this change that was between loading the user and the commit."""
    target_id = _target_id(database)
    real_datetime = settings_api.datetime

    class DeletingDatetime(real_datetime):
        @classmethod
        def utcnow(cls):
            with database() as db:
                target = db.query(User).filter(User.id == target_id).first()
                if target is not None:
                    db.delete(target)
                    db.commit()
            return real_datetime.utcnow()

    monkeypatch.setattr(settings_api, "datetime", DeletingDatetime)

    response = test_client.post(
        f"/api/settings/users/{target_id}/reset-password",
        headers=admin,
        json={"new_password": NEW_PASSWORD},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["key"] == "backend.errors.settings.userNotFound"


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    ["/api/auth/change-password", "/api/settings/change-password"],
    ids=["auth", "settings"],
)
def test_a_password_change_does_not_overwrite_a_reset_made_while_it_hashed(
    test_client, database, admin, monkeypatch, path
):
    """The current password is checked, then the new one is hashed in a
    thread. A reset that lands in between stays: the change is refused as if
    the current password were wrong, which it now is."""
    gate = Gate()
    real_hash = security.get_password_hash

    def held_hash(password):
        if password == NEW_PASSWORD:
            gate.hold()
        return real_hash(password)

    _patch_everywhere(monkeypatch, "get_password_hash", held_hash)
    target = {"Authorization": f"Bearer {create_access_token({'sub': 'target'})}"}
    outcomes: list = []

    def change() -> None:
        outcomes.append(
            test_client.post(
                path,
                headers=target,
                json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            )
        )

    with _held_request(gate, change):
        reset = test_client.post(
            f"/api/settings/users/{_target_id(database)}/reset-password",
            headers=admin,
            json={"new_password": RESET_PASSWORD},
        )

    assert reset.status_code == 200
    assert gate.opened_in_time == [True]
    assert [response.status_code for response in outcomes] == [400]
    assert (
        outcomes[0].json()["detail"]["key"]
        == "backend.errors.auth.currentPasswordIncorrect"
    )
    with database() as db:
        stored = db.query(User).filter(User.username == "target").one()
        assert security.verify_password(RESET_PASSWORD, stored.password_hash)


def _setup_and_enable_totp(test_client, admin) -> tuple[str, list[str]]:
    setup = test_client.post(
        "/api/auth/totp/setup", headers=admin, json={"current_password": PASSWORD}
    )
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    enable = test_client.post(
        "/api/auth/totp/enable",
        headers=admin,
        json={
            "setup_token": setup.json()["setup_token"],
            "code": _hotp(secret, int(time.time()) // 30),
        },
    )
    assert enable.status_code == 200
    return secret, setup.json()["recovery_codes"]


@pytest.mark.unit
@pytest.mark.parametrize("code", ["totp", "recovery"])
def test_disabling_totp_leaves_a_factor_set_up_while_the_password_was_checked(
    test_client, database, admin, monkeypatch, code
):
    """The disable request checks its code against the factor it read before
    the password check. A factor that replaced it meanwhile stays, with its
    recovery codes."""
    old_secret = _enable_totp(database)
    gate = Gate()
    real_verify = security.verify_password

    def held_check(plain, hashed):
        gate.hold()
        return real_verify(plain, hashed)

    _patch_everywhere(monkeypatch, "verify_password", held_check)
    outcomes: list = []

    def disable() -> None:
        outcomes.append(
            test_client.post(
                "/api/auth/totp/disable",
                headers=admin,
                json={
                    "current_password": PASSWORD,
                    "code": (
                        RECOVERY_CODE
                        if code == "recovery"
                        else _hotp(old_secret, int(time.time()) // 30)
                    ),
                },
            )
        )

    with _held_request(gate, disable):
        new_secret, new_codes = _setup_and_enable_totp(test_client, admin)

    assert gate.opened_in_time == [True]
    assert [response.status_code for response in outcomes] == [400]
    with database() as db:
        user = db.query(User).filter(User.username == "admin").one()
        assert user.totp_enabled is True
        assert security.decrypt_secret(user.totp_secret_encrypted) == new_secret
        assert sorted(json.loads(user.totp_recovery_codes_hashes)) == sorted(
            hash_recovery_code(new_code) for new_code in new_codes
        )


@pytest.mark.unit
@pytest.mark.parametrize("change", ["recovery-code-used", "password-changed"])
def test_disabling_totp_is_refused_when_what_it_checked_changed_meanwhile(
    test_client, database, admin, monkeypatch, fixture_password_hashes, change
):
    """A recovery code used up by a TOTP login, or a password changed, while
    the disable request checked the password: the factor stays."""
    _enable_totp(database)
    gate = Gate()
    real_verify = security.verify_password

    def held_check(plain, hashed):
        gate.hold()
        return real_verify(plain, hashed)

    _patch_everywhere(monkeypatch, "verify_password", held_check)
    outcomes: list = []

    def disable() -> None:
        outcomes.append(
            test_client.post(
                "/api/auth/totp/disable",
                headers=admin,
                json={"current_password": PASSWORD, "code": RECOVERY_CODE},
            )
        )

    with _held_request(gate, disable):
        with database() as db:
            user = db.query(User).filter(User.username == "admin").one()
            if change == "recovery-code-used":
                user.totp_recovery_codes_hashes = json.dumps([])
            else:
                user.password_hash = fixture_password_hashes["operator123"]
            db.commit()

    assert gate.opened_in_time == [True]
    assert [response.status_code for response in outcomes] == [400]
    with database() as db:
        user = db.query(User).filter(User.username == "admin").one()
        assert user.totp_enabled is True
        assert user.totp_secret_encrypted is not None


@pytest.mark.unit
def test_disabling_totp_with_a_recovery_code_clears_every_code(
    test_client, database, admin
):
    _enable_totp(database)
    response = test_client.post(
        "/api/auth/totp/disable",
        headers=admin,
        json={"current_password": PASSWORD, "code": RECOVERY_CODE},
    )
    assert response.status_code == 200
    with database() as db:
        user = db.query(User).filter(User.username == "admin").one()
        assert user.totp_enabled is False
        assert user.totp_secret_encrypted is None
        assert user.totp_recovery_codes_hashes is None


@pytest.mark.unit
def test_a_login_asks_for_a_second_factor_enabled_while_its_password_was_checked(
    test_client, database, admin, monkeypatch
):
    """On the loop, a login read the user and issued its token without a
    break. Its password check now runs in a thread: the user is read again
    after it, so a factor enabled meanwhile is asked for."""
    gate = Gate()
    real_verify = security.verify_password

    def held_check(plain, hashed):
        gate.hold()
        return real_verify(plain, hashed)

    _patch_everywhere(monkeypatch, "verify_password", held_check)
    outcomes: list = []

    def log_in() -> None:
        outcomes.append(
            test_client.post(
                "/api/auth/login", data={"username": "admin", "password": PASSWORD}
            )
        )

    with _held_request(gate, log_in):
        _setup_and_enable_totp(test_client, admin)

    assert gate.opened_in_time == [True]
    assert [response.status_code for response in outcomes] == [200]
    body = outcomes[0].json()
    assert body["totp_required"] is True
    assert not body.get("access_token")


@pytest.mark.unit
def test_a_login_fails_when_the_password_changed_while_it_was_checked(
    test_client, database, admin, monkeypatch, fixture_password_hashes
):
    gate = Gate()
    real_verify = security.verify_password

    def held_check(plain, hashed):
        gate.hold()
        return real_verify(plain, hashed)

    _patch_everywhere(monkeypatch, "verify_password", held_check)
    outcomes: list = []

    def log_in() -> None:
        outcomes.append(
            test_client.post(
                "/api/auth/login", data={"username": "admin", "password": PASSWORD}
            )
        )

    with _held_request(gate, log_in):
        with database() as db:
            user = db.query(User).filter(User.username == "admin").one()
            user.password_hash = fixture_password_hashes["operator123"]
            db.commit()

    assert gate.opened_in_time == [True]
    assert [response.status_code for response in outcomes] == [401]


@pytest.mark.unit
def test_a_login_fails_when_the_user_was_deleted_while_it_was_checked(
    test_client, database, admin, monkeypatch
):
    gate = Gate()
    real_verify = security.verify_password

    def held_check(plain, hashed):
        gate.hold()
        return real_verify(plain, hashed)

    _patch_everywhere(monkeypatch, "verify_password", held_check)
    outcomes: list = []

    def log_in() -> None:
        outcomes.append(
            test_client.post(
                "/api/auth/login", data={"username": "target", "password": PASSWORD}
            )
        )

    with _held_request(gate, log_in):
        with database() as db:
            db.delete(db.query(User).filter(User.username == "target").one())
            db.commit()

    assert gate.opened_in_time == [True]
    assert [response.status_code for response in outcomes] == [401]


@pytest.mark.unit
def test_a_login_keeps_the_second_factor_it_read_with_the_password(
    test_client, database, admin, monkeypatch
):
    """A failed attempt before leaves a bucket, so the rate-limit cleanup of
    the login commits; the user would be read again after it. A factor
    disabled at that moment does not let the password alone through."""
    _enable_totp(database)
    failed = test_client.post(
        "/api/auth/login", data={"username": "admin", "password": "wrong"}
    )
    assert failed.status_code == 401
    real_clear = auth.clear_auth_rate_limit

    def clear_while_disabling(db, **kwargs):
        with database() as other:
            user = other.query(User).filter(User.username == "admin").one()
            user.totp_enabled = False
            user.totp_secret_encrypted = None
            user.totp_recovery_codes_hashes = None
            other.commit()
        return real_clear(db, **kwargs)

    monkeypatch.setattr(auth, "clear_auth_rate_limit", clear_while_disabling)

    response = test_client.post(
        "/api/auth/login", data={"username": "admin", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["totp_required"] is True
    assert not response.json().get("access_token")


@pytest.mark.unit
@pytest.mark.parametrize("change", ["totp-disabled", "code-used"])
def test_a_totp_login_with_a_recovery_code_is_refused_when_the_codes_changed(
    test_client, database, admin, monkeypatch, change
):
    """The login uses its recovery code up only while the factor and its codes
    are the ones it checked: a disable (it runs in a thread) or another login
    with the same code may have committed meanwhile."""
    _enable_totp(database)
    real_verify = auth._verify_totp_or_recovery_code

    def verify_while_changing(user, code):
        verified = real_verify(user, code)
        with database() as other:
            stored = other.query(User).filter(User.username == "admin").one()
            if change == "totp-disabled":
                stored.totp_enabled = False
                stored.totp_secret_encrypted = None
                stored.totp_recovery_codes_hashes = None
            else:
                stored.totp_recovery_codes_hashes = json.dumps([])
            other.commit()
        return verified

    monkeypatch.setattr(auth, "_verify_totp_or_recovery_code", verify_while_changing)

    response = test_client.post(
        "/api/auth/login/totp",
        json={
            "login_challenge_token": create_login_challenge_token("admin"),
            "code": RECOVERY_CODE,
        },
    )

    assert response.status_code == 401
    assert not response.json().get("access_token")
    with database() as db:
        user = db.query(User).filter(User.username == "admin").one()
        if change == "totp-disabled":
            assert user.totp_enabled is False
            assert user.totp_recovery_codes_hashes is None
        else:
            assert user.totp_recovery_codes_hashes == json.dumps([])


@pytest.mark.unit
def test_a_totp_login_uses_its_recovery_code_up(test_client, database, admin):
    _enable_totp(database)
    payload = {
        "login_challenge_token": create_login_challenge_token("admin"),
        "code": RECOVERY_CODE,
    }

    first = test_client.post("/api/auth/login/totp", json=payload)
    again = test_client.post("/api/auth/login/totp", json=payload)

    assert first.status_code == 200
    assert first.json()["access_token"]
    assert again.status_code == 401
    with database() as db:
        user = db.query(User).filter(User.username == "admin").one()
        assert json.loads(user.totp_recovery_codes_hashes) == []


@pytest.mark.unit
async def test_a_cancelled_login_keeps_its_turn_until_its_thread_is_done(
    test_db, fixture_password_hashes, monkeypatch
):
    """Cancelled while its thread checks the password, a login must not let
    the next one start: the two would overlap from the rate-limit check to
    the record, and the request's session would close under the thread."""
    from fastapi.security import OAuth2PasswordRequestForm
    from starlette.requests import Request

    test_db.add(
        User(
            username="admin",
            password_hash=fixture_password_hashes[PASSWORD],
            is_active=True,
            role="admin",
        )
    )
    test_db.commit()
    gate = Gate()
    real_verify = security.verify_password

    def held_check(plain, hashed):
        gate.hold()
        return real_verify(plain, hashed)

    _patch_everywhere(monkeypatch, "verify_password", held_check)
    request = Request(
        {"type": "http", "headers": [], "client": ("192.0.2.1", 1234), "state": {}}
    )
    form = OAuth2PasswordRequestForm(username="admin", password=PASSWORD)
    login = asyncio.create_task(auth.login(request, form, test_db))
    reached = await asyncio.to_thread(gate.reached.wait, HOLD_SECONDS)
    assert reached, "the login never checked its password"

    login.cancel()
    for _ in range(10):
        await asyncio.sleep(0)
    held_after_cancel = auth._password_login_turn().locked()
    gate.open()
    with pytest.raises(asyncio.CancelledError):
        await login

    assert held_after_cancel
    assert gate.opened_in_time == [True]
    assert not auth._password_login_turn().locked()


@pytest.mark.unit
def test_an_enrollment_token_is_stored_with_a_hash_of_itself(
    test_client, database, admin
):
    response = test_client.post(
        "/api/managed-machines/enrollment-tokens",
        headers=admin,
        json={"name": "agent", "expires_in_minutes": 60},
    )
    assert response.status_code == 201
    with database() as db:
        stored = db.get(AgentEnrollmentToken, response.json()["id"])
        assert security.verify_password(response.json()["token"], stored.token_hash)
