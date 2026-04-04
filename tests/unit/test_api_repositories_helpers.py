import pytest
from unittest.mock import Mock, patch

from app.api.repositories import (
    _borg_keyfile_name,
    _empty_running_jobs_response,
    get_operation_timeouts,
    get_standard_ssh_opts,
)


@pytest.mark.unit
class TestRepositoryHelperFunctions:
    def test_empty_running_jobs_response_has_expected_shape(self):
        assert _empty_running_jobs_response() == {
            "has_running_jobs": False,
            "check_job": None,
            "compact_job": None,
            "prune_job": None,
        }

    def test_borg_keyfile_name_for_local_path(self):
        assert (
            _borg_keyfile_name("/local/Users/test/backups/my-repo")
            == "local_Users_test_backups_my_repo"
        )

    def test_borg_keyfile_name_for_ssh_path(self):
        assert (
            _borg_keyfile_name("ssh://borg@example.com:2222/backups/repo-name")
            == "borg_example_com_2222_backups_repo_name"
        )

    def test_get_standard_ssh_opts_without_key(self):
        opts = get_standard_ssh_opts()

        assert "-i" not in opts
        assert "StrictHostKeyChecking=no" in opts
        assert "UserKnownHostsFile=/dev/null" in opts
        assert "RequestTTY=no" in opts

    def test_get_standard_ssh_opts_with_key(self):
        opts = get_standard_ssh_opts("/tmp/test-key")

        assert opts[:2] == ["-i", "/tmp/test-key"]
        assert "StrictHostKeyChecking=no" in opts

    def test_get_operation_timeouts_uses_database_values(self):
        mock_settings = Mock(
            info_timeout=11,
            list_timeout=22,
            init_timeout=33,
            backup_timeout=44,
        )
        mock_db = Mock()
        mock_db.query.return_value.first.return_value = mock_settings

        timeouts = get_operation_timeouts(mock_db)

        assert timeouts == {
            "info_timeout": 11,
            "list_timeout": 22,
            "init_timeout": 33,
            "backup_timeout": 44,
        }

    def test_get_operation_timeouts_falls_back_to_config_defaults(self):
        mock_db = Mock()
        mock_db.query.side_effect = RuntimeError("database unavailable")

        timeouts = get_operation_timeouts(mock_db)

        assert set(timeouts.keys()) == {
            "info_timeout",
            "list_timeout",
            "init_timeout",
            "backup_timeout",
        }
        assert all(isinstance(value, int) for value in timeouts.values())

    def test_get_operation_timeouts_creates_and_closes_session_when_db_missing(self):
        mock_settings = Mock(
            info_timeout=101,
            list_timeout=202,
            init_timeout=303,
            backup_timeout=404,
        )
        mock_session = Mock()
        mock_session.query.return_value.first.return_value = mock_settings

        with patch("app.api.repositories.SessionLocal", return_value=mock_session):
            timeouts = get_operation_timeouts()

        assert timeouts["info_timeout"] == 101
        assert timeouts["backup_timeout"] == 404
        mock_session.close.assert_called_once()
