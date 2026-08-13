#!/usr/bin/env python3
"""Rewrite app/api/borg_binaries.json for the Borg versions this repo builds.

The versions are stated once, in docker/runtime-base.env — the single source of
truth. This script reads them from there, asks the GitHub release API for the
sha256 digest of each published Linux binary, and writes the manifest. Adopting a
new Borg version is therefore: change runtime-base.env, run this, commit.

    python scripts/refresh_borg_binary_manifest.py            # versions from runtime-base.env
    python scripts/refresh_borg_binary_manifest.py 1.4.5 2.0.0b22   # or state them
    python scripts/refresh_borg_binary_manifest.py --latest   # adopt newer releases

--latest asks GitHub which releases exist, and if a newer one carries the Linux
binaries this installer needs, bumps the version in runtime-base.env (and the
Dockerfile ARG that mirrors it) and regenerates the manifest. It is what the
scheduled workflow runs to open the adoption PR; the runtime-base image still has
to be rebuilt and re-tagged by a human, which is the point — the red build is the
checklist.

The digests come from the release API rather than from hashing a download, so a
version bump does not require pulling ~180 MB of binaries. Nothing here runs at
build or run time: the manifest is committed so that the installer verifies a
download against a value it did not fetch alongside the file.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "docker" / "runtime-base.env"
DOCKERFILE = REPO_ROOT / "Dockerfile.runtime-base"
MANIFEST = REPO_ROOT / "app" / "api" / "borg_binaries.json"

API = "https://api.github.com/repos/borgbackup/borg/releases/tags/{version}"
RELEASES_API = "https://api.github.com/repos/borgbackup/borg/releases?per_page=100"
RELEASE_URL = "https://github.com/borgbackup/borg/releases/download/{version}/{asset}"

# Published asset name -> (uname -m arch, oldest glibc it was built against).
# Assets outside this list are ignored: macOS and FreeBSD builds, and the source
# tarballs, are not something the Debian-family installer can use.
KNOWN_VARIANTS = {
    "borg-linux-glibc231-x86_64": ("x86_64", "2.31"),
    "borg-linux-glibc235-x86_64-gh": ("x86_64", "2.35"),
    "borg-linux-glibc235-arm64-gh": ("aarch64", "2.35"),
}


def _get_json(url: str):
    """Fetch and decode JSON, authenticating if a token is in the environment.

    The GitHub API rate-limits anonymous callers to 60 requests an hour, which a
    scheduled workflow shares with everything else on the runner. GITHUB_TOKEN
    lifts that to 5000; unset (a local run), the request is anonymous and still
    works.
    """
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json"}
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def versions_from_env() -> dict[str, str]:
    """The Borg versions this repo's runtime base installs, from the single source
    of truth."""
    text = ENV_FILE.read_text(encoding="utf-8")
    versions = {}
    for major in ("1", "2"):
        match = re.search(rf"^BORG{major}_VERSION=(\S+)", text, re.M)
        if not match:
            raise SystemExit(f"No BORG{major}_VERSION in {ENV_FILE.name}")
        versions[major] = match.group(1)
    return versions


def _linux_binaries(release: dict) -> list[dict]:
    """The manifest entries an installer can use from a release's assets."""
    entries = []
    for asset in release.get("assets", []):
        variant = KNOWN_VARIANTS.get(asset["name"])
        if variant is None:
            continue
        digest = asset.get("digest", "")
        if not digest.startswith("sha256:"):
            raise SystemExit(f"No sha256 digest published for {asset['name']}")
        arch, min_glibc = variant
        entries.append(
            {
                "arch": arch,
                "min_glibc": min_glibc,
                "asset": asset["name"],
                "sha256": digest.removeprefix("sha256:"),
            }
        )
    return entries


def binaries_for(version: str) -> list[dict]:
    entries = _linux_binaries(_get_json(API.format(version=version)))
    if not entries:
        raise SystemExit(
            f"Borg {version} publishes no Linux binary this installer can use"
        )
    return entries


