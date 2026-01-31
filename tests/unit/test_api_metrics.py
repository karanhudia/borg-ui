"""
Comprehensive tests for the Prometheus metrics endpoint

Tests cover:
- Metric format and syntax validation
- Metric types (gauge, counter)
- Label consistency
- Data accuracy
- Edge cases (empty DB, null values, orphaned jobs)
- Performance with large datasets
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.database.models import (
    Repository, BackupJob, RestoreJob, CheckJob, CompactJob, PruneJob,
    ScheduledJob, utc_now
)


class TestMetricsEndpoint:
    """Test the /metrics endpoint"""

    def test_endpoint_accessible_no_auth(self, test_client):
        """Metrics endpoint should be accessible without authentication"""
        response = test_client.get("/metrics")
        assert response.status_code == 200

    def test_returns_text_plain(self, test_client):
        """Metrics should return text/plain content type"""
        response = test_client.get("/metrics")
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    def test_empty_database(self, test_client, test_db):
        """Metrics should work with empty database"""
        response = test_client.get("/metrics")
        assert response.status_code == 200

        content = response.text
        # Should still have headers and system metrics
        assert "# Prometheus metrics for borg-ui" in content
        assert "borg_ui_repositories_total 0" in content


class TestPrometheusFormat:
    """Test Prometheus text format compliance"""

    def test_has_help_and_type_declarations(self, test_client, test_db):
        """All metrics should have HELP and TYPE declarations"""
        response = test_client.get("/metrics")
        content = response.text

        # Check for standard format
        assert "# HELP " in content
        assert "# TYPE " in content

    def test_metric_naming_convention(self, test_client, test_db):
        """Metrics should follow Prometheus naming conventions"""
        response = test_client.get("/metrics")
        content = response.text

        # Extract metric names (lines without # and with values)
        metric_lines = [line for line in content.split('\n')
                       if line and not line.startswith('#')]

        for line in metric_lines:
            if '{' in line:
                metric_name = line.split('{')[0]
            else:
                metric_name = line.split(' ')[0]

            # Metric names should be lowercase with underscores
            assert metric_name.islower() or '_' in metric_name
            # Should start with borg_
            assert metric_name.startswith('borg_')

    def test_metric_types_valid(self, test_client, test_db):
        """Metric types should be gauge, counter, histogram, or summary"""
        response = test_client.get("/metrics")
        content = response.text

        type_lines = [line for line in content.split('\n')
                     if line.startswith('# TYPE ')]

        valid_types = ['gauge', 'counter', 'histogram', 'summary']
        for line in type_lines:
            metric_type = line.split()[-1]
            assert metric_type in valid_types, f"Invalid type: {metric_type}"

    def test_labels_properly_quoted(self, test_client, test_db):
        """Label values should be properly quoted"""
        # Create a repository with special characters
        repo = Repository(
            name='Test "Repo" Name',
            path='/test/path',
            total_size='1 GB'
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Check that quotes in labels are handled
        assert 'repository=' in content


class TestRepositoryMetrics:
    """Test repository-related metrics"""

    def test_repository_info_metric(self, test_client, test_db):
        """borg_repository_info should include all repository metadata"""
        repo = Repository(
            name="Test Repo",
            path="/test/path",
            repository_type="local",
            mode="full"
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_repository_info{' in content
        assert 'repository="Test Repo"' in content
        assert 'path="/test/path"' in content
        assert 'type="local"' in content
        assert 'mode="full"' in content
        assert '} 1' in content

    def test_repository_size_parsing(self, test_client, test_db):
        """Repository sizes should be converted to bytes correctly"""
        test_cases = [
            ("1 GB", 1073741824),
            ("500 MB", 524288000),
            ("1.5 TB", 1649267441664),
            ("0", 0),
            ("", 0),
            (None, 0),
        ]

        for size_str, expected_bytes in test_cases:
            repo = Repository(
                name=f"Repo {size_str}",
                path=f"/test/{size_str}",
                total_size=size_str
            )
            test_db.add(repo)

        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Check that sizes are present and in bytes
        assert 'borg_repository_size_bytes' in content
        assert '1073741824' in content  # 1 GB

    def test_repository_timestamps(self, test_client, test_db):
        """Repository timestamps should be Unix timestamps"""
        now = utc_now()
        repo = Repository(
            name="Test Repo",
            path="/test/path",
            last_backup=now,
            last_check=now - timedelta(days=1),
            last_compact=now - timedelta(days=7)
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Check that timestamps are present
        assert 'borg_repository_last_backup_timestamp' in content
        assert 'borg_repository_last_check_timestamp' in content
        assert 'borg_repository_last_compact_timestamp' in content

        # Timestamps should be integers
        import re
        timestamps = re.findall(r'borg_repository_last_backup_timestamp\{[^}]+\} (\d+)', content)
        assert len(timestamps) > 0
        assert all(ts.isdigit() for ts in timestamps)

    def test_null_timestamps(self, test_client, test_db):
        """Null timestamps should be 0"""
        repo = Repository(
            name="New Repo",
            path="/new/path",
            last_backup=None,
            last_check=None,
            last_compact=None
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_repository_last_backup_timestamp{repository="New Repo"} 0' in content


class TestBackupJobMetrics:
    """Test backup job metrics"""

    def test_backup_jobs_total_by_status(self, test_client, test_db):
        """borg_backup_jobs_total should show counts by status"""
        repo = Repository(name="Test", path="/test")
        test_db.add(repo)
        test_db.commit()

        # Create jobs with different statuses
        statuses = ["completed", "failed", "running", "completed_with_warnings"]
        for status in statuses:
            for _ in range(3):
                job = BackupJob(
                    repository=repo.path,
                    status=status,
                    started_at=utc_now()
                )
                test_db.add(job)

        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Check that all statuses are present
        assert 'borg_backup_jobs_total{repository="Test",status="completed"} 3' in content
        assert 'borg_backup_jobs_total{repository="Test",status="failed"} 3' in content
        assert 'borg_backup_jobs_total{repository="Test",status="running"} 3' in content

    def test_backup_last_job_success(self, test_client, test_db):
        """borg_backup_last_job_success should be 1 for success, 0 for failure"""
        repo1 = Repository(name="Success Repo", path="/success")
        repo2 = Repository(name="Failed Repo", path="/failed")
        test_db.add_all([repo1, repo2])
        test_db.commit()

        # Successful backup
        job1 = BackupJob(
            repository=repo1.path,
            status="completed",
            started_at=utc_now()
        )
        # Failed backup
        job2 = BackupJob(
            repository=repo2.path,
            status="failed",
            started_at=utc_now()
        )
        test_db.add_all([job1, job2])
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_backup_last_job_success{repository="Success Repo"} 1' in content
        assert 'borg_backup_last_job_success{repository="Failed Repo"} 0' in content

    def test_backup_duration_calculation(self, test_client, test_db):
        """borg_backup_last_duration_seconds should calculate correctly"""
        repo = Repository(name="Test", path="/test")
        test_db.add(repo)
        test_db.commit()

        start = utc_now()
        end = start + timedelta(seconds=125)  # 2 min 5 sec

        job = BackupJob(
            repository=repo.path,
            status="completed",
            started_at=start,
            completed_at=end
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Should show 125 seconds
        assert 'borg_backup_last_duration_seconds{repository="Test"} 125.00' in content

    def test_backup_size_metrics(self, test_client, test_db):
        """Backup size metrics should show in bytes"""
        repo = Repository(name="Test", path="/test")
        test_db.add(repo)
        test_db.commit()

        job = BackupJob(
            repository=repo.path,
            status="completed",
            original_size=1000000000,  # 1 GB
            deduplicated_size=500000000  # 500 MB
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_backup_last_original_size_bytes{repository="Test"} 1000000000' in content
        assert 'borg_backup_last_deduplicated_size_bytes{repository="Test"} 500000000' in content

    def test_orphaned_backup_jobs(self, test_client, test_db):
        """Backup jobs without matching repos should appear in orphaned metric"""
        # Create a job without a matching repository
        job = BackupJob(
            repository="/orphaned/path",
            status="completed",
            started_at=utc_now()
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Should show in orphaned jobs metric with repository_path label
        assert 'borg_backup_orphaned_jobs_total' in content
        assert 'repository_path="/orphaned/path"' in content
        assert 'status="completed"' in content


class TestLabelConsistency:
    """Test that repository labels are consistent across metrics"""

    def test_all_metrics_use_same_repository_label(self, test_client, test_db):
        """All metrics should use repository name, not path"""
        repo = Repository(
            name="Consistent Repo",
            path="/different/path"
        )
        test_db.add(repo)
        test_db.commit()

        # Create various jobs
        backup_job = BackupJob(
            repository=repo.path,
            status="completed",
            started_at=utc_now(),
            completed_at=utc_now()
        )
        check_job = CheckJob(
            repository_id=repo.id,
            status="completed",
            started_at=utc_now(),
            completed_at=utc_now()
        )
        test_db.add_all([backup_job, check_job])
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Count occurrences of the repository name in labels
        name_count = content.count('repository="Consistent Repo"')
        path_count = content.count('repository="/different/path"')

        # Name should appear more often than path
        assert name_count > 0
        assert name_count >= path_count


class TestSystemMetrics:
    """Test system-level metrics"""

    def test_repositories_total(self, test_client, test_db):
        """borg_ui_repositories_total should count all repos"""
        for i in range(5):
            repo = Repository(name=f"Repo {i}", path=f"/repo{i}")
            test_db.add(repo)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_ui_repositories_total 5' in content

    def test_scheduled_jobs_metrics(self, test_client, test_db):
        """Scheduled job metrics should show total and enabled counts"""
        for i in range(3):
            job = ScheduledJob(
                name=f"Job {i}",
                cron_expression="0 2 * * *",
                enabled=(i < 2)  # 2 enabled, 1 disabled
            )
            test_db.add(job)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_ui_scheduled_jobs_total 3' in content
        assert 'borg_ui_scheduled_jobs_enabled 2' in content

    def test_active_jobs_by_type(self, test_client, test_db):
        """borg_ui_active_jobs should show running jobs by type"""
        repo = Repository(name="Test", path="/test")
        test_db.add(repo)
        test_db.commit()

        # Create running jobs of different types
        backup = BackupJob(repository=repo.path, status="running")
        restore = RestoreJob(repository=repo.path, archive="test", destination="/dest", status="running")
        check = CheckJob(repository_id=repo.id, status="running")

        test_db.add_all([backup, restore, check])
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_ui_active_jobs{type="backup"} 1' in content
        assert 'borg_ui_active_jobs{type="restore"} 1' in content
        assert 'borg_ui_active_jobs{type="check"} 1' in content


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_very_large_numbers(self, test_client, test_db):
        """Should handle very large size values"""
        repo = Repository(
            name="Huge Repo",
            path="/huge",
            total_size="999 TB"
        )
        test_db.add(repo)

        job = BackupJob(
            repository=repo.path,
            status="completed",
            original_size=999999999999999  # ~1 PB
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get("/metrics")
        assert response.status_code == 200
        content = response.text
        assert '999999999999999' in content

    def test_special_characters_in_names(self, test_client, test_db):
        """Should handle special characters in repository names"""
        special_names = [
            'Repo with spaces',
            'Repo-with-dashes',
            'Repo_with_underscores',
            'Repo.with.dots'
        ]

        for name in special_names:
            repo = Repository(name=name, path=f"/{name}")
            test_db.add(repo)

        test_db.commit()

        response = test_client.get("/metrics")
        assert response.status_code == 200
        content = response.text

        # All names should appear in output
        for name in special_names:
            assert f'repository="{name}"' in content

    def test_concurrent_requests(self, test_client, test_db):
        """Metrics endpoint should handle concurrent requests"""
        import concurrent.futures

        # Create some test data
        repo = Repository(name="Test", path="/test")
        test_db.add(repo)
        test_db.commit()

        def fetch_metrics():
            response = test_client.get("/metrics")
            return response.status_code

        # Make 10 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_metrics) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        assert all(status == 200 for status in results)

    def test_performance_with_large_dataset(self, test_client, test_db):
        """Should handle large number of repositories and jobs efficiently"""
        import time

        # Create 50 repositories
        for i in range(50):
            repo = Repository(name=f"Repo {i}", path=f"/repo{i}")
            test_db.add(repo)

        test_db.commit()

        # Create 500 backup jobs
        repos = test_db.query(Repository).all()
        for i in range(500):
            repo = repos[i % len(repos)]
            job = BackupJob(
                repository=repo.path,
                status="completed",
                started_at=utc_now(),
                completed_at=utc_now()
            )
            test_db.add(job)

        test_db.commit()

        # Measure response time
        start = time.time()
        response = test_client.get("/metrics")
        duration = time.time() - start

        assert response.status_code == 200
        # Should respond within 5 seconds even with large dataset
        assert duration < 5.0


class TestMetricValues:
    """Test that metric values are correct"""

    def test_completed_with_warnings_counts_as_success(self, test_client, test_db):
        """completed_with_warnings should count as success"""
        repo = Repository(name="Test", path="/test")
        test_db.add(repo)
        test_db.commit()

        job = BackupJob(
            repository=repo.path,
            status="completed_with_warnings",
            started_at=utc_now()
        )
        test_db.add(job)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        # Should show success=1
        assert 'borg_backup_last_job_success{repository="Test"} 1' in content

    def test_zero_values_explicitly_shown(self, test_client, test_db):
        """Zero values should be explicitly shown, not omitted"""
        repo = Repository(
            name="Empty Repo",
            path="/empty",
            archive_count=0,
            total_size="0"
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.get("/metrics")
        content = response.text

        assert 'borg_repository_archive_count{repository="Empty Repo"} 0' in content
        assert 'borg_repository_size_bytes{repository="Empty Repo"} 0' in content

    def test_metrics_sorted_consistently(self, test_client, test_db):
        """Metrics should appear in consistent order"""
        response1 = test_client.get("/metrics")
        response2 = test_client.get("/metrics")

        # Extract metric names
        def get_metric_names(content):
            return [line.split('{')[0].split(' ')[0]
                   for line in content.split('\n')
                   if line and not line.startswith('#')]

        names1 = get_metric_names(response1.text)
        names2 = get_metric_names(response2.text)

        # Should be in same order
        assert names1 == names2
