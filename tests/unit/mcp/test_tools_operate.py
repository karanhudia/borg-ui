"""Operate tools: backups, plans, schedules, cancel and retry (phase 3, Tasks 3 and 4).

Tools that would start real Borg work run against canned route answers
(`StubApi`); refusals that the app itself gives run against the seeded app.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.mcp.client import ApiError
from tests.unit.mcp.test_tools_stubbed import run

V1 = {"id": 1, "name": "Photos", "path": "/data/example/photos", "borg_version": 1}
V2 = {"id": 2, "name": "Media", "path": "/data/example/media", "borg_version": 2}
REPOS = {"/api/repositories/": {"repositories": [V1, V2]}}
STARTED = {
    "job_id": 412,
    "status": "pending",
    "message": "backend.success.backup.started",
}


def _done(minutes, **extra):
    start = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)
    return {
        "id": 1,
        "type": "backup",
        "status": "completed",
        "started_at": start.isoformat(),
        "completed_at": (start + timedelta(minutes=minutes)).isoformat(),
        **extra,
    }


def _feed(*rows):
    return {"/api/activity/recent": list(rows)}


@pytest.mark.unit
def test_start_backup_borg1_posts_path():
    routes = {**REPOS, **_feed(), "POST /api/backup/start": STARTED}
    result, api = run("start_backup", routes, repository="Photos")
    assert api.posts == [("/api/backup/start", {"repository": "/data/example/photos"})]
    assert result.text.startswith("⏳ Backup of *Photos* started (backup 412).")
    assert result.data["job_type"] == "backup" and result.data["job_id"] == 412


@pytest.mark.unit
def test_start_backup_borg2_posts_id():
    routes = {**REPOS, **_feed(), "POST /api/v2/backup/run": STARTED}
    _, api = run("start_backup", routes, repository="Media")
    assert api.posts == [("/api/v2/backup/run", {"repository_id": 2})]


@pytest.mark.unit
def test_start_backup_answer_has_estimate():
    routes = {**REPOS, **_feed(_done(5), _done(7)), "POST /api/backup/start": STARTED}
    result, api = run("start_backup", routes, repository="Photos")
    assert "Usually takes ~6 min." in result.text
    assert result.text.rstrip().endswith("Want me to wait for it?")
    feed = [params for path, params in api.calls if path == "/api/activity/recent"]
    assert feed[0]["repository_id"] == 1 and feed[0]["status"] == "completed"


@pytest.mark.unit
def test_start_backup_one_prior_run_gives_no_estimate():
    routes = {**REPOS, **_feed(_done(5)), "POST /api/backup/start": STARTED}
    result, _ = run("start_backup", routes, repository="Photos")
    assert "Usually" not in result.text


@pytest.mark.unit
def test_operate_tools_are_not_read_only():
    from app.mcp.registry import REGISTRY

    spec = REGISTRY["start_backup"]
    assert spec.level.label == "operate"
    assert not spec.read_only and not spec.idempotent and not spec.destructive


@pytest.mark.unit
def test_viewer_cannot_start_backup(
    mcp, create_connection, auth_headers, test_user, seeded, test_db
):
    """Spec 5.2 rule 2: an operate connection never exceeds its user. The
    viewer may see *Photos*, so the refusal is the route's own role check."""
    from app.database.models import McpActivity, UserRepositoryPermission

    test_db.add(
        UserRepositoryPermission(
            user_id=test_user.id, repository_id=seeded["photos"].id, role="viewer"
        )
    )
    test_db.commit()
    _, token = create_connection(auth_headers, name="viewer", level="operate")
    result = mcp(token).call("start_backup", repository="Photos")
    assert result["is_error"]
    assert "Traceback" not in result["text"]
    row = test_db.query(McpActivity).order_by(McpActivity.id.desc()).first()
    assert (row.tool, row.outcome) == ("start_backup", "denied_rbac")


@pytest.mark.unit
def test_read_connection_does_not_see_start_backup(admin_mcp):
    assert "start_backup" not in {t["name"] for t in admin_mcp.list_tools()}
    refused = admin_mcp.call("start_backup", repository="Photos")
    assert refused["is_error"]
    assert "needs operate" in refused["text"]


PLAN = {
    "id": 5,
    "name": "Nightly",
    "repositories": [{"repository_id": 1, "repository": {"name": "Photos"}}],
}


@pytest.mark.unit
def test_run_backup_plan_by_name():
    routes = {
        "/api/backup-plans/": {
            "backup_plans": [PLAN, {**PLAN, "id": 6, "name": "Weekly"}]
        },
        **_feed(),
        "POST /api/backup-plans/5/run": {"id": 88, "status": "pending"},
    }
    result, api = run("run_backup_plan", routes, backup_plan="nightly")
    assert api.posts == [("/api/backup-plans/5/run", None)]
    assert result.text.startswith("⏳ *Nightly* started (backup_plan_run 88).")
    assert result.data["job_type"] == "backup_plan_run" and result.data["job_id"] == 88


