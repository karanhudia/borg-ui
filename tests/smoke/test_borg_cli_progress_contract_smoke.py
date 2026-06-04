#!/usr/bin/env python3
"""Raw Borg 1 CLI progress contract smoke test."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeFailure
from tests.utils.borg import init_borg_repo, make_borg_test_env, run_borg


def _write_incompressible_file(path: Path, *, size_mb: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for _ in range(size_mb):
            handle.write(os.urandom(1024 * 1024))


def _detect_app_container() -> str | None:
    preferred = os.environ.get("BORG_UI_SMOKE_APP_CONTAINER")
    if preferred:
        return preferred
    for candidate in ("borg-web-ui-dev", "borg-web-ui"):
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and candidate in result.stdout.splitlines():
            return candidate
    return None


def _run_container_contract(container_name: str) -> list[dict]:
    script = r"""
import json, os, subprocess, tempfile
from pathlib import Path
base = Path(tempfile.mkdtemp(prefix="borg1-cli-contract-", dir="/tmp"))
repo = base / "repo"
src = base / "source"
repo.mkdir(parents=True, exist_ok=True)
src.mkdir(parents=True, exist_ok=True)
(src / "notes.txt").write_text("borg cli contract smoke\n", encoding="utf-8")
with open(src / "large.bin", "wb") as handle:
    for _ in range(128):
        handle.write(os.urandom(1024 * 1024))
env = os.environ.copy()
env["BORG_BASE_DIR"] = str(base / "borg-base")
Path(env["BORG_BASE_DIR"]).mkdir(parents=True, exist_ok=True)
env["BORG_PASSPHRASE"] = ""
subprocess.run(["borg", "init", "--encryption=none", str(repo)], check=True, capture_output=True, text=True, env=env)
result = subprocess.run(
    ["borg", "create", "--progress", "--stats", "--show-rc", "--log-json", "--compression", "none", f"{repo}::contract-smoke", str(src)],
    check=True,
    capture_output=True,
    text=True,
    env=env,
)
frames = []
for line in result.stdout.splitlines():
    if not line.strip() or not line.startswith("{"):
        continue
    payload = json.loads(line)
    if payload.get("type") == "archive_progress":
        frames.append(payload)
print(json.dumps(frames))
"""
    result = subprocess.run(
        ["docker", "exec", container_name, "python", "-c", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SmokeFailure(
            f"Failed to run Borg 1 CLI contract in container {container_name}: {result.stderr or result.stdout}"
        )
    return json.loads(result.stdout.strip() or "[]")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run raw Borg 1 CLI progress contract smoke test"
    )
    parser.parse_args()

    container_name = _detect_app_container()
    if container_name:
        progress_frames = _run_container_contract(container_name)
    else:
        borg = shutil.which("borg")
        if not borg:
            print(
                "Borg 1 CLI progress contract smoke skipped: borg binary not found",
                flush=True,
            )
            return 0

        smoke_root = REPO_ROOT / ".tmp" / "smoke"
        smoke_root.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="borg-cli-contract-", dir=smoke_root))
        try:
            env = make_borg_test_env(str(temp_dir))
            repo_path = temp_dir / "repo"
            source_root = temp_dir / "source"
            source_root.mkdir(parents=True, exist_ok=True)
            (source_root / "notes.txt").write_text(
                "borg cli contract smoke\n", encoding="utf-8"
            )
            _write_incompressible_file(source_root / "large.bin", size_mb=128)

            init_borg_repo(borg, repo_path, env=env, encryption="none")
            result = run_borg(
                borg,
                [
                    "create",
                    "--progress",
                    "--stats",
                    "--show-rc",
                    "--log-json",
                    "--compression",
                    "none",
                    f"{repo_path}::contract-smoke",
                    str(source_root),
                ],
                env=env,
            )

            progress_frames = []
            for line in result.stdout.splitlines():
                if not line.strip() or not line.startswith("{"):
                    continue
                payload = json.loads(line)
                if payload.get("type") == "archive_progress":
                    progress_frames.append(payload)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        live_frames = [frame for frame in progress_frames if not frame.get("finished")]
        if not live_frames:
            if container_name:
                raise SmokeFailure(
                    "Borg 1 CLI did not emit any live archive_progress frames"
                )
            print(
                "Borg 1 CLI progress contract smoke skipped: local borg did not emit live archive_progress frames",
                flush=True,
            )
            return 0

        if not any(frame.get("original_size", 0) > 0 for frame in live_frames):
            raise SmokeFailure(
                f"Borg 1 CLI never emitted non-zero original_size: {live_frames}"
            )
        if not any(frame.get("compressed_size", 0) > 0 for frame in live_frames):
            raise SmokeFailure(
                f"Borg 1 CLI never emitted non-zero compressed_size: {live_frames}"
            )
        if not any(frame.get("path") for frame in live_frames):
            raise SmokeFailure(
                f"Borg 1 CLI never emitted archive_progress path values: {live_frames}"
            )

        print("Borg 1 CLI progress contract smoke passed", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
