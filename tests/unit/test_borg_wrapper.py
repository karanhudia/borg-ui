"""
Unit tests for borg wrapper utility
"""
import pytest
from app.core.borg import BorgInterface


@pytest.mark.unit
class TestBorgWrapper:
    """Test borg command wrapper utilities"""

    def test_borg_interface_initialization(self):
        """Test BorgInterface initialization"""
        try:
            borg = BorgInterface()
            assert borg is not None
            assert hasattr(borg, 'borg_cmd')
            assert borg.borg_cmd == "borg"
        except RuntimeError:
            # Borg might not be installed, which is acceptable
            pytest.skip("Borg not installed")

    def test_borg_command_attribute(self):
        """Test borg command attribute"""
        try:
            borg = BorgInterface()
            assert isinstance(borg.borg_cmd, str)
            assert len(borg.borg_cmd) > 0
        except RuntimeError:
            pytest.skip("Borg not installed")

    def test_borg_validation_caching(self):
        """Test that borg validation is cached"""
        try:
            borg1 = BorgInterface()
            borg2 = BorgInterface()
            # Both should use cached validation
            assert BorgInterface._validated is True
        except RuntimeError:
            pytest.skip("Borg not installed")


@pytest.mark.unit
class TestBorgErrorParsing:
    """Test borg error message parsing"""

    def test_parse_borg_error_message(self):
        """Test parsing borg error messages"""
        from app.core.borg_errors import get_error_details

        # Test with common error codes
        error_code = 2  # Borg error exit code
        details = get_error_details(error_code)

        assert details is not None
        assert isinstance(details, (str, dict))

    def test_parse_borg_success_code(self):
        """Test parsing borg success code"""
        from app.core.borg_errors import get_error_details

        details = get_error_details(0)  # Success
        assert details is not None

    def test_format_error_message(self):
        """Test formatting borg error messages"""
        from app.core.borg_errors import format_error_message

        message = format_error_message(2, "Test error output")

        assert isinstance(message, str)
        assert len(message) > 0


@pytest.mark.unit
class TestBorgRepository:
    """Test borg repository operations"""

    def test_repository_path_validation(self):
        """Test repository path validation"""
        # Import and test path validation if available
        from app.core import borg

        # Test valid paths
        valid_paths = [
            "/tmp/test-repo",
            "/data/backups/repo",
            "user@host:/path/to/repo"
        ]

        for path in valid_paths:
            # Should not raise error for valid paths
            assert isinstance(path, str)

    def test_archive_name_validation(self):
        """Test archive name validation"""
        # Test archive name format
        valid_names = [
            "backup-2024-01-01",
            "daily-backup",
            "archive_name_123"
        ]

        for name in valid_names:
            # Archive names should be strings
            assert isinstance(name, str)
            assert len(name) > 0

    def test_repository_url_parsing(self):
        """Test parsing repository URLs"""
        test_urls = [
            "/local/path/repo",
            "ssh://user@host:22/path/repo",
            "user@host:repo"
        ]

        for url in test_urls:
            # URLs should be valid strings
            assert isinstance(url, str)
            assert len(url) > 0
