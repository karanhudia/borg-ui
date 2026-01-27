"""
Pytest configuration and fixtures for Borg UI tests

This is the main conftest.py that configures pytest and imports
fixtures from the fixtures/ directory.
"""
import pytest
import asyncio
import os
import sys
import tempfile
import warnings

# Suppress asyncio ResourceWarning for unclosed transports during test cleanup
# This is a known issue in Python 3.9+ where subprocess transports may not be
# fully cleaned up before the event loop closes
warnings.filterwarnings("ignore", message="unclosed transport", category=ResourceWarning)
warnings.filterwarnings("ignore", message="unclosed", category=ResourceWarning, module="asyncio")

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
    """Create an event loop for the entire test session.

    This prevents 'Event loop is closed' errors by keeping a single
    event loop alive for all async tests in the session.
    """
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    # Properly shut down async generators and pending tasks
    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())
    except Exception:
        pass
    loop.close()


def pytest_sessionfinish(session, exitstatus):
    """Clean up asyncio after all tests complete.

    This suppresses 'Event loop is closed' errors that occur during
    garbage collection of subprocess transports in Python 3.9+.
    """
    import gc
    import warnings

    # Temporarily suppress ResourceWarnings during cleanup
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=ResourceWarning)
        # Force garbage collection while we still have control
        gc.collect()

    # Set event loop to None to prevent closed loop access during final GC
    asyncio.set_event_loop(None)





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
