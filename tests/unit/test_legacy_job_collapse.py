"""The one-off copy of legacy job rows into `operations` (spec section 14)."""

import json
from datetime import datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import MetaData, insert, select

from app.database import legacy_job_tables as legacy
from app.database.db_upgrade import _alembic_config, _engine
from app.database.legacy_job_collapse import collapse_legacy_job_tables
from app.services.operations.package_facade import _HEADER_PREFIX

PRE_COLLAPSE = "b8c9d0e1f2a3"
NOW = datetime(2026, 9, 1, 12, 0, 0)


@pytest.fixture
def engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, PRE_COLLAPSE)
        connection.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def log_dir(tmp_path):
    return tmp_path / "logs"


def _tables(connection):
    meta = MetaData()
    meta.reflect(bind=connection)
    return meta.tables


def _seed_repository(connection, repo_id=1, path="/srv/repo"):
    tables = _tables(connection)
    connection.execute(
        insert(tables["repositories"]).values(
            id=repo_id,
            name=f"repo{repo_id}",
            path=path,
            encryption="none",
            compression="lz4",
            mode="full",
            execution_target="local",
            executor_type="server",
            borg_version=1,
            check_schedule_enabled=False,
            check_timezone="UTC",
            notify_on_check_success=False,
            notify_on_check_failure=False,
            restore_check_schedule_enabled=False,
            restore_check_timezone="UTC",
            restore_check_full_archive=False,
            restore_check_canary_enabled=False,
            notify_on_restore_check_success=False,
            notify_on_restore_check_failure=False,
            created_at=NOW,
        )
    )


def _insert_rows(connection, table, rows):
    """One statement per row: an executemany would bind the first row's keys
    for every row, silently dropping the columns only later rows name."""
    for row in rows:
        connection.execute(insert(table).values(**row))


def _operations(connection, kind):
    tables = _tables(connection)
    ops = tables["operations"]
    return (
        connection.execute(select(ops).where(ops.c.kind == kind).order_by(ops.c.id))
        .mappings()
        .all()
    )