def write_manifest(current: dict[str, str]) -> None:
    """Regenerate borg_binaries.json for the given Borg 1 and Borg 2 versions."""
    manifest = {
        "current": current,
        "release_url": RELEASE_URL,
        "binaries": {version: binaries_for(version) for version in current.values()},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for version, entries in manifest["binaries"].items():
        print(f"  {version}: {len(entries)} binaries")
    print(f"Wrote {MANIFEST.relative_to(REPO_ROOT)}")


def _covers_both_arches(release: dict) -> bool:
    """A release is adoptable only if it carries both architectures the tests
    require; a half-published one is skipped and picked up on a later run."""
    return {"x86_64", "aarch64"} <= {
        entry["arch"] for entry in _linux_binaries(release)
    }


def latest_adoptable() -> dict[str, str]:
    """The newest release GitHub publishes for each line: a stable 1.x, and a
    2.x that may still be a beta, since that is what this repo pins today."""
    latest: dict[str, Version] = {}
    for release in _get_json(RELEASES_API):
        if release.get("draft"):
            continue
        try:
            version = Version(release["tag_name"])
        except InvalidVersion:
            continue
        major = str(version.major)
        if major not in ("1", "2"):
            continue
        if major == "1" and version.is_prerelease:
            continue
        if version <= latest.get(major, Version("0")):
            continue
        if _covers_both_arches(release):
            latest[major] = version
    if set(latest) != {"1", "2"}:
        missing = {"1", "2"} - set(latest)
        raise SystemExit(f"No adoptable Borg release found for line(s) {missing}")
    return {major: str(version) for major, version in latest.items()}


def _rewrite(path: Path, pattern: str, new_version: str) -> None:
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(pattern, rf"\g<1>{new_version}", text, flags=re.M)
    if not count:
        raise SystemExit(f"No match for {pattern!r} in {path.name}")
    path.write_text(text, encoding="utf-8")


def bump_version(major: str, new_version: str) -> None:
    """Bump BORG{major}_VERSION in the versions file (the truth) and in the
    Dockerfile ARG default that mirrors it — the guard test keeps them in step, so
    the mechanical half updates both. The runtime-base tag/image are the human
    half and stay for the checklist."""
    _rewrite(ENV_FILE, rf"^(BORG{major}_VERSION=)\S+", new_version)
    _rewrite(DOCKERFILE, rf"^(ARG BORG{major}_VERSION=)\S+", new_version)


def _coverage(binaries: list[dict]) -> dict[str, str]:
    """The lowest glibc offered per architecture — the floor a machine of that
    architecture must clear to get a server-source binary at all."""
    lowest: dict[str, str] = {}
    for entry in binaries:
        arch, glibc = entry["arch"], entry["min_glibc"]
        if arch not in lowest or Version(glibc) < Version(lowest[arch]):
            lowest[arch] = glibc
    return lowest


def _coverage_regressions(old: list[dict], new: list[dict]) -> list[str]:
    """How adopting `new` narrows the platforms a server-source install reaches.

    borgbackup changes which static binaries it publishes without saying so in
    the changelog — 1.4.5 dropped the glibc 2.31 x86_64 build, raising that floor
    to 2.35 with no release note. A version bump can therefore quietly drop an
    architecture or push its glibc floor past machines that used to be covered.
    Comparing the manifests turns that into a line the PR can shout.
    """
    before, after = _coverage(old), _coverage(new)
    notes = []
    for arch, floor in sorted(before.items()):
        if arch not in after:
            notes.append(f"drops {arch} (was glibc {floor})")
        elif Version(after[arch]) > Version(floor):
            notes.append(f"raises {arch} glibc floor {floor} -> {after[arch]}")
    return notes


def _emit_output(**values: str) -> None:
    """Hand results to the workflow step through GITHUB_OUTPUT, when set.

    A value spanning several lines is written with the heredoc form GitHub
    Actions requires; single-line values keep the plain key=value form.
    """
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
    """Bump the versions file, its Dockerfile mirror, and the manifest to the
    newest published releases."""
    current = versions_from_env()
    latest = latest_adoptable()
    bumps = {
        major: latest[major]
        for major in ("1", "2")
        if Version(latest[major]) > Version(current[major])
    }
    if not bumps:
        print(f"Up to date: Borg {current['1']}, {current['2']}")
        _emit_output(changed="false")
        return 0

    # Read the coverage the outgoing versions offer before the manifest is
    # overwritten, so the new binaries can be measured against it.
    old_binaries = json.loads(MANIFEST.read_text(encoding="utf-8")).get("binaries", {})

    warnings = []
    for major, new_version in bumps.items():
        print(f"Borg {major}: {current[major]} -> {new_version}")
        bump_version(major, new_version)
        regressions = _coverage_regressions(
            old_binaries.get(current[major], []), binaries_for(new_version)
        )
        for note in regressions:
            warnings.append(f"Borg {major} {new_version} {note}")
    write_manifest({**current, **bumps})

    # A new Borg version is a fresh image lineage — reset the runtime-base revision
    # to 1. The tag it computes then names an image not built yet, which is what
    # keeps the base-image guard red until a human rebuilds and re-points it.
    _rewrite(ENV_FILE, r"^(RUNTIME_BASE_REVISION=)\S+", "1")

    title = "chore(agent-installer): adopt " + ", ".join(
        f"Borg {major} {ver}" for major, ver in bumps.items()
    )
    summary = "; ".join(
        f"Borg {major} {current[major]} -> {ver}" for major, ver in bumps.items()
    )
    warnings_md = ""
    if warnings:
        title += " — coverage regression"
        print("\nCOVERAGE REGRESSION:")
        for note in warnings:
            print(f"  - {note}")
        warnings_md = (
            "> [!WARNING]\n"
            "> This bump narrows which machines a server-source install reaches. "
            "Affected machines fall back to `--borg-source distro`:\n"
            + "\n".join(f"> - {note}" for note in warnings)
        )
    _emit_output(changed="true", title=title, summary=summary, warnings_md=warnings_md)
    return 0


def main() -> int:
    if sys.argv[1:] == ["--latest"]:
        return adopt_latest()

    if len(sys.argv) > 1:
        given = sys.argv[1:]
        if len(given) != 2:
            raise SystemExit(
                "Pass both versions (Borg 1 then Borg 2), --latest, or neither"
            )
        current = {"1": given[0], "2": given[1]}
    else:
        current = versions_from_env()
        print(f"Versions from {ENV_FILE.name}: {current['1']}, {current['2']}")

    write_manifest(current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
