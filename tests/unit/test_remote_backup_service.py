from unittest.mock import AsyncMock, MagicMock

import pytest

import json
import shlex

from app.database.models import BackupJob, Repository, SSHConnection, SSHKey
from app.services.remote_backup_service import (
    RemoteBackupService,
    _collapse_carriage_returns,
    _parse_created_archive_name,
    _redact_command,
)


def _remote_entities(test_db):
    connection = SSHConnection(
        host="docker-host.example",
        username="backup",
        port=2222,
        is_backup_source=True,
        borg_binary_path="/usr/local/bin/borg-wrapper",
    )
    repository = Repository(
        name="Remote Repo",
        path="/repos/remote-direct",
        repository_type="ssh",
        encryption="none",
        remote_path="/usr/lib/borg/borg",
        compression="lz4",
    )
    job = BackupJob(
        repository=repository.path,
        status="pending",
        execution_mode="remote_ssh",
        route_strategy="remote_direct",
        total_expected_size=1000,
    )
    test_db.add_all([connection, repository, job])
    test_db.flush()
    repository.connection_id = connection.id
    job.source_ssh_connection_id = connection.id
    test_db.commit()
    test_db.refresh(connection)
    test_db.refresh(repository)
    test_db.refresh(job)
    return connection, repository, job


def test_ssh_connection_defaults_to_path_resolved_borg(test_db):
    connection = SSHConnection(host="path.example", username="backup", port=22)
    test_db.add(connection)
    test_db.flush()

    assert connection.borg_binary_path == "borg"


def test_repository_url_uses_remote_path_for_same_source_connection(test_db):
    connection, repository, _job = _remote_entities(test_db)
    repository.path = "ssh://backup@docker-host.example:2222/repos/remote-direct"
    test_db.commit()

    service = RemoteBackupService()

    assert (
        service._get_repository_url(
            repository, test_db, source_ssh_connection=connection
        )
        == "/repos/remote-direct"
    )


def test_repository_url_keeps_canonical_ssh_url_for_different_connection(test_db):
    connection, repository, _job = _remote_entities(test_db)
    repository.path = "ssh://backup@docker-host.example:2222/repos/remote-direct"
    other_connection = SSHConnection(
        host="source.example",
        username="backup",
        port=22,
        is_backup_source=True,
    )
    test_db.add(other_connection)
    test_db.commit()

    service = RemoteBackupService()

    assert (
        service._get_repository_url(
            repository, test_db, source_ssh_connection=other_connection
        )
        == "ssh://backup@docker-host.example:2222/repos/remote-direct"
    )


@pytest.mark.asyncio
async def test_build_remote_command_passes_borg_env_through_sudo(test_db, monkeypatch):
    """sudo's env_reset (the Debian-family default) drops the BORG_* shell
    assignments in front of the command, so with use_sudo they must be named
    explicitly as preserved - otherwise borg prompts for a passphrase that
    can never arrive and exits 2 before touching the repository."""
    connection, repository, _job = _remote_entities(test_db)
    repository.encryption = "repokey"
    repository.passphrase = "s3cret pass"
    test_db.commit()
    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    service = RemoteBackupService()

    with_sudo = await service._build_remote_command(
        repository=repository,
        archive_name="{hostname}-{now}",
        source_paths=["/data"],
        exclude_patterns=[],
        borg_binary_path="/usr/bin/borg",
        use_sudo=True,
        source_ssh_connection=connection,
    )
    without_sudo = await service._build_remote_command(
        repository=repository,
        archive_name="{hostname}-{now}",
        source_paths=["/data"],
        exclude_patterns=[],
        borg_binary_path="/usr/bin/borg",
        use_sudo=False,
        source_ssh_connection=connection,
    )

    env_prefix = (
        "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes "
        "BORG_RELOCATED_REPO_ACCESS_IS_OK=yes "
        "BORG_PASSPHRASE='s3cret pass' "
        "BORG_REMOTE_PATH=/usr/lib/borg/borg "
    )
    assert with_sudo.startswith(
        env_prefix + "sudo -n --preserve-env="
        "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK,"
        "BORG_RELOCATED_REPO_ACCESS_IS_OK,"
        "BORG_PASSPHRASE,"
        "BORG_REMOTE_PATH "
        "/usr/bin/borg create "
    )
    assert without_sudo.startswith(env_prefix + "/usr/bin/borg create ")
    assert "sudo" not in without_sudo


