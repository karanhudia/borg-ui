"""The application must arrive with a usable schema however it was started.

The container entrypoint prepares the database, but `uvicorn app.main:app` does
not go through it. Without this, such a start comes up against an empty
database and every request that reads from it fails — which is what the smoke
tests caught.
"""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, inspect, text

from app.database import db_upgrade


@pytest.fixture
def sqlite_url(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    monkeypatch.setattr(db_upgrade.settings, "database_url", url, raising=False)
    return url


def table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return set(inspect(conn).get_table_names())
    finally:
        engine.dispose()


def test_builds_the_schema_when_the_database_is_empty(sqlite_url):
    assert table_names(sqlite_url) == set()

    db_upgrade.ensure_schema()

    names = table_names(sqlite_url)
    assert "users" in names, "the login path needs this on the very first request"
    assert "alembic_version" in names
    assert len(names) > 40


def test_does_nothing_when_the_schema_is_current(sqlite_url):
    db_upgrade.ensure_schema()
    before = table_names(sqlite_url)

    # A second start must not rebuild anything; _upgrade_to_head would raise on
    # an existing schema, so reaching it at all is the failure.
    db_upgrade.ensure_schema()

    assert table_names(sqlite_url) == before


def test_leaves_a_pre_alembic_database_alone(sqlite_url, caplog):
    """Migrating one copies every row and can move the database — a one-time
    operation with a rollback, not something to do behind a starting server."""
    engine = create_engine(sqlite_url)
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.commit()
    engine.dispose()

    db_upgrade.ensure_schema()

    names = table_names(sqlite_url)
    assert "alembic_version" not in names, "must not stamp a database it did not build"
    assert names == {"users"}, "must not add the baseline on top of a legacy schema"
    assert "db_upgrade" in caplog.text


class TestConcurrentStart:
    """Several processes may call this at once once the app runs multiple
    workers. Losing the race is normal and must not take a worker down; a build
    that genuinely failed still has to surface.
    """

    def test_a_lost_race_is_not_an_error(self, sqlite_url, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger=db_upgrade.log.name)
        built_by_someone_else = iter([False, False, True])

        monkeypatch.setattr(
            db_upgrade, "_is_at_head", lambda engine: next(built_by_someone_else)
        )
        monkeypatch.setattr(
            db_upgrade,
            "_upgrade_to_head",
            Mock(side_effect=RuntimeError("table already exists")),
        )
        monkeypatch.setattr(db_upgrade.time, "sleep", lambda _: None)

        db_upgrade.ensure_schema()  # must not raise

        assert "built by another process" in caplog.text

    def test_a_build_that_really_failed_still_raises(self, sqlite_url, monkeypatch):
        monkeypatch.setattr(db_upgrade, "_is_at_head", lambda engine: False)
        monkeypatch.setattr(
            db_upgrade,
            "_upgrade_to_head",
            Mock(side_effect=RuntimeError("disk is full")),
        )
        monkeypatch.setattr(db_upgrade.time, "sleep", lambda _: None)

        with pytest.raises(RuntimeError, match="disk is full"):
            db_upgrade.ensure_schema()
