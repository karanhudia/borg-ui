from datetime import timedelta

import pytest

from app.database.models import Operation, PruneJob, Repository, utc_now
from app.services.operations.enqueue import enqueue, enqueue_chain


def _repo(test_db):
    repo = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


@pytest.mark.unit
class TestActivityUnion:
    def test_index_rows_hidden_by_default_and_shown_with_filter(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        enqueue(test_db, "stats", repository_id=repo.id)
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert body == []
        body = test_client.get(
            "/api/activity/recent?category=index", headers=admin_headers
        ).json()
        assert [i["type"] for i in body] == ["stats"]
        assert body[0]["category"] == "index"
        assert body[0]["status"] == "queued"
        assert body[0]["repository"] == "r"

    def test_legacy_and_operations_merge_ordered_by_time(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        old = PruneJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="completed",
            started_at=utc_now() - timedelta(hours=2),
        )
        test_db.add(old)
        test_db.commit()
        op = enqueue(test_db, "import_connect", repository_id=repo.id, trigger="import")
        op.status = "completed"
        op.started_at = utc_now() - timedelta(hours=1)
        test_db.commit()
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert [i["type"] for i in body] == ["import_connect", "prune"]
        assert body[1]["category"] == "maintenance"
        assert body[1]["trigger"] == "manual"
        assert body[1]["followups"] == []

    def test_collapse_runs_nests_followups(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        parent = enqueue(
            test_db, "import_connect", repository_id=repo.id, trigger="import"
        )
        parent.status = "completed"
        parent.started_at = utc_now()
        test_db.commit()
        chain = enqueue_chain(
            test_db,
            ["stats", "archive_sync"],
            repository_id=repo.id,
            trigger="followup",
            run_id=parent.run_id,
            depends_on_id=parent.id,
        )
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert [i["id"] for i in body] == [parent.id]
        assert [f["kind"] for f in body[0]["followups"]] == ["stats", "archive_sync"]
        flat = test_client.get(
            "/api/activity/recent?collapse_runs=false&category=index&category=import",
            headers=admin_headers,
        ).json()
        assert {i["id"] for i in flat} == {parent.id, chain[0].id, chain[1].id}
        assert all(i["followups"] == [] for i in flat)

    def test_category_filter_keeps_followups_of_visible_parent(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        parent = enqueue(
            test_db, "import_connect", repository_id=repo.id, trigger="import"
        )
        parent.status = "completed"
        parent.started_at = utc_now()
        test_db.commit()
        enqueue_chain(
            test_db,
            ["stats"],
            repository_id=repo.id,
            trigger="followup",
            run_id=parent.run_id,
            depends_on_id=parent.id,
        )
        body = test_client.get(
            "/api/activity/recent?category=import", headers=admin_headers
        ).json()
        assert [i["id"] for i in body] == [parent.id]
        assert [f["kind"] for f in body[0]["followups"]] == ["stats"]

    def test_status_filter_maps_pending_to_queued(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        enqueue(test_db, "import_connect", repository_id=repo.id, trigger="import")
        body = test_client.get(
            "/api/activity/recent?status=pending", headers=admin_headers
        ).json()
        assert [i["type"] for i in body] == ["import_connect"]

    def test_job_type_filter_matches_operation_kind(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        enqueue(test_db, "stats", repository_id=repo.id)
        enqueue(test_db, "archive_sync", repository_id=repo.id)
        body = test_client.get(
            "/api/activity/recent?job_type=stats&category=index", headers=admin_headers
        ).json()
        assert [i["type"] for i in body] == ["stats"]

    def test_trigger_filter_applies_to_legacy_rows(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        test_db.add(
            PruneJob(
                repository_id=repo.id,
                repository_path=repo.path,
                status="completed",
                started_at=utc_now(),
                scheduled_prune=True,
            )
        )
        test_db.add(
            PruneJob(
                repository_id=repo.id,
                repository_path=repo.path,
                status="completed",
                started_at=utc_now(),
            )
        )
        test_db.commit()
        body = test_client.get(
            "/api/activity/recent?trigger=schedule", headers=admin_headers
        ).json()
        assert len(body) == 1 and body[0]["trigger"] == "schedule"

    def test_logs_resolve_operation_kinds(
        self, test_client, test_db, admin_headers, tmp_path
    ):
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        log = tmp_path / "op.log"
        log.write_text("a\nb\n")
        op.log_file_path = str(log)
        test_db.commit()
        r = test_client.get(
            f"/api/activity/archive_sync/{op.id}/logs", headers=admin_headers
        )
        assert r.status_code == 200
        assert r.json()["lines"][0]["content"] == "a"
        r = test_client.get(
            f"/api/activity/archive_sync/{op.id}/logs/download", headers=admin_headers
        )
        assert r.status_code == 200
        assert b"b" in r.content

    def test_logs_unknown_operation_is_404(self, test_client, test_db, admin_headers):
        r = test_client.get(
            "/api/activity/archive_sync/999/logs", headers=admin_headers
        )
        assert r.status_code == 404

    def test_delete_operation_row_via_activity(
        self, test_client, test_db, admin_headers, tmp_path
    ):
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        op.status = "completed"
        log = tmp_path / "op.log"
        log.write_text("x\n")
        op.log_file_path = str(log)
        test_db.commit()
        r = test_client.delete(
            f"/api/activity/archive_sync/{op.id}", headers=admin_headers
        )
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert test_db.get(Operation, op.id) is None
        assert not log.exists()

    def test_delete_running_operation_refused(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        op.status = "running"
        test_db.commit()
        r = test_client.delete(
            f"/api/activity/archive_sync/{op.id}", headers=admin_headers
        )
        assert r.status_code == 400
