from datetime import timedelta

import pytest

from app.database.models import Operation, Repository, SystemSettings, utc_now
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
