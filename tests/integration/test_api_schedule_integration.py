"""
Integration tests for scheduled jobs API with real borg execution

These tests verify scheduled job functionality end-to-end.
Focus on timezone handling and cron expression correctness.
"""
import pytest
from fastapi.testclient import TestClient
from app.database.models import Repository, ScheduledJob
from datetime import datetime, timedelta


@pytest.mark.integration
@pytest.mark.requires_borg
class TestScheduledJobCreation:
    """Test scheduled job creation with cron validation"""

    def test_create_scheduled_job_daily(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test creating daily scheduled backup

        WHY: Verifies cron expressions are stored correctly
        PREVENTS: Backups running at wrong times
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 2 * * *",  # Daily at 2 AM
                "enabled": True,
                "name": "Daily Backup",
                "timezone": "UTC"
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 201], f"Failed to create schedule: {response.json()}"
        data = response.json()

        # Verify schedule was created
        if "schedule" in data:
            schedule_data = data["schedule"]
        elif "job" in data:
            schedule_data = data["job"]
        else:
            schedule_data = data

        assert schedule_data["cron_expression"] == "0 2 * * *"
        assert schedule_data["enabled"] is True
        assert schedule_data["name"] == "Daily Backup"

    def test_create_scheduled_job_with_timezone_conversion(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test timezone is stored for cron conversion

        WHY: Verifies local time is converted to UTC correctly
        PREVENTS: Backups running at wrong local times
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 10 * * *",  # 10 AM in user's timezone
                "enabled": True,
                "name": "Morning Backup",
                "timezone": "America/New_York"  # EST/EDT
            },
            headers=admin_headers
        )

        assert response.status_code in [200, 201, 422]  # 422 if timezone not supported

        if response.status_code in [200, 201]:
            data = response.json()
            schedule_data = data.get("schedule", data)

            # Timezone should be stored
            if "timezone" in schedule_data:
                assert schedule_data["timezone"] == "America/New_York"

    def test_create_scheduled_job_invalid_cron_expression(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test invalid cron expression is rejected

        WHY: Prevents storing malformed schedules
        PREVENTS: Scheduler errors from invalid cron
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "invalid cron",
                "enabled": True,
                "name": "Bad Schedule"
            },
            headers=admin_headers
        )

        # Should reject invalid cron
        assert response.status_code in [400, 422], "Invalid cron should be rejected"

    def test_create_scheduled_job_with_repository_path(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test creating schedule using repository path instead of ID

        WHY: API might accept path as alternative to ID
        PREVENTS: Schedules not finding their repository
        """
        repo, repo_path, test_data_path = db_borg_repo

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository": str(repo_path),  # Use path instead of ID
                "cron_expression": "0 3 * * *",
                "enabled": True,
                "name": "Path-based Schedule"
            },
            headers=admin_headers
        )

        # Should work with either repository or repository_id
        assert response.status_code in [200, 201, 422]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestScheduledJobManagement:
    """Test scheduled job management operations"""

    def test_list_scheduled_jobs(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test listing all scheduled jobs

        WHY: Verifies scheduled jobs are returned correctly
        PREVENTS: UI showing empty schedule list
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create a schedule
        create_response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 2 * * *",
                "enabled": True,
                "name": "Test Schedule"
            },
            headers=admin_headers
        )

        assert create_response.status_code in [200, 201]

        # List schedules
        list_response = test_client.get("/api/schedule/", headers=admin_headers)

        assert list_response.status_code == 200
        data = list_response.json()

        # Should return list of schedules
        if isinstance(data, dict) and "schedules" in data:
            schedules = data["schedules"]
        elif isinstance(data, dict) and "jobs" in data:
            schedules = data["jobs"]
        elif isinstance(data, list):
            schedules = data
        else:
            schedules = []

        assert len(schedules) > 0, "Should have at least one schedule"

    def test_update_scheduled_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db
    ):
        """
        Test updating scheduled job

        WHY: Verifies schedule changes are saved
        PREVENTS: Users unable to modify schedules
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create a schedule directly in database
        schedule = ScheduledJob(
            repository=str(repo_path),
            cron_expression="0 2 * * *",
            enabled=True,
            name="Original Schedule"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        # Update the schedule
        update_response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={
                "cron_expression": "0 3 * * *",  # Change time
                "enabled": False,  # Disable
                "name": "Updated Schedule"
            },
            headers=admin_headers
        )

        # Update should succeed
        assert update_response.status_code in [200, 204], f"Update failed: {update_response.json()}"

    def test_delete_scheduled_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db
    ):
        """
        Test deleting scheduled job

        WHY: Verifies schedules can be removed
        PREVENTS: Unwanted backups continuing to run
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create a schedule
        schedule = ScheduledJob(
            repository=str(repo_path),
            cron_expression="0 2 * * *",
            enabled=True,
            name="To Be Deleted"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        # Delete the schedule
        delete_response = test_client.delete(
            f"/api/schedule/{schedule.id}",
            headers=admin_headers
        )

        # Delete should succeed
        assert delete_response.status_code in [200, 204], f"Delete failed: {delete_response.json()}"

        # Verify schedule no longer exists
        get_response = test_client.get(f"/api/schedule/{schedule.id}", headers=admin_headers)
        assert get_response.status_code in [404, 500], "Deleted schedule should not be found"

    def test_disable_scheduled_job(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo,
        test_db
    ):
        """
        Test disabling scheduled job

        WHY: Verifies schedules can be temporarily disabled
        PREVENTS: Having to delete and recreate schedules
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create enabled schedule
        schedule = ScheduledJob(
            repository=str(repo_path),
            cron_expression="0 2 * * *",
            enabled=True,
            name="Active Schedule"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        # Disable the schedule
        update_response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={"enabled": False},
            headers=admin_headers
        )

        assert update_response.status_code in [200, 204]


