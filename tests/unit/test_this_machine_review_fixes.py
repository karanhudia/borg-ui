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


@pytest.mark.unit
def test_read_all_is_a_backup_service_param():
    from app.services.operations.backup_facade import SERVICE_PARAMS

    assert "read_all" in SERVICE_PARAMS


@pytest.mark.unit
def test_read_all_env_only_when_asked():
    assert sb.read_all_env(True) == {"BORG_UI_READ_ALL": "1"}
    assert sb.read_all_env(False) == {}


@pytest.mark.unit
def test_only_admins_edit_the_system_plan(
    test_client, operator_headers, test_db, operator_user
):
    operator_user.all_repositories_role = "operator"
    plan = BackupPlan(
        name="This machine",
        source_directories='["/local/etc"]',
        system_role=tm.THIS_MACHINE_ROLE,
        created_at=datetime.utcnow(),
    )
    test_db.add(plan)
    test_db.commit()
    response = test_client.put(
        f"/api/backup-plans/{plan.id}",
        json={"name": "x", "source_directories": ["/local/root"], "repositories": []},
        headers=operator_headers,
    )
    assert response.status_code == 403
    assert (
        response.json()["detail"]["key"] == "backend.errors.thisMachine.adminRequired"
    )


# --- CodeRabbit round 1 ---


@pytest.mark.unit
def test_failed_staging_leaves_an_empty_folder_borg_can_open(
    test_db, tmp_path, monkeypatch
):
    monkeypatch.setattr(sb.settings, "data_dir", str(tmp_path))
    with patch.object(sb, "write_staging", side_effect=OSError("boom")):
        assert sb.run_self_backup_step(test_db).startswith(sb.WARNING_PREFIX)
    staging = sb.staging_dir(tmp_path)
    assert staging.is_dir() and not any(staging.iterdir())


@pytest.mark.unit
def test_staging_is_owner_only(test_db, tmp_path, monkeypatch):
    import sqlite3
    import stat

    with sqlite3.connect(tmp_path / "borg.db") as conn:
        conn.execute("create table t (x)")
    monkeypatch.setattr(
        sb.settings, "database_url", f"sqlite:///{tmp_path / 'borg.db'}"
    )
    monkeypatch.setattr(sb.settings, "ssh_keys_dir", str(tmp_path / "ssh_keys"))
    sb.write_staging(
        test_db, tmp_path, app_version="v", alembic_revision="r", hostname="h"
    )
    mode = stat.S_IMODE(sb.staging_dir(tmp_path).stat().st_mode)
    assert mode == 0o700


@pytest.mark.unit
def test_self_backup_includes_borg_keyfiles(tmp_path, monkeypatch):
    (tmp_path / "borg_keys").mkdir()
    monkeypatch.setattr(sb.settings, "ssh_keys_dir", str(tmp_path / "ssh_keys"))
    assert str(tmp_path / "borg_keys") in sb.self_backup_paths(tmp_path)


@pytest.mark.unit
def test_same_name_folders_are_not_excluded_on_the_host(tmp_path):
    host = tmp_path / "local"
    (host / "etc").mkdir(parents=True)
    excludes = tm.exclude_patterns(
        host, host / "var/backups/borg-ui", tmp_path / "data", in_data_volume=False
    )
    assert not _borg_fm_excluded(str(host / "home/alex/this-machine/notes"), excludes)
    fallback = tm.exclude_patterns(
        host, tmp_path / "data/this-machine", tmp_path / "data", in_data_volume=True
    )
    assert _borg_fm_excluded(
        str(host / "var/lib/docker/volumes/v/_data/this-machine/data"), fallback
    )