@pytest.mark.asyncio
async def test_build_remote_command_preserve_env_lists_only_variables_set(
    test_db, monkeypatch
):
    """An unencrypted repository without remote_path sets neither
    BORG_PASSPHRASE nor BORG_REMOTE_PATH, and the preserve list follows."""
    connection, repository, _job = _remote_entities(test_db)
    repository.remote_path = None
    test_db.commit()
    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    service = RemoteBackupService()

    command = await service._build_remote_command(
        repository=repository,
        archive_name="{hostname}-{now}",
        source_paths=["/data"],
        exclude_patterns=[],
        borg_binary_path="/usr/bin/borg",
        use_sudo=True,
        source_ssh_connection=connection,
    )

    assert (
        "sudo -n --preserve-env="
        "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK,"
        "BORG_RELOCATED_REPO_ACCESS_IS_OK "
        "/usr/bin/borg create "
    ) in command
    assert "BORG_PASSPHRASE" not in command
    assert "BORG_REMOTE_PATH" not in command


@pytest.mark.asyncio
async def test_build_remote_command_resolves_default_borg_before_sudo(
    test_db, monkeypatch
):
    """The default Borg command must not depend on sudo's secure_path."""
    connection, repository, _job = _remote_entities(test_db)
    repository.remote_path = None
    test_db.commit()
    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )

    command = await RemoteBackupService()._build_remote_command(
        repository=repository,
        archive_name="{hostname}-{now}",
        source_paths=["/data"],
        exclude_patterns=[],
        borg_binary_path="borg",
        use_sudo=True,
        source_ssh_connection=connection,
    )

    assert command.startswith(
        "export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes "
        "BORG_RELOCATED_REPO_ACCESS_IS_OK=yes && "
        "borg_path=$(command -v borg) && "
        "sudo -n --preserve-env="
        "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK,"
        'BORG_RELOCATED_REPO_ACCESS_IS_OK "$borg_path" create '
    )


@pytest.mark.asyncio
async def test_execute_remote_backup_does_not_require_backup_source_flag_and_uses_source_borg_wrapper(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
    connection.is_backup_source = False
    test_db.commit()
    service = RemoteBackupService()
    commands = []
    connection_id = connection.id
    connection_host = connection.host
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(ssh_connection, command, job_id, db):
        commands.append(command)
        assert ssh_connection.id == connection_id
        await service._update_progress_from_json(
            job_id,
            {
                "original_size": 500,
                "compressed_size": 250,
                "deduplicated_size": 125,
                "nfiles": 7,
            },
            db,
        )
        return {
            "success": True,
            "returncode": 0,
            "stdout": json.dumps(
                {"archive": {"name": "docker-host.example-2026-08-20T11:18:00"}}
            ),
            "stderr": "",
        }

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    send_success = AsyncMock()
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_success",
        send_success,
    )

    result = await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
        exclude_patterns=[],
        compression="lz4",
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert result["success"] is True
    assert job.status == "completed"
    assert job.archive_name == "docker-host.example-2026-08-20T11:18:00"
    assert send_success.await_args.args[2] == "docker-host.example-2026-08-20T11:18:00"
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.remote_hostname == connection_host
    assert job.original_size == 500
    assert job.compressed_size == 250
    assert job.deduplicated_size == 125
    assert job.nfiles == 7
    assert job.progress == 100
    assert job.progress_percent == 100.0
    assert commands
    assert "/usr/local/bin/borg-wrapper create" in commands[0]
    assert "BORG_REMOTE_PATH=/usr/lib/borg/borg" in commands[0]
    assert "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes" in commands[0]
    assert "BORG_RELOCATED_REPO_ACCESS_IS_OK=yes" in commands[0]


