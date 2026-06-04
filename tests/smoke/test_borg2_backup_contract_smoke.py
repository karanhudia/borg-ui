#!/usr/bin/env python3
"""Black-box smoke coverage for Borg 2 running backup progress payloads."""

from __future__ import annotations

import argparse
import queue
import shutil
import sys
import threading
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def _start_borg2_backup(
    base_url: str, token: str, repository_id: int, result_queue: queue.Queue
) -> None:
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/v2/backup/run",
            headers={
                "X-Borg-Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"repository_id": repository_id},
            timeout=300,
        )
        result_queue.put(("response", response))
    except Exception as exc:  # pragma: no cover - smoke helper
        result_queue.put(("error", exc))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Borg 2 backup contract smoke test"
    )
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        system_info = client.system_info()
        feature_access = system_info.get("feature_access", {})
        if not feature_access.get("borg_v2"):
            print(
                "Borg 2 backup contract smoke skipped: borg_v2 feature not enabled",
                flush=True,
            )
            return 0

        if not system_info.get("borg2_version"):
            print(
                "Borg 2 backup contract smoke skipped: borg2 binary not available in app",
                flush=True,
            )
            return 0

        if shutil.which("borg2") is None:
            print(
                "Borg 2 backup contract smoke skipped: borg2 binary not available on smoke runner",
                flush=True,
            )
            return 0

        source_root = client.prepare_source_tree(
            "borg2-contract-source",
            {"notes/readme.txt": "borg2 contract smoke\n"},
        )
        client.write_incompressible_file(source_root / "large.bin", size_mb=128)

        repo_id, repo_path = client.create_repository_v2(
            name="Borg2 Contract Smoke Repo",
            repo_path=client.temp_dir / "borg2-contract-repo",
            source_dirs=[source_root],
            encryption="none",
        )

        result_queue: queue.Queue = queue.Queue()
        worker = threading.Thread(
            target=_start_borg2_backup,
            args=(args.url, client.token, repo_id, result_queue),
            daemon=True,
        )
        worker.start()

        running_job = client.wait_for_backup_job(
            repo_path, statuses={"pending", "running"}, timeout=45
        )
        job_id = int(running_job["id"])
        client.wait_for_running("/api/backup/status", job_id, timeout=45)

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
            progress = status_payload.get("progress_details", {})
            if not required_keys.issubset(progress.keys()):
                raise SmokeFailure(
                    f"Unexpected Borg 2 progress_details shape: {status_payload}"
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
                f"Borg 2 backup never exposed live progress details before completion: {last_payload}"
            )

        worker.join(timeout=300)
        if worker.is_alive():
            raise SmokeFailure(
                "Timed out waiting for Borg 2 backup request to complete"
            )

        result_kind, result_value = result_queue.get_nowait()
        if result_kind == "error":
            raise SmokeFailure(f"Borg 2 backup request failed: {result_value}")

        response = result_value
        if response.status_code != 200:
            raise SmokeFailure(
                f"Borg 2 backup run returned {response.status_code}: {response.text}"
            )

        payload = response.json()
        if payload.get("status") not in {"completed", "completed_with_warnings"}:
            raise SmokeFailure(
                f"Unexpected Borg 2 backup completion payload: {payload}"
            )

        client.log(f"Borg 2 backup contract smoke passed with job {job_id}")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
