import logging
import subprocess
import sys
import time
from pathlib import Path

import pytest
import structlog

import app.main  # noqa: F401  installs the log redaction like production does
from app.utils.redaction import install_log_redaction, redact_secrets

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
@pytest.mark.parametrize(
    "text, expected",
    [
        ("redis://:secret@cache:6379/0", "redis://:***@cache:6379/0"),
        ("rediss://user:secret@cache:6379/0", "rediss://user:***@cache:6379/0"),
        ("redis://:p@ss:w@cache:6379/0", "redis://:***@cache:6379/0"),
        ("redis://cache:6379/0", "redis://cache:6379/0"),
        ("http://token@srv/store", "http://***@srv/store"),
        ("ssh://borg@host:22/./repo", "ssh://borg@host:22/./repo"),
        ("borg@host:repo", "borg@host:repo"),
        (
            "connect to rest:http://u:pw@srv:8000/r failed",
            "connect to rest:http://u:***@srv:8000/r failed",
        ),
        (
            "PUT /cache/settings?redis_url=redis%3A%2F%2F%3Apw%40cache%3A6379 200",
            "PUT /cache/settings?redis_url=redis%3A%2F%2F%3A***%40cache%3A6379 200",
        ),
        (
            "redis://cache:6379/0?password=secret&db=0",
            "redis://cache:6379/0?password=***&db=0",
        ),
        (
            "PUT /cache/settings?redis_url=redis%3A%2F%2Fcache%3Fpassword%3Dsecret",
            "PUT /cache/settings?redis_url=redis%3A%2F%2Fcache%3Fpassword%3D***",
        ),
        ("BORG_PASSPHRASE=hunter2 borg list", "BORG_PASSPHRASE=*** borg list"),
        (
            "AWS_SECRET_ACCESS_KEY=wJalr/K7 aws s3 ls",
            "AWS_SECRET_ACCESS_KEY=*** aws s3 ls",
        ),
        ('{"password": "two words, and more"}', '{"password": "***"}'),
        ("password='a b' user=x", "password='***' user=x"),
        ('{"password_set": false}', '{"password_set": false}'),
        (
            """BORG_PASSPHRASE='a'"'"'b c' borg list""",
            "BORG_PASSPHRASE='***' borg list",
        ),
        (
            "rclone lsd --s3-secret-access-key XYZ --s3-region eu",
            "rclone lsd --s3-secret-access-key *** --s3-region eu",
        ),
        ("password=*** already", "password=*** already"),
        ("-https://u:pw@host/x", "-https://u:***@host/x"),
        ('redis://c:6379?password="hunter2', 'redis://c:6379?password="***'),
        ('redis://c:6379?password="hunter2&db=0', 'redis://c:6379?password="***&db=0'),
        ('password="hunter2 and the rest', 'password="***'),
        ('redis://c:6379?password="a&b?c"&db=0', 'redis://c:6379?password="***"&db=0'),
        ("redis://c:6379?password=ab?cd&db=0", "redis://c:6379?password=***&db=0"),
        ('redis://c?password=ab"cd&db=0', "redis://c?password=***&db=0"),
        ("redis://c:6379?password= hunter2&db=0", "redis://c:6379?password=***&db=0"),
        (
            '"PUT /api?password=abc HTTP/1.1" 200',
            '"PUT /api?password=***" 200',
        ),
        ('password=ab"cd and more', "password=*** and more"),
        ('{"url": "redis://c?password=x"}', '{"url": "redis://c?password=***"}'),
        ('{"event": "x password=ab", "k": 1}', '{"event": "x password=***", "k": 1}'),
        ('redis://c?password="a\\"b"&db=0', 'redis://c?password="***"&db=0'),
        ("""redis://c?password='a'"'"'b'&db=0""", "redis://c?password='***'&db=0"),
        ("redis://c:6379?pass%77ord=ab?cd&db=0", "redis://c:6379?pass%77ord=***&db=0"),
        (
            "/login?next=redis://c:6379?pass%77ord=hunter2&x=1",
            "/login?next=redis://c:6379?pass%77ord=***&x=1",
        ),
        # a trailing backslash does not pull the next log line into the value
        ('password="abc\\\nnext line', 'password="***\\\nnext line'),
        ("+ssh://borg@host/repo", "+ssh://borg@host/repo"),
        ("{'password': 'hunter2', 'user': 'a'}", "{'password': '***', 'user': 'a'}"),
        (
            'redis://c:6379?password="hunter 2"&db=0',
            'redis://c:6379?password="***"&db=0',
        ),
        (
            """{'password': 'it\\'s "x"', 'user': 'a'}""",
            """{'password': '***', 'user': 'a'}""",
        ),
        (
            '/login?next="redis://c:6379?pass%77ord=hunter2"&x=1',
            '/login?next="redis://c:6379?pass%77ord=***"&x=1',
        ),
        (
            "redis://cache:6379/0?pass%77ord=hunter2&db=0",
            "redis://cache:6379/0?pass%77ord=***&db=0",
        ),
        (
            "/login?next=redis://c:6379?pass%77ord=hunter2&x=1",
            "/login?next=redis://c:6379?pass%77ord=***&x=1",
        ),
        ('{"db_password": "hunter2"}', '{"db_password": "***"}'),
        ('{"has_password": true}', '{"has_password": true}'),
        ("api_key=abc123&x=1", "api_key=***&x=1"),
        (None, None),
        ("", ""),
    ],
)
def test_redact_secrets(text, expected):
    assert redact_secrets(text) == expected
    assert redact_secrets(expected) == expected  # idempotent


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "y-" * 50_000,
        "a" * 100_000,
        "a." * 50_000,
        "http" * 25_000,
        "password" * 12_500,
        "?a" * 50_000,
        "'" * 100_000,
        "x" * 50_000 + " password=abc " + "y-" * 25_000,
        '?a="' * 25_000,
        'password="' * 10_000,
        "?a=" * 30_000,
        "?password=" * 10_000,
        'password=a"b' * 10_000,
        "password='" * 10_000,
    ],
    ids=[
        "dashed-run",
        "word",
        "dotted",
        "schemes",
        "keys",
        "query",
        "quotes",
        "mixed",
        "unterminated-query",
        "unterminated-double",
        "unterminated-single",
        "nested-queries",
        "secret-queries",
        "inner-quotes",
    ],
)
def test_redaction_stays_linear_on_large_lines(text):
    """Every log line goes through this; a backtracking pattern turns one big
    line of borg output into seconds of stalled logging."""
    start = time.perf_counter()
    redact_secrets(text)
    assert time.perf_counter() - start < 0.5


