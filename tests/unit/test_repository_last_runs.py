"""`last_runs` (spec 10.2): the repository card's `Last prune` and `Last
index` entries, computed once per page from the same evidence as the
status route."""

import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.database.models import (
    Base,
    Operation,
    Repository,
    SystemSettings,
    utc_now,
)
from app.services.operations import repository_status
from app.services.operations.repository_status import (
    last_runs,
    prune_removal_evidence,
)
from app.services.operations.vocab import category_for

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
)


def _repo(test_db, name="r"):
    repo = Repository(name=name, path=f"/tmp/{name}", encryption="none")
    test_db.add(repo)
    if test_db.query(SystemSettings).first() is None:
        test_db.add(SystemSettings())
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _op(
    test_db,
    repo,
    kind,
    completed_at,
    status="completed",
    result=None,
    params=None,
    started=True,
):
    op = Operation(
        repository_id=repo.id,
        kind=kind,
        category=category_for(kind),
        status=status,
        trigger="manual",
        priority=0,
        run_id="run",
        started_at=(completed_at - timedelta(minutes=1)) if started else None,
        completed_at=completed_at,
        result=result,
        params=params,
    )
    test_db.add(op)
    test_db.commit()
    return op


def _wipe(test_db, repo, *, status, started_at=None, completed_at=None):
    """A wipe operation with its details row, the shape phase 6 gave wipes."""
    from app.services.operations.details import wipe_details

    op = _op(test_db, repo, "wipe", completed_at, status=status, started=False)
    op.started_at = started_at
    wipe_details(test_db, op)
    test_db.commit()
    return op


