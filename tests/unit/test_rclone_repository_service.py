import pytest
from types import SimpleNamespace

from app.database.models import (
    AgentMachine,
    Repository,
    RepositoryStorage,
    RcloneRemote,
)
from app.services.rclone_repository_service import (
    RcloneRepositoryService,
    normalize_extra_flags,
    normalize_rclone_relative_path,
)
from app.services.rclone_service import RcloneCommandResult


@pytest.mark.unit
def test_normalize_rclone_relative_path_accepts_safe_relative_paths():
    assert normalize_rclone_relative_path("borg-ui/repositories/app") == (
        "borg-ui/repositories/app"
    )
    assert normalize_rclone_relative_path(" team/repo// ") == "team/repo"


@pytest.mark.unit
@pytest.mark.parametrize(
    "value",
    ["", "/absolute", "../escape", "team/../../escape", "prod:bucket/path"],
)
def test_normalize_rclone_relative_path_rejects_unsafe_paths(value):
    with pytest.raises(ValueError):
        normalize_rclone_relative_path(value)


@pytest.mark.unit
def test_normalize_extra_flags_preserves_quoted_values():
    assert normalize_extra_flags('--exclude "dir with spaces/**" --fast-list') == [
        "--exclude",
        "dir with spaces/**",
        "--fast-list",
    ]


@pytest.mark.unit
def test_cache_path_is_derived_from_repository_identity(tmp_path):
    service = RcloneRepositoryService(cache_root=str(tmp_path / "cache"))

    assert service.derive_cache_path(42) == str(
        tmp_path / "cache" / "repositories" / "42"
    )


@pytest.mark.unit
def test_compose_target_uses_remote_name_not_database_id():
    service = RcloneRepositoryService(cache_root="/cache")
    remote = RcloneRemote(id=17, name="prod-s3", provider="s3")

    assert service.compose_target(remote, "borg-ui/repositories/app") == (
        "prod-s3:borg-ui/repositories/app"
    )


@pytest.mark.unit
def test_status_serializes_failure_state():
    service = RcloneRepositoryService(cache_root="/cache")
    repository = Repository(id=9, name="App", path="/cache/repositories/9")
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/cache/repositories/9",
        sync_policy="after_success",
        sync_status="failed",
        last_sync_error="rclone sync failed",
    )

    status = service.serialize_status(repository, storage, remote)

    assert status["repository_id"] == 9
    assert status["backend"] == "rclone"
    assert status["sync_status"] == "failed"
    assert status["last_sync_error"] == "rclone sync failed"
    assert status["rclone_target"] == "prod-s3:borg-ui/repositories/app"
    assert status["cache_present"] is False


@pytest.mark.unit
def test_status_detects_cache_presence(tmp_path):
    cache_path = tmp_path / "repositories" / "9"
    cache_path.mkdir(parents=True)
    service = RcloneRepositoryService(cache_root=str(tmp_path))
    repository = Repository(id=9, name="App", path=str(cache_path))
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=str(cache_path),
        sync_policy="after_success",
        sync_status="current",
    )

    assert (
        service.serialize_status(repository, storage, remote)["cache_present"] is True
    )


class _ExplodingRcloneService:
    async def sync(self, *args, **kwargs):
        raise RuntimeError("rclone timed out")


class _SuccessfulRcloneService:
    async def sync(self, *args, **kwargs):
        return RcloneCommandResult(
            success=True,
            return_code=0,
            stdout="",
            stderr="",
            command=["rclone", "sync"],
            redacted_command="rclone sync <path> <path>",
        )


class _RecordingRcloneService:
    def __init__(self):
        self.sync_calls = []

    async def sync(self, source, destination, **kwargs):
        self.sync_calls.append((source, destination, kwargs))
        return RcloneCommandResult(
            success=True,
            return_code=0,
            stdout="",
            stderr="",
            command=["rclone", "sync", source, destination],
            redacted_command="rclone sync <path> <path>",
        )


