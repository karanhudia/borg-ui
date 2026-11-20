from pathlib import Path

import pytest

from app.services import this_machine as tm


@pytest.mark.unit
def test_root_always_reads_everything(tmp_path):
    assert tm.has_read_all(tmp_path, euid=0, marker=tmp_path / "missing") is True


@pytest.mark.unit
def test_marker_means_read_all(tmp_path):
    marker = tmp_path / "read-all"
    marker.touch()
    assert tm.has_read_all(tmp_path, euid=1001, marker=marker) is True


@pytest.mark.unit
def test_no_marker_no_read_all(tmp_path):
    assert tm.has_read_all(tmp_path, euid=1001, marker=tmp_path / "missing") is False


@pytest.mark.unit
def test_no_host_root_no_read_all(tmp_path):
    marker = tmp_path / "read-all"
    marker.touch()
    assert tm.has_read_all(None, euid=1001, marker=marker) is False


@pytest.mark.unit
def test_default_marker_is_env_or_run(monkeypatch):
    monkeypatch.delenv("BORG_UI_READ_ALL_MARKER", raising=False)
    assert tm.read_all_marker() == Path("/run/borg-ui/read-all")
    monkeypatch.setenv("BORG_UI_READ_ALL_MARKER", "/opt/borg-ui/read-all")
    assert tm.read_all_marker() == Path("/opt/borg-ui/read-all")


@pytest.mark.unit
def test_status_reports_read_all_access(test_client, admin_headers, monkeypatch):
    monkeypatch.setattr(tm, "has_read_all", lambda _root: True)
    body = test_client.get("/api/this-machine", headers=admin_headers).json()
    assert body["read_all_access"] is True