@pytest.mark.unit
def test_run_backup_plan_ambiguous_asks():
    routes = {
        "/api/backup-plans/": {
            "backup_plans": [PLAN, {**PLAN, "id": 6, "name": "Nightly old"}]
        },
    }
    with pytest.raises(Exception) as caught:
        run("run_backup_plan", routes, backup_plan="Night")
    assert "Which one?" in getattr(caught.value, "text", str(caught.value))


@pytest.mark.unit
def test_run_schedule_now_single_repository():
    routes = {
        "/api/schedule/": {"jobs": [{"id": 3, "name": "Photos nightly"}]},
        "POST /api/schedule/3/run-now": {
            "message": "backend.success.schedule.scheduledJobStarted",
            "job_id": 501,
        },
    }
    result, api = run("run_schedule_now", routes, schedule="Photos nightly")
    assert api.posts == [("/api/schedule/3/run-now", None)]
    assert result.text.startswith("⏳ *Photos nightly* started (backup 501).")
    assert result.data["job_id"] == 501


@pytest.mark.unit
def test_run_schedule_now_multi_repository():
    routes = {
        "/api/schedule/": {"jobs": [{"id": 3, "name": "Everything"}]},
        "POST /api/schedule/3/run-now": {
            "message": "backend.success.schedule.scheduledJobStartedMulti"
        },
    }
    result, _ = run("run_schedule_now", routes, schedule="Everything")
    assert result.text.startswith("⏳ *Everything* started.")
    assert "list_running_jobs" in result.text


@pytest.mark.unit
def test_start_refusal_is_friendly():
    routes = {
        **REPOS,
        **_feed(),
        "POST /api/backup/start": ApiError(409, "backend.errors.backup.alreadyRunning"),
    }
    with pytest.raises(ApiError):
        run("start_backup", routes, repository="Photos")


# Task 4: cancel and retry


@pytest.mark.unit
def test_cancel_job_uses_the_activity_route():
    routes = {"POST /api/activity/check/9/cancel": {"cancelled": True}}
    result, api = run("cancel_job", routes, job_type="check", job_id=9)
    assert api.posts == [("/api/activity/check/9/cancel", None)]
    assert result.text.startswith("✓ Asked check 9 to stop.")


@pytest.mark.unit
def test_cancel_plan_run_uses_the_plan_route():
    routes = {
        "POST /api/backup-plans/runs/88/cancel": {"id": 88, "status": "cancelled"}
    }
    _, api = run("cancel_job", routes, job_type="backup_plan_run", job_id=88)
    assert api.posts == [("/api/backup-plans/runs/88/cancel", None)]


@pytest.mark.unit
def test_cancel_finished_job_is_friendly(mcp, create_connection, admin_headers, seeded):
    _, token = create_connection(admin_headers, name="ops", level="operate")
    result = mcp(token).call(
        "cancel_job", job_type="backup", job_id=seeded["failed"].id
    )
    assert result["is_error"]
    assert "no Borg UI tool" not in result["text"]
    assert "Something went wrong" not in result["text"]
    assert "finished" in result["text"].lower()


@pytest.mark.unit
def test_retry_failed_backup_returns_new_job():
    routes = {"POST /api/backup/jobs/412/retry": {"job_id": 413, "status": "pending"}}
    result, api = run("retry_job", routes, job_type="backup", job_id=412)
    assert api.posts == [("/api/backup/jobs/412/retry", None)]
    assert result.text.startswith("⏳ Retry of backup 412 started (backup 413).")
    assert result.data["job_id"] == 413


@pytest.mark.unit
def test_retry_plan_run():
    routes = {"POST /api/backup-plans/runs/88/retry": {"id": 90, "status": "pending"}}
    result, _ = run("retry_job", routes, job_type="backup_plan_run", job_id=88)
    assert result.data == {
        "job_type": "backup_plan_run",
        "job_id": 90,
        "estimate_seconds": None,
    }


@pytest.mark.unit
def test_retry_check_is_refused_with_a_pointer():
    result, api = run("retry_job", {}, job_type="check", job_id=9)
    assert result.is_error and api.posts == []
    assert "Only backups and plan runs can be retried" in result.text
    assert "check_repository" in result.text


# Review fixes


@pytest.mark.unit
def test_failed_estimate_still_reports_the_started_job():
    """The start went through; a failed history lookup must not turn that
    into an error the AI would answer by starting it again."""
    routes = {
        **REPOS,
        "/api/activity/recent": lambda params: (_ for _ in ()).throw(ApiError(500)),
        "POST /api/backup/start": STARTED,
    }
    result, _ = run("start_backup", routes, repository="Photos")
    assert not result.is_error
    assert result.text.startswith("⏳ Backup of *Photos* started (backup 412).")
    assert "Usually" not in result.text


@pytest.mark.unit
def test_estimate_timeout_still_reports_the_started_job():
    import httpx

    def slow(params):
        raise httpx.ReadTimeout("slow")

    routes = {**REPOS, "/api/activity/recent": slow, "POST /api/backup/start": STARTED}
    result, _ = run("start_backup", routes, repository="Photos")
    assert not result.is_error and result.data["job_id"] == 412


@pytest.mark.unit
def test_cancel_job_type_cannot_change_the_route():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        run("cancel_job", {}, job_type="../repositories/1/prune#", job_id=9)
