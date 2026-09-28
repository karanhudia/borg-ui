"""The Python runtime manifest must follow the minor this repo builds with.

A macOS endpoint runs the agent on the build this manifest names. If the
pinned minor moves and the manifest does not, the endpoint quietly runs an
older Python than the image; these tests turn that into a failed build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import scripts.refresh_python_runtime_manifest as refresh
from app.api.python_runtimes import (
    CURRENT_PYTHON_RUNTIME,
    PYTHON_RUNTIMES,
    runtime_table,
)

ENV_FILE = Path(__file__).resolve().parents[2] / "docker" / "runtime-base.env"


def pinned_minor() -> str:
    text = ENV_FILE.read_text(encoding="utf-8")
    return re.search(r"^PYTHON_VERSION=(\d+\.\d+)", text, re.M).group(1)


def test_the_manifest_follows_the_pinned_minor():
    assert CURRENT_PYTHON_RUNTIME.startswith(f"{pinned_minor()}."), (
        f"runtime-base.env pins Python {pinned_minor()}, but the manifest records "
        f"{CURRENT_PYTHON_RUNTIME}. Run scripts/refresh_python_runtime_manifest.py."
    )
    assert PYTHON_RUNTIMES.get(CURRENT_PYTHON_RUNTIME)


def test_both_macos_architectures_are_covered():
    runtimes = PYTHON_RUNTIMES[CURRENT_PYTHON_RUNTIME]

    assert {(r.platform, r.arch) for r in runtimes} >= {
        ("darwin", "x86_64"),
        ("darwin", "aarch64"),
    }


def test_checksums_and_sources_are_well_formed():
    for version, runtimes in PYTHON_RUNTIMES.items():
        for runtime in runtimes:
            assert re.fullmatch(r"[0-9a-f]{64}", runtime.sha256), (
                f"{version}/{runtime.asset} has a malformed sha256"
            )
            assert runtime.url.startswith(
                "https://github.com/astral-sh/python-build-standalone/releases/download/"
            )
            assert runtime.url.endswith("install_only.tar.gz")


def test_runtime_table_renders_one_row_per_build():
    rows = [row.split() for row in runtime_table().splitlines()]

    assert len(rows) == len(PYTHON_RUNTIMES[CURRENT_PYTHON_RUNTIME])
    for platform, arch, sha256, url in rows:
        assert platform == "darwin"
        assert arch in {"x86_64", "aarch64"}
        assert re.fullmatch(r"[0-9a-f]{64}", sha256)
        assert url.startswith("https://")


def test_an_unknown_version_contributes_no_rows():
    assert runtime_table("9.9.9+20990101") == ""


def _release(*names: str, tag: str = "20260924", **flags) -> dict:
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": name,
                "digest": "sha256:" + "0" * 64,
                "browser_download_url": f"https://example.invalid/{tag}/{name}",
            }
            for name in names
        ],
        **flags,
    }


BOTH = (
    "cpython-3.12.14+20260924-aarch64-apple-darwin-install_only.tar.gz",
    "cpython-3.12.14+20260924-x86_64-apple-darwin-install_only.tar.gz",
)


def test_only_the_pinned_minor_of_the_install_only_archives_is_read():
    version, entries = refresh.darwin_runtimes(
        _release(
            *BOTH,
            "cpython-3.13.9+20260924-aarch64-apple-darwin-install_only.tar.gz",
            "cpython-3.12.14+20260924-aarch64-apple-darwin-install_only.tar.gz.sha256",
            "cpython-3.12.14+20260924-x86_64-unknown-linux-gnu-install_only.tar.gz",
            "cpython-3.12.14+20260924-aarch64-apple-darwin-debug-full.tar.zst",
        ),
        "3.12",
    )

    assert version == "3.12.14+20260924"
    assert [(e["platform"], e["arch"]) for e in entries] == [
        ("darwin", "aarch64"),
        ("darwin", "x86_64"),
    ]
    assert entries[0]["url"].endswith(BOTH[0])


def test_the_newest_complete_release_is_picked():
    """A release whose second archive is still uploading is passed over."""
    releases = [
        _release(
            "cpython-3.12.15+20261001-aarch64-apple-darwin-install_only.tar.gz",
            tag="20261001",
        ),
        _release(*BOTH, tag="20260924"),
    ]

    version, entries = refresh.latest_build(releases, "3.12")

    assert version == "3.12.14+20260924"
    assert len(entries) == 2


def test_a_release_still_being_hashed_is_passed_over():
    """GitHub serves "digest": null before it has hashed an upload. Such a
    release is not complete yet, and an earlier one is taken instead."""
    unhashed = _release(
        "cpython-3.12.15+20261001-aarch64-apple-darwin-install_only.tar.gz",
        "cpython-3.12.15+20261001-x86_64-apple-darwin-install_only.tar.gz",
        tag="20261001",
    )
    unhashed["assets"][0]["digest"] = None

    assert refresh.darwin_runtimes(unhashed, "3.12") == ("", [])
    assert refresh.latest_build([unhashed, _release(*BOTH)], "3.12")[0] == (
        "3.12.14+20260924"
    )


def test_a_digest_that_is_not_sha256_stops_the_refresh():
    """The manifest must never record a build it cannot verify."""
    release = _release(*BOTH)
    release["assets"][0]["digest"] = "md5:" + "0" * 32

    with pytest.raises(SystemExit, match="No sha256 digest"):
        refresh.darwin_runtimes(release, "3.12")


def test_the_release_pages_are_walked_until_a_complete_build_is_found(monkeypatch):
    """A pinned minor built some time ago sits pages back in the listing."""
    pages = {
        1: [
            _release("cpython-3.13.9+20260924-aarch64-apple-darwin-install_only.tar.gz")
        ],
        2: [_release(*BOTH)],
    }
    monkeypatch.setattr(
        refresh,
        "_get_json",
        lambda url: pages.get(int(url.rsplit("page=", 1)[1]), []),
    )

    assert refresh.latest_build(refresh.published_releases(), "3.12")[0] == (
        "3.12.14+20260924"
    )


def test_drafts_and_prereleases_are_skipped():
    releases = [
        _release(*BOTH, tag="20261002", draft=True),
        _release(*BOTH, tag="20261001", prerelease=True),
        _release(*BOTH, tag="20260924"),
    ]

    assert refresh.latest_build(releases, "3.12")[0] == "3.12.14+20260924"
