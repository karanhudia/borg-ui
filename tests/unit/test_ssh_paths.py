import pytest

from app.utils.ssh_paths import apply_ssh_command_prefix, resolve_sshfs_source_path


@pytest.mark.unit
class TestSshPaths:
    def test_resolve_sshfs_source_path_uses_default_path_for_dot(self):
        assert resolve_sshfs_source_path(".", "/etc/komodo") == "/etc/komodo"
        assert resolve_sshfs_source_path("./", "/etc/komodo") == "/etc/komodo"

    def test_resolve_sshfs_source_path_does_not_apply_ssh_command_prefix(self):
        assert resolve_sshfs_source_path(".", "/share/komodo") == "/share/komodo"
        assert (
            resolve_sshfs_source_path("/share/komodo", "/share/komodo")
            == "/share/komodo"
        )

    def test_apply_ssh_command_prefix_prepends_prefix_once(self):
        assert (
            apply_ssh_command_prefix("/share/komodo", "/volume1")
            == "/volume1/share/komodo"
        )

    def test_apply_ssh_command_prefix_does_not_double_prefix(self):
        assert (
            apply_ssh_command_prefix("/volume1/share/komodo", "/volume1")
            == "/volume1/share/komodo"
        )
