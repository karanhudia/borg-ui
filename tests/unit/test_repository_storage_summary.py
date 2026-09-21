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


def _stats(test_db, repo, completed_at, *, status="completed", result=None):
    op = Operation(
        repository_id=repo.id,
        kind="stats",
        category="index",
        status=status,
        trigger="scheduled",
        priority=10,
        run_id=f"stats-{repo.id}-{completed_at.isoformat()}",
        completed_at=completed_at,
        result=result,
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
    assert summary.first_backup_at == at - timedelta(days=1)
    assert summary.last_backup_at == at
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
    # every row carries its info, so the rows answer for the current set
    assert summary.original_size == 500
    assert summary.original_size_source == "archives"
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
    # the span needs no per-archive info, only consistent rows
    assert summary.first_backup_at is not None and summary.last_backup_at is not None

    newest.original_size = 50
    newest.compressed_size = 40
    newest.nfiles = 9
    test_db.commit()
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 150
    assert summary.compressed_size == 130
    assert summary.latest_archive_files == 9


@pytest.mark.unit
def test_borg1_original_size_comes_from_the_newest_stats_operation(test_db):
    """`borg info` reports the repository's source data size in one call;
    an archive row still waiting for its info does not blank the figure."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b1-repo-level", borg_version=1, archive_count=2)
    _archive(test_db, repo, "filled", at - timedelta(days=1), original_size=100)
    _archive(test_db, repo, "listed-only", at)  # no info yet
    _stats(test_db, repo, at - timedelta(hours=2), result={"original_size": 140})
    _stats(test_db, repo, at - timedelta(hours=1), result={"original_size": 150})
    _stats(test_db, repo, at, status="failed", result={"original_size": 9})

    summary = storage_summaries(test_db, [repo])[repo.id]

    assert summary.original_size == 150
    assert summary.original_size_source == "borg1_cache_stats"
    # the per-archive figures keep their own rules
    assert summary.latest_archive_files is None
    assert summary.compressed_size is None


@pytest.mark.unit
def test_borg1_original_size_falls_back_to_the_complete_archive_sum(test_db):
    """No `stats` operation has reported the figure (an older release's
    rows): the sum over the archive rows serves, under its gate."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b1-fallback", borg_version=1, archive_count=2)
    _archive(test_db, repo, "a1", at - timedelta(days=1), original_size=100)
    newest = _archive(test_db, repo, "a2", at)
    _stats(test_db, repo, at, result={"bytes": 2048, "source": "borg1_cache_stats"})

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size is None
    assert summary.original_size_source is None

    newest.original_size = 50
    test_db.commit()
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 150
    assert summary.original_size_source == "archives"


@pytest.mark.unit
def test_stats_operations_without_the_figure_do_not_hide_the_newest_one(test_db):
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b1-lookback", borg_version=1)
    _stats(test_db, repo, at - timedelta(days=9), result={"original_size": 0})
    for days in range(8):
        _stats(test_db, repo, at - timedelta(days=days), result={"bytes": 1})

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 0  # a measurement, not "nothing"
    assert summary.original_size_source == "borg1_cache_stats"


@pytest.mark.unit
def test_an_unusable_original_size_in_a_stats_result_is_not_a_figure(test_db):
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b1-unusable", borg_version=1)
    for hours, value in enumerate((None, "150", True, -1)):
        _stats(
            test_db, repo, at + timedelta(hours=hours), result={"original_size": value}
        )
        assert storage_summaries(test_db, [repo])[repo.id].original_size is None


@pytest.mark.unit
def test_borg2_original_size_comes_from_the_compact_statistics(test_db):
    """Compact reports the source data size of every archive; the archive
    sum serves only while no compact has reported one."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b2-repo-level", borg_version=2, archive_count=2)
    _archive(test_db, repo, "filled", at - timedelta(days=1), original_size=100)
    newest = _archive(test_db, repo, "listed-only", at)

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size is None and summary.original_size_source is None

    _compact(test_db, repo, at, stats={"repository_size": 7})  # no source size
    newest.original_size = 50
    test_db.commit()
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 150
    assert summary.original_size_source == "archives"

    newest.original_size = None
    test_db.commit()
    _compact(
        test_db,
        repo,
        at + timedelta(hours=1),
        stats={"repository_size": 7, "source_size": 160},
    )
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 160
    assert summary.original_size_source == "compact_stats"
    # a Borg 1 figure filed for a Borg 2 repository is not read
    _stats(test_db, repo, at + timedelta(hours=2), result={"original_size": 1})
    assert storage_summaries(test_db, [repo])[repo.id].original_size == 160


@pytest.mark.unit
def test_a_compact_figure_gives_way_to_the_set_it_no_longer_describes(test_db):
    """An emptied repository measures 0, not the size of the archives it
    used to hold: its rows are complete (there are none) and a compact's
    figure describes a set that is gone."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b2-emptied", borg_version=2, archive_count=0)
    _compact(test_db, repo, at, stats={"source_size": 160, "archive_count": 2})
    _archive_sync(test_db, repo, at + timedelta(hours=1))

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 0
    assert summary.original_size_source == "archives"


