import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import InstalledPackage, PackageInstallJob
from app.services.package_service import PackageInstallService


@pytest.fixture
def package_service():
    return PackageInstallService()


@pytest.fixture
def installed_package(db_session):
    package = InstalledPackage(
        name="borghelper",
        install_command="apt-get install -y borghelper",
        description="Helper package",
        status="pending",
    )
    db_session.add(package)
    db_session.commit()
    db_session.refresh(package)
    return package


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_install_job_creates_pending_job(
    package_service, db_session, installed_package
):
    fake_task = object()

    with patch(
        "app.services.package_service.asyncio.create_task", return_value=fake_task
    ) as mock_create_task:
        job = await package_service.start_install_job(db_session, installed_package.id)

    assert job.id is not None
    assert job.status == "pending"
    assert package_service.running_jobs[job.id] is fake_task
    mock_create_task.assert_called_once()
    scheduled_coroutine = mock_create_task.call_args.args[0]
    scheduled_coroutine.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_install_job_raises_for_missing_package(
    package_service, db_session
):
    with pytest.raises(ValueError, match="Package 999 not found"):
        await package_service.start_install_job(db_session, 999)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_install_job_marks_package_installed(
    package_service, db_session, installed_package
):
    job = PackageInstallJob(package_id=installed_package.id, status="pending")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    process = AsyncMock()
    process.pid = None
    process.returncode = 0
    process.communicate.return_value = (b"installed ok", b"")

    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch("app.database.database.SessionLocal", testing_session_local):
        with patch(
            "app.services.package_service.asyncio.create_subprocess_shell",
            return_value=process,
        ):
            package_service.running_jobs[job.id] = object()
            await package_service._run_install_job(
                job.id,
                installed_package.id,
                installed_package.install_command,
                installed_package.name,
            )

    db_session.refresh(job)
    db_session.refresh(installed_package)

    assert job.status == "completed"
    assert job.exit_code == 0
    assert "installed ok" in job.stdout
    assert installed_package.status == "installed"
    assert installed_package.installed_at is not None
    assert job.id not in package_service.running_jobs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_install_job_marks_failure_on_nonzero_exit(
    package_service, db_session, installed_package
):
    job = PackageInstallJob(package_id=installed_package.id, status="pending")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    process = AsyncMock()
    process.pid = None
    process.returncode = 7
    process.communicate.return_value = (b"", b"permission denied")

    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch("app.database.database.SessionLocal", testing_session_local):
        with patch(
            "app.services.package_service.asyncio.create_subprocess_shell",
            return_value=process,
        ):
            package_service.running_jobs[job.id] = object()
            await package_service._run_install_job(
                job.id,
                installed_package.id,
                installed_package.install_command,
                installed_package.name,
            )

    db_session.refresh(job)
    db_session.refresh(installed_package)

    assert job.status == "failed"
    assert job.error_message == "Installation failed with exit code 7"
    assert installed_package.status == "failed"
    assert "permission denied" in installed_package.install_log
    assert job.id not in package_service.running_jobs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_install_job_marks_timeout_failure(
    package_service, db_session, installed_package
):
    job = PackageInstallJob(package_id=installed_package.id, status="pending")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    process = AsyncMock()
    process.pid = None
    process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    process.kill = MagicMock()

    async def passthrough_wait_for(awaitable, timeout):
        return await awaitable

    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch("app.database.database.SessionLocal", testing_session_local):
        with patch(
            "app.services.package_service.asyncio.create_subprocess_shell",
            return_value=process,
        ):
            with patch(
                "app.services.package_service.asyncio.wait_for",
                side_effect=passthrough_wait_for,
            ):
                package_service.running_jobs[job.id] = object()
                await package_service._run_install_job(
                    job.id,
                    installed_package.id,
                    installed_package.install_command,
                    installed_package.name,
                )

    db_session.refresh(job)
    db_session.refresh(installed_package)

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
    assert job.status == "failed"
    assert "timed out" in job.error_message
    assert installed_package.status == "failed"
    assert job.id not in package_service.running_jobs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_install_job_exits_gracefully_when_job_missing(
    package_service, db_session, installed_package
):
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch("app.database.database.SessionLocal", testing_session_local):
        await package_service._run_install_job(
            job_id=12345,
            package_id=installed_package.id,
            install_command=installed_package.install_command,
            package_name=installed_package.name,
        )

    assert package_service.running_jobs == {}


@pytest.mark.unit
def test_get_job_status_returns_job(db_session, installed_package):
    service = PackageInstallService()
    job = PackageInstallJob(package_id=installed_package.id, status="installing")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    fetched = service.get_job_status(db_session, job.id)

    assert fetched.id == job.id
    assert fetched.status == "installing"


@pytest.mark.unit
def test_get_running_jobs_filters_pending_and_installing(db_session, installed_package):
    service = PackageInstallService()
    pending = PackageInstallJob(package_id=installed_package.id, status="pending")
    installing = PackageInstallJob(package_id=installed_package.id, status="installing")
    completed = PackageInstallJob(package_id=installed_package.id, status="completed")
    db_session.add_all([pending, installing, completed])
    db_session.commit()

    jobs = service.get_running_jobs(db_session)

    assert {job.status for job in jobs} == {"pending", "installing"}
