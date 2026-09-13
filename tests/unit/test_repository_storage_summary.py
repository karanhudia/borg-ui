"""The one storage payload every size reader takes (#981)."""

from datetime import datetime, timedelta

import pytest

from app.database.models import Archive, Operation, Repository
from app.services.operations.repository_status import storage_summaries


def _repo(test_db, name, *, borg_version, **fields):
    repo = Repository(
        name=name, path=f"/repos/{name}", borg_version=borg_version, **fields
    )
    test_db.add(repo)
    test_db.commit()
    return repo


# One listing stamps every row it sees with the same instant; the rows of
# a test repository are "current" together unless a test says otherwise.
SEEN_AT = datetime(2026, 9, 2, 0, 0, 0)


def _archive(test_db, repo, name, start, **fields):
    archive = Archive(
        repository_id=repo.id,
        borg_id=f"id-{name}",
        name=name,
        series="series",
        start=start,
        first_seen_at=SEEN_AT,
        last_seen_at=fields.pop("last_seen_at", SEEN_AT),
        **fields,
    )
    test_db.add(archive)
    test_db.commit()
    return archive


def _compact(test_db, repo, completed_at, *, status="completed", stats=None, note=None):
    op = Operation(
        repository_id=repo.id,
        kind="compact",
        category="maintenance",
        status=status,
        trigger="manual",
        priority=10,
        run_id=f"run-{repo.id}-{completed_at.isoformat()}",
        completed_at=completed_at,
        result=(
            {"stats": stats}
            if stats is not None
            else ({"note": note} if note is not None else None)
        ),
    )
    test_db.add(op)
    test_db.commit()
    return op


def _archive_sync(test_db, repo, completed_at, *, status="completed"):
    op = Operation(
        repository_id=repo.id,
        kind="archive_sync",
        category="index",
        status=status,
        trigger="scheduled",
        priority=10,
        run_id=f"sync-{repo.id}-{completed_at.isoformat()}",
        completed_at=completed_at,
    )
    test_db.add(op)
    test_db.commit()
    return op


@pytest.mark.unit
def test_borg1_summary_reads_the_cache_size_and_the_archive_sums(test_db):
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(
        test_db,
        "b1",
        borg_version=1,
        total_size="2.40 TB",
        total_size_bytes=2_400_000_000_000,
        total_size_source="borg1_cache_stats",
        total_size_measured_at=at,
        borg_last_modified=at - timedelta(hours=1),
        archive_count=2,
    )
    _archive(
        test_db,
        repo,
        "a1",
        at - timedelta(days=1),
        original_size=100,
        compressed_size=80,
        deduplicated_size=10,
        nfiles=5,
    )
    _archive(
        test_db,
        repo,
        "a2",
        at,
        original_size=200,
        compressed_size=150,
        deduplicated_size=20,
        nfiles=7,
    )

    summary = storage_summaries(test_db, [repo])[repo.id]

    assert summary.size_bytes == 2_400_000_000_000
    assert summary.size_source == "borg1_cache_stats"
    assert summary.measured_at == at
    assert summary.last_modified == at - timedelta(hours=1)
    assert summary.original_size == 300
    assert summary.compressed_size == 230
    # Borg 1's stored size is its deduplicated size
    assert summary.deduplicated_size == 2_400_000_000_000
    assert summary.latest_archive_files == 7  # the newest archive
    assert summary.compact is None and summary.compact_at is None


@pytest.mark.unit
def test_borg2_summary_takes_the_newest_successful_compact_statistics(test_db):
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(
        test_db,
        "b2",
        borg_version=2,
        total_size_bytes=2_350_000_000,
        total_size_source="borg2_index",
        archive_count=1,
    )
    _archive(test_db, repo, "a1", at, original_size=500, nfiles=922)
    old_stats = {"repository_size": 1, "deduplicated_size": 1}
    new_stats = {
        "repository_size": 2_350_000_000,
        "deduplicated_size": 2_300_000_000,
        "source_size": 10_830_000_000,
        "compression_factor": 1.5,
    }
    _compact(test_db, repo, at - timedelta(days=2), stats=old_stats)
    _compact(test_db, repo, at - timedelta(days=1), stats=new_stats)
    _compact(test_db, repo, at, status="failed", stats={"repository_size": 9})
    _compact(test_db, repo, at + timedelta(hours=1))  # newest, but no statistics

    summary = storage_summaries(test_db, [repo])[repo.id]

    assert summary.compact == new_stats
    assert summary.compact_at == at - timedelta(days=1)
    assert summary.deduplicated_size == 2_300_000_000
    assert summary.compressed_size is None  # Borg 2 does not report it
    assert summary.original_size == 500
    assert summary.latest_archive_files == 922


