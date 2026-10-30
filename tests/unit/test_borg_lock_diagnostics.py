"""Lock diagnostics must be read-only, local, bounded, and safe to report."""

import json
import os

import pytest


def diagnostic(path, env):
    from app.services.borg_lock_diagnostics import cache_lock_diagnostics

    return cache_lock_diagnostics(
        f"listing archives failed (exit code 73): Failed to create/acquire the lock {path} (timeout).",
        env,
    )


def test_cache_lock_owners_are_reported_without_mutating_lock(tmp_path):
    cache = tmp_path / "cache"
    lock = cache / ("a" * 64) / "lock.exclusive"
    lock.mkdir(parents=True)
    owner = lock / "old-container.123-0"
    owner.touch()
    result = diagnostic(
        lock, {"BORG_CACHE_DIR": str(cache), "BORG_HOST_ID": "current-container"}
    )
    assert result["owners"] == ["old-container.123-0"]
    assert result["owner_liveness"] == "unknown"
    assert result["borg_host_id"] == "current-container"
    assert result["cache_lock_status"] == "present"
    assert owner.exists()
    assert list(lock.iterdir()) == [owner]


@pytest.mark.parametrize("location", ["outside", "symlink", "bad_repository_id"])
def test_does_not_scan_non_cache_paths_or_symlinks(tmp_path, monkeypatch, location):
    cache = tmp_path / "cache"
    outside = tmp_path / "outside"
    outside.mkdir()
    cache.mkdir()
    if location == "outside":
        lock = outside / "lock.exclusive"
    elif location == "symlink":
        (cache / ("a" * 64)).symlink_to(outside, target_is_directory=True)
        lock = cache / ("a" * 64) / "lock.exclusive"
    else:
        lock = cache / "not-a-repository-id" / "lock.exclusive"

    def forbidden(*args):
        pytest.fail("diagnostics must not enumerate this directory")

    monkeypatch.setattr(os, "scandir", forbidden)
    result = diagnostic(lock, {"BORG_CACHE_DIR": str(cache)})
    assert result["cache_lock_status"] == "not_inspected"
    assert result["owners"] == []


@pytest.mark.parametrize("failure", [FileNotFoundError, PermissionError])
def test_disappearing_or_unreadable_lock_is_only_diagnostic(
    tmp_path, monkeypatch, failure
):
    cache = tmp_path / "cache"
    lock = cache / ("a" * 64) / "lock.exclusive"

    def unreadable(*args):
        raise failure("unavailable")

    monkeypatch.setattr(os, "scandir", unreadable)
    result = diagnostic(lock, {"BORG_CACHE_DIR": str(cache)})
    assert result["cache_lock_status"] == failure.__name__
    assert result["owners"] == []


def test_owners_and_secrets_are_bounded_before_reporting(tmp_path):
    cache = tmp_path / "cache"
    lock = cache / ("a" * 64) / "lock.exclusive"
    lock.mkdir(parents=True)
    for i in range(12):
        (lock / f"owner-{i}-password=owner-secret.123-0").touch()
    result = diagnostic(
        lock,
        {
            "BORG_CACHE_DIR": str(cache),
            "BORG_HOST_ID": "password=host-secret " + "x" * 5000,
        },
    )
    assert len(result["owners"]) == 5
    assert result["owners_truncated"] is True
    assert "owner-secret" not in json.dumps(result)
    assert "host-secret" not in json.dumps(result)
    assert len(json.dumps(result)) < 2000
    assert len(list(lock.iterdir())) == 12


def test_no_lock_path_still_reports_host_without_scanning(monkeypatch):
    from app.services.borg_lock_diagnostics import cache_lock_diagnostics

    monkeypatch.setattr(
        os, "scandir", lambda *args: pytest.fail("no lock path to inspect")
    )
    result = cache_lock_diagnostics("Failed to acquire a lock", {})
    assert result["current_hostname"]
    assert result["cache_lock_status"] == "not_inspected"
