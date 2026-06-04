#!/usr/bin/env python3
"""Render tracked no-fix pip-audit findings as CLI ignore arguments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_KNOWN_VULNS_FILE = (
    Path(__file__).resolve().parents[1] / "security" / "pip-audit-known-vulns.json"
)


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

        known_vulns.append({**entry, "id": vuln_id})

    return known_vulns


def build_ignore_args(known_vulns: list[dict[str, Any]]) -> list[str]:
    ignore_args: list[str] = []
    for entry in known_vulns:
        ignore_args.extend(["--ignore-vuln", entry["id"]])
    return ignore_args


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render tracked no-fix pip-audit findings."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ignore_args_parser = subparsers.add_parser(
        "ignore-args",
        help="Print one pip-audit ignore argument per line for shell arrays.",
    )
    ignore_args_parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_KNOWN_VULNS_FILE,
        help="Path to the tracked known vulnerabilities JSON file.",
    )

    args = parser.parse_args(argv)
    if args.command == "ignore-args":
        for value in build_ignore_args(load_known_vulns(args.file)):
            print(value)
        return 0

    parser.error(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
