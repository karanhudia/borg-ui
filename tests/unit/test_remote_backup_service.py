from unittest.mock import AsyncMock

import pytest

from app.database.models import BackupJob, Repository, SSHConnection
from app.services.remote_backup_service import RemoteBackupService


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
async def test_execute_remote_backup_updates_same_job_row_and_uses_source_borg_wrapper(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
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
        return {"success": True, "returncode": 0, "stdout": "{}", "stderr": ""}

    monkeypatch.setattr(
        "app.services.remote_backup_service.SessionLocal", lambda: test_db
    )
    monkeypatch.setattr(service, "_execute_ssh_command", fake_execute_ssh_command)
    monkeypatch.setattr(
        "app.services.remote_backup_service.notification_service.send_backup_success",
        AsyncMock(),
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
async def test_execute_remote_backup_keeps_completed_status_when_success_notification_fails(
    test_db, monkeypatch
):
    connection, repository, job = _remote_entities(test_db)
    service = RemoteBackupService()
    connection_id = connection.id
    repository_id = repository.id
    job_id = job.id

    async def fake_execute_ssh_command(*args, **kwargs):
        return {"success": True, "returncode": 0, "stdout": "{}", "stderr": ""}

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
