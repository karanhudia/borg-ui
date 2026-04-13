#!/usr/bin/env python3
"""Black-box smoke coverage for manual backup cancellation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backup cancel smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "cancel-source",
            {"notes/readme.txt": "cancel smoke\n"},
        )
        client.write_incompressible_file(source_root / "large.bin", size_mb=96)

        repo_id, repo_path = client.create_repository(
            name="Cancel Smoke Repo",
            repo_path=client.temp_dir / "cancel-repo",
            source_dirs=[source_root],
        )

        job_id = client.start_backup(repo_path)
        client.wait_for_running("/api/backup/status", job_id, timeout=45)

        cancel_response = client.request_ok("POST", f"/api/backup/cancel/{job_id}")
        payload = cancel_response.json()
        if "cancel" not in str(payload).lower():
            raise SmokeFailure(f"Unexpected cancel response: {payload}")

        job_data = client.wait_for_job(
            "/api/backup/status", job_id, expected={"cancelled"}, timeout=60
        )
        if job_data["status"] != "cancelled":
            raise SmokeFailure(f"Expected cancelled backup job, got {job_data}")

        archives = client.list_archives(repo_path)
        if archives:
            raise SmokeFailure(
                f"Cancelled backup should not leave archives behind: {archives}"
            )

        running_jobs = client.request_ok(
            "GET", f"/api/repositories/{repo_id}/running-jobs"
        ).json()
        if running_jobs.get("has_running_jobs"):
            raise SmokeFailure(
                f"Repository should not report running jobs after cancel: {running_jobs}"
            )

        client.log("Backup cancel smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
