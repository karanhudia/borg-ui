"""Phase 6: an `operations` row wearing the legacy package-install surface."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    InstalledPackage,
    Operation,
)
from app.services.operations.package_facade import (
    PackageInstallFacade,
    active_package_install,
    resolve_package_job,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def logs_dir(tmp_path, monkeypatch):
    # The runner imports `app.config.settings` as `app_settings`; patch the
    # shared object rather than the runner's alias, which another test can
    # have replaced at module level.
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return tmp_path


def _package(db, *, name="wakeonlan"):
    package = InstalledPackage(
        name=name, install_command=f"apt-get install -y {name}", status="pending"
    )
    db.add(package)
    db.commit()
    return package


def _install_operation(db, *, package_id=3, status="queued", run_id="run-1"):
    op = Operation(
        repository_id=None,
        kind="package_install",
        category="system",
        status=status,
        trigger="manual",
        priority=0,
        run_id=run_id,
        params={"package_id": package_id},
    )
    db.add(op)
    db.commit()
    return op


def test_status_maps_installing_to_running(db):
    op = _install_operation(db)

    job = PackageInstallFacade(db, op)
    assert job.status == "pending"
    assert job.package_id == 3

    job.status = "installing"
    db.commit()
    assert op.status == "running"
    assert PackageInstallFacade(db, op).status == "installing"

    job.status = "completed"
    db.commit()
    assert op.status == "completed"
    assert PackageInstallFacade(db, op).status == "completed"


def test_output_round_trips_through_the_log_file(db, logs_dir):
    op = _install_operation(db, status="running")

    job = PackageInstallFacade(db, op)
    job.write_output(
        "Reading package lists...\nDone", "W: apt does not have a stable CLI"
    )
    db.commit()

    reread = PackageInstallFacade(db, op)
    assert reread.stdout == "Reading package lists...\nDone"
    assert reread.stderr == "W: apt does not have a stable CLI"
    assert op.log_file_path is not None


def test_output_survives_text_that_looks_like_a_sentinel(db, logs_dir):
    op = _install_operation(db, status="running")

    job = PackageInstallFacade(db, op)
    job.write_output("STDOUT:\nnot a real marker", "")
    db.commit()

    assert PackageInstallFacade(db, op).stdout == "STDOUT:\nnot a real marker"


def test_output_survives_the_stream_marker_inside_stdout(db, logs_dir):
    """The file format must not depend on any line apt could print: the
    streams are length-delimited, so even the old marker text round-trips."""
    op = _install_operation(db, status="running")
    stdout = "before\n===== BORG-UI PACKAGE STDERR =====\nafter"
    stderr = "E: unable to locate package"

    job = PackageInstallFacade(db, op)
    job.write_output(stdout, stderr)
    db.commit()

    job = PackageInstallFacade(db, op)
    assert job.stdout == stdout
    assert job.stderr == stderr


def test_missing_output_reads_as_empty_strings(db):
    op = _install_operation(db)

    job = PackageInstallFacade(db, op)
    assert job.stdout == ""
    assert job.stderr == ""
    assert job.exit_code is None


def test_exit_code_lives_in_the_result_json(db):
    op = _install_operation(db, status="running")

    job = PackageInstallFacade(db, op)
    job.exit_code = 100
    db.commit()

    assert op.result == {"exit_code": 100}
    assert PackageInstallFacade(db, op).exit_code == 100


def test_a_log_written_by_something_else_reads_as_stdout(db, logs_dir):
    op = _install_operation(db, status="running")
    path = logs_dir / "plain.log"
    path.write_text("a line the runner logged", encoding="utf-8")
    op.log_file_path = str(path)
    db.commit()

    job = PackageInstallFacade(db, op)
    assert job.stdout == "a line the runner logged"
    assert job.stderr == ""


def test_resolve_returns_none_for_an_unknown_id(db):
    op = _install_operation(db)

    assert isinstance(resolve_package_job(db, op.id), PackageInstallFacade)
    assert resolve_package_job(db, 9999) is None


def test_active_package_install_matches_on_the_params_package_id(db):
    assert active_package_install(db, 3) is None

    op = _install_operation(db, package_id=3)
    assert active_package_install(db, 3).id == op.id
    assert active_package_install(db, 4) is None

    op.status = "completed"
    db.commit()
    assert active_package_install(db, 3) is None
