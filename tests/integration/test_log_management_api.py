"""
Integration tests for Log Management API

Tests /api/settings/system/logs/* endpoints for log management functionality.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database.database import get_db
from app.database.models import User, SystemSettings
from app.core.security import get_password_hash
from datetime import datetime
from pathlib import Path
import tempfile


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def test_db(tmp_path):
    """Create test database"""
    from app.database.database import SessionLocal, engine, Base

    # Create tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin_user(test_db):
    """Create admin user for testing"""
    user = User(
        username="admin",
        email="admin@test.com",
        password_hash=get_password_hash("admin123"),
        is_admin=True,
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def regular_user(test_db):
    """Create regular user for testing"""
    user = User(
        username="user",
        email="user@test.com",
        password_hash=get_password_hash("user123"),
        is_admin=False,
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def admin_token(client, admin_user):
    """Get admin authentication token"""
    response = client.post(
        "/api/auth/login",
        data={"username": "admin", "password": "admin123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def user_token(client, regular_user):
    """Get regular user authentication token"""
    response = client.post(
        "/api/auth/login",
        data={"username": "user", "password": "user123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def temp_log_files(tmp_path):
    """Create temporary log files for testing"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Create some test log files
    (log_dir / "backup_job_1.log").write_text("backup log 1" * 100)
    (log_dir / "backup_job_2.log").write_text("backup log 2" * 100)
    (log_dir / "restore_job_1.log").write_text("restore log" * 100)

    return log_dir