@pytest.mark.asyncio
async def test_execute_ssh_command_uses_public_key_only_authentication_options(
    monkeypatch,
):
    service = RemoteBackupService()
    connection = SSHConnection(
        id=7,
        host="truenas.example",
        username="backup",
        port=2222,
        ssh_key_id=42,
    )
    ssh_key = MagicMock(spec=SSHKey)
    job = MagicMock(spec=BackupJob)
    db = MagicMock()

    def query_side_effect(model):
        query = MagicMock()
        if model == SSHKey:
            query.filter.return_value.first.return_value = ssh_key
        elif model == BackupJob:
            query.filter.return_value.first.return_value = job
        return query

    db.query.side_effect = query_side_effect
    captured_cmd: list[str] = []

    process = AsyncMock()
    process.pid = 1234
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.readline = AsyncMock(return_value=b"")
    process.wait = AsyncMock(return_value=0)

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        return process

    monkeypatch.setattr(
        "app.services.remote_backup_service.write_ssh_key_to_tempfile",
        lambda key: "/tmp/source.key",
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.os.unlink", lambda path: None
    )

    result = await service._execute_ssh_command(
        ssh_connection=connection,
        command="borg create /repo::archive /data",
        job_id=99,
        db=db,
    )

    assert result["success"] is True
    assert captured_cmd[:3] == ["ssh", "-i", "/tmp/source.key"]
    assert "BatchMode=yes" in captured_cmd
    assert "IdentitiesOnly=yes" in captured_cmd
    assert "PreferredAuthentications=publickey" in captured_cmd
    assert "PasswordAuthentication=no" in captured_cmd
    assert "NumberOfPasswordPrompts=0" in captured_cmd


@pytest.mark.asyncio
async def test_verify_remote_borg_resolves_default_path_before_sudo(monkeypatch):
    service = RemoteBackupService()
    connection = SSHConnection(
        id=7,
        host="truenas.example",
        username="backup",
        port=2222,
        ssh_key_id=42,
        borg_binary_path="borg",
        use_sudo=True,
    )
    ssh_key = MagicMock(spec=SSHKey)
    db = MagicMock()

    def query_side_effect(model):
        query = MagicMock()
        if model == SSHConnection:
            query.filter.return_value.first.return_value = connection
        elif model == SSHKey:
            query.filter.return_value.first.return_value = ssh_key
        return query

    db.query.side_effect = query_side_effect
    captured_cmd: list[str] = []
    process = AsyncMock()
    process.communicate = AsyncMock(return_value=(b"borg 1.4.5", b""))
    process.returncode = 0

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        return process

    monkeypatch.setattr("app.services.remote_backup_service.SessionLocal", lambda: db)
    monkeypatch.setattr(
        "app.services.remote_backup_service.write_ssh_key_to_tempfile",
        lambda key: "/tmp/source.key",
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.os.unlink", lambda path: None
    )

    result = await service.verify_remote_borg(connection.id)

    assert result == {"installed": True, "version": "1.4.5", "path": "borg"}
    assert captured_cmd[-1] == (
        'borg_path=$(command -v borg) && exec sudo -n -H "$borg_path" --version'
    )


@pytest.mark.asyncio
async def test_execute_remote_backup_keeps_completed_status_when_success_notification_fails(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
    service = RemoteBackupService()
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(*args, **kwargs):
        return {
            "success": True,
            "returncode": 0,
            "stdout": "{}",
            "stderr": "",
        }

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_success",
        AsyncMock(side_effect=RuntimeError("notification failed")),
    )

    result = await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert result["success"] is True
    assert job.status == "completed"
    assert job.error_message is None


@pytest.mark.asyncio
async def test_execute_remote_backup_records_failure_on_same_job_row(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
    service = RemoteBackupService()
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(*args, **kwargs):
        return {
            "success": False,
            "returncode": 2,
            "stdout": "",
            "stderr": "changed file",
            "error": "Remote backup failed with exit code 2",
        }

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_failure",
        AsyncMock(),
    )

    result = await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert result["success"] is False
    assert job.status == "failed"
    assert job.completed_at is not None
    assert job.error_message == "Remote backup failed with exit code 2"


@pytest.mark.asyncio
async def test_execute_remote_backup_rejects_different_source_and_repository_connections(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
    other_connection = SSHConnection(host="other.example", username="backup", port=22)
    test_db.add(other_connection)
    test_db.flush()
    repository.connection_id = other_connection.id
    test_db.commit()

    service = RemoteBackupService()
    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )

    with pytest.raises(Exception, match="same SSH connection"):
        await service.execute_remote_backup(
            job_id=job.id,
            source_ssh_connection_id=connection.id,
            repository_id=repository.id,
            source_paths=["/var/lib/data"],
        )


