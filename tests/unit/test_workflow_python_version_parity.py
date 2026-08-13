"""Guard: CI must test on the same Python the runtime ships.

``docker/runtime-base.env`` is the single source of truth for the runtime's
Python version. If a workflow pins a different version, CI would validate the
code against a Python the product never runs on — a silent drift bug. This test
turns that drift into a build failure.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_BASE_ENV = REPO_ROOT / "docker" / "runtime-base.env"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_VERSION = r'["\'](\d+(?:\.\d+)+)["\']'
# ``PYTHON_VERSION: "3.12"`` (workflow-level env) and
# ``python-version: "3.12"`` (a direct literal pin). The expression form
# ``python-version: ${{ env.PYTHON_VERSION }}`` resolves to the env value and
# is intentionally not matched here.
_PIN_PATTERNS = (
    re.compile(r"PYTHON_VERSION:\s*" + _VERSION),
    re.compile(r"python-version:\s*" + _VERSION),
)


def _source_of_truth() -> str:
    for line in RUNTIME_BASE_ENV.read_text().splitlines():
        if line.startswith("PYTHON_VERSION="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("PYTHON_VERSION missing from docker/runtime-base.env")


def test_workflow_python_pins_match_runtime_base_env():
    expected = _source_of_truth()

    mismatches = []
    matched = 0
    for workflow in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = workflow.read_text()
        for pattern in _PIN_PATTERNS:
            for version in pattern.findall(text):
                matched += 1
                if version != expected:
                    mismatches.append(f"{workflow.name}: {version}")

    assert not mismatches, (
        f"workflow Python pin(s) differ from docker/runtime-base.env "
        f"(PYTHON_VERSION={expected}): {', '.join(mismatches)}"
    )
    # Fail loudly if the patterns stopped matching anything — otherwise the
    # guard would pass vacuously after a syntax change in the workflows.
    assert matched >= 4, (
        f"expected to find at least 4 Python pins across workflows, found {matched}"
    )
