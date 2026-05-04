#!/usr/bin/env python3
"""Black-box smoke coverage for canary-backed restore verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def main() -> int:
    parser = argparse.ArgumentParser(description="Run restore check smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        source_root = client.prepare_source_tree(
            "restore-check-source",
            {
                "docs/readme.txt": "restore check smoke\n",
                "config/app.ini": "[app]\nmode=smoke\n",
            },
        )
        repo_id, _repo_path, _backup_job_id, backup_data = (
            client.create_repository_and_backup(
                name="Restore Check Smoke Repo",
                repo_path=client.temp_dir / "restore-check-repo",
                source_dirs=[source_root],
            )
        )
        if backup_data["status"] not in {"completed", "completed_with_warnings"}:
            raise SmokeFailure(f"Unexpected backup status: {backup_data}")

        schedule_data = client.update_restore_check_schedule(
            repo_id,
            cron_expression="0 4 * * 0",
        )
        repository_payload = schedule_data["repository"]
        if repository_payload["restore_check_mode"] != "canary":
            raise SmokeFailure(f"Expected canary mode by default: {repository_payload}")

        job_id = client.start_restore_check(repo_id)
        job_data = client.wait_for_job(
            "/api/repositories/restore-check-jobs",
            job_id,
            expected={"completed"},
            timeout=90,
        )

        if job_data.get("mode") != "canary":
            raise SmokeFailure(
                f"Expected completed canary restore check, got {job_data}"
            )
        if not job_data.get("archive_name"):
            raise SmokeFailure(f"Restore check did not record archive name: {job_data}")
        if not job_data.get("has_logs"):
            raise SmokeFailure(f"Restore check should capture logs: {job_data}")

        history_payload = client.request_ok(
            "GET", f"/api/repositories/{repo_id}/restore-check-jobs"
        ).json()
        jobs = history_payload.get("jobs", [])
        if not jobs or jobs[0].get("mode") != "canary":
            raise SmokeFailure(
                f"Unexpected restore check history payload: {history_payload}"
            )

        client.log("Restore check smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
