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
from app.database.models import LicensingState, User
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


def test_scrub_secrets():
    out = scrub_secrets("BORG_PASSPHRASE=hunter2 borg create ssh://me@nas.local/./repo")
    assert "hunter2" not in out and "ssh://me@nas.local/./repo" in out


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
