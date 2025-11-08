"""
Unit tests for dashboard API endpoints
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestDashboardEndpoints:
    """Test dashboard API endpoints"""

    def test_dashboard_status(self, test_client: TestClient, admin_headers):
        """Test dashboard status endpoint"""
        response = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        # Dashboard should return some status information
        assert isinstance(data, dict)

    def test_dashboard_metrics(self, test_client: TestClient, admin_headers):
        """Test dashboard metrics endpoint"""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_dashboard_unauthorized(self, test_client: TestClient):
        """Test dashboard endpoints without authentication"""
        endpoints = ["/api/dashboard/status", "/api/dashboard/metrics"]

        for endpoint in endpoints:
            response = test_client.get(endpoint)
            assert response.status_code in [401, 403], f"Expected 401 or 403 for {endpoint}"
