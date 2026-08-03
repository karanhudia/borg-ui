"""The npm-audit allowlist gate must drop only tracked, reasoned advisories."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.npm_audit_known_vulns import (
    DEFAULT_KNOWN_VULNS_FILE,
    advisories_at_or_above,
    load_known_vulns,
    main,
    non_allowlisted,
    validate_report,
)

REPORT = {
    "vulnerabilities": {
        "react-router": {
            "via": [
                {
                    "severity": "high",
                    "url": "https://github.com/advisories/GHSA-qwww-vcr4-c8h2",
                    "title": "RSC Mode CSRF Bypass",
                }
            ]
        },
        # A transitive pointer, not an advisory of its own.
        "react-router-dom": {"via": ["react-router"]},
        "something-low": {
            "via": [
                {
                    "severity": "low",
                    "url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
                    "title": "A low one",
                }
            ]
        },
    }
}


def test_only_real_advisories_at_or_above_level_are_collected():
    got = advisories_at_or_above(REPORT, "moderate")
    # The transitive string `via` and the low-severity advisory are excluded.
    assert [a["id"] for a in got] == ["GHSA-qwww-vcr4-c8h2"]


def test_a_lower_level_widens_the_net():
    ids = {a["id"] for a in advisories_at_or_above(REPORT, "low")}
    assert ids == {"GHSA-qwww-vcr4-c8h2", "GHSA-aaaa-bbbb-cccc"}


def test_an_allowlisted_advisory_is_dropped():
    assert non_allowlisted(REPORT, [{"id": "GHSA-qwww-vcr4-c8h2"}], "moderate") == []


def test_a_non_allowlisted_advisory_survives():
    remaining = non_allowlisted(REPORT, [], "moderate")
    assert [a["id"] for a in remaining] == ["GHSA-qwww-vcr4-c8h2"]


def test_load_rejects_an_entry_without_an_id(tmp_path: Path):
    bad = tmp_path / "known.json"
    bad.write_text('[{"package": "react-router", "reason": "x"}]', encoding="utf-8")
    with pytest.raises(ValueError):
        load_known_vulns(bad)


def test_load_rejects_an_entry_without_a_reason(tmp_path: Path):
    bad = tmp_path / "known.json"
    bad.write_text('[{"id": "GHSA-qwww-vcr4-c8h2"}]', encoding="utf-8")
    with pytest.raises(ValueError):
        load_known_vulns(bad)


def test_the_tracked_allowlist_loads_and_every_entry_carries_a_reason():
    known = load_known_vulns(DEFAULT_KNOWN_VULNS_FILE)
    assert any(e["id"] == "GHSA-qwww-vcr4-c8h2" for e in known)
    for entry in known:
        assert entry.get("reason"), f"{entry['id']} must carry a reason"


def test_validate_report_rejects_an_error_payload():
    with pytest.raises(ValueError, match="error"):
        validate_report({"error": {"summary": "request to registry failed"}})


def test_validate_report_rejects_a_report_without_vulnerabilities():
    # A failed or truncated audit — must not be treated as clean.
    with pytest.raises(ValueError):
        validate_report({"metadata": {"vulnerabilities": {}}})


def test_validate_report_rejects_a_non_object():
    with pytest.raises(ValueError):
        validate_report([])


def test_validate_report_accepts_a_genuinely_clean_report():
    report = {"vulnerabilities": {}, "metadata": {}}
    assert validate_report(report) is report


def test_gate_fails_on_an_error_report(tmp_path: Path, capsys):
    report = tmp_path / "audit.json"
    report.write_text(
        '{"error": {"summary": "registry unreachable"}}', encoding="utf-8"
    )
    assert main(["gate", "--file", str(report), "--level", "moderate"]) == 1
    assert "did not produce a usable report" in capsys.readouterr().err


def test_gate_fails_on_empty_output(tmp_path: Path):
    report = tmp_path / "audit.json"
    report.write_text("", encoding="utf-8")
    assert main(["gate", "--file", str(report), "--level", "moderate"]) == 1


def test_gate_is_clean_on_a_valid_empty_report(tmp_path: Path):
    report = tmp_path / "audit.json"
    report.write_text('{"vulnerabilities": {}, "metadata": {}}', encoding="utf-8")
    assert main(["gate", "--file", str(report), "--level", "moderate"]) == 0
