"""The binary manifest must describe the Borg versions this repo builds.

A version bump touches the runtime base and the manifest. If only the former is
done, nothing fails loudly: the server reports a version the manifest has no
entry for, and agents are simply told their server offers no Borg to install.
These tests turn that quiet degradation into a failed build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.borg_binaries import BORG_BINARIES, CURRENT_VERSIONS, binary_table

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile.runtime-base"


def dockerfile_versions() -> dict[str, str]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    return {
        major: re.search(rf"^ARG BORG{major}_VERSION=(\S+)", text, re.M).group(1)
        for major in ("1", "2")
    }


@pytest.mark.parametrize("major", ["1", "2"])
def test_manifest_matches_the_version_the_image_builds(major: str):
    expected = dockerfile_versions()[major]

    assert CURRENT_VERSIONS[major] == expected, (
        f"Dockerfile.runtime-base builds Borg {expected}, but the manifest records "
        f"{CURRENT_VERSIONS[major]}. Run scripts/refresh_borg_binary_manifest.py."
    )
    assert BORG_BINARIES.get(expected), (
        f"No published binaries recorded for Borg {expected}. "
        "Run scripts/refresh_borg_binary_manifest.py."
    )


@pytest.mark.parametrize("major", ["1", "2"])
def test_both_supported_architectures_are_covered(major: str):
    """A missing architecture only shows up when someone enrols a node on it."""
    version = CURRENT_VERSIONS[major]

    arches = {binary.arch for binary in BORG_BINARIES[version]}
    assert {"x86_64", "aarch64"} <= arches, f"Borg {version} covers only {arches}"


def test_checksums_are_well_formed():
    for version, binaries in BORG_BINARIES.items():
        for binary in binaries:
            assert re.fullmatch(r"[0-9a-f]{64}", binary.sha256), (
                f"{version}/{binary.asset} has a malformed sha256"
            )


def test_binary_table_renders_one_row_per_binary():
    table = binary_table(CURRENT_VERSIONS)

    rows = [row.split() for row in table.splitlines()]
    assert len(rows) == sum(
        len(BORG_BINARIES[version]) for version in CURRENT_VERSIONS.values()
    )
    for major, arch, min_glibc, sha256, url in rows:
        assert major in {"1", "2"}
        assert arch in {"x86_64", "aarch64"}
        assert re.fullmatch(r"\d+\.\d+", min_glibc)
        assert re.fullmatch(r"[0-9a-f]{64}", sha256)
        assert url.startswith("https://github.com/borgbackup/borg/releases/download/")


def test_an_unknown_version_contributes_no_rows():
    """The installer then reports that the server offers no Borg, rather than
    quietly installing a version nobody asked for."""
    assert binary_table({"1": "9.9.9"}) == ""
