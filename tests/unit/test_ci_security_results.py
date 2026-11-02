"""Consolidating security scans must not allow failed or omitted gates to pass."""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATES = [
    "path-checker-self-test",
    "personal-paths",
    "npm-audit",
    "pip-audit",
    "trivy-fs",
]


def module():
    spec = importlib.util.spec_from_file_location(
        "check_security_results", ROOT / "scripts/ci/check_security_results.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_all_security_gates_must_succeed():
    assert module().failures({name: {"outcome": "success"} for name in GATES}) == []


@pytest.mark.parametrize("name", GATES)
@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped", "missing"])
def test_any_failed_cancelled_skipped_or_missing_scan_fails_summary(name, outcome):
    results = {key: {"outcome": "success"} for key in GATES}
    if outcome == "missing":
        del results[name]
    else:
        results[name]["outcome"] = outcome
    assert module().failures(results)


def test_all_required_scan_steps_run_after_an_earlier_failure():
    jobs = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())["jobs"]
    assert set(jobs) == {"security-summary", "trivy-docker"}
    steps = {s.get("id"): s for s in jobs["security-summary"]["steps"] if s.get("id")}
    assert all(steps[name].get("if") == "${{ !cancelled() }}" for name in GATES)
    assert all(not steps[name].get("continue-on-error", False) for name in GATES)
    final = jobs["security-summary"]["steps"][-1]
    assert final["if"] == "always()"
    assert "check_security_results.py" in final["run"]
