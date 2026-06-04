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

    assert settings.rclone_config_root == f"{settings.data_dir}/rclone"
    assert settings.rclone_cache_root == f"{settings.data_dir}/rclone-cache"
    assert settings.rclone_sync_timeout == 14400
    assert settings.rclone_hydrate_timeout == 14400
    assert settings.rclone_default_transfers == 4
    assert settings.rclone_default_checkers == 8


@pytest.mark.unit
def test_rclone_settings_derive_roots_from_data_dir(monkeypatch):
    """Test rclone storage roots follow non-default DATA_DIR values."""
    monkeypatch.delenv("RCLONE_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("RCLONE_CACHE_ROOT", raising=False)

    settings = Settings(data_dir="/srv/borg-ui")

    assert settings.rclone_config_root == "/srv/borg-ui/rclone"
    assert settings.rclone_cache_root == "/srv/borg-ui/rclone-cache"


@pytest.mark.unit
def test_rclone_settings_env_roots_override_data_dir(monkeypatch):
    """Test explicit rclone root env vars remain server-owned overrides."""
    monkeypatch.setenv("RCLONE_CONFIG_ROOT", "/custom/rclone-config")
    monkeypatch.setenv("RCLONE_CACHE_ROOT", "/custom/rclone-cache")

    settings = Settings(data_dir="/srv/borg-ui")

    assert settings.rclone_config_root == "/custom/rclone-config"
    assert settings.rclone_cache_root == "/custom/rclone-cache"
