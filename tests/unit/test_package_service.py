import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.database.models import InstalledPackage, Operation
from app.services.operations.package_facade import PackageInstallFacade
from app.services.package_service import PackageInstallService
from tests.utils.operations import seed_job_operation


def _install_operation(db_session, package, *, status="queued", run_id="run-1"):
    """Phase 6: the install job is an `operations` row (spec 6.2, 6.3)."""
    op = Operation(
        repository_id=None,
        kind="package_install",
        category="system",
        status=status,
        trigger="manual",
        priority=0,
        run_id=run_id,
        params={"package_id": package.id},
    )
    db_session.add(op)
    db_session.commit()
    db_session.refresh(op)
    return op


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
async def test_start_install_job_queues_an_operation_without_spawning(
    package_service, db_session, installed_package
):
    """Phase 6: the route only enqueues; the runner starts the install."""
    with patch("app.services.package_service.asyncio.create_task") as mock_create_task:
        job = await package_service.start_install_job(db_session, installed_package.id)

    operation = db_session.query(Operation).one()
    assert job.id == operation.id
    assert job.status == "pending"
    assert operation.kind == "package_install"
    assert operation.category == "system"
    assert operation.repository_id is None
    assert operation.params == {"package_id": installed_package.id}
    mock_create_task.assert_not_called()


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
    operation = _install_operation(db_session, installed_package)
    job = PackageInstallFacade(db_session, operation)

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
            await package_service.run_install_job(job.id)

    db_session.refresh(operation)
    db_session.refresh(installed_package)

    assert job.status == "completed"
    assert job.exit_code == 0
    assert "installed ok" in job.stdout
    assert installed_package.status == "installed"
    assert installed_package.installed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_install_job_marks_failure_on_nonzero_exit(
    package_service, db_session, installed_package
):
    operation = _install_operation(db_session, installed_package)
    job = PackageInstallFacade(db_session, operation)

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
            await package_service.run_install_job(job.id)

    db_session.refresh(operation)
    db_session.refresh(installed_package)

    assert job.status == "failed"
    assert job.error_message == "Installation failed with exit code 7"
    assert installed_package.status == "failed"
    assert "permission denied" in installed_package.install_log


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_install_job_marks_timeout_failure(
    package_service, db_session, installed_package
):
    operation = _install_operation(db_session, installed_package)
    job = PackageInstallFacade(db_session, operation)

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
                await package_service.run_install_job(job.id)

    db_session.refresh(operation)
    db_session.refresh(installed_package)

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
    assert job.status == "failed"
    assert "timed out" in job.error_message
    assert installed_package.status == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_install_job_exits_gracefully_when_job_missing(
    package_service, db_session, installed_package
):
    testing_session_local = sessionmaker(
        bind=db_session.get_bind(), autocommit=False, autoflush=False
    )

    with patch("app.database.database.SessionLocal", testing_session_local):
        await package_service.run_install_job(12345)

    # Nothing raised, and no job row was invented for a missing id.
    assert db_session.query(Operation).count() == 0


@pytest.mark.unit
def test_get_job_status_returns_an_operation_backed_job(db_session, installed_package):
    service = PackageInstallService()
    operation = _install_operation(db_session, installed_package, status="running")

    fetched = service.get_job_status(db_session, operation.id)

    assert fetched.id == operation.id
    assert fetched.status == "installing"


@pytest.mark.unit
def test_get_job_status_still_returns_a_pre_phase_6_row(db_session, installed_package):
    service = PackageInstallService()
    job = seed_job_operation(
        db_session,
        "package_install",
        package_id=installed_package.id,
        status="installing",
    )
    db_session.commit()
    db_session.refresh(job)

    fetched = service.get_job_status(db_session, job.id)

    assert fetched.id == job.id
    assert fetched.status == "installing"


@pytest.mark.unit
def test_get_running_jobs_filters_pending_and_installing(db_session, installed_package):
    service = PackageInstallService()
    _install_operation(db_session, installed_package, status="queued", run_id="a")
    _install_operation(db_session, installed_package, status="running", run_id="b")
    _install_operation(db_session, installed_package, status="completed", run_id="c")
    db_session.commit()

    jobs = service.get_running_jobs(db_session)

    assert sorted(job.status for job in jobs) == ["installing", "pending"]