@pytest.mark.unit
class TestLastRuns:
    def test_no_history_is_none_not_a_zero_date(self, test_db):
        repo = _repo(test_db)
        runs = last_runs(test_db, [repo])
        assert runs[repo.id].last_prune is None
        assert runs[repo.id].last_index is None

    def test_empty_page(self, test_db):
        assert last_runs(test_db, []) == {}

    def test_prune_newest_completion_wins(self, test_db):
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "prune", now - timedelta(days=5))
        _op(test_db, repo, "prune", now - timedelta(days=2))
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(days=2)
        _op(test_db, repo, "prune", now - timedelta(days=1))
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(days=1)

    def test_failed_runs_do_not_move_the_value(self, test_db):
        """As for `last_check` and `last_compact`: only a successful
        completion counts. The status route reports the failed attempt."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "prune", now - timedelta(days=5))
        _op(test_db, repo, "prune", now - timedelta(days=1), status="failed")
        _op(test_db, repo, "prune", now - timedelta(hours=1), status="cancelled")
        _op(test_db, repo, "archive_sync", now - timedelta(days=3))
        _op(test_db, repo, "stats", now - timedelta(hours=2), status="failed")
        runs = last_runs(test_db, [repo])
        assert runs[repo.id].last_prune == now - timedelta(days=5)
        assert runs[repo.id].last_index == now - timedelta(days=3)

    def test_prune_from_a_listing_that_saw_archives_disappear(self, test_db):
        """A repository pruned outside Borg UI: the newest successful
        `archive_sync` with removed archives is the evidence, unless a prune
        through Borg UI completed afterwards (same precedence as the
        status route's prune cell)."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "prune", now - timedelta(days=20))
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=2),
            result={"removed_archive_ids": [7]},
        )
        _op(test_db, repo, "archive_sync", now - timedelta(hours=1), result={})
        runs = last_runs(test_db, [repo])
        assert runs[repo.id].last_prune == now - timedelta(days=2)
        assert runs[repo.id].last_index == now - timedelta(hours=1)
        _op(test_db, repo, "prune", now - timedelta(hours=3))
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(
            hours=3
        )

    def test_index_is_the_newest_successful_operation_of_the_category(self, test_db):
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "archive_sync", now - timedelta(hours=5))
        _op(test_db, repo, "history_merge", now - timedelta(hours=4))
        _op(test_db, repo, "stats", now - timedelta(hours=3), status="skipped")
        _op(test_db, repo, "check", now - timedelta(hours=1))
        assert last_runs(test_db, [repo])[repo.id].last_index == now - timedelta(
            hours=4
        )

    def test_a_borg_ui_deletion_explains_the_removal(self, test_db):
        """An archive deleted from the Archives page disappears from the next
        listing like a pruned one; that listing must not read as a prune."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "prune", now - timedelta(days=20))
        _op(test_db, repo, "delete_archive", now - timedelta(days=2, hours=1))
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=2),
            result={"removed_archive_ids": [7]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(
            days=20
        )
        # a later listing with removals and no deletion since is a prune again
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=1),
            result={"removed_archive_ids": [8, 9]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(days=1)

    def test_a_later_deletion_does_not_reopen_an_explained_listing(self, test_db):
        """Archive A deleted at 10:00, its listing at 10:01 explained; archive
        B deleted at 11:00 with its listing still pending. The 10:01 listing
        stays explained: only deletions up to a listing are consulted."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "archive_sync", now - timedelta(hours=5))
        _op(test_db, repo, "delete_archive", now - timedelta(hours=2))
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=2, minutes=-1),
            result={"removed_archive_ids": [1]},
        )
        _op(test_db, repo, "delete_archive", now - timedelta(hours=1))
        assert last_runs(test_db, [repo])[repo.id].last_prune is None

    def test_a_wipe_explains_the_removal(self, test_db):
        """The listing that reports every archive gone after a wipe is not a
        prune."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "archive_sync", now - timedelta(days=2))
        _wipe(
            test_db,
            repo,
            status="completed",
            started_at=now - timedelta(days=1, hours=2),
            completed_at=now - timedelta(days=1, hours=1),
        )
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=1),
            result={"removed_archive_ids": [1, 2, 3]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune is None

    def test_a_cancelled_wipe_preview_explains_nothing(self, test_db):
        """cancel_preview stamps completed_at on a job that never started
        its delete phase; the cron prune's listing after it still counts."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _wipe(test_db, repo, status="cancelled", completed_at=now - timedelta(hours=2))
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=1),
            result={"removed_archive_ids": [1]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(
            hours=1
        )

    def test_a_queued_deletion_cancelled_before_its_turn_explains_nothing(
        self, test_db
    ):
        """A wipe or delete cancelled while still queued never ran; the
        listing after it is prune evidence as before."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(
            test_db,
            repo,
            "wipe",
            now - timedelta(hours=2),
            status="cancelled",
            started=False,
        )
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=1),
            result={"removed_archive_ids": [1]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(
            hours=1
        )

    def test_a_phase_6_wipe_operation_explains_the_removal(self, test_db):
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "wipe", now - timedelta(hours=2), status="failed")
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=1),
            result={"removed_archive_ids": [1, 2]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune is None

    def test_a_deletion_explains_the_first_listing_that_reports_removals(self, test_db):
        """A sync already in flight when the deletion ran listed the archive
        as present and reports nothing; the listing after it reports the
        removal and is the one explained."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "delete_archive", now - timedelta(minutes=30))
        _op(test_db, repo, "archive_sync", now - timedelta(minutes=29), result={})
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(minutes=10),
            result={"removed_archive_ids": [7]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune is None

    def test_a_reaped_delete_operation_explains_nothing(self, test_db):
        """The reaper stamps a never-queued delete failed with a completion
        but no start; it removed nothing."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(
            test_db,
            repo,
            "delete_archive",
            now - timedelta(hours=2),
            status="failed",
            started=False,
        )
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=1),
            result={"removed_archive_ids": [1]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(
            hours=1
        )

    def test_a_cancelled_deletion_still_explains_the_removal(self, test_db):
        """A delete cancelled after Borg dropped the manifest entry removed
        the archive all the same; the listing that reports it is no prune."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(
            test_db,
            repo,
            "delete_archive",
            now - timedelta(hours=2),
            status="cancelled",
        )
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=1),
            result={"removed_archive_ids": [1]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune is None

    def test_an_explained_page_turns_to_the_next(self, test_db, monkeypatch):
        """A cleanup pass longer than one page of listings: every candidate
        on the first page is explained, the cron prune before it still
        counts. With nothing older, the value is unknown; beyond the page
        cap it is unknown rather than searched for."""
        monkeypatch.setattr(repository_status, "REMOVAL_CANDIDATES", 2)
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=4),
            result={"removed_archive_ids": [1]},
        )
        # three explained listings: more than one page of two
        for day in (3, 2, 1):
            _op(test_db, repo, "delete_archive", now - timedelta(days=day, hours=1))
            _op(
                test_db,
                repo,
                "archive_sync",
                now - timedelta(days=day),
                result={"removed_archive_ids": [day]},
            )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(days=4)
        _op(test_db, repo, "delete_archive", now - timedelta(days=4, hours=1))
        assert last_runs(test_db, [repo])[repo.id].last_prune is None
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=5),
            result={"removed_archive_ids": [0]},
        )
        monkeypatch.setattr(repository_status, "REMOVAL_PAGES", 1)
        assert last_runs(test_db, [repo])[repo.id].last_prune is None

    def test_a_deletion_after_the_newest_listing_explains_nothing(self, test_db):
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=2),
            result={"removed_archive_ids": [1]},
        )
        _op(test_db, repo, "delete_archive", now - timedelta(hours=1))
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(
            hours=2
        )

    def test_removals_stay_with_their_repository(self, test_db):
        """Two repositories with removal listings: the previous-listing and
        deletion lookups are scoped per repository."""
        a, b = _repo(test_db, "a"), _repo(test_db, "b")
        now = utc_now().replace(tzinfo=None)
        # a: deletion inside its interval, explained
        _op(test_db, a, "archive_sync", now - timedelta(days=3))
        _op(test_db, a, "delete_archive", now - timedelta(days=2))
        _op(
            test_db,
            a,
            "archive_sync",
            now - timedelta(days=1),
            result={"removed_archive_ids": [1]},
        )
        # b: a's deletion falls inside b's interval, so an unscoped lookup
        # would explain b's listing too; b has no deletion of its own
        _op(test_db, b, "archive_sync", now - timedelta(days=3))
        _op(
            test_db,
            b,
            "archive_sync",
            now - timedelta(hours=1),
            result={"removed_archive_ids": [2]},
        )
        runs = last_runs(test_db, [a, b])
        assert runs[a.id].last_prune is None
        assert runs[b.id].last_prune == now - timedelta(hours=1)

    def test_a_dry_run_prune_is_not_a_prune(self, test_db):
        """The Prune dialog's preview is a completed `prune` operation with
        `params.dry_run`; it removed nothing and moves no value, nor does
        it hide older removal evidence."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=2),
            result={"removed_archive_ids": [1]},
        )
        _op(
            test_db,
            repo,
            "prune",
            now - timedelta(hours=1),
            params={"keep_daily": 7, "dry_run": True},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(days=2)
        _op(test_db, repo, "prune", now, params={"keep_daily": 7, "dry_run": False})
        assert last_runs(test_db, [repo])[repo.id].last_prune == now

    def test_one_deletion_keeps_the_older_removal_evidence(self, test_db):
        """A repository pruned nightly by cron; the operator deletes one
        archive in the UI. The listing that reports it is skipped, the
        night before still counts, the card does not flip to "Never"."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(days=1),
            result={"removed_archive_ids": [1]},
        )
        _op(test_db, repo, "delete_archive", now - timedelta(hours=2))
        _op(
            test_db,
            repo,
            "archive_sync",
            now - timedelta(hours=1),
            result={"removed_archive_ids": [2, 3]},
        )
        assert last_runs(test_db, [repo])[repo.id].last_prune == now - timedelta(days=1)

    def test_rows_stay_with_their_repository(self, test_db):
        """One grouped query per source; nothing leaks between repositories
        on the same page, and a repository outside the page is not read."""
        a, b, other = _repo(test_db, "a"), _repo(test_db, "b"), _repo(test_db, "c")
        now = utc_now().replace(tzinfo=None)
        _op(test_db, a, "prune", now - timedelta(days=1))
        _op(test_db, b, "prune", now - timedelta(days=3))
        _op(test_db, b, "stats", now - timedelta(hours=1))
        _op(test_db, other, "prune", now)
        _op(test_db, other, "archive_sync", now)
        runs = last_runs(test_db, [a, b])
        assert set(runs) == {a.id, b.id}
        assert runs[a.id].last_prune == now - timedelta(days=1)
        assert runs[a.id].last_index is None
        assert runs[b.id].last_prune == now - timedelta(days=3)
        assert runs[b.id].last_index == now - timedelta(hours=1)


