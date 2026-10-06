"""The refresh script must see every Borg release, and must notice when adopting
one narrows which machines a server-source install can reach.

borgbackup announces neither in its changelog. 1.4.5 quietly stopped publishing
the glibc 2.31 x86_64 build, so a version bump is measured against the manifest
it replaces and any regression is surfaced in the PR. A Borg 2 release quietly
renamed the Linux pair from glibc235 to glibc239, so which assets count as
installable is derived from the name rather than listed.
"""

from __future__ import annotations

import io
import urllib.error

import pytest

import scripts.refresh_borg_binary_manifest as refresh
from scripts.refresh_borg_binary_manifest import (
    _covers_both_arches,
    _coverage,
    _coverage_regressions,
    _darwin_binaries,
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
                "borgbackup-2.0.0b25.tar.gz",
                "00_README.txt",
            )
        )
        == []
    )


def test_macos_assets_are_read_from_their_name():
    """The macOS floor is the runner's major in the name, read the same way the
    glibc digits are; the Linux reader still leaves them alone."""
    release = _release(
        "borg-macos-15-arm64-gh",
        "borg-macos-15-x86_64-gh",
        "borg-macos-15-arm64-gh.tgz",
        "borg-linux-glibc243-x86_64-gh",
    )

    assert [
        (entry["platform"], entry["arch"], entry["min_macos"])
        for entry in _darwin_binaries(release)
    ] == [("darwin", "aarch64", "15"), ("darwin", "x86_64", "15")]
    assert [entry["platform"] for entry in _linux_binaries(release)] == ["linux"]


def test_a_macos_asset_without_a_digest_is_left_out_not_fatal():
    """GitHub serves "digest": null while it hashes an asset; for a macOS asset
    that must not stop the manifest, and with it the Linux pin."""
    release = _release("borg-macos-15-arm64-gh", "borg-macos-15-x86_64-gh")
    release["assets"][0]["digest"] = None

    assert [entry["arch"] for entry in _darwin_binaries(release)] == ["x86_64"]


def test_a_dropped_macos_pair_is_a_regression_not_a_stall():
    """macOS coverage must not hold the Linux pin back, so a release without
    it stays adoptable and the loss is shouted in the PR instead."""
    old = [
        {"platform": "linux", "arch": "x86_64", "min_glibc": "2.35"},
        {"platform": "darwin", "arch": "aarch64", "min_macos": "15"},
    ]
    new = [{"platform": "linux", "arch": "x86_64", "min_glibc": "2.35"}]

    assert _coverage_regressions(old, new) == ["drops darwin/aarch64 (was macOS 15)"]
    assert _covers_both_arches(_release(*BOTH_ARCHES))


def test_a_renamed_linux_pair_still_counts_as_adoptable():
    """The glibc239 rename: recognised by a fixed list of names, that release
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
    nothing is how the glibc239 rename went unnoticed for a month."""
    releases = [
        _release("borg-linux-glibc239-x86_64-gh", tag="2.0.0b26"),  # no arm64 yet
        _release(*BOTH_ARCHES, tag="2.0.0b25"),
        _release(*BOTH_ARCHES, tag="1.4.5"),
    ]

    latest, unadoptable = _with_releases(releases, refresh.latest_adoptable)

    assert latest == {"1": "1.4.5", "2": "2.0.0b25"}
    assert len(unadoptable) == 1
    assert "2.0.0b26" in unadoptable[0]
    assert "2.0.0b25" in unadoptable[0]


def test_nothing_is_reported_when_the_newest_release_is_the_one_picked():
    releases = [_release(*BOTH_ARCHES, tag=tag) for tag in ("2.0.0b25", "1.4.5")]

    latest, unadoptable = _with_releases(releases, refresh.latest_adoptable)

    assert latest == {"1": "1.4.5", "2": "2.0.0b25"}
    assert unadoptable == []


