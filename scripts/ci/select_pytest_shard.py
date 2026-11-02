#!/usr/bin/env python3
"""Select a balanced pytest file shard from collected node IDs."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable

try:
    from .pytest_durations import load_durations
except ImportError:  # Direct execution and importlib-based test loading.
    if __name__ == "__main__":
        from pytest_durations import load_durations
    else:
        from scripts.ci.pytest_durations import load_durations


def count_tests_by_file(lines: Iterable[str]) -> dict[str, int]:
    """Count collected pytest node IDs by their owning test file."""
    counts: dict[str, int] = {}

    for raw_line in lines:
        line = raw_line.strip()
        if "::" not in line:
            continue

        test_file = line.split("::", 1)[0]
        if not test_file.endswith(".py"):
            continue

        counts[test_file] = counts.get(test_file, 0) + 1

    return counts


def select_shard(
    test_counts: dict[str, int],
    *,
    shard_index: int,
    shard_total: int,
    durations: dict[str, float] | None = None,
) -> list[str]:
    """Return the test files assigned to one balanced one-based shard."""
    if shard_total < 1:
        raise ValueError("shard_total must be at least 1")
    if shard_index < 1 or shard_index > shard_total:
        raise ValueError("shard_index must be between 1 and shard_total")
    if not test_counts:
        raise ValueError("No pytest test nodes found in input")

    shard_paths: list[list[str]] = [[] for _ in range(shard_total)]
    shard_weights = [0.0 for _ in range(shard_total)]

    known = {
        path: seconds
        for path, seconds in (durations or {}).items()
        if path in test_counts
    }
    seconds_per_test = (
        sum(known.values()) / sum(test_counts[path] for path in known) if known else 1.0
    )
    weights = {
        path: known.get(path, count * seconds_per_test)
        for path, count in test_counts.items()
    }

    files_by_weight = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    for test_file, weight in files_by_weight:
        target_index = min(
            range(shard_total),
            key=lambda index: (shard_weights[index], index),
        )
        shard_paths[target_index].append(test_file)
        shard_weights[target_index] += weight

    selected = set(shard_paths[shard_index - 1])
    return [test_file for test_file in test_counts if test_file in selected]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments for shard selection."""
    parser = argparse.ArgumentParser(
        description="Select pytest test files for one balanced CI shard.",
    )
    parser.add_argument(
        "--durations-file",
        help="Optional JSON file of historical test-file seconds; invalid history is ignored.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        required=True,
        help="One-based shard index to select.",
    )
    parser.add_argument(
        "--shard-total",
        type=int,
        required=True,
        help="Total number of shards.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the shard selector CLI."""
    args = parse_args(argv if argv is not None else sys.argv[1:])
    test_counts = count_tests_by_file(sys.stdin)

    try:
        selected_files = select_shard(
            test_counts,
            shard_index=args.shard_index,
            shard_total=args.shard_total,
            durations=load_durations(args.durations_file)
            if args.durations_file
            else None,
        )
    except ValueError as exc:
        print(f"select_pytest_shard.py: {exc}", file=sys.stderr)
        return 2

    selected_test_count = sum(test_counts[test_file] for test_file in selected_files)
    total_test_count = sum(test_counts.values())
    print(
        "Selected shard "
        f"{args.shard_index}/{args.shard_total}: "
        f"{len(selected_files)} files, "
        f"{selected_test_count}/{total_test_count} tests",
        file=sys.stderr,
    )

    for test_file in selected_files:
        print(test_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
