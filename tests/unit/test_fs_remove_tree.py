import os
from unittest.mock import patch

import pytest

from app.utils import fs
from app.utils.fs import active_mount_points, remove_tree_without_crossing_mounts


@pytest.mark.unit
class TestRemoveTreeWithoutCrossingMounts:
    def _tree(self, tmp_path):
        root = tmp_path / "root"
        (root / "a" / "b").mkdir(parents=True)
        (root / "a" / "b" / "f").write_text("x")
        (root / "top").write_text("x")
        return root

    def test_removes_plain_tree(self, tmp_path):
        root = self._tree(tmp_path)
        with patch("app.utils.fs.active_mount_points", return_value=set()):
            assert remove_tree_without_crossing_mounts(str(root)) is True
        assert not root.exists()

    def test_missing_path_counts_as_removed(self, tmp_path):
        assert remove_tree_without_crossing_mounts(str(tmp_path / "nope")) is True

    def test_refuses_when_something_is_mounted_inside(self, tmp_path):
        root = self._tree(tmp_path)
        with patch("app.utils.fs.active_mount_points", return_value={str(root / "a")}):
            assert remove_tree_without_crossing_mounts(str(root)) is False
        assert (root / "a" / "b" / "f").exists() and (root / "top").exists()

    def test_refuses_when_mount_table_is_unreadable(self, tmp_path):
        root = self._tree(tmp_path)
        with patch("app.utils.fs.active_mount_points", return_value=None):
            assert remove_tree_without_crossing_mounts(str(root)) is False
        assert (root / "top").exists()

    def test_mount_elsewhere_does_not_block(self, tmp_path):
        root = self._tree(tmp_path)
        with patch(
            "app.utils.fs.active_mount_points",
            return_value={"/", str(tmp_path / "rootsibling")},
        ):
            assert remove_tree_without_crossing_mounts(str(root)) is True

    def test_walk_never_descends_into_another_device(self, tmp_path):
        # Stand-in for a mount the table missed: pretend the tree's device
        # differs, so every subdirectory looks like another filesystem.
        root = self._tree(tmp_path)
        other_device = os.lstat(root).st_dev + 1
        assert fs._remove_same_device_tree(str(root), other_device) is False
        assert (root / "a" / "b" / "f").exists()
        assert not (root / "top").exists()

    def test_active_mount_points_includes_root(self):
        points = active_mount_points()
        assert points is not None and "/" in points
