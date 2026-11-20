from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import BackupPlan, Repository
from app.services import this_machine as tm


def _host(tmp_path: Path, *roots: str) -> Path:
    host = tmp_path / "local"
    (host / "etc").mkdir(parents=True)
    (host / "etc" / "os-release").write_text("ID=debian\n")
    for root in roots:
        (host / root).mkdir(parents=True, exist_ok=True)
    return host


@pytest.mark.unit
def test_find_host_root_needs_os_release(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    assert (
        tm.find_host_root([str(bare)], container_root=tmp_path, in_docker=True) is None
    )


@pytest.mark.unit
def test_find_host_root_finds_mounted_host(tmp_path):
    host = _host(tmp_path)
    container = tmp_path / "container"
    container.mkdir()
    assert (
        tm.find_host_root([str(host)], container_root=container, in_docker=True) == host
    )


@pytest.mark.unit
def test_find_host_root_skips_container_root(tmp_path):
    host = _host(tmp_path)
    assert tm.find_host_root([str(host)], container_root=host, in_docker=True) is None


@pytest.mark.unit
def test_find_host_root_native_is_slash():
    assert tm.find_host_root([], in_docker=False) == Path("/")


@pytest.mark.unit
def test_snapshot_location_host_and_fallback(tmp_path):
    host = _host(tmp_path)
    data = tmp_path / "data"
    assert tm.snapshot_location(host, data) == (host / "var/backups/borg-ui", False)
    assert tm.snapshot_location(None, data) == (data / "this-machine", True)


@pytest.mark.unit
def test_source_directories_only_existing_roots(tmp_path):
    host = _host(tmp_path, "home", "var/lib/docker/volumes")
    assert tm.source_directories(host) == [
        str(host / "etc"),
        str(host / "home"),
        str(host / "var/lib/docker/volumes"),
    ]


@pytest.mark.unit
def test_excludes_cover_live_database_and_repo(tmp_path):
    host = _host(tmp_path)
    repo = host / "var/backups/borg-ui"
    excludes = tm.exclude_patterns(host, repo, tmp_path / "data")
    for pattern in ("**/borg.db", "**/borg.db-wal", "**/borg.db-shm", "**/.cache"):
        assert pattern in excludes
    assert str(repo) in excludes
    assert str(host / "var/lib/docker/overlay2") in excludes


@pytest.mark.unit
def test_compact_due():
    now = datetime(2026, 11, 20, 12, 0)
    assert tm.compact_due(None, now - timedelta(hours=1), now) is True
    assert tm.compact_due(tm.THIS_MACHINE_ROLE, None, now) is True
    assert tm.compact_due(tm.THIS_MACHINE_ROLE, now - timedelta(hours=2), now) is False
    assert tm.compact_due(tm.THIS_MACHINE_ROLE, now - timedelta(hours=25), now) is True


@pytest.mark.unit
def test_estimate_size_counts_and_excludes(tmp_path):
    root = tmp_path / "src"
    (root / "keep").mkdir(parents=True)
    (root / "keep" / "a").write_bytes(b"x" * 100)
    (root / ".cache").mkdir()
    (root / ".cache" / "b").write_bytes(b"x" * 1000)
    estimate = tm.estimate_size([str(root)], ["**/.cache"])
    assert estimate.bytes == 100 and estimate.complete is True


def _patches():
    return (
        patch(
            "app.api.repositories.initialize_borg_repository",
            new=AsyncMock(return_value={"success": True}),
        ),
        patch("app.api.repositories.mqtt_service.sync_state_with_db"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_creates_flagged_plan_and_repo(test_db, admin_user, tmp_path):
    host = _host(tmp_path, "home")
    init, mqtt = _patches()
    with init, mqtt, patch.object(tm, "_host_root", return_value=host):
        result = await tm.setup_this_machine(test_db, admin_user)

    plan = test_db.get(BackupPlan, result.plan_id)
    assert plan.name == "This machine" and plan.system_role == "this_machine"
    assert plan.cron_expression == "0 * * * *" and plan.schedule_enabled
    assert (
        plan.prune_keep_hourly,
        plan.prune_keep_daily,
        plan.prune_keep_weekly,
        plan.prune_keep_monthly,
        plan.prune_keep_yearly,
    ) == (24, 7, 4, 6, 0)
    assert plan.run_prune_after and plan.run_compact_after
    repo = test_db.get(Repository, result.repository_id)
    assert repo.name == "This machine (local)" and repo.system_role == "this_machine"
    assert repo.path == str(host / "var/backups/borg-ui")
    assert repo.encryption == "repokey-blake2"
    assert repo.restore_check_cron_expression == "0 4 * * 0"
    assert result.in_data_volume is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_is_idempotent(test_db, admin_user, tmp_path):
    host = _host(tmp_path)
    init, mqtt = _patches()
    with init, mqtt, patch.object(tm, "_host_root", return_value=host):
        first = await tm.setup_this_machine(test_db, admin_user)
        second = await tm.setup_this_machine(test_db, admin_user)
    assert (first.plan_id, first.repository_id) == (
        second.plan_id,
        second.repository_id,
    )
    assert test_db.query(BackupPlan).count() == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_setup_without_host_root_uses_data_volume(
    test_db, admin_user, tmp_path, monkeypatch
):
    monkeypatch.setattr(tm.settings, "data_dir", str(tmp_path / "data"))
    init, mqtt = _patches()
    with init, mqtt, patch.object(tm, "_host_root", return_value=None):
        result = await tm.setup_this_machine(test_db, admin_user)
    assert result.in_data_volume is True
    repo = test_db.get(Repository, result.repository_id)
    assert repo.path == str(tmp_path / "data" / "this-machine")


@pytest.mark.unit
def test_setup_route_requires_admin(test_client, operator_headers):
    assert (
        test_client.post(
            "/api/this-machine/setup", headers=operator_headers
        ).status_code
        == 403
    )
    assert (
        test_client.get(
            "/api/this-machine/estimate", headers=operator_headers
        ).status_code
        == 403
    )


@pytest.mark.unit
def test_status_route_reports_not_configured(test_client, admin_headers):
    body = test_client.get("/api/this-machine", headers=admin_headers).json()
    assert body["configured"] is False and body["plan_id"] is None
