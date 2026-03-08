# -*- coding: utf-8 -*-
"""Unit tests for borg_ui_schedule module."""

import sys
import os
import types
import pytest

# ---------------------------------------------------------------------------
# Namespace shim
# ---------------------------------------------------------------------------
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


_load_source(
    "ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client",
    os.path.join(MU_PATH, "borg_ui_client.py"),
)
_load_source(
    "ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_common",
    os.path.join(MU_PATH, "borg_ui_common.py"),
)
sched_mod = _load_source(
    "ansible_collections.borgui.borg_ui.plugins.modules.borg_ui_schedule",
    os.path.join(MOD_PATH, "borg_ui_schedule.py"),
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPOS = [
    {"id": 1, "name": "vault-01", "path": "/backups/vault-01"},
    {"id": 2, "name": "gitlab-01", "path": "/backups/gitlab-01"},
]

JOB_FIXTURE = {
    "id": 10,
    "name": "nightly-mgt",
    "cron_expression": "0 2 * * *",
    "repository_ids": [1, 2],
    "enabled": True,
    "description": "Nightly backup",
    "run_prune_after": False,
    "run_compact_after": False,
    "prune_keep_hourly": 0,
    "prune_keep_daily": 7,
    "prune_keep_weekly": 4,
    "prune_keep_monthly": 6,
    "prune_keep_quarterly": 0,
    "prune_keep_yearly": 1,
}


class MockClient:
    def __init__(self):
        self.calls = []
        self._responses = {}
        self._post_resp = None
        self._put_resp = None

    def get(self, path):
        self.calls.append(("GET", path))
        return self._responses.get(path)

    def post(self, path, data=None):
        self.calls.append(("POST", path, data))
        return self._post_resp

    def put(self, path, data=None):
        self.calls.append(("PUT", path, data))
        return self._put_resp

    def delete(self, path):
        self.calls.append(("DELETE", path))
        return None


# ---------------------------------------------------------------------------
# Tests for _resolve_repository_names
# ---------------------------------------------------------------------------

from ansible_collections.borgui.borg_ui.plugins.module_utils.borg_ui_client import BorgUIClientError


class TestResolveRepositoryNames:
    def test_resolves_names_to_ids(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {"repositories": REPOS}
        ids = sched_mod._resolve_repository_ids(client, ["vault-01", "gitlab-01"])
        assert sorted(ids) == [1, 2]

    def test_fails_on_unknown_name(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {"repositories": REPOS}
        with pytest.raises(BorgUIClientError, match="not found"):
            sched_mod._resolve_repository_ids(client, ["nonexistent"])

    def test_empty_list_returns_empty(self):
        client = MockClient()
        client._responses["/api/repositories/"] = {"repositories": REPOS}
        ids = sched_mod._resolve_repository_ids(client, [])
        assert ids == []


# ---------------------------------------------------------------------------
# Tests for _find_schedule
# ---------------------------------------------------------------------------

class TestFindSchedule:
    def test_finds_by_name(self):
        client = MockClient()
        client._responses["/api/schedule/"] = {"jobs": [JOB_FIXTURE]}
        result = sched_mod._find_schedule_by_name(client, "nightly-mgt")
        assert result is not None
        assert result["id"] == 10

    def test_returns_none_when_not_found(self):
        client = MockClient()
        client._responses["/api/schedule/"] = {"jobs": []}
        result = sched_mod._find_schedule_by_name(client, "missing")
        assert result is None


def _desired_from_fixture(overrides=None):
    """Build a desired dict matching JOB_FIXTURE for _needs_update."""
    d = {
        "cron_expression": JOB_FIXTURE["cron_expression"],
        "enabled": JOB_FIXTURE["enabled"],
        "description": JOB_FIXTURE["description"],
        "repository_ids": JOB_FIXTURE["repository_ids"],
        "run_prune_after": JOB_FIXTURE["run_prune_after"],
        "run_compact_after": JOB_FIXTURE["run_compact_after"],
        "prune_keep_hourly": JOB_FIXTURE["prune_keep_hourly"],
        "prune_keep_daily": JOB_FIXTURE["prune_keep_daily"],
        "prune_keep_weekly": JOB_FIXTURE["prune_keep_weekly"],
        "prune_keep_monthly": JOB_FIXTURE["prune_keep_monthly"],
        "prune_keep_quarterly": JOB_FIXTURE["prune_keep_quarterly"],
        "prune_keep_yearly": JOB_FIXTURE["prune_keep_yearly"],
    }
    if overrides:
        d.update(overrides)
    return d


# ---------------------------------------------------------------------------
# Tests for _needs_update
# ---------------------------------------------------------------------------

class TestNeedsUpdate:
    def test_no_update_when_same(self):
        assert sched_mod._needs_update(JOB_FIXTURE, _desired_from_fixture()) is False

    def test_detects_cron_change(self):
        assert sched_mod._needs_update(
            JOB_FIXTURE, _desired_from_fixture({"cron_expression": "0 3 * * *"})
        ) is True

    def test_detects_repo_change(self):
        assert sched_mod._needs_update(
            JOB_FIXTURE, _desired_from_fixture({"repository_ids": [1]})
        ) is True

    def test_repo_id_order_ignored(self):
        """Reordering repos should not count as a change."""
        assert sched_mod._needs_update(
            JOB_FIXTURE, _desired_from_fixture({"repository_ids": [2, 1]})
        ) is False
