import io
import zipfile

import yaml

from app.database.models import Repository, ScheduledJob
from app.scripts import export_config


def _add_repository(db_session, name: str, path: str) -> Repository:
    repository = Repository(
        name=name,
        path=path,
        repository_type="local",
        encryption="repokey",
        compression="lz4",
    )
    db_session.add(repository)
    db_session.commit()
    db_session.refresh(repository)
    return repository


def test_cli_writes_yaml_file_for_single_repository(tmp_path, db_session):
    repository = _add_repository(db_session, "App Config", "/backups/app-config")
    output_path = tmp_path / "borg-ui-config.yaml"
    stderr = io.StringIO()

    exit_code = export_config.main(
        ["--output", str(output_path)],
        session_factory=lambda: db_session,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert yaml.safe_load(output_path.read_text(encoding="utf-8")) == {
        "repositories": [repository.path],
        "compression": "lz4",
        "borg_ui_name": "App Config",
    }


def test_cli_writes_zip_file_for_selected_repositories(tmp_path, db_session):
    first = _add_repository(db_session, "App One", "/backups/app-one")
    second = _add_repository(db_session, "App Two", "/backups/app-two")
    _add_repository(db_session, "Ignored App", "/backups/ignored")
    output_path = tmp_path / "selected-configs.zip"

    exit_code = export_config.main(
        [
            "--repository-id",
            str(first.id),
            "--repository-id",
            str(second.id),
            "--output",
            str(output_path),
        ],
        session_factory=lambda: db_session,
    )

    assert exit_code == 0
    with zipfile.ZipFile(output_path) as archive:
        assert sorted(archive.namelist()) == ["appone.yaml", "apptwo.yaml"]
        assert yaml.safe_load(archive.read("appone.yaml"))["repositories"] == [
            "/backups/app-one"
        ]
        assert yaml.safe_load(archive.read("apptwo.yaml"))["repositories"] == [
            "/backups/app-two"
        ]


def test_cli_can_write_single_repository_export_to_stdout(db_session):
    repository = _add_repository(db_session, "Stdout App", "/backups/stdout")
    stdout = io.BytesIO()

    exit_code = export_config.main(
        ["--output", "-"],
        session_factory=lambda: db_session,
        stdout=stdout,
    )

    assert exit_code == 0
    assert yaml.safe_load(stdout.getvalue())["repositories"] == [repository.path]


def test_cli_no_schedules_excludes_schedule_retention(tmp_path, db_session):
    repository = _add_repository(db_session, "Scheduled App", "/backups/scheduled")
    db_session.add(
        ScheduledJob(
            name="scheduled-app-backup",
            cron_expression="0 2 * * *",
            repository=repository.path,
            enabled=True,
            prune_keep_daily=7,
            run_prune_after=True,
            run_compact_after=False,
        )
    )
    db_session.commit()
    output_path = tmp_path / "no-schedules.yaml"

    exit_code = export_config.main(
        ["--no-schedules", "--output", str(output_path)],
        session_factory=lambda: db_session,
    )

    assert exit_code == 0
    data = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert "keep_daily" not in data


def test_cli_returns_error_when_no_repositories_match(tmp_path, db_session):
    stderr = io.StringIO()
    output_path = tmp_path / "missing.yaml"

    exit_code = export_config.main(
        ["--repository-id", "999", "--output", str(output_path)],
        session_factory=lambda: db_session,
        stderr=stderr,
    )

    assert exit_code == 1
    assert "No repositories found to export" in stderr.getvalue()
    assert not output_path.exists()