@pytest.mark.unit
def test_config_import_installs_log_redaction():
    """app.config is the first app module every entry point imports, so the
    hook is in place before import-time work (the archive cache) can log.
    A fresh interpreter, so nothing else has installed it first."""
    check = (
        "import logging, app.config; "
        "assert logging.getLogRecordFactory().redacts_secrets"
    )
    subprocess.run([sys.executable, "-c", check], check=True, cwd=REPO_ROOT)


@pytest.mark.unit
def test_app_installs_log_redaction():
    assert getattr(logging.getLogRecordFactory(), "redacts_secrets", False)
    install_log_redaction()  # idempotent: no second wrapper
    assert logging.getLogRecordFactory().redacts_secrets


@pytest.mark.unit
def test_every_logger_is_redacted_without_call_site_help(caplog):
    url = "redis://:hunter2@cache:6379/0"
    caplog.set_level(logging.INFO)

    structlog.get_logger().info("saved", changes={"redis_url": {"new": url}})
    logging.getLogger("plain").info(f"Reconfigured (URL: {url})")
    logging.getLogger("args").info("url=%s", url)
    try:
        raise ConnectionError(f"cannot reach {url}")
    except ConnectionError:
        logging.getLogger("exc").exception("failed")

    assert caplog.records
    assert "hunter2" not in caplog.text
    assert "redis://:***@cache:6379/0" in caplog.text