@pytest.mark.unit
def test_status_reports_the_saved_repository_location(
    test_client, admin_headers, test_db, tmp_path, monkeypatch
):
    monkeypatch.setattr(tm.settings, "data_dir", str(tmp_path / "data"))
    test_db.add(
        Repository(
            name="This machine (local)",
            path=str(tmp_path / "data" / "this-machine"),
            encryption="none",
            repository_type="local",
            mode="full",
            system_role=tm.THIS_MACHINE_ROLE,
        )
    )
    test_db.commit()
    host = tmp_path / "local"
    (host / "etc").mkdir(parents=True)
    with patch.object(tm, "_host_root", return_value=host):
        body = test_client.get("/api/this-machine", headers=admin_headers).json()
    assert body["in_data_volume"] is True


# --- CodeRabbit round 2 ---


def _sqlite(path):
    import sqlite3

    with sqlite3.connect(path) as conn:
        conn.execute("create table if not exists t (x)")


@pytest.mark.unit
def test_staging_uses_the_active_secret_key(test_db, tmp_path, monkeypatch):
    _sqlite(tmp_path / "borg.db")
    (tmp_path / ".secret_key").write_text("file-key")
    monkeypatch.setattr(sb.settings, "secret_key", "env-key")
    monkeypatch.setattr(
        sb.settings, "database_url", f"sqlite:///{tmp_path / 'borg.db'}"
    )
    monkeypatch.setattr(sb.settings, "ssh_keys_dir", str(tmp_path / "ssh_keys"))
    paths = sb.write_staging(
        test_db, tmp_path, app_version="v", alembic_revision="r", hostname="h"
    )
    staged = sb.staging_dir(tmp_path) / sb.SECRET_KEY_NAME
    assert staged.read_text() == "env-key"
    assert str(tmp_path / ".secret_key") not in paths


@pytest.mark.unit
def test_sqlite_url_options_are_not_part_of_the_filename(
    test_db, tmp_path, monkeypatch
):
    _sqlite(tmp_path / "borg.db")
    monkeypatch.setattr(
        sb.settings,
        "database_url",
        f"sqlite:///{tmp_path / 'borg.db'}?check_same_thread=false",
    )
    monkeypatch.setattr(sb.settings, "ssh_keys_dir", str(tmp_path / "ssh_keys"))
    sb.write_staging(
        test_db, tmp_path, app_version="v", alembic_revision="r", hostname="h"
    )
    import sqlite3

    with sqlite3.connect(sb.staging_dir(tmp_path) / sb.SNAPSHOT_NAME) as conn:
        tables = {r[0] for r in conn.execute("select name from sqlite_master")}
    assert "t" in tables


@pytest.mark.unit
def test_a_collector_that_raises_anything_is_skipped(tmp_path):
    def broken(_root, _out):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    def fine(_root, out):
        (out / "ok").write_text("x")
        return True

    with patch.object(sb, "_REBUILD_COLLECTORS", (("broken", broken), ("fine", fine))):
        assert sb.collect_rebuild_inputs(tmp_path, tmp_path) == ["fine"]


# --- PR #1587 review ---


@pytest.mark.unit
def test_root_only_source_roots_are_kept(tmp_path):
    host = tmp_path / "local"
    (host / "etc").mkdir(parents=True)
    real_is_dir = Path.is_dir

    def is_dir(self):
        if self.name == "volumes":
            raise PermissionError(13, "Permission denied", str(self))
        return real_is_dir(self)

    with patch.object(Path, "is_dir", is_dir):
        sources = tm.source_directories(host)
    assert str(host / "var/lib/docker/volumes") in sources


@pytest.mark.unit
def test_read_all_backups_skip_the_source_existence_preflight(tmp_path):
    from app.services.backup_service import backup_service

    missing = str(tmp_path / "behind-root-only/volumes")
    backup_service._validate_local_source_paths_exist([missing], read_all=True)
    with pytest.raises(Exception):
        backup_service._validate_local_source_paths_exist([missing])


