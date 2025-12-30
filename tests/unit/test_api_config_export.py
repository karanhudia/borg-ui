"""
Unit tests for configuration export API endpoints.
Tests timestamp formatting in exported filenames.
"""
import pytest
import re
from datetime import datetime
from fastapi.testclient import TestClient
from app.database.models import Repository, ScheduledJob


@pytest.mark.unit
class TestConfigExportTimestamps:
    """Test that exported filenames include timestamps"""

    def test_single_yaml_export_has_timestamp(self, test_client: TestClient, admin_headers, test_db):
        """Test that single YAML export filename has timestamp prefix"""
        # Create a test repository
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            repository_type="local",
            encryption="none"
        )
        test_db.add(repo)
        test_db.commit()

        # Export configuration
        response = test_client.post(
            "/api/config/export/borgmatic",
            json={
                "repository_ids": [repo.id],
                "include_schedules": True
            },
            headers=admin_headers
        )

        assert response.status_code == 200

        # Check Content-Disposition header contains timestamp
        content_disposition = response.headers.get("Content-Disposition")
        assert content_disposition is not None

        # Extract filename from Content-Disposition header
        # Format: attachment; filename=YYYY-MM-DD_HH-MM-SS_reponame.yaml
        filename_match = re.search(r'filename=([^\s;]+)', content_disposition)
        assert filename_match, "No filename found in Content-Disposition header"

        filename = filename_match.group(1)

        # Verify timestamp format: YYYY-MM-DD_HH-MM-SS
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_'
        assert re.match(timestamp_pattern, filename), \
            f"Filename '{filename}' does not start with timestamp in format YYYY-MM-DD_HH-MM-SS_"

        # Verify it ends with .yaml
        assert filename.endswith('.yaml'), f"Filename '{filename}' does not end with .yaml"

    def test_zip_export_has_timestamp(self, test_client: TestClient, admin_headers, test_db):
        """Test that ZIP export filename has timestamp prefix"""
        # Create multiple test repositories
        repo1 = Repository(
            name="Test Repo 1",
            path="/test/repo1",
            repository_type="local",
            encryption="none"
        )
        repo2 = Repository(
            name="Test Repo 2",
            path="/test/repo2",
            repository_type="local",
            encryption="none"
        )
        test_db.add(repo1)
        test_db.add(repo2)
        test_db.commit()

        # Export all configurations (should return ZIP with multiple repos)
        response = test_client.post(
            "/api/config/export/borgmatic",
            json={
                "repository_ids": [repo1.id, repo2.id],
                "include_schedules": True
            },
            headers=admin_headers
        )

        assert response.status_code == 200
        assert response.headers.get("Content-Type") == "application/zip"

        # Check Content-Disposition header contains timestamp
        content_disposition = response.headers.get("Content-Disposition")
        assert content_disposition is not None

        # Extract filename from Content-Disposition header
        # Format: attachment; filename=YYYY-MM-DD_HH-MM-SS_borgmatic-configs.zip
        filename_match = re.search(r'filename=([^\s;]+)', content_disposition)
        assert filename_match, "No filename found in Content-Disposition header"

        filename = filename_match.group(1)

        # Verify timestamp format: YYYY-MM-DD_HH-MM-SS
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_'
        assert re.match(timestamp_pattern, filename), \
            f"Filename '{filename}' does not start with timestamp in format YYYY-MM-DD_HH-MM-SS_"

        # Verify it ends with borgmatic-configs.zip
        assert filename.endswith('borgmatic-configs.zip'), \
            f"Filename '{filename}' does not end with borgmatic-configs.zip"

    def test_timestamp_format_is_sortable(self, test_client: TestClient, admin_headers, test_db):
        """Test that timestamp format allows chronological sorting by filename"""
        # Create a test repository
        repo = Repository(
            name="Sort Test",
            path="/test/sort",
            repository_type="local",
            encryption="none"
        )
        test_db.add(repo)
        test_db.commit()

        # Make two exports with a small delay
        import time

        response1 = test_client.post(
            "/api/config/export/borgmatic",
            json={"repository_ids": [repo.id], "include_schedules": True},
            headers=admin_headers
        )

        time.sleep(1)  # Wait 1 second to ensure different timestamp

        response2 = test_client.post(
            "/api/config/export/borgmatic",
            json={"repository_ids": [repo.id], "include_schedules": True},
            headers=admin_headers
        )

        # Extract both filenames
        filename1 = re.search(r'filename=([^\s;]+)',
                             response1.headers.get("Content-Disposition")).group(1)
        filename2 = re.search(r'filename=([^\s;]+)',
                             response2.headers.get("Content-Disposition")).group(1)

        # Verify first export has earlier timestamp (lexicographic sort)
        assert filename1 < filename2, \
            f"Filenames not chronologically sortable: {filename1} should be < {filename2}"

    def test_fallback_filename_has_timestamp(self, test_client: TestClient, admin_headers, test_db):
        """Test that fallback filename (when repo name is not sanitizable) has timestamp"""
        # Create a repository with special characters that will be sanitized away
        repo = Repository(
            name="###",  # Will be sanitized to empty string
            path="/test/special",
            repository_type="local",
            encryption="none"
        )
        test_db.add(repo)
        test_db.commit()

        response = test_client.post(
            "/api/config/export/borgmatic",
            json={"repository_ids": [repo.id], "include_schedules": True},
            headers=admin_headers
        )

        assert response.status_code == 200

        content_disposition = response.headers.get("Content-Disposition")
        filename = re.search(r'filename=([^\s;]+)', content_disposition).group(1)

        # Should use fallback with timestamp
        # Format: YYYY-MM-DD_HH-MM-SS_borgmatic-config.yaml
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_borgmatic-config\.yaml$'
        assert re.match(timestamp_pattern, filename), \
            f"Fallback filename '{filename}' does not match expected format"