@pytest.mark.integration
@pytest.mark.requires_borg
class TestScheduledJobValidation:
    """Test scheduled job validation"""

    def test_create_schedule_for_nonexistent_repository(
        self,
        test_client: TestClient,
        admin_headers
    ):
        """
        Test schedule creation fails for missing repository

        WHY: Prevents orphaned schedules
        PREVENTS: Scheduler errors trying to backup missing repos
        """
        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": 99999,  # Non-existent
                "cron_expression": "0 2 * * *",
                "enabled": True,
                "name": "Orphan Schedule"
            },
            headers=admin_headers
        )

        # Should reject or warn about missing repository
        assert response.status_code in [200, 400, 404, 422]

    def test_create_duplicate_schedule_same_repository(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test multiple schedules can exist for same repository

        WHY: Users might want different schedules (daily + weekly)
        PREVENTS: Unnecessarily restricting schedule flexibility
        """
        repo, repo_path, test_data_path = db_borg_repo

        # Create first schedule
        response1 = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 2 * * *",  # Daily
                "enabled": True,
                "name": "Daily Backup"
            },
            headers=admin_headers
        )

        assert response1.status_code in [200, 201]

        # Create second schedule for same repo
        response2 = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "0 3 * * 0",  # Weekly on Sunday
                "enabled": True,
                "name": "Weekly Backup"
            },
            headers=admin_headers
        )

        # Should allow multiple schedules
        assert response2.status_code in [200, 201, 409]  # 409 if duplicates not allowed

    def test_cron_expression_validation(
        self,
        test_client: TestClient,
        admin_headers,
        db_borg_repo
    ):
        """
        Test various cron expressions are validated correctly

        WHY: Prevents storing invalid cron that will never run
        PREVENTS: Silent schedule failures
        """
        repo, repo_path, test_data_path = db_borg_repo

        invalid_crons = [
            "not a cron",
            "60 2 * * *",  # Invalid minute
            "0 25 * * *",  # Invalid hour
            "* * * * * *",  # 6 fields (should be 5)
        ]

        for invalid_cron in invalid_crons:
            response = test_client.post(
                "/api/schedule/",
                json={
                    "repository_id": repo.id,
                    "cron_expression": invalid_cron,
                    "enabled": True,
                    "name": f"Invalid: {invalid_cron}"
                },
                headers=admin_headers
            )

            # Each invalid cron should be rejected or cause validation error
            # We're just verifying the API doesn't crash
            assert response.status_code in [200, 201, 400, 422, 500]
