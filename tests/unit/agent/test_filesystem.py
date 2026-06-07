from pathlib import Path

import pytest

from agent.borg_ui_agent.filesystem import (
    FilesystemBrowseError,
    browse_filesystem,
    execute_filesystem_browse_job,
)


def test_browse_filesystem_lists_visible_items(tmp_path: Path):
    (tmp_path / "dir").mkdir()
    (tmp_path / "file.txt").write_text("hello")
    (tmp_path / ".hidden").write_text("hidden")

    result = browse_filesystem(str(tmp_path))

    assert result["success"] is True
    assert result["current_path"] == str(tmp_path.resolve())
    assert [item["name"] for item in result["items"]] == ["dir", "file.txt"]
    assert result["items"][0]["type"] == "directory"


def test_browse_filesystem_can_include_hidden_items(tmp_path: Path):
    (tmp_path / ".hidden").write_text("hidden")

    result = browse_filesystem(str(tmp_path), include_hidden=True)

    assert [item["name"] for item in result["items"]] == [".hidden"]
    assert result["items"][0]["hidden"] is True


@pytest.mark.parametrize(
    "path_factory,code",
    [
        (lambda tmp_path: tmp_path / "missing", "missing"),
        (lambda tmp_path: tmp_path / "file.txt", "not_directory"),
    ],
)
def test_browse_filesystem_structured_failures(tmp_path: Path, path_factory, code):
    path = path_factory(tmp_path)
    if code == "not_directory":
        path.write_text("hello")

    with pytest.raises(FilesystemBrowseError) as exc:
        browse_filesystem(str(path))

    assert exc.value.to_result()["error"]["code"] == code


class BrowseClient:
    def __init__(self):
        self.calls = []

    def complete_job(self, job_id, *, result):
        self.calls.append(("complete_job", job_id, result))

    def fail_job(self, job_id, *, error_message, return_code=None):
        self.calls.append(("fail_job", job_id, error_message, return_code))


def test_execute_filesystem_browse_job_completes(tmp_path: Path):
    (tmp_path / "data").mkdir()
    client = BrowseClient()

    result = execute_filesystem_browse_job(
        {
            "id": 12,
            "payload": {
                "job_kind": "filesystem.browse",
                "filesystem": {"path": str(tmp_path), "include_hidden": False},
            },
        },
        client,
    )

    assert result.status == "completed"
    assert client.calls[0][0] == "complete_job"
    assert client.calls[0][2]["items"][0]["name"] == "data"


def test_execute_filesystem_browse_job_fails_with_clear_error(tmp_path: Path):
    client = BrowseClient()

    result = execute_filesystem_browse_job(
        {
            "id": 13,
            "payload": {
                "job_kind": "filesystem.browse",
                "filesystem": {"path": str(tmp_path / "missing")},
            },
        },
        client,
    )

    assert result.status == "failed"
    assert client.calls[0][0] == "fail_job"
    assert "Path not found" in client.calls[0][2]
