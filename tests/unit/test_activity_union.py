from datetime import timedelta

import pytest

from app.database.models import (
    Operation,
    Repository,
    ScriptExecution,
    UserRepositoryPermission,
    utc_now,
)
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

    def test_two_operations_ordered_by_time(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        old = enqueue(test_db, "prune", repository_id=repo.id)
        old.status = "completed"
        old.started_at = utc_now() - timedelta(hours=2)
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

    def test_collapse_runs_folds_a_reconcile_chain_into_one_row(
        self, test_client, test_db, admin_headers
    ):
        """A reconcile enqueues four index operations in one run. They are
        one row with three steps under it, not four rows an hour."""
        repo = _repo(test_db)
        chain = enqueue_chain(
            test_db,
            ["archive_sync", "history_merge", "history_index", "stats"],
            repository_id=repo.id,
            trigger="reconcile",
        )
        for op in chain:
            op.status = "completed"
            op.started_at = utc_now()
        test_db.commit()
        body = test_client.get(
            "/api/activity/recent?category=index", headers=admin_headers
        ).json()
        assert [i["id"] for i in body] == [chain[0].id]
        assert body[0]["type"] == "archive_sync"
        assert [f["kind"] for f in body[0]["followups"]] == [
            "history_merge",
            "history_index",
            "stats",
        ]

    def test_collapse_runs_keeps_separate_runs_apart(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        first = enqueue_chain(
            test_db,
            ["archive_sync", "stats"],
            repository_id=repo.id,
            trigger="reconcile",
        )
        second = enqueue_chain(
            test_db,
            ["archive_sync", "stats"],
            repository_id=repo.id,
            trigger="reconcile",
        )
        body = test_client.get(
            "/api/activity/recent?category=index", headers=admin_headers
        ).json()
        assert {i["id"] for i in body} == {first[0].id, second[0].id}
        assert all(len(i["followups"]) == 1 for i in body)

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

    def test_trigger_filter_applies_to_every_source(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        scheduled = enqueue(test_db, "prune", repository_id=repo.id, trigger="schedule")
        scheduled.status = "completed"
        scheduled.started_at = utc_now()
        manual = enqueue(test_db, "prune", repository_id=repo.id)
        manual.status = "completed"
        manual.started_at = utc_now()
        test_db.commit()
        body = test_client.get(
            "/api/activity/recent?trigger=schedule", headers=admin_headers
        ).json()
        assert len(body) == 1 and body[0]["trigger"] == "schedule"

    def test_recent_hides_operations_for_inaccessible_repositories(
        self, test_client, test_db, test_user, auth_headers
    ):
        """A viewer granted one repository must not see another's operations."""
        allowed = _repo(test_db)
        denied = Repository(
            name="denied", path="/tmp/denied", encryption="none", compression="lz4"
        )
        test_db.add(denied)
        test_db.commit()
        test_db.refresh(denied)
        test_db.add(
            UserRepositoryPermission(
                user_id=test_user.id, repository_id=allowed.id, role="viewer"
            )
        )
        test_db.commit()
        enqueue(test_db, "import_connect", repository_id=allowed.id, trigger="import")
        enqueue(test_db, "import_connect", repository_id=denied.id, trigger="import")

        body = test_client.get("/api/activity/recent", headers=auth_headers).json()
        repo_ids = {item.get("repository_id") for item in body}
        assert denied.id not in repo_ids
        assert allowed.id in repo_ids

    def test_logs_resolve_operation_kinds(
        self, test_client, test_db, admin_headers, tmp_path
    ):
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        log = tmp_path / "op.log"
        log.write_text("a\nb\n")
        op.log_file_path = str(log)
        # A queued op has no visible logs under the log-save policy; use a
        # finished status so the policy check in the logs/download routes
        # allows reading them.
        op.status = "completed_with_warnings"
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

    def test_download_honours_the_log_visibility_policy(
        self, test_client, test_db, admin_headers, tmp_path
    ):
        """The download route must not serve what the logs route hides, or the
        policy is only advisory."""
        repo = _repo(test_db)
        op = enqueue(test_db, "archive_sync", repository_id=repo.id)
        log = tmp_path / "queued.log"
        log.write_text("secret\n")
        op.log_file_path = str(log)
        op.status = "queued"
        test_db.commit()
        assert (
            test_client.get(
                f"/api/activity/archive_sync/{op.id}/logs", headers=admin_headers
            ).status_code
            == 404
        )
        assert (
            test_client.get(
                f"/api/activity/archive_sync/{op.id}/logs/download",
                headers=admin_headers,
            ).status_code
            == 404
        )

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

    def test_repository_id_filters_every_source(
        self, test_client, test_db, admin_headers
    ):
        """A repository's own Activity must not depend on how much other work
        the install did meanwhile: the filter runs in SQL, per source, before
        each source's limit."""
        mine = _repo(test_db)
        other = Repository(
            name="other", path="/tmp/other", encryption="none", compression="lz4"
        )
        test_db.add(other)
        test_db.commit()
        test_db.refresh(other)

        old = enqueue(test_db, "prune", repository_id=mine.id)
        old.status = "completed"
        old.started_at = utc_now() - timedelta(hours=5)
        test_db.commit()
        mine_op = enqueue(test_db, "import_connect", repository_id=mine.id)
        mine_op.status = "completed"
        mine_op.started_at = utc_now() - timedelta(hours=4)
        test_db.commit()

        # Newer work on another repository, which would crowd the shared
        # window out on a busy install.
        for _ in range(5):
            noise = enqueue(test_db, "import_connect", repository_id=other.id)
            noise.status = "completed"
            noise.started_at = utc_now()
            test_db.commit()

        body = test_client.get(
            f"/api/activity/recent?repository_id={mine.id}&limit=3",
            headers=admin_headers,
        ).json()
        assert [i["type"] for i in body] == ["import_connect", "prune"]
        assert {i["repository"] for i in body} == {"r"}

    def test_repository_id_keeps_that_repository_script_executions(
        self, test_client, test_db, admin_headers
    ):
        """A script execution names its repository, so the repository's own
        Activity keeps the hooks that ran against it."""
        mine = _repo(test_db)
        other = Repository(
            name="other", path="/tmp/other", encryption="none", compression="lz4"
        )
        test_db.add(other)
        test_db.commit()
        test_db.refresh(other)

        test_db.add_all(
            [
                ScriptExecution(
                    repository_id=mine.id,
                    agent_script_name="pre-backup.sh",
                    hook_type="pre-backup",
                    status="completed",
                    started_at=utc_now(),
                ),
                ScriptExecution(
                    repository_id=other.id,
                    agent_script_name="other.sh",
                    hook_type="pre-backup",
                    status="completed",
                    started_at=utc_now(),
                ),
                ScriptExecution(
                    agent_script_name="standalone.sh",
                    hook_type="standalone",
                    status="completed",
                    started_at=utc_now(),
                ),
            ]
        )
        test_db.commit()

        body = test_client.get(
            f"/api/activity/recent?repository_id={mine.id}", headers=admin_headers
        ).json()
        scripts = [i for i in body if i["type"] == "script_execution"]
        assert len(scripts) == 1
        assert scripts[0]["repository"] == "r"

    def test_repository_id_drops_rows_with_no_repository(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        enqueue(test_db, "package_install")
        op = enqueue(test_db, "import_connect", repository_id=repo.id)
        op.status = "completed"
        test_db.commit()
        body = test_client.get(
            f"/api/activity/recent?repository_id={repo.id}", headers=admin_headers
        ).json()
        assert [i["type"] for i in body] == ["import_connect"]

    def test_repository_id_unknown_repository_is_empty(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        enqueue(test_db, "import_connect", repository_id=repo.id)
        body = test_client.get(
            "/api/activity/recent?repository_id=99999", headers=admin_headers
        ).json()
        assert body == []


@pytest.mark.unit
class TestActivityPagination:
    def test_before_cursor_pages_into_older_runs(
        self, test_client, test_db, admin_headers
    ):
        repo = _repo(test_db)
        for hours in (1, 2, 3):
            op = enqueue(test_db, "prune", repository_id=repo.id)
            op.status = "completed"
            op.started_at = utc_now() - timedelta(hours=hours)
            test_db.commit()

        page = test_client.get(
            "/api/activity/recent?limit=2", headers=admin_headers
        ).json()
        assert len(page) == 2
        # `Z`, like the client: a query string reads `+00:00` back as a space.
        cursor = page[-1]["sort_at"].replace("+00:00", "Z")

        older = test_client.get(
            f"/api/activity/recent?limit=2&before={cursor}", headers=admin_headers
        ).json()
        # Inclusive, so the row the page ended on comes back with the one
        # after it; the client drops what it has already shown.
        keys = [i["activity_key"] for i in page] + [i["activity_key"] for i in older]
        assert len(set(keys)) == 3

    def test_rows_sharing_one_timestamp_are_not_stranded(
        self, test_client, test_db, admin_headers
    ):
        """A page that ends inside a group of equal timestamps must not lose
        the rest of that group: every one of them is reachable by paging."""
        repo = _repo(test_db)
        shared = utc_now() - timedelta(hours=1)
        for _ in range(4):
            op = enqueue(test_db, "prune", repository_id=repo.id)
            op.status = "completed"
            op.started_at = shared
            test_db.commit()

        seen: set[str] = set()
        cursor = None
        for _ in range(6):
            url = "/api/activity/recent?limit=2"
            if cursor:
                url += f"&before={cursor}"
            page = test_client.get(url, headers=admin_headers).json()
            fresh = [i for i in page if i["activity_key"] not in seen]
            seen.update(i["activity_key"] for i in page)
            # The client stops when a page brings nothing new, which is what
            # keeps an inclusive cursor from asking for the same second twice.
            if len(page) < 2 or not fresh:
                break
            cursor = page[-1]["sort_at"].replace("+00:00", "Z")
        assert len(seen) == 4


@pytest.mark.unit
class TestFailedPlanRuns:
    def _plan_run(self, test_db, status="failed", error="boom"):
        from app.database.models import BackupPlan, BackupPlanRun

        plan = BackupPlan(name="nightly", enabled=True, source_directories="[]")
        test_db.add(plan)
        test_db.commit()
        run = BackupPlanRun(
            backup_plan_id=plan.id,
            status=status,
            trigger="schedule",
            started_at=utc_now(),
            completed_at=utc_now(),
            error_message=error,
        )
        test_db.add(run)
        test_db.commit()
        return plan, run

    def test_failed_plan_run_with_no_operations_is_listed(
        self, test_client, test_db, admin_headers
    ):
        plan, run = self._plan_run(test_db)
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert [i["type"] for i in body] == ["backup_plan_run"]
        assert body[0]["status"] == "failed"
        assert body[0]["error_message"] == "boom"
        assert body[0]["repository"] == plan.name
        assert body[0]["trigger"] == "plan"

    def test_a_clean_plan_run_gets_no_row_of_its_own(
        self, test_client, test_db, admin_headers
    ):
        from app.database.models import ScriptExecution

        _, run = self._plan_run(test_db, status="completed", error=None)
        test_db.add(
            ScriptExecution(
                backup_plan_id=run.backup_plan_id,
                backup_plan_run_id=run.id,
                hook_type="pre-backup",
                status="completed",
                started_at=utc_now(),
            )
        )
        test_db.commit()
        # The band names the run already; its plan-level hooks hang from
        # there, so the feed returns the hook and no run row beside it.
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert [i["type"] for i in body] == ["script_execution"]
        assert body[0]["backup_plan_run_id"] == run.id

    def test_a_failed_plan_run_is_hidden_from_a_viewer_of_only_one_repository(
        self, test_client, test_db, test_user, auth_headers
    ):
        """The row names the plan and carries its error, and a plan spans
        repositories: a viewer of one of them may not read it."""
        from app.database.models import BackupPlanRepository

        _, run = self._plan_run(test_db, error="ssh key rejected")
        allowed = _repo(test_db)
        denied = Repository(
            name="denied", path="/tmp/denied", encryption="none", compression="lz4"
        )
        test_db.add(denied)
        test_db.commit()
        test_db.refresh(denied)
        for repo in (allowed, denied):
            test_db.add(
                BackupPlanRepository(
                    backup_plan_id=run.backup_plan_id,
                    repository_id=repo.id,
                    execution_order=repo.id,
                )
            )
        test_db.add(
            UserRepositoryPermission(
                user_id=test_user.id, repository_id=allowed.id, role="viewer"
            )
        )
        test_db.commit()

        body = test_client.get("/api/activity/recent", headers=auth_headers).json()
        assert body == []
        # The same run is there for someone who may see both repositories.
        test_db.add(
            UserRepositoryPermission(
                user_id=test_user.id, repository_id=denied.id, role="viewer"
            )
        )
        test_db.commit()
        body = test_client.get("/api/activity/recent", headers=auth_headers).json()
        assert [i["type"] for i in body] == ["backup_plan_run"]
        assert body[0]["error_message"] == "ssh key rejected"

    def test_failed_plan_run_is_silent_when_its_own_run_failed(
        self, test_client, test_db, admin_headers
    ):
        _, run = self._plan_run(test_db)
        repo = _repo(test_db)
        op = enqueue(test_db, "backup", repository_id=repo.id)
        op.backup_plan_run_id = run.id
        op.status = "failed"
        op.started_at = utc_now()
        test_db.commit()
        # The backup says it failed, in the same band and with more detail.
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert [i["type"] for i in body] == ["backup"]


@pytest.mark.unit
class TestPlanRunBookkeeping:
    def test_a_locked_write_is_run_again_whole(self):
        from sqlalchemy.exc import OperationalError

        from app.services import backup_plan_execution_service as svc

        sessions = []

        class FakeSession:
            def __init__(self):
                self.committed = False
                self.rolled_back = False
                self.closed = False
                sessions.append(self)

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

            def close(self):
                self.closed = True

        ran = []

        def work(db):
            ran.append(db)
            # The mutation itself is what the lock hits, on the flush the
            # commit drives. Retrying the commit alone would replay nothing.
            if len(ran) < 3:
                raise OperationalError("UPDATE", {}, Exception("database is locked"))

        monkeypatched = svc.SessionLocal
        svc.SessionLocal = FakeSession
        try:
            svc._write_bookkeeping(work, delay=0)
        finally:
            svc.SessionLocal = monkeypatched

        # Three attempts, each reading and mutating again in its own session.
        assert len(ran) == 3
        assert [s.committed for s in sessions] == [False, False, True]
        assert all(s.closed for s in sessions)

    def test_a_terminal_child_is_not_moved_back(self, test_db):
        """A worker deciding to skip a repository must not overwrite the
        cancellation someone committed while it was deciding."""
        from app.database.models import (
            BackupPlan,
            BackupPlanRun,
            BackupPlanRunRepository,
        )
        from app.services.backup_plan_execution_service import _update_children

        plan = BackupPlan(name="nightly", enabled=True, source_directories="[]")
        test_db.add(plan)
        test_db.commit()
        run = BackupPlanRun(backup_plan_id=plan.id, status="running", trigger="manual")
        test_db.add(run)
        test_db.commit()
        repo = _repo(test_db)
        child = BackupPlanRunRepository(
            backup_plan_run_id=run.id, repository_id=repo.id, status="cancelled"
        )
        pending = BackupPlanRunRepository(
            backup_plan_run_id=run.id, repository_id=None, status="pending"
        )
        test_db.add_all([child, pending])
        test_db.commit()

        _update_children(test_db, run.id, {"status": "skipped"})
        test_db.commit()
        test_db.refresh(child)
        test_db.refresh(pending)
        assert child.status == "cancelled"
        assert pending.status == "skipped"

    def test_other_errors_are_not_retried(self):
        from sqlalchemy.exc import OperationalError

        from app.services import backup_plan_execution_service as svc

        class FakeSession:
            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        ran = []

        def work(db):
            ran.append(db)
            raise OperationalError("UPDATE", {}, Exception("no such table"))

        monkeypatched = svc.SessionLocal
        svc.SessionLocal = FakeSession
        try:
            with pytest.raises(OperationalError):
                svc._write_bookkeeping(work, delay=0)
        finally:
            svc.SessionLocal = monkeypatched
        assert len(ran) == 1
