from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import json

import pytest

from app.core.borg_router import BorgRouter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_stats_delegates_to_v2_repository_helper(db_session):
    repo = SimpleNamespace(borg_version=2)

    with patch(
        "app.api.repositories.update_repository_stats",
        new=AsyncMock(return_value=True),
    ) as mock_update:
        result = await BorgRouter(repo).update_stats(db_session)

    assert result is True
    mock_update.assert_awaited_once_with(repo, db_session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_stats_delegates_to_v1_repository_helper(db_session):
    repo = SimpleNamespace(borg_version=1)

    with patch(
        "app.api.repositories.update_repository_stats",
        new=AsyncMock(return_value=False),
    ) as mock_update:
        result = await BorgRouter(repo).update_stats(db_session)

    assert result is False
    mock_update.assert_awaited_once_with(repo, db_session)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_total_size_bytes_delegates_to_v2_repository_service():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        remote_path="/usr/bin/borg2",
    )

    with patch(
        "app.services.v2.repository_service.repository_v2_service.calculate_total_size_bytes",
        new=AsyncMock(return_value=4096),
    ) as mock_size:
        size = await BorgRouter(repo).calculate_total_size_bytes(
            env={"BORG_PASSPHRASE": "secret"},
            info_timeout=99,
            use_bypass_lock=True,
            temp_key_file="/tmp/key",
        )

    assert size == 4096
    mock_size.assert_awaited_once_with(
        repo,
        temp_key_file="/tmp/key",
        timeout=30,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calculate_total_size_bytes_uses_v1_info_command():
    repo = SimpleNamespace(
        borg_version=1,
        path="/tmp/repo",
        remote_path="/usr/bin/borg",
    )

    with patch(
        "app.core.borg.borg._execute_command",
        new=AsyncMock(
            return_value={
                "success": True,
                "stdout": '{"cache":{"stats":{"unique_csize": 2048}}}',
            }
        ),
    ) as mock_exec:
        size = await BorgRouter(repo).calculate_total_size_bytes(
            env={"BORG_PASSPHRASE": "secret"},
            info_timeout=55,
            use_bypass_lock=True,
        )

    assert size == 2048
    cmd = mock_exec.await_args.args[0]
    assert "--remote-path" in cmd
    assert "--bypass-lock" in cmd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_delegates_to_agent_when_managed():
    repo = SimpleNamespace(borg_version=2, id=41, executor_type="agent")

    with (
        patch.object(
            BorgRouter, "_run_agent_maintenance", new=AsyncMock()
        ) as mock_agent,
        patch(
            "app.services.v2.check_service.check_v2_service.execute_check",
            new=AsyncMock(),
        ) as mock_v2,
    ):
        await BorgRouter(repo).check(7)

    mock_agent.assert_awaited_once_with(
        job_kind="repository.check",
        maintenance_kind="check",
        maintenance_job_id=7,
    )
    mock_v2.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_maintenance_translates_http_errors_for_background_flows():
    # queue_/wait_for_ raise HTTPException, but _run_agent_maintenance also runs
    # in schedulers / post-backup flows with no HTTP context, so it must not leak
    # an HTTP-specific exception.
    from fastapi import HTTPException

    repo = SimpleNamespace(borg_version=2, id=41, executor_type="agent")
    fake_db = MagicMock()
    fake_db.query.return_value.get.return_value = SimpleNamespace(id=41)
    fake_db.query.return_value.first.return_value = None

    with (
        patch("app.database.database.SessionLocal", return_value=fake_db),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            return_value=SimpleNamespace(id=99),
        ),
        patch(
            "app.services.agent_job_dispatcher.dispatch_agent_job_best_effort",
            new=AsyncMock(),
        ),
        patch(
            "app.services.repository_executor.wait_for_agent_repository_operation_job",
            new=AsyncMock(
                side_effect=HTTPException(status_code=502, detail={"key": "boom"})
            ),
        ),
        pytest.raises(RuntimeError) as excinfo,
    ):
        await BorgRouter(repo)._run_agent_maintenance(
            job_kind="repository.check",
            maintenance_kind="check",
            maintenance_job_id=7,
        )

    assert not isinstance(excinfo.value, HTTPException)
    assert "check" in str(excinfo.value)


