"""Static Borg binaries published with each upstream release.

Borg publishes no wheels on PyPI, only sdists, so any pip-based install
compiles from source and needs a build toolchain on the target machine. The
static single-file binaries shipped with each release let a managed agent get
the exact Borg version its server runs without one.

The data lives in ``borg_binaries.json`` beside this module rather than in
Python, because the agent image build reads the same file: the checksums are
stated once and consumed by everything that needs them.

The manifest is checked in rather than fetched at runtime so that the
installer can verify what it downloaded against a value the server did not
learn from the same place it got the file.

To adopt a new Borg version, change the version in ``docker/runtime-base.env``
and run::

    python scripts/refresh_borg_binary_manifest.py

which reads that file and rewrites this manifest.
``tests/unit/test_borg_binaries.py`` fails if the two ever disagree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

MANIFEST_PATH = Path(__file__).with_name("borg_binaries.json")


class BorgBinary(NamedTuple):
    """One published binary: which machine it runs on, and what it hashes to."""

    platform: str  # "linux" or "darwin"
    arch: str  # as reported by `uname -m`
    # The oldest platform the binary was built against: a glibc version on
    # Linux, a macOS major on Darwin. The installer compares it with what the
    # machine has, in either case as a version number.
    floor: str
    asset: str
    sha256: str


def _binary(entry: dict) -> BorgBinary:
    platform = entry.get("platform", "linux")
    floor = entry["min_glibc"] if platform == "linux" else entry["min_macos"]
    return BorgBinary(platform, entry["arch"], floor, entry["asset"], entry["sha256"])


def _load() -> tuple[dict, str, dict[str, str]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    binaries = {
        version: tuple(_binary(entry) for entry in entries)
        for version, entries in manifest["binaries"].items()
    }
    return binaries, manifest["release_url"], manifest["current"]


# Linux and macOS variants are listed, the platforms the managed agent
# installer runs on. 32-bit ARM and musl have no published binary at all,
# which is why the installer has to fail explicitly for them rather than guess.
BORG_BINARIES, RELEASE_URL, CURRENT_VERSIONS = _load()


def binary_table(versions: dict[str, str | None]) -> str:
    """Render the installer's binary lookup table.

    ``versions`` maps a Borg major ("1", "2") to the exact version the server
    runs. Each output line is ``major platform arch floor sha256 url``; the
    installer picks the newest build of its platform and architecture that
    its machine can run. A major with an unknown version contributes no rows,
    and the installer then says so instead of installing something else.
    """
    lines = []
    for major, version in sorted(versions.items()):
        if not version:
            continue
        for binary in BORG_BINARIES.get(version, ()):
            url = RELEASE_URL.format(version=version, asset=binary.asset)
            lines.append(
                f"{major} {binary.platform} {binary.arch} {binary.floor} "
                f"{binary.sha256} {url}"
            )
    return "\n".join(lines)
