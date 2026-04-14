"""Shared archive browsing helpers for v1/v2 and restore/archive routes."""

from __future__ import annotations

import json
from typing import Dict, List


def parse_archive_items(stdout: str) -> List[Dict]:
    """Parse borg --json-lines output into normalized archive items."""
    items: List[Dict] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item_data = json.loads(line)
        except json.JSONDecodeError:
            continue

        item_path = (item_data.get("path") or "").strip("/")
        if not item_path:
            continue

        items.append(
            {
                "path": item_path,
                "type": item_data.get("type", ""),
                "size": item_data.get("size"),
                "mtime": item_data.get("mtime"),
            }
        )

    return items


def build_browse_items(
    all_items: List[Dict], path: str, *, hide_directory_sizes: bool = False
) -> List[Dict]:
    """Build immediate children for a browse path from a full/raw item list."""
    normalized_path = path.strip("/")

    def calculate_directory_size(dir_path: str) -> int:
        total_size = 0
        normalized_dir_path = dir_path.strip("/")
        search_prefix = f"{normalized_dir_path}/" if normalized_dir_path else ""

        for item in all_items:
            item_path = (item.get("path") or "").strip("/")
            if not item_path:
                continue

            if search_prefix:
                if (
                    item_path.startswith(search_prefix)
                    or item_path == normalized_dir_path
                ):
                    if item.get("type") != "d" and item.get("size") is not None:
                        total_size += item.get("size", 0)
            else:
                if item.get("type") != "d" and item.get("size") is not None:
                    total_size += item.get("size", 0)

        return total_size

    items: List[Dict] = []
    seen_paths = set()

    for item in all_items:
        item_path = (item.get("path") or "").strip("/")
        item_type = item.get("type", "")
        item_size = item.get("size")
        item_mtime = item.get("mtime")

        if not item_path:
            continue

        if normalized_path:
            if item_path == normalized_path:
                continue
            if not item_path.startswith(normalized_path + "/"):
                continue
            relative_path = item_path[len(normalized_path) + 1 :]
        else:
            relative_path = item_path

        if not relative_path:
            continue

        if "/" in relative_path:
            dir_name = relative_path.split("/")[0]
            if dir_name in seen_paths:
                continue
            seen_paths.add(dir_name)
            full_dir_path = (
                f"{normalized_path}/{dir_name}" if normalized_path else dir_name
            )
            items.append(
                {
                    "name": dir_name,
                    "type": "directory",
                    "size": None
                    if hide_directory_sizes
                    else calculate_directory_size(full_dir_path),
                    "mtime": None,
                    "path": full_dir_path,
                }
            )
            continue

        if relative_path in seen_paths:
            continue
        seen_paths.add(relative_path)
        full_path = (
            f"{normalized_path}/{relative_path}" if normalized_path else relative_path
        )

        if item_type == "d":
            items.append(
                {
                    "name": relative_path,
                    "type": "directory",
                    "size": None
                    if hide_directory_sizes
                    else calculate_directory_size(full_path),
                    "mtime": item_mtime,
                    "path": full_path,
                }
            )
        else:
            items.append(
                {
                    "name": relative_path,
                    "type": "file",
                    "size": item_size,
                    "mtime": item_mtime,
                    "path": full_path,
                }
            )

    items.sort(key=lambda entry: (entry["type"] != "directory", entry["name"].lower()))
    return items


def collect_browse_paths(all_items: List[Dict]) -> List[str]:
    """Collect every directory path that can be browsed, including root."""
    paths = {""}

    for item in all_items:
        item_path = (item.get("path") or "").strip("/")
        if not item_path:
            continue

        parts = item_path.split("/")
        max_depth = len(parts) if item.get("type") == "d" else len(parts) - 1
        for depth in range(1, max_depth + 1):
            paths.add("/".join(parts[:depth]))

    return sorted(paths)
