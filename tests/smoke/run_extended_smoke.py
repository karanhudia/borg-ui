#!/usr/bin/env python3
"""Run the slower live-server smoke checks against a built Borg UI instance."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_script(*args: str) -> int:
    cmd = [sys.executable, *args]
    print(f"\n==> Running {' '.join(args)}")
    completed = subprocess.run(cmd, cwd=ROOT)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Borg UI extended smoke tests")
    parser.add_argument("--url", default="http://localhost:8082", help="Base URL of the running app")
    parser.add_argument(
        "--test-dir",
        default="/tmp/borg-ui-tests",
        help="Prepared Borg smoke test directory",
    )
    args = parser.parse_args()

    failures = []
    scripts = [
        ("tests/smoke/test_borg2_api_smoke.py", "--url", args.url),
        ("tests/smoke/test_borg2_archive_browse_smoke.py", "--url", args.url),
        ("tests/smoke/test_borg2_backup_contract_smoke.py", "--url", args.url),
        ("tests/smoke/test_encrypted_repo_smoke.py", "--url", args.url),
        ("tests/smoke/test_maintenance_smoke.py", "--url", args.url),
        ("tests/smoke/test_restore_cancel_smoke.py", "--url", args.url),
        ("tests/smoke/test_delete_cancel_smoke.py", "--url", args.url),
        ("tests/smoke/test_mount_smoke.py", "--url", args.url),
        ("tests/smoke/test_remote_ssh_smoke.py", "--url", args.url),
        ("tests/integration/test_multiple_source_dirs.py", "--url", args.url),
        ("tests/integration/test_archive_contents.py", args.test_dir, "--url", args.url),
        ("tests/integration/test_archive_directory_browsing.py", "--url", args.url),
    ]

    for script in scripts:
        if run_script(*script) != 0:
            failures.append(" ".join(script))

    if failures:
        print("\nExtended smoke suite failed:")
        for script in failures:
            print(f" - {script}")
        return 1

    print("\nExtended smoke suite passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
