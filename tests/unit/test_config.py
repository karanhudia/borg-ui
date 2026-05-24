"""
Unit tests for app configuration
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import Settings


@pytest.mark.unit
def test_settings_default_values():
    """Test that settings have sensible defaults"""
    settings = Settings()

    assert settings.secret_key is not None
    assert len(settings.secret_key) > 0
    assert settings.algorithm == "HS256"
    assert settings.access_token_expire_minutes > 0


@pytest.mark.unit
def test_settings_database_path():
    """Test database path configuration"""
    settings = Settings()

    assert settings.database_url is not None
    assert "sqlite" in settings.database_url or "postgresql" in settings.database_url


@pytest.mark.unit
def test_settings_environment():
    """Test environment configuration"""
    settings = Settings()

    assert settings.environment is not None
    assert settings.app_name == "Borg Web UI"


@pytest.mark.unit
def test_rclone_settings_default_values():
    """Test rclone storage settings have safe production defaults."""
    settings = Settings()

    assert settings.rclone_config_root == "/data/rclone"
    assert settings.rclone_cache_root == "/data/rclone-cache"
    assert settings.rclone_sync_timeout == 14400
    assert settings.rclone_hydrate_timeout == 14400
    assert settings.rclone_default_transfers == 4
    assert settings.rclone_default_checkers == 8