@pytest.mark.unit
class TestRepositoriesListPayload:
    def test_list_omits_the_fields_when_they_cannot_be_computed(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """No entry rather than "Never": the card keys on the field being
        absent, and the rest of the list must still be served."""
        from app.api import repositories as repositories_api

        from sqlalchemy import text

        def boom(db, repositories):
            # a real failed statement, so the rollback path is the one taken
            db.execute(text("SELECT json_array_length('not json')"))

        monkeypatch.setattr(repositories_api, "last_runs", boom)
        repo = _repo(test_db)
        r = test_client.get("/api/repositories/", headers=admin_headers)
        assert r.status_code == 200
        item = {i["id"]: i for i in r.json()["repositories"]}[repo.id]
        assert "last_prune" not in item and "last_index" not in item
        assert item["name"] == repo.name

    def test_list_carries_last_prune_and_last_index(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        pruned = datetime(2026, 9, 1, 3, 0)
        indexed = datetime(2026, 9, 7, 4, 30)
        _op(test_db, repo, "prune", pruned)
        _op(test_db, repo, "archive_sync", indexed)
        empty = _repo(test_db, "empty")

        r = test_client.get("/api/repositories/", headers=admin_headers)

        assert r.status_code == 200
        by_id = {item["id"]: item for item in r.json()["repositories"]}
        assert by_id[repo.id]["last_prune"].startswith("2026-09-01T03:00:00")
        assert by_id[repo.id]["last_index"].startswith("2026-09-07T04:30:00")
        assert by_id[empty.id]["last_prune"] is None
        assert by_id[empty.id]["last_index"] is None


def _reset_postgres():
    """Like the sibling PostgreSQL suites: the shared CI database may be at
    any Alembic revision after a migration test, and `create_all` skips
    tables that exist, so start from an empty schema."""
    engine = create_engine(POSTGRES_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.mark.unit
@requires_postgres
class TestRemovalCriterionOnPostgres:
    """The JSON array length and the dry-run flag are spelled per dialect;
    SQLite is covered by the tests above, this one holds the PostgreSQL
    spelling."""

    def test_removal_and_dry_run_read_the_json_columns(self):
        _reset_postgres()
        engine = create_engine(POSTGRES_URL)
        Base.metadata.create_all(engine)
        db = Session(bind=engine)
        try:
            repo = _repo(db, "pg-removal")
            now = utc_now().replace(tzinfo=None)
            _op(
                db,
                repo,
                "archive_sync",
                now - timedelta(days=3),
                result={"removed_archive_ids": [1]},
            )
            _op(
                db,
                repo,
                "archive_sync",
                now - timedelta(days=2),
                result={"removed_archive_ids": []},
            )
            _op(db, repo, "archive_sync", now - timedelta(days=1), result=None)
            _op(
                db,
                repo,
                "archive_sync",
                now - timedelta(hours=12),
                result={"removed_archive_ids": "not a list"},
            )
            _op(
                db,
                repo,
                "archive_sync",
                now,
                result={"removed_archive_ids": [2]},
                status="failed",
            )
            _op(db, repo, "prune", now, params={"dry_run": True})
            assert prune_removal_evidence(db, [repo.id])[repo.id] == now - timedelta(
                days=3
            )
            assert last_runs(db, [repo])[repo.id].last_prune == now - timedelta(days=3)
            _op(db, repo, "delete_archive", now - timedelta(days=3, hours=1))
            assert last_runs(db, [repo])[repo.id].last_prune is None
            # the positive direction of the dry-run filter: a real prune counts
            _op(db, repo, "prune", now - timedelta(hours=1), params={"dry_run": False})
            assert last_runs(db, [repo])[repo.id].last_prune == now - timedelta(hours=1)
        finally:
            db.close()
            engine.dispose()
            _reset_postgres()