@pytest.mark.unit
def test_a_compact_figure_stands_while_no_complete_sum_replaces_it(test_db):
    """The new archive's row has no info yet, so the rows cannot answer:
    a figure that lags one archive beats no figure at all, which is the
    whole point of reading one."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b2-newer-backup", borg_version=2, archive_count=2)
    _archive(test_db, repo, "a1", at - timedelta(days=1), original_size=100)
    _archive(test_db, repo, "a2", at)  # the new one, no info yet
    _compact(
        test_db,
        repo,
        at - timedelta(hours=1),
        stats={"source_size": 100, "archive_count": 1},
    )

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 100
    assert summary.original_size_source == "compact_stats"


@pytest.mark.unit
def test_complete_rows_outrank_a_figure_that_cannot_have_followed_them(test_db):
    """A compact reports what it analysed and does not move until the next
    one, so a complete set of rows is the newer answer and is taken. The
    same holds for a Borg 1 `stats` run that no longer describes the
    repository: the rows decide while they are complete."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    borg2 = _repo(test_db, "b2-rows-win", borg_version=2, archive_count=1)
    _archive(test_db, borg2, "a1", at, original_size=100)
    _compact(test_db, borg2, at, stats={"source_size": 160})

    summary = storage_summaries(test_db, [borg2])[borg2.id]
    assert summary.original_size == 100
    assert summary.original_size_source == "archives"

    borg1 = _repo(test_db, "b1-rows-win", borg_version=1, archive_count=1)
    _archive(test_db, borg1, "a1", at, original_size=100)
    _stats(test_db, borg1, at, result={"original_size": 160})

    summary = storage_summaries(test_db, [borg1])[borg1.id]
    assert summary.original_size == 100
    assert summary.original_size_source == "archives"


@pytest.mark.unit
def test_a_listed_repository_without_archives_measures_zero(test_db):
    """An archive count of 0 from a listing answers on its own: no
    archives, no source data. It must not wait for the rows, which the
    `archives` index mode never deletes (it runs no `history_merge`), or a
    compact's figure would outlive the archives it described for good."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(
        test_db, "b2-lingering", borg_version=2, archive_count=0, index_mode="archives"
    )
    _archive(test_db, repo, "gone-1", at - timedelta(days=1), original_size=100)
    _archive(test_db, repo, "gone-2", at, original_size=200)
    # the listing that found the repository empty ran after those rows
    # were last seen, and never deletes them in this mode
    _archive_sync(test_db, repo, SEEN_AT + timedelta(hours=1))
    _compact(test_db, repo, at, stats={"source_size": 300})

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 0
    assert summary.original_size_source == "archives"
    # the per-archive figures still wait: the rows and the count disagree
    assert summary.archives_consistent is False
    assert summary.latest_archive_files is None


@pytest.mark.unit
def test_the_figure_carries_the_time_of_the_run_that_reported_it(test_db):
    """`measured_at` is the size measurement's time, which moves whenever a
    size is written; the source data size can come from an older run (a
    repo-info that failed while a disk measurement succeeded), and a
    compact's figure is as old as that compact. Each carries its own
    time, so a reader cannot present it as newly measured."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    borg1 = _repo(test_db, "b1-stamped", borg_version=1, archive_count=2)
    _archive(test_db, borg1, "filled", at - timedelta(days=1), original_size=100)
    _archive(test_db, borg1, "listed-only", at)
    _stats(test_db, borg1, at - timedelta(days=2), result={"original_size": 150})
    _stats(test_db, borg1, at, result={"bytes": 4096})  # no figure of its own

    summary = storage_summaries(test_db, [borg1])[borg1.id]
    assert summary.original_size == 150
    assert summary.original_size_at == at - timedelta(days=2)

    borg2 = _repo(test_db, "b2-stamped", borg_version=2, archive_count=2)
    _archive(test_db, borg2, "filled", at - timedelta(days=1), original_size=100)
    _archive(test_db, borg2, "listed-only", at)
    _compact(test_db, borg2, at - timedelta(days=3), stats={"source_size": 160})

    summary = storage_summaries(test_db, [borg2])[borg2.id]
    assert summary.original_size == 160
    assert summary.original_size_at == at - timedelta(days=3)


