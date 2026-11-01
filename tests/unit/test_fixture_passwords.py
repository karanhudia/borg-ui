"""Exercise shared user fixtures with real password hashing in a fresh session."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_fixed_password_hashes_cannot_be_mutated(fixture_password_hashes):
    with pytest.raises(TypeError):
        fixture_password_hashes["testpass123"] = "changed"


def test_user_fixtures_hash_fixed_passwords_once_without_weakening_bcrypt(tmp_path):
    """Repeated users keep fresh database state while reusing two real hashes."""
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "conftest.py").write_text("""
import json
import time
from collections import Counter
from pathlib import Path
import pytest
from app.core import security
from tests.fixtures import api

pytest_plugins = ["tests.fixtures.database", "tests.fixtures.api"]
original_hash = security.get_password_hash
calls = Counter()
hash_seconds = 0

def measured_hash(password):
    global hash_seconds
    start = time.perf_counter()
    result = original_hash(password)
    hash_seconds += time.perf_counter() - start
    calls[password] += 1
    return result

# Instrument the real function; retain its full bcrypt implementation and cost.
security.get_password_hash = measured_hash
api.get_password_hash = measured_hash

@pytest.fixture
def test_db(db_session):
    return db_session

def pytest_sessionfinish(session):
    Path("observed.json").write_text(json.dumps({
        "calls": dict(calls), "hash_seconds": hash_seconds,
    }))
""")
    (tmp_path / "test_users.py").write_text("""
import pytest
from app.core.security import verify_password
from app.database.models import User

@pytest.mark.parametrize("iteration", range(3))
@pytest.mark.parametrize("fixture_name,password,username", [
    ("test_user", "testpass123", "testuser"),
    ("sample_user", "testpass123", "testuser"),
    ("admin_user", "admin123", "admin"),
])
def test_real_user(request, db_session, iteration, fixture_name, password, username):
    assert db_session.query(User).count() == 0
    user = request.getfixturevalue(fixture_name)
    assert user.username == username
    assert db_session.query(User).count() == 1
    assert verify_password(password, user.password_hash)
    assert not verify_password("wrong-password", user.password_hash)
    assert user.password_hash.startswith("$2b$12$")
    user.username = "changed-only-in-this-test"
    user.password_hash = "changed-only-in-this-test"
    db_session.commit()
""")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--confcutdir", str(tmp_path)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = json.loads((tmp_path / "observed.json").read_text())
    print(f"Real fixture password hash profile: {observed}")
    assert observed["calls"] == {"testpass123": 1, "admin123": 1}
