import json
import time
from contextlib import contextmanager

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.models import LicensingState, Operation, User
from app.services import error_reporter
from app.services.error_reporter import (
    flush,
    fnv1a64,
    normalize_message,
    report_exception,
    report_failure,
    scrub_secrets,
)


@pytest.fixture(autouse=True)
def _fresh_reporter():
    error_reporter._reset_for_tests()
    yield
    error_reporter._reset_for_tests()


@pytest.fixture
def sent(monkeypatch):
    events = []

    def record(url, data=None, headers=None, timeout=None):
        assert url == "https://t.borgui.com/e"
        assert headers["User-Agent"].startswith("borg-ui-backend/")
        assert timeout == 3
        events.extend(json.loads(data)["events"])

    monkeypatch.setattr(settings, "error_reporting_enabled", True)
    monkeypatch.setattr(requests, "post", record)
    return events


@pytest.fixture
def reporter_db(db_engine, monkeypatch):
    factory = sessionmaker(bind=db_engine)
    monkeypatch.setattr(error_reporter, "SessionLocal", factory)
    session = factory()
    yield session
    session.close()


def test_fnv_matches_frontend():
    assert fnv1a64("") == "cbf29ce484222325"
    assert fnv1a64("a") == "af63dc4c8601ec8c"


def test_normalize_matches_frontend():
    assert (
        normalize_message("Repo '/mnt/backup/photos' id 42 (3f2a9c1d7b) not found")
        == "Repo <str> id <n> (<hex>) not found"
    )
    assert (
        normalize_message(
            "lock 0b6f1e1c-3f0a-4c4e-9a43-2b1e5f8d9c10 at /data/x/y and C:\\Borg\\r"
        )
        == "lock <uuid> at <path> and <path>"
    )


@pytest.mark.parametrize("serialize", [json.dumps, repr])
def test_structured_error_keys_do_not_collide(serialize):
    missing = serialize(
        {
            "key": "backend.errors.repo.repositoryDirNotExist",
            "params": {"path": "/mnt/borg-repository"},
        }
    )
    invalid = serialize(
        {
            "key": "backend.errors.repo.notValidBorgRepository",
            "params": {"path": "/mnt/borg-repository"},
        }
    )
    another_path = serialize(
        {
            "key": "backend.errors.repo.repositoryDirNotExist",
            "params": {"path": "/backups/photos"},
        }
    )

    assert normalize_message(missing) != normalize_message(invalid)
    assert normalize_message(missing) == normalize_message(another_path)
    assert "backend.errors.repo.repositoryDirNotExist" in normalize_message(missing)
    assert "/mnt/borg-repository" not in normalize_message(missing)


def test_distinct_structured_failures_are_not_folded_together(sent):
    for key in ("repositoryDirNotExist", "notValidBorgRepository"):
        report_failure(
            kind="job",
            type_="backup_failed",
            component="backup",
            message=json.dumps(
                {"key": f"backend.errors.repo.{key}", "params": {"path": "/mnt/repo"}}
            ),
        )
    flush()

    assert len(sent) == 2
    assert sent[0]["props"]["fingerprint"] != sent[1]["props"]["fingerprint"]


def test_scrub_secrets():
    out = scrub_secrets("BORG_PASSPHRASE=hunter2 borg create ssh://me@nas.local/./repo")
    assert "hunter2" not in out and "ssh://me@nas.local/./repo" in out


def test_cleanup_memory_addresses_share_a_fingerprint(sent):
    for address in ("0x1541083437e0", "0x14ac9995f7e0"):
        report_failure(
            kind="job",
            type_="archive_sync_failed",
            component="archive_sync",
            message=f"Exception ignored in: <function Repository.__del__ at {address}>",
        )
    flush()
    assert len(sent) == 1


@pytest.mark.parametrize(
    "padding", ["", "  intermediate frame\n" * 80], ids=["summary", "detail"]
)
def test_bare_basic_credentials_are_redacted_before_details_and_fingerprinting(
    sent, padding
):
    tokens = ("YWxpY2U6c2VjcmV0", "Ym9iOm90aGVyc2VjcmV0", "YTpi")
    for token in tokens:
        report_failure(
            kind="job",
            type_="rclone_sync_failed",
            component="rclone_sync",
            message=f"rclone failed\n{padding}OSError: Basic {token}",
        )
    flush()

    assert len(sent) == 1
    props = sent[0]["props"]
    for token in tokens:
        assert token not in json.dumps(props)
    detail = props["stack"] if padding else props["message"]
    assert "OSError: Basic [redacted]" in detail


