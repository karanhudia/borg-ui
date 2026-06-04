from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.maintenance_state import apply_compact_completion


@pytest.mark.unit
def test_apply_compact_completion_marks_success_and_updates_repository():
    now = datetime(2026, 4, 16, 10, 0, 0)
    job = SimpleNamespace(
        status="running",
        progress=10,
        progress_message=None,
        error_message=None,
        completed_at=None,
    )
    repo = SimpleNamespace(last_compact=None)

    apply_compact_completion(job, repo, 0, now=now)

    assert job.status == "completed"
    assert job.progress == 100
    assert job.progress_message == "Compact completed successfully"
    assert job.error_message is None
    assert job.completed_at == now
    assert repo.last_compact == now


@pytest.mark.unit
def test_apply_compact_completion_marks_warnings_and_updates_repository():
    now = datetime(2026, 4, 16, 10, 0, 0)
    job = SimpleNamespace(
        status="running",
        progress=10,
        progress_message=None,
        error_message=None,
        completed_at=None,
    )
    repo = SimpleNamespace(last_compact=None)

    apply_compact_completion(job, repo, 100, now=now)

    assert job.status == "completed_with_warnings"
    assert job.progress == 100
    assert "warnings" in job.progress_message
    assert job.error_message == job.progress_message
    assert job.completed_at == now
    assert repo.last_compact == now


@pytest.mark.unit
def test_apply_compact_completion_marks_failure_without_repository_update():
    now = datetime(2026, 4, 16, 10, 0, 0)
    previous_compact = datetime(2026, 4, 15, 10, 0, 0)
    job = SimpleNamespace(
        status="running",
        progress=10,
        progress_message=None,
        error_message=None,
        completed_at=None,
    )
    repo = SimpleNamespace(last_compact=previous_compact)

    apply_compact_completion(job, repo, 2, now=now)

    assert job.status == "failed"
    assert job.error_message == "Compact failed with exit code 2"
    assert job.completed_at == now
    assert repo.last_compact == previous_compact