@pytest.mark.unit
def test_a_figure_the_rows_answer_for_carries_no_time_of_its_own(test_db):
    """The rows are as new as the listing that wrote them, which the
    reader already knows; only a figure from elsewhere needs a stamp."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b1-rows-stamped", borg_version=1, archive_count=1)
    _archive(test_db, repo, "a1", at, original_size=100)
    _stats(test_db, repo, at, result={"original_size": 150})

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 100
    assert summary.original_size_source == "archives"
    assert summary.original_size_at is None


@pytest.mark.unit
def test_a_newer_compact_without_the_figure_does_not_hide_an_older_one(test_db):
    """The dialog shows the newest statistics a compact reported; the
    source data size is looked up on its own, so a later run that
    reported a repository size without one does not blank it."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b2-partial", borg_version=2, archive_count=2)
    _archive(test_db, repo, "filled", at - timedelta(days=1), original_size=100)
    _archive(test_db, repo, "listed-only", at)  # no info yet
    _compact(
        test_db,
        repo,
        at - timedelta(days=1),
        stats={"repository_size": 7, "source_size": 160},
    )
    _compact(test_db, repo, at, stats={"repository_size": 7})

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 160
    assert summary.original_size_source == "compact_stats"
    assert summary.original_size_at == at - timedelta(days=1)
    # the statistics on show stay the newest ones reported
    assert summary.compact == {"repository_size": 7}
    assert summary.compact_at == at


@pytest.mark.unit
def test_rows_a_listing_has_not_counted_yet_are_not_an_empty_repository(test_db):
    """`apply_listing` commits the rows, `fill_archive_info` runs, and only
    then is `archive_count` written: for the length of that fill a
    repository that just gained its first archives has rows and a count of
    0. That is not an emptied repository, and must not read as 0 B."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b1-arriving", borg_version=1, archive_count=0)
    _archive_sync(test_db, repo, at)  # the listing that found it empty
    # the sync under way stamped its rows after that; it has not completed
    _archive(
        test_db,
        repo,
        "first",
        at + timedelta(hours=1),
        original_size=100,
        last_seen_at=at + timedelta(hours=1),
    )
    _stats(test_db, repo, at + timedelta(hours=1), result={"original_size": 100})

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 100
    assert summary.original_size_source == "borg1_cache_stats"


@pytest.mark.unit
@pytest.mark.parametrize("leftover_row", [True, False])
def test_a_figure_newer_than_the_empty_listing_outweighs_the_count(
    test_db, leftover_row
):
    """`archive_count` is written by a listing and by nothing else, so an
    archive created outside Borg UI leaves it at 0 until the next one. A
    compact that ran after that listing and reported source data says the
    repository is not empty; the count is the older evidence.

    Both ways the rows can look: a row the `archives` mode never deleted,
    and none at all. Without rows the sum has nothing to add up, and zero
    rows all carrying their figure must not read as a measured 0."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(
        test_db,
        f"b2-external-{leftover_row}",
        borg_version=2,
        archive_count=0,
        index_mode="archives",
    )
    if leftover_row:
        _archive(test_db, repo, "gone", at, original_size=100)
    _archive_sync(test_db, repo, SEEN_AT + timedelta(hours=1))
    _compact(test_db, repo, SEEN_AT + timedelta(hours=2), stats={"source_size": 160})

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.original_size == 160
    assert summary.original_size_source == "compact_stats"


