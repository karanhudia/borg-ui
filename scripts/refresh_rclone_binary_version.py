#!/usr/bin/env python3
"""Adopt newer rclone static releases for the runtime base image.

The runtime base ships the official static rclone binary (downloads.rclone.org),
not the distro package — the Debian build lags years behind and breaks OneDrive
cloud-mirror sync (issue #798). The version is stated once, in
docker/runtime-base.env, and the per-arch checksums the Dockerfile verifies the
download against live in Dockerfile.runtime-base.

    python scripts/refresh_rclone_binary_version.py            # report current vs latest
    python scripts/refresh_rclone_binary_version.py --latest   # adopt a newer release

--latest asks downloads.rclone.org which stable release is current, and if it is
newer than the pin, rewrites RCLONE_VERSION (the truth and its Dockerfile ARG
mirror), refreshes both RCLONE_SHA256_* checksums, and bumps
RUNTIME_BASE_REVISION — because the Borg versions do not move, only the revision
changes the runtime-base tag, and a fresh tag is what makes the new binary get
built and pulled. It is what the scheduled workflow runs to open the adoption PR;
rebuilding and re-pointing the image is the human half, which is the point — the
red base-image guard is the checklist.

The checksums come from the release's published SHA256SUMS rather than from
hashing a download, so a bump does not pull the binaries. Nothing here runs at
build or run time.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "docker" / "runtime-base.env"
DOCKERFILE = REPO_ROOT / "Dockerfile.runtime-base"

VERSION_URL = "https://downloads.rclone.org/version.txt"
SHA256SUMS_URL = "https://downloads.rclone.org/v{version}/SHA256SUMS"

# rclone zip suffix (linux-<goarch>) -> the Dockerfile ARG that pins its checksum.
# Only the architectures the runtime base builds for are tracked; a release
# missing either is not adoptable and is skipped until it is complete.
ARCHES = {
    "amd64": "RCLONE_SHA256_AMD64",
    "arm64": "RCLONE_SHA256_ARM64",
}


def _get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"Accept": "text/plain"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def current_version() -> str:
    """The rclone version the runtime base pins, from the single source of truth."""
    match = re.search(r"^RCLONE_VERSION=(\S+)", ENV_FILE.read_text(encoding="utf-8"), re.M)
    if not match:
        raise SystemExit(f"No RCLONE_VERSION in {ENV_FILE.name}")
    return match.group(1)


def _parse_version(version_txt: str) -> str:
    """The bare version from downloads.rclone.org/version.txt ("rclone v1.75.0")."""
    match = re.search(r"v?(\d+\.\d+\.\d+)", version_txt)
    if not match:
        raise SystemExit(f"Could not parse a version from {version_txt!r}")
    return match.group(1)


def _parse_sha256sums(sums_text: str, version: str) -> dict[str, str]:
    """The per-arch checksums for the linux zips this image needs, keyed by the
    ARCHES key. A line reads '<hash>  rclone-v1.75.0-linux-amd64.zip'."""
    found: dict[str, str] = {}
    for arch in ARCHES:
        asset = f"rclone-v{version}-linux-{arch}.zip"
        match = re.search(rf"^([0-9a-f]{{64}})\s+{re.escape(asset)}$", sums_text, re.M)
        if match:
            found[arch] = match.group(1)
    return found


def latest_version() -> str:
    return _parse_version(_get_text(VERSION_URL))


def checksums_for(version: str) -> dict[str, str]:
    sums = _parse_sha256sums(_get_text(SHA256SUMS_URL.format(version=version)), version)
    missing = set(ARCHES) - set(sums)
    if missing:
        raise SystemExit(
            f"rclone {version} publishes no linux zip for arch(es) {sorted(missing)}"
        )
    return sums


def _rewrite(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(pattern, rf"\g<1>{replacement}", text, flags=re.M)
    if not count:
        raise SystemExit(f"No match for {pattern!r} in {path.name}")
    path.write_text(text, encoding="utf-8")


def _bump_revision() -> None:
    """An rclone bump keeps the Borg versions, so it is a recipe-only change:
    increment RUNTIME_BASE_REVISION so the computed tag names a new image. That
    tag does not exist until rebuilt, which keeps the base-image guard red for the
    human half."""
    text = ENV_FILE.read_text(encoding="utf-8")
    match = re.search(r"^RUNTIME_BASE_REVISION=(\d+)", text, re.M)
    if not match:
        raise SystemExit(f"No RUNTIME_BASE_REVISION in {ENV_FILE.name}")
    _rewrite(ENV_FILE, r"^(RUNTIME_BASE_REVISION=)\d+", str(int(match.group(1)) + 1))


def adopt(new_version: str, checksums: dict[str, str]) -> None:
    _rewrite(ENV_FILE, r"^(RCLONE_VERSION=)\S+", new_version)
    _rewrite(DOCKERFILE, r"^(ARG RCLONE_VERSION=)\S+", new_version)
    for arch, arg in ARCHES.items():
        _rewrite(DOCKERFILE, rf"^(ARG {arg}=)\S+", checksums[arch])
    _bump_revision()


def _emit_output(**values: str) -> None:
    """Hand results to the workflow step through GITHUB_OUTPUT, when set."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            if "\n" in value:
                handle.write(f"{key}<<__EOF__\n{value}\n__EOF__\n")
            else:
                handle.write(f"{key}={value}\n")


def adopt_latest() -> int:
    current = current_version()
    latest = latest_version()
    try:
        newer = Version(latest) > Version(current)
    except InvalidVersion as exc:
        raise SystemExit(f"Unparseable rclone version: {exc}")
    if not newer:
        print(f"Up to date: rclone {current}")
        _emit_output(changed="false")
        return 0

    print(f"rclone: {current} -> {latest}")
    adopt(latest, checksums_for(latest))
    title = f"chore(runtime-base): adopt rclone {latest}"
    summary = f"rclone {current} -> {latest}"
    _emit_output(changed="true", title=title, summary=summary)
    return 0


def main() -> int:
    if sys.argv[1:] == ["--latest"]:
        return adopt_latest()
    if sys.argv[1:]:
        raise SystemExit("Pass --latest, or no arguments to report")

    current = current_version()
    latest = latest_version()
    print(f"Pinned: rclone {current}. Current stable: rclone {latest}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
