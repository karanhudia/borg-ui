"""
Unit tests for Borg error handling
"""
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.borg_errors import BORG_EXIT_CODES, BORG_MESSAGE_IDS


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
