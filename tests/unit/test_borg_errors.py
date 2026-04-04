"""
Unit tests for Borg error handling
"""
import pytest
import json

from app.core.borg_errors import (
    BORG_EXIT_CODES,
    BORG_MESSAGE_IDS,
    format_error_message,
    get_error_details,
    get_exit_code_message,
    is_lock_error,
)


@pytest.mark.unit
def test_borg_exit_codes_exist():
    """Test that exit code mappings are defined"""
    assert BORG_EXIT_CODES is not None
    assert isinstance(BORG_EXIT_CODES, dict)
    assert len(BORG_EXIT_CODES) > 0


@pytest.mark.unit
def test_borg_success_exit_code():
    """Test that success exit code (0) is defined"""
    assert 0 in BORG_EXIT_CODES
    assert "success" in BORG_EXIT_CODES[0].lower()


@pytest.mark.unit
def test_borg_common_error_codes():
    """Test that common error codes are defined"""
    # Repository doesn't exist
    assert 13 in BORG_EXIT_CODES or "DoesNotExist" in str(BORG_MESSAGE_IDS)

    # Repository locked
    assert 15 in BORG_EXIT_CODES or "Locked" in str(BORG_MESSAGE_IDS)


@pytest.mark.unit
def test_borg_message_ids_exist():
    """Test that message ID mappings are defined"""
    assert BORG_MESSAGE_IDS is not None
    assert isinstance(BORG_MESSAGE_IDS, dict)
    assert len(BORG_MESSAGE_IDS) > 0


@pytest.mark.unit
def test_borg_message_structure():
    """Test that message IDs have proper structure"""
    for message_id, data in BORG_MESSAGE_IDS.items():
        assert isinstance(data, dict)
        assert "message" in data
        assert "severity" in data
        assert data["severity"] in ["error", "warning", "info"]


@pytest.mark.unit
def test_repository_error_messages():
    """Test repository-related error messages"""
    repo_errors = [key for key in BORG_MESSAGE_IDS.keys() if "Repository" in key]
    assert len(repo_errors) > 0

    # Check specific common errors
    assert "Repository.DoesNotExist" in BORG_MESSAGE_IDS
    assert "Repository.AlreadyExists" in BORG_MESSAGE_IDS


@pytest.mark.unit
def test_get_error_details_returns_known_mapping():
    details = get_error_details("Repository.DoesNotExist")

    assert details["message"] == "Repository does not exist at the specified path"
    assert details["severity"] == "error"
    assert "initialized with 'borg init'" in details["suggestion"]


@pytest.mark.unit
def test_get_error_details_returns_default_for_unknown_msgid():
    details = get_error_details("Totally.Unknown", default_message="Fallback message")

    assert details == {
        "message": "Fallback message",
        "suggestion": "Check the Borg documentation for more details",
        "severity": "error",
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (0, "Success"),
        (13, "Repository does not exist"),
        (70, "Failed to acquire the lock"),
        (31, "Archive does not exist"),
    ],
)
def test_get_exit_code_message_for_known_codes(exit_code, expected):
    assert get_exit_code_message(exit_code) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exit_code", "expected"),
    [
        (9, "Error (exit code 9)"),
        (42_000, "Unknown error (exit code 42000)"),
        (99, "Unsupported authentication suite"),
        (100, "Warning: File changed during backup"),
        (127, "Warning (exit code 127)"),
    ],
)
def test_get_exit_code_message_for_ranges(exit_code, expected):
    assert get_exit_code_message(exit_code) == expected


@pytest.mark.unit
@pytest.mark.parametrize("exit_code", [70, 71, 72, 73, 74, 75])
def test_is_lock_error_detects_lock_exit_codes(exit_code):
    assert is_lock_error(exit_code=exit_code) is True


@pytest.mark.unit
@pytest.mark.parametrize("msgid", ["LockError", "LockErrorT", "LockFailed", "LockTimeout", "NotLocked", "NotMyLock"])
def test_is_lock_error_detects_lock_message_ids(msgid):
    assert is_lock_error(msgid=msgid) is True


@pytest.mark.unit
def test_is_lock_error_rejects_non_lock_cases():
    assert is_lock_error(exit_code=52) is False
    assert is_lock_error(msgid="Repository.DoesNotExist") is False
    assert is_lock_error() is False


@pytest.mark.unit
def test_format_error_message_prefers_msgid_locale_key():
    payload = json.loads(format_error_message(msgid="Repository.DoesNotExist", exit_code=13))

    assert payload == {"key": "backend.errors.borg.repositoryDoesNotExist"}


@pytest.mark.unit
def test_format_error_message_falls_back_to_exit_code():
    payload = json.loads(format_error_message(exit_code=52))

    assert payload == {
        "key": "backend.errors.borg.exitCodeError",
        "params": {"exitCode": 52},
    }


@pytest.mark.unit
def test_format_error_message_uses_unknown_error_when_no_inputs():
    payload = json.loads(format_error_message())

    assert payload == {"key": "backend.errors.borg.unknownError"}