@pytest.mark.unit
def test_an_unwritten_archive_count_reads_as_zero_like_everywhere_else(test_db):
    """`archive_count` is nullable, and a row whose count was never
    written reads as 0 for the consistency check. The empty-repository
    answer has to read it the same way, or a listed repository with no
    rows reports nothing where it measured zero."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "b1-null-count", borg_version=1)
    # the column default fills an insert, so the NULL is written after it
    repo.archive_count = None
    test_db.commit()
    _archive_sync(test_db, repo, at)
    assert repo.archive_count is None

    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.archives_consistent is True
    assert summary.original_size == 0
    assert summary.original_size_source == "archives"


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
        assert row["storage"]["archives_listed"] is False
        assert row["storage"]["compact"] is None

        single = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
        assert single.status_code == 200, single.text
        storage = single.json()["repository"]["storage"]
        assert storage["size_bytes"] == 2_350_000_000
        assert storage["compact"] == {"repository_size": 2_350_000_000}
        assert storage["compact_at"] is not None
        assert storage["compressed_size"] is None

    def test_list_names_the_index_work_still_pending(
        self, test_client, test_db, admin_headers
    ):
        """After an import the chain (stats, archive_sync, history_index) is
        queued; the list names those kinds so the card says "indexing"
        instead of showing 0 archives and no size as final values (#1063).
        Finished and non-index work is not named."""
        fresh = _repo(test_db, "fresh-import", borg_version=2, archive_count=0)
        settled = _repo(test_db, "settled", borg_version=2, archive_count=3)
        for kind, status in (
            ("stats", "queued"),
            ("archive_sync", "running"),
            ("history_index", "queued"),
            ("compact", "queued"),
        ):
            test_db.add(
                Operation(
                    repository_id=fresh.id,
                    kind=kind,
                    category="maintenance" if kind == "compact" else "index",
                    status=status,
                    trigger="followup",
                    priority=10,
                    run_id=f"import-{fresh.id}-{kind}",
                )
            )
        test_db.add(
            Operation(
                repository_id=settled.id,
                kind="stats",
                category="index",
                status="completed",
                trigger="reconcile",
                priority=10,
                run_id=f"reconcile-{settled.id}",
                completed_at=datetime(2026, 9, 1, 12, 0, 0),
            )
        )
        # a routine reconcile listing waiting in the queue is named too: the
        # card keeps the settled repository's figures, since only a
        # placeholder is replaced by "indexing"; a manual resync carries the
        # same trigger and must show
        test_db.add(
            Operation(
                repository_id=settled.id,
                kind="archive_sync",
                category="index",
                status="queued",
                trigger="reconcile",
                priority=10,
                run_id=f"reconcile-{settled.id}-next",
            )
        )
        test_db.commit()

        listed = test_client.get("/api/repositories/", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        rows = {r["id"]: r for r in listed.json()["repositories"]}
        assert rows[fresh.id]["index_pending_kinds"] == [
            "archive_sync",
            "history_index",
            "stats",
        ]
        assert rows[settled.id]["index_pending_kinds"] == ["archive_sync"]

        # the detail carries the same kinds
        single = test_client.get(f"/api/repositories/{fresh.id}", headers=admin_headers)
        assert single.status_code == 200, single.text
        assert single.json()["repository"]["index_pending_kinds"] == [
            "archive_sync",
            "history_index",
            "stats",
        ]

    def test_storage_route_serves_the_stored_figures_without_borg(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """The header and the dialog read this route: the same summary the
        detail carries plus the pending index kinds, and no live Borg call,
        so it cannot race the dialog's `/info` for the repository lock."""
        import app.api.repositories as repositories_api

        repo = _repo(
            test_db,
            "stored-only",
            borg_version=1,
            archive_count=1,
            total_size_bytes=4096,
            total_size_source="borg1_cache_stats",
        )
        test_db.add(
            Operation(
                repository_id=repo.id,
                kind="stats",
                category="index",
                status="queued",
                trigger="manual",
                priority=10,
                run_id=f"manual-{repo.id}",
            )
        )
        test_db.commit()

        async def no_borg(*args, **kwargs):
            raise AssertionError("the storage route must not run borg")

        monkeypatch.setattr(repositories_api, "get_repository_stats", no_borg)

        response = test_client.get(
            f"/api/repositories/{repo.id}/storage", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["repository_id"] == repo.id
        assert body["storage"]["size_bytes"] == 4096
        assert body["storage"]["size_source"] == "borg1_cache_stats"
        assert body["index_pending_kinds"] == ["stats"]

        missing = test_client.get(
            "/api/repositories/999999/storage", headers=admin_headers
        )
        assert missing.status_code == 404

    def test_storage_route_needs_access_to_the_repository(
        self, test_client, test_db, admin_headers, auth_headers
    ):
        """The figures and the pending work of a repository are read with the
        viewer role on it, like the detail: a user without any permission on
        the repository is refused."""
        repo = _repo(test_db, "guarded", borg_version=1, archive_count=1)
        allowed = test_client.get(
            f"/api/repositories/{repo.id}/storage", headers=admin_headers
        )
        assert allowed.status_code == 200, allowed.text
        denied = test_client.get(
            f"/api/repositories/{repo.id}/storage", headers=auth_headers
        )
        assert denied.status_code == 403, denied.text

    def test_list_survives_a_failing_operations_query(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """The list's storage columns and pending kinds both read the
        operations table; when that fails the list still answers, without
        those fields, and the fallback does not run the failing query
        again."""
        import app.services.operations.repository_status as status_module

        from sqlalchemy import text

        repo = _repo(test_db, "listed-under-failure", borg_version=1, archive_count=1)

        def boom(db, repository_ids):
            db.execute(text("SELECT nothing FROM no_such_table"))

        monkeypatch.setattr(status_module, "_listed_repositories", boom)
        listed = test_client.get("/api/repositories/", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        row = next(r for r in listed.json()["repositories"] if r["id"] == repo.id)
        assert row["storage"] is None
        assert row["index_pending_kinds"] == []

    def test_list_keeps_the_sizes_when_the_pending_kinds_query_fails(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """Each decorative field has its own guard: the pending kinds failing
        after the sizes were read leaves the sizes on the cards."""
        import app.api.repositories as repositories_api

        from sqlalchemy import text

        repo = _repo(
            test_db,
            "sized-under-failure",
            borg_version=2,
            total_size="2.35 GB",
            total_size_bytes=2_523_456_789,
            total_size_source="borg2_index",
            archive_count=1,
        )

        def boom(db, repository_ids):
            db.execute(text("SELECT nothing FROM no_such_table"))

        monkeypatch.setattr(repositories_api, "index_pending_kinds", boom)
        listed = test_client.get("/api/repositories/", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        row = next(r for r in listed.json()["repositories"] if r["id"] == repo.id)
        assert row["storage"]["size_bytes"] == 2_523_456_789
        assert row["index_pending_kinds"] == []

    def test_storage_route_survives_a_failing_pending_kinds_query(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """The pending kinds are decorative: their query failing leaves the
        field empty and the route up, on the detail as well."""
        import app.api.repositories as repositories_api

        from sqlalchemy import text

        repo = _repo(test_db, "flaky", borg_version=1, archive_count=1)

        def boom(db, repository_ids):
            db.execute(text("SELECT nothing FROM no_such_table"))

        monkeypatch.setattr(repositories_api, "index_pending_kinds", boom)
        storage = test_client.get(
            f"/api/repositories/{repo.id}/storage", headers=admin_headers
        )
        assert storage.status_code == 200, storage.text
        assert storage.json()["index_pending_kinds"] == []
        detail = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["repository"]["index_pending_kinds"] == []

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
    assert summary.archives_listed is False
    assert summary.original_size is None

    _archive_sync(test_db, repo, at + timedelta(hours=1))
    summary = storage_summaries(test_db, [repo])[repo.id]
    assert summary.archives_consistent is True
    assert summary.archives_listed is True
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


@pytest.mark.unit
def test_route_carries_the_original_size_with_its_source(
    test_client, test_db, admin_headers
):
    """Rows and count disagree, so the archive figures are withheld; the
    repository-level figure does not depend on them. The list stays on the
    stored columns."""
    at = datetime(2026, 9, 1, 12, 0, 0)
    repo = _repo(test_db, "sourced", borg_version=1, archive_count=2)
    _archive(test_db, repo, "only", at, original_size=1, nfiles=1)
    _stats(test_db, repo, at, result={"original_size": 150})

    single = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
    assert single.status_code == 200, single.text
    storage = single.json()["repository"]["storage"]
    assert storage["archives_consistent"] is False
    assert storage["original_size"] == 150
    assert storage["original_size_source"] == "borg1_cache_stats"
    assert storage["latest_archive_files"] is None

    light = storage_summaries(test_db, [repo], archives=False)[repo.id]
    assert light.original_size is None and light.original_size_source is None
