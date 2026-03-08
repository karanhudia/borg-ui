# -*- coding: utf-8 -*-
"""Unit tests for borg_ui_notification module."""

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
notif_mod = _load_source(
    "ansible_collections.borgui.borg_ui.plugins.modules.borg_ui_notification",
    os.path.join(MOD_PATH, "borg_ui_notification.py"),
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOTIF_FIXTURE = {
    "id": 1,
    "name": "Slack Alerts",
    "service_url": "slack://token@channel",
    "enabled": True,
    "title_prefix": None,
    "include_job_name_in_title": False,
    "notify_on_backup_start": False,
    "notify_on_backup_success": False,
    "notify_on_backup_failure": True,
    "notify_on_restore_success": False,
    "notify_on_restore_failure": True,
    "notify_on_check_success": False,
    "notify_on_check_failure": True,
    "notify_on_schedule_failure": True,
    "monitor_all_repositories": True,
    "repository_ids": None,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
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
# Tests for _find_notification
# ---------------------------------------------------------------------------

class TestFindNotification:
    def test_finds_by_name(self):
        client = MockClient()
        client._responses["/api/notifications"] = [NOTIF_FIXTURE]
        result = notif_mod._find_notification_by_name(client, "Slack Alerts")
        assert result is not None
        assert result["id"] == 1

    def test_returns_none_when_not_found(self):
        client = MockClient()
        client._responses["/api/notifications"] = []
        result = notif_mod._find_notification_by_name(client, "Missing")
        assert result is None

    def test_case_sensitive_match(self):
        client = MockClient()
        client._responses["/api/notifications"] = [NOTIF_FIXTURE]
        result = notif_mod._find_notification_by_name(client, "slack alerts")  # wrong case
        assert result is None


# ---------------------------------------------------------------------------
# Tests for _needs_update
# ---------------------------------------------------------------------------

MATCHING_PARAMS = {
    "service_url": NOTIF_FIXTURE["service_url"],
    "enabled": NOTIF_FIXTURE["enabled"],
    "title_prefix": NOTIF_FIXTURE["title_prefix"],
    "include_job_name_in_title": NOTIF_FIXTURE["include_job_name_in_title"],
    "notify_on_backup_start": NOTIF_FIXTURE["notify_on_backup_start"],
    "notify_on_backup_success": NOTIF_FIXTURE["notify_on_backup_success"],
    "notify_on_backup_failure": NOTIF_FIXTURE["notify_on_backup_failure"],
    "notify_on_restore_success": NOTIF_FIXTURE["notify_on_restore_success"],
    "notify_on_restore_failure": NOTIF_FIXTURE["notify_on_restore_failure"],
    "notify_on_check_success": NOTIF_FIXTURE["notify_on_check_success"],
    "notify_on_check_failure": NOTIF_FIXTURE["notify_on_check_failure"],
    "notify_on_schedule_failure": NOTIF_FIXTURE["notify_on_schedule_failure"],
    "monitor_all_repositories": NOTIF_FIXTURE["monitor_all_repositories"],
    "repository_ids": NOTIF_FIXTURE["repository_ids"],
}


class TestNeedsUpdate:
    def test_no_change_when_identical(self):
        changed, _, _ = notif_mod._needs_update(NOTIF_FIXTURE, MATCHING_PARAMS)
        assert changed is False

    def test_detects_service_url_change(self):
        params = dict(MATCHING_PARAMS, service_url="mailto://user@smtp.example.com")
        changed, _, _ = notif_mod._needs_update(NOTIF_FIXTURE, params)
        assert changed is True

    def test_detects_enabled_change(self):
        params = dict(MATCHING_PARAMS, enabled=False)
        changed, _, _ = notif_mod._needs_update(NOTIF_FIXTURE, params)
        assert changed is True

    def test_detects_notify_flag_change(self):
        params = dict(MATCHING_PARAMS, notify_on_backup_success=True)
        changed, _, _ = notif_mod._needs_update(NOTIF_FIXTURE, params)
        assert changed is True

    def test_detects_monitor_all_change(self):
        params = dict(MATCHING_PARAMS, monitor_all_repositories=False, repository_ids=[1])
        changed, _, _ = notif_mod._needs_update(NOTIF_FIXTURE, params)
        assert changed is True


# ---------------------------------------------------------------------------
# Tests for _build_payload
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_includes_all_configurable_fields(self):
        params = dict(MATCHING_PARAMS, name="Test")
        payload = notif_mod._build_payload(params)
        assert payload["name"] == "Test"
        assert "service_url" in payload
        assert "enabled" in payload
        assert "notify_on_backup_failure" in payload
        assert "monitor_all_repositories" in payload