@pytest.mark.asyncio
async def test_execute_remote_backup_keeps_failed_status_when_failure_notification_fails(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
    service = RemoteBackupService()
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(*args, **kwargs):
        return {
            "success": False,
            "returncode": 2,
            "stdout": "",
            "stderr": "changed file",
            "error": "Remote backup failed with exit code 2",
        }

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_failure",
        AsyncMock(side_effect=RuntimeError("notification failed")),
    )

    result = await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert result["success"] is False
    assert job.status == "failed"
    assert job.error_message == "Remote backup failed with exit code 2"


@pytest.mark.asyncio
async def test_update_progress_from_json_only_sets_percent_with_known_total(test_db):
    service = RemoteBackupService()
    job_without_total = BackupJob(repository="/repo", status="running")
    job_with_total = BackupJob(
        repository="/repo",
        status="running",
        total_expected_size=1000,
    )
    test_db.add_all([job_without_total, job_with_total])
    test_db.commit()

    await service._update_progress_from_json(
        job_without_total.id,
        {
            "original_size": 500,
            "compressed_size": 250,
            "deduplicated_size": 125,
            "nfiles": 7,
        },
        test_db,
    )
    await service._update_progress_from_json(
        job_with_total.id,
        {
            "original_size": 500,
            "compressed_size": 250,
            "deduplicated_size": 125,
            "nfiles": 7,
        },
        test_db,
    )

    test_db.refresh(job_without_total)
    test_db.refresh(job_with_total)
    assert job_without_total.original_size == 500
    assert job_without_total.compressed_size == 250
    assert job_without_total.deduplicated_size == 125
    assert job_without_total.nfiles == 7
    assert job_without_total.progress == 0
    assert job_without_total.progress_percent == 0.0
    assert job_with_total.progress == 50
    assert job_with_total.progress_percent == 50.0


@pytest.mark.asyncio
async def test_execute_remote_backup_records_warning_exit_as_completed_with_warnings(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
    service = RemoteBackupService()
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(*args, **kwargs):
        return {
            "success": False,
            "returncode": 1,
            "stdout": json.dumps({"archive": {"name": "host-2026-08-20T11:18:00"}}),
            "stderr": "BackupFileNotFoundError: /etc/dangling-symlink",
            "error": "Remote backup failed with exit code 1",
        }

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    send_warning = AsyncMock()
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_warning",
        send_warning,
    )

    result = await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert result["success"] is True
    assert job.status == "completed_with_warnings"
    assert job.progress == 100
    assert job.progress_percent == 100.0
    assert job.completed_at is not None
    assert job.archive_name == "host-2026-08-20T11:18:00"
    assert json.loads(job.error_message) == {
        "key": "backend.errors.service.backupCompletedWithWarning",
        "params": {"exitCode": 1},
    }
    send_warning.assert_awaited_once()
    assert send_warning.await_args.args[2] == "host-2026-08-20T11:18:00"


@pytest.mark.asyncio
async def test_execute_ssh_command_reports_transport_facts_only(monkeypatch):
    """_execute_ssh_command must not classify warnings - the exit code may be
    the remote shell's (127 = borg missing), so the caller decides."""
    service = RemoteBackupService()
    connection = SSHConnection(
        id=7,
        host="truenas.example",
        username="backup",
        port=2222,
        ssh_key_id=42,
    )
    ssh_key = MagicMock(spec=SSHKey)
    job = MagicMock(spec=BackupJob)
    db = MagicMock()

    def query_side_effect(model):
        query = MagicMock()
        if model == SSHKey:
            query.filter.return_value.first.return_value = ssh_key
        elif model == BackupJob:
            query.filter.return_value.first.return_value = job
        return query

    db.query.side_effect = query_side_effect

    process = AsyncMock()
    process.pid = 1234
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.readline = AsyncMock(return_value=b"")

    monkeypatch.setattr(
        "app.services.remote_backup_service.write_ssh_key_to_tempfile",
        lambda key: "/tmp/source.key",
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.os.unlink", lambda path: None
    )

    for returncode in (0, 1, 104, 127, 2):
        process.wait = AsyncMock(return_value=returncode)
        result = await service._execute_ssh_command(
            ssh_connection=connection,
            command="borg create /repo::archive /data",
            job_id=99,
            db=db,
        )
        assert result["success"] is (returncode == 0), returncode
        assert "warning" not in result
        if returncode == 0:
            assert result["error"] is None
        else:
            assert (
                result["error"] == f"Remote backup failed with exit code {returncode}"
            )