@pytest.mark.unit
def test_archive_sums_wait_until_every_archive_carries_its_info(test_db):
    """A listing creates archive rows without sizes; `fill_archive_info`
    fills a few per run. A sum over the filled ones would read as a total,
    so the sums are reported only once every archive has its info."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "partial", borg_version=1, archive_count=2)
    _archive(
        test_db,
        repo,
        "filled",
        at - timedelta(days=1),
        original_size=100,
        compressed_size=90,
        nfiles=3,
    )
    newest = _archive(test_db, repo, "listed-only", at)  # no info yet

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size is None
    assert summary.compressed_size is None
    assert summary.latest_archive_files is None  # the newest archive has no info yet

    newest.original_size = 50
    newest.compressed_size = 40
    newest.nfiles = 9
    test_db.commit()
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 150
    assert summary.compressed_size == 130
    assert summary.latest_archive_files == 9


@pytest.mark.unit
def test_unmeasured_repository_reports_nothing_not_zero(test_db):
    repo = _repo(test_db, "fresh", borg_version=2)

    summary = storage_summaries(test_db, [repo])[repo.id]

    assert summary.size_bytes is None
    assert summary.size_source is None
    assert summary.measured_at is None
    # no rows against the count it was created with: no listing has run,
    # so there is nothing to sum, not a sum of 0
    assert summary.archives_consistent is False
    assert summary.original_size is None
    assert summary.deduplicated_size is None
    assert summary.latest_archive_files is None
    assert storage_summaries(test_db, []) == {}


@pytest.mark.unit
class TestStorageInResponses:
    def test_list_and_single_routes_carry_the_storage_object(
        self, test_client, test_db, admin_headers
    ):
        at = datetime(2026, 9, 1, 12, 0, 0)
        repo = _repo(
            test_db,
            "listed",
            borg_version=2,
            total_size="2.35 GB",
            total_size_bytes=2_350_000_000,
            total_size_source="borg2_index",
            total_size_measured_at=at,
        )
        _compact(test_db, repo, at, stats={"repository_size": 2_350_000_000})

        listed = test_client.get("/api/repositories/", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        rows = listed.json()["repositories"]
        row = next(r for r in rows if r["id"] == repo.id)
        assert row["total_size"] == "2.35 GB"
        assert row["storage"]["size_bytes"] == 2_350_000_000
        assert row["storage"]["size_source"] == "borg2_index"
        assert row["storage"]["measured_at"] is not None
        # the polled list carries the stored columns only
        assert row["storage"]["archives_consistent"] is None
        assert row["storage"]["compact"] is None

        single = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
        assert single.status_code == 200, single.text
        storage = single.json()["repository"]["storage"]
        assert storage["size_bytes"] == 2_350_000_000
        assert storage["compact"] == {"repository_size": 2_350_000_000}
        assert storage["compact_at"] is not None
        assert storage["compressed_size"] is None

    def test_storage_failure_does_not_take_the_detail_down(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """The detail route runs the archive queries; a failure there logs
        and leaves `storage` null. (The list reads stored columns only and
        runs no query of its own.)"""
        repo = _repo(test_db, "still-served", borg_version=1)
        import app.api.repositories as repositories_api

        from sqlalchemy import text

        def boom(db, repositories, *, archives=True):
            # a real statement failure, so the session is in the state the
            # handler's rollback exists for
            db.execute(text("SELECT nothing FROM no_such_table"))

        monkeypatch.setattr(repositories_api, "storage_summaries", boom)
        single = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
        assert single.status_code == 200, single.text
        assert single.json()["repository"]["storage"] is None


@pytest.mark.unit
def test_sums_leave_out_archives_the_newest_listing_no_longer_saw(test_db):
    """A prune drops archives; the next listing stamps the rows it still
    sees and leaves the removed ones for `history_merge`. Until then those
    rows are not part of the sums, as they are not part of `archive_count`."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "pruned", borg_version=1, archive_count=1)
    kept = _archive(
        test_db, repo, "kept", at, original_size=100, compressed_size=80, nfiles=4
    )
    _archive(
        test_db,
        repo,
        "removed",
        at + timedelta(hours=1),
        original_size=900,
        compressed_size=700,
        nfiles=99,
    )
    # the listing after the prune saw only `kept`
    kept.last_seen_at = SEEN_AT + timedelta(days=1)
    test_db.commit()

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 100
    assert summary.compressed_size == 80
    assert summary.latest_archive_files == 4


