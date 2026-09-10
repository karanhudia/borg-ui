"""Unit tests for the startup package-installation script.

The script used to open /data/borg.db with raw sqlite3 — on installs with an
external database that file does not exist (or worse, exists empty) and every
boot crashed with "no such table". It now talks to the application's own
DATABASE_URL through SQLAlchemy; these tests pin the query/update behaviour
against a real (SQLite) engine and the fresh-install skip.
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.database.models import Base, InstalledPackage

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def startup_packages():
    spec = importlib.util.spec_from_file_location(
        "startup_packages_under_test", REPO_ROOT / "app/scripts/startup_packages.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    from app.database.models import Operation

    Base.metadata.create_all(
        engine, tables=[InstalledPackage.__table__, Operation.__table__]
    )
    return engine


def _seed_package(engine, status):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO installed_packages"
                " (name, install_command, status, created_at, updated_at)"
                " VALUES ('wakeonlan', 'apt-get install -y wakeonlan', :status,"
                " '2026-01-01', '2026-01-01')"
            ),
            {"status": status},
        )


@pytest.mark.unit
def test_missing_package_is_returned_and_reset_to_pending(
    startup_packages, engine, monkeypatch
):
    _seed_package(engine, status="installed")
    monkeypatch.setattr(startup_packages, "engine", engine)
    monkeypatch.setattr(startup_packages, "_database_absent", lambda: False)
    monkeypatch.setattr(
        startup_packages, "is_package_actually_installed", lambda name: False
    )

    packages = startup_packages.get_packages_to_install()

    assert [(name, status) for _, name, status, _ in packages] == [
        ("wakeonlan", "pending")
    ]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM installed_packages")).scalar() == (
            "pending"
        )


@pytest.mark.unit
def test_present_package_is_left_alone(startup_packages, engine, monkeypatch):
    _seed_package(engine, status="installed")
    monkeypatch.setattr(startup_packages, "engine", engine)
    monkeypatch.setattr(startup_packages, "_database_absent", lambda: False)
    monkeypatch.setattr(
        startup_packages, "is_package_actually_installed", lambda name: True
    )

    assert startup_packages.get_packages_to_install() == []
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM installed_packages")).scalar() == (
            "installed"
        )


@pytest.mark.unit
def test_fresh_sqlite_install_skips_without_creating_a_file(
    startup_packages, tmp_path, monkeypatch
):
    missing = tmp_path / "not-there.db"
    monkeypatch.setattr(
        startup_packages.settings, "database_url", f"sqlite:///{missing}"
    )

    assert startup_packages.get_packages_to_install() == []
    assert not missing.exists()


@pytest.mark.unit
def test_missing_schema_is_handled_not_raised(startup_packages, tmp_path, monkeypatch):
    # An existing but table-less database (the exact shape of the stray empty
    # /data/borg.db seen in production) must degrade to "no packages".
    empty = create_engine(f"sqlite:///{tmp_path}/empty.db")
    with empty.connect():
        pass
    monkeypatch.setattr(startup_packages, "engine", empty)
    monkeypatch.setattr(startup_packages, "_database_absent", lambda: False)

    assert startup_packages.get_packages_to_install() == []


def test_packages_with_an_in_flight_install_operation_are_skipped(
    startup_packages, tmp_path, monkeypatch
):
    """Phase 6: an install queued before the restart lives in `operations`, so
    the startup script must not queue a second one for the same package."""
    import json

    from app.database.models import Operation

    engine = create_engine(f"sqlite:///{tmp_path}/ops.db")
    Base.metadata.create_all(
        engine,
        tables=[
            InstalledPackage.__table__,
            Operation.__table__,
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO installed_packages"
                " (name, install_command, status, created_at, updated_at)"
                " VALUES ('htop', 'apt-get install -y htop', 'pending',"
                " '2026-09-08 00:00:00', '2026-09-08 00:00:00')"
            )
        )
        package_id = conn.execute(
            text("SELECT id FROM installed_packages WHERE name = 'htop'")
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO operations"
                " (kind, category, status, trigger, priority, run_id, params,"
                " created_at)"
                " VALUES ('package_install', 'system', 'queued', 'manual', 0,"
                " 'run-1', :params, '2026-09-08 00:00:00')"
            ),
            {"params": json.dumps({"package_id": package_id})},
        )

    monkeypatch.setattr(startup_packages, "engine", engine)
    monkeypatch.setattr(startup_packages, "_database_absent", lambda: False)
    monkeypatch.setattr(
        startup_packages, "is_package_actually_installed", lambda name: False
    )

    assert startup_packages.get_packages_to_install() == []


def test_a_completed_install_operation_does_not_block_a_reinstall(
    startup_packages, tmp_path, monkeypatch
):
    import json

    from app.database.models import Operation

    engine = create_engine(f"sqlite:///{tmp_path}/ops-done.db")
    Base.metadata.create_all(
        engine,
        tables=[
            InstalledPackage.__table__,
            Operation.__table__,
        ],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO installed_packages"
                " (name, install_command, status, created_at, updated_at)"
                " VALUES ('htop', 'apt-get install -y htop', 'pending',"
                " '2026-09-08 00:00:00', '2026-09-08 00:00:00')"
            )
        )
        package_id = conn.execute(
            text("SELECT id FROM installed_packages WHERE name = 'htop'")
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO operations"
                " (kind, category, status, trigger, priority, run_id, params,"
                " created_at)"
                " VALUES ('package_install', 'system', 'completed', 'manual', 0,"
                " 'run-1', :params, '2026-09-08 00:00:00')"
            ),
            {"params": json.dumps({"package_id": package_id})},
        )

    monkeypatch.setattr(startup_packages, "engine", engine)
    monkeypatch.setattr(startup_packages, "_database_absent", lambda: False)
    monkeypatch.setattr(
        startup_packages, "is_package_actually_installed", lambda name: False
    )

    assert [row[1] for row in startup_packages.get_packages_to_install()] == ["htop"]


def test_a_database_without_the_operations_table_still_works(
    startup_packages, engine, monkeypatch
):
    """A pre-phase-1 database has no operations table; the check degrades to
    the legacy one rather than crashing the boot."""
    _seed_package(engine, "pending")
    monkeypatch.setattr(startup_packages, "engine", engine)
    monkeypatch.setattr(startup_packages, "_database_absent", lambda: False)
    monkeypatch.setattr(
        startup_packages, "is_package_actually_installed", lambda name: False
    )

    assert len(startup_packages.get_packages_to_install()) == 1
