"""
Unit tests for app/scripts/deploy_ssh_key.py path resolution.

No real SSH and no real database: the ORM session is replaced with a stub and
the deploy directory is a tmp_path wired in through settings.ssh_home_dir.
"""

import stat
from types import SimpleNamespace

import pytest

from app.api.ssh_keys import DEPLOY_SSH_KEY_SCRIPT
from app.config import settings
from app.core.security import encrypt_secret
from app.scripts import deploy_ssh_key

PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----\n"
)
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest borg-ui"


class _StubQuery:
    def __init__(self, key):
        self._key = key

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._key


class _StubSession:
    def __init__(self, key):
        self._key = key

    def query(self, *args, **kwargs):
        return _StubQuery(self._key)

    def close(self):
        pass


def _system_key():
    return SimpleNamespace(
        private_key=encrypt_secret(PRIVATE_KEY),
        key_type="ed25519",
        public_key=PUBLIC_KEY,
        is_system_key=True,
    )


def _no_borg_user(name):
    raise KeyError(name)


@pytest.fixture
def deploy_dir(tmp_path, monkeypatch):
    """Point the deploy step at a fresh directory, as an LXC DATA_DIR would."""
    target = tmp_path / "opt" / "borg-ui" / "data" / "ssh_keys"
    monkeypatch.setattr(settings, "ssh_home_dir", str(target))
    # No borg user on the test host; mirror the LXC-as-root case explicitly.
    monkeypatch.setattr(deploy_ssh_key.pwd, "getpwnam", _no_borg_user)
    return target


@pytest.mark.unit
class TestDeploySshKeyScript:
    def test_writes_key_pair_into_configured_ssh_home_dir(
        self, deploy_dir, monkeypatch
    ):
        monkeypatch.setattr(
            "app.database.database.SessionLocal", lambda: _StubSession(_system_key())
        )

        deploy_ssh_key.deploy_ssh_keys()

        private_key = deploy_dir / "id_ed25519"
        public_key = deploy_dir / "id_ed25519.pub"
        assert private_key.read_text() == PRIVATE_KEY
        assert public_key.read_text() == PUBLIC_KEY
        assert stat.S_IMODE(deploy_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(private_key.stat().st_mode) == 0o600
        assert stat.S_IMODE(public_key.stat().st_mode) == 0o644

    def test_only_touches_the_configured_directory(self, deploy_dir, monkeypatch):
        seen = []
        real_mkdir = deploy_ssh_key.Path.mkdir

        def recording_mkdir(self, *args, **kwargs):
            seen.append(str(self))
            return real_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(deploy_ssh_key.Path, "mkdir", recording_mkdir)
        monkeypatch.setattr(
            "app.database.database.SessionLocal", lambda: _StubSession(None)
        )

        deploy_ssh_key.deploy_ssh_keys()

        # mkdir(parents=True) recurses through the ancestors, so several paths
        # are recorded; all of them must lie on the configured path and none
        # may be the old hardcoded /home/borg/.ssh.
        allowed = {str(deploy_dir), *(str(parent) for parent in deploy_dir.parents)}
        assert str(deploy_dir) in seen
        assert set(seen) <= allowed
        assert not any(path.startswith("/home/borg") for path in seen)

    def test_no_system_key_leaves_directory_empty(self, deploy_dir, monkeypatch):
        monkeypatch.setattr(
            "app.database.database.SessionLocal", lambda: _StubSession(None)
        )

        deploy_ssh_key.deploy_ssh_keys()

        assert deploy_dir.is_dir()
        assert list(deploy_dir.iterdir()) == []


@pytest.mark.unit
def test_api_locates_deploy_script_relative_to_package():
    assert DEPLOY_SSH_KEY_SCRIPT.is_file()
    assert DEPLOY_SSH_KEY_SCRIPT.name == "deploy_ssh_key.py"
    assert not str(DEPLOY_SSH_KEY_SCRIPT).startswith("/app/app/")