@pytest.mark.parametrize("long_detail", [False, True])
@pytest.mark.parametrize(
    "url,secret",
    [
        ("https://alice:demo-url-secret@storage.example/repo", "demo-url-secret"),
        ("https://demo-bare-token@storage.example/repo", "demo-bare-token"),
        (
            "https%3A%2F%2Falice%3Ademo-encoded-secret%40storage.example/repo",
            "demo-encoded-secret",
        ),
    ],
)
def test_handled_failure_redacts_url_credentials_before_telemetry(
    sent, long_detail, url, secret
):
    from app.services.operations.runner import _report_failed_operation

    message = f"rclone failed at {url}\n"
    if long_detail:
        message += "  intermediate frame\n" * 80
    message += f"OSError: unable to access {url}"
    _report_failed_operation(
        Operation(kind="rclone_sync", status="failed", error_message=message), None
    )
    flush()

    props = sent[0]["props"]
    assert props["handled"] is True
    assert secret not in json.dumps(props)
    assert "storage.example/repo" in props["message"]
    if long_detail:
        assert "OSError: unable to access" in props["stack"]
        assert "storage.example/repo" in props["stack"]
    else:
        assert "stack" not in props


def test_long_handled_failure_keeps_inspectable_redacted_diagnostics(sent):
    from app.core.borg_errors import ArchiveListingError
    from app.services.operations.runner import _report_failed_operation

    message = str(
        ArchiveListingError(
            {
                "return_code": 2,
                "stderr": "Traceback\n"
                + "  frame\n" * 400
                + "PermissionError: cannot open config BORG_PASSPHRASE=hunter2",
            }
        )
    )
    _report_failed_operation(
        Operation(kind="archive_sync", status="failed", error_message=message), None
    )
    flush()

    props = sent[0]["props"]
    assert props["handled"] is True
    assert len(props["message"]) <= 500
    assert "PermissionError: cannot open config" in props["stack"]
    assert len(props["stack"]) <= 8192
    assert "hunter2" not in json.dumps(props)


def test_scrub_secrets_matches_frontend():
    out = scrub_secrets(
        "BORG_PASSPHRASE=hunter2 borg create ssh://me@nas.local/./repo "
        "Authorization: Bearer abc.def"
    )
    assert "hunter2" not in out
    assert "abc.def" not in out
    assert "ssh://me@nas.local/./repo" in out
    assert (
        scrub_secrets(
            "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----"
        )
        == "[redacted]"
    )


def test_scrub_secrets_other_shapes():
    text = (
        "BORG_NEW_PASSPHRASE='new one' password=pw1 api_key=k1 token=t1 secret=s1 "
        "pass=p1 headers={'Authorization': 'Bearer b1'}\n"
        "[remote]\ntype = s3\nsecret_access_key = SAK\n"
        'token = {"access_token":"ya29"}\nclient_secret = CS\npass = P2\n'
        "host nas.local path /srv/repo"
    )
    out = scrub_secrets(text)
    for secret in (
        "new one",
        "pw1",
        "k1",
        "t1",
        "s1",
        "p1",
        "b1",
        "SAK",
        "ya29",
        "CS",
        "P2",
    ):
        assert secret not in out, secret
    assert "type = s3" in out and "nas.local" in out and "/srv/repo" in out


def test_skips_when_a_user_said_no(reporter_db, sent):
    reporter_db.add(User(username="a", password_hash="x", analytics_enabled=False))
    reporter_db.add(User(username="b", password_hash="x", analytics_enabled=True))
    reporter_db.commit()
    report_failure(kind="job", type_="backup_failed", message="x")
    flush()
    assert sent == []


