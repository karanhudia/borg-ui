"""scratch_tools leaves the real tools registered, whatever the test order."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()


@pytest.mark.unit
def test_real_tools_are_registered():
    """The probe for the test below; on its own it always passes."""
    from app.mcp import tools  # noqa: F401
    from app.mcp.registry import REGISTRY

    assert "get_overview" in REGISTRY


@pytest.mark.unit
def test_real_tools_outlive_a_scratch_tools_test_that_first_imports_them():
    # A fresh interpreter, so the real tools are first imported inside a
    # scratch_tools test, as on a worker whose earlier files never imported
    # them. Without the xdist worker variables the child does not take over
    # this worker's databases.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTEST_") and key != "BORG_TEST_POSTGRES_URL"
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "tests/unit/mcp/test_registry.py::test_top_level_follows_the_registered_tools",
            f"{HERE}::test_real_tools_are_registered",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
