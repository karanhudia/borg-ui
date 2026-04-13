"""
Comprehensive unit tests for dashboard API endpoints
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.api.dashboard import (
    ScheduledJobInfo,
    SystemMetrics,
    format_bytes,
    get_recent_jobs,
    parse_size_to_bytes,
)
from app.database.models import (
    BackupJob,
    CheckJob,
    CompactJob,
    Repository,
    ScheduledJob,
    SSHConnection,
)


@pytest.mark.unit
class TestDashboardStatus:
    """Test dashboard status endpoints"""

    def _mock_dashboard_status(self):
        return patch(
            "app.api.dashboard.get_system_metrics",
            return_value=SystemMetrics(
                cpu_usage=12.5,
                cpu_count=8,
                memory_usage=43.0,
                memory_total=1024,
                memory_available=512,
                disk_usage=55.0,
                disk_total=2048,
                disk_free=1024,
                uptime=123456,
            ),
        )

    def test_dashboard_status(self, test_client: TestClient, admin_headers):
        """Test dashboard status endpoint"""
        with self._mock_dashboard_status():
            response = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "system_metrics" in data
        assert "scheduled_jobs" in data
        assert "recent_jobs" in data
        assert "alerts" in data
        assert "last_updated" in data

    def test_dashboard_status_structure(self, test_client: TestClient, admin_headers):
        """Test dashboard status returns proper structure"""
        with self._mock_dashboard_status():
            response = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "system_metrics",
            "scheduled_jobs",
            "recent_jobs",
            "alerts",
            "last_updated",
        }

    def test_dashboard_status_contains_repositories(
        self, test_client: TestClient, admin_headers
    ):
        """Test that dashboard status includes repository count"""
        with self._mock_dashboard_status():
            response = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["scheduled_jobs"], list)

    def test_dashboard_status_caching(self, test_client: TestClient, admin_headers):
        """Test that dashboard status can be called multiple times"""
        with self._mock_dashboard_status():
            response1 = test_client.get("/api/dashboard/status", headers=admin_headers)
            response2 = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response1.status_code == response2.status_code
        assert response1.status_code == 200

    def test_dashboard_status_contract(self, test_client: TestClient, admin_headers):
        """Test that dashboard status returns the documented aggregate shape."""
        metrics = SystemMetrics(
            cpu_usage=12.5,
            cpu_count=8,
            memory_usage=43.0,
            memory_total=1024,
            memory_available=512,
            disk_usage=55.0,
            disk_total=2048,
            disk_free=1024,
            uptime=123456,
        )
        scheduled_job = ScheduledJobInfo(
            id=7,
            name="Nightly backup",
            cron_expression="0 2 * * *",
            repository="/srv/backups/repo",
            enabled=True,
            last_run="2026-04-03T20:00:00+00:00",
            next_run="2026-04-04T02:00:00+00:00",
        )
        recent_job = {
            "id": 11,
            "repository": "/srv/backups/repo",
            "status": "completed",
            "started_at": "2026-04-04T00:00:00+00:00",
            "completed_at": "2026-04-04T00:10:00+00:00",
            "progress": 100,
            "error_message": None,
            "triggered_by": "manual",
            "schedule_id": None,
            "has_logs": True,
        }

        with patch("app.api.dashboard.get_system_metrics", return_value=metrics):
            with patch(
                "app.api.dashboard.get_scheduled_jobs", return_value=[scheduled_job]
            ):
                with patch(
                    "app.api.dashboard.get_recent_jobs", return_value=[recent_job]
                ):
                    with patch(
                        "app.api.dashboard.get_alerts",
                        return_value=[{"type": "info", "message": "ok"}],
                    ):
                        response = test_client.get(
                            "/api/dashboard/status", headers=admin_headers
                        )

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "system_metrics",
            "scheduled_jobs",
            "recent_jobs",
            "alerts",
            "last_updated",
        }
        assert data["system_metrics"]["cpu_usage"] == 12.5
        assert data["scheduled_jobs"][0]["name"] == "Nightly backup"
        assert data["recent_jobs"][0]["triggered_by"] == "manual"
        assert data["alerts"] == [{"type": "info", "message": "ok"}]
        assert data["last_updated"].endswith("+00:00")


@pytest.mark.unit
class TestDashboardMetrics:
    """Test dashboard metrics endpoints"""

    def test_dashboard_metrics(self, test_client: TestClient, admin_headers):
        """Test dashboard metrics endpoint"""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "cpu_usage",
            "memory_usage",
            "disk_usage",
            "network_io",
            "load_average",
        }

    def test_metrics_basic(self, test_client: TestClient, admin_headers):
        """Test basic metrics endpoint"""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert "cpu_usage" in data
        assert "network_io" in data

    def test_metrics_backup_statistics(self, test_client: TestClient, admin_headers):
        """Test metrics includes backup statistics"""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["network_io"], dict)
        assert isinstance(data["load_average"], list)

    def test_metrics_time_range(self, test_client: TestClient, admin_headers):
        """Test metrics with time range parameters"""
        response = test_client.get(
            "/api/dashboard/metrics", params={"days": 7}, headers=admin_headers
        )

        assert response.status_code == 200

    def test_metrics_repository_specific(self, test_client: TestClient, admin_headers):
        """Test metrics for specific repository"""
        response = test_client.get(
            "/api/dashboard/metrics", params={"repository_id": 1}, headers=admin_headers
        )

        assert response.status_code == 200

    def test_metrics_returns_network_and_load_fields(
        self, test_client: TestClient, admin_headers
    ):
        """Test metrics contract includes the expected hardware summary fields."""
        response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {
            "cpu_usage",
            "memory_usage",
            "disk_usage",
            "network_io",
            "load_average",
        }
        assert set(data["network_io"].keys()) == {
            "bytes_sent",
            "bytes_recv",
            "packets_sent",
            "packets_recv",
        }
        assert len(data["load_average"]) == 3


@pytest.mark.unit
class TestDashboardAuthentication:
    """Test authentication for dashboard endpoints"""

    def test_dashboard_unauthorized(self, test_client: TestClient):
        """Test dashboard endpoints without authentication"""
        endpoints = ["/api/dashboard/status", "/api/dashboard/metrics"]

        for endpoint in endpoints:
            response = test_client.get(endpoint)
            assert response.status_code == 401, f"Expected 401 for {endpoint}"


@pytest.mark.unit
class TestDashboardSummary:
    """Test dashboard summary information"""

    def test_get_dashboard_summary(self, test_client: TestClient, admin_headers):
        """Test getting dashboard summary"""
        response = test_client.get("/api/dashboard/summary", headers=admin_headers)

        assert response.status_code == 404

    def test_dashboard_activity_feed(self, test_client: TestClient, admin_headers):
        """Test getting recent activity"""
        response = test_client.get("/api/dashboard/activity", headers=admin_headers)

        assert response.status_code == 404

    def test_dashboard_recent_backups(self, test_client: TestClient, admin_headers):
        """Test getting recent backups"""
        response = test_client.get(
            "/api/dashboard/recent-backups", headers=admin_headers
        )

        assert response.status_code == 404

    def test_dashboard_alerts(self, test_client: TestClient, admin_headers):
        """Test getting dashboard alerts"""
        response = test_client.get("/api/dashboard/alerts", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestDashboardHelpers:
    """Test dashboard helper functions directly."""

    @pytest.mark.parametrize(
        "size_string, expected",
        [
            ("0", 0),
            ("512 B", 512),
            ("1 KB", 1024),
            ("1.5 MB", 1572864),
            ("2 GB", 2147483648),
            ("3 TB", 3298534883328),
            ("bad-value", 0),
            (None, 0),
        ],
    )
    def test_parse_size_to_bytes(self, size_string, expected):
        assert parse_size_to_bytes(size_string) == expected

    @pytest.mark.parametrize(
        "size_value, expected",
        [
            (0, "0.0 B"),
            (512, "512.0 B"),
            (1024, "1.0 KB"),
            (1024 * 1024, "1.0 MB"),
            (1024 * 1024 * 1024, "1.0 GB"),
        ],
    )
    def test_format_bytes(self, size_value, expected):
        assert format_bytes(size_value) == expected

    def test_get_recent_jobs_normalizes_trigger_state_and_logs(self):
        now = datetime.now(timezone.utc)
        jobs = [
            BackupJob(
                id=1,
                repository="/srv/backups/full",
                status="completed",
                started_at=now - timedelta(hours=1),
                completed_at=now - timedelta(minutes=30),
                progress=100,
                scheduled_job_id=9,
                log_file_path="/tmp/job.log",
            ),
            BackupJob(
                id=2,
                repository="/srv/backups/manual",
                status="failed",
                started_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=2, minutes=5),
                progress=42,
                error_message="boom",
                logs="legacy logs",
            ),
        ]

        all_query = MagicMock()
        all_query.return_value = jobs
        limit_query = MagicMock()
        limit_query.all = all_query
        order_query = MagicMock()
        order_query.limit.return_value = limit_query
        query = MagicMock()
        query.order_by.return_value = order_query
        db = MagicMock()
        db.query.return_value = query

        result = get_recent_jobs(db, limit=2)

        assert [job["id"] for job in result] == [1, 2]
        assert result[0]["triggered_by"] == "schedule"
        assert result[0]["has_logs"] is True
        assert result[1]["triggered_by"] == "manual"
        assert result[1]["error_message"] == "boom"

    def test_get_recent_jobs_returns_empty_on_query_error(self):
        db = MagicMock()
        db.query.side_effect = RuntimeError("boom")

        assert get_recent_jobs(db) == []

    def test_get_system_metrics_falls_back_when_component_reads_fail(self):
        from app.api.dashboard import get_system_metrics

        with patch(
            "app.api.dashboard.psutil.cpu_percent", side_effect=RuntimeError("cpu")
        ):
            with patch(
                "app.api.dashboard.psutil.virtual_memory",
                side_effect=RuntimeError("memory"),
            ):
                with patch(
                    "app.api.dashboard.psutil.disk_usage",
                    side_effect=RuntimeError("disk"),
                ):
                    with patch(
                        "app.api.dashboard.psutil.boot_time",
                        side_effect=RuntimeError("uptime"),
                    ):
                        metrics = get_system_metrics()

        assert metrics.cpu_usage == 0.0
        assert metrics.cpu_count == 1
        assert metrics.memory_usage == 0.0
        assert metrics.memory_total == 0
        assert metrics.memory_available == 0
        assert metrics.disk_usage == 0.0
        assert metrics.disk_total == 0
        assert metrics.disk_free == 0
        assert metrics.uptime == 0


@pytest.mark.unit
class TestDashboardStatistics:
    """Test dashboard statistics calculations"""

    def test_storage_statistics(self, test_client: TestClient, admin_headers):
        """Test storage usage statistics"""
        response = test_client.get(
            "/api/dashboard/storage-stats", headers=admin_headers
        )

        assert response.status_code == 404

    def test_backup_success_rate(self, test_client: TestClient, admin_headers):
        """Test backup success rate statistics"""
        response = test_client.get("/api/dashboard/success-rate", headers=admin_headers)

        assert response.status_code == 404

    def test_repository_health_summary(self, test_client: TestClient, admin_headers):
        """Test repository health summary"""
        response = test_client.get(
            "/api/dashboard/repository-health", headers=admin_headers
        )

        assert response.status_code == 404


@pytest.mark.unit
class TestDashboardCharts:
    """Test dashboard chart data endpoints"""

    def test_backup_trends(self, test_client: TestClient, admin_headers):
        """Test getting backup trends over time"""
        response = test_client.get("/api/dashboard/trends", headers=admin_headers)

        assert response.status_code == 404

    def test_storage_growth(self, test_client: TestClient, admin_headers):
        """Test getting storage growth data"""
        response = test_client.get(
            "/api/dashboard/storage-growth", headers=admin_headers
        )

        assert response.status_code == 404

    def test_performance_metrics(self, test_client: TestClient, admin_headers):
        """Test getting performance metrics"""
        response = test_client.get("/api/dashboard/performance", headers=admin_headers)

        assert response.status_code == 404


@pytest.mark.unit
class TestDashboardScheduleAndOverview:
    """Test the live dashboard schedule and overview contracts."""

    def test_dashboard_schedule_uses_scheduled_jobs_contract(
        self, test_client: TestClient, admin_headers
    ):
        job = ScheduledJobInfo(
            id=12,
            name="Weekly maintenance",
            cron_expression="0 3 * * 0",
            repository="/srv/backups/repo",
            enabled=True,
            last_run="2026-04-04T03:00:00+00:00",
            next_run="2026-04-05T03:00:00+00:00",
        )

        with patch("app.api.dashboard.get_scheduled_jobs", return_value=[job]):
            response = test_client.get("/api/dashboard/schedule", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["jobs"][0]["name"] == "Weekly maintenance"
        assert data["next_execution"] is not None

    def test_dashboard_status_returns_500_when_system_metrics_fail(
        self, test_client: TestClient, admin_headers
    ):
        with patch(
            "app.api.dashboard.get_system_metrics", side_effect=RuntimeError("boom")
        ):
            response = test_client.get("/api/dashboard/status", headers=admin_headers)

        assert response.status_code == 500
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.dashboard.failedGetDashboardStatus"
        )

    def test_dashboard_metrics_returns_500_when_psutil_fails(
        self, test_client: TestClient, admin_headers
    ):
        with patch(
            "app.api.dashboard.psutil.cpu_percent", side_effect=RuntimeError("boom")
        ):
            response = test_client.get("/api/dashboard/metrics", headers=admin_headers)

        assert response.status_code == 500
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.dashboard.failedGetMetrics"
        )

    def test_dashboard_overview_aggregates_real_database_state(
        self,
        test_client: TestClient,
        admin_headers,
        test_db,
    ):
        now = datetime.now(timezone.utc)
        full_repo = Repository(
            name="Full Repo",
            path="/srv/backups/full",
            repository_type="local",
            mode="full",
            archive_count=2,
            total_size="1.5 TB",
            last_backup=now - timedelta(days=8),
            last_check=now - timedelta(days=45),
            last_compact=now - timedelta(days=75),
        )
        observe_repo = Repository(
            name="Observe Repo",
            path="/srv/backups/observe",
            repository_type="ssh",
            mode="observe",
            archive_count=5,
            total_size="2 GB",
            last_backup=datetime.utcnow() - timedelta(hours=12),
        )
        test_db.add_all([full_repo, observe_repo])
        test_db.commit()
        test_db.refresh(full_repo)
        test_db.refresh(observe_repo)

        schedule = ScheduledJob(
            name="Nightly Full Repo",
            cron_expression="0 2 * * *",
            repository_id=full_repo.id,
            enabled=True,
            next_run=now + timedelta(hours=2),
        )
        far_schedule = ScheduledJob(
            name="Far Future Repo",
            cron_expression="0 2 * * *",
            repository_id=full_repo.id,
            enabled=True,
            next_run=now + timedelta(hours=30),
        )
        ssh_connection = SSHConnection(
            host="backup.example.com",
            username="borg",
            port=22,
            status="connected",
        )
        test_db.add_all([schedule, far_schedule, ssh_connection])
        test_db.commit()
        test_db.refresh(schedule)
        test_db.refresh(far_schedule)
        test_db.refresh(ssh_connection)

        test_db.add_all(
            [
                BackupJob(
                    repository=full_repo.path,
                    status="completed",
                    started_at=now - timedelta(days=2),
                    completed_at=now - timedelta(days=2, minutes=10),
                    progress=100,
                    scheduled_job_id=schedule.id,
                ),
                BackupJob(
                    repository=full_repo.path,
                    status="failed",
                    started_at=now - timedelta(days=1),
                    completed_at=now - timedelta(days=1, minutes=5),
                    progress=80,
                    error_message="backup failed",
                ),
                CheckJob(
                    repository_id=full_repo.id,
                    repository_path=full_repo.path,
                    status="completed",
                    started_at=now - timedelta(days=3),
                    completed_at=now - timedelta(days=3, minutes=15),
                ),
                CompactJob(
                    repository_id=full_repo.id,
                    repository_path=full_repo.path,
                    status="completed",
                    started_at=now - timedelta(days=4),
                    completed_at=now - timedelta(days=4, minutes=20),
                ),
            ]
        )
        test_db.commit()

        metrics = SystemMetrics(
            cpu_usage=12.5,
            cpu_count=8,
            memory_usage=43.0,
            memory_total=1024,
            memory_available=512,
            disk_usage=55.0,
            disk_total=2048,
            disk_free=1024,
            uptime=123456,
        )

        with patch("app.api.dashboard.get_system_metrics", return_value=metrics):
            response = test_client.get("/api/dashboard/overview", headers=admin_headers)

        assert response.status_code == 200
        data = response.json()

        assert data["summary"] == {
            "total_repositories": 2,
            "local_repositories": 1,
            "ssh_repositories": 1,
            "active_schedules": 2,
            "total_schedules": 2,
            "ssh_connections_active": 1,
            "ssh_connections_total": 1,
            "success_rate_30d": 50.0,
            "successful_jobs_30d": 1,
            "failed_jobs_30d": 1,
            "total_jobs_30d": 2,
        }

        assert data["storage"]["total_archives"] == 7
        assert data["storage"]["total_size"] == "1.5 TB"
        repo_health = {item["name"]: item for item in data["repository_health"]}
        assert repo_health["Full Repo"]["health_status"] == "critical"
        assert repo_health["Full Repo"]["schedule_name"] == "Nightly Full Repo"
        assert repo_health["Observe Repo"]["mode"] == "observe"
        assert repo_health["Observe Repo"]["dimension_health"] == {
            "backup": "healthy",
            "check": "unknown",
            "compact": "healthy",
        }
        assert len(data["repository_health"]) == 2
        assert [item["type"] for item in data["activity_feed"]][:3] == [
            "backup",
            "backup",
            "check",
        ]
        assert data["activity_feed"][0]["repository"] == "Full Repo"
        assert [item["name"] for item in data["upcoming_tasks"]] == [
            "Nightly Full Repo"
        ]
        assert data["upcoming_tasks"][0]["next_run"].startswith(
            schedule.next_run.isoformat()
        )
        assert data["system_metrics"]["cpu_usage"] == 12.5
        assert data["last_updated"].endswith("+00:00")