def test_sends_instance_key_when_known(reporter_db, sent):
    reporter_db.add(User(username="a", password_hash="x", analytics_enabled=True))
    reporter_db.add(LicensingState(instance_id="abc"))
    reporter_db.commit()
    report_failure(
        kind="job", type_="backup_failed", message="exit 2", component="backup"
    )
    flush()
    event = sent[0]
    assert event["instance_key"] == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert event["name"] == "Error - Report" and event["source"] == "app"
    assert event["props"] == {
        "origin": "backend",
        "kind": "job",
        "type": "backup_failed",
        "message": "exit 2",
        "fingerprint": fnv1a64("backend|job|backup_failed|backup|exit <n>"),
        "component": "backup",
        "handled": True,
        "count": 1,
    }


def test_sends_without_key_when_db_unreadable(monkeypatch, sent):
    monkeypatch.setattr(
        error_reporter,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(OperationalError("x", {}, None)),
    )
    report_exception(RuntimeError("boom"), kind="startup")
    flush()
    assert "instance_key" not in sent[0] and sent[0]["props"]["kind"] == "startup"


def test_exception_report_shape(sent):
    def explode():
        raise ValueError("bad BORG_PASSPHRASE=hunter2 at /srv/repo")

    try:
        explode()
    except ValueError as exc:
        report_exception(exc, kind="job", component="backup")
    flush()
    props = sent[0]["props"]
    assert props["type"] == "ValueError"
    assert props["handled"] is False
    assert props["component"] == "backup"
    assert "hunter2" not in props["message"] and "hunter2" not in props["stack"]
    assert "/srv/repo" in props["message"]
    assert "Traceback" in props["stack"]


@pytest.mark.parametrize(
    "status_code, handled", [(400, True), (403, True), (500, False)]
)
def test_operation_http_refusal_classification(sent, status_code, handled):
    from app.services.operations.runner import _report_failed_operation

    error = HTTPException(
        status_code=status_code,
        detail={
            "key": "backend.errors.repo.agentBorg2TooOld",
            "params": {"version": "2.0.0b24", "minimum": "2.0.0b25"},
        },
    )
    operation = Operation(
        kind="archive_sync", status="failed", error_message=str(error)
    )

    _report_failed_operation(operation, error)
    flush()

    assert len(sent) == 1
    props = sent[0]["props"]
    assert props["handled"] is handled
    assert props["component"] == "archive_sync"
    assert "agentBorg2TooOld" in props["message"]
    assert "2.0.0b24" in props["message"]
    if handled:
        assert props["type"] == "archive_sync_failed"
        assert "stack" not in props
    else:
        assert props["type"] == "fastapi.exceptions.HTTPException"
        assert "stack" in props


def test_top_frame_is_the_last_app_frame():
    try:
        error_reporter.fnv1a64(None)
    except Exception as exc:
        assert error_reporter._top_frame(exc) == "app.services.error_reporter:fnv1a64"
    assert error_reporter._top_frame(RuntimeError("no traceback")) == ""


def test_send_failure_never_raises_or_blocks(monkeypatch):
    monkeypatch.setattr(settings, "error_reporting_enabled", True)
    monkeypatch.setattr(requests, "post", lambda *a, **k: time.sleep(10))
    start = time.monotonic()
    report_exception(RuntimeError("x"), kind="request")
    assert time.monotonic() - start < 0.1
    start = time.monotonic()
    flush(timeout=0.2)
    assert time.monotonic() - start < 1


