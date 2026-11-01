"""Mount target checks cover every local SSHFS and Borg allocation branch."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.database.models import (
    AgentJob,
    Repository,
    SSHConnection,
    SSHKey,
    SystemSettings,
    UserRepositoryPermission,
)
from app.services import mount_service as ms


@pytest.fixture
def mount_service(tmp_path, monkeypatch):
    service = ms.MountService.__new__(ms.MountService)
    service.mount_base_dir = tmp_path / "mounts"
    service.mount_base_dir.mkdir()
    service.active_mounts = {}
    service._save_state = Mock()
    service._cleanup_temp_files = Mock()
    service._unmount_fuse = AsyncMock()
    service._is_mount_point_occupied = Mock(return_value=False)
    session = MagicMock()

    def query(model):
        result = MagicMock()
        if model is Repository:
            result.filter.return_value.first.return_value = Repository(
                id=1, name="Fixture", path="/inert/repository", repository_type="local"
            )
        elif model is SystemSettings:
            result.first.return_value = SystemSettings(mount_timeout=10)
        elif model is SSHConnection:
            result.filter.return_value.first.return_value = SSHConnection(
                id=1, ssh_key_id=1, host="inert.invalid", username="fixture", port=22
            )
        elif model is SSHKey:
            result.filter.return_value.first.return_value = SSHKey(id=1, name="Fixture")
        return result

    session.query.side_effect = query
    monkeypatch.setattr(ms, "SessionLocal", lambda: session)
    service._check_sshfs_available = AsyncMock(return_value=True)
    service._decrypt_and_write_key = Mock(return_value="/inert/key")
    service._check_remote_is_file = AsyncMock(return_value=False)
    service._execute_sshfs_mount = AsyncMock()
    service._verify_mount_readable = AsyncMock()
    process = SimpleNamespace(pid=123, returncode=None)
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(ms.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(ms.asyncio, "sleep", AsyncMock())
    output = MagicMock()
    output.__contains__.return_value = True
    monkeypatch.setattr(
        ms.subprocess, "run", Mock(return_value=SimpleNamespace(stdout=output))
    )
    return service, spawn


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", ["single", "shared-directory", "shared-file"])
@pytest.mark.parametrize(
    "remote,relative",
    [
        ("/", "."),
        ("/srv/with spaces", "srv/with spaces"),
        ("/a/../../outside", "outside"),
        # Borg starts the archived path after "/./"; the spelling is kept
        ("/srv/./data", "srv/./data"),
    ],
)
async def test_ssh_targets_stay_below_staging_root(
    mount_service, tmp_path, monkeypatch, builder, remote, relative
):
    service, _ = mount_service
    root = tmp_path / "staging"
    root.mkdir()
    monkeypatch.setattr(ms.tempfile, "mkdtemp", lambda **kwargs: str(root))
    if builder == "shared-file" and remote == "/":
        remote, relative = "/file", "file"
    if builder == "single":
        returned, _ = await service.mount_ssh_directory(1, remote)
        assert returned == str(root)
        expected = root if relative == "." else root / relative
    else:
        service._check_remote_is_file.return_value = builder == "shared-file"
        returned, mounts = await service.mount_ssh_paths_shared(
            1, [remote], preserve_symlinks=True
        )
        assert returned == str(root)
        assert mounts[0][1] == relative
        expected = (
            (root / relative).parent
            if builder == "shared-file" and relative != "."
            else root / relative
        )
    call = service._execute_sshfs_mount.call_args.kwargs
    assert os.path.normpath(call["mount_point"]) == os.path.normpath(str(expected))
    assert os.path.commonpath(
        [str(root), os.path.realpath(call["mount_point"])]
    ) == str(root)
    assert call["remote_path"] == (
        os.path.dirname(remote) or "/" if builder == "shared-file" else remote
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("builder", ["single", "shared-directory", "shared-file"])
async def test_ssh_symlink_escape_is_refused_before_mkdir_or_mount(
    mount_service, tmp_path, monkeypatch, builder
):
    service, _ = mount_service
    root, outside = tmp_path / "staging", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(ms.tempfile, "mkdtemp", lambda **kwargs: str(root))
    mkdir = Mock(side_effect=AssertionError("unvalidated target reached mkdir"))
    monkeypatch.setattr(ms.os, "makedirs", mkdir)
    with pytest.raises(ValueError, match="staging root"):
        if builder == "single":
            await service.mount_ssh_directory(1, "/link/new")
        else:
            service._check_remote_is_file.return_value = builder == "shared-file"
            remote = "/link/new/file" if builder == "shared-file" else "/link/new"
            await service.mount_ssh_paths_shared(1, [remote], preserve_symlinks=True)
    mkdir.assert_not_called()
    service._execute_sshfs_mount.assert_not_awaited()
    assert not (outside / "new").exists()


@pytest.mark.asyncio
async def test_shared_root_symlink_is_checked_before_child_reuse(
    mount_service, tmp_path, monkeypatch
):
    service, _ = mount_service
    root, outside = tmp_path / "staging", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    monkeypatch.setattr(ms.tempfile, "mkdtemp", lambda **kwargs: str(root))

    async def mount(**kwargs):
        (root / "link").symlink_to(outside, target_is_directory=True)

    service._execute_sshfs_mount.side_effect = mount
    mkdir = Mock(side_effect=AssertionError("unvalidated child reached mkdir"))
    monkeypatch.setattr(ms.os, "makedirs", mkdir)
    with pytest.raises(ValueError, match="staging root"):
        await service.mount_ssh_paths_shared(
            1, ["/", "/link/new"], preserve_symlinks=True
        )
    mkdir.assert_not_called()
    assert service._execute_sshfs_mount.await_count == 1
    assert not (outside / "new").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target", ["../outside", "absolute", ".", "link/new", "nul\x00byte"]
)
async def test_operator_borg_mount_denial_has_no_side_effects(
    mount_service, tmp_path, monkeypatch, target
):
    service, spawn = mount_service
    outside = tmp_path / "outside"
    outside.mkdir()
    (service.mount_base_dir / "link").symlink_to(outside, target_is_directory=True)
    supplied = str(outside / "new") if target == "absolute" else target
    mkdir = Mock(side_effect=AssertionError("denied request reached mkdir"))
    monkeypatch.setattr(ms.os, "makedirs", mkdir)
    with pytest.raises(ms.MountPointNotAllowed):
        await service.mount_borg_archive(
            1, mount_point=supplied, confine_to_mount_base=True
        )
    mkdir.assert_not_called()
    spawn.assert_not_awaited()
    assert not (outside / "new").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("automatic", [False, True])
async def test_borg_suffixed_candidate_is_checked_before_mkdir(
    mount_service, tmp_path, monkeypatch, automatic
):
    service, spawn = mount_service
    occupied = service.mount_base_dir / "chosen"
    occupied.mkdir()
    (occupied / "inert.txt").write_text("fixture")
    outside = tmp_path / "outside"
    outside.mkdir()
    (service.mount_base_dir / "chosen_12345678").symlink_to(
        outside, target_is_directory=True
    )
    monkeypatch.setattr(ms.uuid, "uuid4", lambda: SimpleNamespace(hex="12345678abcdef"))
    mkdir = Mock(side_effect=AssertionError("unvalidated suffix reached mkdir"))
    monkeypatch.setattr(ms.os, "makedirs", mkdir)
    with pytest.raises(ms.MountPointNotAllowed):
        await service.mount_borg_archive(
            1,
            archive_name="chosen",
            mount_point=None if automatic else str(occupied),
            confine_to_mount_base=True,
        )
    mkdir.assert_not_called()
    spawn.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "relative",
        "absolute",
        "automatic",
        "occupied",
        "admin-outside",
        "admin-relative-parent",
    ],
)
async def test_valid_borg_mount_targets_preserve_behavior(
    mount_service, tmp_path, kind
):
    service, spawn = mount_service
    target = service.mount_base_dir / "chosen"
    supplied = "chosen" if kind == "relative" else str(target)
    if kind == "automatic":
        supplied = None
    elif kind == "occupied":
        target.mkdir()
        (target / "inert.txt").write_text("fixture")
    elif kind == "admin-outside":
        target = tmp_path / "admin-custom"
        supplied = str(target)
    elif kind == "admin-relative-parent":
        # an administrator's relative name is joined as before, unchecked
        supplied = "../admin-relative"
        target = service.mount_base_dir / supplied
    selected, mount_id = await service.mount_borg_archive(
        1,
        archive_name="chosen",
        mount_point=supplied,
        confine_to_mount_base=not kind.startswith("admin-"),
    )
    if kind == "occupied":
        assert selected.startswith(str(target) + "_")
    else:
        assert selected == str(target)
    # by value: where the mount point sits in the argv is not this test's concern
    assert selected in spawn.call_args.args
    assert service.active_mounts[mount_id].mount_point == selected


@pytest.mark.parametrize("target", ["../outside", "absolute"])
def test_operator_mount_route_maps_denial_to_403_without_creation(
    test_client,
    test_db,
    operator_user,
    operator_headers,
    mount_service,
    tmp_path,
    monkeypatch,
    target,
):
    from app.api import mounts

    service, spawn = mount_service
    repo = Repository(
        name="Route fixture",
        path="/inert/repository",
        repository_type="local",
        encryption="none",
    )
    test_db.add(repo)
    test_db.flush()
    test_db.add(
        UserRepositoryPermission(
            user_id=operator_user.id, repository_id=repo.id, role="operator"
        )
    )
    test_db.commit()
    monkeypatch.setattr(mounts, "mount_service", service)
    mkdir = Mock(side_effect=AssertionError("denied route reached mkdir"))
    monkeypatch.setattr(ms.os, "makedirs", mkdir)
    supplied = str(tmp_path / "outside") if target == "absolute" else target
    response = test_client.post(
        "/api/mounts/borg",
        json={"repository_id": repo.id, "mount_point": supplied},
        headers=operator_headers,
    )
    assert response.status_code == 403
    assert (
        response.json()["detail"]["key"] == "backend.errors.filesystem.permissionDenied"
    )
    mkdir.assert_not_called()
    spawn.assert_not_awaited()
    assert test_db.query(AgentJob).count() == 0