class _RecordingMountService:
    def __init__(self):
        self.mount_calls = []
        self.unmount_calls = []
        self.active_mounts = {}

    async def mount_ssh_directory(self, connection_id, remote_path, job_id=None):
        self.mount_calls.append((connection_id, remote_path, job_id))
        mount_id = "mount-ssh-repo"
        self.active_mounts[mount_id] = SimpleNamespace(
            mount_point="/tmp/sshfs_mount_9/backups/app"
        )
        return "/tmp/sshfs_mount_9", mount_id

    async def unmount(self, mount_id, force=False):
        self.unmount_calls.append((mount_id, force))
        self.active_mounts.pop(mount_id, None)
        return True


class _ListingRcloneService:
    def __init__(self, entries):
        self.entries = entries

    async def lsjson(self, target, *, timeout=60):
        return self.entries


@pytest.mark.unit
def test_build_mirror_storage_uses_primary_repository_path_as_source():
    service = RcloneRepositoryService(cache_root="/cache")

    storage = service.build_mirror_storage(
        repository_id=9,
        source_path="/srv/borg/app",
        remote_id=3,
        remote_path="borg-ui/repositories/app",
        sync_policy="manual",
        extra_flags=["--fast-list"],
    )

    assert storage.backend == "rclone"
    assert storage.cache_path == "/srv/borg/app"
    assert storage.sync_direction == "primary_to_remote"
    assert storage.sync_status == "pending"
    assert storage.extra_flags == ["--fast-list"]


@pytest.mark.unit
def test_build_ssh_mirror_storage_records_server_owned_mount_strategy():
    service = RcloneRepositoryService(cache_root="/cache")

    storage = service.build_mirror_storage(
        repository_id=9,
        source_path="ssh://borg@storage.example:22/backups/app",
        source_backend="ssh",
        remote_id=3,
        remote_path="borg-ui/repositories/app",
        sync_policy="manual",
    )

    assert storage.backend == "rclone"
    assert storage.cache_path is None
    assert storage.sync_direction == "sshfs_mount_to_remote"
    assert storage.sync_status == "pending"


