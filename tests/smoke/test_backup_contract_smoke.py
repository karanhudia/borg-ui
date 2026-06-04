#!/usr/bin/env python3
"""Black-box smoke coverage for Borg 1 manual backup contracts."""

from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Borg backup contract smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "backup-contract-source",
            {"notes/readme.txt": "backup contract smoke\n"},
        )
        client.write_incompressible_file(source_root / "large.bin", size_mb=128)

        repo_id, repo_path = client.create_repository(
            name="Backup Contract Smoke Repo",
            repo_path=client.temp_dir / "backup-contract-repo",
            source_dirs=[source_root],
            encryption="none",
        )

        response = client.request_ok(
            "POST",
            "/api/backup/start",
            headers=client._headers(json_body=True),
            json={"repository": repo_path},
            expected=(200, 201, 202),
        )
        payload = response.json()
        if set(payload.keys()) != {"job_id", "status", "message"}:
            raise SmokeFailure(f"Unexpected backup start payload: {payload}")
        if payload["status"] != "pending":
            raise SmokeFailure(f"Unexpected backup start status: {payload}")
        if payload["message"] != "Backup job started":
            raise SmokeFailure(f"Unexpected backup start message: {payload}")

        job_id = int(payload["job_id"])

        required_keys = {
            "original_size",
            "nfiles",
            "current_file",
            "progress_percent",
            "backup_speed",
            "total_expected_size",
            "estimated_time_remaining",
        }

        deadline = time.time() + 90
        last_payload = None
        while time.time() < deadline:
            status_payload = client.request_ok(
                "GET", f"/api/backup/status/{job_id}"
            ).json()
            last_payload = status_payload

            if status_payload.get("repository") != repo_path:
                raise SmokeFailure(
                    f"Unexpected backup status repository payload: {status_payload}"
                )

            progress = status_payload.get("progress_details", {})
            if not required_keys.issubset(progress.keys()):
                raise SmokeFailure(
                    f"Unexpected backup progress_details shape: {status_payload}"
                )

            has_live_progress = any(
                [
                    progress.get("original_size", 0) > 0,
                    progress.get("nfiles", 0) > 0,
                    bool(progress.get("current_file")),
                    progress.get("backup_speed", 0) > 0,
                ]
            )
            if status_payload.get("status") == "running" and has_live_progress:
                break
            time.sleep(0.5)
        else:
            raise SmokeFailure(
                f"Backup never exposed live progress details before completion: {last_payload}"
            )

        final_payload = client.wait_for_job(
            "/api/backup/status",
            job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=180,
        )
        if final_payload.get("repository") != repo_path:
            raise SmokeFailure(
                f"Unexpected final backup status repository payload: {final_payload}"
            )
        if not required_keys.issubset(final_payload.get("progress_details", {}).keys()):
            raise SmokeFailure(
                f"Unexpected final backup contract payload: {final_payload}"
            )

        client.log(
            f"Backup contract smoke passed for repository {repo_id} with job {job_id}"
        )
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