@pytest.mark.unit
def test_compressed_sum_needs_every_archive_to_carry_it(test_db):
    """Borg 1 fills `compressed_size` next to `original_size`; a payload
    that carried one without the other leaves the compressed sum unreported
    rather than short."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "half", borg_version=1, archive_count=2)
    _archive(test_db, repo, "a1", at, original_size=100, compressed_size=80, nfiles=1)
    _archive(test_db, repo, "a2", at + timedelta(hours=1), original_size=50, nfiles=1)

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 150
    assert summary.compressed_size is None


@pytest.mark.unit
def test_summaries_group_by_repository(test_db):
    """One page, several repositories: each summary carries its own rows
    and its own newest compact."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    one = _repo(test_db, "one", borg_version=2, archive_count=1)
    two = _repo(test_db, "two", borg_version=2, archive_count=2)
    _archive(test_db, one, "o1", at, original_size=10, nfiles=1)
    _archive(test_db, two, "t1", at, original_size=20, nfiles=2)
    _archive(test_db, two, "t2", at + timedelta(hours=1), original_size=30, nfiles=3)
    _compact(test_db, one, at, stats={"repository_size": 1})
    _compact(test_db, two, at, stats={"repository_size": 2})

    summaries = storage_summaries(test_db, [one, two])
    assert summaries[one.id].original_size == 10
    assert summaries[one.id].latest_archive_files == 1
    assert summaries[one.id].compact == {"repository_size": 1}
    assert summaries[two.id].original_size == 50
    assert summaries[two.id].latest_archive_files == 3
    assert summaries[two.id].compact == {"repository_size": 2}


@pytest.mark.unit
def test_archive_figures_are_withheld_when_the_rows_do_not_match_the_count(test_db):
    """A listing that found nothing stamps nothing, so the rows it reported
    removed still look current; `archive_count` says 0. The archive figures
    are not reported until the rows and the count agree again."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "wiped", borg_version=1, archive_count=0)
    _archive(test_db, repo, "gone", at, original_size=100, compressed_size=80, nfiles=4)

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.archives_consistent is False
    assert summary.original_size is None
    assert summary.compressed_size is None
    assert summary.latest_archive_files is None

    repo.archive_count = 1
    test_db.commit()
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.archives_consistent is True
    assert summary.original_size == 100
    assert summary.latest_archive_files == 4


@pytest.mark.unit
def test_files_come_from_a_current_archive_only(test_db):
    """Two archives started in the same second; the newer row was pruned
    and waits for `history_merge`: the file count is the surviving one's."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "same-second", borg_version=1, archive_count=1)
    _archive(
        test_db,
        repo,
        "kept",
        at,
        original_size=1,
        compressed_size=1,
        nfiles=4,
        last_seen_at=SEEN_AT + timedelta(days=1),
    )
    _archive(test_db, repo, "pruned", at, original_size=1, compressed_size=1, nfiles=99)

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.latest_archive_files == 4


