"""Unit tests for the manual admin scripts (reset_password, delete_ssh_key).

Both used to open /data/borg.db with raw sqlite3, which silently targeted the
wrong (or a nonexistent) database on installs using DATABASE_URL. They now run
against the application's database; these tests pin that behaviour with a real
SQLite engine and file-URL plumbing.
"""

import importlib.util
from pathlib import Path

import bcrypt
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Repository, SSHConnection, SSHKey, User
from app.scripts.reset_password import reset_password

REPO_ROOT = Path(__file__).resolve().parents[2]


def _database(tmp_path, *models):
    path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine, tables=[m.__table__ for m in models])
    return f"sqlite:///{path}", engine


# --- reset_password -----------------------------------------------------------


@pytest.mark.unit
def test_reset_password_updates_hash_and_clears_must_change(tmp_path):
    url, engine = _database(tmp_path, User)
    with sessionmaker(bind=engine)() as db:
        db.add(User(username="admin", password_hash="old", must_change_password=True))
        db.commit()

    reset_password("admin", "newpassword123", url)

    with engine.connect() as conn:
        password_hash, must_change = conn.execute(
            text("SELECT password_hash, must_change_password FROM users")
        ).fetchone()
    assert bcrypt.checkpw(b"newpassword123", password_hash.encode())
    assert not must_change


@pytest.mark.unit
def test_reset_password_unknown_user_exits_nonzero(tmp_path):
    url, _ = _database(tmp_path, User)
    with pytest.raises(SystemExit) as excinfo:
        reset_password("nobody", "pw", url)
    assert excinfo.value.code == 1


@pytest.mark.unit
def test_reset_password_missing_sqlite_file_exits_without_creating_it(tmp_path):
    missing = tmp_path / "not-there.db"
    with pytest.raises(SystemExit):
        reset_password("admin", "pw", f"sqlite:///{missing}")
    assert not missing.exists()


# --- delete_ssh_key -----------------------------------------------------------


@pytest.fixture()
def delete_ssh_key_module():
    spec = importlib.util.spec_from_file_location(
        "delete_ssh_key_under_test", REPO_ROOT / "app/scripts/delete_ssh_key.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_delete_ssh_key_clears_references_and_deletes(
    delete_ssh_key_module, tmp_path, monkeypatch
):
    url, engine = _database(tmp_path, SSHKey, SSHConnection, Repository)
    with sessionmaker(bind=engine)() as db:
        key = SSHKey(
            name="k",
            key_type="ed25519",
            public_key="pub",
            private_key="priv",
            is_system_key=True,
        )
        db.add(key)
        db.flush()
        db.add(SSHConnection(host="h", username="u", ssh_key_id=key.id))
        db.add(Repository(name="r", path="/tmp/r", ssh_key_id=key.id))
        db.commit()
    monkeypatch.setattr(delete_ssh_key_module.settings, "database_url", url)

    assert delete_ssh_key_module.delete_ssh_key(is_system=True, force=True) == 0

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ssh_keys")).scalar() == 0
        status, key_ref = conn.execute(
            text("SELECT status, ssh_key_id FROM ssh_connections")
        ).fetchone()
        assert (status, key_ref) == ("failed", None)
        assert (
            conn.execute(text("SELECT ssh_key_id FROM repositories")).scalar() is None
        )


@pytest.mark.unit
def test_delete_ssh_key_missing_database_errors_cleanly(
    delete_ssh_key_module, tmp_path, monkeypatch
):
    missing = tmp_path / "not-there.db"
    monkeypatch.setattr(
        delete_ssh_key_module.settings, "database_url", f"sqlite:///{missing}"
    )
    assert delete_ssh_key_module.delete_ssh_key(key_id=1) == 1
    assert not missing.exists()
