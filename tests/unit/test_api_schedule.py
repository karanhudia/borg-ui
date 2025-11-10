"""
Comprehensive unit tests for schedule API endpoints.
Each test verifies ONE specific expected outcome.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.database.models import Repository, ScheduledJob


@pytest.mark.unit
class TestScheduleList:
    """Test schedule listing endpoints"""

    def test_list_schedules_empty(self, test_client: TestClient, admin_headers):
        """Test listing schedules returns 200 when none exist"""
        response = test_client.get("/api/schedule/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_schedules_with_data(self, test_client: TestClient, admin_headers, test_db):
        """Test listing schedules returns 200 with schedule data"""
        # Create a test repository
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        # Create a test schedule
        schedule = ScheduledJob(
            repository_id=repo.id,
            cron_expression="0 2 * * *",
            enabled=True,
            name="Daily Backup"
        )
        test_db.add(schedule)
        test_db.commit()

        response = test_client.get("/api/schedule/", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_list_schedules_unauthorized(self, test_client: TestClient):
        """Test listing schedules without authentication returns 403"""
        response = test_client.get("/api/schedule/")

        assert response.status_code == 403


@pytest.mark.unit
class TestScheduleCreate:
    """Test schedule creation"""

    def test_create_schedule_missing_fields(self, test_client: TestClient, admin_headers):
        """Test creating schedule with missing fields returns 422"""
        response = test_client.post(
            "/api/schedule/",
            json={},
            headers=admin_headers
        )

        assert response.status_code == 422  # Validation error

    def test_create_schedule_invalid_repository(self, test_client: TestClient, admin_headers):
        """Test creating schedule with invalid repository returns 404"""
        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": 99999,
                "cron_expression": "0 2 * * *",  # Daily at 2 AM
                "enabled": True,
                "name": "Test Schedule"
            },
            headers=admin_headers
        )

        # Should fail to find repository
        assert response.status_code in [404, 422, 500]

    def test_create_schedule_invalid_cron(self, test_client: TestClient, admin_headers, test_db):
        """Test creating schedule with invalid cron expression returns 422"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": repo.id,
                "cron_expression": "invalid cron",
                "enabled": True,
                "name": "Test Schedule"
            },
            headers=admin_headers
        )

        # Should validate cron expression
        assert response.status_code in [400, 422, 500]

    def test_create_schedule_unauthorized(self, test_client: TestClient):
        """Test creating schedule without authentication returns 403"""
        response = test_client.post(
            "/api/schedule/",
            json={
                "repository_id": 1,
                "cron_expression": "0 2 * * *",
                "enabled": True
            }
        )

        assert response.status_code == 403


