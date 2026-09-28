#!/usr/bin/env python3
"""Rewrite app/api/python_runtimes.json for the Python minor this repo builds.

The minor is stated once, in docker/runtime-base.env. This script reads it from
there, asks the python-build-standalone release API for the newest build of
that minor that covers both macOS architectures, and writes the manifest with
the sha256 digest of each build. Moving to a newer build is therefore: run
this, commit.

    python scripts/refresh_python_runtime_manifest.py          # minor from runtime-base.env
    python scripts/refresh_python_runtime_manifest.py 3.13     # or state it

The digests come from the release API rather than from hashing a download, so
a refresh does not pull the archives. Nothing here runs at build or run time:
the manifest is committed so that the installer verifies a download against a
value it did not fetch alongside the file.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "docker" / "runtime-base.env"
MANIFEST = REPO_ROOT / "app" / "api" / "python_runtimes.json"

RELEASES_API = (
    "https://api.github.com/repos/astral-sh/python-build-standalone/releases"
    "?per_page=30&page={page}"
)
# Releases are listed newest first; a pinned minor still built a year ago is
# a few pages back.
MAX_PAGES = 10

# The relocatable "install_only" archives for macOS. The build tag (a date)
# follows the CPython version after a plus sign; the archive unpacks to a
# `python/` directory that runs from wherever it is placed.
DARWIN_ASSET = re.compile(
    r"^cpython-(\d+\.\d+\.\d+)\+(\d{8})-(aarch64|x86_64)-apple-darwin-install_only"
    r"\.tar\.gz$"
)

REQUIRED_ARCHES = {"aarch64", "x86_64"}


def _get_json(url: str):
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json"}
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def minor_from_env() -> str:
    text = ENV_FILE.read_text(encoding="utf-8")
    match = re.search(r"^PYTHON_VERSION=(\d+\.\d+)\s*$", text, re.M)
    if not match:
        raise SystemExit(f"No PYTHON_VERSION in {ENV_FILE.name}")
    return match.group(1)


def darwin_runtimes(release: dict, minor: str) -> tuple[str, list[dict]]:
    """The manifest entries a release offers for the minor, and their version.

    A release carries builds of several minors; only the pinned one counts.
    Returns an empty list when the release covers neither architecture, or
    when an asset has no digest yet: GitHub serves ``"digest": null`` for an
    upload it has not hashed, which is what a release still being published
    looks like, and the caller then takes an earlier complete one.
    """
    version = ""
    entries = []
    for asset in release.get("assets", []):
        match = DARWIN_ASSET.match(asset["name"])
        if match is None:
            continue
        cpython, tag, arch = match.groups()
        if not cpython.startswith(f"{minor}."):
            continue
        digest = asset.get("digest")
        if not digest:
            return "", []
        if not digest.startswith("sha256:"):
            raise SystemExit(f"No sha256 digest published for {asset['name']}")
        version = f"{cpython}+{tag}"
        entries.append(
            {
                "platform": "darwin",
                "arch": arch,
                "asset": asset["name"],
                "sha256": digest.removeprefix("sha256:"),
                "url": asset["browser_download_url"],
            }
        )
    return version, entries


def latest_build(releases, minor: str) -> tuple[str, list[dict]]:
    """The newest release whose builds of the minor cover both architectures.

    Releases are listed newest first. One whose archives are still uploading
    covers one architecture only and is passed over; the next run picks it up.
    """
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        version, entries = darwin_runtimes(release, minor)
        if REQUIRED_ARCHES <= {entry["arch"] for entry in entries}:
            return version, entries
    raise SystemExit(f"No python-build-standalone release covers CPython {minor}")


def published_releases():
    """Every release, newest first, page by page, until the API runs dry."""
    for page in range(1, MAX_PAGES + 1):
        releases = _get_json(RELEASES_API.format(page=page))
        if not releases:
            return
        yield from releases


def write_manifest(minor: str) -> None:
    version, entries = latest_build(published_releases(), minor)
    manifest = {"current": version, "runtimes": {version: entries}}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  {version}: {len(entries)} runtimes")
    print(f"Wrote {MANIFEST.relative_to(REPO_ROOT)}")


def main() -> int:
    if len(sys.argv) > 2:
        raise SystemExit("Pass the Python minor (for example 3.12), or nothing")
    if len(sys.argv) == 2:
        minor = sys.argv[1]
    else:
        minor = minor_from_env()
        print(f"Python minor from {ENV_FILE.name}: {minor}")
    write_manifest(minor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
