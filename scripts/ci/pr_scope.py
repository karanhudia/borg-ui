#!/usr/bin/env python3
"""Allow backend skips only for a complete, unambiguous frontend-only PR diff."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath

FRONTEND_ONLY = (
    "frontend/src/",
    "frontend/.storybook/",
    "frontend/scripts/",
    "frontend/public/",
)


def backend_required(diff: bytes) -> bool:
    """Parse git's NUL name-status format, conservatively rejecting ambiguity."""
    if not diff or not diff.endswith(b"\0"):
        return True
    try:
        fields = diff[:-1].decode("utf-8", errors="strict").split("\0")
    except UnicodeDecodeError:
        return True
    if len(fields) % 2:
        return True
    for status, name in zip(fields[::2], fields[1::2]):
        # Renames/copies/type changes deliberately require all checks, even if
        # both names look like frontend paths. Added/deleted files are included.
        if status not in {"A", "M", "D"}:
            return True
        path = PurePosixPath(name)
        if (
            not name.startswith(FRONTEND_ONLY)
            or str(path) != name
            or ".." in path.parts
            or "\\" in name
        ):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    required = True
    if args.event == "pull_request" and args.base and args.head:
        try:
            diff = subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-status",
                    "-z",
                    "--find-renames",
                    f"{args.base}...{args.head}",
                    "--",
                ],
                check=True,
                capture_output=True,
            ).stdout
            required = backend_required(diff)
        except (OSError, subprocess.CalledProcessError):
            # Metadata failures must increase testing, never reduce it.
            pass
    print(f"backend={str(required).lower()}")


if __name__ == "__main__":
    main()
