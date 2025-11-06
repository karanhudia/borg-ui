"""
Unit tests for database models
"""
import pytest
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database.models import Repository, User


@pytest.mark.unit
def test_repository_model_creation():
    """Test Repository model instantiation"""
    repo = Repository(
        name="Test Repo",
        path="/tmp/test-repo",
        encryption="repokey",
        compression="lz4",
        repository_type="local"
    )

    assert repo.name == "Test Repo"
    assert repo.path == "/tmp/test-repo"
    assert repo.encryption == "repokey"
    assert repo.compression == "lz4"
    assert repo.repository_type == "local"


@pytest.mark.unit
def test_repository_model_defaults():
    """Test Repository model default values"""
    repo = Repository(
        name="Test Repo",
        path="/tmp/test-repo"
    )

    assert repo.encryption is None or repo.encryption == "none"
    assert repo.compression is None or repo.compression in ["lz4", "zstd", "none"]
    assert repo.source_directories == [] or repo.source_directories is None
    assert repo.exclude_patterns == [] or repo.exclude_patterns is None


@pytest.mark.unit
def test_user_model_creation():
    """Test User model instantiation"""
    user = User(
        username="testuser",
        password_hash="hashed_pwd_123",
        is_active=True
    )

    assert user.username == "testuser"
    assert user.password_hash == "hashed_pwd_123"
    assert user.is_active is True


@pytest.mark.unit
def test_user_model_defaults():
    """Test User model default values"""
    user = User(
        username="testuser",
        password_hash="hashed_pwd_123"
    )

    # Check default is_active
    assert user.is_active is True or user.is_active is None
