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

from app.database.models import Base, InstalledPackage, PackageInstallJob

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
    Base.metadata.create_all(
        engine, tables=[InstalledPackage.__table__, PackageInstallJob.__table__]
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
