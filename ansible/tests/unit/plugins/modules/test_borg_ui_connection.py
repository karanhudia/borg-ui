# -*- coding: utf-8 -*-
"""Unit tests for borg_ui_connection module."""

import sys
import os
import types
import pytest

TESTS_DIR = os.path.dirname(__file__)
ANSIBLE_DIR = os.path.abspath(os.path.join(TESTS_DIR, "..", "..", "..", ".."))
MU_PATH = os.path.join(ANSIBLE_DIR, "plugins", "module_utils")
MOD_PATH = os.path.join(ANSIBLE_DIR, "plugins", "modules")


def _ensure_pkg(name, path_hint=None):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__path__ = [path_hint] if path_hint else []
        mod.__package__ = name
        sys.modules[name] = mod
    return sys.modules[name]


_ensure_pkg("ansible_collections")
_ensure_pkg("ansible_collections.borgui")
_ensure_pkg("ansible_collections.borgui.borg_ui")
_ensure_pkg("ansible_collections.borgui.borg_ui.plugins")
_ensure_pkg("ansible_collections.borgui.borg_ui.plugins.module_utils", MU_PATH)
_ensure_pkg("ansible_collections.borgui.borg_ui.plugins.modules", MOD_PATH)

if "ansible" not in sys.modules:
    sys.modules["ansible"] = types.ModuleType("ansible")
if "ansible.module_utils" not in sys.modules:
    sys.modules["ansible.module_utils"] = types.ModuleType("ansible.module_utils")
if "ansible.module_utils.basic" not in sys.modules:
    basic = types.ModuleType("ansible.module_utils.basic")
    class _FM:
        def __init__(self, **kw): pass
    basic.AnsibleModule = _FM
    sys.modules["ansible.module_utils.basic"] = basic


def _load_source(module_name, file_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_load_source("ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client",
             os.path.join(MU_PATH, "borg_ui_client.py"))
_load_source("ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_common",
             os.path.join(MU_PATH, "borg_ui_common.py"))
conn_mod = _load_source(
    "ansible_collections.borgui.borg_ui.plugins.modules.borg_ui_connection",
    os.path.join(MOD_PATH, "borg_ui_connection.py"),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONN_FIXTURE = {
    "id": 1,
    "ssh_key_id": 2,
    "ssh_key_name": "my-ssh-key",
    "host": "backup-server.example.com",
    "username": "ansible",
    "port": 22,
    "use_sftp_mode": False,
    "default_path": "/opt",
    "ssh_path_prefix": "",
    "mount_point": "",
    "status": "connected",
    "error_message": None,
}

REPOS_FIXTURE = [
    {"id": 10, "name": "vault-01", "source_ssh_connection_id": 1},
    {"id": 11, "name": "gitlab-01", "source_ssh_connection_id": None},
]


class MockClient:
    def __init__(self):
        self.calls = []
        self._responses = {}
        self._put_resp = None

    def get(self, path):
        self.calls.append(("GET", path))
        return self._responses.get(path)

    def put(self, path, data=None):
        self.calls.append(("PUT", path, data))
        return self._put_resp

    def delete(self, path):
        self.calls.append(("DELETE", path))
        return None


# ---------------------------------------------------------------------------
# Tests for _find_connection
# ---------------------------------------------------------------------------

class TestFindConnection:
    def test_finds_by_host_user_port(self):
        client = MockClient()
        client._responses["/api/ssh-keys/connections"] = {
            "connections": [CONN_FIXTURE]
        }
        result = conn_mod._find_connection(client, "backup-server.example.com", "ansible", 22)
        assert result is not None
        assert result["id"] == 1

    def test_returns_none_for_wrong_user(self):
        client = MockClient()
        client._responses["/api/ssh-keys/connections"] = {
            "connections": [CONN_FIXTURE]
        }
        result = conn_mod._find_connection(client, "backup-server.example.com", "root", 22)
        assert result is None

    def test_returns_none_for_wrong_port(self):
        client = MockClient()
        client._responses["/api/ssh-keys/connections"] = {
            "connections": [CONN_FIXTURE]
        }
        result = conn_mod._find_connection(client, "backup-server.example.com", "ansible", 2222)
        assert result is None

    def test_returns_none_for_wrong_host(self):
        client = MockClient()
        client._responses["/api/ssh-keys/connections"] = {
            "connections": [CONN_FIXTURE]
        }
        result = conn_mod._find_connection(client, "other.example.com", "ansible", 22)
        assert result is None

    def test_returns_none_when_no_connections(self):
        client = MockClient()
        client._responses["/api/ssh-keys/connections"] = {"connections": []}
        result = conn_mod._find_connection(client, "backup-server.example.com", "ansible", 22)
        assert result is None


# ---------------------------------------------------------------------------
# Tests for _needs_update
# ---------------------------------------------------------------------------

def _conn_desired(overrides=None):
    """Build a desired-state dict for connection _needs_update."""
    d = {
        "host": CONN_FIXTURE["host"],
        "username": CONN_FIXTURE["username"],
        "port": CONN_FIXTURE["port"],
        "use_sftp_mode": CONN_FIXTURE["use_sftp_mode"],
        "default_path": CONN_FIXTURE["default_path"],
        "ssh_path_prefix": CONN_FIXTURE["ssh_path_prefix"],
        "mount_point": CONN_FIXTURE["mount_point"],
    }
    if overrides:
        d.update(overrides)
    return d


class TestNeedsUpdate:
    def test_no_change_when_same(self):
        changed, _, _ = conn_mod._needs_update(CONN_FIXTURE, _conn_desired())
        assert changed is False

    def test_detects_sftp_change(self):
        changed, _, _ = conn_mod._needs_update(CONN_FIXTURE, _conn_desired({"use_sftp_mode": True}))
        assert changed is True

    def test_detects_default_path_change(self):
        changed, _, _ = conn_mod._needs_update(CONN_FIXTURE, _conn_desired({"default_path": "/home"}))
        assert changed is True


# ---------------------------------------------------------------------------
# Tests for _get_repos_using_connection
# ---------------------------------------------------------------------------

class TestGetReferencingRepos:
    def test_finds_repos_referencing_connection(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {"repositories": REPOS_FIXTURE}
        result = conn_mod._get_referencing_repos(client, connection_id=1)
        assert len(result) == 1
        assert result[0]["name"] == "vault-01"

    def test_returns_empty_when_none_reference(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {
            "repositories": [{"id": 11, "name": "gitlab-01", "source_ssh_connection_id": None}]
        }
        result = conn_mod._get_referencing_repos(client, connection_id=1)
        assert result == []