@pytest.mark.unit
def test_build_agent_mirror_storage_records_agent_owned_sync_strategy():
    service = RcloneRepositoryService(cache_root="/cache")

    storage = service.build_mirror_storage(
        repository_id=9,
        source_path="/agent/repositories/app",
        source_backend="agent",
        remote_id=3,
        remote_path="borg-ui/repositories/app",
        sync_policy="manual",
    )

    assert storage.backend == "rclone"
    assert storage.cache_path is None
    assert storage.sync_direction == "agent_to_remote"
    assert storage.sync_status == "pending"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_repository_mirror_uses_primary_repository_path_source(db_session):
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    repository = Repository(id=9, name="App", path="/srv/borg/app", encryption="none")
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path="/srv/borg/app",
        sync_policy="manual",
        sync_status="pending",
        sync_direction="primary_to_remote",
    )
    db_session.add_all([remote, repository, storage])
    db_session.commit()
    rclone = _RecordingRcloneService()
    service = RcloneRepositoryService(cache_root="/cache", service=rclone)

    await service.sync_repository(db_session, repository)

    assert rclone.sync_calls[0][0] == "/srv/borg/app"
    assert rclone.sync_calls[0][1] == "prod-s3:borg-ui/repositories/app"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_repository_agent_mirror_queues_agent_owned_rclone_job(
    db_session, monkeypatch
):
    remote = RcloneRemote(
        id=3,
        name="prod-s3",
        provider="s3",
        config_source="managed",
        redacted_config={"type": "s3", "provider": "AWS"},
    )
    agent = AgentMachine(
        id=7,
        name="Laptop",
        agent_id="agt_laptop",
        token_hash="hash",
        token_prefix="token",
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    repository = Repository(
        id=9,
        name="Agent App",
        path="/agent/repositories/app",
        encryption="none",
        execution_target="agent",
        executor_type="agent",
        agent_machine_id=7,
    )
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=None,
        sync_policy="manual",
        sync_status="pending",
        sync_direction="agent_to_remote",
        extra_flags=["--fast-list"],
    )
    db_session.add_all([remote, agent, repository, storage])
    db_session.commit()
    queued_jobs = []

    def fake_queue(db, repo, *, job_kind, operation=None, **_kwargs):
        queued_jobs.append({"repo": repo, "job_kind": job_kind, "operation": operation})
        return SimpleNamespace(id=42)

    async def fake_wait(db, agent_job_id, *, timeout_seconds, **_kwargs):
        return {"return_code": 0, "stdout": "synced", "stderr": ""}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.queue_agent_repository_operation_job",
        fake_queue,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.wait_for_agent_repository_operation_job",
        fake_wait,
        raising=False,
    )
    service = RcloneRepositoryService(cache_root="/cache")

    status = await service.sync_repository(db_session, repository)

    assert queued_jobs[0]["job_kind"] == "repository.rclone_sync"
    assert queued_jobs[0]["operation"]["rclone"]["remote_name"] == "prod-s3"
    assert queued_jobs[0]["operation"]["rclone"]["remote_path"] == (
        "borg-ui/repositories/app"
    )
    assert queued_jobs[0]["operation"]["rclone"]["source_path"] == (
        "/agent/repositories/app"
    )
    assert queued_jobs[0]["operation"]["rclone"]["config"] == {
        "type": "s3",
        "provider": "AWS",
    }
    assert status["sync_status"] == "current"
    assert status["sync_direction"] == "agent_to_remote"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_repository_agent_mirror_records_failed_agent_result(
    db_session, monkeypatch
):
    remote = RcloneRemote(
        id=4,
        name="prod-s3",
        provider="s3",
        config_source="managed",
        redacted_config={"type": "s3", "provider": "AWS"},
    )
    agent = AgentMachine(
        id=8,
        name="Laptop",
        agent_id="agt_laptop_failed_sync",
        token_hash="hash",
        token_prefix="token",
        status="online",
        capabilities=["repository.rclone_sync"],
    )
    repository = Repository(
        id=10,
        name="Agent App Failed",
        path="/agent/repositories/app",
        encryption="none",
        execution_target="agent",
        executor_type="agent",
        agent_machine_id=8,
    )
    storage = RepositoryStorage(
        repository_id=10,
        backend="rclone",
        rclone_remote_id=4,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=None,
        sync_policy="manual",
        sync_status="pending",
        sync_direction="agent_to_remote",
    )
    db_session.add_all([remote, agent, repository, storage])
    db_session.commit()

    def fake_queue(db, repo, *, job_kind, operation=None, **_kwargs):
        return SimpleNamespace(id=43)

    async def fake_wait(db, agent_job_id, *, timeout_seconds, **_kwargs):
        return {"return_code": 2, "stdout": "", "stderr": "remote denied"}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.queue_agent_repository_operation_job",
        fake_queue,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.rclone_repository_service.wait_for_agent_repository_operation_job",
        fake_wait,
        raising=False,
    )
    service = RcloneRepositoryService(cache_root="/cache")

    status = await service.sync_repository(db_session, repository)

    assert status["sync_status"] == "failed"
    assert status["last_sync_error"] == "remote denied"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_repository_ssh_mirror_mounts_server_owned_source(db_session):
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    repository = Repository(
        id=9,
        name="SSH App",
        path="ssh://borg@storage.example:22/backups/app",
        connection_id=7,
        encryption="none",
        repository_type="ssh",
    )
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=None,
        sync_policy="manual",
        sync_status="pending",
        sync_direction="sshfs_mount_to_remote",
    )
    db_session.add_all([remote, repository, storage])
    db_session.commit()
    rclone = _RecordingRcloneService()
    mount_service = _RecordingMountService()
    service = RcloneRepositoryService(
        cache_root="/cache", service=rclone, ssh_mount_service=mount_service
    )

    await service.sync_repository(db_session, repository)

    assert mount_service.mount_calls == [(7, "/backups/app", None)]
    assert rclone.sync_calls[0][0] == "/tmp/sshfs_mount_9/backups/app"
    assert rclone.sync_calls[0][1] == "prod-s3:borg-ui/repositories/app"
    assert mount_service.unmount_calls == [("mount-ssh-repo", True)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preflight_remote_path_blocks_unverified_non_empty_target():
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    service = RcloneRepositoryService(
        cache_root="/cache",
        service=_ListingRcloneService([{"Name": "existing-repo", "IsDir": True}]),
    )

    with pytest.raises(ValueError, match="not empty"):
        await service.preflight_remote_path(
            remote,
            "borg-ui/repositories/app",
            verified_non_empty=False,
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_preflight_remote_path_allows_verified_non_empty_target():
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    service = RcloneRepositoryService(
        cache_root="/cache",
        service=_ListingRcloneService([{"Name": "existing-repo", "IsDir": True}]),
    )

    await service.preflight_remote_path(
        remote,
        "borg-ui/repositories/app",
        verified_non_empty=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_repository_persists_failure_when_rclone_raises(
    db_session, tmp_path
):
    cache_path = tmp_path / "cache" / "repositories" / "9"
    cache_path.mkdir(parents=True)
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    repository = Repository(id=9, name="App", path=str(cache_path), encryption="none")
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=str(cache_path),
        sync_policy="after_success",
        sync_status="pending",
    )
    db_session.add_all([remote, repository, storage])
    db_session.commit()

    service = RcloneRepositoryService(
        cache_root=str(tmp_path / "cache"), service=_ExplodingRcloneService()
    )

    status = await service.sync_repository(db_session, repository)

    db_session.refresh(storage)
    assert status["sync_status"] == "failed"
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "rclone timed out"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hydrate_repository_persists_failure_when_cache_swap_fails(
    db_session, tmp_path, monkeypatch
):
    cache_path = tmp_path / "cache" / "repositories" / "9"
    cache_path.mkdir(parents=True)
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    repository = Repository(id=9, name="App", path=str(cache_path), encryption="none")
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=str(cache_path),
        sync_policy="after_success",
        sync_status="pending",
    )
    db_session.add_all([remote, repository, storage])
    db_session.commit()

    def raise_swap_error(*args, **kwargs):
        raise RuntimeError("cache swap failed")

    monkeypatch.setattr(
        "app.services.rclone_repository_service.os.replace", raise_swap_error
    )
    service = RcloneRepositoryService(
        cache_root=str(tmp_path / "cache"), service=_SuccessfulRcloneService()
    )

    status = await service.hydrate_repository(db_session, repository)

    db_session.refresh(storage)
    assert status["sync_status"] == "failed"
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "cache swap failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_hydrate_repository_persists_failure_when_rclone_raises(
    db_session, tmp_path
):
    cache_path = tmp_path / "cache" / "repositories" / "9"
    remote = RcloneRemote(id=3, name="prod-s3", provider="s3")
    repository = Repository(id=9, name="App", path=str(cache_path), encryption="none")
    storage = RepositoryStorage(
        repository_id=9,
        backend="rclone",
        rclone_remote_id=3,
        rclone_remote_path="borg-ui/repositories/app",
        cache_path=str(cache_path),
        sync_policy="after_success",
        sync_status="pending",
    )
    db_session.add_all([remote, repository, storage])
    db_session.commit()

    service = RcloneRepositoryService(
        cache_root=str(tmp_path / "cache"), service=_ExplodingRcloneService()
    )

    status = await service.hydrate_repository(db_session, repository)

    db_session.refresh(storage)
    assert status["sync_status"] == "failed"
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "rclone timed out"
