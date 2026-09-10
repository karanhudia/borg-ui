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


@pytest.mark.unit
@pytest.mark.parametrize(
    "configured, expected, warns",
    [
        (None, "admin123", "admin123"),  # not set: the documented default
        ("", "admin123", "admin123"),  # a blank template field: empty string
        ("   ", "admin123", "admin123"),  # whitespace only is no password
        ("admin123", "admin123", "admin123"),  # the default, set explicitly
        ("change-me", "change-me", None),
        (" padded ", "padded", "whitespace"),  # an env file's stray space
        (" admin123 ", "admin123", "whitespace"),  # trimmed to the default, said
    ],
)
@pytest.mark.asyncio
async def test_first_admin_password_falls_back_when_the_variable_is_blank(
    db_session, monkeypatch, configured, expected, warns
):
    """A template with a blank password field sets INITIAL_ADMIN_PASSWORD to
    an empty string; the first admin must then get the documented default,
    never an empty password, and the operator must see the warning that
    says so. A trimmed value is announced too. The forced password change
    stays."""
    from unittest.mock import patch

    from app.core.security import create_first_user
    from app.database.models import User

    if configured is None:
        monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", configured)
    assert db_session.query(User).count() == 0

    # `create_first_user` closes the session it gets; the fixture's StaticPool
    # keeps the in-memory database alive for the assertions below.
    with (
        patch("app.core.security.get_db", side_effect=lambda: iter([db_session])),
        patch("app.core.security.logger") as log,
    ):
        await create_first_user()

    admin = db_session.query(User).filter(User.username == "admin").one()
    assert verify_password(expected, admin.password_hash)
    assert admin.must_change_password is True
    assert admin.role == "admin"
    warnings = " ".join(str(call) for call in log.warning.call_args_list)
    if warns is None:
        assert not log.warning.called
    else:
        assert warns in warnings
