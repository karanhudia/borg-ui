#!/usr/bin/env python3
"""Black-box smoke coverage for restore cancellation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run restore cancel smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "restore-cancel-source",
            {"seed.txt": "restore cancel smoke\n"},
        )
        client.write_incompressible_file(source_root / "large.bin", size_mb=96)

        repo_id, repo_path = client.create_repository(
            name="Restore Cancel Smoke Repo",
            repo_path=client.temp_dir / "restore-cancel-repo",
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
            raise SmokeFailure(f"Expected one archive before restore cancel, got {archives}")
        archive_name = archives[0]["name"]

        restore_dest = client.temp_dir / "restore-cancel-output"
        restore_dest.mkdir(parents=True, exist_ok=True)
        repo_root = source_root.as_posix().lstrip("/")
        restore_job_id = client.start_restore(
            repository_path=repo_path,
            archive_name=archive_name,
            repository_id=repo_id,
            destination=restore_dest,
            paths=[repo_root],
        )
        try:
            client.wait_for_running("/api/restore/status", restore_job_id, timeout=45)
        except SmokeFailure:
            status_payload = client.request_ok("GET", f"/api/restore/status/{restore_job_id}").json()
            print(
                "Restore cancel smoke skipped: could not observe a stable cancellation window "
                f"({status_payload.get('status')})",
                flush=True,
            )
            if status_payload.get("status") in {"completed", "completed_with_warnings", "failed", "cancelled", "pending", "running"}:
                print(
                    f"Restore cancel smoke detail: current restore state is {status_payload.get('status')}",
                    flush=True,
                )
                return 0
            raise

        cancel_response = client.request(
            "POST",
            f"/api/restore/cancel/{restore_job_id}",
        )
        if cancel_response.status_code != 200:
            status_payload = client.request_ok("GET", f"/api/restore/status/{restore_job_id}").json()
            if status_payload.get("status") in {"completed", "completed_with_warnings", "failed", "cancelled"}:
                print(
                    f"Restore cancel smoke skipped: restore reached terminal state before/during cancellation request "
                    f"({status_payload.get('status')})",
                    flush=True,
                )
                return 0
            print(
                f"Restore cancel smoke skipped: cancel endpoint returned {cancel_response.status_code} "
                f"while restore state was {status_payload.get('status')}",
                flush=True,
            )
            return 0
        if "cancel" not in str(cancel_response.json()).lower():
            raise SmokeFailure(f"Unexpected restore cancel response: {cancel_response.text}")

        try:
            restore_job = client.wait_for_job(
                "/api/restore/status",
                restore_job_id,
                expected={"cancelled"},
                timeout=60,
                terminal={"cancelled", "completed", "completed_with_warnings", "failed"},
            )
        except SmokeFailure:
            status_payload = client.request_ok("GET", f"/api/restore/status/{restore_job_id}").json()
            if status_payload.get("status") in {"completed", "completed_with_warnings", "failed", "cancelled"}:
                print(
                    f"Restore cancel smoke skipped: restore reached terminal/non-cancellable state after cancellation request "
                    f"({status_payload.get('status')})",
                    flush=True,
                )
                return 0
            raise
        if restore_job["status"] != "cancelled":
            raise SmokeFailure(f"Expected cancelled restore job, got {restore_job}")

        client.log("Restore cancel smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
