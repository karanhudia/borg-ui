"""A real noisy Borg stand-in must not block mount readiness."""

import asyncio
import os
import stat
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import Repository, SystemSettings
from app.services.mount_service import MountService


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["ready", "exit", "timeout"])
async def test_large_stderr_file_preserves_readiness_and_failure_diagnostics(
    tmp_path, monkeypatch, outcome
):
    ready = tmp_path / "ready"
    children = []
    handles = []
    original_spawn = asyncio.create_subprocess_exec
    original_sleep = asyncio.sleep
    repo = Repository(id=1, name="repo", path="/repository", repository_type="local")
    db = MagicMock()

    def query(model):
        result = MagicMock()
        if model == Repository:
            result.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            result.first.return_value = SystemSettings(mount_timeout=5)
            result.filter.return_value.all.return_value = []
        return result

    db.query.side_effect = query

    async def spawn(*args, **kwargs):
        stderr = kwargs["stderr"]
        assert stat.S_ISREG(os.fstat(stderr.fileno()).st_mode)
        assert not kwargs.get("start_new_session", False)
        handles.append(stderr)
        child = await original_spawn(
            sys.executable,
            "-c",
            "import sys,time,pathlib; sys.stderr.write('x'*2000000+'\\n'); "
            "sys.stderr.write('password=hidden\\nmount diagnostic\\n'); sys.stderr.flush(); "
            f"pathlib.Path({str(ready)!r}).touch(); "
            + ("sys.exit(2)" if outcome == "exit" else "time.sleep(60)"),
            stderr=stderr,
            stdout=kwargs["stdout"],
            stdin=kwargs["stdin"],
        )
        children.append(child)
        return child

    async def poll(delay):
        if delay == 5:

            async def initialized():
                while not ready.exists():
                    await original_sleep(0.01)

            await asyncio.wait_for(initialized(), 3)
            if outcome == "exit":
                await asyncio.wait_for(children[0].wait(), 3)
        else:
            await original_sleep(0.01)

    monkeypatch.setattr("app.services.mount_service.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.services.mount_service.SessionLocal", lambda: db)
    service = MountService()
    mount_path = tmp_path / "mounts" / "repository"
    monkeypatch.setattr(
        "app.services.mount_service.asyncio.create_subprocess_exec", spawn
    )
    monkeypatch.setattr("app.services.mount_service.asyncio.sleep", poll)
    monkeypatch.setattr(
        "app.services.mount_service.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            stdout=str(mount_path) if outcome == "ready" else "", returncode=0
        ),
    )
    try:
        if outcome == "ready":
            _, mount_id = await asyncio.wait_for(service.mount_borg_archive(1), 5)
            info = service.active_mounts[mount_id]
            stderr_root = info.temp_root
            assert ready.exists()
            assert (
                os.path.getsize(
                    os.path.join(stderr_root, f"borg-mount-{mount_id}.stderr")
                )
                > 2000000
            )
            with patch.object(
                service, "_unmount_borg", new=AsyncMock(return_value=True)
            ):
                assert await service.unmount(mount_id)
            assert not os.path.exists(stderr_root)
        else:
            with pytest.raises(Exception, match="mount diagnostic") as failure:
                await asyncio.wait_for(service.mount_borg_archive(1), 5)
            assert "hidden" not in str(failure.value)
            assert len(str(failure.value)) < 8500
            assert not os.path.exists(os.path.dirname(handles[0].name))
        assert all(handle.closed for handle in handles)
        await asyncio.wait_for(children[0].wait(), 3)
    finally:
        for child in children:
            if child.returncode is None:
                child.kill()
            await asyncio.wait_for(child.wait(), 3)
