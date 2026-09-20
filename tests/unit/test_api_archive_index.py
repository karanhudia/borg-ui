from datetime import datetime, timedelta

import pytest
from tests.utils.operations import seed_job_operation

from app.database.models import (
    Archive,
    BackupPlan,
    BackupPlanRepository,
    ArchiveChange,
    LicensingState,
    Operation,
    Repository,
    SystemSettings,
    utc_now,
)


def _repo(test_db, name="r", **kw):
    repo = Repository(
        name=name, path=f"/tmp/{name}", encryption="none", compression="lz4", **kw
    )
    test_db.add(repo)
    if test_db.query(SystemSettings).first() is None:
        test_db.add(SystemSettings())
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _archive(
    test_db,
    repo,
    name,
    day,
    series="nas",
    state="indexed",
    size=100,
    dur=10.0,
    nfiles=10,
):
    a = Archive(
        repository_id=repo.id,
        borg_id=f"id-{name}",
        name=name,
        series=series,
        start=datetime(2026, 9, day, 2),
        history_state=state,
        original_size=size,
        deduplicated_size=size,
        duration_seconds=dur,
        nfiles=nfiles,
    )
    test_db.add(a)
    test_db.commit()
    test_db.refresh(a)
    return a


def _op(
    test_db,
    repo,
    kind,
    status="completed",
    completed_at=None,
    category=None,
    trigger="manual",
    params=None,
):
    from app.services.operations.vocab import category_for

    op = Operation(
        repository_id=repo.id,
        kind=kind,
        category=category or category_for(kind),
        status=status,
        trigger=trigger,
        priority=0,
        run_id="run",
        # a row with a completion ran; deletion evidence keys on started_at
        started_at=(completed_at - timedelta(minutes=1)) if completed_at else None,
        completed_at=completed_at,
        params=params,
    )
    test_db.add(op)
    test_db.commit()
    return op


def _pro(test_db):
    # get_or_create_licensing_state always returns the first row in the
    # table; flip it rather than inserting a second one, in case an earlier
    # request in this test already created the default Community row.
    state = test_db.query(LicensingState).first()
    if state is None:
        test_db.add(
            LicensingState(instance_id="t-archive-index", plan="pro", status="active")
        )
    else:
        state.plan = "pro"
        state.status = "active"
    test_db.commit()


@pytest.mark.unit
class TestArchiveList:
    def test_lists_from_table_with_filters_and_sync_state(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)
        _archive(test_db, repo, "b1", 2, series="docs")
        _archive(test_db, repo, "a2", 3)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives", headers=admin_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert [a["name"] for a in body["archives"]] == ["a2", "b1", "a1"]
        assert body["sync_state"] == "never" and body["last_synced_at"] is None
        assert sorted(body["series"]) == ["docs", "nas"]
        assert body["history_available"] is False
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives?series=nas&since=2026-09-02T00:00:00",
            headers=admin_headers,
        )
        assert [a["name"] for a in r.json()["archives"]] == ["a2"]

    def test_sync_state_fresh_syncing_stale(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _op(test_db, repo, "archive_sync", completed_at=utc_now())
        assert (
            test_client.get(
                f"/api/repositories/{repo.id}/archives", headers=admin_headers
            ).json()["sync_state"]
            == "fresh"
        )
        _op(test_db, repo, "archive_sync", status="queued")
        assert (
            test_client.get(
                f"/api/repositories/{repo.id}/archives", headers=admin_headers
            ).json()["sync_state"]
            == "syncing"
        )
        test_db.query(Operation).delete()
        _op(test_db, repo, "archive_sync", completed_at=utc_now() - timedelta(days=3))
        assert (
            test_client.get(
                f"/api/repositories/{repo.id}/archives", headers=admin_headers
            ).json()["sync_state"]
            == "stale"
        )

    def test_sync_state_tolerates_two_missed_reconciles(self, test_db):
        """One missed hourly reconcile must not flip the chip to stale; the
        threshold is three intervals."""
        from app.api.archive_index import sync_state_from

        now = utc_now().replace(tzinfo=None)
        assert sync_state_from(False, now - timedelta(minutes=170), 60) == "fresh"
        assert sync_state_from(False, now - timedelta(minutes=190), 60) == "stale"

    def test_detail_has_neighbours_and_history_state(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2, state="pending")
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a2.id}", headers=admin_headers
        )
        assert r.status_code == 200
        assert r.json()["history_state"] == "pending"
        assert r.json()["predecessor_id"] == a1.id and r.json()["successor_id"] is None
        assert (
            test_client.get(
                f"/api/repositories/{repo.id}/archives/999", headers=admin_headers
            ).status_code
            == 404
        )

    def test_detail_carries_measurement_date_and_predecessor_stats(
        self, test_client, test_db, admin_headers
    ):
        """Spec 4.2: the header draws its deltas from one request."""
        repo = _repo(test_db)
        a1 = _archive(test_db, repo, "a1", 1, size=100, dur=10.0, nfiles=10)
        a2 = _archive(test_db, repo, "a2", 2, size=150, dur=12.0, nfiles=11)
        a2.stats_measured_at = datetime(2026, 9, 2, 2, 30)
        test_db.commit()

        body = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a2.id}", headers=admin_headers
        ).json()
        assert body["stats_measured_at"].startswith("2026-09-02T02:30")
        assert body["predecessor_stats"] == {
            "id": a1.id,
            "nfiles": 10,
            "original_size": 100,
            "deduplicated_size": 100,
            "duration_seconds": 10.0,
        }

        first = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a1.id}", headers=admin_headers
        ).json()
        assert first["predecessor_stats"] is None
        assert first["stats_measured_at"] is None

    def test_live_listing_moved(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        # The generated schema rather than app.routes: how the route table is
        # nested varies between FastAPI versions, and included routers do not
        # necessarily expose a `path` of their own.
        paths = test_client.app.openapi()["paths"]
        assert "/api/repositories/{repo_id}/archives/live" in paths
        assert "get" in paths["/api/repositories/{repo_id}/archives/live"]

    def test_requires_repository_access(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        assert test_client.get(
            f"/api/repositories/{repo.id}/archives", headers=auth_headers
        ).status_code in (403, 404)


@pytest.mark.unit
class TestHeatmap:
    def test_repository_band_holds_every_archive(
        self, test_client, test_db, admin_headers
    ):
        """The band is the archive index, not an inference over it: an archive
        whose name puts it in a one-archive series is still in the repository
        band and still counted (issue #943)."""
        repo = _repo(test_db)
        for d in (1, 2, 4):
            _archive(test_db, repo, f"a{d}", d)
        _archive(test_db, repo, "old-a5", 5, series="old", size=10)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap",
            headers=admin_headers,
        )
        assert r.status_code == 200
        body = r.json()
        band = body["repository"]
        assert band["count"] == 4
        days = {d["date"]: d for d in band["days"]}
        assert set(days) == {"2026-09-01", "2026-09-02", "2026-09-04", "2026-09-05"}
        assert (
            days["2026-09-01"]["count"] == 1
            and days["2026-09-01"]["deduplicated_size"] == 100
        )
        assert {s["series"] for s in body["series"]} == {"nas", "old"}
        assert body["flags_available"] == {
            "missed_run": True,
            "size_outlier": False,
            "duration_outlier": False,
        }

    def test_no_missed_days_without_a_cron(self, test_client, test_db, admin_headers):
        """Nothing schedules this repository, so an absent day is as likely a
        prune as a failure and the heatmap says nothing (issue #943)."""
        repo = _repo(test_db)
        for d in (1, 2, 4):
            _archive(test_db, repo, f"a{d}", d)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?until=2026-09-06T00:00:00",
            headers=admin_headers,
        )
        body = r.json()
        assert body["cadence_known"] is False
        assert body["repository"]["missed_days"] == []

    def test_plan_cron_gives_the_cadence(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _plan(test_db, repo, cron_expression="0 2 * * *")
        for d in (1, 2, 4):
            _archive(test_db, repo, f"a{d}", d)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?until=2026-09-06T00:00:00",
            headers=admin_headers,
        )
        body = r.json()
        assert body["cadence_known"] is True
        assert body["repository"]["missed_days"] == ["2026-09-03", "2026-09-05"]

    def test_a_completed_backup_clears_the_day(
        self, test_client, test_db, admin_headers
    ):
        """The run happened and its archive was pruned; the operation row is
        the evidence (#966) that keeps the day out of the red."""
        repo = _repo(test_db)
        _plan(test_db, repo, cron_expression="0 2 * * *")
        for d in (1, 2, 4):
            _archive(test_db, repo, f"a{d}", d)
        seed_job_operation(
            test_db,
            "backup",
            repository_id=repo.id,
            status="completed",
            started_at=datetime(2026, 9, 3, 2, 0),
            completed_at=datetime(2026, 9, 3, 2, 30),
        )
        test_db.commit()
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?until=2026-09-06T00:00:00",
            headers=admin_headers,
        )
        assert r.json()["repository"]["missed_days"] == ["2026-09-05"]

    def test_days_beyond_retention_are_not_missed(
        self, test_client, test_db, admin_headers
    ):
        """With prune keeping two daily archives, older days have no archive by
        design, so they carry no claim either way."""
        repo = _repo(test_db)
        _plan(
            test_db,
            repo,
            cron_expression="0 2 * * *",
            run_prune_after=True,
            prune_keep_daily=2,
        )
        _archive(test_db, repo, "a1", 1)
        _archive(test_db, repo, "a5", 5)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?until=2026-09-06T00:00:00",
            headers=admin_headers,
        )
        body = r.json()
        assert body["retention_since"] == "2026-09-04"
        assert body["repository"]["missed_days"] == ["2026-09-04"]

    def test_outliers_compare_within_a_series(
        self, test_client, test_db, admin_headers
    ):
        """The days are repository-wide, the comparison is not: a small archive
        of one series must not be judged against a large series that happens to
        have run before it."""
        repo = _repo(test_db)
        for d in range(1, 8):
            _archive(test_db, repo, f"big{d}", d, series="media", size=1000)
        _archive(test_db, repo, "docs1", 8, series="docs", size=10)
        _pro(test_db)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?until=2026-09-09T00:00:00",
            headers=admin_headers,
        )
        days = {d["date"]: d for d in r.json()["repository"]["days"]}
        assert days["2026-09-08"]["anomalies"] == []

    def test_outlier_flags_only_for_pro(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        for d in range(1, 8):
            _archive(test_db, repo, f"a{d}", d)
        _archive(test_db, repo, "a8", 8, size=10)
        _pro(test_db)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?until=2026-09-09T00:00:00",
            headers=admin_headers,
        )
        days = {d["date"]: d for d in r.json()["repository"]["days"]}
        assert days["2026-09-08"]["anomalies"] == ["size_outlier"]
        assert r.json()["flags_available"]["size_outlier"] is True


