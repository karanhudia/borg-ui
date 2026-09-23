"""`has_logs` for a list of backups reads a log file only where its text can
still change the answer (#1118)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.database.models import (
    AgentJob,
    AgentJobLog,
    AgentMachine,
    Operation,
    OperationBackupDetails,
    Repository,
    SystemSettings,
)
from app.services.operations.backup_facade import (
    backup_facades,
    backup_job_has_logs,
    backup_jobs_have_logs,
)

START = datetime(2026, 9, 1, 2, 0, 0)


def _set_log_save_policy(db, policy):
    settings = db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
    settings.log_save_policy = policy
    db.commit()


@pytest.fixture
def read_files(monkeypatch, tmp_path):
    """The log files whose text was read, in order."""
    paths = []
    original = Path.read_text

    def spy(self, *args, **kwargs):
        if self.is_relative_to(tmp_path):
            paths.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    return paths


def _backup(db, repo, i, *, status, log_text, execution_mode="local", tmp_path):
    """A completed backup whose transcript sits in a file of its own."""
    log_file = tmp_path / f"backup-{i}.log"
    log_file.write_text(log_text, encoding="utf-8")
    at = START + timedelta(hours=i)
    op = Operation(
        repository_id=repo.id,
        kind="backup",
        category="backup",
        status=status,
        trigger="manual",
        run_id=f"run-{i}",
        execution_mode=execution_mode,
        log_file_path=str(log_file),
        started_at=at,
        completed_at=at + timedelta(minutes=1),
    )
    db.add(op)
    db.flush()
    db.add(OperationBackupDetails(operation_id=op.id, archive_name=f"archive-{i}"))
    return op


def _seed_mixed_outcomes(db, tmp_path):
    """Twelve server-side backups: four failed, four with warnings, four
    clean. One clean backup's transcript carries a warning line."""
    repo = Repository(name="repo", path="/repos/one", encryption="none")
    db.add(repo)
    db.commit()
    ops = {}
    for i in range(12):
        status = ("failed", "completed_with_warnings", "completed")[i % 3]
        text = "A f\nWarning: file changed" if i == 11 else "A f\nA g"
        ops[i] = _backup(db, repo, i, status=status, log_text=text, tmp_path=tmp_path)
    db.commit()
    return repo, ops


def _has_logs(db, policy):
    _set_log_save_policy(db, policy)
    jobs = backup_facades(
        db,
        db.query(Operation)
        .filter(Operation.kind == "backup")
        .order_by(Operation.id)
        .all(),
    )
    return backup_jobs_have_logs(db, jobs, log_save_policy=policy)


@pytest.mark.unit
@pytest.mark.parametrize("policy", ["failed_only", "all_jobs"])
def test_policies_that_never_read_text_read_no_file(
    test_db, tmp_path, read_files, policy
):
    _, ops = _seed_mixed_outcomes(test_db, tmp_path)

    answers = _has_logs(test_db, policy)

    assert read_files == []
    expected = {
        "failed_only": {i: op.status == "failed" for i, op in ops.items()},
        "all_jobs": {i: True for i in ops},
    }[policy]
    assert {i: answers[op.id] for i, op in ops.items()} == expected


@pytest.mark.unit
def test_only_a_clean_completed_backup_has_its_file_read(test_db, tmp_path, read_files):
    """Failed and warning backups are decided by their status; only the
    clean ones need their transcript searched for a marker."""
    _, ops = _seed_mixed_outcomes(test_db, tmp_path)

    answers = _has_logs(test_db, "failed_and_warnings")

    clean = [op for op in ops.values() if op.status == "completed"]
    assert sorted(read_files) == sorted(op.log_file_path for op in clean)
    assert {i: answers[op.id] for i, op in ops.items()} == {
        i: op.status != "completed" or i == 11 for i, op in ops.items()
    }


@pytest.mark.unit
def test_an_error_message_with_a_marker_decides_without_the_file(
    test_db, tmp_path, read_files
):
    repo = Repository(name="repo", path="/repos/one", encryption="none")
    test_db.add(repo)
    test_db.commit()
    op = _backup(
        test_db, repo, 0, status="completed", log_text="A f", tmp_path=tmp_path
    )
    op.error_message = "Warning: 1 file changed while reading"
    test_db.commit()

    answers = _has_logs(test_db, "failed_and_warnings")

    assert answers[op.id] is True
    assert read_files == []


