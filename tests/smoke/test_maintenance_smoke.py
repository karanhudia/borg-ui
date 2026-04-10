#!/usr/bin/env python3
"""Black-box smoke coverage for repository maintenance APIs."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run maintenance smoke tests")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "maintenance-source",
            {"base.txt": "maintenance smoke\n"},
        )
        repo_id, repo_path = client.create_repository(
            name="Maintenance Smoke Repo",
            repo_path=client.temp_dir / "maintenance-repo",
            source_dirs=[source_root],
        )

        for index in range(3):
            (source_root / f"archive-{index}.txt").write_text(f"version {index}\n", encoding="utf-8")
            backup_job_id = client.start_backup(repo_path)
            client.wait_for_job(
                "/api/backup/status",
                backup_job_id,
                expected={"completed", "completed_with_warnings"},
                timeout=90,
            )
            time.sleep(1)

        archives_before = client.list_archives(repo_path)
        if len(archives_before) < 3:
            raise SmokeFailure(f"Expected at least 3 archives before prune, got {archives_before}")

        check_response = client.request_ok(
            "POST",
            f"/api/repositories/{repo_id}/check",
            headers=client._headers(json_body=True),
            json={"max_duration": 120},
        )
        check_payload = check_response.json()
        if set(check_payload.keys()) != {"job_id", "status", "message"}:
            raise SmokeFailure(f"Unexpected check response shape: {check_payload}")
        if check_payload["status"] != "pending":
            raise SmokeFailure(f"Expected check to start pending: {check_payload}")
        check_job_id = check_payload["job_id"]
        client.wait_for_job("/api/repositories/check-jobs", check_job_id, expected={"completed"}, timeout=120)

        compact_response = client.request_ok("POST", f"/api/repositories/{repo_id}/compact")
        compact_payload = compact_response.json()
        if set(compact_payload.keys()) != {"job_id", "status", "message"}:
            raise SmokeFailure(f"Unexpected compact response shape: {compact_payload}")
        if compact_payload["status"] != "pending":
            raise SmokeFailure(f"Expected compact to start pending: {compact_payload}")
        compact_job_id = compact_payload["job_id"]
        client.wait_for_job("/api/repositories/compact-jobs", compact_job_id, expected={"completed"}, timeout=120)

        prune_response = client.request_ok(
            "POST",
            f"/api/repositories/{repo_id}/prune",
            headers=client._headers(json_body=True),
            json={
                "keep_hourly": 0,
                "keep_daily": 1,
                "keep_weekly": 0,
                "keep_monthly": 0,
                "keep_quarterly": 0,
                "keep_yearly": 0,
                "dry_run": False,
            },
        )
        prune_payload = prune_response.json()
        if set(prune_payload.keys()) != {"job_id", "status", "dry_run", "prune_result"}:
            raise SmokeFailure(f"Unexpected prune response shape: {prune_payload}")
        if prune_payload.get("status") != "completed":
            raise SmokeFailure(f"Expected prune to complete successfully: {prune_payload}")
        prune_result = prune_payload.get("prune_result", {})
        if set(prune_result.keys()) != {"success", "stdout", "stderr"}:
            raise SmokeFailure(f"Unexpected prune result shape: {prune_payload}")
        if prune_result.get("success") is not True:
            raise SmokeFailure(f"Expected prune_result.success to be true: {prune_payload}")

        archives_after = client.list_archives(repo_path)
        if len(archives_after) != 1:
            raise SmokeFailure(f"Expected prune to leave one archive, got {archives_after}")

        stale_lock_dir = client.temp_dir / "maintenance-repo" / "lock.exclusive"
        stale_lock_dir.mkdir(parents=True, exist_ok=True)
        (stale_lock_dir / "fakepid").write_text("99999\n", encoding="utf-8")
        break_lock_response = client.request_ok("POST", f"/api/repositories/{repo_id}/break-lock")
        if break_lock_response.status_code != 200:
            raise SmokeFailure(f"Unexpected break-lock response: {break_lock_response.text}")

        client.log("Maintenance smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
