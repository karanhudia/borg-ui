# Backup Report Period Windows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated backup report activity match the configured daily, weekly, or monthly report period.

**Architecture:** Keep the existing monitoring/report service boundary. Add a deterministic period-start helper in `app/services/backup_monitoring_service.py`, update `build_backup_report()` to use it, and cover the behavior with focused pytest tests.

**Tech Stack:** Python, FastAPI service layer, SQLAlchemy models, pytest.

---

### Task 1: Reproduce the Fixed Seven-Day Report Gap

**Files:**
- Modify: `tests/unit/test_backup_monitoring_service.py`

- [ ] Add a failing test named `test_build_backup_report_uses_daily_activity_window`.

```python
@pytest.mark.unit
def test_build_backup_report_uses_daily_activity_window(db_session):
    now = datetime(2026, 5, 20, 8, 30, tzinfo=timezone.utc)
    settings = SystemSettings(
        backup_reports_frequency="daily",
        backup_reports_include_summary=False,
        backup_reports_include_stale_repositories=False,
        backup_reports_include_recent_activity=True,
    )
    db_session.add(settings)
    db_session.add_all(
        [
            BackupJob(
                repository="/repos/recent",
                status="completed",
                started_at=now - timedelta(hours=3),
                completed_at=now - timedelta(hours=2),
            ),
            BackupJob(
                repository="/repos/old",
                status="completed",
                started_at=now - timedelta(days=2),
                completed_at=now - timedelta(days=2) + timedelta(hours=1),
            ),
        ]
    )
    db_session.commit()

    report = build_backup_report(db_session, settings, now)

    assert report.recent_backup_count == 1
    assert "/repos/recent" in report.body
    assert "/repos/old" not in report.body
    assert "Activity window:" in report.body
```

- [ ] Run `pytest tests/unit/test_backup_monitoring_service.py::test_build_backup_report_uses_daily_activity_window -q`.
- [ ] Confirm it fails because the current implementation includes the two-day-old job.

### Task 2: Implement Period-Aware Report Windows

**Files:**
- Modify: `app/services/backup_monitoring_service.py`
- Modify: `tests/unit/test_backup_monitoring_service.py`

- [ ] Add a helper called `_report_activity_period_start(settings: SystemSettings, now: datetime) -> datetime`.
- [ ] Use `timedelta(days=1)` for daily and `timedelta(days=7)` for weekly.
- [ ] For monthly, compute the previous month with `calendar.monthrange()` and clamp the day to the previous month's maximum day.
- [ ] Update `build_backup_report()` to query jobs from `period_start` and include an `Activity window: <start> to <end>` line under the recent activity heading.
- [ ] Add a monthly regression test proving a job just inside the monthly period is included and one just outside is excluded.
- [ ] Run `pytest tests/unit/test_backup_monitoring_service.py -q`.

### Task 3: Validate and Handoff

**Files:**
- No additional files expected.

- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run an app/API-level proof for manual report generation.
- [ ] Update the Linear workpad with validation evidence.
- [ ] Commit, push, open/update the PR with `.github/PULL_REQUEST_TEMPLATE.md`, add `symphony`, run PR feedback sweep, and move BOR-49 to Human Review only when checks are green.
