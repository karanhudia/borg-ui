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

To adopt a new Borg version, change the version in ``Dockerfile.runtime-base``
and run::

    python scripts/refresh_borg_binary_manifest.py

which reads that version and rewrites this manifest.
``tests/unit/test_borg_binaries.py`` fails if the two ever disagree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

MANIFEST_PATH = Path(__file__).with_name("borg_binaries.json")


class BorgBinary(NamedTuple):
    """One published binary: which machine it runs on, and what it hashes to."""

    arch: str  # as reported by `uname -m`
    min_glibc: str  # oldest glibc the binary was built against
    asset: str
    sha256: str


def _load() -> tuple[dict, str, dict[str, str]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    binaries = {
        version: tuple(BorgBinary(**entry) for entry in entries)
        for version, entries in manifest["binaries"].items()
    }
    return binaries, manifest["release_url"], manifest["current"]


# Only Linux variants are listed: the managed agent installer is Debian-family
# only. 32-bit ARM and musl have no published binary at all, which is why the
# installer has to fail explicitly for them rather than guess.
BORG_BINARIES, RELEASE_URL, CURRENT_VERSIONS = _load()


def binary_table(versions: dict[str, str | None]) -> str:
    """Render the installer's binary lookup table.

    ``versions`` maps a Borg major ("1", "2") to the exact version the server
    runs. Each output line is ``major arch min_glibc sha256 url``; the
    installer picks the newest glibc build its machine can run. A major with an
    unknown version contributes no rows, and the installer then says so instead
    of installing something else.
    """
    lines = []
    for major, version in sorted(versions.items()):
        if not version:
            continue
        for binary in BORG_BINARIES.get(version, ()):
            url = RELEASE_URL.format(version=version, asset=binary.asset)
            lines.append(
                f"{major} {binary.arch} {binary.min_glibc} {binary.sha256} {url}"
            )
    return "\n".join(lines)