@pytest.mark.unit
def test_backup_rows_become_backup_operations_with_details(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        connection.execute(
            insert(legacy.backup_jobs).values(
                id=7,
                repository="/srv/repo",
                repository_id=1,
                status="completed",
                started_at=NOW,
                completed_at=NOW + timedelta(minutes=5),
                progress=100,
                progress_percent=100.0,
                archive_name="daily-1",
                original_size=10,
                compressed_size=5,
                deduplicated_size=2,
                nfiles=3,
                execution_mode="local",
                route_strategy="local",
                created_at=NOW,
                scheduled_job_id=None,
                maintenance_status="maintenance_completed",
            )
        )
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    assert report.copied["backup_jobs"] == 1
    with engine.connect() as connection:
        [op] = _operations(connection, "backup")
        assert op["category"] == "backup"
        assert op["status"] == "completed"
        assert op["trigger"] == "manual"
        assert op["priority"] == 0
        assert op["repository_id"] == 1
        assert op["execution_mode"] == "server"
        assert op["progress_percent"] == 100.0
        assert op["started_at"] == NOW
        assert op["created_at"] == NOW
        assert len(op["run_id"]) == 36
        details = _tables(connection)["operation_backup_details"]
        [row] = (
            connection.execute(
                select(details).where(details.c.operation_id == op["id"])
            )
            .mappings()
            .all()
        )
        assert row["archive_name"] == "daily-1"
        assert row["nfiles"] == 3
        assert row["maintenance_status"] == "maintenance_completed"
        assert row["retry_attempt"] == 1
    assert report.id_maps["backup_jobs"] == {7: op["id"]}


@pytest.mark.unit
def test_backup_trigger_and_status_words(engine, log_dir):
    """pending -> queued; a plan run row is trigger plan; a schedule row is
    trigger schedule at priority 5; a retry row is trigger retry."""
    with engine.begin() as connection:
        _seed_repository(connection)
        tables = _tables(connection)
        connection.execute(
            insert(tables["scheduled_jobs"]).values(
                id=3,
                name="nightly",
                cron_expression="0 2 * * *",
                enabled=True,
                timezone="UTC",
                run_repository_scripts=False,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(tables["backup_plan_runs"]).values(
                id=9,
                trigger="manual",
                status="completed",
                retry_attempt=1,
                created_at=NOW,
            )
        )
        _insert_rows(
            connection,
            legacy.backup_jobs,
            [
                dict(
                    id=1,
                    repository="/srv/repo",
                    repository_id=1,
                    status="pending",
                    created_at=NOW,
                ),
                dict(
                    id=2,
                    repository="/srv/repo",
                    repository_id=1,
                    status="failed",
                    scheduled_job_id=3,
                    created_at=NOW,
                ),
                dict(
                    id=3,
                    repository="/srv/repo",
                    repository_id=1,
                    status="completed",
                    backup_plan_run_id=9,
                    created_at=NOW,
                ),
                dict(
                    id=4,
                    repository="/srv/repo",
                    repository_id=1,
                    status="cancelled",
                    retry_source_job_id=2,
                    retry_original_job_id=2,
                    retry_attempt=2,
                    created_at=NOW,
                ),
            ],
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        ops = _operations(connection, "backup")
        by_old = {op["params"]["legacy_id"]: op for op in ops}
        assert by_old[1]["status"] == "queued"
        assert by_old[2]["trigger"] == "schedule" and by_old[2]["priority"] == 5
        assert by_old[2]["scheduled_job_id"] == 3
        assert by_old[3]["trigger"] == "plan" and by_old[3]["backup_plan_run_id"] == 9
        assert by_old[4]["trigger"] == "retry"
        details = _tables(connection)["operation_backup_details"]
        [retry] = (
            connection.execute(
                select(details).where(details.c.operation_id == by_old[4]["id"])
            )
            .mappings()
            .all()
        )
        assert retry["retry_source_job_id"] == by_old[2]["id"]
        assert retry["retry_original_job_id"] == by_old[2]["id"]


@pytest.mark.unit
def test_backup_repository_resolved_by_path_when_id_missing(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection, repo_id=4, path="/srv/old")
        _insert_rows(
            connection,
            legacy.backup_jobs,
            [
                dict(id=1, repository="/srv/old/", status="completed", created_at=NOW),
                dict(id=2, repository="/nowhere", status="failed", created_at=NOW),
            ],
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        ops = _operations(connection, "backup")
        by_old = {op["params"]["legacy_id"]: op for op in ops}
        assert by_old[1]["repository_id"] == 4
        assert by_old[2]["repository_id"] is None
        assert by_old[2]["params"]["repository"] == "/nowhere"


@pytest.mark.unit
def test_backup_inline_logs_become_the_operation_log_file(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        log_dir.mkdir()
        (log_dir / "backup_job_2.log").write_text("from file\n")
        _insert_rows(
            connection,
            legacy.backup_jobs,
            [
                dict(
                    id=1,
                    repository="/srv/repo",
                    repository_id=1,
                    status="failed",
                    logs="inline text",
                    created_at=NOW,
                ),
                dict(
                    id=2,
                    repository="/srv/repo",
                    repository_id=1,
                    status="failed",
                    logs="Logs saved to: backup_job_2.log",
                    created_at=NOW,
                ),
                dict(
                    id=3,
                    repository="/srv/repo",
                    repository_id=1,
                    status="completed",
                    log_file_path=str(log_dir / "backup_job_2.log"),
                    created_at=NOW,
                ),
            ],
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        ops = {
            op["params"]["legacy_id"]: op for op in _operations(connection, "backup")
        }
    assert ops[1]["log_file_path"] == str(log_dir / f"operation_{ops[1]['id']}.log")
    assert (log_dir / f"operation_{ops[1]['id']}.log").read_text() == "inline text"
    assert ops[2]["log_file_path"] == str(log_dir / "backup_job_2.log")
    assert ops[3]["log_file_path"] == str(log_dir / "backup_job_2.log")


@pytest.mark.unit
def test_links_are_rewritten_to_the_new_ids(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        tables = _tables(connection)
        connection.execute(
            insert(legacy.backup_jobs).values(
                id=5,
                repository="/srv/repo",
                repository_id=1,
                status="completed",
                created_at=NOW,
            )
        )
        connection.execute(
            insert(tables["agent_machines"]).values(
                id=1,
                name="m",
                agent_id="agent-1",
                token_hash="x",
                token_prefix="x",
                status="online",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            insert(tables["agent_jobs"]).values(
                id=1,
                agent_machine_id=1,
                backup_job_id=5,
                job_type="backup",
                status="completed",
                payload={},
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            insert(tables["backup_plan_runs"]).values(
                id=1,
                trigger="manual",
                status="completed",
                retry_attempt=1,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(tables["backup_plan_run_repositories"]).values(
                id=1,
                backup_plan_run_id=1,
                repository_id=1,
                backup_job_id=5,
                status="completed",
            )
        )
        connection.execute(
            insert(tables["script_executions"]).values(
                id=1,
                backup_job_id=5,
                hook_type="pre_backup",
                status="completed",
            )
        )
        connection.execute(
            insert(legacy.backup_job_retry_lineage).values(
                id=1,
                original_job_id=5,
                retry_source_job_id=5,
                attempt_number=2,
                requested_at=NOW,
                created_job_id=5,
                request_snapshot={"kind": "backup_job_retry"},
            )
        )
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    new_id = report.id_maps["backup_jobs"][5]
    with engine.connect() as connection:
        tables = _tables(connection)
        assert (
            connection.execute(select(tables["agent_jobs"].c.operation_id)).scalar()
            == new_id
        )
        assert (
            connection.execute(
                select(tables["backup_plan_run_repositories"].c.backup_operation_id)
            ).scalar()
            == new_id
        )
        assert (
            connection.execute(
                select(tables["script_executions"].c.operation_id)
            ).scalar()
            == new_id
        )
        [lineage] = (
            connection.execute(select(tables["operation_backup_retry_lineage"]))
            .mappings()
            .all()
        )
        assert (
            lineage["original_job_id"],
            lineage["retry_source_job_id"],
            lineage["created_operation_id"],
        ) == (new_id, new_id, new_id)
        assert lineage["request_snapshot"] == {"kind": "backup_job_retry"}


@pytest.mark.unit
def test_restore_rows(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        connection.execute(
            insert(legacy.restore_jobs).values(
                id=1,
                repository="/srv/repo",
                archive="daily-1",
                destination="/tmp/out",
                status="completed",
                progress=100,
                nfiles=4,
                original_size=100,
                restored_size=100,
                restore_speed=1.5,
                destination_type="local",
                repository_type="local",
                logs="restored ok",
                created_at=NOW,
            )
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        [op] = _operations(connection, "restore")
        assert op["category"] == "restore" and op["repository_id"] == 1
        assert op["execution_mode"] == "server"
        details = _tables(connection)["operation_restore_details"]
        [row] = connection.execute(select(details)).mappings().all()
        assert (
            row["archive"],
            row["destination"],
            row["nfiles"],
            row["restored_size"],
        ) == ("daily-1", "/tmp/out", 4, 100)
        assert (log_dir / f"operation_{op['id']}.log").read_text() == "restored ok"


@pytest.mark.unit
def test_maintenance_rows_carry_their_inputs_in_params(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        connection.execute(
            insert(legacy.check_jobs).values(
                id=1,
                repository_id=1,
                repository_path="/srv/repo",
                status="completed",
                progress=100,
                progress_message="done",
                max_duration=3600,
                extra_flags="--verify-data",
                scheduled_check=True,
                process_pid=12,
                process_start_time=34,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(legacy.restore_check_jobs).values(
                id=1,
                repository_id=1,
                archive_name="daily-1",
                status="needs_backup",
                probe_paths=json.dumps(["/etc"]),
                full_archive=False,
                scheduled_restore_check=False,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(legacy.compact_jobs).values(
                id=1,
                repository_id=1,
                status="running",
                scheduled_compact=True,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(legacy.prune_jobs).values(
                id=1,
                repository_id=1,
                status="pending",
                scheduled_prune=False,
                created_at=NOW,
            )
        )
        connection.execute(
            insert(legacy.delete_archive_jobs).values(
                id=1,
                repository_id=1,
                archive_name="daily-0",
                status="failed",
                error_message="boom",
                created_at=NOW,
            )
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        [check] = _operations(connection, "check")
        assert check["params"] == {
            "legacy_id": 1,
            "max_duration": 3600,
            "extra_flags": "--verify-data",
            "scheduled_check": True,
        }
        assert (
            check["trigger"] == "schedule"
            and check["process_pid"] == 12
            and check["process_start_time"] == 34.0
        )
        assert check["progress_message"] == "done"
        [rc] = _operations(connection, "restore_check")
        assert rc["status"] == "skipped" and rc["skip_reason"] == "needs_backup"
        assert rc["params"]["probe_paths"] == ["/etc"]
        assert rc["params"]["archive_name"] == "daily-1"
        [compact] = _operations(connection, "compact")
        assert compact["status"] == "running"
        assert compact["params"]["scheduled_compact"] is True
        [prune] = _operations(connection, "prune")
        assert prune["status"] == "queued" and prune["trigger"] == "manual"
        [delete] = _operations(connection, "delete_archive")
        assert delete["params"]["archive_name"] == "daily-0"
        assert delete["error_message"] == "boom"


@pytest.mark.unit
def test_executed_wipes_move_and_previews_stay(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        _insert_rows(
            connection,
            legacy.repository_wipe_jobs,
            [
                dict(
                    id=1,
                    repository_id=1,
                    status="previewed",
                    phase="preview",
                    archive_count=2,
                    run_compact=True,
                    created_at=NOW,
                ),
                dict(
                    id=2,
                    repository_id=1,
                    status="completed_compaction_failed",
                    phase="compact",
                    archive_count=2,
                    run_compact=True,
                    confirmed_at=NOW,
                    started_at=NOW,
                    completed_at=NOW,
                    created_at=NOW,
                ),
                dict(
                    id=3,
                    repository_id=1,
                    status="failed_partial",
                    phase="delete",
                    archive_count=2,
                    run_compact=False,
                    created_at=NOW,
                ),
            ],
        )
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    assert report.copied["repository_wipe_jobs"] == 2
    with engine.connect() as connection:
        remaining = (
            connection.execute(select(legacy.repository_wipe_jobs.c.id)).scalars().all()
        )
        assert remaining == [1]
        ops = {op["params"]["legacy_id"]: op for op in _operations(connection, "wipe")}
        assert ops[2]["status"] == "completed_with_warnings"
        assert ops[3]["status"] == "failed"
        details = _tables(connection)["operation_wipe_details"]
        rows = {
            r["operation_id"]: r
            for r in connection.execute(select(details)).mappings().all()
        }
        assert rows[ops[2]["id"]]["phase"] == "compact_failed"
        assert rows[ops[3]["id"]]["phase"] == "delete_failed_partial"
        assert rows[ops[3]["id"]]["run_compact"] is False


@pytest.mark.unit
def test_rclone_and_package_rows(engine, log_dir):
    with engine.begin() as connection:
        _seed_repository(connection)
        tables = _tables(connection)
        connection.execute(
            insert(tables["installed_packages"]).values(
                id=1,
                name="rsync",
                install_command="apt-get install -y rsync",
                status="installed",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        connection.execute(
            insert(legacy.rclone_sync_jobs).values(
                id=1,
                repository_id=1,
                direction="push",
                operation="hydrate",
                status="completed",
                triggered_by="initial",
                bytes_transferred=10,
                files_transferred=2,
                log_path="/var/log/x",
                log_text="synced",
                created_at=NOW,
            )
        )
        connection.execute(
            insert(legacy.package_install_jobs).values(
                id=1,
                package_id=1,
                status="installing",
                exit_code=None,
                stdout="out",
                stderr="err",
                created_at=NOW,
            )
        )
        collapse_legacy_job_tables(connection, log_dir=log_dir)
    with engine.connect() as connection:
        [rclone] = _operations(connection, "rclone_sync")
        assert rclone["category"] == "mirror"
        assert rclone["trigger"] == "import"
        assert rclone["log_file_path"] == "/var/log/x"
        details = _tables(connection)["operation_rclone_details"]
        [row] = connection.execute(select(details)).mappings().all()
        assert (
            row["operation"],
            row["direction"],
            row["bytes_transferred"],
            row["log_text"],
        ) == ("hydrate", "push", 10, "synced")
        [package] = _operations(connection, "package_install")
        assert package["status"] == "running" and package["category"] == "system"
        assert package["repository_id"] is None
        assert package["params"] == {"legacy_id": 1, "package_id": 1}
        body = (log_dir / f"operation_{package['id']}.log").read_text()
        assert body.startswith(f"{_HEADER_PREFIX} stdout=3 stderr=3\n")
        assert body.endswith("outerr")


@pytest.mark.unit
def test_rows_whose_repository_is_gone_are_skipped_for_kinds_that_need_one(
    engine, log_dir
):
    """A check row's repository_id has no ondelete, so SQLite installs can
    hold rows pointing at deleted repositories. `operations.repository_id`
    is a real foreign key on both dialects; those rows cannot be copied."""
    with engine.connect() as connection:
        # The dangling row is the thing under test, so foreign keys come off
        # for the seed. The pragma has to run before any transaction opens.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.execute(
            insert(legacy.check_jobs).values(
                id=1, repository_id=99, status="completed", created_at=NOW
            )
        )
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
        connection.commit()
    assert report.copied["check_jobs"] == 0 and report.skipped["check_jobs"] == 1


@pytest.mark.unit
def test_copy_is_idempotent_on_an_empty_legacy_set(engine, log_dir):
    with engine.begin() as connection:
        report = collapse_legacy_job_tables(connection, log_dir=log_dir)
    assert sum(report.copied.values()) == 0