@pytest.mark.asyncio
async def test_execute_remote_backup_treats_shell_127_as_failure(test_db, monkeypatch):
    """Exit 127 is the remote shell's 'command not found' - inside borg's
    modern warning range, but no archive was written. Must stay a failure."""
    connection, repository, job = _remote_entities(test_db)
    service = RemoteBackupService()
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(*args, **kwargs):
        return {
            "success": False,
            "returncode": 127,
            "stdout": "",
            "stderr": "bash: line 1: /usr/local/bin/borg-wrapper: command not found",
            "error": "Remote backup failed with exit code 127",
        }

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    send_failure = AsyncMock()
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_failure",
        send_failure,
    )

    result = await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert result["success"] is False
    assert job.status == "failed"
    assert job.archive_name is None
    assert job.error_message == "Remote backup failed with exit code 127"
    send_failure.assert_awaited_once()


def test_parse_created_archive_name():
    stdout = json.dumps(
        {
            "archive": {"name": "host-2026-08-20T11:18:00", "id": "ceb0dfe2"},
            "repository": {"location": "ssh://backup@host/repo"},
        },
        indent=4,
    )
    assert _parse_created_archive_name(stdout) == "host-2026-08-20T11:18:00"
    assert _parse_created_archive_name("") is None
    assert _parse_created_archive_name(None) is None
    assert _parse_created_archive_name("not json") is None
    assert _parse_created_archive_name(json.dumps({"archive": {}})) is None
    assert _parse_created_archive_name(json.dumps(["archive"])) is None


def test_redact_command_masks_every_shape_shlex_quote_produces():
    for passphrase in ["simple", "s3cret pass", "it's", "a'b'c", 'x"y', "ends with '"]:
        command = (
            f"BORG_RELOCATED_REPO_ACCESS_IS_OK=yes "
            f"BORG_PASSPHRASE={shlex.quote(passphrase)} "
            f"BORG_REMOTE_PATH=/usr/bin/borg /usr/bin/borg create repo::a /data"
        )
        assert _redact_command(command) == (
            "BORG_RELOCATED_REPO_ACCESS_IS_OK=yes BORG_PASSPHRASE=*** "
            "BORG_REMOTE_PATH=/usr/bin/borg /usr/bin/borg create repo::a /data"
        ), passphrase

    untouched = (
        "BORG_RELOCATED_REPO_ACCESS_IS_OK=yes /usr/bin/borg create repo::a /data"
    )
    assert _redact_command(untouched) == untouched


def test_redact_command_is_idempotent():
    """Output is redacted at capture and again at transcript assembly; the
    second pass must leave already-masked text untouched (it used to eat the
    character after the mask, e.g. the colon of a shell error)."""
    once = _redact_command("bash: BORG_PASSPHRASE='s3cret pass': command not found")

    assert once == "bash: BORG_PASSPHRASE=***: command not found"
    assert _redact_command(once) == once


def test_collapse_carriage_returns_keeps_the_final_state():
    assert (
        _collapse_carriage_returns("Initializing\r 12% done\r 80%\rWARNING: changed\n")
        == "WARNING: changed"
    )
    assert _collapse_carriage_returns("plain line\n") == "plain line"
    assert _collapse_carriage_returns("\r\r\n") == ""


