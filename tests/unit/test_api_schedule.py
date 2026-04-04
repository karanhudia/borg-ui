"""
Comprehensive unit tests for schedule API endpoints.
Each test verifies ONE specific expected outcome.
"""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.database.models import Repository, ScheduledJob
from tests.unit.helpers import assert_auth_required


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
            repository="/test/repo",
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

        assert_auth_required(response)


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

        assert response.status_code == 404

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

        assert response.status_code == 400

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

        assert_auth_required(response)


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
            repository="/test/repo",
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
        assert data.get("success") == True
        assert "job" in data
        assert data["job"]["id"] == schedule.id

    def test_get_schedule_nonexistent(self, test_client: TestClient, admin_headers):
        """Test getting non-existent schedule returns 404"""
        response = test_client.get("/api/schedule/99999", headers=admin_headers)

        assert response.status_code == 404

    def test_get_schedule_unauthorized(self, test_client: TestClient):
        """Test getting schedule without authentication returns 403"""
        response = test_client.get("/api/schedule/1")

        assert response.status_code == 401


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
            repository="/test/repo",
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
            repository="/test/repo",
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

        assert response.status_code == 400

    def test_update_schedule_unauthorized(self, test_client: TestClient):
        """Test updating schedule without authentication returns 403"""
        response = test_client.put(
            "/api/schedule/1",
            json={"enabled": False}
        )

        assert response.status_code == 401


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
            repository="/test/repo",
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

        assert response.status_code == 401


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
            repository="/test/repo",
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

        assert response.status_code == 401


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

        assert response.status_code == 401


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
        """Test validating cron expression returns preview metadata"""
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={
                "minute": "0",
                "hour": "2",
                "day_of_month": "*",
                "month": "*",
                "day_of_week": "*",
            },
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["cron_expression"] == "0 2 * * *"
        assert len(data["next_runs"]) == 10
        assert data["description"] == "0 2 * * *"

    def test_validate_cron_invalid(self, test_client: TestClient, admin_headers):
        """Test validating invalid cron expression returns structured failure"""
        response = test_client.post(
            "/api/schedule/validate-cron",
            json={
                "minute": "invalid",
                "hour": "*",
                "day_of_month": "*",
                "month": "*",
                "day_of_week": "*",
            },
            headers=admin_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["cron_expression"] == "invalid * * * *"
        assert "Invalid cron expression" in data["error"]

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

        # Auth is checked before validation
        assert response.status_code == 401

    def test_get_upcoming_jobs_unauthorized(self, test_client: TestClient):
        """Test getting upcoming jobs without authentication returns 403"""
        response = test_client.get("/api/schedule/upcoming-jobs")

        assert response.status_code == 401


@pytest.mark.unit
class TestScheduleRoleGuard:
    """Viewers must be blocked from all mutating schedule endpoints."""

    def test_viewer_cannot_create_schedule(self, test_client, auth_headers):
        response = test_client.post(
            "/api/schedule/",
            json={"name": "x", "cron_expression": "0 * * * *", "repository_ids": []},
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.schedule.operatorAccessRequired"

    def test_viewer_cannot_update_schedule(self, test_client, auth_headers):
        response = test_client.put(
            "/api/schedule/1",
            json={"name": "y"},
            headers=auth_headers,
        )
        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.schedule.operatorAccessRequired"

    def test_viewer_cannot_delete_schedule(self, test_client, auth_headers):
        response = test_client.delete("/api/schedule/1", headers=auth_headers)
        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.schedule.operatorAccessRequired"

    def test_viewer_cannot_toggle_schedule(self, test_client, auth_headers):
        response = test_client.post("/api/schedule/1/toggle", headers=auth_headers)
        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.schedule.operatorAccessRequired"

    def test_viewer_cannot_duplicate_schedule(self, test_client, auth_headers):
        response = test_client.post("/api/schedule/1/duplicate", headers=auth_headers)
        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.schedule.operatorAccessRequired"

    def test_viewer_cannot_run_schedule_now(self, test_client, auth_headers):
        response = test_client.post("/api/schedule/1/run-now", headers=auth_headers)
        assert response.status_code == 403
        assert response.json()["detail"]["key"] == "backend.errors.schedule.operatorAccessRequired"

    def test_viewer_can_list_schedules(self, test_client, auth_headers):
        """Read endpoints must remain accessible to viewers."""
        response = test_client.get("/api/schedule/", headers=auth_headers)
        assert response.status_code == 200

    def test_operator_no_repo_permission_blocked_on_create(
        self, test_client, operator_headers, test_db
    ):
        """Operator passes global check but fails per-repo check if no explicit permission."""
        from app.database.models import Repository
        repo = Repository(name="op-test-repo", path="/backup/op-test", encryption="none")
        test_db.add(repo)
        test_db.commit()
        test_db.refresh(repo)

        response = test_client.post(
            "/api/schedule/",
            json={
                "name": "op-sched",
                "cron_expression": "0 * * * *",
                "repository_ids": [repo.id],
            },
            headers=operator_headers,
        )
        assert response.status_code == 403
