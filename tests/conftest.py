"""
Pytest configuration and fixtures for Borg UI tests

This is the main conftest.py that configures pytest and imports
fixtures from the fixtures/ directory.
"""
import pytest
import os
import sys
import tempfile

# Set up test environment variables BEFORE importing app modules
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="borg-test-data-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.environ['DATA_DIR']}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["ENVIRONMENT"] = "test"
os.environ["BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK"] = "yes"
os.environ["BORG_RELOCATED_REPO_ACCESS_IS_OK"] = "yes"

# Add parent directory to path so we can import from app/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import fixtures from fixtures directory
pytest_plugins = [
    "tests.fixtures.database",
    "tests.fixtures.api",
    "tests.fixtures.borg",
]


@pytest.fixture(scope="session")
def event_loop():
    """
    Create an instance of the default event loop for the session.
    Fixes 'RuntimeError: Event loop is closed' when using async fixtures/subprocesses.
    """
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require external dependencies"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that require running services"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take a long time to run"
    )
    config.addinivalue_line(
        "markers", "requires_borg: Tests that require borg binary to be installed"
    )
    config.addinivalue_line(
        "markers", "requires_ui: Tests that require Borg UI to be running"
    )


@pytest.fixture(scope="session")
def test_base_url():
    """Get the base URL for testing from environment or use default"""
    return os.environ.get("TEST_BASE_URL", "http://localhost:8082")


@pytest.fixture(scope="session")
def test_directory():
    """Get the test directory path"""
    return os.environ.get("TEST_DIRECTORY", "/tmp/borg-ui-tests")


@pytest.fixture(scope="session")
def admin_credentials():
    """Default admin credentials for testing"""
    return {
        "username": os.environ.get("TEST_ADMIN_USER", "admin"),
        "password": os.environ.get("TEST_ADMIN_PASSWORD", "admin123")
    }


@pytest.fixture
def borg_available():
    """Check if borg is available on the system"""
    import shutil
    return shutil.which("borg") is not None


@pytest.fixture
def skip_if_no_borg(borg_available):
    """Skip test if borg is not available"""
    if not borg_available:
        pytest.skip("Borg binary not found. Install borgbackup to run this test.")


@pytest.fixture
def temp_test_dir(tmp_path):
    """Create a temporary test directory"""
    test_dir = tmp_path / "borg-test"
    test_dir.mkdir()
    return str(test_dir)