@pytest.mark.asyncio
async def test_execute_ssh_command_collapses_progress_and_names_the_failure_cause(
    monkeypatch,
):
    service = RemoteBackupService()
    connection = SSHConnection(
        id=7, host="truenas.example", username="backup", port=2222, ssh_key_id=42
    )
    ssh_key = MagicMock(spec=SSHKey)
    job = MagicMock(spec=BackupJob)
    db = MagicMock()

    def query_side_effect(model):
        query = MagicMock()
        if model == SSHKey:
            query.filter.return_value.first.return_value = ssh_key
        elif model == BackupJob:
            query.filter.return_value.first.return_value = job
        return query

    db.query.side_effect = query_side_effect

    process = AsyncMock()
    process.pid = 1234
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.readline = AsyncMock(
        side_effect=[
            b"Initializing cache\r 12% done\r 80% done\rWARNING: file changed\n",
            b"Cannot acquire a passphrase: BORG_PASSPHRASE is not set.\n",
            b"",
        ]
    )
    process.wait = AsyncMock(return_value=2)

    monkeypatch.setattr(
        "app.services.remote_backup_service.write_ssh_key_to_tempfile",
        lambda key: "/tmp/source.key",
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.os.unlink", lambda path: None
    )

    result = await service._execute_ssh_command(
        ssh_connection=connection,
        command="borg create /repo::archive /data",
        job_id=99,
        db=db,
    )

    assert result["success"] is False
    assert result["stderr"] == (
        "WARNING: file changed\nCannot acquire a passphrase: BORG_PASSPHRASE is not set."
    )
    assert result["error"] == (
        "Remote backup failed with exit code 2: "
        "Cannot acquire a passphrase: BORG_PASSPHRASE is not set."
    )


@pytest.mark.asyncio
async def test_execute_ssh_command_redacts_the_failure_cause_before_truncating(
    monkeypatch,
):
    """A shell echoing a long quoted BORG_PASSPHRASE= assignment must not leak
    part of it through the 300-character cut - redaction runs first."""
    service = RemoteBackupService()
    connection = SSHConnection(
        id=7, host="truenas.example", username="backup", port=2222, ssh_key_id=42
    )
    ssh_key = MagicMock(spec=SSHKey)
    job = MagicMock(spec=BackupJob)
    db = MagicMock()

    def query_side_effect(model):
        query = MagicMock()
        if model == SSHKey:
            query.filter.return_value.first.return_value = ssh_key
        elif model == BackupJob:
            query.filter.return_value.first.return_value = job
        return query

    db.query.side_effect = query_side_effect
    passphrase = "p" * 400
    echoed = (
        f"bash: BORG_PASSPHRASE={shlex.quote(passphrase + ' x')}: command not found\n"
    )

    process = AsyncMock()
    process.pid = 1234
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.readline = AsyncMock(side_effect=[echoed.encode(), b""])
    process.wait = AsyncMock(return_value=127)

    monkeypatch.setattr(
        "app.services.remote_backup_service.write_ssh_key_to_tempfile",
        lambda key: "/tmp/source.key",
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.os.unlink", lambda path: None
    )

    result = await service._execute_ssh_command(
        ssh_connection=connection,
        command="borg create /repo::archive /data",
        job_id=99,
        db=db,
    )

    assert result["error"] == (
        "Remote backup failed with exit code 127: "
        "bash: BORG_PASSPHRASE=***: command not found"
    )
    assert "ppp" not in result["error"]
    # Redaction happens at capture, so the retained stderr (the transcript
    # source) never holds the raw passphrase either.
    assert result["stderr"] == "bash: BORG_PASSPHRASE=***: command not found"
    assert "ppp" not in result["stderr"]


@pytest.mark.asyncio
async def test_failed_remote_backup_stores_redacted_transcript_in_log_file(
    test_db, monkeypatch, tmp_path
):
    """Default policy (failed_and_warnings): a failed job gets a per-job log
    file with the command (passphrase masked), borg's stderr and stdout -
    what the local path has always produced."""
    connection, repository, job = _remote_entities(test_db)
    repository.encryption = "repokey"
    repository.passphrase = "s3cret pass"
    test_db.commit()
    service = RemoteBackupService()
    service.log_dir = tmp_path
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(ssh_connection, command, job_id, db):
        assert "BORG_PASSPHRASE='s3cret pass'" in command
        # The executor redacts both streams at capture, so its result never
        # carries the raw value - the stub models that contract, and the
        # transcript's second redaction pass must leave the mask untouched.
        return {
            "success": False,
            "returncode": 2,
            "stdout": "",
            "stderr": (
                "bash: BORG_PASSPHRASE=***: command not found\n"
                "Cannot acquire a passphrase: BORG_PASSPHRASE is not set."
            ),
            "error": (
                "Remote backup failed with exit code 2: "
                "bash: BORG_PASSPHRASE=***: command not found"
            ),
        }

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_failure",
        AsyncMock(),
    )

    await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert job.status == "failed"
    assert job.log_file_path and job.log_file_path.startswith(str(tmp_path))
    assert job.logs.startswith("Logs saved to: backup_job_")
    content = open(job.log_file_path).read()
    assert content.startswith("$ BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes ")
    assert "BORG_PASSPHRASE=***" in content
    # neither the command line nor a shell echoing it may leak the value
    assert "s3cret pass" not in content
    assert "s3cret pass" not in job.error_message
    assert job.error_message.endswith("bash: BORG_PASSPHRASE=***: command not found")
    assert "/usr/local/bin/borg-wrapper create" in content
    assert "/var/lib/docker/volumes/app" in content
    assert "Cannot acquire a passphrase: BORG_PASSPHRASE is not set." in content


