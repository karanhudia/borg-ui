import logging
import subprocess
import sys
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