def test_send_exception_is_swallowed(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise requests.ConnectionError("down")

    monkeypatch.setattr(settings, "error_reporting_enabled", True)
    monkeypatch.setattr(requests, "post", boom)
    report_failure(kind="job", type_="x_failed", message="x")
    flush()
    assert calls == [1]


def test_flood_control(sent):
    for _ in range(100):
        report_failure(kind="job", type_="backup_failed", message="exit 2")
    flush()
    assert len(sent) == 1


def test_flood_control_folds_repeats_into_count(monkeypatch, sent):
    now = [1000.0]
    monkeypatch.setattr(error_reporter, "_now", lambda: now[0])
    for _ in range(100):
        report_failure(kind="job", type_="backup_failed", message="exit 2")
    now[0] += 600
    report_failure(kind="job", type_="backup_failed", message="exit 2")
    flush()
    assert [e["props"]["count"] for e in sent] == [1, 100]


def test_caps_reports_at_30_per_hour(sent):
    for i in range(50):
        report_failure(kind="job", type_=f"kind{'x' * i}_failed", message="x")
    flush()
    assert len(sent) == 30


def test_long_stack_keeps_the_exception_line(monkeypatch, sent):
    stack = "frame\n" * 20000 + "BORG_PASSPHRASE=hunter2\nRuntimeError: boom\n"
    monkeypatch.setattr(error_reporter, "_format_stack", lambda exc: stack)
    report_exception(RuntimeError("boom"), kind="job")
    flush()
    out = sent[0]["props"]["stack"]
    assert len(out) <= error_reporter.STACK_LIMIT
    assert out.endswith("RuntimeError: boom\n") and "hunter2" not in out


def test_drops_stack_when_props_too_large(monkeypatch, sent):
    # 8192 characters escape to six each in JSON: only non-ASCII can pass the cap
    monkeypatch.setattr(error_reporter, "_format_stack", lambda exc: "\u00e9" * 20000)
    report_exception(RuntimeError("x" * 600), kind="job")
    flush()
    props = sent[0]["props"]
    assert "stack" not in props
    assert len(props["message"]) == 500
    assert len(json.dumps(props, separators=(",", ":"))) <= 16384


def test_disabled_sends_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: calls.append(1))
    report_failure(kind="job", type_="x_failed", message="x")
    flush()
    assert calls == []


@contextmanager
def _test_route(path, endpoint):
    from app.main import app

    app.add_api_route(path, endpoint)
    route = app.router.routes.pop()
    # ahead of the SPA catch-all, which would otherwise match first
    app.router.routes.insert(0, route)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.router.routes.remove(route)


