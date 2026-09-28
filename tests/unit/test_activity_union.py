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
        """The before cursor exposes runs older than the first page."""
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
        """Create a plan run with the requested terminal state."""
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
        """A failed plan run remains visible when no operation explains it."""
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
        """A successful plan run relies on its member rows for activity."""
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
        """A failed backup row suppresses the less specific plan-run row."""
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

    def test_a_listed_failed_plan_run_can_be_deleted(
        self, test_client, test_db, admin_headers
    ):
        """The row the list offers a delete for answers that delete."""
        from app.database.models import BackupPlanRun, BackupPlanRunRepository

        _, run = self._plan_run(test_db)
        repo = _repo(test_db)
        test_db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id, repository_id=repo.id, status="failed"
            )
        )
        test_db.add(
            ScriptExecution(
                backup_plan_id=run.backup_plan_id,
                backup_plan_run_id=run.id,
                hook_type="pre-backup",
                status="failed",
                started_at=utc_now(),
            )
        )
        test_db.commit()
        run_id = run.id
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        row = next(i for i in body if i["type"] == "backup_plan_run")

        response = test_client.delete(
            f"/api/activity/{row['type']}/{row['id']}", headers=admin_headers
        )

        assert response.status_code == 200, response.json()
        test_db.expire_all()
        assert test_db.get(BackupPlanRun, run_id) is None
        assert (
            test_db.query(BackupPlanRunRepository)
            .filter(BackupPlanRunRepository.backup_plan_run_id == run_id)
            .count()
            == 0
        )
        assert (
            test_db.query(ScriptExecution)
            .filter(ScriptExecution.backup_plan_id == row["backup_plan_id"])
            .count()
            == 0
        )
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert body == []

    def test_deleting_a_plan_run_keeps_its_finished_backups(
        self, test_client, test_db, admin_headers
    ):
        """A run that failed after its backups succeeded is listed, and its
        delete leaves those backups in place, unlinked from the run."""
        from app.database.models import BackupPlanRun

        _, run = self._plan_run(test_db, error="post-backup hook failed")
        repo = _repo(test_db)
        op = enqueue(test_db, "backup", repository_id=repo.id)
        op.backup_plan_run_id = run.id
        op.status = "completed"
        op.started_at = utc_now()
        test_db.add(
            ScriptExecution(
                backup_plan_id=run.backup_plan_id,
                backup_plan_run_id=run.id,
                operation_id=op.id,
                repository_id=repo.id,
                hook_type="post-backup",
                status="completed",
                started_at=utc_now(),
            )
        )
        test_db.commit()
        run_id, op_id = run.id, op.id
        body = test_client.get("/api/activity/recent", headers=admin_headers).json()
        assert {i["type"] for i in body} == {"backup", "backup_plan_run"}

        response = test_client.delete(
            f"/api/activity/backup_plan_run/{run_id}", headers=admin_headers
        )

        assert response.status_code == 200, response.json()
        test_db.expire_all()
        assert test_db.get(BackupPlanRun, run_id) is None
        kept = test_db.get(Operation, op_id)
        assert kept is not None
        assert kept.backup_plan_run_id is None
        # The backup's own hook stays with the backup.
        hooks = (
            test_db.query(ScriptExecution)
            .filter(ScriptExecution.operation_id == op_id)
            .all()
        )
        assert [(h.hook_type, h.backup_plan_run_id) for h in hooks] == [
            ("post-backup", None)
        ]

    def test_a_hook_left_running_by_a_restart_does_not_hold_the_run(
        self, test_client, test_db, admin_headers
    ):
        """A restart fails the run but leaves its hook row running; the
        listed failure is still deletable."""
        from app.database.models import BackupPlanRun

        _, run = self._plan_run(test_db)
        test_db.add(
            ScriptExecution(
                backup_plan_id=run.backup_plan_id,
                backup_plan_run_id=run.id,
                hook_type="pre-backup",
                status="running",
                started_at=utc_now(),
            )
        )
        test_db.commit()
        run_id = run.id

        response = test_client.delete(
            f"/api/activity/backup_plan_run/{run_id}", headers=admin_headers
        )

        assert response.status_code == 200, response.json()
        test_db.expire_all()
        assert test_db.get(BackupPlanRun, run_id) is None
        assert test_db.query(ScriptExecution).count() == 0

    def test_a_plan_run_its_failed_backup_speaks_for_is_not_deleted_here(
        self, test_client, test_db, admin_headers
    ):
        """The list shows the failed backup instead of the run; the run goes
        with that backup, not through a row the list never offered."""
        from app.database.models import BackupPlanRun

        _, run = self._plan_run(test_db)
        repo = _repo(test_db)
        op = enqueue(test_db, "backup", repository_id=repo.id)
        op.backup_plan_run_id = run.id
        op.status = "failed"
        op.started_at = utc_now()
        test_db.commit()
        run_id = run.id

        response = test_client.delete(
            f"/api/activity/backup_plan_run/{run_id}", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.planRunHasFailedOperation"
        )
        test_db.expire_all()
        assert test_db.get(BackupPlanRun, run_id) is not None

    def test_a_plan_run_with_an_unfinished_operation_is_not_deleted(
        self, test_client, test_db, admin_headers
    ):
        """A run marked failed while one of its operations still waits keeps
        the run that operation will report to."""
        from app.database.models import BackupPlanRun

        _, run = self._plan_run(test_db)
        repo = _repo(test_db)
        op = enqueue(test_db, "backup", repository_id=repo.id)
        op.backup_plan_run_id = run.id
        test_db.commit()
        assert op.status == "queued"
        run_id = run.id

        response = test_client.delete(
            f"/api/activity/backup_plan_run/{run_id}", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.activity.cannotDeleteRunningJob"
        )
        test_db.expire_all()
        assert test_db.get(BackupPlanRun, run_id) is not None

    @pytest.mark.parametrize(
        "agent_job_status, expected", [("running", 400), ("completed", 200)]
    )
    def test_an_agent_hook_still_running_holds_the_run(
        self, test_client, test_db, admin_headers, agent_job_status, expected
    ):
        """An agent's hook job outlives a restart and reports to its row, so a
        run whose agent hook is still going stays; a finished one does not."""
        from app.database.models import AgentJob, AgentMachine, BackupPlanRun

        _, run = self._plan_run(test_db)
        machine = AgentMachine(
            agent_id="agent-hook",
            name="agent-hook",
            token_hash="hash",
            token_prefix="prefix",
        )
        test_db.add(machine)
        test_db.flush()
        agent_job = AgentJob(
            agent_machine_id=machine.id,
            job_type="script",
            status=agent_job_status,
            payload={},
        )
        test_db.add(agent_job)
        test_db.flush()
        test_db.add(
            ScriptExecution(
                backup_plan_id=run.backup_plan_id,
                backup_plan_run_id=run.id,
                agent_job_id=agent_job.id,
                hook_type="pre-backup",
                status="running",
                started_at=utc_now(),
            )
        )
        test_db.commit()
        run_id = run.id

        response = test_client.delete(
            f"/api/activity/backup_plan_run/{run_id}", headers=admin_headers
        )

        assert response.status_code == expected, response.json()
        test_db.expire_all()
        assert (test_db.get(BackupPlanRun, run_id) is None) == (expected == 200)

    @pytest.mark.parametrize("status", ["completed", "running"])
    def test_a_plan_run_the_list_does_not_show_is_not_found(
        self, test_client, test_db, admin_headers, status
    ):
        """Only the failed run the list emits as a row is deletable here."""
        from app.database.models import BackupPlanRun

        _, run = self._plan_run(test_db, status=status, error=None)
        run_id = run.id

        response = test_client.delete(
            f"/api/activity/backup_plan_run/{run_id}", headers=admin_headers
        )

        assert response.status_code == 404
        test_db.expire_all()
        assert test_db.get(BackupPlanRun, run_id) is not None

    def test_a_plan_run_is_deleted_by_admins_only(
        self, test_client, test_db, auth_headers
    ):
        """The same gate as every other delete on the list."""
        from app.database.models import BackupPlanRun

        _, run = self._plan_run(test_db)
        run_id = run.id

        response = test_client.delete(
            f"/api/activity/backup_plan_run/{run_id}", headers=auth_headers
        )

        assert response.status_code == 403
        test_db.expire_all()
        assert test_db.get(BackupPlanRun, run_id) is not None


