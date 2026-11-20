"""Regression tests for the phase 1 review findings."""

import fnmatch
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.database.models import BackupPlan, BackupPlanRepository, Repository
from app.services import self_backup as sb
from app.services import this_machine as tm
from app.services.backup_plan_execution_service import BackupPlanExecutionService


def _borg_fm_excluded(path: str, patterns: list[str]) -> bool:
    """Borg 1's default `fm:` matching: the leading slash is dropped and a
    pattern matches the full path or any leading directory of it."""
    path = path.lstrip("/")
    parts = path.split("/")
    prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    return any(
        fnmatch.fnmatchcase(prefix, p.lstrip("/"))
        for p in patterns
        for prefix in prefixes
    )


@pytest.mark.unit
def test_staged_snapshot_survives_the_plan_excludes(tmp_path):
    host = tmp_path / "local"
    (host / "etc").mkdir(parents=True)
    (host / "etc/os-release").write_text("ID=debian\n")
    data = tmp_path / "data"
    excludes = tm.exclude_patterns(host, host / "var/backups/borg-ui", data)
    staged = sb.staging_dir(data) / sb.SNAPSHOT_NAME
    assert not _borg_fm_excluded(str(staged), excludes)
    assert _borg_fm_excluded(str(data / "borg.db"), excludes)
    assert _borg_fm_excluded(str(data / "borg.db-wal"), excludes)


@pytest.mark.unit
def test_permanent_delete_of_system_repository_removes_record(
    test_client, admin_headers, test_db, tmp_path
):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "config").write_text("[repository]\n")
    (root / "data").mkdir()
    repo = Repository(
        name="This machine (local)",
        path=str(root),
        encryption="none",
        repository_type="local",
        mode="full",
        system_role=tm.THIS_MACHINE_ROLE,
    )
    test_db.add(repo)
    test_db.commit()
    with patch("app.api.repositories.mqtt_service.sync_state_with_db"):
        response = test_client.post(
            f"/api/repositories/{repo.id}/permanent-delete?confirm_system=true",
            json={"understood": True, "confirmation_phrase": repo.name},
            headers=admin_headers,
        )
    assert response.status_code == 200, response.text
    test_db.expire_all()
    assert test_db.get(Repository, repo.id) is None


@pytest.mark.unit
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
def test_unreadable_rebuild_inputs_do_not_drop_the_database(
    test_db, tmp_path, monkeypatch
):
    import sqlite3

    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "borg.db") as conn:
        conn.execute("create table t (x)")
    monkeypatch.setattr(sb.settings, "database_url", f"sqlite:///{data / 'borg.db'}")
    monkeypatch.setattr(sb.settings, "ssh_keys_dir", str(data / "ssh_keys"))
    host = tmp_path / "host"
    crontabs = host / "var/spool/cron/crontabs"
    crontabs.mkdir(parents=True)
    (crontabs / "root").write_text("x")
    wants = host / "etc/systemd/system/multi-user.target.wants"
    wants.mkdir(parents=True)
    os.chmod(crontabs, 0)
    os.chmod(wants, 0)
    try:
        sb.write_staging(
            test_db,
            data,
            app_version="v",
            alembic_revision="r",
            hostname="h",
            host_root=host,
        )
    finally:
        os.chmod(crontabs, 0o755)
        os.chmod(wants, 0o755)
    staging = sb.staging_dir(data)
    assert (staging / sb.SNAPSHOT_NAME).exists()
    assert (staging / "manifest.json").exists()


@pytest.mark.unit
@pytest.mark.skipif(os.geteuid() == 0, reason="root writes everywhere")
def test_unwritable_host_root_falls_back_to_data_volume(tmp_path):
    host = tmp_path / "local"
    (host / "etc").mkdir(parents=True)
    (host / "etc/os-release").write_text("ID=debian\n")
    os.chmod(host, 0o555)
    try:
        location = tm.snapshot_location(host, tmp_path / "data")
    finally:
        os.chmod(host, 0o755)
    assert location == (tmp_path / "data" / "this-machine", True)


@pytest.mark.unit
def test_user_plans_exclude_the_staging_folder(test_db):
    repo = Repository(
        name="r",
        path="/repos/r",
        encryption="none",
        repository_type="local",
        mode="full",
    )
    test_db.add(repo)
    test_db.flush()
    plan = BackupPlan(
        name="mine",
        source_directories='["/local/var/lib/docker/volumes"]',
        created_at=datetime.utcnow(),
    )
    test_db.add(plan)
    test_db.flush()
    link = BackupPlanRepository(
        backup_plan_id=plan.id,
        repository_id=repo.id,
        enabled=True,
        execution_order=1,
        created_at=datetime.utcnow(),
    )
    test_db.add(link)
    test_db.commit()
    context, _ = BackupPlanExecutionService._run_context(plan, [link])
    leaked = "/local/var/lib/docker/volumes/borg_data/_data/self-backup/staging/x"
    assert _borg_fm_excluded(leaked, context.exclude_patterns)


@pytest.mark.unit
def test_startup_clears_leftover_staging(tmp_path, monkeypatch):
    staging = sb.staging_dir(tmp_path)
    staging.mkdir(parents=True)
    (staging / sb.SNAPSHOT_NAME).write_text("old")
    monkeypatch.setattr(sb.settings, "data_dir", str(tmp_path))
    sb.clear_staging_at_startup()
    assert not staging.exists()


@pytest.mark.unit
def test_snapshot_name_is_not_borg_db():
    assert Path(sb.SNAPSHOT_NAME).name != "borg.db"
