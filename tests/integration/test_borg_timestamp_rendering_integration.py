"""The timezone contracts of borg's rendered archive timestamps, measured
against real binaries.

borg 1 renders archive times in the local zone of the listing process with no
UTC offset - the reason parse_borg_archive_time needs to know the render zone.
borg 2 (measured on 2.0.0b22 and 2.0.0b23) renders them WITH an explicit UTC
offset, both in the bare ``repo-list --json`` and in the key-restricted
``--json --format`` fast path the agent uses - those values are
self-describing and take the parser's offset branch regardless of any zone
hint. These tests pin both contracts so a borg release changing either
rendering fails loudly instead of silently shifting ``last_backup``.
"""

import json
import shutil
import subprocess
from datetime import datetime

import pytest

from app.utils.datetime_utils import parse_borg_archive_time
from tests.utils.borg import create_archive, init_borg_repo, make_borg_test_env

# Deliberately a zone without DST: the offset to UTC is +9 all year, so the
# wrong-assumption assertion below is deterministic on any test date.
CREATE_ZONE = "Asia/Tokyo"
CREATE_OFFSET_HOURS = 9


def _listing_time(binary: str, repo_path, env: dict, zone: str, *args) -> str:
    borg2 = binary and shutil.which(binary) and binary.endswith("borg2")
    if borg2:
        cmd = [binary, "--repo", str(repo_path), "repo-list", "--json", *args]
    else:
        cmd = [binary, "list", "--json", *args, str(repo_path)]
    result = subprocess.run(
        cmd,
        env={**env, "TZ": zone},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    archives = json.loads(result.stdout)["archives"]
    assert archives, "expected one archive in the listing"
    return archives[0]["time"]


@pytest.mark.integration
@pytest.mark.requires_borg
def test_borg1_listing_times_are_naive_local_and_need_the_render_zone(tmp_path):
    borg1 = shutil.which("borg")
    if not borg1:
        pytest.skip("borg binary not found")

    env = make_borg_test_env(str(tmp_path))
    env["TZ"] = CREATE_ZONE
    repo_path = tmp_path / "repo"
    source = tmp_path / "src"
    source.mkdir()
    (source / "f.txt").write_text("data\n", encoding="utf-8")
    init_borg_repo(borg1, repo_path, env=env, encryption="none")
    create_archive(borg1, repo_path, "tz-test", [source], env=env)

    utc_str = _listing_time(borg1, repo_path, env, "UTC")
    tokyo_str = _listing_time(borg1, repo_path, env, CREATE_ZONE)

    # borg 1 renders in the listing process's zone, without an offset.
    assert datetime.fromisoformat(utc_str).tzinfo is None
    assert datetime.fromisoformat(tokyo_str).tzinfo is None
    assert utc_str != tokyo_str

    # With the render zone supplied, both listings resolve to the same
    # UTC instant.
    parsed_utc = parse_borg_archive_time(utc_str, timezone_name="UTC")
    parsed_tokyo = parse_borg_archive_time(tokyo_str, timezone_name=CREATE_ZONE)
    assert parsed_utc == parsed_tokyo

    # Assuming UTC for a non-UTC rendering - the pre-fix behavior - shifts
    # the value by the render zone's offset.
    wrongly_assumed_utc = parse_borg_archive_time(tokyo_str, timezone_name="UTC")
    shift = wrongly_assumed_utc - parsed_utc
    assert shift.total_seconds() == CREATE_OFFSET_HOURS * 3600


@pytest.mark.integration
@pytest.mark.requires_borg
def test_borg2_listing_times_carry_their_utc_offset(tmp_path):
    borg2 = shutil.which("borg2")
    if not borg2:
        pytest.skip("borg2 binary not found")

    env = make_borg_test_env(str(tmp_path))
    env["TZ"] = CREATE_ZONE
    repo_path = tmp_path / "repo2"
    source = tmp_path / "src2"
    source.mkdir()
    (source / "f.txt").write_text("data\n", encoding="utf-8")
    try:
        init_borg_repo(borg2, repo_path, env=env, encryption="none")
    except AssertionError:
        # 2.0.0b23 renamed the unencrypted modes with no alias for the plain
        # b22 names; the rendering contract under test is the same either way.
        init_borg_repo(borg2, repo_path, env=env, encryption="none-sha256")
    create_archive(borg2, repo_path, "tz-test", [source], env=env)

    utc_str = _listing_time(borg2, repo_path, env, "UTC")
    tokyo_str = _listing_time(borg2, repo_path, env, CREATE_ZONE)
    # The key-restricted fast path the agent uses for remote-friendly
    # listings must keep the same self-describing rendering.
    fast_path_str = _listing_time(
        borg2, repo_path, env, CREATE_ZONE, "--format", "{name}{id}{time}"
    )

    for value in (utc_str, tokyo_str, fast_path_str):
        assert datetime.fromisoformat(value).tzinfo is not None

    # Self-describing: all renderings resolve to one UTC instant without any
    # zone hint.
    parsed = {
        parse_borg_archive_time(utc_str),
        parse_borg_archive_time(tokyo_str),
        parse_borg_archive_time(fast_path_str),
    }
    assert len(parsed) == 1
