"""GET /api/activity/recent names the parents of its non-operation rows once
per source, and asks for a script execution's output only where the policy
needs it (#1119)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from app.database.models import (
    AvailabilityScheduleSkip,
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    Repository,
    ScheduledJob,
    Script,
    ScriptExecution,
    SystemSettings,
    UserRepositoryPermission,
)
from tests.utils.statements import count_statements

START = datetime(2026, 9, 1, 2, 0, 0)


def _set_log_save_policy(db, policy):
    settings = db.query(SystemSettings).first()
    if settings is None:
        settings = SystemSettings()
        db.add(settings)
    settings.log_save_policy = policy
    db.commit()


def _add_rows(db, start, stop, *, stdout="A f\nA g"):
    """One row per source and index, each with parents of its own: an
    availability plan skip, an automation skip, a failed plan run with no
    operation, and a completed script execution with output."""
    for i in range(start, stop):
        at = START + timedelta(hours=i)
        plan = BackupPlan(name=f"plan-{i}", enabled=True, source_directories="[]")
        schedule = ScheduledJob(name=f"schedule-{i}", cron_expression="0 2 * * *")
        repo = Repository(name=f"repo-{i}", path=f"/repos/{i}", encryption="none")
        script = Script(name=f"script-{i}", file_path=f"library/{i}.sh")
        db.add_all([plan, schedule, repo, script])
        db.flush()
        db.add_all(
            [
                BackupPlanRun(
                    backup_plan_id=plan.id,
                    trigger="availability",
                    status="skipped",
                    skip_reason="source_unavailable",
                    started_at=at,
                    completed_at=at,
                ),
                AvailabilityScheduleSkip(
                    scheduled_job_id=schedule.id,
                    reason="source_unavailable",
                    occurred_at=at + timedelta(minutes=1),
                ),
                BackupPlanRun(
                    backup_plan_id=plan.id,
                    trigger="schedule",
                    status="failed",
                    error_message="pre-backup hook failed",
                    started_at=at + timedelta(minutes=2),
                    completed_at=at + timedelta(minutes=3),
                ),
                ScriptExecution(
                    script_id=script.id,
                    repository_id=repo.id,
                    backup_plan_id=plan.id,
                    hook_type="pre-backup",
                    status="completed",
                    exit_code=0,
                    stdout=stdout,
                    started_at=at + timedelta(minutes=4),
                    completed_at=at + timedelta(minutes=5),
                ),
            ]
        )
    db.commit()


def _recent(test_client, test_db, headers):
    response, statements = count_statements(
        test_db,
        lambda: test_client.get("/api/activity/recent?limit=50", headers=headers),
    )
    return response.json(), statements


def _by_type(rows):
    out = {}
    for row in rows:
        out.setdefault(row["type"], []).append(row)
    return out


@pytest.mark.unit
@pytest.mark.parametrize("policy", ["failed_and_warnings", "all_jobs"])
def test_statement_count_does_not_grow_with_rows_per_source(
    test_client, test_db, admin_headers, policy
):
    _set_log_save_policy(test_db, policy)

    _add_rows(test_db, 0, 3)
    rows, three = _recent(test_client, test_db, admin_headers)
    assert {t: len(r) for t, r in _by_type(rows).items()} == {
        "availability_check": 6,
        "backup_plan_run": 3,
        "script_execution": 3,
    }

    _add_rows(test_db, 3, 12)
    rows, twelve = _recent(test_client, test_db, admin_headers)
    assert {t: len(r) for t, r in _by_type(rows).items()} == {
        "availability_check": 24,
        "backup_plan_run": 12,
        "script_execution": 12,
    }

    assert twelve == three


@pytest.mark.unit
def test_rows_keep_their_parents_names(test_client, test_db, admin_headers):
    _set_log_save_policy(test_db, "failed_and_warnings")
    _add_rows(test_db, 0, 2)

    rows, _ = _recent(test_client, test_db, admin_headers)
    by_type = _by_type(rows)

    skips = {row["activity_key"]: row for row in by_type["availability_check"]}
    plan_skips = [row for row in skips.values() if row["triggered_by"] == "backup_plan"]
    assert sorted(row["repository"] for row in plan_skips) == ["plan-0", "plan-1"]
    assert all(row["backup_plan_name"] == row["repository"] for row in plan_skips)
    automation_skips = [
        row for row in skips.values() if row["triggered_by"] == "schedule"
    ]
    assert sorted(row["repository"] for row in automation_skips) == [
        "schedule-0",
        "schedule-1",
    ]
    assert all(row["schedule_name"] == row["repository"] for row in automation_skips)
    failed = by_type["backup_plan_run"]
    assert sorted(row["repository"] for row in failed) == ["plan-0", "plan-1"]
    assert all(row["backup_plan_name"] == row["repository"] for row in failed)
    assert all(row["error_message"] == "pre-backup hook failed" for row in failed)
    scripts = by_type["script_execution"]
    assert sorted(row["package_name"] for row in scripts) == ["script-0", "script-1"]
    assert sorted(row["repository"] for row in scripts) == ["repo-0", "repo-1"]
    assert sorted(row["repository_path"] for row in scripts) == ["/repos/0", "/repos/1"]
    assert sorted(row["backup_plan_name"] for row in scripts) == ["plan-0", "plan-1"]


@pytest.mark.unit
def test_script_output_is_read_only_where_the_policy_needs_it(
    test_client, test_db, admin_headers
):
    """The list does not move every execution's output; under the default
    policy the database says which clean executions carry a marker, and the
    policy still refuses a pending one whatever its output says."""
    _set_log_save_policy(test_db, "failed_and_warnings")
    _add_rows(test_db, 0, 2)
    _add_rows(test_db, 2, 3, stdout="A f\nWARNING: x")
    _add_rows(test_db, 3, 4, stdout="A f\nerror: y")
    clean, marked, failed_marker = (
        test_db.query(ScriptExecution)
        .filter(ScriptExecution.script_id.in_(tuple(ids)))
        .all()
        for ids in (
            [1, 2],
            [3],
            [4],
        )
    )
    pending = clean[0]
    pending.status = "pending"
    pending.stdout = "Warning: from an earlier attempt"
    test_db.commit()

    statements = []
    engine = test_db.get_bind()

    def issued(conn, cursor, statement, parameters, context, executemany):
        if "FROM script_executions" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", issued)
    try:
        rows, _ = _recent(test_client, test_db, admin_headers)
    finally:
        event.remove(engine, "before_cursor_execute", issued)

    has_logs = {
        row["package_name"]: row["has_logs"]
        for row in rows
        if row["type"] == "script_execution"
    }
    assert has_logs == {
        "script-0": False,
        "script-1": False,
        "script-2": True,
        "script-3": True,
    }
    # No statement returns an output column; the marker search reads them
    # inside the database.
    assert statements
    assert not [
        s
        for s in statements
        if "script_executions.stdout AS" in s or "script_executions.stderr AS" in s
    ]


def _add_failed_runs(db, user, start, stop, *, granted=True):
    """One failed plan run per index, its plan linking two repositories of
    its own; the reader holds a viewer grant on them, or on neither."""
    for i in range(start, stop):
        at = START + timedelta(hours=i)
        plan = BackupPlan(name=f"plan-{i}", enabled=True, source_directories="[]")
        repos = [
            Repository(name=f"repo-{i}-{n}", path=f"/repos/{i}/{n}", encryption="none")
            for n in range(2)
        ]
        db.add_all([plan, *repos])
        db.flush()
        for n, repo in enumerate(repos):
            db.add(
                BackupPlanRepository(
                    backup_plan_id=plan.id, repository_id=repo.id, execution_order=n
                )
            )
            if granted:
                db.add(
                    UserRepositoryPermission(
                        user_id=user.id, repository_id=repo.id, role="viewer"
                    )
                )
        db.add(
            BackupPlanRun(
                backup_plan_id=plan.id,
                trigger="schedule",
                status="failed",
                error_message="pre-backup hook failed",
                started_at=at,
                completed_at=at + timedelta(minutes=1),
            )
        )
    db.commit()


@pytest.mark.unit
def test_a_non_admin_reader_costs_no_statement_per_plan_link(
    test_client, test_db, operator_user, operator_headers
):
    """A plan is visible to a non-admin only when they may view every
    repository it links. The rule reads the reader's grants once for the
    listed plans, and a plan linking a repository they were not granted
    stays hidden."""
    _add_failed_runs(test_db, operator_user, 0, 3)
    _add_failed_runs(test_db, operator_user, 100, 101, granted=False)
    rows, three = _recent(test_client, test_db, operator_headers)
    assert sorted(r["repository"] for r in rows if r["type"] == "backup_plan_run") == [
        "plan-0",
        "plan-1",
        "plan-2",
    ]

    _add_failed_runs(test_db, operator_user, 3, 12)
    rows, twelve = _recent(test_client, test_db, operator_headers)
    assert len([r for r in rows if r["type"] == "backup_plan_run"]) == 12

    assert twelve == three


@pytest.mark.unit
def test_a_wildcard_grant_costs_no_statement_per_plan_either(
    test_client, test_db, operator_user, operator_headers
):
    """A non-admin whose role covers all repositories has no permission
    rows to pre-filter by; the plans' links are still loaded with the
    plans, not one plan at a time."""
    operator_user.all_repositories_role = "viewer"
    test_db.commit()
    _add_failed_runs(test_db, operator_user, 0, 3, granted=False)
    rows, three = _recent(test_client, test_db, operator_headers)
    assert len([r for r in rows if r["type"] == "backup_plan_run"]) == 3

    _add_failed_runs(test_db, operator_user, 3, 12, granted=False)
    rows, twelve = _recent(test_client, test_db, operator_headers)
    assert len([r for r in rows if r["type"] == "backup_plan_run"]) == 12

    assert twelve == three
