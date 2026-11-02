#!/usr/bin/env python3
"""Merge pytest xunit1 testcase totals into advisory per-file timing history."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree


def valid_test_path(value: object) -> bool:
    """Accept canonical repository-relative Python paths only."""
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and str(path) == value
        and path.suffix == ".py"
        and not any(ord(character) < 32 for character in value)
    )


def load_durations(path: Path | str) -> dict[str, float]:
    """Load positive finite seconds; unusable history falls back to test counts."""
    try:
        values = json.loads(Path(path).read_text())
        if not isinstance(values, dict):
            raise ValueError("expected a JSON object")
        durations: dict[str, float] = {}
        for test_file, seconds in values.items():
            if (
                not valid_test_path(test_file)
                or isinstance(seconds, bool)
                or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds)
                or seconds <= 0
            ):
                raise ValueError(f"invalid duration for {test_file!r}")
            durations[test_file] = float(seconds)
        return durations
    except (OSError, ValueError, OverflowError) as exc:
        print(f"Ignoring pytest timing history {path}: {exc}", file=sys.stderr)
        return {}


def merge_junit_reports(paths: Iterable[Path | str]) -> dict[str, float]:
    """Sum testcase times, including pytest's default setup/call/teardown total."""
    durations: dict[str, float] = {}
    for path in paths:
        try:
            root = ElementTree.parse(path).getroot()
            if root.tag not in {"testsuites", "testsuite"}:
                raise ValueError("expected a JUnit testsuite or testsuites root")
            cases = list(root.iter("testcase"))
            if not cases:
                raise ValueError("report contains no testcases")
            for case in cases:
                test_file = case.get("file")
                if not valid_test_path(test_file):
                    raise ValueError(
                        f"invalid testcase file {test_file!r}; use junit_family=xunit1"
                    )
                seconds = float(case.attrib["time"])
                if not math.isfinite(seconds) or seconds < 0:
                    raise ValueError(f"invalid testcase duration {seconds!r}")
                total = durations.get(test_file, 0.0) + seconds
                if not math.isfinite(total):
                    raise ValueError(f"duration overflow for {test_file!r}")
                durations[test_file] = total
        except (OSError, ElementTree.ParseError, ValueError, KeyError) as exc:
            raise ValueError(f"Invalid JUnit report {path}: {exc}") from exc
    # Zero-time files have no usable measurement and use calibrated fallback.
    return {path: seconds for path, seconds in sorted(durations.items()) if seconds > 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        durations = merge_junit_reports(args.reports)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(durations, indent=2, sort_keys=True) + "\n")
    except (ValueError, OSError) as exc:
        print(f"pytest_durations.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