@pytest.mark.unit
def test_a_pending_backup_is_refused_without_reading_its_file(
    test_db, tmp_path, read_files
):
    """A backup back in the queue keeps its file from an earlier attempt;
    the policy refuses a pending job whatever that file says."""
    repo = Repository(name="repo", path="/repos/one", encryption="none")
    test_db.add(repo)
    test_db.commit()
    op = _backup(
        test_db, repo, 0, status="queued", log_text="Warning: x", tmp_path=tmp_path
    )
    test_db.commit()

    answers = _has_logs(test_db, "failed_and_warnings")

    assert answers[op.id] is False
    assert read_files == []


def _agent_backup(db, repo, machine, i, *, lines, log_text, tmp_path):
    op = _backup(
        db,
        repo,
        i,
        status="completed",
        log_text=log_text,
        execution_mode="agent",
        tmp_path=tmp_path,
    )
    agent_job = AgentJob(
        agent_machine_id=machine.id,
        operation_id=op.id,
        job_type="backup",
        status="completed",
        payload={},
    )
    db.add(agent_job)
    db.flush()
    db.add_all(
        AgentJobLog(
            agent_job_id=agent_job.id,
            sequence=n,
            stream="stdout",
            created_at=START,
            message=line,
        )
        for n, line in enumerate(lines)
    )
    return op


@pytest.mark.unit
def test_an_agent_backup_is_decided_on_its_log_lines_not_its_file(
    test_db, tmp_path, read_files
):
    """The file of an agent backup is written from its log lines at
    completion, so the lines answer for it. Only a backup whose lines are
    gone falls back to the file."""
    machine = AgentMachine(
        name="machine", agent_id="agent-1", token_hash="x", token_prefix="p"
    )
    repo = Repository(name="repo", path="/repos/one", encryption="none")
    test_db.add_all([machine, repo])
    test_db.commit()
    clean = _agent_backup(
        test_db,
        repo,
        machine,
        0,
        lines=["A f", "A g"],
        log_text="A f\nA g",
        tmp_path=tmp_path,
    )
    warned = _agent_backup(
        test_db,
        repo,
        machine,
        1,
        lines=["A f", "Warning: x"],
        log_text="A f\nWarning: x",
        tmp_path=tmp_path,
    )
    lines_gone = _agent_backup(
        test_db,
        repo,
        machine,
        2,
        lines=[],
        log_text="A f\nWarning: y",
        tmp_path=tmp_path,
    )
    test_db.commit()

    answers = _has_logs(test_db, "failed_and_warnings")

    assert (answers[clean.id], answers[warned.id], answers[lines_gone.id]) == (
        False,
        True,
        True,
    )
    assert read_files == [lines_gone.log_file_path]


@pytest.mark.unit
def test_one_backup_reads_its_file_after_lines_without_a_marker(
    test_client, test_db, admin_headers, tmp_path, read_files
):
    """The list's marker query is the database's `LIKE`, which SQLite runs
    over a text up to its first NUL byte. One backup's answer reads the
    transcript after the lines, so a marker behind a NUL still opens the
    log where a route serves it."""
    _set_log_save_policy(test_db, "failed_and_warnings")
    machine = AgentMachine(
        name="machine", agent_id="agent-1", token_hash="x", token_prefix="p"
    )
    repo = Repository(name="repo", path="/repos/one", encryption="none")
    test_db.add_all([machine, repo])
    test_db.commit()
    line = "ok\0WARNING: skipped file"
    backup = _agent_backup(
        test_db, repo, machine, 0, lines=[line], log_text=line, tmp_path=tmp_path
    )
    test_db.commit()

    jobs = backup_facades(test_db, [backup])
    assert backup_jobs_have_logs(test_db, jobs) == {backup.id: False}
    assert read_files == []
    assert backup_job_has_logs(test_db, jobs[0]) is True
    assert read_files == [backup.log_file_path]

    response = test_client.get(
        f"/api/activity/backup/{backup.id}/logs", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["lines"][0]["content"] == line
    response = test_client.get(
        f"/api/backup/logs/{backup.id}/stream", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["lines"][0]["content"] == line
