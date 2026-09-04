from datetime import datetime, timedelta

import pytest

from app.database.models import (
    Archive,
    ArchiveChange,
    BackupJob,
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
        completed_at=completed_at,
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

    def test_live_listing_moved(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        # Mounted sub-applications and included routers have no `path`.
        paths = {
            route.path for route in test_client.app.routes if hasattr(route, "path")
        }
        assert "/api/repositories/{repo_id}/archives/live" in paths

    def test_requires_repository_access(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        assert test_client.get(
            f"/api/repositories/{repo.id}/archives", headers=auth_headers
        ).status_code in (403, 404)


@pytest.mark.unit
class TestHeatmap:
    def test_counts_sizes_and_missed_days_for_community(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        for d in (1, 2, 4):
            _archive(test_db, repo, f"a{d}", d)
        _archive(test_db, repo, "a5", 5, size=10)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?since=2026-09-01T00:00:00&until=2026-09-06T00:00:00",
            headers=admin_headers,
        )
        assert r.status_code == 200
        body = r.json()
        series = {s["series"]: s for s in body["series"]}["nas"]
        days = {d["date"]: d for d in series["days"]}
        assert (
            days["2026-09-01"]["count"] == 1
            and days["2026-09-01"]["deduplicated_size"] == 100
        )
        assert "2026-09-03" in series["missed_days"]
        assert days["2026-09-05"]["anomalies"] == []
        assert body["flags_available"] == {
            "missed_run": True,
            "size_outlier": False,
            "duration_outlier": False,
        }

    def test_outlier_flags_only_for_pro(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        for d in range(1, 8):
            _archive(test_db, repo, f"a{d}", d)
        _archive(test_db, repo, "a8", 8, size=10)
        _pro(test_db)
        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/heatmap?since=2026-09-01T00:00:00&until=2026-09-09T00:00:00",
            headers=admin_headers,
        )
        series = r.json()["series"][0]
        days = {d["date"]: d for d in series["days"]}
        assert days["2026-09-08"]["anomalies"] == ["size_outlier"]
        assert r.json()["flags_available"]["size_outlier"] is True


@pytest.mark.unit
class TestStatusStrip:
    def test_cells_from_operations_and_legacy(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        now = utc_now()
        _op(test_db, repo, "prune", completed_at=now - timedelta(days=20))
        _op(test_db, repo, "archive_sync", completed_at=now - timedelta(hours=1))
        _op(test_db, repo, "check", status="running")
        test_db.add(
            BackupJob(
                repository_id=repo.id,
                status="completed",
                completed_at=now - timedelta(days=3),
            )
        )
        test_db.commit()
        r = test_client.get(
            f"/api/repositories/{repo.id}/status-strip", headers=admin_headers
        )
        assert r.status_code == 200
        cells = {c["cell"]: c for c in r.json()["cells"]}
        assert set(cells) == {"backup", "check", "prune", "compact", "index"}
        assert (
            cells["backup"]["source"] == "legacy"
            and cells["backup"]["status"] == "completed"
        )
        assert cells["prune"]["threshold_days"] == 14
        assert cells["prune"]["overdue"] is None
        assert (
            cells["check"]["running"] is True and cells["check"]["completed_at"] is None
        )
        assert cells["index"]["age_seconds"] < 4000
        assert r.json()["overdue_available"] is False

    def test_overdue_flags_for_pro_and_mirror_cell(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db, repository_type="rclone")
        _pro(test_db)
        _op(test_db, repo, "prune", completed_at=utc_now() - timedelta(days=20))
        r = test_client.get(
            f"/api/repositories/{repo.id}/status-strip", headers=admin_headers
        )
        cells = {c["cell"]: c for c in r.json()["cells"]}
        assert "mirror" in cells
        assert cells["prune"]["overdue"] is True and cells["compact"]["overdue"] is True
        assert r.json()["overdue_available"] is True


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
