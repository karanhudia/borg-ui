"""Shared helpers for unit API tests."""

from __future__ import annotations


def assert_auth_required(response, *, expected_status: int = 401) -> None:
    """Assert that an API response requires authentication."""
    assert response.status_code == expected_status
