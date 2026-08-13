"""bcrypt hashes at most 72 bytes and (since bcrypt 5) raises on longer input.

Password fields that are hashed with ``get_password_hash`` must reject over-limit
input at the request boundary, so registration / password change / reset return a
clean 422 instead of a 500. These tests pin that on the shared validator and on
every model that carries a hashed password field.
"""

import pytest
from pydantic import ValidationError

from app.api import auth as auth_api
from app.api import settings as settings_api
from app.core.security import (
    BCRYPT_MAX_PASSWORD_BYTES,
    enforce_bcrypt_password_length,
)

AT_LIMIT = "a" * BCRYPT_MAX_PASSWORD_BYTES  # 72 ASCII bytes
OVER_LIMIT = "a" * (BCRYPT_MAX_PASSWORD_BYTES + 1)  # 73 bytes
MULTIBYTE_AT_LIMIT = "é" * (BCRYPT_MAX_PASSWORD_BYTES // 2)  # 36 chars = 72 bytes
MULTIBYTE_OVER_LIMIT = "é" * (BCRYPT_MAX_PASSWORD_BYTES // 2 + 1)  # 37 chars = 74 bytes


def test_validator_accepts_at_limit():
    assert enforce_bcrypt_password_length(AT_LIMIT) == AT_LIMIT
    assert enforce_bcrypt_password_length(MULTIBYTE_AT_LIMIT) == MULTIBYTE_AT_LIMIT


def test_validator_rejects_over_limit():
    with pytest.raises(ValueError):
        enforce_bcrypt_password_length(OVER_LIMIT)


def test_validator_counts_bytes_not_characters():
    # 37 two-byte characters are only 37 characters but 74 bytes.
    with pytest.raises(ValueError):
        enforce_bcrypt_password_length(MULTIBYTE_OVER_LIMIT)


# (model, kwargs-builder) for every model carrying a hashed password field.
_MODELS = [
    (auth_api.UserCreate, lambda pw: {"username": "u", "password": pw}),
    (auth_api.PasswordChange, lambda pw: {"current_password": "x", "new_password": pw}),
    (settings_api.UserCreate, lambda pw: {"username": "u", "password": pw}),
    (
        settings_api.PasswordChange,
        lambda pw: {"current_password": "x", "new_password": pw},
    ),
    (settings_api.PasswordReset, lambda pw: {"new_password": pw}),
]


@pytest.mark.parametrize("model, build", _MODELS)
def test_models_accept_at_limit(model, build):
    model(**build(AT_LIMIT))
    model(**build(MULTIBYTE_AT_LIMIT))


@pytest.mark.parametrize("model, build", _MODELS)
def test_models_reject_over_limit(model, build):
    with pytest.raises(ValidationError):
        model(**build(OVER_LIMIT))
    with pytest.raises(ValidationError):
        model(**build(MULTIBYTE_OVER_LIMIT))
