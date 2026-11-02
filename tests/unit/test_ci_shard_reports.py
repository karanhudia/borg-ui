"""Missing or ambiguous shard artifacts must never produce partial coverage."""

from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ci/verify_shard_reports.py"


def reports(tmp_path, shards=6):
    junit = tmp_path / "junit"
    coverage = tmp_path / "coverage"
    junit.mkdir()
    coverage.mkdir()
    for index in range(1, shards + 1):
        (junit / f"unit-{index}.xml").write_text("<testsuite/>")
        (coverage / f"unit-{index}.coverage").write_bytes(b"coverage database")
    return junit, coverage


def verify(junit, coverage, shards=6):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--shards",
            str(shards),
            "--junit-dir",
            str(junit),
            "--coverage-dir",
            str(coverage),
        ],
        capture_output=True,
        text=True,
    )


def test_complete_six_shard_artifacts_pass(tmp_path):
    junit, coverage = reports(tmp_path)
    result = verify(junit, coverage)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kind", ["junit", "coverage"])
@pytest.mark.parametrize("damage", ["missing", "empty", "extra", "nested", "symlink"])
def test_incomplete_or_ambiguous_shard_reports_fail_closed(tmp_path, kind, damage):
    junit, coverage = reports(tmp_path)
    directory, suffix = (junit, "xml") if kind == "junit" else (coverage, "coverage")
    report = directory / f"unit-6.{suffix}"
    if damage == "missing":
        report.unlink()
    elif damage == "empty":
        report.write_bytes(b"")
    elif damage == "extra":
        (directory / f"unit-7.{suffix}").write_bytes(b"unexpected shard")
    elif damage == "nested":
        (directory / "nested").mkdir()
        report.rename(directory / "nested" / report.name)
    else:
        report.unlink()
        report.symlink_to(directory / f"unit-1.{suffix}")
    result = verify(junit, coverage)
    assert result.returncode != 0
    assert "shard reports" in result.stderr


def test_wrong_shard_index_cannot_replace_missing_report(tmp_path):
    junit, coverage = reports(tmp_path)
    (coverage / "unit-6.coverage").rename(coverage / "unit-0.coverage")
    result = verify(junit, coverage)
    assert result.returncode != 0
    assert "unit-6.coverage" in result.stderr


def test_invalid_shard_total_is_rejected(tmp_path):
    junit, coverage = reports(tmp_path)
    assert verify(junit, coverage, shards=0).returncode != 0


def test_missing_artifact_directory_fails_closed(tmp_path):
    result = verify(tmp_path / "missing-junit", tmp_path / "missing-coverage")
    assert result.returncode != 0
    assert "shard reports" in result.stderr