@pytest.mark.unit
def test_only_admins_update_a_system_repository(
    test_client, operator_headers, test_db, operator_user
):
    operator_user.all_repositories_role = "operator"
    repo = Repository(
        name="This machine (local)",
        path="/backups/tm",
        encryption="none",
        repository_type="local",
        mode="full",
        system_role=tm.THIS_MACHINE_ROLE,
    )
    test_db.add(repo)
    test_db.commit()
    response = test_client.put(
        f"/api/repositories/{repo.id}",
        json={"custom_flags": "--pattern R /local/root"},
        headers=operator_headers,
    )
    # Already admin-only for every repository (ENDPOINT_POLICIES); keep it so.
    assert response.status_code == 403
    assert response.json()["detail"]["key"] == "backend.errors.repo.adminAccessRequired"


def _host_root(tmp_path):
    host = tmp_path / "local"
    (host / "etc").mkdir(parents=True, exist_ok=True)
    (host / "etc/os-release").write_text("ID=debian\n")
    return host


@pytest.mark.unit
async def test_setup_adopts_an_unflagged_plan_left_by_a_crash(
    test_db, admin_user, tmp_path
):
    from unittest.mock import AsyncMock

    host = _host_root(tmp_path)
    with (
        patch(
            "app.api.repositories.initialize_borg_repository",
            new=AsyncMock(return_value={"success": True}),
        ),
        patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        patch.object(tm, "_host_root", return_value=host),
    ):
        first = await tm.setup_this_machine(test_db, admin_user)
        plan = test_db.get(BackupPlan, first.plan_id)
        plan.system_role = None  # the crash: role never committed
        test_db.commit()
        again = await tm.setup_this_machine(test_db, admin_user)
    assert again.plan_id == first.plan_id
    assert test_db.get(BackupPlan, first.plan_id).system_role == tm.THIS_MACHINE_ROLE


@pytest.mark.unit
async def test_setup_retries_a_missing_restore_check(test_db, admin_user, tmp_path):
    from unittest.mock import AsyncMock

    host = _host_root(tmp_path)
    with (
        patch(
            "app.api.repositories.initialize_borg_repository",
            new=AsyncMock(return_value={"success": True}),
        ),
        patch("app.api.repositories.mqtt_service.sync_state_with_db"),
        patch.object(tm, "_host_root", return_value=host),
    ):
        first = await tm.setup_this_machine(test_db, admin_user)
        repo = test_db.get(Repository, first.repository_id)
        repo.restore_check_cron_expression = None
        test_db.query(BackupPlan).delete()
        test_db.commit()
        await tm.setup_this_machine(test_db, admin_user)
    test_db.expire_all()
    assert test_db.get(Repository, first.repository_id).restore_check_cron_expression


@pytest.mark.unit
async def test_setup_reports_the_reused_repository_location(
    test_db, admin_user, tmp_path, monkeypatch
):
    monkeypatch.setattr(tm.settings, "data_dir", str(tmp_path / "data"))
    test_db.add(
        Repository(
            name="This machine (local)",
            path=str(tmp_path / "data" / "this-machine"),
            encryption="none",
            repository_type="local",
            mode="full",
            system_role=tm.THIS_MACHINE_ROLE,
            restore_check_cron_expression="0 4 * * 0",
        )
    )
    test_db.commit()
    host = _host_root(tmp_path)
    with patch.object(tm, "_host_root", return_value=host):
        result = await tm.setup_this_machine(test_db, admin_user)
    assert result.in_data_volume is True


@pytest.mark.unit
async def test_concurrent_setup_conflict_is_not_a_500(test_db, admin_user, tmp_path):
    from sqlalchemy.exc import IntegrityError

    host = _host_root(tmp_path)
    with (
        patch.object(tm, "_host_root", return_value=host),
        patch.object(
            tm, "_create_repository", side_effect=IntegrityError("x", {}, Exception())
        ),
    ):
        with pytest.raises(tm.HTTPException) as exc:
            await tm.setup_this_machine(test_db, admin_user)
    assert exc.value.status_code == 409


@pytest.mark.unit
def test_staging_is_cleared_in_lease_protected_recovery():
    import inspect

    from app import main

    assert "clear_staging_at_startup" in inspect.getsource(
        main._recover_interrupted_work
    )
    assert "clear_staging_at_startup" not in inspect.getsource(main.startup_event)
