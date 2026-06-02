#!/usr/bin/env python3
"""Black-box smoke coverage for manual-only legacy schedule run-now flows."""

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
    parser = argparse.ArgumentParser(description="Run manual-only schedule smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()
        run_id = str(int(time.time()))
        schedule_name = f"Manual Only Schedule Smoke {run_id}"

        source_root = client.prepare_source_tree(
            "manual-only-schedule-source",
            {"manual.txt": "manual-only schedule smoke\n"},
        )
        repo_id, repo_path = client.create_repository(
            name=f"Manual Only Schedule Smoke Repo {run_id}",
            repo_path=client.temp_dir / "manual-only-schedule-repo",
            source_dirs=[source_root],
        )

        create_response = client.request_ok(
            "POST",
            "/api/schedule/",
            headers=client._headers(json_body=True),
            json={
                "name": schedule_name,
                "repository_ids": [repo_id],
                "enabled": True,
                "run_prune_after": True,
                "run_compact_after": True,
            },
            expected=(200, 201),
        )
        schedule = create_response.json().get("job") or create_response.json()
        schedule_id = schedule["id"]
        if schedule.get("schedule_enabled") is not False:
            raise SmokeFailure(
                f"Manual-only create did not return schedule_enabled=false: {schedule}"
            )
        if schedule.get("cron_expression") is not None:
            raise SmokeFailure(f"Manual-only create returned cron data: {schedule}")
        if schedule.get("timezone") is not None:
            raise SmokeFailure(f"Manual-only create returned timezone data: {schedule}")

        list_response = client.request_ok("GET", "/api/schedule/")
        listed_schedule = next(
            item for item in list_response.json()["jobs"] if item["id"] == schedule_id
        )
        if listed_schedule.get("schedule_enabled") is not False:
            raise SmokeFailure(
                f"Manual-only list did not mark job clearly: {listed_schedule}"
            )
        if listed_schedule.get("cron_expression") is not None:
            raise SmokeFailure(
                f"Manual-only list returned cron data: {listed_schedule}"
            )
        if listed_schedule.get("timezone") is not None:
            raise SmokeFailure(
                f"Manual-only list returned timezone data: {listed_schedule}"
            )
        if listed_schedule.get("next_run") is not None:
            raise SmokeFailure(f"Manual-only list returned next_run: {listed_schedule}")

        client.run_schedule_now(schedule_id)

        deadline = time.time() + 90
        while time.time() < deadline:
            archives = client.list_archives(repo_path)
            if len(archives) == 1:
                break
            time.sleep(0.5)

        archives = client.list_archives(repo_path)
        if len(archives) != 1:
            raise SmokeFailure(
                f"Expected exactly one archive after manual-only run-now for {repo_path}, got {archives}"
            )

        client.log("Manual-only schedule smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
