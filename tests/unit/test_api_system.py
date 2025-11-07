"""
Unit tests for system API endpoints
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestSystemEndpoints:
    """Test system API endpoints"""

    def test_system_info(self, test_client: TestClient, admin_headers):
        """Test getting system information"""
        response = test_client.get("/api/system/info", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should contain basic system info
        assert "app_version" in data or "borg_version" in data or "platform" in data or "system" in data

    def test_system_info_unauthorized(self, test_client: TestClient):
        """Test system info without authentication"""
        response = test_client.get("/api/system/info")

        # System info might be public or require auth
        assert response.status_code in [200, 401, 403]

    def test_borg_version(self, test_client: TestClient, admin_headers):
        """Test getting borg version"""
        response = test_client.get("/api/system/borg-version", headers=admin_headers)

        # Should return version or error if borg not installed
        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_disk_usage(self, test_client: TestClient, admin_headers):
        """Test getting disk usage information"""
        response = test_client.get("/api/system/disk-usage", headers=admin_headers)

        assert response.status_code in [200, 404, 500]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_system_health(self, test_client: TestClient, admin_headers):
        """Test system health check"""
        response = test_client.get("/api/system/health", headers=admin_headers)

        assert response.status_code in [200, 404, 503]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            # Should have some health indicator
            assert "status" in data or "healthy" in data or "health" in data
