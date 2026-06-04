import pytest

from app.utils.restore_layout import compute_restore_strip_components


@pytest.mark.unit
def test_contents_only_single_directory_strips_selected_directory_components():
    assert (
        compute_restore_strip_components(
            ["home/username/folder1/folder2"],
            restore_layout="contents_only",
            path_metadata=[
                {"path": "home/username/folder1/folder2", "type": "directory"}
            ],
        )
        == 4
    )


@pytest.mark.unit
def test_contents_only_single_file_keeps_file_name():
    assert (
        compute_restore_strip_components(
            ["/home/username/file.txt"],
            restore_layout="contents_only",
            path_metadata=[{"path": "home/username/file.txt", "type": "file"}],
        )
        == 2
    )


@pytest.mark.unit
def test_contents_only_multiple_files_share_parent():
    assert (
        compute_restore_strip_components(
            ["home/username/a.txt", "home/username/b.txt"],
            restore_layout="contents_only",
            path_metadata=[
                {"path": "home/username/a.txt", "type": "file"},
                {"path": "home/username/b.txt", "type": "file"},
            ],
        )
        == 2
    )


@pytest.mark.unit
def test_contents_only_multiple_directories_preserves_selected_directory_names():
    assert (
        compute_restore_strip_components(
            ["home/username/folder1", "home/username/folder2"],
            restore_layout="contents_only",
            path_metadata=[
                {"path": "home/username/folder1", "type": "directory"},
                {"path": "home/username/folder2", "type": "directory"},
            ],
        )
        == 2
    )


@pytest.mark.unit
def test_preserve_path_does_not_strip_components():
    assert (
        compute_restore_strip_components(
            ["home/username/folder1/folder2"],
            restore_layout="preserve_path",
            path_metadata=[
                {"path": "home/username/folder1/folder2", "type": "directory"}
            ],
        )
        is None
    )


@pytest.mark.unit
def test_contents_only_empty_paths_does_not_strip_components():
    assert compute_restore_strip_components([], restore_layout="contents_only") is None
