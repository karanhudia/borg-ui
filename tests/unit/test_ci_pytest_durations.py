"""Timing ingestion checks against real report files and CLI output."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import pytest_durations


def test_merges_testcase_totals_across_reports(tmp_path):
    first = tmp_path / "first.xml"
    first.write_text(
        '<testsuites><testsuite time="999"><testcase file="tests/a.py" time="1.25"/>'
        '<testcase file="tests/a.py" time="2.5"/>'
        '<testcase file="tests/b.py" time="0"/></testsuite></testsuites>'
    )
    second = tmp_path / "second.xml"
    second.write_text(
        '<testsuite><testcase file="tests/a.py" time="0.25"/>'
        '<testcase file="tests/c.py" time="3"/></testsuite>'
    )
    output = tmp_path / "history.json"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(pytest_durations.__file__)),
            str(first),
            str(second),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text()) == {"tests/a.py": 4, "tests/c.py": 3}


@pytest.mark.parametrize(
    "case",
    [
        '<testcase time="1"/>',
        '<testcase file="../a.py" time="1"/>',
        '<testcase file="/tmp/a.py" time="1"/>',
        '<testcase file="tests/a.py" time="nan"/>',
        '<testcase file="tests/a.py" time="inf"/>',
        '<testcase file="tests/a.py" time="-1"/>',
        '<testcase file="tests/a.py"/>',
        '<testcase file="tests/a.txt" time="1"/>',
        '<testcase file="tests/a.py" time="oops"/>',
    ],
)
def test_rejects_invalid_producer_testcases(tmp_path, case):
    report = tmp_path / "bad.xml"
    report.write_text(f"<testsuite>{case}</testsuite>")
    with pytest.raises(ValueError):
        pytest_durations.merge_junit_reports([report])


def test_malformed_xml_fails_cli_without_replacing_history(tmp_path):
    report = tmp_path / "bad.xml"
    report.write_text("<testsuites>")
    output = tmp_path / "history.json"
    output.write_text("previous history")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(pytest_durations.__file__)),
            str(report),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "bad.xml" in result.stderr
    assert output.read_text() == "previous history"


@pytest.mark.parametrize(
    "contents",
    [
        "{",
        "[]",
        '{"tests/a.py": -1}',
        '{"tests/a.py": NaN}',
        '{"tests/a.py": true}',
        '{"../a.py": 1}',
        '{"tests/a.py": 0}',
        '{"tests/a.py": "1"}',
    ],
)
def test_invalid_history_is_advisory_and_falls_back(tmp_path, contents):
    history = tmp_path / "history.json"
    history.write_text(contents)
    assert pytest_durations.load_durations(history) == {}


def test_missing_history_and_valid_history(tmp_path):
    history = tmp_path / "history.json"
    assert pytest_durations.load_durations(history) == {}
    history.write_text('{"tests/a.py": 1.25}')
    assert pytest_durations.load_durations(history) == {"tests/a.py": 1.25}


def test_real_pytest_report_includes_setup_and_teardown_time(tmp_path):
    test_file = tmp_path / "test_phases.py"
    test_file.write_text(
        "import time\nimport pytest\n"
        "@pytest.fixture\ndef phases():\n"
        "    time.sleep(0.04)\n    yield\n    time.sleep(0.04)\n"
        "def test_phases(phases):\n    time.sleep(0.01)\n"
    )
    report = tmp_path / "observed.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-q",
            "--junitxml",
            str(report),
            "-o",
            "junit_family=xunit1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    durations = pytest_durations.merge_junit_reports([report])
    assert durations["test_phases.py"] >= 0.08


@pytest.mark.parametrize("xml", ["<testsuite/>", "<other/>"])
def test_rejects_reports_without_testcases(tmp_path, xml):
    report = tmp_path / "empty.xml"
    report.write_text(xml)
    with pytest.raises(ValueError):
        pytest_durations.merge_junit_reports([report])


def test_merger_cli_creates_output_parent_directory(tmp_path):
    report = tmp_path / "report.xml"
    report.write_text('<testsuite><testcase file="tests/a.py" time="1"/></testsuite>')
    output = tmp_path / "ci-timings" / "history.json"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(pytest_durations.__file__)),
            str(report),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text()) == {"tests/a.py": 1}
