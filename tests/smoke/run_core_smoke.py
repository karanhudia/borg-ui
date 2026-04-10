#!/usr/bin/env python3
"""Run the fast live-server smoke checks against a built Borg UI instance."""

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
    parser = argparse.ArgumentParser(description="Run Borg UI core smoke tests")
    parser.add_argument("--url", default="http://localhost:8082", help="Base URL of the running app")
    args = parser.parse_args()

    failures = []
    scripts = [
        ("tests/manual/test_app.py", "--url", args.url),
        ("tests/smoke/test_borg_api_smoke.py", "--url", args.url),
        ("tests/smoke/test_backup_contract_smoke.py", "--url", args.url),
        ("tests/smoke/test_backup_cancel_smoke.py", "--url", args.url),
        ("tests/smoke/test_schedule_run_now_smoke.py", "--url", args.url),
        ("tests/smoke/test_permissions_failure_smoke.py", "--url", args.url),
        ("tests/smoke/test_failed_backup_logs_smoke.py", "--url", args.url),
    ]

    for script in scripts:
        if run_script(*script) != 0:
            failures.append(" ".join(script))

    if failures:
        print("\nCore smoke suite failed:")
        for script in failures:
            print(f" - {script}")
        return 1

    print("\nCore smoke suite passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