def test_unhandled_request_reports_and_returns_500(test_db, sent):
    def boom():
        raise RuntimeError("kaboom")

    with _test_route("/api/__boom", boom) as client:
        response = client.get("/api/__boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    flush()
    assert sent[0]["props"]["kind"] == "request"
    assert sent[0]["props"]["component"] == "GET /api/__boom"
    assert sent[0]["props"]["status"] == 500


def test_http_500_reports_its_cause_and_keeps_the_response(test_db, sent):
    def wrapped():
        try:
            raise ValueError("db down")
        except ValueError:
            raise HTTPException(status_code=500, detail="Could not list repos")

    with _test_route("/api/__wrapped", wrapped) as client:
        response = client.get("/api/__wrapped")
    assert response.status_code == 500
    assert response.json() == {"detail": "Could not list repos"}
    flush()
    assert len(sent) == 1
    props = sent[0]["props"]
    assert props["type"] == "ValueError" and props["message"] == "db down"
    assert props["component"] == "GET /api/__wrapped"


def test_http_4xx_is_not_reported(test_db, sent):
    def missing():
        raise HTTPException(status_code=404, detail="Not Found")

    with _test_route("/api/__missing", missing) as client:
        response = client.get("/api/__missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    flush()
    assert sent == []


def test_repository_http_failure_preserves_status_and_reason_with_cause(test_db, sent):
    detail = {
        "key": "backend.errors.repo.failedToInitializeRepository",
        "params": {"error": "private repository details"},
    }

    def wrapped(repo_id: int):
        try:
            raise ValueError("borg initialization failed")
        except ValueError:
            raise HTTPException(status_code=502, detail=detail)

    with _test_route("/api/__repositories/{repo_id}", wrapped) as client:
        response = client.get("/api/__repositories/123?passphrase=private-input")

    assert response.status_code == 502
    assert response.json() == {"detail": detail}
    flush()
    assert len(sent) == 1
    props = sent[0]["props"]
    assert props["type"] == "ValueError"
    assert props["status"] == 502
    assert props["error_key"] == "repo.failedToInitializeRepository"
    assert props["component"] == "GET /api/__repositories/{repo_id}"
    assert "private repository details" not in json.dumps(props)
    assert "private-input" not in json.dumps(props)


@pytest.mark.parametrize(
    "detail",
    [
        "private details",
        {"key": "private details"},
        {"key": 42},
        {"key": "backend.errors.repo.private/path"},
        {"key": "backend.errors." + "x" * 200},
    ],
)
def test_http_failure_omits_unstructured_reason_keys(test_db, sent, detail):
    def wrapped():
        try:
            raise RuntimeError("failed")
        except RuntimeError:
            raise HTTPException(status_code=500, detail=detail)

    with _test_route("/api/__bad_reason", wrapped) as client:
        response = client.get("/api/__bad_reason")
    assert response.status_code == 500
    flush()
    assert "error_key" not in sent[0]["props"]


def test_fingerprint_does_not_depend_on_secrets(sent):
    report_failure(kind="job", type_="x_failed", message="BORG_PASSPHRASE=a failed")
    report_failure(kind="job", type_="x_failed", message="BORG_PASSPHRASE=bbbb failed")
    try:
        raise RuntimeError("Authorization: Bearer one")
    except RuntimeError as exc:
        first = exc
    try:
        raise RuntimeError("Authorization: Bearer two")
    except RuntimeError as exc:
        second = exc
    report_exception(first, kind="request")
    report_exception(second, kind="request")
    flush()
    # the second of each pair is folded into the first: same fingerprint
    assert len(sent) == 2


def test_scrub_caps_its_input():
    out = scrub_secrets("-" * 200_000 + " token=t1")
    assert len(out) <= error_reporter.SCRUB_INPUT_LIMIT


def test_scrub_is_linear_on_long_hyphenated_runs():
    # an unbounded name prefix took about a minute on this input
    start = time.monotonic()
    scrub_secrets("a-" * 32768)
    assert time.monotonic() - start < 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", ["ensure_schema", "after_schema"])
async def test_startup_failure_is_sent_before_the_process_exits(
    monkeypatch, sent, failing
):
    # no flush() here: startup_event itself has to wait for the send
    import app.database.db_upgrade as db_upgrade
    import app.main as main

    async def fine_after_schema():
        pass

    async def broken_after_schema():
        raise RuntimeError("startup broke")

    def broken_schema():
        raise RuntimeError("no such table: users")

    monkeypatch.setattr(
        db_upgrade,
        "ensure_schema",
        broken_schema if failing == "ensure_schema" else lambda: None,
    )
    monkeypatch.setattr(
        main,
        "_startup_after_schema",
        broken_after_schema if failing == "after_schema" else fine_after_schema,
    )
    with pytest.raises(RuntimeError):
        await main.startup_event()
    expected = (
        ("migration", "ensure_schema")
        if failing == "ensure_schema"
        else ("startup", "startup_event")
    )
    assert [(e["props"]["kind"], e["props"]["component"]) for e in sent] == [expected]


def test_flush_is_bounded_and_never_raises(monkeypatch):
    monkeypatch.setattr(settings, "error_reporting_enabled", True)
    monkeypatch.setattr(requests, "post", lambda *a, **k: time.sleep(10))
    report_failure(kind="startup", type_="x", message="x")
    start = time.monotonic()
    flush()
    assert 2.5 < time.monotonic() - start < 4
    monkeypatch.setattr(error_reporter, "_queue", None)
    flush()


def test_an_opt_out_applies_without_waiting_for_the_cache(reporter_db, sent):
    user = User(username="a", password_hash="x", analytics_enabled=True)
    reporter_db.add(user)
    reporter_db.commit()
    report_failure(kind="job", type_="backup_failed", message="first")
    flush()
    assert len(sent) == 1

    user.analytics_enabled = False
    reporter_db.commit()
    error_reporter.invalidate_consent_cache()
    report_failure(kind="job", type_="backup_failed", message="second")
    flush()
    assert len(sent) == 1


def test_a_read_overtaken_by_an_opt_out_is_not_cached(monkeypatch):
    class Session:
        def query(self, *a):
            # the preference changes while this read is in flight
            error_reporter.invalidate_consent_cache()
            raise RuntimeError("stale read")

        def close(self):
            pass

    monkeypatch.setattr(error_reporter, "SessionLocal", Session)
    assert error_reporter._consent() == (True, None)
    assert error_reporter._consent_cache is None


def test_only_production_outside_ci_reports():
    from app.config import error_reporting_allowed

    assert error_reporting_allowed("production", {}) is True
    assert error_reporting_allowed("development", {}) is False
    assert error_reporting_allowed("production", {"CI": "true"}) is False
