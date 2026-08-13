"""The refresh script must notice when adopting a Borg release narrows which
machines a server-source install can reach.

borgbackup does not announce dropped binaries in its changelog — 1.4.5 quietly
stopped publishing the glibc 2.31 x86_64 build — so the version bump is measured
against the manifest it replaces, and any regression is surfaced in the PR.
"""

from __future__ import annotations

from scripts.refresh_borg_binary_manifest import _coverage, _coverage_regressions


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
