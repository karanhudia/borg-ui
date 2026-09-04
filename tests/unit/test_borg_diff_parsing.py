import json
from pathlib import Path

import pytest

from app.core.borg_diff import ChangeRecord, parse_diff_line, parse_list_line

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "borg_output"


def _records(name, parser):
    out = {}
    for line in (FIXTURES / name).read_text().splitlines():
        rec = parser(line)
        if rec is not None:
            out[rec.path] = rec
    return out


@pytest.mark.unit
@pytest.mark.parametrize("fixture", ["borg1_diff.jsonl", "borg2_diff.jsonl"])
def test_diff_fixture_maps_every_change_kind(fixture):
    """Real `borg diff --json-lines` output from Borg 1.4.5 and Borg 2.0.0b21
    (see tests/fixtures/borg_output/README.md), asserting the exact shapes
    the two versions produce."""
    recs = _records(fixture, parse_diff_line)

    # A directory's own mtime/ctime move whenever a child is added or
    # removed; borg diff carries no type field, so this is indistinguishable
    # from a metadata-only file change (README, "A real limitation").
    src = recs["src"]
    assert src.change == "modified" and src.size_delta == 0
    assert src.mode_changed is False and src.owner_changed is False
    assert src.is_directory is False

    grow = recs["src/grow.txt"]
    assert grow.change == "modified" and grow.size_delta == 10
    assert grow.size_before is None and grow.size_after is None

    mode = recs["src/mode.sh"]
    assert mode.change == "modified" and mode.mode_changed is True
    assert mode.size_delta == 0

    link_changed = recs["src/link_changed"]
    assert link_changed.change == "modified" and link_changed.size_delta is None
    assert link_changed.mode_changed is False and link_changed.owner_changed is False

    new = recs["src/new.txt"]
    assert new.change == "added" and new.size_after == 4 and new.size_before is None

    link_added = recs["src/link_added"]
    assert link_added.change == "added" and link_added.size_after is None
    assert link_added.is_directory is False

    dir_new = recs["src/dir_new"]
    assert dir_new.change == "added" and dir_new.is_directory is True
    assert dir_new.size_after is None

    inner = recs["src/dir_new/f.txt"]
    assert inner.change == "added" and inner.size_after == 2

    gone = recs["src/gone.txt"]
    assert (
        gone.change == "removed" and gone.size_before == 5 and gone.size_after is None
    )

    link_removed = recs["src/link_removed"]
    assert link_removed.change == "removed" and link_removed.size_before is None

    assert "src/dir_a/inner.txt" not in recs
    assert "src/keep.txt" not in recs


@pytest.mark.unit
@pytest.mark.parametrize("fixture", ["borg1_list.jsonl", "borg2_list.jsonl"])
def test_list_fixture_maps_entries_to_added_records(fixture):
    recs = _records(fixture, parse_list_line)
    keep = recs["src/keep.txt"]
    assert keep == ChangeRecord("src/keep.txt", "added", size_after=5)
    assert recs["src/dir_a"].is_directory is True
    assert recs["src/dir_a"].change == "added"
    assert recs["src/dir_a"].size_after is None
    link = recs["src/link_changed"]
    assert link.change == "added" and link.size_after is None
    assert link.is_directory is False
    inner = recs["src/dir_a/inner.txt"]
    assert inner.change == "added" and inner.size_after == 2


@pytest.mark.unit
def test_parse_diff_line_rejects_junk():
    assert parse_diff_line("") is None
    assert parse_diff_line("not json") is None
    assert parse_diff_line(json.dumps({"changes": []})) is None
    assert parse_diff_line(json.dumps({"path": "p", "changes": []})) is None


@pytest.mark.unit
def test_parse_diff_line_prefers_presence_over_modification():
    line = json.dumps(
        {
            "path": "a",
            "changes": [
                {"type": "mode", "old_mode": "-rw", "new_mode": "-rwx"},
                {"type": "added", "size": 3},
            ],
        }
    )
    rec = parse_diff_line(line)
    assert rec.change == "added" and rec.size_after == 3 and rec.mode_changed is True


@pytest.mark.unit
def test_parse_diff_line_reads_borg2_presence_shape():
    """Borg 2 has no `size` key on added/removed entries; it has `added`
    and `removed` ints (README)."""
    added = parse_diff_line(
        json.dumps(
            {"path": "a", "changes": [{"type": "added", "added": 9, "removed": 0}]}
        )
    )
    assert added.change == "added" and added.size_after == 9
    removed = parse_diff_line(
        json.dumps(
            {"path": "a", "changes": [{"type": "removed", "added": 0, "removed": 9}]}
        )
    )
    assert removed.change == "removed" and removed.size_before == 9


@pytest.mark.unit
def test_parse_diff_line_accepts_both_mode_and_owner_spellings():
    for kind in ("mode", "changed mode"):
        rec = parse_diff_line(json.dumps({"path": "a", "changes": [{"type": kind}]}))
        assert rec.mode_changed is True
    for kind in ("owner", "changed owner"):
        rec = parse_diff_line(json.dumps({"path": "a", "changes": [{"type": kind}]}))
        assert rec.owner_changed is True


@pytest.mark.unit
def test_parse_diff_line_mtime_only_is_modified_with_zero_delta():
    rec = parse_diff_line(json.dumps({"path": "a", "changes": [{"type": "mtime"}]}))
    assert rec.change == "modified" and rec.size_delta == 0


@pytest.mark.unit
def test_borg1_diff_command_shape(monkeypatch):
    from app.core import borg as borg_module

    captured = {}

    class FakeStream:
        def __init__(self, cmd, *, env=None, timeout=3600):
            captured["cmd"] = cmd
            captured["env"] = env

    monkeypatch.setattr(borg_module, "CommandLineStream", FakeStream)
    b = borg_module.BorgInterface.__new__(borg_module.BorgInterface)
    b.borg_cmd = "borg"
    b.diff_archives(
        "/r", "a1", "a2", remote_path="/opt/borg", passphrase="pw", bypass_lock=True
    )
    assert captured["cmd"] == [
        "borg",
        "diff",
        "--remote-path",
        "/opt/borg",
        "--bypass-lock",
        "--json-lines",
        "/r::a1",
        "a2",
    ]
    assert captured["env"]["BORG_PASSPHRASE"] == "pw"
    assert captured["env"]["BORG_LOCK_WAIT"] == "20"
    b.list_archive_lines("/r", "a1")
    assert captured["cmd"] == ["borg", "list", "--json-lines", "/r::a1"]


@pytest.mark.unit
def test_borg2_diff_command_shape(monkeypatch):
    from app.core import borg2 as borg2_module

    captured = {}

    class FakeStream:
        def __init__(self, cmd, *, env=None, timeout=3600):
            captured["cmd"] = cmd
            captured["env"] = env

    monkeypatch.setattr(borg2_module, "CommandLineStream", FakeStream)
    b = borg2_module.Borg2Interface.__new__(borg2_module.Borg2Interface)
    b.borg_cmd = "borg2"
    b.diff_archives("/r", "aid:1", "aid:2", passphrase="pw", remote_path="/opt/borg2")
    assert captured["cmd"] == [
        "borg2",
        "-r",
        "/r",
        "diff",
        "--json-lines",
        "--remote-path",
        "/opt/borg2",
        "aid:1",
        "aid:2",
    ]
    assert captured["env"]["BORG_PASSPHRASE"] == "pw"
    b.list_archive_lines("/r", "aid:1")
    assert captured["cmd"] == ["borg2", "-r", "/r", "list", "--json-lines", "aid:1"]
