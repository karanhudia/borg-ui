"""The refresh script must see every Borg release, and must notice when adopting
one narrows which machines a server-source install can reach.

borgbackup announces neither in its changelog. 1.4.5 quietly stopped publishing
the glibc 2.31 x86_64 build, so a version bump is measured against the manifest
it replaces and any regression is surfaced in the PR. 2.0.0b22 quietly renamed
the Linux pair from glibc235 to glibc239, so which assets count as installable
is derived from the name rather than listed.
"""

from __future__ import annotations

import scripts.refresh_borg_binary_manifest as refresh
from scripts.refresh_borg_binary_manifest import (
    _covers_both_arches,
    _coverage,
    _coverage_regressions,
    _linux_binaries,
)

BOTH_ARCHES = ("borg-linux-glibc239-x86_64-gh", "borg-linux-glibc239-arm64-gh")


def _release(*names: str, tag: str = "0.0.0") -> dict:
    """A release payload carrying the named assets, digests filled in."""
    return {
        "tag_name": tag,
        "assets": [{"name": name, "digest": "sha256:" + "0" * 64} for name in names],
    }


def test_linux_assets_are_read_from_their_name():
    """The glibc floor is the digits in the asset name, whichever they are — the
    list of names seen so far does not get a say."""
    entries = _linux_binaries(
        _release(
            "borg-linux-glibc239-x86_64-gh",
            "borg-linux-glibc239-arm64-gh",
            "borg-linux-glibc231-x86_64",
        )
    )

    assert [(entry["arch"], entry["min_glibc"]) for entry in entries] == [
        ("x86_64", "2.39"),
        ("aarch64", "2.39"),
        ("x86_64", "2.31"),
    ]


def test_assets_the_installer_cannot_use_are_ignored():
    """Other platforms, the archive and signature companions, and the sources."""
    assert (
        _linux_binaries(
            _release(
                "borg-macos-15-arm64-gh",
                "borg-freebsd-15-x86_64-gh",
                "borg-linux-glibc239-x86_64-gh.tgz",
                "borg-linux-glibc231-x86_64.asc",
                "borgbackup-2.0.0b22.tar.gz",
                "00_README.txt",
            )
        )
        == []
    )


def test_a_renamed_linux_pair_still_counts_as_adoptable():
    """The 2.0.0b22 regression: recognised by a fixed list of names, this release
    read as one that publishes nothing installable, and was passed over without
    a word — which is how a Borg 2 release went unnoticed for a month."""
    assert _covers_both_arches(
        _release("borg-linux-glibc239-x86_64-gh", "borg-linux-glibc239-arm64-gh")
    )


def test_coverage_takes_the_lowest_glibc_per_arch():
    binaries = [
        {"arch": "x86_64", "min_glibc": "2.35"},
        {"arch": "x86_64", "min_glibc": "2.31"},
        {"arch": "aarch64", "min_glibc": "2.35"},
    ]
    assert _coverage(binaries) == {"x86_64": "2.31", "aarch64": "2.35"}


def test_raised_glibc_floor_is_reported():
    """The real 1.4.4 -> 1.4.5 case: x86_64 stays, but its floor rises."""
    old = [
        {"arch": "x86_64", "min_glibc": "2.31"},
        {"arch": "x86_64", "min_glibc": "2.35"},
        {"arch": "aarch64", "min_glibc": "2.35"},
    ]
    new = [
        {"arch": "x86_64", "min_glibc": "2.35"},
        {"arch": "aarch64", "min_glibc": "2.35"},
    ]
    assert _coverage_regressions(old, new) == ["raises x86_64 glibc floor 2.31 -> 2.35"]


def test_dropped_architecture_is_reported():
    old = [
        {"arch": "x86_64", "min_glibc": "2.35"},
        {"arch": "aarch64", "min_glibc": "2.35"},
    ]
    new = [{"arch": "x86_64", "min_glibc": "2.35"}]
    assert _coverage_regressions(old, new) == ["drops aarch64 (was glibc 2.35)"]


def test_no_regression_when_coverage_holds_or_widens():
    old = [{"arch": "x86_64", "min_glibc": "2.35"}]
    new = [
        {"arch": "x86_64", "min_glibc": "2.31"},
        {"arch": "aarch64", "min_glibc": "2.35"},
    ]
    assert _coverage_regressions(old, new) == []


def test_a_newer_release_without_both_arches_is_named_not_just_skipped():
    """Passing one over is right — it may still be uploading — but saying
    nothing is how the b22 rename went unnoticed for a month."""
    releases = [
        _release("borg-linux-glibc239-x86_64-gh", tag="2.0.0b23"),  # no arm64 yet
        _release(*BOTH_ARCHES, tag="2.0.0b22"),
        _release(*BOTH_ARCHES, tag="1.4.5"),
    ]

    latest, unadoptable = _with_releases(releases, refresh.latest_adoptable)

    assert latest == {"1": "1.4.5", "2": "2.0.0b22"}
    assert len(unadoptable) == 1
    assert "2.0.0b23" in unadoptable[0]
    assert "2.0.0b22" in unadoptable[0]


def test_nothing_is_reported_when_the_newest_release_is_the_one_picked():
    releases = [_release(*BOTH_ARCHES, tag=tag) for tag in ("2.0.0b22", "1.4.5")]

    latest, unadoptable = _with_releases(releases, refresh.latest_adoptable)

    assert latest == {"1": "1.4.5", "2": "2.0.0b22"}
    assert unadoptable == []


def test_a_passed_over_release_reaches_the_workflow_with_nothing_to_bump(
    monkeypatch, tmp_path
):
    """The shape of the miss: the pin is already at the newest adoptable
    release, so no PR is opened and the job output is the only place the
    skipped one can surface — the workflow fails the run on it."""
    releases = [
        _release("borg-linux-glibc239-x86_64-gh", tag="2.0.0b23"),
        _release(*BOTH_ARCHES, tag="2.0.0b22"),
        _release(*BOTH_ARCHES, tag="1.4.5"),
    ]
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        refresh, "versions_from_env", lambda: {"1": "1.4.5", "2": "2.0.0b22"}
    )

    assert _with_releases(releases, refresh.adopt_latest) == 0

    written = output.read_text(encoding="utf-8")
    assert "changed=false" in written
    assert "unadoptable=Borg 2.0.0b23 " in written


def _with_releases(releases, call):
    """Run `call` with the release API answering `releases`.

    Not a fixture: two of these tests want the value returned, one wants the
    side effect, and both need the same one-line stand-in for the network.
    """
    original = refresh._get_json
    refresh._get_json = lambda url: releases
    try:
        return call()
    finally:
        refresh._get_json = original
