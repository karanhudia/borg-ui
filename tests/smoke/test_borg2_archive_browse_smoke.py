#!/usr/bin/env python3
"""Black-box smoke coverage for Borg 2 archive browsing depth semantics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.smoke.live_helpers import SmokeClient, SmokeFailure


def _item_map(items: list[dict]) -> dict[str, dict]:
    return {item["name"]: item for item in items}


def _assert_names(items: list[dict], expected: set[str], *, context: str) -> dict[str, dict]:
    names = {item["name"] for item in items}
    if names != expected:
        raise SmokeFailure(f"Unexpected Borg 2 browse items for {context}: expected {expected}, got {names}")
    return _item_map(items)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Borg 2 archive browse smoke test")
    parser.add_argument("--url", default="http://localhost:8082")
    args = parser.parse_args()

    client = SmokeClient(args.url)
    try:
        client.authenticate()

        system_info = client.system_info()
        feature_access = system_info.get("feature_access", {})
        if not feature_access.get("borg_v2"):
            print("Borg 2 archive browse smoke skipped: borg_v2 feature not enabled", flush=True)
            return 0

        if not system_info.get("borg2_version"):
            print("Borg 2 archive browse smoke skipped: borg2 binary not available in app", flush=True)
            return 0

        source_root = client.prepare_source_tree(
            "borg2-browse-source",
            {
                "root.txt": "root level\n",
                "alpha/readme.txt": "alpha\n",
                "alpha/beta/notes.txt": "beta\n",
                "alpha/beta/gamma/deep.txt": "deep\n",
                "zeta/leaf.txt": "zeta\n",
            },
        )
        unique_suffix = client.temp_dir.name

        repo_id, repo_path, _job_id, _backup = client.create_repository_and_backup_v2(
            name=f"Borg2 Browse Smoke Repo {unique_suffix}",
            repo_path=client.temp_dir / "borg2-browse-repo",
            source_dirs=[source_root],
            encryption="none",
        )

        archives = client.list_archives_v2(repo_id)
        if len(archives) != 1:
            raise SmokeFailure(f"Expected exactly one Borg 2 archive for browse smoke, got {archives}")

        archive = archives[0]
        archive_id = archive.get("id") or archive.get("name")
        if not archive_id:
            raise SmokeFailure(f"Archive payload missing id/name: {archive}")

        source_parts = [part for part in client.container_path(source_root).strip("/").split("/") if part]
        if not source_parts:
            raise SmokeFailure("Expected non-empty container path for Borg 2 browse smoke source")

        items = client.browse_archive_contents_v2(repo_id, archive_id)
        _assert_names(items, {source_parts[0]}, context="archive root")

        current_path = ""
        for index, part in enumerate(source_parts):
            if current_path:
                current_path = f"{current_path}/{part}"
            else:
                current_path = part
            items = client.browse_archive_contents_v2(repo_id, archive_id, path=current_path)
            if index < len(source_parts) - 1:
                _assert_names(items, {source_parts[index + 1]}, context=current_path)
            else:
                root_items = _assert_names(items, {"alpha", "root.txt", "zeta"}, context=current_path)
                if root_items["root.txt"]["type"] != "file":
                    raise SmokeFailure(f"Expected root.txt to be a file: {root_items['root.txt']}")
                if root_items["alpha"]["type"] != "directory" or root_items["zeta"]["type"] != "directory":
                    raise SmokeFailure(f"Expected alpha and zeta to be directories: {root_items}")

        alpha_items = _assert_names(
            client.browse_archive_contents_v2(repo_id, archive_id, path=f"{current_path}/alpha"),
            {"beta", "readme.txt"},
            context=f"{current_path}/alpha",
        )
        if alpha_items["readme.txt"]["type"] != "file" or alpha_items["beta"]["type"] != "directory":
            raise SmokeFailure(f"Unexpected alpha browse types: {alpha_items}")

        beta_items = _assert_names(
            client.browse_archive_contents_v2(repo_id, archive_id, path=f"{current_path}/alpha/beta"),
            {"gamma", "notes.txt"},
            context=f"{current_path}/alpha/beta",
        )
        if beta_items["notes.txt"]["type"] != "file" or beta_items["gamma"]["type"] != "directory":
            raise SmokeFailure(f"Unexpected beta browse types: {beta_items}")

        gamma_items = _assert_names(
            client.browse_archive_contents_v2(repo_id, archive_id, path=f"{current_path}/alpha/beta/gamma"),
            {"deep.txt"},
            context=f"{current_path}/alpha/beta/gamma",
        )
        if gamma_items["deep.txt"]["type"] != "file":
            raise SmokeFailure(f"Unexpected gamma browse payload: {gamma_items}")

        client.log(f"Borg 2 archive browse smoke passed for repo {repo_id} at {repo_path}")
        return 0
    finally:
        client.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
