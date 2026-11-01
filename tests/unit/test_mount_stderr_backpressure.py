"""Real pipes prove mount readiness and shutdown cannot depend on stderr capacity."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import Repository, SystemSettings
from app.services.mount_service import MountService


async def _wait_file(path):
    while not path.exists():
        await asyncio.sleep(0.01)


async def _kill_child(process):
    if process.returncode is None:
        process.kill()
    await asyncio.wait_for(process.communicate(), 3)


@pytest.mark.asyncio
async def test_large_stderr_does_not_block_readiness_and_stop_reaps_child(tmp_path):
    ready = tmp_path / "ready"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import sys,time,pathlib; sys.stderr.write('x'*2000000+'\\n'); sys.stderr.flush(); "
        f"pathlib.Path({str(ready)!r}).touch(); time.sleep(60)",
        stderr=asyncio.subprocess.PIPE,
    )
    service = MountService.__new__(MountService)
    service._borg_processes = {}
    try:
        owner = service._track_borg_process("mount", process)
        await asyncio.wait_for(_wait_file(ready), 3)
        assert len(owner.diagnostic) <= 8192
        await asyncio.wait_for(owner.stop(), 3)
        assert process.returncode is not None
        assert owner.task.done()
        assert service._borg_processes == {}
    finally:
        if process.returncode is None:
            await _kill_child(process)


@pytest.mark.asyncio
async def test_exit_diagnostic_is_bounded_redacted_and_registration_removed():
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('password=\\\"'+'s'*20000+'\\\"\\n'); "
        "sys.stderr.write('x'*12000+'\\npassword=hidden\\nPermission denied\\n')",
        stderr=asyncio.subprocess.PIPE,
    )
    service = MountService.__new__(MountService)
    service._borg_processes = {}
    try:
        owner = service._track_borg_process("mount", process)
        await asyncio.wait_for(owner.task, 3)
        assert len(owner.diagnostic) <= 8192
        assert "Permission denied" in owner.diagnostic
        assert "hidden" not in owner.diagnostic
        assert "ssss" not in owner.diagnostic
        assert service._borg_processes == {}
    finally:
        if process.returncode is None:
            await _kill_child(process)


@pytest.fixture
def real_child_mount(tmp_path):
    ready = tmp_path / "ready"
    spawned = []
    original_spawn = asyncio.create_subprocess_exec
    original_sleep = asyncio.sleep
    repo = Repository(id=1, name="repo", path="/repository", repository_type="local")
    db = MagicMock()

    def query(model):
        result = MagicMock()
        if model == Repository:
            result.filter.return_value.first.return_value = repo
        elif model == SystemSettings:
            result.first.return_value = SystemSettings(mount_timeout=10)
            result.filter.return_value.all.return_value = []
        return result

    db.query.side_effect = query

    async def spawn(*args, **kwargs):
        child = await original_spawn(
            sys.executable,
            "-c",
            "import sys,time,pathlib; sys.stderr.write('x'*2000000+'\\n'); sys.stderr.flush(); "
            "sys.stderr.write('password=hidden\\nmount still initializing\\n'); sys.stderr.flush(); "
            f"pathlib.Path({str(ready)!r}).touch(); time.sleep(60)",
            stderr=asyncio.subprocess.PIPE,
            start_new_session=kwargs.get("start_new_session", False),
        )
        spawned.append(child)
        return child

    async def poll(_):
        await original_sleep(0.05)

    with (
        patch("app.services.mount_service.settings") as settings,
        patch("app.services.mount_service.SessionLocal", return_value=db),
        patch(
            "app.services.mount_service.subprocess.run",
            return_value=SimpleNamespace(stdout="", returncode=0),
        ),
    ):
        settings.data_dir = str(tmp_path)
        service = MountService()
        mount_path = tmp_path / "mounts" / "repository"
        with (
            patch(
                "app.services.mount_service.asyncio.create_subprocess_exec",
                side_effect=spawn,
            ),
            patch("app.services.mount_service.asyncio.sleep", side_effect=poll),
            patch(
                "app.services.mount_service.resolve_repository_ssh_connection",
                return_value=None,
            ),
            patch(
                "app.services.mount_service.subprocess.run",
                side_effect=lambda *a, **k: SimpleNamespace(
                    stdout=str(mount_path) if ready.exists() else "", returncode=0
                ),
            ),
        ):
            yield service, spawned, ready


@pytest.mark.asyncio
async def test_mount_success_keeps_drain_until_unmount(real_child_mount):
    service, spawned, ready = real_child_mount
    try:
        _, mount_id = await asyncio.wait_for(service.mount_borg_archive(1), 3)
        assert ready.exists()
        assert mount_id in service._borg_processes
        with patch.object(service, "_unmount_borg", new=AsyncMock(return_value=True)):
            assert await service.unmount(mount_id)
        assert spawned[0].returncode is not None
        assert service._borg_processes == {}
    finally:
        for process in spawned:
            if process.returncode is None:
                await _kill_child(process)


@pytest.mark.asyncio
async def test_mount_cancellation_reaps_process_and_drain(real_child_mount):
    service, spawned, _ = real_child_mount
    task = asyncio.create_task(service.mount_borg_archive(1))
    try:
        while not spawned:
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert spawned[0].returncode is not None
        assert service._borg_processes == {}
    finally:
        if not task.done():
            task.cancel()
        for process in spawned:
            if process.returncode is None:
                await _kill_child(process)


@pytest.mark.asyncio
async def test_cancelling_stop_kills_a_child_that_ignores_term(tmp_path):
    ready = tmp_path / "term-ready"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import signal,time,pathlib; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(ready)!r}).touch(); time.sleep(60)",
        stderr=asyncio.subprocess.PIPE,
    )
    service = MountService.__new__(MountService)
    service._borg_processes = {}
    stop = None
    try:
        owner = service._track_borg_process("mount", process)
        await asyncio.wait_for(_wait_file(ready), 3)
        stop = asyncio.create_task(owner.stop())
        await asyncio.sleep(0.01)
        stop.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(stop, 3)
        assert process.returncode is not None
        assert owner.task.done()
        assert service._borg_processes == {}
    finally:
        if stop is not None and not stop.done():
            stop.cancel()
        if process.returncode is None:
            await _kill_child(process)


@pytest.mark.asyncio
async def test_readiness_timeout_keeps_bounded_diagnostic_and_reaps_child(
    real_child_mount,
):
    service, spawned, _ = real_child_mount
    try:
        with patch(
            "app.services.mount_service.subprocess.run",
            return_value=SimpleNamespace(stdout="", returncode=0),
        ):
            with pytest.raises(Exception, match="Mount timeout") as failure:
                await asyncio.wait_for(service.mount_borg_archive(1), 3)
        assert "mount still initializing" in str(failure.value)
        assert "hidden" not in str(failure.value)
        assert len(str(failure.value)) < 8500
        assert spawned[0].returncode is not None
        assert service._borg_processes == {}
    finally:
        for process in spawned:
            if process.returncode is None:
                await _kill_child(process)


@pytest.mark.asyncio
async def test_stop_cancels_a_stderr_reader_that_never_reaches_eof():
    process = SimpleNamespace(
        returncode=0,
        stderr=SimpleNamespace(
            read=AsyncMock(side_effect=lambda _: asyncio.Event().wait())
        ),
        wait=AsyncMock(return_value=0),
    )

    # An async reader that remains pending, even after its direct child exited.
    async def never_eof(_):
        await asyncio.Event().wait()

    process.stderr.read = never_eof
    service = MountService.__new__(MountService)
    service._borg_processes = {}
    owner = service._track_borg_process("mount", process)
    owner.stop_timeout = 0.01
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(owner.stop(), 0.2)
        assert owner.task.done()
        assert service._borg_processes == {}
    finally:
        owner.task.cancel()
        await asyncio.gather(owner.task, return_exceptions=True)


@pytest.mark.asyncio
async def test_inherited_stderr_does_not_keep_exited_mount_owner_alive():
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); sys.stderr.write('mount failed\\n')",
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    service = MountService.__new__(MountService)
    service._borg_processes = {}
    try:
        owner = service._track_borg_process("mount", process, process_group=True)
        while process.returncode is None:
            await asyncio.sleep(0.01)
        await asyncio.wait_for(owner.stop(), 3)
        assert owner.task.done()
        assert "mount failed" in owner.diagnostic
        assert service._borg_processes == {}
    finally:
        import os, signal

        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await _kill_child(process)


@pytest.mark.asyncio
async def test_mount_timeout_survives_cleanup_error(real_child_mount):
    from app.services.mount_service import _BorgMountProcess

    service, spawned, _ = real_child_mount
    original_stop = _BorgMountProcess.stop

    async def failed_cleanup(owner):
        await original_stop(owner)
        raise RuntimeError("cleanup marker")

    try:
        with (
            patch.object(_BorgMountProcess, "stop", new=failed_cleanup),
            patch(
                "app.services.mount_service.subprocess.run",
                return_value=SimpleNamespace(stdout="", returncode=0),
            ),
        ):
            with pytest.raises(Exception, match="Mount timeout"):
                await asyncio.wait_for(service.mount_borg_archive(1), 3)
        assert spawned[0].returncode is not None
        assert service._borg_processes == {}
    finally:
        for process in spawned:
            if process.returncode is None:
                await _kill_child(process)


@pytest.mark.asyncio
async def test_private_key_body_split_across_chunks_is_never_retained():
    process = SimpleNamespace(
        returncode=0,
        stderr=SimpleNamespace(
            read=AsyncMock(
                side_effect=[
                    b"prefix\n-----BE",
                    b"GIN OPENSSH PRIVATE KEY-----\nSENSITIVE",
                    b"BODY\n-----END OPENSSH PRIVATE KEY-----\nPermission denied\n",
                    b"",
                ]
            )
        ),
        wait=AsyncMock(return_value=0),
    )
    service = MountService.__new__(MountService)
    service._borg_processes = {}
    owner = service._track_borg_process("mount", process)
    await owner.task
    assert "SENSITIVE" not in owner.diagnostic
    assert "BODY" not in owner.diagnostic
    assert "Permission denied" in owner.diagnostic
    assert service._borg_processes == {}


@pytest.mark.asyncio
async def test_drain_read_error_terminates_and_reaps_owned_child():
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time;time.sleep(60)",
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    service = MountService.__new__(MountService)
    service._borg_processes = {}
    try:
        with patch.object(
            process.stderr,
            "read",
            new=AsyncMock(side_effect=OSError("password=secret")),
        ):
            owner = service._track_borg_process("mount", process, process_group=True)
            with pytest.raises(OSError):
                await owner.task
            await asyncio.wait_for(process.wait(), 1)
            assert service._borg_processes == {}
    finally:
        if process.returncode is None:
            await _kill_child(process)