def test_a_passed_over_release_reaches_the_workflow_with_nothing_to_bump(
    monkeypatch, tmp_path
):
    """The shape of the miss: the pin is already at the newest adoptable
    release, so no PR is opened and the job output is the only place the
    skipped one can surface — the workflow fails the run on it."""
    releases = [
        _release("borg-linux-glibc239-x86_64-gh", tag="2.0.0b26"),
        _release(*BOTH_ARCHES, tag="2.0.0b25"),
        _release(*BOTH_ARCHES, tag="1.4.5"),
    ]
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        refresh, "versions_from_env", lambda: {"1": "1.4.5", "2": "2.0.0b25"}
    )

    assert _with_releases(releases, refresh.adopt_latest) == 0

    written = output.read_text(encoding="utf-8")
    assert "changed=false" in written
    assert "unadoptable=Borg 2.0.0b26 " in written


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


# Borg 2 pins its store: 2.0.0b25 requires borgstore ~= 0.7.0, 2.0.0b24 ~= 0.6.1,
# and the runtime base installs exactly BORGSTORE_VERSION next to it. A Borg 2
# bump that left the store behind produced an adoption commit that could not
# build. The PyPI payloads below carry the fields the script reads, in the shape
# PyPI's JSON API serves them.

B25_REQUIRES_DIST = [
    "borghash~=0.1.0",
    "borgstore[blake3,rest]~=0.7.0",
    'borgstore[blake3,rest,s3]~=0.7.0; extra == "s3"',
    'borgstore[blake3,rest,sftp]~=0.7.0; extra == "sftp"',
    'borgstore[blake3,rclone,rest]~=0.7.0; extra == "rclone"',
    "msgpack>=1.0.3,<=1.1.2",
]


def _store_releases(
    *versions: str, yanked: tuple[str, ...] = (), requires_python: dict | None = None
) -> dict:
    requires_python = requires_python or {}
    return {
        "releases": {
            version: [
                {
                    "filename": f"borgstore-{version}.tar.gz",
                    "yanked": version in yanked,
                    "requires_python": requires_python.get(version, ">=3.11"),
                }
            ]
            for version in versions
        }
    }


def _pypi(requires_dist=B25_REQUIRES_DIST, store=None):
    """A stand-in for PyPI's JSON API: borgbackup's release metadata and the
    borgstore project page."""
    store = store or _store_releases("0.6.1", "0.6.4", "0.7.0")

    def get(url):
        if "/borgbackup/" in url:
            return {"info": {"requires_dist": requires_dist}}
        if "/borgstore/" in url:
            return store
        raise AssertionError(f"unexpected PyPI request {url}")

    return get


