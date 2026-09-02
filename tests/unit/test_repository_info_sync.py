"""The info dialog's archive list must reach the repository row.

The real sequence this guards (observed live): stats refresh writes
archive_count=1, a backup finishes two minutes later, the info click then shows
two archives in the dialog while the card still says one — because the info
routes fetched the authoritative list and threw it away.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services.repository_info_sync import (
    _newest_archive_time,
    sync_archive_stats_from_info,
)


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeRepo:
    def __init__(self, borg_version, archive_count=1, last_backup=None):
        self.name = "repo"
        self.borg_version = borg_version
        self.archive_count = archive_count
        self.last_backup = last_backup


@pytest.mark.unit
def test_borg2_count_and_newest_time_are_written():
    """The timestamps are verbatim from the live case — offset-carrying ISO
    strings; the column stores naive UTC."""
    repo = FakeRepo(borg_version=2, archive_count=1)
    db = FakeDb()
    info = {
        "archives": [
            {"name": "k8s-borg", "start": "2026-08-19T20:03:15.388152+02:00"},
            {"name": "k8s-borg", "start": "2026-08-19T21:03:18.624537+02:00"},
        ]
    }

    sync_archive_stats_from_info(repo, info, db)

    assert repo.archive_count == 2
    assert repo.last_backup == datetime(2026, 8, 19, 19, 3, 18, 624537)
    assert db.commits == 1


@pytest.mark.unit
def test_borg1_is_never_touched():
    """Borg 1's repository-level info carries no archive list; the parsed shape
    yields [] even for a populated repository. Writing that back would wipe a
    real count to 0."""
    repo = FakeRepo(borg_version=1, archive_count=5)
    db = FakeDb()

    sync_archive_stats_from_info(repo, {"archives": []}, db)

    assert repo.archive_count == 5
    assert db.commits == 0


@pytest.mark.unit
def test_an_empty_borg2_repository_writes_zero_and_clears_last_backup():
    """Zero archives with a stale newest-backup time would contradict itself
    on the card — an empty listing clears both columns."""
    repo = FakeRepo(borg_version=2, archive_count=3, last_backup=datetime(2026, 8, 1))
    db = FakeDb()

    sync_archive_stats_from_info(repo, {"archives": []}, db)

    assert repo.archive_count == 0
    assert repo.last_backup is None
    assert db.commits == 1


@pytest.mark.unit
@pytest.mark.parametrize("info", [{}, {"archives": None}, {"archives": "raw"}])
def test_a_response_without_a_list_is_ignored(info):
    repo = FakeRepo(borg_version=2, archive_count=4)
    db = FakeDb()

    sync_archive_stats_from_info(repo, info, db)

    assert repo.archive_count == 4
    assert db.commits == 0


@pytest.mark.unit
def test_unparsable_times_still_update_the_count_and_keep_last_backup():
    """Archives exist, only their times are unreadable — that is no evidence
    the known last_backup is wrong, so it stays."""
    repo = FakeRepo(borg_version=2, archive_count=0, last_backup=datetime(2026, 8, 1))
    db = FakeDb()
    info = {"archives": [{"name": "a", "time": "not-a-date"}, {"name": "b"}]}

    sync_archive_stats_from_info(repo, info, db)

    assert repo.archive_count == 2
    assert repo.last_backup == datetime(2026, 8, 1)


@pytest.mark.unit
def test_a_failing_commit_is_swallowed_and_rolled_back():
    """The info response has already been served — a stats write must never
    turn it into a 500."""

    class FailingDb(FakeDb):
        def commit(self):
            raise RuntimeError("database is locked")

    repo = FakeRepo(borg_version=2)
    db = FailingDb()

    sync_archive_stats_from_info(repo, {"archives": []}, db)

    assert db.rollbacks == 1


@pytest.mark.unit
def test_a_failing_rollback_is_swallowed_too():
    """A session broken enough that even rollback() raises must still not
    escape the helper — the never-raise contract has no exceptions."""

    class BrokenDb(FakeDb):
        def commit(self):
            raise RuntimeError("database is locked")

        def rollback(self):
            super().rollback()
            raise RuntimeError("connection is closed")

    repo = FakeRepo(borg_version=2)
    db = BrokenDb()

    sync_archive_stats_from_info(repo, {"archives": []}, db)

    assert db.rollbacks == 1


@pytest.mark.unit
def test_the_warning_logs_do_not_read_orm_attributes_after_rollback():
    """A rollback expires ORM attributes, so on a broken session even
    repository.name can hit the database and raise when read afterwards — the
    warning logs must use the name captured up front."""

    class ExpiringRepo(FakeRepo):
        expired = False

        def __getattribute__(self, item):
            if item == "name" and object.__getattribute__(self, "expired"):
                raise RuntimeError("attribute refresh on a broken session")
            return object.__getattribute__(self, item)

    class FailingDb(FakeDb):
        def __init__(self, repo):
            super().__init__()
            self._repo = repo

        def commit(self):
            raise RuntimeError("database is locked")

        def rollback(self):
            super().rollback()
            self._repo.expired = True

    repo = ExpiringRepo(borg_version=2)
    db = FailingDb(repo)

    sync_archive_stats_from_info(repo, {"archives": []}, db)

    assert db.rollbacks == 1


@pytest.mark.unit
def test_naive_times_resolve_through_the_given_zone():
    """Borg emits naive local wall clock; the agent's reported zone converts
    it - assuming UTC pushed last_backup into the future on non-UTC agents."""
    newest = _newest_archive_time(
        [{"name": "a1", "time": "2026-09-02T12:45:14"}],
        timezone_name="Europe/Berlin",
    )

    assert newest == datetime(2026, 9, 2, 10, 45, 14)


@pytest.mark.unit
def test_numeric_epoch_times_go_through_the_shared_parser():
    newest = _newest_archive_time([{"name": "a1", "time": 1788345914}])

    assert newest == datetime(2026, 9, 2, 10, 45, 14)


@pytest.mark.unit
def test_the_zero_epoch_is_a_valid_time_and_wins_over_start():
    newest = _newest_archive_time(
        [{"name": "a1", "time": 0, "start": "2026-09-02T12:45:14+00:00"}]
    )

    assert newest == datetime(1970, 1, 1, 0, 0, 0)