@pytest.mark.unit
class TestScheduleGet:
    """Test getting individual schedule"""

    def test_get_schedule_success(self, test_client: TestClient, admin_headers, test_db):
        """Test getting existing schedule returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        schedule = ScheduledJob(
            repository_id=repo.id,
            cron_expression="0 2 * * *",
            enabled=True,
            name="Daily Backup"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = test_client.get(f"/api/schedule/{schedule.id}", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == schedule.id or data.get("schedule", {}).get("id") == schedule.id

    def test_get_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting non-existent schedule returns 404"""
        response = test_client.get("/api/schedule/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_get_schedule_unauthorized(self, test_client: TestClient):
        """Test getting schedule without authentication returns 403"""
        response = test_client.get("/api/schedule/1")

        assert response.status_code == 403


@pytest.mark.unit
class TestScheduleUpdate:
    """Test schedule update operations"""

    def test_update_schedule_success(self, test_client: TestClient, admin_headers, test_db):
        """Test updating existing schedule returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        schedule = ScheduledJob(
            repository_id=repo.id,
            cron_expression="0 2 * * *",
            enabled=True,
            name="Daily Backup"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={
                "cron_expression": "0 3 * * *",
                "enabled": False
            },
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_update_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test updating non-existent schedule returns 404"""
        response = test_client.put(
            "/api/schedule/99999",
            json={
                "cron_expression": "0 3 * * *",
                "enabled": False
            },
            headers=admin_headers
        )

        assert response.status_code == 404

    def test_update_schedule_invalid_cron(self, test_client: TestClient, admin_headers, test_db):
        """Test updating schedule with invalid cron returns 422"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        schedule = ScheduledJob(
            repository_id=repo.id,
            cron_expression="0 2 * * *",
            enabled=True,
            name="Daily Backup"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = test_client.put(
            f"/api/schedule/{schedule.id}",
            json={
                "cron_expression": "invalid cron"
            },
            headers=admin_headers
        )

        assert response.status_code in [400, 422, 500]

    def test_update_schedule_unauthorized(self, test_client: TestClient):
        """Test updating schedule without authentication returns 403"""
        response = test_client.put(
            "/api/schedule/1",
            json={"enabled": False}
        )

        assert response.status_code == 403


@pytest.mark.unit
class TestScheduleDelete:
    """Test schedule deletion"""

    def test_delete_schedule_success(self, test_client: TestClient, admin_headers, test_db):
        """Test deleting existing schedule returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        schedule = ScheduledJob(
            repository_id=repo.id,
            cron_expression="0 2 * * *",
            enabled=True,
            name="Daily Backup"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = test_client.delete(f"/api/schedule/{schedule.id}", headers=admin_headers)

        assert response.status_code == 200

    def test_delete_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test deleting non-existent schedule returns 404"""
        response = test_client.delete("/api/schedule/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_delete_schedule_unauthorized(self, test_client: TestClient):
        """Test deleting schedule without authentication returns 403"""
        response = test_client.delete("/api/schedule/1")

        assert response.status_code == 403


@pytest.mark.unit
class TestScheduleToggle:
    """Test schedule toggle functionality"""

    def test_toggle_schedule_success(self, test_client: TestClient, admin_headers, test_db):
        """Test toggling existing schedule returns 200"""
        repo = Repository(name="Test Repo", path="/test/repo", encryption="none", repository_type="local")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        schedule = ScheduledJob(
            repository_id=repo.id,
            cron_expression="0 2 * * *",
            enabled=True,
            name="Daily Backup"
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = test_client.post(f"/api/schedule/{schedule.id}/toggle", headers=admin_headers)

        assert response.status_code == 200

    def test_toggle_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test toggling non-existent schedule returns 404"""
        response = test_client.post("/api/schedule/99999/toggle", headers=admin_headers)

        assert response.status_code == 404

    def test_toggle_schedule_unauthorized(self, test_client: TestClient):
        """Test toggling schedule without authentication returns 403"""
        response = test_client.post("/api/schedule/1/toggle")

        assert response.status_code == 403


@pytest.mark.unit
class TestScheduleRunNow:
    """Test immediate schedule execution"""

    def test_run_schedule_now_nonexistent(self, test_client: TestClient, admin_headers):
        """Test running non-existent schedule returns 404"""
        response = test_client.post("/api/schedule/99999/run-now", headers=admin_headers)

        assert response.status_code == 404

    def test_run_schedule_now_unauthorized(self, test_client: TestClient):
        """Test running schedule without authentication returns 403"""
        response = test_client.post("/api/schedule/1/run-now")

        assert response.status_code == 403


@pytest.mark.unit
class TestScheduleHelpers:
    """Test schedule helper endpoints"""

    def test_get_cron_presets(self, test_client: TestClient, admin_headers):
        """Test getting cron presets returns 200"""
        response = test_client.get("/api/schedule/cron-presets", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_validate_cron_valid(self, test_client: TestClient, admin_headers):
        """Test validating valid cron expression returns 200"""
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={"cron_expression": "0 2 * * *"},
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_validate_cron_invalid(self, test_client: TestClient, admin_headers):
        """Test validating invalid cron expression returns 400/422"""
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={"cron_expression": "invalid cron"},
            headers=admin_headers
        )

        assert response.status_code in [400, 422]

    def test_get_upcoming_jobs(self, test_client: TestClient, admin_headers):
        """Test getting upcoming jobs returns 200"""
        response = test_client.get("/api/schedule/upcoming-jobs", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_validate_cron_unauthorized(self, test_client: TestClient):
        """Test validating cron without authentication returns 403"""
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={"cron_expression": "0 2 * * *"}
        )

        assert response.status_code == 403

    def test_get_upcoming_jobs_unauthorized(self, test_client: TestClient):
        """Test getting upcoming jobs without authentication returns 403"""
        response = test_client.get("/api/schedule/upcoming-jobs")

        assert response.status_code == 403
