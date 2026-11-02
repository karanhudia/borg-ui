#!/usr/bin/env python3
"""Require the exact complete shard artifact inventory before coverage combine."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def verify_directory(directory: Path, *, shards: int, suffix: str) -> None:
    expected = {f"unit-{index}.{suffix}" for index in range(1, shards + 1)}
    actual = {entry.name for entry in directory.iterdir()}
    if actual != expected:
        raise ValueError(
            f"{directory}: missing {sorted(expected - actual)}, "
            f"unexpected {sorted(actual - expected)}"
        )
    for name in sorted(expected):
        report = directory / name
        if report.is_symlink() or not report.is_file() or report.stat().st_size == 0:
            raise ValueError(f"{report}: expected a nonempty regular shard report")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shards", type=int, required=True)
    parser.add_argument("--junit-dir", type=Path, required=True)
    parser.add_argument("--coverage-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.shards < 1:
            raise ValueError("shard count must be positive")
        verify_directory(args.junit_dir, shards=args.shards, suffix="xml")
        verify_directory(args.coverage_dir, shards=args.shards, suffix="coverage")
    except (OSError, ValueError) as exc:
        print(f"Invalid shard reports: {exc}", file=sys.stderr)
        return 2
    print(f"Verified all {args.shards} JUnit and coverage shard reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