@pytest.mark.unit
def test_files_are_withheld_while_the_newest_archive_has_no_info(test_db):
    """Two current archives tied on start; the newest (highest id) is not
    filled yet: no older archive's count stands in for it."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "tied", borg_version=1, archive_count=2)
    _archive(test_db, repo, "older", at, original_size=1, compressed_size=1, nfiles=4)
    _archive(test_db, repo, "newest", at)  # listed, not filled

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.latest_archive_files is None


@pytest.mark.unit
def test_the_list_reads_the_stored_columns_only(test_db):
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "listed", borg_version=2, total_size_bytes=5, archive_count=1)
    _archive(test_db, repo, "a1", at, original_size=100, nfiles=3)
    _compact(test_db, repo, at, stats={"repository_size": 5})

    light = storage_summaries(test_db, [repo], archives=False)[repo.id]
    assert light.size_bytes == 5
    assert light.archives_consistent is None  # not computed, not withheld
    assert (
        light.original_size is None
        and light.latest_archive_files is None
        and light.compact is None
    )
    full = storage_summaries(test_db, [repo])[repo.id]
    assert full.original_size == 100 and full.latest_archive_files == 3
    assert full.compact == {"repository_size": 5}


@pytest.mark.unit
def test_compacts_without_statistics_do_not_hide_the_newest_figure(test_db):
    """An agent that predates the report runs compacts without statistics;
    however many of them land, the newest figure that exists is served."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "lookback", borg_version=2)
    _compact(test_db, repo, at - timedelta(days=9), stats={"repository_size": 3})
    for days in range(8):
        _compact(test_db, repo, at - timedelta(days=days))  # no statistics

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.compact == {"repository_size": 3}
    assert summary.compact_at == at - timedelta(days=9)


@pytest.mark.unit
def test_only_the_newest_few_compacts_that_mention_statistics_are_read(test_db):
    """The rows are filtered in SQL on the text of the serialized result,
    so one that mentions the key without carrying a usable dict still
    ranks; the window is what keeps a few of those from hiding the
    figure, and what bounds the rows read per repository."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "window", borg_version=2)
    _compact(test_db, repo, at - timedelta(days=4), stats={"repository_size": 7})
    for days in (3, 2):
        _compact(test_db, repo, at - timedelta(days=days), stats=None, note="stats")

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.compact == {"repository_size": 7}

    # a third such row fills the window and the figure drops out
    _compact(test_db, repo, at - timedelta(days=1), stats=None, note="stats")
    assert storage_summaries(test_db, [repo])[repo.id].compact is None


@pytest.mark.unit
def test_an_emptied_repository_measures_zero_not_nothing(test_db):
    """Every archive pruned and the rows dropped: once a listing has run,
    zero rows against a count of 0 are a measurement, unlike the same
    state of a repository whose listing never ran (a fresh import, or one
    whose index mode runs no listing)."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "emptied", borg_version=1, archive_count=0)
    _archive_sync(test_db, repo, at, status="failed")
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.archives_consistent is False
    assert summary.original_size is None

    _archive_sync(test_db, repo, at + timedelta(hours=1))
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.archives_consistent is True
    assert summary.original_size == 0
    assert summary.compressed_size == 0
    assert summary.latest_archive_files is None


@pytest.mark.unit
def test_borg1_deduplicated_size_needs_the_cache_source(test_db):
    """A Borg 1 size from a store walk is not a deduplicated size."""
    repo = _repo(
        test_db,
        "walked",
        borg_version=1,
        total_size_bytes=4096,
        total_size_source="storage_used",
    )
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.size_bytes == 4096
    assert summary.deduplicated_size is None


@pytest.mark.unit
def test_a_row_before_the_column_still_reports_its_size(test_db):
    """A row the backfill did not reach (an unparseable string then, a real
    one now) is read through the same rule as the dashboard and the
    gauges: the string parsed back, with no `measured_at`."""
    repo = _repo(
        test_db,
        "legacy",
        borg_version=1,
        total_size="1.00 KB",
        total_size_source="borg1_cache_stats",
    )
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.size_bytes == 1024
    assert summary.deduplicated_size == 1024  # the same figure, by the same rule
    assert summary.measured_at is None


@pytest.mark.unit
def test_route_carries_the_consistency_flag(test_client, test_db, admin_headers):
    repo = _repo(test_db, "flagged", borg_version=1, archive_count=2)
    _archive(test_db, repo, "only", datetime(2026, 9, 1), original_size=1, nfiles=1)
    single = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
    assert single.status_code == 200, single.text
    storage = single.json()["repository"]["storage"]
    assert storage["archives_consistent"] is False
    assert storage["original_size"] is None
