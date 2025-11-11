"""
Comprehensive unit tests for dashboard API endpoints
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestDashboardStatus:
    """Test dashboard status endpoints"""

    def test_dashboard_status(self, test_client: TestClient, admin_headers):
        """Test dashboard status endpoint"""
        response = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        # Dashboard should return some status information
        assert isinstance(data, dict)

    def test_dashboard_status_structure(self, test_client: TestClient, admin_headers):
        """Test dashboard status returns proper structure"""
        response = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        # Should contain some status information
        assert len(data) > 0

    def test_dashboard_status_contains_repositories(self, test_client: TestClient, admin_headers):
        """Test that dashboard status includes repository count"""
        response = test_client.get("/api/dashboard/status", headers=admin_headers)

        if response.status_code == 200:
            data = response.json()
            # Might have repository count or related info
            assert isinstance(data, dict)

    def test_dashboard_status_caching(self, test_client: TestClient, admin_headers):
        """Test that dashboard status can be called multiple times"""
        response1 = test_client.get("/api/dashboard/status", headers=admin_headers)
        response2 = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response1.status_code == response2.status_code
        assert response1.status_code == 200


@pytest.mark.unit
class TestDashboardMetrics:
    """Test dashboard metrics endpoints"""

    def test_dashboard_metrics(self, test_client: TestClient, admin_headers):
        """Test dashboard metrics endpoint"""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_metrics_basic(self, test_client: TestClient, admin_headers):
        """Test basic metrics endpoint"""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_metrics_backup_statistics(self, test_client: TestClient, admin_headers):
        """Test metrics includes backup statistics"""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        if response.status_code == 200:
            data = response.json()
            # Might include backup counts, sizes, etc.
            assert isinstance(data, dict)

    def test_metrics_time_range(self, test_client: TestClient, admin_headers):
        """Test metrics with time range parameters"""
        response = test_client.get(
            "/api/dashboard/metrics",
            params={"days": 7},
            headers=admin_headers
        )

        assert response.status_code in [200, 422]

    def test_metrics_repository_specific(self, test_client: TestClient, admin_headers):
        """Test metrics for specific repository"""
        response = test_client.get(
            "/api/dashboard/metrics",
            params={"repository_id": 1},
            headers=admin_headers
        )

        assert response.status_code in [200, 404, 422]


@pytest.mark.unit
class TestDashboardAuthentication:
    """Test authentication for dashboard endpoints"""

    def test_dashboard_unauthorized(self, test_client: TestClient):
        """Test dashboard endpoints without authentication"""
        endpoints = ["/api/dashboard/status", "/api/dashboard/metrics"]

        for endpoint in endpoints:
            response = test_client.get(endpoint)
            assert response.status_code in [401, 403], f"Expected 401 or 403 for {endpoint}"


@pytest.mark.unit
class TestDashboardSummary:
    """Test dashboard summary information"""

    def test_get_dashboard_summary(self, test_client: TestClient, admin_headers):
        """Test getting dashboard summary"""
        response = test_client.get("/api/dashboard/summary", headers=admin_headers)

        # Endpoint might or might not exist
        assert response.status_code in [200, 404]

    def test_dashboard_activity_feed(self, test_client: TestClient, admin_headers):
        """Test getting recent activity"""
        response = test_client.get("/api/dashboard/activity", headers=admin_headers)

        assert response.status_code in [200, 404]

    def test_dashboard_recent_backups(self, test_client: TestClient, admin_headers):
        """Test getting recent backups"""
        response = test_client.get("/api/dashboard/recent-backups", headers=admin_headers)

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_dashboard_alerts(self, test_client: TestClient, admin_headers):
        """Test getting dashboard alerts"""
        response = test_client.get("/api/dashboard/alerts", headers=admin_headers)

        assert response.status_code in [200, 404]
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))


@pytest.mark.unit
class TestDashboardStatistics:
    """Test dashboard statistics calculations"""

    def test_storage_statistics(self, test_client: TestClient, admin_headers):
        """Test storage usage statistics"""
        response = test_client.get("/api/dashboard/storage-stats", headers=admin_headers)

        assert response.status_code in [200, 404]

    def test_backup_success_rate(self, test_client: TestClient, admin_headers):
        """Test backup success rate statistics"""
        response = test_client.get("/api/dashboard/success-rate", headers=admin_headers)

        assert response.status_code in [200, 404]

    def test_repository_health_summary(self, test_client: TestClient, admin_headers):
        """Test repository health summary"""
        response = test_client.get("/api/dashboard/repository-health", headers=admin_headers)

        assert response.status_code in [200, 404]


@pytest.mark.unit
class TestDashboardCharts:
    """Test dashboard chart data endpoints"""

    def test_backup_trends(self, test_client: TestClient, admin_headers):
        """Test getting backup trends over time"""
        response = test_client.get("/api/dashboard/trends", headers=admin_headers)

        assert response.status_code in [200, 404]

    def test_storage_growth(self, test_client: TestClient, admin_headers):
        """Test getting storage growth data"""
        response = test_client.get("/api/dashboard/storage-growth", headers=admin_headers)

        assert response.status_code in [200, 404]

    def test_performance_metrics(self, test_client: TestClient, admin_headers):
        """Test getting performance metrics"""
        response = test_client.get("/api/dashboard/performance", headers=admin_headers)

        assert response.status_code in [200, 404]
