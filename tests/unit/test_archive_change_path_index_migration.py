"""Tests for revision e4f5a6b7c8d9 (drop the archive_changes raw-path indexes).

The B-tree entry-size limit only exists on PostgreSQL, so both the failure the
revision fixes and the reason its downgrade leaves the indexes absent can only
be proven there; those tests are skipped unless BORG_TEST_POSTGRES_URL is set.
The SQLite test pins the downgrade policy itself, which holds on any dialect.
"""

import os
import random
import string
from datetime import datetime

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.database.db_upgrade import _alembic_config, _engine
from app.database.models import Archive, ArchiveChange, Repository

REVISION = "e4f5a6b7c8d9"
PREVIOUS = "d3e4f5a6b7c8"
PATH_INDEXES = {"ix_archive_changes_path", "ix_archive_changes_archive_path"}
# Past PostgreSQL's ~2.7 KB B-tree entry limit. Index entries are compressed
# before that check, so the value must not compress: a repetitive "x" * 4096
# shrinks to a few bytes and fits. Seeded, so every run inserts the same path.
LONG_PATH = "/" + "".join(
    random.Random(2026).choices(string.ascii_letters + string.digits, k=4096)
)

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
)


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


def _path_indexes(url):
    engine = _engine(url)
    names = {i["name"] for i in inspect(engine).get_indexes("archive_changes")}
    engine.dispose()
    return names & PATH_INDEXES


def _insert_long_path(url):
    """One change row whose path is longer than a B-tree entry may be.

    Rolled back on failure: an aborted transaction left open would keep its
    locks on archive_changes and block the DDL that follows.
    """
    engine = _engine(url)
    session = sessionmaker(bind=engine)()
    try:
        repo = Repository(name="r", path="/srv/r")
        session.add(repo)
        session.flush()
        archive = Archive(
            repository_id=repo.id,
            borg_id="b",
            name="a",
            series="s",
            start=datetime(2026, 9, 4),
        )
        session.add(archive)
        session.flush()
        session.add(
            ArchiveChange(archive_id=archive.id, path=LONG_PATH, change="added")
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def _stored_paths(url):
    engine = _engine(url)
    session = sessionmaker(bind=engine)()
    paths = [row.path for row in session.query(ArchiveChange)]
    session.close()
    engine.dispose()
    return paths


def _reset_postgres():
    engine = _engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.mark.unit
def test_downgrade_leaves_the_path_indexes_absent_and_keeps_long_rows(tmp_path):
    """The downgrade policy: never recreate the indexes. Once the revision has
    run, rows past the entry limit may exist, and recreating an index over
    them fails on PostgreSQL; leaving two performance-only indexes absent is
    the safe reversal."""
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, REVISION)
    assert _path_indexes(url) == set()

    _insert_long_path(url)
    _migrate(url, PREVIOUS, down=True)

    assert _path_indexes(url) == set()
    assert _stored_paths(url) == [LONG_PATH]


@pytest.mark.unit
@requires_postgres
def test_the_entry_limit_is_real_and_the_downgrade_survives_long_rows():
    """Proven end to end on PostgreSQL: with the indexes in place the insert of
    a long path fails (the bug this revision fixes), after the revision it
    succeeds, and the downgrade then completes over that row instead of
    failing on CREATE INDEX."""
    _reset_postgres()
    _migrate(POSTGRES_URL, PREVIOUS)
    assert _path_indexes(POSTGRES_URL) == PATH_INDEXES

    with pytest.raises(DBAPIError, match="exceeds btree"):
        _insert_long_path(POSTGRES_URL)
    assert _stored_paths(POSTGRES_URL) == []

    _migrate(POSTGRES_URL, REVISION)
    _insert_long_path(POSTGRES_URL)
    assert _stored_paths(POSTGRES_URL) == [LONG_PATH]

    _migrate(POSTGRES_URL, PREVIOUS, down=True)
    assert _path_indexes(POSTGRES_URL) == set()
    assert _stored_paths(POSTGRES_URL) == [LONG_PATH]
