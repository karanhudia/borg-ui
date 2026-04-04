from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.models import BackupJob, Repository, ScheduledJob, ScheduledJobRepository


def _create_repo(test_db, name: str, path: str) -> Repository:
    repo = Repository(name=name, path=path, encryption="none", repository_type="local", mode="full")
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _create_schedule(test_db, name: str, cron_expression: str = "0 2 * * *", **kwargs) -> ScheduledJob:
    schedule = ScheduledJob(name=name, cron_expression=cron_expression, enabled=True, **kwargs)
    test_db.add(schedule)
    test_db.commit()
    test_db.refresh(schedule)
    return schedule


@pytest.mark.unit
class TestScheduleRouteContracts:
    def test_list_schedules_includes_deduped_repository_ids(self, test_client: TestClient, admin_headers, test_db):
        repo_a = _create_repo(test_db, "Repo A", "/repos/a")
        repo_b = _create_repo(test_db, "Repo B", "/repos/b")
        schedule = _create_schedule(test_db, "Nightly")
        test_db.add_all(
            [
                ScheduledJobRepository(scheduled_job_id=schedule.id, repository_id=repo_b.id, execution_order=0),
                ScheduledJobRepository(scheduled_job_id=schedule.id, repository_id=repo_a.id, execution_order=1),
            ]
        )
        test_db.commit()

        response = test_client.get("/api/schedule/", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        job = next(item for item in body["jobs"] if item["id"] == schedule.id)
        assert job["repository_ids"] == [repo_b.id, repo_a.id]

    def test_upcoming_jobs_returns_enabled_jobs_sorted_and_filtered(
        self, test_client: TestClient, admin_headers, test_db
    ):
        soon = _create_schedule(test_db, "Soon", cron_expression="*/15 * * * *", repository="/repos/a")
        _create_schedule(test_db, "Tomorrow", cron_expression="0 0 * * *", repository="/repos/b")
        disabled = _create_schedule(test_db, "Disabled", cron_expression="*/10 * * * *", repository="/repos/c")
        disabled.enabled = False
        test_db.commit()

        response = test_client.get("/api/schedule/upcoming-jobs?hours=1", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        names = [job["name"] for job in body["upcoming_jobs"]]
        assert "Soon" in names
        assert "Tomorrow" not in names
        assert "Disabled" not in names
        assert body["upcoming_jobs"] == sorted(body["upcoming_jobs"], key=lambda item: item["next_run"])
        assert any(job["id"] == soon.id for job in body["upcoming_jobs"])

    def test_update_schedule_rejects_duplicate_name(self, test_client: TestClient, admin_headers, test_db):
        existing = _create_schedule(test_db, "Existing", repository="/repos/existing")
        target = _create_schedule(test_db, "Target", repository="/repos/target")

        response = test_client.put(
            f"/api/schedule/{target.id}",
            json={"name": existing.name},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.schedule.jobNameExists"

    def test_delete_schedule_nulls_backup_job_links(self, test_client: TestClient, admin_headers, test_db):
        schedule = _create_schedule(test_db, "Delete Me", repository="/repos/delete-me")
        backup_job = BackupJob(repository="/repos/delete-me", status="completed", scheduled_job_id=schedule.id)
        test_db.add(backup_job)
        test_db.commit()
        test_db.refresh(backup_job)

        response = test_client.delete(f"/api/schedule/{schedule.id}", headers=admin_headers)

        assert response.status_code == 200
        test_db.refresh(backup_job)
        assert backup_job.scheduled_job_id is None
        assert test_db.query(ScheduledJob).filter_by(id=schedule.id).first() is None

    def test_duplicate_schedule_copies_multi_repo_links_in_order(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo_a = _create_repo(test_db, "Repo A", "/repos/a")
        repo_b = _create_repo(test_db, "Repo B", "/repos/b")
        original = _create_schedule(
            test_db,
            "Original",
            repository="/repos/a",
            repository_id=repo_a.id,
            archive_name_template="{job_name}-{repo_name}",
            run_repository_scripts=True,
            run_prune_after=True,
            run_compact_after=True,
        )
        test_db.add_all(
            [
                ScheduledJobRepository(scheduled_job_id=original.id, repository_id=repo_b.id, execution_order=0),
                ScheduledJobRepository(scheduled_job_id=original.id, repository_id=repo_a.id, execution_order=1),
            ]
        )
        test_db.commit()

        response = test_client.post(f"/api/schedule/{original.id}/duplicate", headers=admin_headers)

        assert response.status_code == 200
        duplicated_id = response.json()["job"]["id"]
        duplicated = test_db.query(ScheduledJob).filter_by(id=duplicated_id).first()
        assert duplicated is not None
        assert duplicated.enabled is False
        assert duplicated.archive_name_template == "{job_name}-{repo_name}"
        assert duplicated.run_repository_scripts is True
        assert duplicated.run_prune_after is True
        assert duplicated.run_compact_after is True

        links = (
            test_db.query(ScheduledJobRepository)
            .filter_by(scheduled_job_id=duplicated_id)
            .order_by(ScheduledJobRepository.execution_order)
            .all()
        )
        assert [link.repository_id for link in links] == [repo_b.id, repo_a.id]

    def test_run_now_requires_configured_repositories(self, test_client: TestClient, admin_headers, test_db):
        schedule = _create_schedule(test_db, "Empty")
        schedule.repository = None
        schedule.repository_id = None
        test_db.commit()

        response = test_client.post(f"/api/schedule/{schedule.id}/run-now", headers=admin_headers)

        assert response.status_code == 400
        assert response.json()["detail"]["key"] == "backend.errors.schedule.noRepositoriesConfigured"

    def test_validate_cron_returns_preview_for_valid_expression(self, test_client: TestClient, admin_headers):
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={
                "minute": "0",
                "hour": "*/6",
                "day_of_month": "*",
                "month": "*",
                "day_of_week": "1-5",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["cron_expression"] == "0 */6 * * 1-5"
        assert len(body["next_runs"]) == 10

    def test_validate_cron_returns_structured_failure_for_invalid_expression(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={
                "minute": "invalid",
                "hour": "*",
                "day_of_month": "*",
                "month": "*",
                "day_of_week": "*",
            },
            headers=admin_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["cron_expression"] == "invalid * * * *"
        assert "Invalid cron expression" in body["error"]
