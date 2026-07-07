"""
Unit tests for security functions
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import get_password_hash, verify_password, create_access_token


@pytest.mark.unit
def test_password_hashing():
    """Test password hashing works"""
    password = "testpassword123"
    hashed = get_password_hash(password)

    assert hashed != password
    assert len(hashed) > 0
    assert hashed.startswith("$2b$")  # bcrypt hash format


@pytest.mark.unit
def test_password_verification():
    """Test password verification works correctly"""
    password = "testpassword123"
    hashed = get_password_hash(password)

    # Correct password should verify
    assert verify_password(password, hashed) is True

    # Wrong password should not verify
    assert verify_password("wrongpassword", hashed) is False


@pytest.mark.unit
def test_verify_password_rejects_invalid_or_missing_hash():
    """A missing/non-bcrypt stored hash fails cleanly instead of raising.

    OIDC-only users have no local bcrypt password_hash; bcrypt.checkpw would
    raise ValueError('Invalid salt'), which previously surfaced as a 500 on a
    password login attempt. verify_password must return False for these.
    """
    assert verify_password("anything", "") is False
    assert verify_password("anything", None) is False
    assert verify_password("anything", "not-a-bcrypt-hash") is False

    # A real hash still verifies correctly.
    hashed = get_password_hash("realpassword")
    assert verify_password("realpassword", hashed) is True
    assert verify_password("wrong", hashed) is False


@pytest.mark.unit
def test_different_passwords_different_hashes():
    """Test that different passwords produce different hashes"""
    password1 = "password123"
    password2 = "password456"

    hash1 = get_password_hash(password1)
    hash2 = get_password_hash(password2)

    assert hash1 != hash2


@pytest.mark.unit
def test_same_password_different_hashes():
    """Test that same password produces different hashes (salt)"""
    password = "testpassword123"

    hash1 = get_password_hash(password)
    hash2 = get_password_hash(password)

    # Hashes should be different due to salt
    assert hash1 != hash2

    # But both should verify correctly
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True


@pytest.mark.unit
def test_create_access_token():
    """Test JWT token creation"""
    data = {"sub": "testuser"}
    token = create_access_token(data)

    assert token is not None
    assert len(token) > 0
    assert isinstance(token, str)
    # JWT tokens have 3 parts separated by dots
    assert token.count(".") == 2
