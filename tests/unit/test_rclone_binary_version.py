"""The rclone adoption script parses upstream's published version and checksums.

The runtime base ships the official static rclone binary, and a scheduled job
bumps the pin when a newer stable is out (issue #798). These cover the parsing
that turns downloads.rclone.org's plain-text files into the version and per-arch
checksums the Dockerfile verifies against — the network calls stay out of the
test.
"""

from __future__ import annotations

import pytest

from scripts.refresh_rclone_binary_version import _parse_sha256sums, _parse_version


def test_parses_bare_version_from_version_txt():
    assert _parse_version("rclone v1.75.0\n") == "1.75.0"


def test_parses_version_without_leading_v():
    assert _parse_version("1.75.0") == "1.75.0"


def test_unparseable_version_is_an_error():
    with pytest.raises(SystemExit):
        _parse_version("rclone beta")


SHA256SUMS = (
    "aa2804e08f48250e71009c727124b6341cd0288465804a9a09d14663cabafbaa  "
    "rclone-v1.75.0-linux-amd64.zip\n"
    "d0ad88ba4c8e285b7c9efa591e0ab643280a91741e13c27f3a9c0957ccfa5203  "
    "rclone-v1.75.0-linux-arm64.zip\n"
    "0000000000000000000000000000000000000000000000000000000000000000  "
    "rclone-v1.75.0-osx-amd64.zip\n"
)


def test_parses_both_arch_checksums():
    sums = _parse_sha256sums(SHA256SUMS, "1.75.0")
    assert sums == {
        "amd64": "aa2804e08f48250e71009c727124b6341cd0288465804a9a09d14663cabafbaa",
        "arm64": "d0ad88ba4c8e285b7c9efa591e0ab643280a91741e13c27f3a9c0957ccfa5203",
    }


def test_ignores_other_platforms_and_wrong_version():
    # An osx asset must not leak in, and a version mismatch must match nothing.
    assert _parse_sha256sums(SHA256SUMS, "1.74.0") == {}