@pytest.mark.asyncio
async def test_successful_remote_backup_keeps_transcript_in_job_row_per_policy(
    test_db, monkeypatch, tmp_path
):
    """Default policy keeps no file for a clean success; the transcript still
    lands in the job row so the Activity view has something to show."""
    connection, repository, job = _remote_entities(test_db)
    service = RemoteBackupService()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    service.log_dir = log_dir
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id
    stats = json.dumps({"archive": {"name": "host-2026-08-20T11:18:00"}})

    async def fake_execute_ssh_command(*args, **kwargs):
        return {"success": True, "returncode": 0, "stdout": stats, "stderr": ""}

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_success",
        AsyncMock(),
    )

    await service.execute_remote_backup(
        job_id=job_id,
        source_ssh_connection_id=connection_id,
        repository_id=repository_id,
        source_paths=["/var/lib/docker/volumes/app"],
    )

    job = test_db.query(BackupJob).filter(BackupJob.id == job_id).one()
    assert job.status == "completed"
    assert job.log_file_path is None
    assert list(log_dir.iterdir()) == []
    assert job.logs.startswith("$ BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes ")
    assert stats in job.logs


@pytest.mark.asyncio
async def test_execute_ssh_command_never_returns_or_logs_the_passphrase(monkeypatch):
    """A remote shell error can echo the whole command line — including the
    BORG_PASSPHRASE assignment — on either stream. Both streams are redacted
    at capture, so neither the returned output nor anything handed to the
    logger ever carries the secret."""
    secret = "hunter2-super-secret"
    echoed = f"sh: 1: BORG_PASSPHRASE={shlex.quote(secret)} borg: not found"

    service = RemoteBackupService()
    connection = SSHConnection(
        id=7, host="truenas.example", username="backup", port=2222, ssh_key_id=42
    )
    ssh_key = MagicMock(spec=SSHKey)
    job = MagicMock(spec=BackupJob)
    db = MagicMock()

    def query_side_effect(model):
        query = MagicMock()
        if model == SSHKey:
            query.filter.return_value.first.return_value = ssh_key
        elif model == BackupJob:
            query.filter.return_value.first.return_value = job
        return query

    db.query.side_effect = query_side_effect

    process = AsyncMock()
    process.pid = 1234
    process.stdout.readline = AsyncMock(side_effect=[echoed.encode(), b""])
    process.stderr.readline = AsyncMock(side_effect=[echoed.encode(), b""])
    process.wait = AsyncMock(return_value=127)

    log_records: list[tuple] = []

    class RecordingLogger:
        def __getattr__(self, level):
            def record(*args, **kwargs):
                log_records.append((level, args, kwargs))

            return record

    monkeypatch.setattr(
        "app.services.remote_backup_service.write_ssh_key_to_tempfile",
        lambda key: "/tmp/source.key",
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.asyncio.create_subprocess_exec",
        AsyncMock(return_value=process),
    )
    monkeypatch.setattr(
        "app.services.remote_backup_service.os.unlink", lambda path: None
    )
    monkeypatch.setattr("app.services.remote_backup_service.logger", RecordingLogger())

    result = await service._execute_ssh_command(
        ssh_connection=connection,
        command=f"BORG_PASSPHRASE={shlex.quote(secret)} borg create /repo::a /data",
        job_id=99,
        db=db,
    )

    for field in ("stdout", "stderr", "error"):
        assert secret not in (result[field] or ""), field
    # The mask proves redaction ran (rather than the lines being dropped).
    assert "BORG_PASSPHRASE=***" in result["stdout"]
    assert "BORG_PASSPHRASE=***" in result["stderr"]
    assert secret not in repr(log_records)
