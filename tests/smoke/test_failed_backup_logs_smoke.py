#!/usr/bin/env python3
"""Black-box smoke coverage for failed backup log downloads."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run failed backup logs smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        missing_repo_path = client.temp_dir / "missing-repo"
        backup_job_id = client.start_backup(str(missing_repo_path))
        job_data = client.wait_for_job("/api/backup/status", backup_job_id, expected={"failed"}, timeout=45)
        if job_data["status"] != "failed":
            raise SmokeFailure(f"Expected failed backup job, got {job_data}")

        logs_response = client.request_ok("GET", f"/api/backup/logs/{backup_job_id}/download")
        disposition = logs_response.headers.get("content-disposition", "")
        if "backup_job_" not in disposition or not logs_response.content:
            raise SmokeFailure(f"Unexpected backup logs download response: headers={logs_response.headers}")

        body = logs_response.text.lower()
        if "repository" not in body and "not found" not in body:
            raise SmokeFailure(f"Expected missing-repository error in logs, got: {logs_response.text[:400]}")

        client.log("Failed backup logs smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
