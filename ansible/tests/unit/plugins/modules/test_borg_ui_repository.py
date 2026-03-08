# -*- coding: utf-8 -*-
"""Unit tests for borg_ui_repository module."""

import json
import sys
import os
import types
import pytest

# ---------------------------------------------------------------------------
# Namespace shim — allows importing without installing the collection
# ---------------------------------------------------------------------------
TESTS_DIR = os.path.dirname(__file__)
ANSIBLE_DIR = os.path.abspath(os.path.join(TESTS_DIR, "..", "..", "..", ".."))


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

MU_PATH = os.path.join(ANSIBLE_DIR, "plugins", "module_utils")
_ensure_pkg("ansible_collections.borgui.borg_ui.plugins.module_utils", MU_PATH)

MOD_PATH = os.path.join(ANSIBLE_DIR, "plugins", "modules")
_ensure_pkg("ansible_collections.borgui.borg_ui.plugins.modules", MOD_PATH)


def _load_source(module_name, file_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load module_utils first
client_mod = _load_source(
    "ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client",
    os.path.join(MU_PATH, "borg_ui_client.py"),
)
common_mod = _load_source(
    "ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_common",
    os.path.join(MU_PATH, "borg_ui_common.py"),
)


# Stub AnsibleModule before loading the module under test
class _FakeAnsibleModule:
    def __init__(self, **kwargs):
        pass


if "ansible" not in sys.modules:
    sys.modules["ansible"] = types.ModuleType("ansible")
if "ansible.module_utils" not in sys.modules:
    sys.modules["ansible.module_utils"] = types.ModuleType("ansible.module_utils")
if "ansible.module_utils.basic" not in sys.modules:
    basic = types.ModuleType("ansible.module_utils.basic")
    basic.AnsibleModule = _FakeAnsibleModule
    sys.modules["ansible.module_utils.basic"] = basic

repo_mod = _load_source(
    "ansible_collections.borgui.borg_ui.plugins.modules.borg_ui_repository",
    os.path.join(MOD_PATH, "borg_ui_repository.py"),
)

BorgUIClientError = client_mod.BorgUIClientError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_FIXTURE = {
    "id": 1,
    "name": "vault-01",
    "path": "/backups/vault-01",
    "encryption": "repokey",
    "compression": "auto,lz4",
    "source_directories": ["/opt"],
    "exclude_patterns": [],
    "pre_backup_script": "",
    "post_backup_script": "",
    "hook_timeout": 300,
    "pre_hook_timeout": 300,
    "post_hook_timeout": 300,
    "continue_on_hook_failure": False,
    "mode": "full",
    "bypass_lock": False,
    "custom_flags": "",
    "source_ssh_connection_id": None,
    "repository_type": "local",
    "last_backup": None,
    "total_size": 0,
    "archive_count": 0,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "has_keyfile": False,
    "has_running_maintenance": False,
}

SCHEDULE_FIXTURE = {
    "id": 10,
    "name": "nightly",
    "repository_ids": [1],
    "cron_expression": "0 2 * * *",
    "enabled": True,
}


class MockClient:
    """Mock BorgUIClient that records calls and returns preset responses."""

    def __init__(self):
        self.calls = []
        self._get_responses = {}
        self._post_response = None
        self._put_response = None
        self._delete_response = None

    def get(self, path):
        self.calls.append(("GET", path))
        return self._get_responses.get(path)

    def post(self, path, data=None):
        self.calls.append(("POST", path, data))
        return self._post_response

    def put(self, path, data=None):
        self.calls.append(("PUT", path, data))
        return self._put_response

    def delete(self, path):
        self.calls.append(("DELETE", path))
        return self._delete_response


# ---------------------------------------------------------------------------
# Tests for _find_repository
# ---------------------------------------------------------------------------

class TestFindRepository:
    def test_finds_by_name(self):
        client = MockClient()
        client._get_responses["/api/repositories/"] = {
            "repositories": [REPO_FIXTURE]
        }
        result = repo_mod._find_repo_by_name(client, "vault-01")
        assert result is not None
        assert result["id"] == 1

    def test_returns_none_when_not_found(self):
        client = MockClient()
        client._get_responses["/api/repositories/"] = {"repositories": []}
        result = repo_mod._find_repo_by_name(client, "missing")
        assert result is None

    def test_raises_on_client_error(self):
        client = MockClient()

        def _raise(*a, **kw):
            raise BorgUIClientError("connection refused")

        client.get = _raise
        with pytest.raises(BorgUIClientError):
            repo_mod._find_repo_by_name(client, "vault-01")


# ---------------------------------------------------------------------------
# Tests for _build_payload
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_includes_required_fields(self):
        params = {
            "name": "vault-01",
            "path": "/backups/vault-01",
            "encryption": "repokey",
            "compression": "auto,lz4",
            "source_directories": ["/opt"],
            "exclude_patterns": [],
            "pre_backup_script": "",
            "post_backup_script": "",
            "hook_timeout": 300,
            "pre_hook_timeout": 300,
            "post_hook_timeout": 300,
            "continue_on_hook_failure": False,
            "mode": "full",
            "bypass_lock": False,
            "custom_flags": "",
            "source_connection_id": None,
            "passphrase": "secret",
        }
        payload = repo_mod._build_payload(params)
        assert payload["name"] == "vault-01"
        assert payload["path"] == "/backups/vault-01"

    def test_payload_structure(self):
        params = {
            "name": "vault-01",
            "path": "/backups/vault-01",
            "encryption": "repokey",
            "compression": "auto,lz4",
            "source_directories": [],
            "exclude_patterns": [],
            "pre_backup_script": "",
            "post_backup_script": "",
            "hook_timeout": 300,
            "pre_hook_timeout": 300,
            "post_hook_timeout": 300,
            "continue_on_hook_failure": False,
            "mode": "full",
            "bypass_lock": False,
            "custom_flags": "",
            "source_connection_id": None,
            "passphrase": "secret",
        }
        payload = repo_mod._build_payload(params)
        # Verify the key fields are present
        assert "name" in payload
        assert "path" in payload
        assert "encryption" in payload


# ---------------------------------------------------------------------------
# Tests for _needs_update
# ---------------------------------------------------------------------------

def _desired_params(overrides=None):
    """Build a desired-state params dict mirroring REPO_FIXTURE."""
    p = {
        "compression": REPO_FIXTURE["compression"],
        "source_directories": REPO_FIXTURE["source_directories"],
        "exclude_patterns": REPO_FIXTURE["exclude_patterns"],
        "pre_backup_script": REPO_FIXTURE["pre_backup_script"],
        "post_backup_script": REPO_FIXTURE["post_backup_script"],
        "hook_timeout": REPO_FIXTURE["hook_timeout"],
        "pre_hook_timeout": REPO_FIXTURE["pre_hook_timeout"],
        "post_hook_timeout": REPO_FIXTURE["post_hook_timeout"],
        "continue_on_hook_failure": REPO_FIXTURE["continue_on_hook_failure"],
        "mode": REPO_FIXTURE["mode"],
        "bypass_lock": REPO_FIXTURE["bypass_lock"],
        "custom_flags": REPO_FIXTURE["custom_flags"],
    }
    if overrides:
        p.update(overrides)
    return p


class TestNeedsUpdate:
    def test_no_change_when_same(self):
        changed, _, _ = repo_mod._needs_update(REPO_FIXTURE, _desired_params())
        assert changed is False

    def test_detects_changed_compression(self):
        changed, _, _ = repo_mod._needs_update(REPO_FIXTURE, _desired_params({"compression": "zstd"}))
        assert changed is True

    def test_detects_changed_source_directories(self):
        changed, _, _ = repo_mod._needs_update(REPO_FIXTURE, _desired_params({"source_directories": ["/opt", "/etc"]}))
        assert changed is True

    def test_diff_contains_only_changed_keys(self):
        changed, before, after = repo_mod._needs_update(
            REPO_FIXTURE, _desired_params({"compression": "zstd"})
        )
        assert changed is True
        assert "compression" in before
        assert before["compression"] == "auto,lz4"
        assert after["compression"] == "zstd"


# ---------------------------------------------------------------------------
# Tests for cascade delete logic (_get_schedules_using_repo)
# ---------------------------------------------------------------------------

class TestGetReferencingSchedules:
    def test_finds_schedules_referencing_repo(self):
        client = MockClient()
        client._get_responses["/api/schedule/"] = {
            "jobs": [
                SCHEDULE_FIXTURE,
                {"id": 11, "name": "weekly", "repository_ids": [2]},
            ]
        }
        result = repo_mod._get_referencing_schedules(client, repo_id=1)
        assert len(result) == 1
        assert result[0]["name"] == "nightly"

    def test_returns_empty_when_no_references(self):
        client = MockClient()
        client._get_responses["/api/schedule/"] = {
            "jobs": [{"id": 11, "name": "weekly", "repository_ids": [2]}]
        }
        result = repo_mod._get_referencing_schedules(client, repo_id=1)
        assert result == []

    def test_handles_none_repository_ids(self):
        client = MockClient()
        client._get_responses["/api/schedule/"] = {
            "jobs": [{"id": 11, "name": "weekly", "repository_ids": None}]
        }
        result = repo_mod._get_referencing_schedules(client, repo_id=1)
        assert result == []