@pytest.mark.unit
class TestPlanRunBookkeeping:
    def test_a_locked_write_is_run_again_whole(self):
        """A locked write replays its mutation in a new session."""
        from sqlalchemy.exc import OperationalError

        from app.services import backup_plan_execution_service as svc

        sessions = []

        class FakeSession:
            def __init__(self):
                """Track the lifecycle of one bookkeeping attempt."""
                self.committed = False
                self.rolled_back = False
                self.closed = False
                sessions.append(self)

            def commit(self):
                """Record that this attempt reached its commit."""
                self.committed = True

            def rollback(self):
                """Record that this attempt was rolled back."""
                self.rolled_back = True

            def close(self):
                """Record that this attempt released its session."""
                self.closed = True

        ran = []

        def work(db):
            """Raise lock errors until the third mutation attempt."""
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
        """A non-lock database error escapes without a retry."""
        from sqlalchemy.exc import OperationalError

        from app.services import backup_plan_execution_service as svc

        class FakeSession:
            def commit(self):
                """Model a successful commit for the fake session."""
                pass

            def rollback(self):
                """Model a rollback for the fake session."""
                pass

            def close(self):
                """Model closing the fake session."""
                pass

        ran = []

        def work(db):
            """Raise a database error that is unrelated to locking."""
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
