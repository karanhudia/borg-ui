#!/usr/bin/env python3
"""Gate `npm audit --json` against a tracked allowlist of non-applicable findings.

npm audit has no `--ignore-vuln`, so — unlike pip-audit — the allowlist cannot be
passed to the tool. This mirrors scripts/pip_audit_known_vulns.py in spirit: it
reads the audit JSON, drops advisories whose GHSA id is tracked in
security/npm-audit-known-vulns.json, and fails only if a non-allowlisted advisory
at or above the chosen level remains. Every tracked entry carries a reason, so the
allowlist is an audited record, not a silent mute.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_KNOWN_VULNS_FILE = (
    Path(__file__).resolve().parents[1] / "security" / "npm-audit-known-vulns.json"
)
SEVERITY_ORDER = ["info", "low", "moderate", "high", "critical"]
GHSA_RE = re.compile(r"GHSA-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}", re.IGNORECASE)


def load_known_vulns(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")

    known_vulns: list[dict[str, Any]] = []
    for index, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"known vuln entry {index} must be a JSON object")

        vuln_id = str(entry.get("id", "")).strip()
        if not vuln_id:
            raise ValueError(f"known vuln entry {index} must include a non-empty id")
        if any(char.isspace() for char in vuln_id):
            raise ValueError(f"known vuln entry {index} id must not contain whitespace")

        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                f"known vuln entry {index} ({vuln_id}) must include a non-empty "
                "reason — the allowlist is an audited record, not a silent mute"
            )

        known_vulns.append({**entry, "id": vuln_id})

    return known_vulns


def validate_report(report: Any) -> dict[str, Any]:
    """Reject an npm audit result that did not actually run.

    A successful `npm audit --json` (v2) is an object with a `vulnerabilities`
    map. npm emits `{"error": ...}` on failures (network, registry, bad flags),
    and the workflow ignores the audit exit code — so without this a failed or
    truncated audit would parse into zero advisories and pass as clean. Fail
    loudly instead of reporting a green gate on an audit that never happened.
    """
    if not isinstance(report, dict):
        raise ValueError("npm audit report is not a JSON object")
    if "error" in report:
        error = report["error"]
        summary = error.get("summary", error) if isinstance(error, dict) else error
        raise ValueError(f"npm audit reported an error: {summary}")
    if not isinstance(report.get("vulnerabilities"), dict):
        raise ValueError(
            "npm audit report has no 'vulnerabilities' object — a failed, empty, "
            "or unexpected report shape; refusing to report clean"
        )
    return report


def advisories_at_or_above(report: dict[str, Any], level: str) -> list[dict[str, str]]:
    """Distinct advisories in a validated `npm audit --json` report at or above
    `level`.

    Real advisories are the object-valued entries in each package's `via`; a
    string `via` is just a transitive pointer to another package and carries no
    advisory of its own. The report is assumed validated (see validate_report):
    `vulnerabilities` is indexed directly, never defaulted to empty.
    """
    threshold = SEVERITY_ORDER.index(level)
    found: dict[str, dict[str, str]] = {}
    for package in report["vulnerabilities"].values():
        for via in package.get("via", []):
            if not isinstance(via, dict):
                continue
            severity = via.get("severity", "info")
            if SEVERITY_ORDER.index(severity) < threshold:
                continue
            match = GHSA_RE.search(via.get("url", "") or "")
            ghsa = match.group(0) if match else str(via.get("url", ""))
            found[ghsa] = {
                "id": ghsa,
                "severity": severity,
                "title": str(via.get("title", "")),
            }
    return list(found.values())


def non_allowlisted(
    report: dict[str, Any], known_vulns: list[dict[str, Any]], level: str
) -> list[dict[str, str]]:
    allowed = {entry["id"] for entry in known_vulns}
    return [a for a in advisories_at_or_above(report, level) if a["id"] not in allowed]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate npm audit against an allowlist.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gate = subparsers.add_parser(
        "gate", help="Fail on non-allowlisted advisories at or above --level."
    )
    gate.add_argument(
        "--file", type=Path, help="npm audit --json output (default: read stdin)."
    )
    gate.add_argument("--level", default="moderate", choices=SEVERITY_ORDER)
    gate.add_argument("--known-vulns", type=Path, default=DEFAULT_KNOWN_VULNS_FILE)

    args = parser.parse_args(argv)
    if args.command != "gate":
        parser.error(f"unsupported command: {args.command}")

    raw = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        report = validate_report(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"npm audit did not produce a usable report: {exc}", file=sys.stderr)
        return 1

    known_vulns = load_known_vulns(args.known_vulns)
    allowed = {entry["id"] for entry in known_vulns}

    remaining = []
    for advisory in advisories_at_or_above(report, args.level):
        if advisory["id"] in allowed:
            print(f"ignored (allowlisted): {advisory['id']} {advisory['title']}")
        else:
            remaining.append(advisory)
            print(
                f"FAIL: {advisory['id']} [{advisory['severity']}] {advisory['title']}",
                file=sys.stderr,
            )

    if remaining:
        print(
            f"{len(remaining)} non-allowlisted advisory(ies) at or above "
            f"'{args.level}' — see security/npm-audit-known-vulns.json to track a "
            "reviewed, non-applicable one.",
            file=sys.stderr,
        )
        return 1
    print(f"npm audit clean at or above '{args.level}' (allowlist applied).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
