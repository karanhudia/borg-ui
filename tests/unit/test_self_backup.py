import json
import sqlite3
from datetime import datetime
from unittest.mock import patch

import pytest

from app.database.models import BackupPlan, BackupPlanRepository, Repository
from app.services import self_backup as sb
from app.services.backup_plan_execution_service import BackupPlanExecutionService
from app.services.this_machine import THIS_MACHINE_ROLE


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    db_file = data / "borg.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("create table t (x)")
        conn.execute("insert into t values (1)")
    (data / ".secret_key").write_text("s3cret")
    (data / "ssh_keys").mkdir()
    monkeypatch.setattr(sb.settings, "data_dir", str(data))
    monkeypatch.setattr(sb.settings, "database_url", f"sqlite:///{db_file}")
    monkeypatch.setattr(sb.settings, "ssh_keys_dir", str(data / "ssh_keys"))
    return data


def _write(db, data_dir, host_root=None):
    return sb.write_staging(
        db,
        data_dir,
        app_version="2.4.10",
        alembic_revision="abc123",
        hostname="box",
        host_root=host_root,
    )


@pytest.mark.unit
def test_write_staging_copies_db_and_manifest(test_db, data_dir):
    _write(test_db, data_dir)
    staging = sb.staging_dir(data_dir)
    with sqlite3.connect(staging / "borg.db") as conn:
        assert conn.execute("select x from t").fetchone() == (1,)
    manifest = json.loads((staging / "manifest.json").read_text())
    assert manifest["alembic_revision"] == "abc123"
    assert manifest["borg_ui_version"] == "2.4.10"
    assert manifest["hostname"] == "box" and manifest["format"] == 1


@pytest.mark.unit
def test_write_staging_empties_leftovers(test_db, data_dir):
    staging = sb.staging_dir(data_dir)
    staging.mkdir(parents=True)
    (staging / "stale").write_text("old")
    _write(test_db, data_dir)
    assert not (staging / "stale").exists()


@pytest.mark.unit
def test_write_staging_refuses_postgres(test_db, data_dir, monkeypatch):
    monkeypatch.setattr(sb.settings, "database_url", "postgresql://u:p@h/db")
    with pytest.raises(sb.SelfBackupUnsupported):
        _write(test_db, data_dir)


@pytest.mark.unit
def test_clear_staging_tolerates_missing(data_dir):
    sb.clear_staging(data_dir)
    assert not sb.staging_dir(data_dir).exists()


@pytest.mark.unit
def test_rebuild_inputs_skip_missing_tools(tmp_path):
    root = tmp_path / "host"
    (root / "var/lib/dpkg").mkdir(parents=True)
    (root / "var/lib/dpkg/status").write_text("Package: bash\n")
    (root / "var/spool/cron/crontabs").mkdir(parents=True)
    (root / "var/spool/cron/crontabs/root").write_text("0 * * * * true\n")
    staging = tmp_path / "staging"
    staging.mkdir()
    with patch.object(sb.shutil, "which", return_value=None):
        written = sb.collect_rebuild_inputs(root, staging)
    assert set(written) == {"dpkg-status", "crontabs"}
    assert (staging / "rebuild/crontabs/crontabs/root").exists()


@pytest.mark.unit
def test_rebuild_inputs_without_host_root(tmp_path):
    assert sb.collect_rebuild_inputs(None, tmp_path) == []


@pytest.mark.unit
def test_self_backup_paths_only_existing(data_dir):
    paths = sb.self_backup_paths(data_dir)
    assert paths == [
        str(sb.staging_dir(data_dir)),
        str(data_dir / ".secret_key"),
        str(data_dir / "ssh_keys"),
    ]


@pytest.mark.unit
def test_with_self_backup_paths_extends_local_location():
    extra = ["/data/self-backup/staging", "/data/.secret_key"]
    dirs, locations = sb.with_self_backup_paths(
        ["/local/etc"], [{"source_type": "local", "paths": ["/local/etc"]}], extra
    )
    assert dirs == ["/local/etc", *extra]
    assert locations == [{"source_type": "local", "paths": ["/local/etc", *extra]}]


def _plan(test_db, role):
    repo = Repository(
        name=f"r-{role}",
        path=f"/repos/{role}",
        encryption="none",
        repository_type="local",
        mode="full",
    )
    test_db.add(repo)
    test_db.flush()
    plan = BackupPlan(
        name=f"p-{role}",
        source_directories='["/local/etc"]',
        system_role=role,
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
    return plan, [link]


@pytest.mark.unit
def test_system_plan_context_includes_self_backup_paths(test_db, data_dir):
    plan, links = _plan(test_db, THIS_MACHINE_ROLE)
    context, _ = BackupPlanExecutionService._run_context(plan, links)
    assert str(sb.staging_dir(data_dir)) in context.source_directories
    assert any(
        str(sb.staging_dir(data_dir)) in location["paths"]
        for location in context.source_locations
    )


@pytest.mark.unit
def test_user_plan_context_has_no_self_backup_paths(test_db, data_dir):
    plan, links = _plan(test_db, None)
    context, _ = BackupPlanExecutionService._run_context(plan, links)
    assert context.source_directories == ["/local/etc"]


@pytest.mark.unit
def test_self_backup_verdict_turns_failure_into_warning(test_db, data_dir):
    with patch.object(sb, "write_staging", side_effect=OSError("disk full")):
        warning = sb.run_self_backup_step(test_db)
    assert warning.startswith("Borg UI settings were not included in this snapshot")
    assert "disk full" in warning


@pytest.mark.unit
def test_self_backup_step_success_has_no_warning(test_db, data_dir):
    assert sb.run_self_backup_step(test_db) is None
    assert (sb.staging_dir(data_dir) / "manifest.json").exists()
