#!/usr/bin/env python3
"""Black-box smoke coverage for schedule run-now flows."""

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
    parser = argparse.ArgumentParser(description="Run schedule run-now smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        repo_ids = []
        repo_paths = []
        for suffix in ("one", "two"):
            source_root = client.prepare_source_tree(
                f"schedule-source-{suffix}",
                {f"{suffix}.txt": f"schedule smoke {suffix}\n"},
            )
            repo_id, repo_path = client.create_repository(
                name=f"Schedule Smoke {suffix}",
                repo_path=client.temp_dir / f"schedule-repo-{suffix}",
                source_dirs=[source_root],
            )
            repo_ids.append(repo_id)
            repo_paths.append(repo_path)

        schedule_id = client.create_schedule(
            name="Smoke Run Now",
            cron_expression="0 6 * * *",
            repository_ids=repo_ids,
        )
        client.run_schedule_now(schedule_id)

        deadline = time.time() + 90
        while time.time() < deadline:
            done = True
            for repo_path in repo_paths:
                archives = client.list_archives(repo_path)
                if len(archives) != 1:
                    done = False
                    break
            if done:
                break
            time.sleep(0.5)

        for repo_path in repo_paths:
            archives = client.list_archives(repo_path)
            if len(archives) != 1:
                raise SmokeFailure(
                    f"Expected exactly one archive after run-now for {repo_path}, got {archives}"
                )

        client.log("Schedule run-now smoke passed")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
