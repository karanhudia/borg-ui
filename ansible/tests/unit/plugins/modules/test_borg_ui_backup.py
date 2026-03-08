# -*- coding: utf-8 -*-
"""Unit tests for borg_ui_backup module."""

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
backup_mod = _load_source(
    "ansible_collections.borgui.borg_ui.plugins.modules.borg_ui_backup",
    os.path.join(MOD_PATH, "borg_ui_backup.py"),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPOS = [
    {"id": 1, "name": "vault-01", "path": "/backups/vault-01"},
    {"id": 2, "name": "gitlab-01", "path": "/backups/gitlab-01"},
]

JOB_RUNNING = {
    "id": 42,
    "repository": "/backups/vault-01",
    "status": "running",
    "progress": 45,
    "started_at": "2024-01-01T02:00:00",
    "completed_at": None,
    "error_message": None,
    "logs": None,
    "progress_details": {
        "progress_percent": 45,
        "nfiles": 100,
        "current_file": "/opt/test.txt",
    },
}

JOB_COMPLETED = dict(JOB_RUNNING, status="completed", progress=100, logs="Backup done.")
JOB_FAILED = dict(JOB_RUNNING, status="failed", error_message="Borg lock error")


class MockClient:
    def __init__(self):
        self.calls = []
        self._responses = {}
        self._post_resp = None

    def get(self, path):
        self.calls.append(("GET", path))
        return self._responses.get(path)

    def post(self, path, data=None):
        self.calls.append(("POST", path, data))
        return self._post_resp


# ---------------------------------------------------------------------------
# Tests for _resolve_repository_path
# ---------------------------------------------------------------------------

from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client import (
    BorgUIClientError,
)


class TestResolveRepositoryPath:
    def test_resolves_by_name(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {"repositories": REPOS}
        path = backup_mod._resolve_repo_path(client, "vault-01")
        assert path == "/backups/vault-01"

    def test_raises_on_unknown_name(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {"repositories": REPOS}
        with pytest.raises(BorgUIClientError, match="not found"):
            backup_mod._resolve_repo_path(client, "nonexistent")

    def test_raises_on_empty_repos(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {"repositories": []}
        with pytest.raises(BorgUIClientError):
            backup_mod._resolve_repo_path(client, "vault-01")
