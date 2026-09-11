from datetime import timedelta

import pytest
from sqlalchemy import text

from app.database.models import (
    Operation,
    Repository,
    SystemSettings,
    UserRepositoryPermission,
    utc_now,
)
from app.services.operations.enqueue import enqueue


def _repo(test_db, name="r"):
    repo = Repository(
        name=name, path=f"/tmp/{name}", encryption="none", compression="lz4"
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _settings(test_db):
    s = test_db.query(SystemSettings).first()
    if s is None:
        s = SystemSettings()
        test_db.add(s)
        test_db.commit()
    return s


@pytest.mark.unit
class TestOperationsList:
    def test_list_filters_and_cursor(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a = enqueue(test_db, "stats", repository_id=repo.id, trigger="manual")
        b = enqueue(test_db, "archive_sync", repository_id=repo.id, trigger="reconcile")
        c = enqueue(test_db, "backup", repository_id=repo.id, trigger="schedule")
        r = test_client.get("/api/operations/?category=index", headers=admin_headers)
        assert r.status_code == 200
        assert [i["id"] for i in r.json()["items"]] == [b.id, a.id]
        r = test_client.get("/api/operations/?trigger=schedule", headers=admin_headers)
        assert [i["kind"] for i in r.json()["items"]] == ["backup"]
        r = test_client.get("/api/operations/?limit=2", headers=admin_headers)
        body = r.json()
        assert [i["id"] for i in body["items"]] == [c.id, b.id]
        assert body["next_cursor"] == b.id
        r = test_client.get(
            f"/api/operations/?limit=2&cursor={b.id}", headers=admin_headers
        )
        assert [i["id"] for i in r.json()["items"]] == [a.id]
        assert r.json()["next_cursor"] is None

    def test_list_item_shape_is_activity_superset(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        enqueue(test_db, "stats", repository_id=repo.id)
        item = test_client.get("/api/operations/", headers=admin_headers).json()[
            "items"
        ][0]
        for key in (
            "id",
            "type",
            "status",
            "started_at",
            "completed_at",
            "error_message",
            "repository",
            "triggered_by",
            "has_logs",
            "kind",
            "category",
            "trigger",
            "priority",
            "run_id",
            "progress_message",
            "skip_reason",
            "followups",
        ):
            assert key in item
        assert item["repository"] == "r"
        assert item["type"] == "stats"

    def test_requires_auth(self, test_client):
        assert test_client.get("/api/operations/").status_code == 401


@pytest.mark.unit
class TestOperationsQueue:
    def test_queue_names_the_maintenance_operation_that_holds_the_lane(
        self, test_client, test_db, admin_headers
    ):
        """A prune holds the lane as much as a backup does; the payload says
        which one it is, so the waiting stages do not have to guess."""
        repo = _repo(test_db)
        _settings(test_db)
        prune = enqueue(test_db, "prune", repository_id=repo.id)
        prune.status = "running"
        waiting = enqueue(test_db, "stats", repository_id=repo.id)
        test_db.commit()

        body = test_client.get("/api/operations/queue", headers=admin_headers).json()
        group = body["repositories"][0]

        assert group["lane_busy"] is True
        assert group["lane_holder"] == {"kind": "prune", "id": prune.id}
        assert waiting.id in {o["id"] for o in group["operations"]}

    def test_queue_reports_no_lane_holder_while_the_lane_is_free(
        self, test_client, test_db, admin_headers
    ):
        """A running index operation shares the repository rather than
        taking it, so it is not a holder and the lane stays free."""
        repo = _repo(test_db)
        _settings(test_db)
        running = enqueue(test_db, "stats", repository_id=repo.id)
        running.status = "running"
        enqueue(test_db, "archive_sync", repository_id=repo.id)
        test_db.commit()

        body = test_client.get("/api/operations/queue", headers=admin_headers).json()
        group = body["repositories"][0]

        assert group["lane_busy"] is False
        assert group["lane_holder"] is None

    def test_queue_holder_is_the_operation_that_took_the_lane(
        self, test_client, test_db, admin_headers
    ):
        """With two running exclusive rows the earliest start holds the
        lane; a row without one falls behind it rather than winning on id."""
        repo = _repo(test_db)
        _settings(test_db)
        later = enqueue(test_db, "check", repository_id=repo.id)
        later.status = "running"
        later.started_at = utc_now() - timedelta(minutes=1)
        undated = enqueue(test_db, "compact", repository_id=repo.id)
        undated.status = "running"
        undated.started_at = None
        earlier = enqueue(test_db, "prune", repository_id=repo.id)
        earlier.status = "running"
        earlier.started_at = utc_now() - timedelta(minutes=9)
        test_db.commit()

        body = test_client.get("/api/operations/queue", headers=admin_headers).json()
        group = body["repositories"][0]

        assert group["lane_holder"] == {"kind": "prune", "id": earlier.id}

    def test_queue_holder_falls_back_to_the_lowest_id_without_starts(
        self, test_client, test_db, admin_headers
    ):
        """A plan creates its post-backup prune and compact already running
        and without a start, so two rows can tie on the sentinel; the
        lowest id decides rather than the iteration order."""
        repo = _repo(test_db)
        _settings(test_db)
        first = enqueue(test_db, "prune", repository_id=repo.id)
        first.status = "running"
        first.started_at = None
        second = enqueue(test_db, "compact", repository_id=repo.id)
        second.status = "running"
        second.started_at = None
        test_db.commit()

        body = test_client.get("/api/operations/queue", headers=admin_headers).json()
        group = body["repositories"][0]

        assert first.id < second.id
        assert group["lane_holder"] == {"kind": "prune", "id": first.id}

    def test_queue_never_gives_the_system_group_a_lane_holder(
        self, test_client, test_db, admin_headers
    ):
        """Work without a repository is listed under System, which has no
        lane to take."""
        _settings(test_db)
        op = enqueue(test_db, "package_install")
        op.status = "running"
        test_db.commit()

        body = test_client.get("/api/operations/queue", headers=admin_headers).json()
        system = [g for g in body["repositories"] if g["repository_id"] is None][0]

        assert system["lane_busy"] is False
        assert system["lane_holder"] is None

    def test_queue_survives_an_operation_kind_this_build_does_not_know(
        self, test_client, test_db, admin_headers
    ):
        """A row left by a newer build costs its claim to the lane, not the
        board: it stays in the listing, and the stages under it read as
        merely queued rather than the whole page failing to load."""
        repo = _repo(test_db)
        _settings(test_db)
        known = enqueue(test_db, "prune", repository_id=repo.id)
        known.status = "running"
        test_db.commit()
        test_db.execute(
            text("UPDATE operations SET kind = :kind WHERE id = :id"),
            {"kind": "teleport", "id": known.id},
        )
        test_db.commit()

        response = test_client.get("/api/operations/queue", headers=admin_headers)

        assert response.status_code == 200
        group = response.json()["repositories"][0]
        assert known.id in {o["id"] for o in group["operations"]}
        assert group["lane_busy"] is False
        assert group["lane_holder"] is None

    def test_queue_groups_and_limits(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        settings = _settings(test_db)
        settings.index_workers = 3
        test_db.commit()
        running = enqueue(test_db, "history_index", repository_id=repo.id)
        running.status = "running"
        old = enqueue(test_db, "stats", repository_id=repo.id)
        old.status = "completed"
        old.completed_at = utc_now() - timedelta(minutes=5)
        recent = enqueue(test_db, "stats", repository_id=repo.id)
        recent.status = "completed"
        recent.completed_at = utc_now()
        test_db.commit()
        body = test_client.get("/api/operations/queue", headers=admin_headers).json()
        group = body["repositories"][0]
        assert group["repository_id"] == repo.id
        assert group["repository_name"] == "r"
        assert group["lane_busy"] is True
        # the waiting stages name what holds the lane instead of guessing
        assert group["lane_holder"] == {"kind": "history_index", "id": running.id}
        assert {o["id"] for o in group["operations"]} == {running.id, recent.id}
        assert body["limits"]["index_workers"] == 3
        assert body["limits"]["index_running"] == 1
        assert body["paused"] is False


@pytest.mark.unit
class TestOperationsDetailAndCancel:
    def test_detail_includes_run(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        a = enqueue(test_db, "stats", repository_id=repo.id)
        b = enqueue(
            test_db,
            "archive_sync",
            repository_id=repo.id,
            run_id=a.run_id,
            depends_on_id=a.id,
        )
        body = test_client.get(f"/api/operations/{a.id}", headers=admin_headers).json()
        assert body["id"] == a.id
        assert [o["id"] for o in body["run"]] == [a.id, b.id]

    def test_detail_404(self, test_client, admin_headers):
        assert (
            test_client.get("/api/operations/999", headers=admin_headers).status_code
            == 404
        )

    def test_cancel_queued(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        r = test_client.post(f"/api/operations/{op.id}/cancel", headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "cancel_requested"}
        test_db.expire_all()
        assert test_db.get(Operation, op.id).status == "cancelled"

    def test_cancel_terminal_is_409(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        op.status = "completed"
        test_db.commit()
        r = test_client.post(f"/api/operations/{op.id}/cancel", headers=admin_headers)
        assert r.status_code == 409

    def test_cancel_requires_operator(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        r = test_client.post(f"/api/operations/{op.id}/cancel", headers=auth_headers)
        assert r.status_code == 403

    def test_cancel_system_operation_requires_admin(
        self, test_client, test_db, operator_headers, admin_headers
    ):
        op = enqueue(test_db, "package_install", repository_id=None)
        r = test_client.post(
            f"/api/operations/{op.id}/cancel", headers=operator_headers
        )
        assert r.status_code == 403
        r = test_client.post(f"/api/operations/{op.id}/cancel", headers=admin_headers)
        assert r.status_code == 200


@pytest.mark.unit
class TestPauseAndLimits:
    def test_pause_resume(self, test_client, test_db, admin_headers):
        assert test_client.post(
            "/api/operations/pause", headers=admin_headers
        ).json() == {"paused": True}
        assert test_db.query(SystemSettings).first().background_paused is True
        assert test_client.post(
            "/api/operations/resume", headers=admin_headers
        ).json() == {"paused": False}

    def test_limits_validation_and_update(self, test_client, test_db, admin_headers):
        r = test_client.put(
            "/api/operations/limits", json={"index_workers": 0}, headers=admin_headers
        )
        assert r.status_code == 422
        r = test_client.put(
            "/api/operations/limits", json={"index_workers": 4}, headers=admin_headers
        )
        assert r.status_code == 200
        assert r.json()["index_workers"] == 4
        assert test_db.query(SystemSettings).first().index_workers == 4

    def test_pause_requires_admin(self, test_client, auth_headers):
        assert (
            test_client.post("/api/operations/pause", headers=auth_headers).status_code
            == 403
        )


@pytest.mark.unit
class TestLogs:
    def test_logs_and_download(self, test_client, test_db, admin_headers, tmp_path):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        log = tmp_path / f"operation_{op.id}.log"
        log.write_text("line1\nline2\n")
        op.log_file_path = str(log)
        # The default policy is failed_and_warnings, so use a finished status
        # it admits; a queued row has no logs by policy and is covered below.
        op.status = "completed_with_warnings"
        test_db.commit()
        body = test_client.get(
            f"/api/operations/{op.id}/logs?limit=1", headers=admin_headers
        ).json()
        assert body["lines"][0]["content"] == "line1"
        assert body["has_more"] is True
        r = test_client.get(
            f"/api/operations/{op.id}/logs/download", headers=admin_headers
        )
        assert r.status_code == 200
        assert b"line2" in r.content

    def test_logs_hidden_for_queued_operation_by_policy(
        self, test_client, test_db, admin_headers, tmp_path
    ):
        """`has_logs` is false for a queued row, so neither log route may serve it."""
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        log = tmp_path / f"operation_{op.id}.log"
        log.write_text("line1\n")
        op.log_file_path = str(log)
        test_db.commit()
        assert (
            test_client.get(
                f"/api/operations/{op.id}/logs", headers=admin_headers
            ).status_code
            == 404
        )
        assert (
            test_client.get(
                f"/api/operations/{op.id}/logs/download", headers=admin_headers
            ).status_code
            == 404
        )

    def test_download_refused_while_operation_running(
        self, test_client, test_db, admin_headers, tmp_path
    ):
        """The runner marks an operation running before the log is fully written."""
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        log = tmp_path / f"operation_{op.id}.log"
        log.write_text("partial\n")
        op.log_file_path = str(log)
        op.status = "running"
        test_db.commit()
        r = test_client.get(
            f"/api/operations/{op.id}/logs/download", headers=admin_headers
        )
        assert r.status_code == 404

    def test_logs_without_file(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        op.status = "completed_with_warnings"
        test_db.commit()
        r = test_client.get(f"/api/operations/{op.id}/logs", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["lines"] == []

    def test_download_without_file_is_404(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        op = enqueue(test_db, "stats", repository_id=repo.id)
        r = test_client.get(
            f"/api/operations/{op.id}/logs/download", headers=admin_headers
        )
        assert r.status_code == 404


def _archive(test_db, repo, name, **kw):
    from datetime import datetime

    from app.database.models import Archive

    a = Archive(
        repository_id=repo.id,
        borg_id=f"id-{name}",
        name=name,
        series="s",
        start=datetime(2026, 9, 1, 2),
        **kw,
    )
    test_db.add(a)
    test_db.commit()
    return a


@pytest.mark.unit
class TestOperationsRepositories:
    """GET /api/operations/repositories: the derived-data hub, one row per
    repository whether or not anything is running."""

    def test_rows_name_the_history_capability(
        self, test_client, test_db, admin_headers
    ):
        """The executor first, then the plan: an agent's repository is
        agent-unsupported on every plan; a server repository is plan-locked
        on Community and has the stage on Pro."""
        from app.database.models import LicensingState

        _repo(test_db, "server")
        agent = _repo(test_db, "agent")
        agent.executor_type = "agent"
        agent.execution_target = "agent"
        test_db.commit()

        r = test_client.get("/api/operations/repositories", headers=admin_headers)
        rows = {row["repository_name"]: row for row in r.json()["repositories"]}
        assert rows["server"]["history_capability"] == "plan_locked"
        assert rows["agent"]["history_capability"] == "agent_unsupported"
        assert r.json()["history_available"] is False

        # the first request created the single licensing row; flip that one
        # (lookups always read the first row in the table)
        state = test_db.query(LicensingState).first()
        state.plan = "pro"
        state.status = "active"
        test_db.commit()
        r = test_client.get("/api/operations/repositories", headers=admin_headers)
        rows = {row["repository_name"]: row for row in r.json()["repositories"]}
        assert rows["server"]["history_capability"] == "available"
        assert rows["agent"]["history_capability"] == "agent_unsupported"
        assert r.json()["history_available"] is True

    def test_rows_cover_every_repository_with_index_totals(
        self, test_client, test_db, admin_headers
    ):
        nas = _repo(test_db, "nas")
        _repo(test_db, "empty")
        _archive(test_db, nas, "a1", history_state="indexed", history_rows=10)
        _archive(
            test_db,
            nas,
            "a2",
            history_state="indexed",
            history_rows=5,
            history_truncated=True,
        )
        _archive(test_db, nas, "a3", history_state="failed", history_attempts=3)
        _archive(test_db, nas, "a4", history_state="pending")
        sync = enqueue(test_db, "archive_sync", repository_id=nas.id)
        sync.status = "completed"
        sync.completed_at = utc_now() - timedelta(minutes=10)
        stats = enqueue(test_db, "stats", repository_id=nas.id, trigger="reconcile")
        stats.status = "completed"
        stats.completed_at = utc_now() - timedelta(minutes=9)
        test_db.commit()

        r = test_client.get("/api/operations/repositories", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        rows = {row["repository_name"]: row for row in body["repositories"]}
        assert list(rows) == ["empty", "nas"]

        row = rows["nas"]
        assert row["repository_id"] == nas.id
        assert row["sync_state"] == "fresh"
        assert row["last_synced_at"] is not None
        assert row["last_stats_at"] is not None
        assert row["archives"] == 4
        assert row["history"] == {
            "indexed": 2,
            "pending": 1,
            "failed": 1,
            "skipped": 0,
            "truncated": 1,
            "rows": 15,
        }

        assert rows["empty"]["sync_state"] == "never"
        assert rows["empty"]["archives"] == 0
        assert rows["empty"]["history"]["rows"] == 0
        assert rows["empty"]["last_stats_at"] is None

        assert body["totals"]["repositories"] == 2
        assert body["totals"]["archives"] == 4
        assert body["totals"]["history_rows"] == 15
        # Bytes come from the database engine and may be unknown, but the
        # key is always present so the client can render "approx." or nothing.
        assert "history_bytes" in body["totals"]
        assert body["last_reconcile_at"] is not None
        assert body["reconcile_interval_minutes"] == 60
        assert body["history_available"] is False

    def test_rows_are_scoped_to_accessible_repositories(
        self, test_client, test_db, auth_headers
    ):
        _repo(test_db, "hidden")
        r = test_client.get("/api/operations/repositories", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["repositories"] == []
        assert r.json()["totals"]["repositories"] == 0

    def test_totals_count_only_accessible_repositories(
        self, test_client, test_db, admin_headers, auth_headers, test_user
    ):
        """A viewer with one grant must not learn how much everyone else has
        stored, so the aggregates run over the accessible rows only."""
        mine = _repo(test_db, "mine")
        hidden = _repo(test_db, "hidden")
        _archive(test_db, mine, "a1", history_state="indexed", history_rows=10)
        _archive(test_db, hidden, "b1", history_state="indexed", history_rows=999)
        test_db.add(
            UserRepositoryPermission(
                user_id=test_user.id, repository_id=mine.id, role="viewer"
            )
        )
        test_db.commit()

        body = test_client.get(
            "/api/operations/repositories", headers=auth_headers
        ).json()
        assert [row["repository_name"] for row in body["repositories"]] == ["mine"]
        assert body["totals"]["repositories"] == 1
        assert body["totals"]["archives"] == 1
        assert body["totals"]["history_rows"] == 10
        # The on-disk figure covers the whole table, so it is admin-only.
        assert body["totals"]["history_bytes"] is None

        admin = test_client.get(
            "/api/operations/repositories", headers=admin_headers
        ).json()
        assert admin["totals"]["history_rows"] == 1009

    def test_history_bytes_is_measured_once_per_interval(
        self, test_client, test_db, admin_headers, monkeypatch
    ):
        """The size scan walks the whole archive_changes b-tree, and the board
        polls every 30 seconds, so it is cached rather than re-measured."""
        from app.api import operations as operations_api

        _repo(test_db, "nas")
        calls = []
        operations_api._history_bytes_cache = None
        monkeypatch.setattr(
            operations_api,
            "_measure_history_table_bytes",
            lambda db: (calls.append(1), 4096)[1],
        )
        for _ in range(3):
            body = test_client.get(
                "/api/operations/repositories", headers=admin_headers
            ).json()
            assert body["totals"]["history_bytes"] == 4096
        assert len(calls) == 1

    def test_detail_lists_failed_and_truncated_archives(
        self, test_client, test_db, admin_headers
    ):
        nas = _repo(test_db, "nas")
        _archive(test_db, nas, "ok", history_state="indexed", history_rows=1)
        _archive(test_db, nas, "big", history_state="indexed", history_truncated=True)
        _archive(test_db, nas, "bad", history_state="failed", history_attempts=2)
        r = test_client.get(
            f"/api/operations/repositories/{nas.id}", headers=admin_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert body["repository_id"] == nas.id
        assert [a["name"] for a in body["failed_archives"]] == ["bad"]
        assert body["failed_archives"][0]["history_attempts"] == 2
        assert [a["name"] for a in body["truncated_archives"]] == ["big"]

    def test_detail_requires_repository_access(
        self, test_client, test_db, auth_headers
    ):
        repo = _repo(test_db, "hidden")
        r = test_client.get(
            f"/api/operations/repositories/{repo.id}", headers=auth_headers
        )
        assert r.status_code == 403

    def test_reconcile_now_enqueues_a_run_per_repository(
        self, test_client, test_db, admin_headers, auth_headers
    ):
        _repo(test_db, "a")
        _repo(test_db, "b")
        assert (
            test_client.post(
                "/api/operations/reconcile", headers=auth_headers
            ).status_code
            == 403
        )
        r = test_client.post("/api/operations/reconcile", headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["repositories"] == 2
        reconcile_ops = (
            test_db.query(Operation).filter(Operation.trigger == "reconcile").all()
        )
        assert {o.repository_id for o in reconcile_ops} == {
            r.id for r in test_db.query(Repository).all()
        }
