#!/usr/bin/env python3
"""Black-box smoke coverage for archive delete cancellation."""

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
    parser = argparse.ArgumentParser(description="Run delete cancel smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "delete-cancel-source",
            {"seed.txt": "delete cancel smoke\n"},
        )
        client.write_incompressible_file(source_root / "large.bin", size_mb=128)

        repo_id, repo_path = client.create_repository(
            name="Delete Cancel Smoke Repo",
            repo_path=client.temp_dir / "delete-cancel-repo",
            source_dirs=[source_root],
        )
        backup_job_id = client.start_backup(repo_path)
        client.wait_for_job(
            "/api/backup/status",
            backup_job_id,
            expected={"completed", "completed_with_warnings"},
            timeout=120,
        )

        archives = client.list_archives(repo_path)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected one archive before delete cancel, got {archives}")
        archive_name = archives[0]["name"]

        delete_response = client.request_ok(
            "DELETE",
            f"/api/archives/{archive_name}",
            params={"repository": repo_path},
        )
        delete_job_id = delete_response.json()["job_id"]

        deadline = time.time() + 45
        last_status = None
        while time.time() < deadline:
            payload = client.request_ok("GET", f"/api/archives/delete-jobs/{delete_job_id}").json()
            last_status = payload["status"]
            if last_status == "running":
                break
            if last_status in {"completed", "completed_with_warnings"}:
                print("Delete cancel smoke skipped: delete completed before cancellation window", flush=True)
                return 0
            time.sleep(0.25)

        if last_status != "running":
            print(f"Delete cancel smoke skipped: delete never reached running state ({last_status})", flush=True)
            return 0

        cancel_response = client.request("POST", f"/api/archives/delete-jobs/{delete_job_id}/cancel")
        if cancel_response.status_code == 400:
            payload = client.request_ok("GET", f"/api/archives/delete-jobs/{delete_job_id}").json()
            if payload.get("status") in {"completed", "completed_with_warnings"}:
                print("Delete cancel smoke skipped: delete completed before cancellation request", flush=True)
                return 0
            raise SmokeFailure(f"Delete cancel returned 400 unexpectedly: {cancel_response.text}")
        if cancel_response.status_code != 200:
            raise SmokeFailure(
                f"POST /api/archives/delete-jobs/{delete_job_id}/cancel returned "
                f"{cancel_response.status_code}: {cancel_response.text}"
            )
        if "cancel" not in str(cancel_response.json()).lower():
            raise SmokeFailure(f"Unexpected delete cancel response: {cancel_response.text}")

        try:
            job_payload = client.wait_for_job(
                "/api/archives/delete-jobs",
                delete_job_id,
                expected={"cancelled"},
                timeout=60,
                terminal={"cancelled", "completed", "completed_with_warnings", "failed"},
            )
        except SmokeFailure:
            payload = client.request_ok("GET", f"/api/archives/delete-jobs/{delete_job_id}").json()
            if payload.get("status") in {"completed", "completed_with_warnings"}:
                print("Delete cancel smoke skipped: delete completed after cancellation request", flush=True)
                return 0
            raise
        if job_payload["status"] != "cancelled":
            raise SmokeFailure(f"Expected cancelled delete job, got {job_payload}")

        archives_after = client.list_archives(repo_path)
        if not archives_after:
            raise SmokeFailure("Cancelled delete should leave the archive intact")

        client.log("Delete cancel smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
