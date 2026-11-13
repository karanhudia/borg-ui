"""Prove API schema reuse preserves real per-test SQLite isolation."""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_api_database_builds_once_and_isolates_mutations(tmp_path):
    """Schema copies must retain constraints and survive exceptional teardown."""
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "conftest.py").write_text("""
import hashlib
import json
from pathlib import Path
import sqlite3
import shutil
import pytest
from sqlalchemy import event

# Register every application model before measuring API schema construction.
import app.main
from app.database.database import Base
from tests.fixtures import api

pytest_plugins = ["tests.fixtures.api"]
original_create = Base.metadata.create_all
original_drop = Base.metadata.drop_all
original_engine = api.create_engine
original_copy = shutil.copyfile
copies = []
builds = []
drops = []
engines = []
sessions = []
paths = []
initial_tables = set(Base.metadata.tables)

def measured_create(*args, **kwargs):
    result = original_create(*args, **kwargs)
    engine = kwargs.get("bind") or args[0]
    path = Path(engine.url.database)
    builds.append({"path": str(path), "hash": hashlib.sha256(path.read_bytes()).hexdigest()})
    return result

def measured_drop(*args, **kwargs):
    drops.append(1)
    return original_drop(*args, **kwargs)

def measured_engine(*args, **kwargs):
    engine = original_engine(*args, **kwargs)
    state = {"path": engine.url.database, "disposed": False, "connections": 0}
    engines.append(state)
    event.listen(engine, "engine_disposed", lambda unused: state.update(disposed=True))
    event.listen(engine, "connect", lambda *unused: state.update(connections=state["connections"] + 1))
    event.listen(engine, "close", lambda *unused: state.update(connections=state["connections"] - 1))
    return engine

def measured_copy(source, destination, *args, **kwargs):
    # A successful copy may never race an open schema-building connection.
    assert engines[0]["disposed"] and engines[0]["connections"] == 0
    assert str(source) == builds[0]["path"]
    copies.append(str(destination))
    return original_copy(source, destination, *args, **kwargs)

shutil.copyfile = measured_copy
Base.metadata.create_all = measured_create
Base.metadata.drop_all = measured_drop
api.create_engine = measured_engine

@pytest.fixture(autouse=True)
def observe_database(test_db):
    assert set(Base.metadata.tables) == initial_tables
    assert all(test_db is not previous for previous in sessions)
    assert all(test_db.bind is not previous.bind for previous in sessions)
    sessions.append(test_db)
    path = test_db.bind.url.database
    assert path not in paths
    paths.append(path)
    assert test_db.bind.pool.__class__.__name__ == "NullPool"
    yield

def pytest_sessionfinish(session):
    from app.main import app
    source = builds[0]
    path = Path(source["path"])
    tables = {}
    if path.exists():
        with sqlite3.connect(path) as connection:
            names = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            tables = {name: connection.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0] for (name,) in names}
    Path("observed.json").write_text(json.dumps({
        "builds": builds, "drops": len(drops), "paths": paths, "copies": copies,
        "engines": engines, "tables": tables, "expected_tables": sorted(initial_tables),
        "source_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
        "overrides_cleared": not app.dependency_overrides,
    }))
""")
    (tmp_path / "test_databases.py").write_text("""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from app.database.database import Base
from app.database.models import Repository, RepositoryStorage


def assert_empty_real_schema(db):
    assert set(inspect(db.bind).get_table_names()) == set(Base.metadata.tables)
    for table in Base.metadata.sorted_tables:
        assert db.execute(table.select()).first() is None
    for _ in range(2):
        with db.bind.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    db.add(RepositoryStorage(repository_id=999999))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def mutate(db):
    db.add(Repository(name="committed", path="/committed", encryption="none"))
    db.commit()
    db.execute(text("CREATE TABLE private_table (id INTEGER PRIMARY KEY)"))
    db.commit()
    db.add(Repository(name="pending", path="/pending", encryption="none"))
    db.flush()


@pytest.mark.parametrize("iteration", range(3))
def test_independent_database(test_db, iteration):
    assert_empty_real_schema(test_db)
    mutate(test_db)


@pytest.mark.xfail(strict=True, raises=RuntimeError)
def test_exceptional_exit(test_db):
    assert_empty_real_schema(test_db)
    mutate(test_db)
    raise RuntimeError("intentional test body failure")


def test_after_exception_is_empty(test_db):
    assert_empty_real_schema(test_db)
""")
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = str(root)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'application.db'}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--confcutdir", str(tmp_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = json.loads((tmp_path / "observed.json").read_text())
    assert len(observed["builds"]) == 1, observed
    assert observed["drops"] == 0, observed
    assert len(observed["paths"]) == len(set(observed["paths"])) == 5
    assert observed["builds"][0]["path"] not in observed["paths"]
    # SQLite owns the empty AUTOINCREMENT bookkeeping table.
    assert set(observed["tables"]) - {"sqlite_sequence"} == set(
        observed["expected_tables"]
    )
    assert observed["copies"] == observed["paths"]
    assert not any(observed["tables"].values())
    assert observed["source_hash"] == observed["builds"][0]["hash"]
    assert len(observed["engines"]) == 6
    assert all(engine["disposed"] for engine in observed["engines"])
    assert all(engine["connections"] == 0 for engine in observed["engines"])
    assert observed["overrides_cleared"]