class TestGetSystemSettings:
    """Test GET /api/settings/system endpoint"""

    def test_get_system_settings_with_log_storage(self, client, admin_token, test_db):
        """Should return system settings including log storage info"""
        # Create system settings
        settings = SystemSettings(
            log_retention_days=30,
            log_save_policy="failed_and_warnings",
            log_max_total_size_mb=500,
            log_cleanup_on_startup=True
        )
        test_db.add(settings)
        test_db.commit()

        response = client.get(
            "/api/settings/system",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "settings" in data
        assert "log_storage" in data

        # Check log settings
        assert data["settings"]["log_retention_days"] == 30
        assert data["settings"]["log_save_policy"] == "failed_and_warnings"
        assert data["settings"]["log_max_total_size_mb"] == 500
        assert data["settings"]["log_cleanup_on_startup"] is True

        # Check log storage structure
        log_storage = data["log_storage"]
        assert "total_size_mb" in log_storage
        assert "file_count" in log_storage
        assert "usage_percent" in log_storage
        assert "files_by_type" in log_storage

    def test_get_system_settings_creates_defaults(self, client, admin_token, test_db):
        """Should create default settings if none exist"""
        response = client.get(
            "/api/settings/system",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should have created default settings
        assert data["settings"]["log_retention_days"] == 30
        assert data["settings"]["log_max_total_size_mb"] == 500
        assert data["settings"]["log_cleanup_on_startup"] is True

    def test_get_system_settings_requires_auth(self, client):
        """Should require authentication"""
        response = client.get("/api/settings/system")

        assert response.status_code == 401


class TestUpdateSystemSettings:
    """Test PUT /api/settings/system endpoint"""

    def test_update_log_save_policy(self, client, admin_token, test_db):
        """Should update log save policy"""
        response = client.put(
            "/api/settings/system",
            json={"log_save_policy": "all_jobs"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify in database
        settings = test_db.query(SystemSettings).first()
        assert settings.log_save_policy == "all_jobs"

    def test_update_log_max_size(self, client, admin_token, test_db):
        """Should update log max total size"""
        response = client.put(
            "/api/settings/system",
            json={"log_max_total_size_mb": 1000},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200

        # Verify in database
        settings = test_db.query(SystemSettings).first()
        assert settings.log_max_total_size_mb == 1000

    def test_update_log_cleanup_on_startup(self, client, admin_token, test_db):
        """Should update log cleanup on startup setting"""
        response = client.put(
            "/api/settings/system",
            json={"log_cleanup_on_startup": False},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200

        # Verify in database
        settings = test_db.query(SystemSettings).first()
        assert settings.log_cleanup_on_startup is False

    def test_validate_log_save_policy(self, client, admin_token):
        """Should validate log_save_policy values"""
        response = client.put(
            "/api/settings/system",
            json={"log_save_policy": "invalid_policy"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        assert "Invalid log_save_policy" in response.json()["detail"]

    def test_validate_log_max_size_minimum(self, client, admin_token):
        """Should enforce minimum log max size"""
        response = client.put(
            "/api/settings/system",
            json={"log_max_total_size_mb": 5},  # Below minimum of 10
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 400
        assert "at least 10 MB" in response.json()["detail"]

    def test_update_requires_admin(self, client, user_token):
        """Should require admin access to update settings"""
        response = client.put(
            "/api/settings/system",
            json={"log_save_policy": "all_jobs"},
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    def test_warning_when_new_limit_below_usage(self, client, admin_token, test_db, monkeypatch):
        """Should warn when new limit is below current usage"""
        # Mock log_manager to return high usage
        from app.services import log_manager as lm

        def mock_calculate():
            return {
                "total_size_mb": 600.0,
                "file_count": 100,
                "oldest_log_date": None,
                "newest_log_date": None,
                "files_by_type": {}
            }

        monkeypatch.setattr(lm.log_manager, "calculate_log_storage", mock_calculate)

        response = client.put(
            "/api/settings/system",
            json={"log_max_total_size_mb": 500},  # Below current usage
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "warnings" in data
        assert any("exceeds new limit" in w for w in data["warnings"])


class TestGetLogStorageStats:
    """Test GET /api/settings/system/logs/storage endpoint"""

    def test_get_log_storage_stats(self, client, admin_token, test_db):
        """Should return detailed log storage statistics"""
        # Create settings
        settings = SystemSettings(
            log_retention_days=30,
            log_max_total_size_mb=500
        )
        test_db.add(settings)
        test_db.commit()

        response = client.get(
            "/api/settings/system/logs/storage",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "storage" in data

        storage = data["storage"]
        assert "total_size_bytes" in storage
        assert "total_size_mb" in storage
        assert "file_count" in storage
        assert "oldest_log_date" in storage
        assert "newest_log_date" in storage
        assert "files_by_type" in storage
        assert "usage_percent" in storage
        assert "limit_mb" in storage
        assert "retention_days" in storage

    def test_get_log_storage_requires_auth(self, client):
        """Should require authentication"""
        response = client.get("/api/settings/system/logs/storage")

        assert response.status_code == 401

    def test_get_log_storage_allows_regular_users(self, client, user_token):
        """Should allow regular users to view log storage stats"""
        response = client.get(
            "/api/settings/system/logs/storage",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 200


class TestManualLogCleanup:
    """Test POST /api/settings/system/logs/cleanup endpoint"""

    def test_manual_cleanup_success(self, client, admin_token, test_db, monkeypatch):
        """Should perform manual log cleanup"""
        # Create settings
        settings = SystemSettings(
            log_retention_days=30,
            log_max_total_size_mb=500
        )
        test_db.add(settings)
        test_db.commit()

        # Mock cleanup to return success
        from app.services import log_manager as lm

        def mock_cleanup(db, max_age_days, max_total_size_mb, dry_run):
            return {
                "age_cleanup": {
                    "deleted_count": 5,
                    "deleted_size_mb": 10.5,
                    "skipped_count": 0,
                    "errors": []
                },
                "size_cleanup": {
                    "deleted_count": 2,
                    "deleted_size_mb": 5.2,
                    "skipped_count": 1,
                    "final_size_mb": 100.0,
                    "errors": []
                },
                "total_deleted_count": 7,
                "total_deleted_size_mb": 15.7,
                "total_errors": [],
                "success": True
            }

        monkeypatch.setattr(lm.log_manager, "cleanup_logs_combined", mock_cleanup)

        response = client.post(
            "/api/settings/system/logs/cleanup",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "message" in data
        assert "cleanup_results" in data
        assert "current_storage" in data

        results = data["cleanup_results"]
        assert results["total_deleted_count"] == 7
        assert results["total_deleted_size_mb"] == 15.7

    def test_manual_cleanup_requires_admin(self, client, user_token):
        """Should require admin access"""
        response = client.post(
            "/api/settings/system/logs/cleanup",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    def test_manual_cleanup_uses_settings(self, client, admin_token, test_db, monkeypatch):
        """Should use settings from database"""
        # Create custom settings
        settings = SystemSettings(
            log_retention_days=15,
            log_max_total_size_mb=250
        )
        test_db.add(settings)
        test_db.commit()

        # Capture the parameters passed to cleanup
        captured_params = {}

        from app.services import log_manager as lm

        def mock_cleanup(db, max_age_days, max_total_size_mb, dry_run):
            captured_params["max_age_days"] = max_age_days
            captured_params["max_total_size_mb"] = max_total_size_mb
            captured_params["dry_run"] = dry_run

            return {
                "age_cleanup": {"deleted_count": 0, "deleted_size_mb": 0, "skipped_count": 0, "errors": []},
                "size_cleanup": {"deleted_count": 0, "deleted_size_mb": 0, "skipped_count": 0, "final_size_mb": 0, "errors": []},
                "total_deleted_count": 0,
                "total_deleted_size_mb": 0,
                "total_errors": [],
                "success": True
            }

        monkeypatch.setattr(lm.log_manager, "cleanup_logs_combined", mock_cleanup)

        response = client.post(
            "/api/settings/system/logs/cleanup",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 200

        # Verify it used the correct settings
        assert captured_params["max_age_days"] == 15
        assert captured_params["max_total_size_mb"] == 250
        assert captured_params["dry_run"] is False


class TestLogManagementEndToEnd:
    """End-to-end tests for log management workflow"""

    def test_full_log_management_workflow(self, client, admin_token, test_db):
        """Test complete workflow: get settings -> update -> cleanup -> verify"""
        # Step 1: Get initial settings
        response = client.get(
            "/api/settings/system",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        initial_settings = response.json()["settings"]

        # Step 2: Update settings
        response = client.put(
            "/api/settings/system",
            json={
                "log_save_policy": "all_jobs",
                "log_retention_days": 15,
                "log_max_total_size_mb": 250,
                "log_cleanup_on_startup": False
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200

        # Step 3: Verify settings were updated
        response = client.get(
            "/api/settings/system",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        updated_settings = response.json()["settings"]

        assert updated_settings["log_save_policy"] == "all_jobs"
        assert updated_settings["log_retention_days"] == 15
        assert updated_settings["log_max_total_size_mb"] == 250
        assert updated_settings["log_cleanup_on_startup"] is False

        # Step 4: Get log storage stats
        response = client.get(
            "/api/settings/system/logs/storage",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        storage_stats = response.json()["storage"]

        assert storage_stats["limit_mb"] == 250
        assert storage_stats["retention_days"] == 15