@pytest.mark.parametrize(
    "maintenance_kind, job_kind, model_name, extra",
    [
        ("prune", "repository.prune", "PruneJob", {}),
        ("compact", "repository.compact", "CompactJob", {}),
        ("check", "repository.check", "CheckJob", {}),
        (
            "delete_archive",
            "repository.delete_archive",
            "DeleteArchiveJob",
            {"archive_name": "arch-1"},
        ),
    ],
)
@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_agent_maintenance_fails_the_job_when_queue_fails(
    db_session, maintenance_kind, job_kind, model_name, extra
):
    # If the agent job cannot even be queued (e.g. database is locked), the
    # already-created maintenance *_job must be failed closed so it does not
    # orphan and block the repo via admission. A real "database is locked" dooms
    # the session's transaction, so the fail-closed helper has to recover it and
    # still persist 'failed' -- exercise the real helper against a real row, not
    # a mock that would hide that defect. Parameterized across every maintenance
    # kind so a wrong entry in the kind->model mapping cannot slip through.
    from datetime import datetime

    import app.database.models as models_mod
    from app.database.models import PruneJob, Repository

    model = getattr(models_mod, model_name)
    repo_row = Repository(
        name=f"Locked {model_name}",
        path=f"/repos/locked-{maintenance_kind}",
        encryption="none",
        repository_type="local",
    )
    db_session.add(repo_row)
    db_session.flush()
    job = model(
        repository_id=repo_row.id,
        repository_path=repo_row.path,
        status="pending",
        created_at=datetime.utcnow(),
        **extra,
    )
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    repo = SimpleNamespace(borg_version=2, id=repo_row.id, executor_type="agent")

    def _doom_then_fail(*args, **kwargs):
        # Emulate a "database is locked" style failure that dooms the session's
        # transaction: a failed flush (here a NOT NULL violation, stand-in for a
        # failed commit) leaves it requiring a rollback before any further query
        # can run -- exactly the state the fail-closed helper must recover from.
        try:
            db_session.add(PruneJob(repository_path="/x", status="pending"))
            db_session.flush()  # repository_id is NOT NULL -> IntegrityError
        except Exception:
            pass
        raise RuntimeError("database is locked")

    with (
        patch("app.database.database.SessionLocal", return_value=db_session),
        patch(
            "app.services.repository_executor.queue_agent_repository_operation_job",
            side_effect=_doom_then_fail,
        ),
        pytest.raises(RuntimeError, match="database is locked"),
    ):
        await BorgRouter(repo)._run_agent_maintenance(
            job_kind=job_kind,
            maintenance_kind=maintenance_kind,
            maintenance_job_id=job_id,
        )

    # The real _fail_orphaned_maintenance_job ran despite the doomed transaction
    # and persisted the failed state.
    refreshed = db_session.query(model).get(job_id)
    assert refreshed.status == "failed"
    assert refreshed.completed_at is not None
    assert refreshed.error_message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compact_delegates_to_agent_when_managed():
    repo = SimpleNamespace(borg_version=2, id=41, executor_type="agent")

    with (
        patch.object(
            BorgRouter, "_run_agent_maintenance", new=AsyncMock()
        ) as mock_agent,
        patch(
            "app.services.v2.compact_service.compact_v2_service.execute_compact",
            new=AsyncMock(),
        ) as mock_v2,
    ):
        await BorgRouter(repo).compact(7)

    mock_agent.assert_awaited_once_with(
        job_kind="repository.compact",
        maintenance_kind="compact",
        maintenance_job_id=7,
    )
    mock_v2.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_delegates_to_agent_when_managed():
    repo = SimpleNamespace(borg_version=2, id=41, executor_type="agent")

    with (
        patch.object(
            BorgRouter, "_run_agent_maintenance", new=AsyncMock()
        ) as mock_agent,
        patch(
            "app.services.v2.prune_service.prune_v2_service.execute_prune",
            new=AsyncMock(),
        ) as mock_v2,
    ):
        await BorgRouter(repo).prune(
            7, 1, 2, 3, 4, 5, 6, dry_run=True, keep_within="1d"
        )

    mock_agent.assert_awaited_once_with(
        job_kind="repository.prune",
        maintenance_kind="prune",
        maintenance_job_id=7,
        operation={
            "keep_hourly": 1,
            "keep_daily": 2,
            "keep_weekly": 3,
            "keep_monthly": 4,
            "keep_quarterly": 5,
            "keep_yearly": 6,
            "keep_within": "1d",
            "dry_run": True,
        },
    )
    mock_v2.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_delegates_to_v2_service():
    repo = SimpleNamespace(borg_version=2, id=41)

    with patch(
        "app.services.v2.check_service.check_v2_service.execute_check",
        new=AsyncMock(),
    ) as mock_check:
        await BorgRouter(repo).check(7)

    mock_check.assert_awaited_once_with(7, 41)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_delegates_to_v1_service():
    repo = SimpleNamespace(borg_version=1, id=19)

    with patch(
        "app.services.check_service.check_service.execute_check",
        new=AsyncMock(),
    ) as mock_check:
        await BorgRouter(repo).check(5)

    mock_check.assert_awaited_once_with(5, 19)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compact_delegates_to_v2_service():
    repo = SimpleNamespace(borg_version=2, id=41)

    with patch(
        "app.services.v2.compact_service.compact_v2_service.execute_compact",
        new=AsyncMock(),
    ) as mock_compact:
        await BorgRouter(repo).compact(7)

    mock_compact.assert_awaited_once_with(7, 41)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compact_delegates_to_v1_service():
    repo = SimpleNamespace(borg_version=1, id=19)

    with patch(
        "app.services.compact_service.compact_service.execute_compact",
        new=AsyncMock(),
    ) as mock_compact:
        await BorgRouter(repo).compact(5)

    mock_compact.assert_awaited_once_with(5, 19)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_delegates_to_v2_service():
    repo = SimpleNamespace(borg_version=2, id=41)

    with patch(
        "app.services.v2.prune_service.prune_v2_service.execute_prune",
        new=AsyncMock(),
    ) as mock_prune:
        await BorgRouter(repo).prune(7, 1, 2, 3, 4, 5, 6, dry_run=True)

    mock_prune.assert_awaited_once_with(
        job_id=7,
        repository_id=41,
        keep_hourly=1,
        keep_daily=2,
        keep_weekly=3,
        keep_monthly=4,
        keep_quarterly=5,
        keep_yearly=6,
        dry_run=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_delegates_keep_within_to_v2_service():
    repo = SimpleNamespace(borg_version=2, id=41)

    with patch(
        "app.services.v2.prune_service.prune_v2_service.execute_prune",
        new=AsyncMock(),
    ) as mock_prune:
        await BorgRouter(repo).prune(
            job_id=7,
            keep_hourly=1,
            keep_daily=2,
            keep_weekly=3,
            keep_monthly=4,
            keep_quarterly=5,
            keep_yearly=6,
            dry_run=True,
            keep_within="1d",
        )

    mock_prune.assert_awaited_once_with(
        job_id=7,
        repository_id=41,
        keep_hourly=1,
        keep_daily=2,
        keep_weekly=3,
        keep_monthly=4,
        keep_quarterly=5,
        keep_yearly=6,
        dry_run=True,
        keep_within="1d",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_delegates_to_v1_service():
    repo = SimpleNamespace(borg_version=1, id=19)

    with patch(
        "app.services.prune_service.prune_service.execute_prune",
        new=AsyncMock(),
    ) as mock_prune:
        await BorgRouter(repo).prune(5, 1, 2, 3, 4, 5, 6)

    mock_prune.assert_awaited_once_with(
        job_id=5,
        repository_id=19,
        keep_hourly=1,
        keep_daily=2,
        keep_weekly=3,
        keep_monthly=4,
        keep_quarterly=5,
        keep_yearly=6,
        dry_run=False,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_archive_delegates_to_v2_service():
    repo = SimpleNamespace(borg_version=2, id=41)

    with patch(
        "app.services.v2.delete_archive_service.delete_archive_v2_service.execute_delete",
        new=AsyncMock(),
    ) as mock_delete:
        await BorgRouter(repo).delete_archive(7, "archive-1")

    mock_delete.assert_awaited_once_with(7, 41, "archive-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_archive_delegates_to_v1_service():
    repo = SimpleNamespace(borg_version=1, id=19)

    with patch(
        "app.services.delete_archive_service.delete_archive_service.execute_delete",
        new=AsyncMock(),
    ) as mock_delete:
        await BorgRouter(repo).delete_archive(5, "archive-1")

    mock_delete.assert_awaited_once_with(5, 19, "archive-1")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v2_returns_parsed_archives():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        passphrase="secret",
        remote_path=None,
        bypass_lock=True,
    )

    with patch(
        "app.core.borg2.borg2.list_archives",
        new=AsyncMock(
            return_value={"success": True, "stdout": '{"archives":[{"name":"a1"}]}'}
        ),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == [{"name": "a1"}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v2_returns_empty_on_failure():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        passphrase=None,
        remote_path=None,
        bypass_lock=False,
    )

    with patch(
        "app.core.borg2.borg2.list_archives",
        new=AsyncMock(return_value={"success": False, "stderr": "boom"}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v2_returns_empty_on_invalid_json():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        passphrase=None,
        remote_path=None,
        bypass_lock=False,
    )

    with patch(
        "app.core.borg2.borg2.list_archives",
        new=AsyncMock(return_value={"success": True, "stdout": "not-json"}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v1_parses_json_archives_payload():
    repo = SimpleNamespace(
        borg_version=1,
        path="/tmp/repo",
        passphrase="secret",
        remote_path="/usr/bin/borg",
        bypass_lock=True,
    )

    with patch(
        "app.core.borg.borg.list_archives",
        new=AsyncMock(
            return_value={"success": True, "stdout": '{"archives":[{"name":"a1"}]}'}
        ),
    ) as mock_list:
        archives = await BorgRouter(repo).list_archives()

    assert archives == [{"name": "a1"}]
    mock_list.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v1_returns_empty_on_invalid_json():
    repo = SimpleNamespace(
        borg_version=1,
        path="/tmp/repo",
        passphrase="secret",
        remote_path="/usr/bin/borg",
        bypass_lock=True,
    )

    with patch(
        "app.core.borg.borg.list_archives",
        new=AsyncMock(return_value={"success": True, "stdout": "not-json"}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_repository_delegates_to_v2_repository_service():
    repo = SimpleNamespace(
        borg_version=2,
        path="/tmp/repo",
        passphrase="secret",
        remote_path="/usr/bin/borg2",
        bypass_lock=True,
    )

    with patch(
        "app.services.v2.repository_service.repository_v2_service.verify_repository",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_verify:
        result = await BorgRouter(repo).verify_repository(ssh_key_id=9, timeout=45)

    assert result == {"success": True}
    mock_verify.assert_awaited_once_with(
        path="/tmp/repo",
        passphrase="secret",
        ssh_key_id=9,
        remote_path="/usr/bin/borg2",
        timeout=45,
        bypass_lock=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_repository_delegates_to_v1_repository_service():
    repo = SimpleNamespace(
        borg_version=1,
        path="/tmp/repo",
        encryption="repokey",
        passphrase="secret",
        remote_path="/usr/bin/borg",
    )

    with patch(
        "app.services.repository_service.repository_service.initialize_repository",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_init:
        result = await BorgRouter(repo).initialize_repository(
            ssh_key_id=3, init_timeout=90
        )

    assert result == {"success": True}
    mock_init.assert_awaited_once_with(
        path="/tmp/repo",
        encryption="repokey",
        passphrase="secret",
        ssh_key_id=3,
        remote_path="/usr/bin/borg",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_keyfile_delegates_to_v2_repository_service():
    repo = SimpleNamespace(borg_version=2, path="/tmp/repo")

    with patch(
        "app.services.v2.repository_service.repository_v2_service.export_keyfile",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_export:
        result = await BorgRouter(repo).export_keyfile("/tmp/repo.key")

    assert result == {"success": True}
    mock_export.assert_awaited_once_with(repository=repo, output_path="/tmp/repo.key")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archives_for_v1_returns_empty_on_failure():
    repo = SimpleNamespace(
        borg_version=1,
        path="/tmp/repo",
        passphrase=None,
        remote_path=None,
        bypass_lock=False,
    )

    with patch(
        "app.core.borg.borg.list_archives",
        new=AsyncMock(return_value={"success": False, "stderr": "boom"}),
    ):
        archives = await BorgRouter(repo).list_archives()

    assert archives == []


@pytest.mark.unit
def test_validate_local_repository_access_requires_config_file_for_v1(tmp_path):
    repo_path = tmp_path / "v1-invalid"
    repo_path.mkdir()
    (repo_path / "config").mkdir()

    repo = SimpleNamespace(borg_version=1, path=str(repo_path))

    with pytest.raises(ValueError) as exc:
        BorgRouter(repo).validate_local_repository_access()

    payload = json.loads(str(exc.value))
    assert payload["key"] == "backend.errors.repo.notValidBorgRepository"


@pytest.mark.unit
def test_validate_local_repository_access_skips_v1_config_check_for_v2(tmp_path):
    repo_path = tmp_path / "v2-repo"
    repo_path.mkdir()

    repo = SimpleNamespace(borg_version=2, path=str(repo_path))

    with patch(
        "app.services.v2.backup_service.backup_v2_service.validate_local_repository_access"
    ) as mock_validate:
        BorgRouter(repo).validate_local_repository_access()

    mock_validate.assert_called_once_with(repo)


@pytest.mark.unit
def test_build_backup_create_command_uses_v2_shape():
    repo = SimpleNamespace(borg_version=2)

    with patch(
        "app.services.v2.backup_service.backup_v2_service.build_backup_create_command",
        return_value=["borg2", "create", "manual-1"],
    ) as mock_build:
        cmd = BorgRouter(repo).build_backup_create_command(
            repository_path="/repos/v2",
            archive_name="manual-1",
            compression="zstd",
            exclude_patterns=["*.tmp"],
            custom_flags=["--one-file-system"],
        )

    assert cmd == ["borg2", "create", "manual-1"]
    mock_build.assert_called_once_with(
        repository_path="/repos/v2",
        archive_name="manual-1",
        compression="zstd",
        exclude_patterns=["*.tmp"],
        custom_flags=["--one-file-system"],
        upload_ratelimit_kib=None,
    )


@pytest.mark.unit
def test_build_backup_create_command_adds_v1_resolved_upload_ratelimit():
    repo = SimpleNamespace(borg_version=1)

    cmd = BorgRouter(repo).build_backup_create_command(
        repository_path="/repos/v1",
        archive_name="manual-1",
        compression="zstd",
        exclude_patterns=[],
        custom_flags=[],
        upload_ratelimit_kib=512,
    )

    assert "--upload-ratelimit" in cmd
    assert cmd[cmd.index("--upload-ratelimit") + 1] == "512"


@pytest.mark.unit
def test_build_backup_create_command_forwards_v2_resolved_upload_ratelimit():
    repo = SimpleNamespace(borg_version=2)

    with patch(
        "app.services.v2.backup_service.backup_v2_service.build_backup_create_command",
        return_value=["borg2", "create", "manual-1"],
    ) as mock_build:
        cmd = BorgRouter(repo).build_backup_create_command(
            repository_path="/repos/v2",
            archive_name="manual-1",
            compression="zstd",
            exclude_patterns=[],
            custom_flags=[],
            upload_ratelimit_kib=512,
        )

    assert cmd == ["borg2", "create", "manual-1"]
    mock_build.assert_called_once_with(
        repository_path="/repos/v2",
        archive_name="manual-1",
        compression="zstd",
        exclude_patterns=[],
        custom_flags=[],
        upload_ratelimit_kib=512,
    )


@pytest.mark.unit
def test_build_mount_command_uses_v1_shape():
    repo = SimpleNamespace(borg_version=1)

    cmd = BorgRouter(repo).build_mount_command(
        repository_path="/repo/path",
        archive_name="archive-1",
        mount_point="/mnt/repo",
        remote_path="/usr/bin/borg",
        bypass_lock=True,
    )

    assert cmd == [
        "borg",
        "mount",
        "--remote-path",
        "/usr/bin/borg",
        "/repo/path::archive-1",
        "/mnt/repo",
        "-o",
        "allow_other",
        "-f",
        "--bypass-lock",
    ]


@pytest.mark.unit
def test_build_mount_command_uses_v2_shape():
    repo = SimpleNamespace(borg_version=2)

    with patch("app.core.borg2.borg2.borg_cmd", "borg2"):
        cmd = BorgRouter(repo).build_mount_command(
            repository_path="/repo/path",
            archive_name="archive-1",
            mount_point="/mnt/repo",
            remote_path="/usr/bin/borg2",
            bypass_lock=False,
        )

    assert cmd == [
        "borg2",
        "--remote-path",
        "/usr/bin/borg2",
        "-r",
        "/repo/path",
        "mount",
        "-a",
        "archive-1",
        "/mnt/repo",
        "-o",
        "allow_other",
        "-f",
    ]


@pytest.mark.unit
def test_build_mount_command_ignores_bypass_lock_for_v2():
    repo = SimpleNamespace(borg_version=2)

    with patch("app.core.borg2.borg2.borg_cmd", "borg2"):
        cmd = BorgRouter(repo).build_mount_command(
            repository_path="/repo/path",
            archive_name="archive-1",
            mount_point="/mnt/repo",
            bypass_lock=True,
        )

    assert "--bypass-lock" not in cmd


@pytest.mark.unit
def test_build_unmount_command_uses_v2_shape():
    repo = SimpleNamespace(borg_version=2)

    with patch("app.core.borg2.borg2.borg_cmd", "borg2"):
        cmd = BorgRouter(repo).build_unmount_command("/mnt/repo")

    assert cmd == ["borg2", "umount", "/mnt/repo"]


@pytest.mark.unit
def test_build_backup_create_command_uses_v1_shape():
    repo = SimpleNamespace(borg_version=1)

    cmd = BorgRouter(repo).build_backup_create_command(
        repository_path="/repos/v1",
        archive_name="manual-1",
        compression="lz4",
        exclude_patterns=["*.cache"],
        custom_flags=["--read-special"],
    )

    assert cmd == [
        "borg",
        "create",
        "--progress",
        "--stats",
        "--show-rc",
        "--log-json",
        "--compression",
        "lz4",
        "--exclude",
        "*.cache",
        "--read-special",
        "/repos/v1::manual-1",
    ]


@pytest.mark.unit
def test_build_stats_commands_use_v2_binaries():
    repo = SimpleNamespace(borg_version=2)

    with (
        patch(
            "app.services.v2.backup_service.backup_v2_service.build_archive_info_command",
            return_value=["borg2", "info", "a1"],
        ) as mock_archive,
        patch(
            "app.services.v2.backup_service.backup_v2_service.build_repo_list_command",
            return_value=["borg2", "repo-list"],
        ) as mock_list,
        patch(
            "app.services.v2.backup_service.backup_v2_service.build_repo_info_command",
            return_value=["borg2", "info"],
        ) as mock_info,
    ):
        router = BorgRouter(repo)
        assert router.build_archive_info_command("/repos/v2", "a1") == [
            "borg2",
            "info",
            "a1",
        ]
        assert router.build_repo_list_command("/repos/v2") == ["borg2", "repo-list"]
        assert router.build_repo_info_command("/repos/v2") == ["borg2", "info"]

    mock_archive.assert_called_once_with("/repos/v2", "a1")
    mock_list.assert_called_once_with("/repos/v2")
    mock_info.assert_called_once_with("/repos/v2")


@pytest.mark.unit
def test_build_restore_extract_command_adds_strip_components_for_v1():
    repo = SimpleNamespace(borg_version=1)

    cmd = BorgRouter(repo).build_restore_extract_command(
        repository_path="/repos/v1",
        archive_name="manual-1",
        paths=["home/user/folder"],
        remote_path="/usr/bin/borg",
        bypass_lock=True,
        strip_components=3,
    )

    assert cmd == [
        "borg",
        "extract",
        "--progress",
        "--log-json",
        "--umask",
        "0022",
        "--remote-path",
        "/usr/bin/borg",
        "--bypass-lock",
        "--strip-components",
        "3",
        "/repos/v1::manual-1",
        "home/user/folder",
    ]


@pytest.mark.unit
def test_build_restore_extract_command_delegates_strip_components_for_v2():
    repo = SimpleNamespace(borg_version=2)

    with patch(
        "app.services.v2.restore_service.restore_v2_service.build_extract_command",
        return_value=["borg2", "extract"],
    ) as mock_build:
        cmd = BorgRouter(repo).build_restore_extract_command(
            repository_path="/repos/v2",
            archive_name="manual-1",
            paths=["home/user/folder"],
            strip_components=3,
        )

    assert cmd == ["borg2", "extract"]
    mock_build.assert_called_once_with(
        repository_path="/repos/v2",
        archive_name="manual-1",
        paths=["home/user/folder"],
        remote_path=None,
        bypass_lock=False,
        strip_components=3,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preview_restore_delegates_to_v2_restore_service():
    repo = SimpleNamespace(borg_version=2)

    with patch(
        "app.services.v2.restore_service.restore_v2_service.preview_restore",
        new=AsyncMock(return_value={"success": True, "stdout": "preview"}),
    ) as mock_preview:
        result = await BorgRouter(repo).preview_restore("a1", ["etc/hosts"], "/restore")

    assert result == {"success": True, "stdout": "preview"}
    mock_preview.assert_awaited_once_with(
        repo=repo,
        archive="a1",
        paths=["etc/hosts"],
        destination="/restore",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_archive_contents_delegates_to_v2_restore_service():
    repo = SimpleNamespace(borg_version=2)

    with patch(
        "app.services.v2.restore_service.restore_v2_service.list_archive_contents",
        new=AsyncMock(return_value={"success": True, "stdout": ""}),
    ) as mock_list:
        result = await BorgRouter(repo).list_archive_contents(
            "a1", path="etc", max_lines=123
        )

    assert result == {"success": True, "stdout": ""}
    mock_list.assert_awaited_once_with(
        repo=repo,
        archive="a1",
        path="etc",
        max_lines=123,
    )


@pytest.mark.unit
def test_build_break_lock_command_uses_v1_shape():
    repo = SimpleNamespace(borg_version=1)

    cmd = BorgRouter(repo).build_break_lock_command(
        "/repo/path", remote_path="/usr/bin/borg"
    )

    assert cmd == ["borg", "break-lock", "--remote-path", "/usr/bin/borg", "/repo/path"]


@pytest.mark.unit
def test_build_break_lock_command_uses_v2_shape():
    repo = SimpleNamespace(borg_version=2)

    with patch("app.core.borg2.borg2.borg_cmd", "borg2"):
        cmd = BorgRouter(repo).build_break_lock_command(
            "/repo/path", remote_path="/usr/bin/borg2"
        )

    assert cmd == [
        "borg2",
        "-r",
        "/repo/path",
        "break-lock",
        "--remote-path",
        "/usr/bin/borg2",
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_break_lock_delegates_to_v2_core():
    repo = SimpleNamespace(
        borg_version=2,
        path="/repo/path",
        passphrase="secret",
        remote_path="/usr/bin/borg2",
    )

    with patch(
        "app.core.borg2.borg2.break_lock",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_break:
        result = await BorgRouter(repo).break_lock()

    assert result == {"success": True}
    mock_break.assert_awaited_once_with(
        "/repo/path",
        passphrase="secret",
        remote_path="/usr/bin/borg2",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_break_lock_delegates_to_v1_core():
    repo = SimpleNamespace(
        borg_version=1,
        path="/repo/path",
        passphrase="secret",
        remote_path="/usr/bin/borg",
    )

    with patch(
        "app.core.borg.borg.break_lock",
        new=AsyncMock(return_value={"success": True}),
    ) as mock_break:
        result = await BorgRouter(repo).break_lock()

    assert result == {"success": True}
    mock_break.assert_awaited_once_with(
        "/repo/path",
        remote_path="/usr/bin/borg",
        passphrase="secret",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_break_lock_delegates_to_agent_when_managed():
    repo = SimpleNamespace(
        borg_version=2, id=41, path="/repo/path", executor_type="agent"
    )

    with (
        patch.object(
            BorgRouter,
            "_run_agent_break_lock",
            new=AsyncMock(return_value={"success": True}),
        ) as mock_agent,
        patch("app.core.borg2.borg2.break_lock", new=AsyncMock()) as mock_v2,
    ):
        result = await BorgRouter(repo).break_lock()

    assert result == {"success": True}
    mock_agent.assert_awaited_once_with()
    mock_v2.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_archive_delegates_to_agent_when_managed():
    repo = SimpleNamespace(borg_version=2, id=41, executor_type="agent")

    with (
        patch.object(
            BorgRouter, "_run_agent_maintenance", new=AsyncMock()
        ) as mock_agent,
        patch(
            "app.services.v2.delete_archive_service.delete_archive_v2_service"
            ".execute_delete",
            new=AsyncMock(),
        ) as mock_v2,
    ):
        await BorgRouter(repo).delete_archive(7, "aid:deadbeef")

    mock_agent.assert_awaited_once_with(
        job_kind="repository.delete_archive",
        maintenance_kind="delete_archive",
        maintenance_job_id=7,
        operation={"archive": "aid:deadbeef"},
    )
    mock_v2.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prune_delegates_to_v2_service():
    repo = SimpleNamespace(borg_version=2, id=41)

    with patch(
        "app.services.v2.prune_service.prune_v2_service.execute_prune",
        new=AsyncMock(),
    ) as mock_prune:
        await BorgRouter(repo).prune(
            job_id=7,
            keep_hourly=1,
            keep_daily=2,
            keep_weekly=3,
            keep_monthly=4,
            keep_quarterly=5,
            keep_yearly=6,
            dry_run=True,
        )

    mock_prune.assert_awaited_once_with(
        job_id=7,
        repository_id=41,
        keep_hourly=1,
        keep_daily=2,
        keep_weekly=3,
        keep_monthly=4,
        keep_quarterly=5,
        keep_yearly=6,
        dry_run=True,
    )
