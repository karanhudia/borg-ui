import pytest

from app.database.models import Repository, RepositoryStorage, RcloneRemote
from app.services.rclone_repository_service import (
    RcloneRepositoryService,
    normalize_rclone_relative_path,
)


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
