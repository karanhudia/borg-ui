"""Unit tests for the shared SQLite-file-absent guard."""

import pytest

from app.database.url_utils import sqlite_database_missing


@pytest.mark.unit
def test_existing_sqlite_file_is_not_missing(tmp_path):
    db = tmp_path / "borg.db"
    db.write_text("")
    assert sqlite_database_missing(f"sqlite:///{db}") is False


@pytest.mark.unit
def test_absent_sqlite_file_is_missing(tmp_path):
    db = tmp_path / "not-there.db"
    assert sqlite_database_missing(f"sqlite:///{db}") is True


@pytest.mark.unit
def test_non_sqlite_backend_is_never_missing():
    # A server database is always "present" - a missing schema surfaces as a
    # query error, never as a filesystem check.
    assert sqlite_database_missing("postgresql://u:p@db.example/borg") is False


@pytest.mark.unit
def test_in_memory_sqlite_is_not_missing():
    assert sqlite_database_missing("sqlite:///:memory:") is False
    assert sqlite_database_missing("sqlite://") is False