@pytest.mark.unit
class TestArchiveGrowth:
    def _measured(self, test_db, repo, name, day, **kw):
        a = _archive(test_db, repo, name, day, **kw)
        a.stats_measured_at = utc_now().replace(tzinfo=None)
        test_db.commit()
        return a

    def test_points_carry_a_running_total_and_skip_unmeasured_archives(
        self, test_client, test_db, admin_headers
    ):
        """One point per measured archive, oldest first; the running total
        is the repository footprint after that archive (spec 4.3). A row the
        info fill has not reached yet has no size and is not a point."""
        repo = _repo(test_db)
        self._measured(test_db, repo, "a1", 1, size=100)
        stale = _archive(test_db, repo, "a2", 2, size=50)  # sizes, no date
        unmeasured = _archive(test_db, repo, "a3", 3)
        unmeasured.original_size = None
        unmeasured.deduplicated_size = None
        test_db.commit()
        self._measured(test_db, repo, "old-a4", 4, series="old", size=30)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/growth", headers=admin_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert [p["name"] for p in body["points"]] == ["a1", "a2", "old-a4"]
        assert [p["running_total"] for p in body["points"]] == [100, 150, 180]
        assert [p["stale"] for p in body["points"]] == [False, True, False]
        assert body["points"][1]["archive_id"] == stale.id
        assert body["points"][0]["original_size"] == 100
        assert body["points"][0]["start"].startswith("2026-09-01T02:00:00")
        assert body["series"] == ["nas", "old"]
        assert body["stale_count"] == 1
        assert body["unmeasured_count"] == 1

    def test_points_carry_the_repository_size_measured_after_them(
        self, test_client, test_db, admin_headers
    ):
        """The growth line: each point takes the last size sample between
        its start and the next archive's. An archive older than every
        sample has none; the newest takes the latest."""
        from app.database.models import RepositorySizeSample

        repo = _repo(test_db)
        a1 = self._measured(test_db, repo, "a1", 1, size=100)
        a2 = self._measured(test_db, repo, "a2", 2, size=50)
        a3 = self._measured(test_db, repo, "a3", 3, size=20)
        add = lambda when, size: test_db.add(  # noqa: E731
            RepositorySizeSample(
                repository_id=repo.id, measured_at=when, size_bytes=size, source="t"
            )
        )
        add(a2.start + timedelta(minutes=5), 5_000)  # after a2, before a3
        add(a2.start + timedelta(hours=6), 4_000)  # a prune later that day: wins
        add(a3.start + timedelta(minutes=5), 20_000)
        test_db.commit()

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/growth", headers=admin_headers
        )
        assert r.status_code == 200
        sizes = [p["repository_size"] for p in r.json()["points"]]
        assert sizes == [None, 4_000, 20_000]
        assert a1.id  # the oldest predates the sampling and stays unknown

    def test_an_unplotted_archive_bounds_the_sample_window(
        self, test_client, test_db, admin_headers
    ):
        """A sample taken after an archive this curve does not plot (another
        series, or one the info fill never measured) belongs to that archive,
        not to the plotted point before it."""
        from app.database.models import RepositorySizeSample

        repo = _repo(test_db)
        self._measured(test_db, repo, "a1", 1, size=100)
        other = self._measured(test_db, repo, "old-a2", 2, series="old", size=30)
        self._measured(test_db, repo, "a3", 3, size=20)
        test_db.add(
            RepositorySizeSample(
                repository_id=repo.id,
                measured_at=other.start + timedelta(minutes=5),
                size_bytes=9_000,
                source="t",
            )
        )
        test_db.commit()

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/growth?series=nas",
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert [p["repository_size"] for p in r.json()["points"]] == [None, None]

    def test_series_filter_restarts_the_running_total(
        self, test_client, test_db, admin_headers
    ):
        """Filtered to one series, the total is that series' footprint, and
        the series list still names every series so the select can switch."""
        repo = _repo(test_db)
        self._measured(test_db, repo, "a1", 1, size=100)
        self._measured(test_db, repo, "old-a2", 2, series="old", size=30)
        self._measured(test_db, repo, "old-a3", 3, series="old", size=20)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/growth",
            params={"series": "old"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert [p["name"] for p in body["points"]] == ["old-a2", "old-a3"]
        assert [p["running_total"] for p in body["points"]] == [30, 50]
        assert body["series"] == ["nas", "old"]

    def test_rows_reported_removed_are_not_points(
        self, test_client, test_db, admin_headers
    ):
        """A row the newest listing reported removed lingers until
        history_merge deletes it (never in the `archives` index mode). It is
        no longer in the repository, so it adds nothing to the footprint."""
        repo = _repo(test_db)
        self._measured(test_db, repo, "a1", 1, size=100)
        removed = self._measured(test_db, repo, "a2", 2, series="gone", size=50)
        self._measured(test_db, repo, "a3", 3, size=20)
        unmeasured = _archive(test_db, repo, "old-a4", 4, series="old")
        unmeasured.deduplicated_size = None
        test_db.commit()
        sync = _op(
            test_db, repo, "archive_sync", completed_at=datetime(2026, 9, 5, 9, 54)
        )
        sync.result = {"listed": 2, "removed_archive_ids": [removed.id]}
        test_db.commit()

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/growth", headers=admin_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert [p["name"] for p in body["points"]] == ["a1", "a3"]
        assert [p["running_total"] for p in body["points"]] == [100, 120]
        # The selector lists surviving series only, measured or not.
        assert body["series"] == ["nas", "old"]
        assert body["unmeasured_count"] == 1

    def test_requires_repository_access(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        assert test_client.get(
            f"/api/repositories/{repo.id}/archives/growth", headers=auth_headers
        ).status_code in (403, 404)


def _plan(test_db, repo, **flags):
    """An enabled, scheduled plan: only such a plan runs on its own and is
    an expectation (a manual-only plan is not)."""
    flags.setdefault("schedule_enabled", True)
    flags.setdefault("cron_expression", "0 0 * * *")
    plan = BackupPlan(
        name=f"plan-{repo.id}", source_directories="[]", enabled=True, **flags
    )
    test_db.add(plan)
    test_db.flush()
    test_db.add(
        BackupPlanRepository(
            backup_plan_id=plan.id,
            repository_id=repo.id,
            enabled=True,
            execution_order=0,
        )
    )
    test_db.commit()
    return plan


def _cells(test_client, admin_headers, repo, route="status"):
    r = test_client.get(f"/api/repositories/{repo.id}/{route}", headers=admin_headers)
    assert r.status_code == 200
    return r.json(), {c["cell"]: c for c in r.json()["cells"]}


@pytest.mark.unit
class TestRepositoryStatus:
    def test_cells_from_the_operations_of_each_kind(
        self, test_client, test_db, admin_headers
    ):
        """With no archives the operations are the only evidence."""
        repo = _repo(test_db)
        now = utc_now()
        _op(test_db, repo, "prune", completed_at=now - timedelta(days=20))
        _op(test_db, repo, "archive_sync", completed_at=now - timedelta(hours=1))
        _op(test_db, repo, "check", status="running")
        seed_job_operation(
            test_db,
            "backup",
            repository_id=repo.id,
            status="completed",
            completed_at=now - timedelta(days=3),
        )
        test_db.commit()
        body, cells = _cells(test_client, admin_headers, repo)
        assert set(cells) == {"backup", "check", "prune", "compact", "index"}
        assert (
            cells["backup"]["source"] == "operations"
            and cells["backup"]["status"] == "completed"
        )
        assert cells["prune"]["threshold_days"] == 14
        assert cells["prune"]["overdue"] is None
        assert (
            cells["check"]["running"] is True and cells["check"]["completed_at"] is None
        )
        assert cells["index"]["age_seconds"] < 4000
        assert body["overdue_available"] is False

    def test_status_prefers_a_new_check_operation_over_the_legacy_row(
        self, test_client, test_db, admin_headers
    ):
        """Phase 5 moved check to `operations`; a migrated kind's first run
        must take over its status cell with no route change."""

        repo = _repo(test_db)
        old = utc_now() - timedelta(days=10)
        test_db.add(
            seed_job_operation(
                test_db,
                "check",
                repository_id=repo.id,
                status="failed",
                completed_at=old,
            )
        )
        _op(test_db, repo, "check", completed_at=old + timedelta(hours=1))
        test_db.commit()

        r = test_client.get(
            f"/api/repositories/{repo.id}/status", headers=admin_headers
        )

        cells = {c["cell"]: c for c in r.json()["cells"]}
        assert cells["check"]["status"] == "completed"
        assert cells["check"]["source"] == "operations"

    def test_backup_comes_from_the_archive_list(
        self, test_client, test_db, admin_headers
    ):
        """An archive created outside Borg UI (cron, CLI) is the backup; an
        older Borg UI job row does not make it look overdue (#935)."""
        repo = _repo(test_db)
        newest = _archive(test_db, repo, "a2", 5)
        _archive(test_db, repo, "a1", 1)
        test_db.add(
            seed_job_operation(
                test_db,
                "backup",
                repository_id=repo.id,
                status="completed",
                completed_at=datetime(2026, 8, 14, 8, 45),
            )
        )
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["backup"]["source"] == "archive"
        assert cells["backup"]["status"] == "completed"
        assert cells["backup"]["completed_at"].startswith(newest.start.isoformat()[:19])

    def test_failed_attempt_newer_than_the_archive_shows_the_failure(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)
        _op(test_db, repo, "backup", status="failed", completed_at=datetime(2026, 9, 3))
        # a terminal row without completed_at (PostgreSQL sorts NULL first on
        # DESC) must not hide the timestamped one
        _op(test_db, repo, "backup", status="cancelled", completed_at=None)
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["backup"]["status"] == "failed"
        assert cells["backup"]["source"] == "operations"
        assert cells["backup"]["completed_at"].startswith("2026-09-03")

    def test_removed_archive_pending_history_merge_is_no_backup_evidence(
        self, test_client, test_db, admin_headers
    ):
        """archive_sync reports a removed archive and leaves the row to
        history_merge; until that runs the row is no evidence, as for
        last_backup."""
        repo = _repo(test_db)
        older = _archive(test_db, repo, "a1", 1)
        removed = _archive(test_db, repo, "a2", 5)
        sync = _op(
            test_db, repo, "archive_sync", completed_at=datetime(2026, 9, 5, 9, 54)
        )
        sync.result = {"listed": 1, "removed_archive_ids": [removed.id]}
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["backup"]["source"] == "archive"
        assert cells["backup"]["completed_at"].startswith(older.start.isoformat()[:19])

    def test_a_prune_preview_is_not_the_last_prune(
        self, test_client, test_db, admin_headers
    ):
        """The Prune dialog's dry run is a completed `prune` operation with
        `params.dry_run`; the cell keeps the real run and, on Pro with a
        plan that prunes, stays overdue. A running preview still shows as
        running."""
        repo = _repo(test_db)
        _pro(test_db)
        _plan(test_db, repo, run_prune_after=True)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "prune", completed_at=now - timedelta(days=20))
        _op(
            test_db,
            repo,
            "prune",
            completed_at=now - timedelta(hours=1),
            params={"keep_daily": 7, "dry_run": True},
        )
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["completed_at"].startswith(
            (now - timedelta(days=20)).isoformat()[:19]
        )
        assert cells["prune"]["overdue"] is True
        _op(test_db, repo, "prune", status="running", params={"dry_run": True})
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["running"] is True

    def test_a_borg_ui_deletion_does_not_read_as_a_prune(
        self, test_client, test_db, admin_headers
    ):
        """An archive deleted from the Archives page disappears from the
        next listing like a pruned one; the prune cell keeps its job row."""
        repo = _repo(test_db)
        now = utc_now().replace(tzinfo=None)
        _op(test_db, repo, "archive_sync", completed_at=now - timedelta(days=4))
        _op(test_db, repo, "prune", completed_at=now - timedelta(days=3))
        _op(test_db, repo, "delete_archive", completed_at=now - timedelta(days=2))
        sync = _op(test_db, repo, "archive_sync", completed_at=now - timedelta(days=1))
        sync.result = {"removed_archive_ids": [7]}
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["source"] == "operations"
        assert cells["prune"]["completed_at"].startswith(
            (now - timedelta(days=3)).isoformat()[:19]
        )

    def test_archive_evidence_reads_a_bounded_window_per_series(
        self, test_client, test_db, admin_headers
    ):
        """Only the newest CADENCE_SAMPLE archives per series are read, and
        the newest archive (the backup evidence) is among them, so a long
        hourly history is not scanned on every status request."""
        from app.services.operations import anomalies
        from app.services.operations.repository_status import series_starts

        repo = _repo(test_db)
        for day in range(1, 21):
            _archive(test_db, repo, f"nas-{day}", day)
        for day in range(1, 4):
            _archive(test_db, repo, f"db-{day}", day, series="db")
        by_series = series_starts(test_db, repo.id)
        assert len(by_series["nas"]) == anomalies.CADENCE_SAMPLE == 14
        assert by_series["nas"][-1] == datetime(2026, 9, 20, 2)
        assert by_series["nas"][0] == datetime(2026, 9, 7, 2)
        assert len(by_series["db"]) == 3
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["backup"]["completed_at"].startswith("2026-09-20T02")

    def test_cancelled_attempt_newer_than_the_archive_shows_the_cancellation(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)
        _op(
            test_db,
            repo,
            "backup",
            status="cancelled",
            completed_at=datetime(2026, 9, 3),
        )
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["backup"]["status"] == "cancelled"
        assert cells["backup"]["source"] == "operations"
        assert cells["backup"]["completed_at"].startswith("2026-09-03")

    def test_cancelled_sync_is_no_prune_evidence(
        self, test_client, test_db, admin_headers
    ):
        """The runner keeps the listing of a sync it marks cancelled but
        enqueues no follow-ups, so its removals are not applied."""
        repo = _repo(test_db)
        sync = _op(
            test_db,
            repo,
            "archive_sync",
            status="cancelled",
            completed_at=datetime(2026, 9, 5, 9, 54),
        )
        sync.result = {"listed": 19, "removed_archive_ids": [99]}
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["source"] != "removal"
        assert cells["prune"]["status"] is None

    def test_prune_comes_from_detected_removals(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        sync = _op(
            test_db, repo, "archive_sync", completed_at=datetime(2026, 9, 5, 9, 54)
        )
        sync.result = {"listed": 19, "removed_archive_ids": [99]}
        test_db.add(
            seed_job_operation(
                test_db,
                "prune",
                repository_id=repo.id,
                status="completed",
                completed_at=datetime(2026, 8, 14, 8, 45),
            )
        )
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["source"] == "removal"
        assert cells["prune"]["completed_at"].startswith("2026-09-05T09:54")
        # a newer prune run through Borg UI is exact evidence and wins
        _op(test_db, repo, "prune", completed_at=datetime(2026, 9, 6, 1, 0))
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["source"] == "operations"

    def test_overdue_is_judged_against_plans_schedules_and_cadence(
        self, test_client, test_db, admin_headers
    ):
        """Pro: backup against twice the series cadence; prune and compact
        only when a plan runs them; check only when scheduled."""
        repo = _repo(test_db, repository_type="rclone", check_schedule_enabled=False)
        _pro(test_db)
        _op(test_db, repo, "prune", completed_at=utc_now() - timedelta(days=20))
        _, cells = _cells(test_client, admin_headers, repo)
        assert "mirror" in cells
        # nothing planned: no expectation, no warning
        assert cells["prune"]["overdue"] is None
        assert cells["compact"]["overdue"] is None
        assert cells["check"]["overdue"] is None
        # no archives at all: the backup is overdue
        assert cells["backup"]["overdue"] is True

        plan = _plan(test_db, repo, run_prune_after=True, run_compact_after=True)
        repo.check_schedule_enabled = True
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is True
        assert cells["compact"]["overdue"] is True
        assert cells["check"]["overdue"] is True

        # an enabled plan whose association with this repository is disabled
        # skips it at run time, so it is no expectation either
        association = (
            test_db.query(BackupPlanRepository)
            .filter_by(backup_plan_id=plan.id, repository_id=repo.id)
            .one()
        )
        association.enabled = False
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is None
        assert cells["compact"]["overdue"] is None
        association.enabled = True
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is True

        # a cron plan without an expression never gets a due time from the
        # scheduler, so it is no expectation either; availability mode is
        plan.cron_expression = None
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is None
        assert cells["compact"]["overdue"] is None
        plan.schedule_mode = "availability"
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is True
        plan.schedule_mode = "cron"
        plan.cron_expression = "0 0 * * *"
        test_db.commit()

    def test_backup_cadence_threshold(self, test_client, test_db, admin_headers):
        """Daily archives: the fixed two-day rule; weekly archives: two weeks."""
        repo = _repo(test_db)
        _pro(test_db)
        now = utc_now().replace(tzinfo=None)
        for i in range(4):
            a = _archive(test_db, repo, f"w{i}", 1)
            a.start = now - timedelta(days=7 * (4 - i))
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["backup"]["threshold_days"] == 14
        assert cells["backup"]["overdue"] is False  # 7 days old, cadence 7 days

        for a in test_db.query(Archive).filter_by(repository_id=repo.id):
            a.start = a.start - timedelta(days=10)
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["backup"]["overdue"] is True  # 17 days old

    def test_two_daily_series_are_not_one_hourly_cadence(self, test_db):
        """Review F09: two nightly hosts a minute apart interleave into
        one-minute gaps; each series is daily and on time at noon."""
        from app.services.operations.repository_status import repository_status

        repo = _repo(test_db)
        now = datetime(2026, 9, 6, 12)
        for day in range(7):
            for minute, series in enumerate(("host-a", "host-b")):
                a = _archive(test_db, repo, f"{series}-{day}", 1, series=series)
                a.start = datetime(2026, 9, 6, 0, minute) - timedelta(days=day)
        test_db.commit()
        cell = {
            c["cell"]: c
            for c in repository_status(test_db, repo, now=now, pro=True)["cells"]
        }["backup"]
        assert cell["overdue"] is False
        assert cell["threshold_days"] == 2

        # one series falling silent makes the repository overdue even while
        # the other keeps going
        for a in test_db.query(Archive).filter_by(series="host-b"):
            a.start = a.start - timedelta(days=5)
        test_db.commit()
        cell = {
            c["cell"]: c
            for c in repository_status(test_db, repo, now=now, pro=True)["cells"]
        }["backup"]
        assert cell["overdue"] is True

    def test_manual_only_plan_is_no_expectation(
        self, test_client, test_db, admin_headers
    ):
        """Review F10: the dispatcher requires schedule_enabled, so a plan
        that is only run by hand promises no prune, compact or check."""
        repo = _repo(test_db, check_schedule_enabled=False)
        _pro(test_db)
        _plan(
            test_db,
            repo,
            schedule_enabled=False,
            run_prune_after=True,
            run_compact_after=True,
            run_check_after=True,
        )
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is None
        assert cells["compact"]["overdue"] is None
        assert cells["check"]["overdue"] is None

    def test_legacy_schedule_targets_follow_the_scheduler(
        self, test_client, test_db, admin_headers
    ):
        """Review F11: association rows first, else the direct repository,
        else the path, as app/api/schedule.py dispatches."""
        from app.database.models import ScheduledJob, ScheduledJobRepository

        repo = _repo(test_db)
        other = _repo(test_db, name="other")
        _pro(test_db)
        direct = ScheduledJob(
            name="direct",
            repository_id=repo.id,
            enabled=True,
            cron_expression="0 0 * * *",
            run_prune_after=True,
            run_compact_after=True,
        )
        test_db.add(direct)
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is True and cells["compact"]["overdue"] is True

        # association rows take precedence over a stale direct field
        test_db.add(
            ScheduledJobRepository(
                scheduled_job_id=direct.id, repository_id=other.id, execution_order=0
            )
        )
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["prune"]["overdue"] is None
        _, cells = _cells(test_client, admin_headers, other)
        assert cells["prune"]["overdue"] is True

        # an enabled cron job without an expression is never dispatched, so
        # it is no expectation either (CodeRabbit on the F11 change)
        idle = ScheduledJob(
            name="idle",
            repository_id=repo.id,
            enabled=True,
            cron_expression=None,
            run_compact_after=True,
        )
        test_db.add(idle)
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["compact"]["overdue"] is None
        test_db.delete(idle)
        test_db.commit()

        # path-only legacy job
        by_path = ScheduledJob(
            name="by-path",
            repository=repo.path,
            enabled=True,
            cron_expression="0 0 * * *",
            run_compact_after=True,
        )
        test_db.add(by_path)
        test_db.commit()
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["compact"]["overdue"] is True
        assert cells["prune"]["overdue"] is None

    def test_scheduled_plan_check_after_backup_is_an_expectation(
        self, test_client, test_db, admin_headers
    ):
        """Review F12: the executor runs run_check_after, so it expects a
        check even with the repository's own check schedule off."""
        repo = _repo(test_db, check_schedule_enabled=False)
        _pro(test_db)
        _plan(test_db, repo, run_check_after=True)
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["check"]["overdue"] is True
        _op(test_db, repo, "check", completed_at=utc_now() - timedelta(days=1))
        _, cells = _cells(test_client, admin_headers, repo)
        assert cells["check"]["overdue"] is False

    def test_removal_evidence_is_the_newest_listing_with_removals(self, test_db):
        """The newest listing with removals wins; newer listings without
        removals do not hide it."""
        from app.services.operations.repository_status import prune_removal_evidence

        repo = _repo(test_db)
        now = utc_now()
        _op(test_db, repo, "archive_sync", completed_at=now - timedelta(days=3))
        removal = _op(
            test_db, repo, "archive_sync", completed_at=now - timedelta(days=2)
        )
        removal.result = {"removed_archive_ids": [7]}
        newer = _op(test_db, repo, "archive_sync", completed_at=now - timedelta(days=1))
        newer.result = {"removed_archive_ids": []}
        test_db.commit()
        assert (
            prune_removal_evidence(test_db, [repo.id])[repo.id] == removal.completed_at
        )


@pytest.mark.unit
class TestRebuild:
    def test_rebuild_from_stats_and_archives(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "a1", 1)
        a.original_size = 5
        test_db.commit()
        r = test_client.post(
            f"/api/repositories/{repo.id}/rebuild",
            json={"from": "stats"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["stats"]
        r = test_client.post(
            f"/api/repositories/{repo.id}/rebuild",
            json={"from": "archives"},
            headers=admin_headers,
        )
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        # history_merge is not plan gated: it is the only deleter of rows for
        # archives that have left the repository, so a Community rebuild needs
        # it too. history_index is gated and absent here.
        assert kinds == ["archive_sync", "history_merge", "stats"]
        ops = test_db.query(Operation).all()
        assert all(o.trigger == "manual" and o.priority == 20 for o in ops)
        test_db.refresh(a)
        assert a.original_size is None

    def test_resync_enqueues_the_reconcile_chain_once(
        self, test_client, test_db, admin_headers
    ):
        """Deleting, pruning, or wiping leaves the stored archive list ahead
        of the repository, and the list is what the Archives page reads, so
        the client asks for a resync instead of waiting for the interval."""
        repo = _repo(test_db)
        r = test_client.post(
            f"/api/repositories/{repo.id}/resync", headers=admin_headers
        )
        assert r.status_code == 200, r.text
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["archive_sync", "history_merge", "stats"]
        ops = test_db.query(Operation).all()
        assert all(o.trigger == "reconcile" and o.priority == 20 for o in ops)

        # A second call while the first run is still queued adds nothing, so
        # a burst of deletes does not build a queue of identical runs.
        again = test_client.post(
            f"/api/repositories/{repo.id}/resync", headers=admin_headers
        )
        assert again.status_code == 200
        assert again.json()["operations"] == []
        assert test_db.query(Operation).count() == len(kinds)

    def test_resync_requires_operator(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        r = test_client.post(
            f"/api/repositories/{repo.id}/resync", headers=auth_headers
        )
        assert r.status_code == 403

    def test_rebuild_from_history_is_pro_and_resets_archives(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "a1", 1)
        test_db.add(ArchiveChange(archive_id=a.id, path="x", change="added"))
        test_db.commit()
        r = test_client.post(
            f"/api/repositories/{repo.id}/rebuild",
            json={"from": "history"},
            headers=admin_headers,
        )
        assert (
            r.status_code == 403 and r.json()["detail"]["feature"] == "archive_history"
        )
        _pro(test_db)
        r = test_client.post(
            f"/api/repositories/{repo.id}/rebuild",
            json={"from": "history"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["history_index", "stats"]
        test_db.refresh(a)
        assert (
            a.history_state == "pending" and test_db.query(ArchiveChange).count() == 0
        )

    async def test_rebuild_from_history_stops_a_running_history_index(
        self, test_db, monkeypatch
    ):
        """A run in flight holds the archive list, the excludes and the row
        cap it started with, and writes rows back after the delete (#1079),
        so the rebuild stops it before it resets anything."""
        import asyncio

        from app.api import archive_index

        repo = _repo(test_db)
        op = _op(test_db, repo, "history_index", status="running")
        stopping = asyncio.Event()
        task = asyncio.create_task(stopping.wait())

        async def request_cancel(operation_id):
            assert operation_id == op.id
            stopping.set()
            return True

        monkeypatch.setattr(
            archive_index.operation_runner, "request_cancel", request_cancel
        )
        archive_index.operation_runner.running_tasks[op.id] = task
        try:
            await archive_index._stop_history_writers(test_db, repo.id)
        finally:
            archive_index.operation_runner.running_tasks.pop(op.id, None)
        assert task.done()

    async def test_rebuild_from_history_refuses_a_run_that_does_not_stop(
        self, test_db, monkeypatch
    ):
        """Deleting the rows of a run that keeps going is the bug itself, so
        a run that ignores the cancel refuses the rebuild instead."""
        import asyncio

        from fastapi import HTTPException

        from app.api import archive_index

        repo = _repo(test_db)
        op = _op(test_db, repo, "history_merge", status="running")
        task = asyncio.create_task(asyncio.Event().wait())

        async def request_cancel(operation_id):
            return True

        monkeypatch.setattr(
            archive_index.operation_runner, "request_cancel", request_cancel
        )
        monkeypatch.setattr(archive_index, "CANCEL_WAIT_SECONDS", 0.01)
        archive_index.operation_runner.running_tasks[op.id] = task
        try:
            with pytest.raises(HTTPException) as err:
                await archive_index._stop_history_writers(test_db, repo.id)
        finally:
            archive_index.operation_runner.running_tasks.pop(op.id, None)
            task.cancel()
        assert err.value.status_code == 409
        assert err.value.detail["key"] == "backend.errors.archives.historyRunning"
        assert err.value.detail["params"]["operationId"] == op.id

    async def test_rebuild_from_history_refuses_a_run_of_another_worker(
        self, test_db, monkeypatch
    ):
        """No task here means no cancel flag to raise: the row is another
        worker's, and its rows would come back after the delete."""
        from fastapi import HTTPException

        from app.api import archive_index

        repo = _repo(test_db)
        _op(test_db, repo, "history_index", status="running")

        async def request_cancel(operation_id):
            return False

        monkeypatch.setattr(
            archive_index.operation_runner, "request_cancel", request_cancel
        )
        with pytest.raises(HTTPException) as err:
            await archive_index._stop_history_writers(test_db, repo.id)
        assert err.value.status_code == 409

    def test_rebuild_from_history_ignores_finished_and_other_repositories(
        self, test_client, test_db, admin_headers
    ):
        """Only a running history writer on this repository blocks; a
        finished one, and another repository's run, do not."""
        _pro(test_db)
        repo = _repo(test_db)
        other = _repo(test_db, name="r2")
        _op(test_db, repo, "history_index", status="completed")
        _op(test_db, other, "history_index", status="running")
        r = test_client.post(
            f"/api/repositories/{repo.id}/rebuild",
            json={"from": "history"},
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text

    def test_rebuild_requires_operator(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        r = test_client.post(
            f"/api/repositories/{repo.id}/rebuild",
            json={"from": "stats"},
            headers=auth_headers,
        )
        assert r.status_code == 403

    def test_rebuild_rejects_unknown_stage(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.post(
            f"/api/repositories/{repo.id}/rebuild",
            json={"from": "x"},
            headers=admin_headers,
        )
        assert r.status_code == 422


@pytest.mark.unit
class TestRepositorySettings:
    def test_history_excludes_round_trip(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.get(f"/api/repositories/{repo.id}", headers=admin_headers)
        # The single-repository GET nests the payload under "repository".
        assert r.json()["repository"]["history_index_excludes"][0] == "**/.cache/**"
        r = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"history_index_excludes": ["**/tmp/**"]},
            headers=admin_headers,
        )
        assert r.status_code == 200
        test_db.refresh(repo)
        assert repo.history_index_excludes == ["**/tmp/**"]

    def test_an_explicitly_empty_exclude_list_survives_the_round_trip(
        self, test_client, test_db, admin_headers
    ):
        """Clearing every pattern stores []; the defaults are only a fallback
        for a row that predates the column. Reading [] back as the defaults
        would show five active patterns while the indexer excludes nothing."""
        repo = _repo(test_db)
        r = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"history_index_excludes": []},
            headers=admin_headers,
        )
        assert r.status_code == 200
        test_db.refresh(repo)
        assert repo.history_index_excludes == []

        single = test_client.get(
            f"/api/repositories/{repo.id}", headers=admin_headers
        ).json()["repository"]
        assert single["history_index_excludes"] == []

        listed = test_client.get("/api/repositories/", headers=admin_headers).json()
        rows = listed if isinstance(listed, list) else listed["repositories"]
        row = next(x for x in rows if x["id"] == repo.id)
        assert row["history_index_excludes"] == []


def _change(test_db, archive, path, change, before=None, after=None, count=None):
    test_db.add(
        ArchiveChange(
            archive_id=archive.id,
            path=path,
            change=change,
            size_before=before,
            size_after=after,
            summary_count=count,
        )
    )
    test_db.commit()


@pytest.mark.unit
class TestProGate:
    @pytest.mark.parametrize(
        "path", ["/archives/1/changes", "/history?path=x", "/search?q=x"]
    )
    def test_community_gets_403(self, test_client, test_db, admin_headers, path):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)
        r = test_client.get(f"/api/repositories/{repo.id}{path}", headers=admin_headers)
        assert r.status_code == 403
        assert r.json()["detail"] == {
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": "archive_history",
            "required": "pro",
            "current": "community",
        }


@pytest.mark.unit
class TestChanges:
    def _three(self, test_db, repo):
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2)
        a3 = _archive(test_db, repo, "a3", 3)
        _change(test_db, a1, "a", "added", after=10)
        _change(test_db, a1, "b", "added", after=3)
        _change(test_db, a2, "a", "modified", before=10, after=12)
        _change(test_db, a2, "b", "removed", before=3)
        _change(test_db, a2, "d", "added", after=5)
        _change(test_db, a3, "a", "modified", before=12, after=20)
        _change(test_db, a3, "b", "added", after=7)
        _change(test_db, a3, "d", "removed", before=5)
        _change(test_db, a3, "lib/x/y/z", "summary", count=4)
        return a1, a2, a3

    def test_default_compares_with_predecessor(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes",
            headers=admin_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["compare_to_id"] == a2.id
        assert {c["path"]: c["change"] for c in body["changes"]} == {
            "a": "modified",
            "b": "added",
            "d": "removed",
            "lib/x/y/z": "summary",
        }
        assert body["totals"] == {"added": 1, "removed": 1, "modified": 1, "summary": 1}
        assert body["next_cursor"] is None and body["history_state"] == "indexed"

    def test_compare_to_folds_intermediate_deltas(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes?compare_to={a1.id}",
            headers=admin_headers,
        )
        body = r.json()
        by = {c["path"]: c for c in body["changes"]}
        assert by["a"]["change"] == "modified" and (
            by["a"]["size_before"],
            by["a"]["size_after"],
        ) == (
            10,
            20,
        )
        assert by["b"]["change"] == "modified" and (
            by["b"]["size_before"],
            by["b"]["size_after"],
        ) == (
            3,
            7,
        )
        assert "d" not in by

    def test_filters_and_cursor(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes?change=added&change=removed",
            headers=admin_headers,
        )
        assert sorted(c["path"] for c in r.json()["changes"]) == ["b", "d"]
        # The totals are the filter chips' counts, so they describe the whole
        # comparison, not the slice the chips currently show.
        assert r.json()["totals"] == {
            "added": 1,
            "removed": 1,
            "modified": 1,
            "summary": 1,
        }
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes?path_prefix=lib/",
            headers=admin_headers,
        )
        assert [c["path"] for c in r.json()["changes"]] == ["lib/x/y/z"]
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes?limit=2",
            headers=admin_headers,
        )
        first = r.json()
        assert len(first["changes"]) == 2 and first["next_cursor"] is not None
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes?limit=2&cursor={first['next_cursor']}",
            headers=admin_headers,
        )
        assert len(r.json()["changes"]) == 2 and r.json()["next_cursor"] is None

    def test_pending_archive_returns_empty_with_state(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _pro(test_db)
        a = _archive(test_db, repo, "a1", 1, state="pending")
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a.id}/changes",
            headers=admin_headers,
        )
        assert (
            r.status_code == 200
            and r.json()["changes"] == []
            and r.json()["history_state"] == "pending"
        )

    def test_compare_to_must_be_older_in_same_series(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _pro(test_db)
        a1, a2, a3 = self._three(test_db, repo)
        other = _archive(test_db, repo, "o", 1, series="other")
        assert (
            test_client.get(
                f"/api/repositories/{repo.id}/archives/{a1.id}/changes?compare_to={a3.id}",
                headers=admin_headers,
            ).status_code
            == 400
        )
        assert (
            test_client.get(
                f"/api/repositories/{repo.id}/archives/{a3.id}/changes?compare_to={other.id}",
                headers=admin_headers,
            ).status_code
            == 400
        )


@pytest.mark.unit
class TestHistory:
    def test_history_entries_and_present_ranges(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _pro(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2)
        a3 = _archive(test_db, repo, "a3", 3)
        a4 = _archive(test_db, repo, "a4", 4)
        _change(test_db, a1, "docs/f", "added", after=1)
        _change(test_db, a2, "docs/f", "modified", before=1, after=2)
        _change(test_db, a3, "docs/f", "removed", before=2)
        _change(test_db, a4, "docs/f", "added", after=9)
        r = test_client.get(
            f"/api/repositories/{repo.id}/history?path=docs/f", headers=admin_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert [e["archive_id"] for e in body["entries"]] == [
            a4.id,
            a3.id,
            a2.id,
            a1.id,
        ]
        assert (
            body["entries"][0]["change"] == "added"
            and body["entries"][0]["size_after"] == 9
        )
        assert body["present"] == [
            {"series": "nas", "from_archive_id": a1.id, "to_archive_id": a3.id},
            {"series": "nas", "from_archive_id": a4.id, "to_archive_id": None},
        ]
        assert body["present_in_latest"] is True
        r = test_client.get(
            f"/api/repositories/{repo.id}/history?path=nope", headers=admin_headers
        )
        assert r.json()["entries"] == [] and r.json()["present_in_latest"] is False


@pytest.mark.unit
class TestSearch:
    def test_search_groups_by_path(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2)
        a3 = _archive(test_db, repo, "a3", 3)
        _change(test_db, a1, "docs/Invoice.xlsx", "added", after=1)
        _change(test_db, a2, "docs/Invoice.xlsx", "modified", before=1, after=2)
        _change(test_db, a1, "old/invoice.txt", "added", after=1)
        _change(test_db, a3, "old/invoice.txt", "removed", before=1)
        _change(test_db, a1, "photo.jpg", "added", after=1)
        r = test_client.get(
            f"/api/repositories/{repo.id}/search?q=invoice", headers=admin_headers
        )
        assert r.status_code == 200
        results = {x["path"]: x for x in r.json()["results"]}
        assert set(results) == {"docs/Invoice.xlsx", "old/invoice.txt"}
        inv = results["docs/Invoice.xlsx"]
        assert (
            inv["archive_count"] == 2
            and inv["first_seen_archive_id"] == a1.id
            and inv["last_seen_archive_id"] == a2.id
        )
        assert inv["present_in_latest"] is True
        assert results["old/invoice.txt"]["present_in_latest"] is False
        assert r.json()["truncated"] is False
        r = test_client.get(
            f"/api/repositories/{repo.id}/search?q=invoice&limit=1",
            headers=admin_headers,
        )
        assert len(r.json()["results"]) == 1 and r.json()["truncated"] is True
        assert (
            test_client.get(
                f"/api/repositories/{repo.id}/search?q=", headers=admin_headers
            ).status_code
            == 422
        )


@pytest.mark.unit
class TestTimezoneAwareRangeParams:
    """`?until=...Z` parses into an aware datetime, but Archive.start and the
    anomaly helpers are naive UTC, so the value has to be normalised before it
    reaches either."""

    def test_heatmap_accepts_offset_carrying_bounds(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)
        _archive(test_db, repo, "a2", 3)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap",
            params={
                "since": "2026-08-01T00:00:00Z",
                "until": "2026-10-01T00:00:00+02:00",
            },
            headers=admin_headers,
        )

        assert r.status_code == 200
        assert r.json()["series"][0]["days"]

    def test_list_accepts_offset_carrying_bounds(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _archive(test_db, repo, "a1", 1)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives",
            params={"since": "2026-08-01T00:00:00Z", "until": "2026-10-01T00:00:00Z"},
            headers=admin_headers,
        )

        assert r.status_code == 200
        assert len(r.json()["archives"]) == 1


@pytest.mark.unit
class TestFoldAndSearchBounds:
    def test_changes_reports_an_incomplete_fold(
        self, test_client, test_db, admin_headers
    ):
        """An intermediate archive that was never indexed contributes an empty
        delta, so the fold silently omits whatever changed in that window. The
        response has to say so."""
        repo = _repo(test_db)
        _pro(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2, state="failed")
        a3 = _archive(test_db, repo, "a3", 3)
        _change(test_db, a1, "a", "added", after=10)
        _change(test_db, a3, "c", "added", after=1)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes?compare_to={a1.id}",
            headers=admin_headers,
        )

        body = r.json()
        assert body["incomplete"] is True
        assert body["unindexed_archive_ids"] == [a2.id]

    def test_complete_fold_is_not_flagged(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _pro(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        a2 = _archive(test_db, repo, "a2", 2)
        a3 = _archive(test_db, repo, "a3", 3)
        _change(test_db, a2, "a", "added", after=10)
        _change(test_db, a3, "c", "added", after=1)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{a3.id}/changes?compare_to={a1.id}",
            headers=admin_headers,
        )

        body = r.json()
        assert body["incomplete"] is False and body["unindexed_archive_ids"] == []

    def test_search_bounds_the_scan_to_the_page_of_paths(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """The grouped result was limited only after every matching change row
        had been loaded, so a broad query pulled the whole table into memory.
        The path page must be bounded in SQL."""
        from app.api import archive_index

        repo = _repo(test_db)
        _pro(test_db)
        a1 = _archive(test_db, repo, "a1", 1)
        for i in range(12):
            _change(test_db, a1, f"file-{i:02d}.txt", "added", after=1)

        loaded: list[int] = []
        original = archive_index.rows_for_paths

        def counting(db, repository, paths):
            rows = original(db, repository, paths)
            loaded.append(len(rows))
            return rows

        monkeypatch.setattr(archive_index, "rows_for_paths", counting)
        r = test_client.get(
            f"/api/repositories/{repo.id}/search?q=file&limit=3",
            headers=admin_headers,
        )

        assert r.status_code == 200
        assert len(r.json()["results"]) == 3 and r.json()["truncated"] is True
        # Only the three paths on this page are grouped, not all twelve.
        assert loaded == [3]


@pytest.mark.unit
class TestWideCompareWindow:
    def test_compare_window_larger_than_the_sqlite_variable_limit(
        self, test_client, test_db, admin_headers
    ):
        """The window is bound one parameter per archive. Older SQLite builds
        cap that at 999, which three years of daily backups passes, so the
        query is chunked like known_sizes does for the same pattern. Modern
        builds allow 32766, so this exercises the wide window rather than
        reproducing the limit itself."""
        repo = _repo(test_db)
        _pro(test_db)
        first = _archive(test_db, repo, "a0", 1)
        _change(test_db, first, "a", "added", after=1)
        rows = [
            Archive(
                repository_id=repo.id,
                borg_id=f"id-w{i}",
                name=f"w{i}",
                series="nas",
                start=datetime(2026, 9, 1, 2) + timedelta(hours=i + 1),
                history_state="indexed",
            )
            for i in range(1100)
        ]
        test_db.add_all(rows)
        test_db.commit()
        last = rows[-1]
        test_db.add(
            ArchiveChange(
                archive_id=last.id,
                path="a",
                change="modified",
                size_before=1,
                size_after=2,
            )
        )
        test_db.commit()

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/{last.id}/changes"
            f"?compare_to={first.id}",
            headers=admin_headers,
        )

        assert r.status_code == 200
        assert {c["path"] for c in r.json()["changes"]} == {"a"}


@pytest.mark.unit
def test_archive_changes_has_no_btree_index_on_the_unbounded_path():
    """`path` is unbounded Text; a B-tree index over it makes the INSERT of a
    change row for a long archived path fail (PostgreSQL entry-size limit).
    No index may reference the raw path column at all - alone, inside a
    composite, or within an expression such as lower(path) - while archive_id
    keeps its own index for per-archive reads."""
    from sqlalchemy import Column
    from sqlalchemy.sql import visitors

    table = ArchiveChange.__table__
    path = table.c.path

    def referenced_columns(index):
        return {
            element
            for expression in index.expressions
            for element in visitors.iterate(expression)
            if isinstance(element, Column)
        }

    for index in table.indexes:
        assert path not in referenced_columns(index), (
            f"index {index.name} references the unbounded path column"
        )
    assert not path.index
    assert any({c.name for c in idx.columns} == {"archive_id"} for idx in table.indexes)


@pytest.mark.unit
class TestAgentRepositoryHistoryCapability:
    """A repository whose agent cannot produce the change listing has no
    history stage: the responses say so, nothing enqueues it, and a rebuild
    of it is refused (#953). Once its agent advertises the diff job it is a
    repository like any other (#1052)."""

    @staticmethod
    def _agent_repo(test_db):
        return _repo(
            test_db, name="agent", executor_type="agent", execution_target="agent"
        )

    @staticmethod
    def _capable_agent_repo(test_db):
        from app.database.models import AgentMachine

        machine = AgentMachine(
            name="current",
            agent_id="agt_history",
            token_hash="x",
            token_prefix="x",
            status="online",
            capabilities=["repository.list_archives", "repository.diff"],
        )
        test_db.add(machine)
        test_db.commit()
        return _repo(
            test_db,
            name="capable",
            executor_type="agent",
            execution_target="agent",
            agent_machine_id=machine.id,
        )

    def test_an_agent_with_the_diff_job_has_the_history_stage(
        self, test_client, test_db, admin_headers
    ):
        capable = self._capable_agent_repo(test_db)
        a = _archive(test_db, capable, "a1", 1, state="skipped")
        r = test_client.get(
            f"/api/repositories/{capable.id}/archives", headers=admin_headers
        )
        # Community: the plan decides, as for a server repository
        assert r.json()["history_capability"] == "plan_locked"

        _pro(test_db)
        r = test_client.get(
            f"/api/repositories/{capable.id}/archives", headers=admin_headers
        )
        assert r.json()["history_capability"] == "available"
        r = test_client.post(
            f"/api/repositories/{capable.id}/rebuild",
            json={"from": "history"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["history_index", "stats"]
        test_db.refresh(a)
        assert a.history_state == "pending"

    def test_list_and_detail_name_the_capability(
        self, test_client, test_db, admin_headers
    ):
        _pro(test_db)
        agent = self._agent_repo(test_db)
        server = _repo(test_db, name="server")
        a = _archive(test_db, agent, "a1", 1, state="skipped")
        b = _archive(test_db, server, "b1", 1)

        r = test_client.get(
            f"/api/repositories/{agent.id}/archives", headers=admin_headers
        )
        assert r.status_code == 200
        assert r.json()["history_capability"] == "agent_unsupported"
        # `history_available` keeps meaning "the plan has the feature"
        assert r.json()["history_available"] is True
        r = test_client.get(
            f"/api/repositories/{agent.id}/archives/{a.id}", headers=admin_headers
        )
        assert r.json()["history_capability"] == "agent_unsupported"
        r = test_client.get(
            f"/api/repositories/{agent.id}/archives/{a.id}/changes",
            headers=admin_headers,
        )
        assert r.json()["history_capability"] == "agent_unsupported"

        r = test_client.get(
            f"/api/repositories/{server.id}/archives", headers=admin_headers
        )
        assert r.json()["history_capability"] == "available"
        assert r.json()["history_available"] is True
        r = test_client.get(
            f"/api/repositories/{server.id}/archives/{b.id}", headers=admin_headers
        )
        assert r.json()["history_capability"] == "available"

    def test_community_reads_as_plan_locked(self, test_client, test_db, admin_headers):
        server = _repo(test_db, name="server")
        r = test_client.get(
            f"/api/repositories/{server.id}/archives", headers=admin_headers
        )
        assert r.json()["history_capability"] == "plan_locked"
        assert r.json()["history_available"] is False
        # the executor's reason outlasts the plan: an agent's repository
        # names it on Community too
        agent = self._agent_repo(test_db)
        r = test_client.get(
            f"/api/repositories/{agent.id}/archives", headers=admin_headers
        )
        assert r.json()["history_capability"] == "agent_unsupported"
        assert r.json()["history_available"] is False

    def test_rebuild_from_history_is_refused_for_an_agent_repository(
        self, test_client, test_db, admin_headers
    ):
        _pro(test_db)
        agent = self._agent_repo(test_db)
        a = _archive(test_db, agent, "a1", 1, state="skipped")
        r = test_client.post(
            f"/api/repositories/{agent.id}/rebuild",
            json={"from": "history"},
            headers=admin_headers,
        )
        assert r.status_code == 409
        assert (
            r.json()["detail"]["key"]
            == "backend.errors.archives.historyUnavailableForAgent"
        )
        test_db.refresh(a)
        assert a.history_state == "skipped"  # not reset to "pending" for nothing
        assert test_db.query(Operation).count() == 0

    def test_rebuild_from_archives_skips_the_history_stage_for_an_agent_repository(
        self, test_client, test_db, admin_headers
    ):
        _pro(test_db)
        agent = self._agent_repo(test_db)
        _archive(test_db, agent, "a1", 1, state="skipped")
        r = test_client.post(
            f"/api/repositories/{agent.id}/rebuild",
            json={"from": "archives"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        kinds = [test_db.get(Operation, i).kind for i in r.json()["operations"]]
        assert kinds == ["archive_sync", "history_merge", "stats"]

    def test_path_history_reports_its_coverage(
        self, test_client, test_db, admin_headers
    ):
        _pro(test_db)
        agent = self._agent_repo(test_db)
        _archive(test_db, agent, "a1", 1, state="skipped")
        _archive(test_db, agent, "a2", 2, state="skipped")
        r = test_client.get(
            f"/api/repositories/{agent.id}/history",
            params={"path": "etc/hosts"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["entries"] == []
        # `skipped` archives are uncovered like `pending` ones; the
        # capability says why they stay so
        assert r.json()["coverage"] == {
            "indexed": 0,
            "exhausted": 0,
            "total": 2,
            "capability": "agent_unsupported",
        }

        server = _repo(test_db, name="server")
        _archive(test_db, server, "b1", 1)
        _archive(test_db, server, "b2", 2, state="pending")
        retrying = _archive(test_db, server, "b3", 3, state="failed")
        given_up = _archive(test_db, server, "b4", 4, state="failed")
        given_up.history_attempts = 3
        test_db.commit()
        r = test_client.get(
            f"/api/repositories/{server.id}/history",
            params={"path": "etc/hosts"},
            headers=admin_headers,
        )
        # one failure still has retries, one the executor gave up on
        assert retrying.history_attempts in (None, 0)
        assert r.json()["coverage"] == {
            "indexed": 1,
            "exhausted": 1,
            "total": 4,
            "capability": "available",
        }


from unittest.mock import AsyncMock, patch

from app.services import prune_preview as pp
from app.services.prune_preview import Verdict


def _hex(n):
    return f"{n:064x}"


def _fake_dry_run(status="completed", log="borg said"):
    from app.services.operations.vocab import category_for

    async def run(
        db, repository, retention, *, user_id, run_id=None, depends_on_id=None
    ):
        op = Operation(
            kind="prune",
            category=category_for("prune"),
            repository_id=repository.id,
            status=status,
            trigger="manual",
            priority=0,
            run_id="run",
            params={**retention.as_params(), "dry_run": True},
        )
        db.add(op)
        db.commit()
        return op, log

    return run


class TestPrunePreview:
    def _setup(self, test_db):
        repo = _repo(test_db)
        a1 = _archive(test_db, repo, "a1", 1, size=100)
        a2 = _archive(test_db, repo, "a2", 2, size=200)
        a3 = _archive(test_db, repo, "a3", 3, size=300)
        for n, a in enumerate((a1, a2, a3), start=1):
            a.borg_id = _hex(n)
        test_db.commit()
        verdicts = [
            Verdict(_hex(3), "a3", "kept", "daily #1"),
            Verdict(_hex(2), "a2", "deleted", None),
            Verdict(_hex(1), "a1", "deleted", None),
        ]
        return repo, (a1, a2, a3), verdicts

    def test_preview_joins_measures_and_sums(self, test_client, test_db, admin_headers):
        repo, (a1, a2, a3), verdicts = self._setup(test_db)
        with (
            patch.object(pp, "run_prune_dry_run", new=_fake_dry_run()),
            patch.object(pp, "parse_prune_verdicts", return_value=verdicts),
            patch.object(
                pp, "remeasure_candidates", new=AsyncMock(return_value=False)
            ) as remeasure,
            patch.object(pp, "footprint", return_value=1000),
        ):
            r = test_client.post(
                f"/api/repositories/{repo.id}/prune/preview",
                json={"keep_daily": 1},
                headers=admin_headers,
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert [(a["name"], a["verdict"]) for a in body["archives"]] == [
            ("a1", "deleted"),
            ("a2", "deleted"),
            ("a3", "kept"),
        ]
        assert body["deleted_count"] == 2 and body["kept_count"] == 1
        assert body["freed_at_least"] == 300
        assert (
            body["footprint_before"] == 1000 and body["footprint_after_at_most"] == 700
        )
        assert body["partial_measure"] is False and body["log"] == "borg said"
        assert {a.id for a in remeasure.await_args.args[2]} == {a1.id, a2.id}
        assert body["lost_files"] == {"available": False, "capability": "plan_locked"}

    def test_stored_candidate_reads_back_without_borg(
        self, test_client, test_db, admin_headers
    ):
        """Clicking a compared policy is a read: the verdicts the comparison
        kept are joined to the index again, no dry run, no new operation."""
        from app.database.models import PruneComparison

        repo, (a1, a2, a3), verdicts = self._setup(test_db)
        test_db.add(
            PruneComparison(
                repository_id=repo.id,
                candidate="standard",
                label="Standard",
                retention={"keep_daily": 1},
                kept_count=1,
                deleted_count=2,
                freed_at_least=300,
                archive_count_at=3,
                computed_at=utc_now(),
                verdicts=[[v.borg_id, v.name, v.verdict, v.rule] for v in verdicts],
            )
        )
        test_db.commit()
        before = test_db.query(Operation).count()
        with patch.object(pp, "run_prune_dry_run", new=_fake_dry_run()) as never:
            r = test_client.get(
                f"/api/repositories/{repo.id}/prune/comparison/standard/preview",
                headers=admin_headers,
            )
            missing = test_client.get(
                f"/api/repositories/{repo.id}/prune/comparison/wide/preview",
                headers=admin_headers,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["kept_count"] == 1 and body["deleted_count"] == 2
        assert {a["id"] for a in body["archives"]} == {a1.id, a2.id, a3.id}
        assert body["freed_at_least"] == a1.deduplicated_size + a2.deduplicated_size
        assert test_db.query(Operation).count() == before
        assert never  # patched, never awaited: nothing ran Borg
        assert missing.status_code == 404

    def test_preview_run_id_groups_the_visit(self, test_client, test_db, admin_headers):
        """The dry runs of one visit to the preview page share a run, so the
        timeline shows them as steps instead of a loose row each."""
        repo, _, verdicts = self._setup(test_db)
        seen: list = []
        inner = _fake_dry_run()

        async def capture(db, repository, retention, **kwargs):
            seen.append(kwargs.get("run_id"))
            return await inner(db, repository, retention, **kwargs)

        with (
            patch.object(pp, "run_prune_dry_run", new=capture),
            patch.object(pp, "parse_prune_verdicts", return_value=verdicts),
            patch.object(pp, "remeasure_candidates", new=AsyncMock(return_value=False)),
            patch.object(pp, "footprint", return_value=1000),
        ):
            visit = "3f1d2b8e-0b1a-4c3d-9e7f-2a5b6c7d8e9f"
            for keep in (1, 2):
                r = test_client.post(
                    f"/api/repositories/{repo.id}/prune/preview",
                    json={"keep_daily": keep, "preview_run_id": visit},
                    headers=admin_headers,
                )
                assert r.status_code == 200
            bad = test_client.post(
                f"/api/repositories/{repo.id}/prune/preview",
                json={"keep_daily": 1, "preview_run_id": "run"},
                headers=admin_headers,
            )
        assert seen == [visit, visit]
        assert bad.status_code == 422

    def test_preview_on_pro_walks_lost_files(self, test_client, test_db, admin_headers):
        _pro(test_db)
        repo, (a1, a2, a3), verdicts = self._setup(test_db)
        with (
            patch.object(pp, "run_prune_dry_run", new=_fake_dry_run()),
            patch.object(pp, "parse_prune_verdicts", return_value=verdicts),
            patch.object(pp, "remeasure_candidates", new=AsyncMock(return_value=False)),
            patch.object(
                pp,
                "lost_files",
                return_value={
                    "incomplete": False,
                    "unindexed_archive_ids": [],
                    "total_count": 0,
                    "total_size": 0,
                    "top": [],
                    "by_folder": [],
                },
            ) as lost,
        ):
            r = test_client.post(
                f"/api/repositories/{repo.id}/prune/preview",
                json={"keep_daily": 1},
                headers=admin_headers,
            )
        assert r.status_code == 200
        assert r.json()["lost_files"]["available"] is True
        assert lost.call_args.kwargs["deleted_ids"] == {a1.id, a2.id}
        assert list(lost.call_args.args[2]) == ["nas"]

    def test_no_keep_rule_is_400(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.post(
            f"/api/repositories/{repo.id}/prune/preview",
            json={"keep_daily": 0},
            headers=admin_headers,
        )
        assert r.status_code == 400
        assert r.json()["detail"]["key"] == "backend.errors.prune.noKeepRule"

    def test_failed_dry_run_is_502_with_the_log(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        with patch.object(
            pp, "run_prune_dry_run", new=_fake_dry_run(status="failed", log="boom")
        ):
            r = test_client.post(
                f"/api/repositories/{repo.id}/prune/preview",
                json={"keep_daily": 1},
                headers=admin_headers,
            )
        assert r.status_code == 502
        assert r.json()["detail"]["key"] == "backend.errors.prune.dryRunFailed"
        assert r.json()["detail"]["params"]["log"] == "boom"

    def test_viewer_cannot_preview(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        r = test_client.post(
            f"/api/repositories/{repo.id}/prune/preview",
            json={"keep_daily": 1},
            headers=auth_headers,
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_run_candidate_returns_counts_and_freed(self, test_db):
        repo = _repo(test_db)
        kept = _archive(test_db, repo, "a1", 1, size=10)
        gone = _archive(test_db, repo, "a2", 2, size=30)
        kept.borg_id = _hex(1)
        gone.borg_id = _hex(2)
        test_db.commit()
        log = (
            f"Keeping archive (rule: daily #1):            a1  Thu, 2026-09-17 15:07:55 [{kept.borg_id}]\n"
            f"Would prune:                                 a2  Thu, 2026-09-17 15:07:55 [{gone.borg_id}]\n"
        )
        with (
            patch.object(pp, "run_prune_dry_run", new=_fake_dry_run(log=log)),
            patch.object(pp, "remeasure_candidates", new=AsyncMock(return_value=False)),
        ):
            result = await pp.run_candidate(
                test_db, repo, pp.Retention(keep_daily=1), user_id=None
            )
        assert (result.kept_count, result.deleted_count) == (1, 1)
        assert result.freed_at_least == 30
        assert [a.id for a in result.candidates] == [gone.id]
        assert result.partial_measure is False


class TestPruneComparison:
    def test_get_returns_empty_and_stale_before_a_run(
        self, test_client, admin_headers, test_db
    ):
        repo = _repo(test_db)
        res = test_client.get(
            f"/api/repositories/{repo.id}/prune/comparison", headers=admin_headers
        )
        assert res.status_code == 200
        assert res.json() == {
            "computed_at": None,
            "archive_count_at": None,
            "stale": True,
            "candidates": [],
        }

    def test_get_returns_stored_rows(self, test_client, admin_headers, test_db):
        from app.database.models import PruneComparison

        repo = _repo(test_db)
        test_db.add(
            PruneComparison(
                repository_id=repo.id,
                candidate="standard",
                label="Standard",
                retention={"keep_daily": 7},
                kept_count=2,
                deleted_count=1,
                freed_at_least=40,
                archive_count_at=0,
                computed_at=utc_now(),
                verdicts=[["ab", "a0", "kept", "daily #1"]],
            )
        )
        test_db.commit()
        body = test_client.get(
            f"/api/repositories/{repo.id}/prune/comparison", headers=admin_headers
        ).json()
        assert body["stale"] is False
        # Naive UTC in the column; the browser reads an offset-less value as
        # local time, so the route must say which zone it is.
        assert body["computed_at"] is not None
        assert body["candidates"][0]["key"] == "standard"
        assert body["candidates"][0]["freed_at_least"] == 40

    def test_refresh_enqueues_one_operation_and_refuses_a_second(
        self, test_client, admin_headers, test_db, monkeypatch
    ):
        from app.database.models import Operation

        monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
        repo = _repo(test_db)
        res = test_client.post(
            f"/api/repositories/{repo.id}/prune/comparison/refresh",
            headers=admin_headers,
        )
        assert res.status_code == 200
        op = test_db.get(Operation, res.json()["operation_id"])
        assert (op.kind, op.status, op.trigger) == ("prune_compare", "queued", "manual")
        again = test_client.post(
            f"/api/repositories/{repo.id}/prune/comparison/refresh",
            headers=admin_headers,
        )
        assert again.status_code == 409


class TestPruneRetentionDefaults:
    def test_defaults_without_plan_or_prune(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.get(
            f"/api/repositories/{repo.id}/prune/retention-defaults",
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json() == {
            "source": "default",
            "plan_name": None,
            "keep_hourly": 0,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 6,
            "keep_quarterly": 0,
            "keep_yearly": 1,
            "keep_within": None,
        }

    def test_last_manual_prune_wins_over_defaults(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        _op(
            test_db,
            repo,
            "prune",
            params={"keep_daily": 3, "keep_within": "2d", "dry_run": True},
        )
        _op(test_db, repo, "prune", params={"keep_daily": 9, "keep_weekly": 2})
        r = test_client.get(
            f"/api/repositories/{repo.id}/prune/retention-defaults",
            headers=admin_headers,
        )
        body = r.json()
        assert (
            body["source"] == "last_prune"
            and body["keep_daily"] == 9
            and body["keep_weekly"] == 2
        )

    def test_plan_wins_over_last_prune(self, test_client, test_db, admin_headers):
        from app.database.models import BackupPlan, BackupPlanRepository

        repo = _repo(test_db)
        _op(test_db, repo, "prune", params={"keep_daily": 9})
        plan = BackupPlan(
            name="Nightly",
            run_prune_after=True,
            enabled=True,
            prune_keep_daily=14,
            prune_keep_within="1d",
            source_directories="[]",
        )
        test_db.add(plan)
        test_db.flush()
        test_db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=0,
            )
        )
        test_db.commit()
        r = test_client.get(
            f"/api/repositories/{repo.id}/prune/retention-defaults",
            headers=admin_headers,
        )
        body = r.json()
        assert body["source"] == "plan" and body["plan_name"] == "Nightly"
        assert body["keep_daily"] == 14 and body["keep_within"] == "1d"


@pytest.mark.unit
def test_set_repository_size_appends_a_sample_for_a_stored_repository(test_db):
    """A repository row in a session gets a history row per write, which
    the growth chart draws; the commit is the caller's."""
    from datetime import datetime

    from app.database.models import Repository, RepositorySizeSample
    from app.services.storage_usage import set_repository_size

    repo = Repository(name="r", path="/tmp/r", encryption="none")
    test_db.add(repo)
    test_db.commit()
    set_repository_size(repo, 2048, "borg2_index", measured_at=datetime(2026, 1, 1))
    set_repository_size(repo, 4096, "compact_stats", measured_at=datetime(2026, 1, 2))
    test_db.commit()
    rows = (
        test_db.query(RepositorySizeSample)
        .filter(RepositorySizeSample.repository_id == repo.id)
        .order_by(RepositorySizeSample.measured_at)
        .all()
    )
    assert [(r.size_bytes, r.source) for r in rows] == [
        (2048, "borg2_index"),
        (4096, "compact_stats"),
    ]


@pytest.mark.unit
def test_format_bytes_is_the_one_writer_of_a_size_string():
    """Every module that renders a byte count shares this function: the
    repository card, the dashboard totals, the SSH and rclone storage
    figures, the notification bodies and the backup service's messages.
    Two decimals, base 1024, and the top unit is EB (a value past PB used
    to come back labelled PB in two of the copies)."""
    from app.services.storage_usage import bytes_from_formatted, format_bytes

    assert format_bytes(0) == "0.00 B"
    assert format_bytes(999) == "999.00 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1536) == "1.50 KB"
    assert format_bytes(1024**2) == "1.00 MB"
    assert format_bytes(5 * 1024**3) == "5.00 GB"
    assert format_bytes(1024**4) == "1.00 TB"
    assert format_bytes(1024**5) == "1.00 PB"
    assert format_bytes(1024**6) == "1.00 EB"
    # Past 2**53 the arithmetic is float, so a count just under a boundary
    # carries to the next unit: 1 byte short of an exabyte reads "1.00 EB"
    # rather than "1024.00 PB". Deliberate. Exact arithmetic here would buy
    # a worse-reading string at a size no repository reaches.
    assert format_bytes(1024**6 - 1) == "1.00 EB"
    # the parser reads back what this writes, to the precision it prints
    assert bytes_from_formatted(format_bytes(1024**3)) == 1024**3


@pytest.mark.unit
def test_stored_size_bytes_is_the_one_rule_every_reader_applies():
    from types import SimpleNamespace

    from app.services.storage_usage import bytes_from_formatted, stored_size_bytes

    assert (
        stored_size_bytes(
            SimpleNamespace(total_size="2.19 GB", total_size_bytes=2_350_000_000)
        )
        == 2_350_000_000
    )
    assert (
        stored_size_bytes(SimpleNamespace(total_size="1.00 KB", total_size_bytes=None))
        == 1024
    )
    assert (
        stored_size_bytes(SimpleNamespace(total_size="Unknown", total_size_bytes=None))
        is None
    )
    assert (
        stored_size_bytes(SimpleNamespace(total_size=None, total_size_bytes=None))
        is None
    )
    assert bytes_from_formatted("2.40 TB") == 2_638_827_906_662
    # the shapes older releases wrote
    assert bytes_from_formatted("1.5GB") == 1_610_612_736
    assert bytes_from_formatted("1 GiB") == 1_073_741_824
    assert bytes_from_formatted("4096") == 4096
    assert bytes_from_formatted("512 b") == 512
    assert bytes_from_formatted("NaN KB") is None
    assert bytes_from_formatted("-1.00 KB") is None
    assert bytes_from_formatted("1.00 XB") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "text_value",
    [
        "2.40 TB",
        "490.23 KB",
        "0.00 B",
        "1.5GB",
        "1 GiB",
        "4096",
        "512 b",
        "Unknown",
        "N/A",
        "",
        None,
        "-1 KB",
        "1.00 XB",
    ],
)
def test_the_migration_backfill_parses_like_the_service(text_value):
    """The backfill carries its own copy of the parser (a migration imports
    no app code); the two must agree, or `measured_at is None` stops
    meaning what the docstrings say."""
    import importlib.util
    from pathlib import Path

    from app.services import storage_usage
    from app.services.storage_usage import bytes_from_formatted

    versions = Path(__file__).resolve().parents[2] / "app/database/alembic/versions"
    path = next(versions.glob("a9b8c7d6e5f4_*.py"))
    spec = importlib.util.spec_from_file_location("size_bytes_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.bytes_from_formatted(text_value) == bytes_from_formatted(text_value)
    # a widened service pattern must be widened in the copy as well; the
    # table above cannot know a shape added later
    assert module._SIZE_TEXT.pattern == storage_usage._SIZE_TEXT.pattern
    assert module._SIZE_TEXT.flags == storage_usage._SIZE_TEXT.flags
    assert module._SIZE_UNITS == storage_usage._SIZE_UNITS