def _repo_files(tmp_path, monkeypatch, borgstore="0.6.1"):
    """Point the script at a throwaway copy of the files --latest rewrites, so the
    test reads the same whichever Borg 2 the checkout pins."""
    env = tmp_path / "runtime-base.env"
    env.write_text(
        "BORG1_VERSION=1.4.5\n"
        "BORG2_VERSION=2.0.0b24\n"
        f"BORGSTORE_VERSION={borgstore}\n"
        "PYTHON_VERSION=3.12\n"
        "RUNTIME_BASE_REVISION=3\n",
        encoding="utf-8",
    )
    dockerfile = tmp_path / "Dockerfile.runtime-base"
    dockerfile.write_text(
        "ARG BORG1_VERSION=1.4.5\n"
        "ARG BORG2_VERSION=2.0.0b24\n"
        f"ARG BORGSTORE_VERSION={borgstore}\n"
        "FROM scratch\n"
        "ARG BORG2_VERSION=2.0.0b24\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "borg_binaries.json"
    manifest.write_text('{"binaries": {}}\n', encoding="utf-8")
    monkeypatch.setattr(refresh, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(refresh, "ENV_FILE", env)
    monkeypatch.setattr(refresh, "DOCKERFILE", dockerfile)
    monkeypatch.setattr(refresh, "MANIFEST", manifest)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return env, dockerfile, manifest, output


def _github(monkeypatch, *tags: str):
    """The release API answering with `tags`, each carrying both Linux arches."""
    releases = [_release(*BOTH_ARCHES, tag=tag) for tag in tags]
    by_tag = {release["tag_name"]: release for release in releases}

    def get(url):
        if url == refresh.RELEASES_API:
            return releases
        return by_tag[url.rstrip("/").rsplit("/", 1)[-1]]

    monkeypatch.setattr(refresh, "_get_json", get)


def test_a_borg2_bump_moves_borgstore_into_the_range_the_release_requires(
    monkeypatch, tmp_path
):
    """The 2.0.0b25 run: BORG2_VERSION moved to b25 while BORGSTORE_VERSION
    stayed at the 0.6.1 b24 needed, and the image could not install the pair."""
    env, dockerfile, _, output = _repo_files(tmp_path, monkeypatch)
    _github(monkeypatch, "2.0.0b25", "1.4.5")
    monkeypatch.setattr(refresh, "_get_pypi_json", _pypi(), raising=False)

    assert refresh.adopt_latest() == 0

    assert "BORG2_VERSION=2.0.0b25\n" in env.read_text(encoding="utf-8")
    assert "BORGSTORE_VERSION=0.7.0\n" in env.read_text(encoding="utf-8")
    assert "ARG BORGSTORE_VERSION=0.7.0\n" in dockerfile.read_text(encoding="utf-8")
    written = output.read_text(encoding="utf-8")
    assert (
        "title=chore(agent-installer): adopt Borg 2 2.0.0b25, borgstore 0.7.0\n"
        in written
    )
    assert "borgstore 0.6.1 -> 0.7.0" in written


def test_the_newest_installable_store_in_the_range_is_picked(monkeypatch):
    """Newest within ~= 0.7.0: not the next minor, not a yanked release, not a
    pre-release the range does not name."""
    store = _store_releases(
        "0.6.4", "0.7.0", "0.7.1", "0.7.2", "0.7.3rc1", "0.8.0", yanked=("0.7.2",)
    )
    monkeypatch.setattr(refresh, "_get_pypi_json", _pypi(store=store))

    assert refresh.borgstore_for("2.0.0b25", "3.12") == "0.7.1"


def test_a_store_release_for_newer_pythons_only_is_passed_over(monkeypatch):
    """The image runs PYTHON_VERSION; a borgstore that requires a newer Python
    would fail its build although an older one in the range installs."""
    store = _store_releases(
        "0.7.0", "0.7.1", requires_python={"0.7.0": ">=3.11", "0.7.1": ">=3.13"}
    )
    monkeypatch.setattr(refresh, "_get_pypi_json", _pypi(store=store))

    assert refresh.borgstore_for("2.0.0b25", "3.12") == "0.7.0"
    assert refresh.borgstore_for("2.0.0b25", "3.13") == "0.7.1"


def test_only_the_requirement_lines_pip_applies_to_the_image_count(monkeypatch):
    """borgbackup is installed without extras on PYTHON_VERSION: a line for
    another Python or for an extra must not narrow the range, or a range that
    pip resolves fine would read as unsatisfiable."""
    requires_dist = [
        'borgstore[rest]~=0.6.1; python_version < "3.12"',
        'borgstore[rest]~=0.7.0; python_version >= "3.12"',
        'borgstore[rest,s3]~=0.6.1; extra == "s3"',
    ]
    store = _store_releases("0.6.4", "0.7.0")
    monkeypatch.setattr(refresh, "_get_pypi_json", _pypi(requires_dist, store))

    assert refresh.borgstore_for("2.0.0b25", "3.12") == "0.7.0"
    assert refresh.borgstore_for("2.0.0b25", "3.11") == "0.6.4"


def test_a_pin_inside_the_range_still_moves_to_the_newest(monkeypatch, tmp_path):
    env, dockerfile, _, output = _repo_files(tmp_path, monkeypatch, borgstore="0.7.0")
    _github(monkeypatch, "2.0.0b26", "1.4.5")
    monkeypatch.setattr(
        refresh, "_get_pypi_json", _pypi(store=_store_releases("0.7.0", "0.7.1"))
    )

    assert refresh.adopt_latest() == 0

    assert "BORGSTORE_VERSION=0.7.1\n" in env.read_text(encoding="utf-8")
    assert "ARG BORGSTORE_VERSION=0.7.1\n" in dockerfile.read_text(encoding="utf-8")
    assert "borgstore 0.7.0 -> 0.7.1" in output.read_text(encoding="utf-8")


def test_a_store_already_at_the_newest_is_left_out_of_the_title(monkeypatch, tmp_path):
    env, _, _, output = _repo_files(tmp_path, monkeypatch, borgstore="0.7.0")
    _github(monkeypatch, "2.0.0b26", "1.4.5")
    monkeypatch.setattr(refresh, "_get_pypi_json", _pypi())

    assert refresh.adopt_latest() == 0

    assert "BORGSTORE_VERSION=0.7.0\n" in env.read_text(encoding="utf-8")
    written = output.read_text(encoding="utf-8")
    assert "title=chore(agent-installer): adopt Borg 2 2.0.0b26\n" in written
    assert "borgstore" not in written


def test_a_borg1_bump_leaves_the_store_and_pypi_alone(monkeypatch, tmp_path):
    env, dockerfile, _, _ = _repo_files(tmp_path, monkeypatch)
    _github(monkeypatch, "2.0.0b24", "1.4.6")

    def no_pypi(url):
        raise AssertionError(f"PyPI asked for {url} on a Borg 1 bump")

    monkeypatch.setattr(refresh, "_get_pypi_json", no_pypi)

    assert refresh.adopt_latest() == 0

    assert "BORG1_VERSION=1.4.6\n" in env.read_text(encoding="utf-8")
    assert "BORGSTORE_VERSION=0.6.1\n" in env.read_text(encoding="utf-8")
    assert "ARG BORGSTORE_VERSION=0.6.1\n" in dockerfile.read_text(encoding="utf-8")


def _unchanged(files, before):
    return [path.read_text(encoding="utf-8") for path in files] == before


def test_an_unreadable_pypi_fails_the_run_before_anything_is_written(
    monkeypatch, tmp_path
):
    """Red with a reason, never a pin guessed: without PyPI the run cannot know
    which store the new Borg 2 takes, so it opens no PR at all."""
    env, dockerfile, manifest, _ = _repo_files(tmp_path, monkeypatch)
    before = [path.read_text(encoding="utf-8") for path in (env, dockerfile, manifest)]
    _github(monkeypatch, "2.0.0b25", "1.4.5")

    def offline(url):
        raise urllib.error.URLError("temporary failure in name resolution")

    monkeypatch.setattr(refresh, "_get_pypi_json", offline)

    with pytest.raises(SystemExit) as raised:
        refresh.adopt_latest()

    assert "Borg 2.0.0b25" in str(raised.value)
    assert "temporary failure in name resolution" in str(raised.value)
    assert _unchanged((env, dockerfile, manifest), before)


def test_a_range_no_release_satisfies_is_named_and_nothing_is_written(
    monkeypatch, tmp_path
):
    env, dockerfile, manifest, _ = _repo_files(tmp_path, monkeypatch)
    before = [path.read_text(encoding="utf-8") for path in (env, dockerfile, manifest)]
    _github(monkeypatch, "2.0.0b25", "1.4.5")
    store = _store_releases("0.6.1", "0.7.0", yanked=("0.7.0",))
    monkeypatch.setattr(refresh, "_get_pypi_json", _pypi(store=store))

    with pytest.raises(SystemExit) as raised:
        refresh.adopt_latest()

    assert "requires borgstore~=0.7.0" in str(raised.value)
    assert _unchanged((env, dockerfile, manifest), before)


def test_a_release_without_a_store_requirement_fails_the_run(monkeypatch):
    monkeypatch.setattr(
        refresh, "_get_pypi_json", _pypi(requires_dist=["msgpack>=1.0.3"])
    )

    with pytest.raises(SystemExit, match="names no borgstore requirement"):
        refresh.borgstore_for("2.0.0b25", "3.12")


def test_pypi_is_asked_without_the_github_token(monkeypatch):
    """The workflow hands the script GITHUB_TOKEN for the release API; it must
    not travel to another host."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_secret")
    monkeypatch.setenv("GH_TOKEN", "ghs_secret")
    sent = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout):
        sent.append(request)
        return Response(b'{"releases": {}}')

    monkeypatch.setattr(refresh.urllib.request, "urlopen", urlopen)

    assert refresh._get_pypi_json(refresh.PYPI_BORGSTORE_API) == {"releases": {}}
    assert sent[0].get_header("Authorization") is None
    assert sent[0].full_url == "https://pypi.org/pypi/borgstore/json"
