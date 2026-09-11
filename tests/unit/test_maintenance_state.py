from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.maintenance_state import (
    apply_compact_completion,
    apply_compact_stats,
)


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


@pytest.mark.unit
def test_apply_compact_completion_persists_stats_and_fills_an_unmeasured_size():
    """`borg compact --stats` output lands on the job; where nothing has
    measured the repository, it also fills total_size (#931)."""
    job = SimpleNamespace(
        status="running",
        progress=0,
        progress_message=None,
        error_message=None,
        completed_at=None,
        stats=None,
    )
    repo = SimpleNamespace(last_compact=None, total_size=None, total_size_source=None)
    stats = {"repository_size": 502_000, "object_count": 6, "size_precision": "exact"}

    assert apply_compact_completion(job, repo, 0, stats=stats) is True

    assert job.stats == stats
    assert repo.total_size == "490.23 KB"
    assert repo.total_size_bytes == 502_000
    assert repo.total_size_measured_at is not None
    # value and provenance move together: the label names pack file bytes
    assert repo.total_size_source == "compact_stats"

    # An emptied repository measures 0 and replaces the older compact figure.
    apply_compact_completion(
        job, repo, 0, stats={"repository_size": 0, "size_precision": "exact"}
    )
    assert repo.total_size == "0.00 B"
    assert repo.total_size_source == "compact_stats"

    # the warning completion path writes them too
    repo = SimpleNamespace(last_compact=None, total_size=None, total_size_source=None)
    apply_compact_completion(job, repo, 100, stats=stats)
    assert job.status == "completed_with_warnings"
    assert repo.total_size == "490.23 KB"
    assert repo.total_size_source == "compact_stats"


@pytest.mark.unit
def test_apply_compact_completion_keeps_size_without_stats_or_on_failure():
    job = SimpleNamespace(
        status="running",
        progress=0,
        progress_message=None,
        error_message=None,
        completed_at=None,
        stats="untouched",
    )
    repo = SimpleNamespace(
        last_compact=None, total_size="keep", total_size_source="storage_used"
    )

    assert apply_compact_completion(job, repo, 0, stats=None) is False
    assert job.stats == "untouched" and repo.total_size == "keep"
    assert repo.total_size_source == "storage_used"

    assert apply_compact_completion(job, repo, 2, stats={"repository_size": 1}) is False
    assert job.stats == "untouched" and repo.total_size == "keep"
    assert repo.total_size_source == "storage_used"


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    ["borg2_index", "borg1_cache_stats", None],
    ids=["index", "borg1-cache", "unlabelled"],
)
def test_apply_compact_stats_keeps_a_measured_size(source):
    """Measurement first (#934): the statistics land on the job, a size the
    index sum or the cache statistics wrote stays, as does one that
    predates the source label. The stats follow-up measures again after
    every compact."""
    job = SimpleNamespace(stats=None)
    repo = SimpleNamespace(total_size="7.00 GB", total_size_source=source)
    stats = {"repository_size": 5, "size_precision": "exact"}

    assert apply_compact_stats(job, repo, stats) is False

    assert job.stats == stats
    assert repo.total_size == "7.00 GB"
    assert repo.total_size_source == source


@pytest.mark.unit
def test_apply_compact_stats_replaces_a_store_walk_and_an_older_compact():
    """A store walk counts store file bytes and an older compact is older:
    an exact compact figure is the better of the two."""
    job = SimpleNamespace(stats=None)
    for source in ("storage_used", "compact_stats"):
        repo = SimpleNamespace(total_size="old", total_size_source=source)
        assert (
            apply_compact_stats(
                job, repo, {"repository_size": 5, "size_precision": "exact"}
            )
            is True
        )
        assert repo.total_size == "5.00 B"
        assert repo.total_size_source == "compact_stats"


@pytest.mark.unit
def test_apply_compact_stats_rounded_figure_replaces_only_an_older_compact():
    """A compact that ran without BORG_UNITS=raw printed rounded sizes: the
    statistics land on the job; the size replaces nothing measured, not
    even a store walk, only no size or an older compact's figure."""
    job = SimpleNamespace(stats=None)
    rounded = {
        "repository_size": 1_000_000,
        "size_precision": "rounded_to_printed_unit",
    }

    for source in ("borg2_index", "storage_used", None):
        repo = SimpleNamespace(total_size="1.43 MB", total_size_source=source)
        apply_compact_stats(job, repo, rounded)
        assert job.stats["repository_size"] == 1_000_000
        assert repo.total_size == "1.43 MB"
        assert repo.total_size_source == source

    # a measured source with no size yet is a measurement too
    repo = SimpleNamespace(total_size=None, total_size_source="borg2_index")
    apply_compact_stats(job, repo, {"repository_size": 5, "size_precision": "exact"})
    assert repo.total_size is None
    assert repo.total_size_source == "borg2_index"

    # an unlabelled figure is not trusted either
    repo = SimpleNamespace(total_size="5.00 GB", total_size_source="storage_used")
    apply_compact_stats(job, repo, {"repository_size": 1_000_000})
    assert repo.total_size == "5.00 GB"

    for total_size, source in ((None, None), ("old", "compact_stats")):
        repo = SimpleNamespace(total_size=total_size, total_size_source=source)
        apply_compact_stats(job, repo, rounded)
        assert repo.total_size == "976.56 KB"
        assert repo.total_size_source == "compact_stats"
