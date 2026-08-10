"""
Unit tests for app configuration
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.engine import make_url

from app.config import Settings, resolve_database_url


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


@pytest.mark.unit
class TestResolveDatabaseUrl:
    """Which database the application runs on, and how that is decided."""

    def test_no_configuration_keeps_the_sqlite_file(self):
        assert resolve_database_url({}, "/data") == "sqlite:////data/borg.db"

    def test_database_url_wins_over_everything(self):
        env = {
            "DATABASE_URL": "postgresql+psycopg://u:p@elsewhere/db",
            "DB_HOST": "ignored",
            "DB_USER": "ignored",
            "DB_PASSWORD": "ignored",
        }
        assert (
            resolve_database_url(env, "/data")
            == "postgresql+psycopg://u:p@elsewhere/db"
        )

    def test_db_host_assembles_a_postgres_url(self):
        env = {
            "DB_HOST": "db.example",
            "DB_USER": "borg_writer_user",
            "DB_PASSWORD": "secret",
            "DB_PORT": "6432",
            "DB_NAME": "borgdb",
        }
        assert resolve_database_url(env, "/data") == (
            "postgresql+psycopg://borg_writer_user:secret@db.example:6432/borgdb"
        )

    def test_port_and_name_have_defaults(self):
        env = {"DB_HOST": "db.example", "DB_USER": "u", "DB_PASSWORD": "p"}
        assert resolve_database_url(env, "/data") == (
            "postgresql+psycopg://u:p@db.example:5432/borg"
        )

    def test_a_password_with_url_characters_survives(self):
        """Generated passwords contain these. Unquoted, "/" ends the host and
        "@" starts a new one, and the failure looks like a wrong host."""
        env = {
            "DB_HOST": "db.example",
            "DB_USER": "user@corp",
            "DB_PASSWORD": "p@ss/w:rd%21+x",
        }

        url = resolve_database_url(env, "/data")

        assert url == (
            "postgresql+psycopg://user%40corp:p%40ss%2Fw%3Ard%2521%2Bx@db.example:5432/borg"
        )
        # The real check: it still parses back to the credentials we put in.
        parsed = make_url(url)
        assert parsed.host == "db.example"
        assert parsed.username == "user@corp"
        assert parsed.password == "p@ss/w:rd%21+x"
        assert parsed.database == "borg"

    @pytest.mark.parametrize(
        "env,missing",
        [
            ({"DB_HOST": "db.example", "DB_PASSWORD": "p"}, "DB_USER"),
            ({"DB_HOST": "db.example", "DB_USER": "u"}, "DB_PASSWORD"),
            ({"DB_HOST": "db.example"}, "DB_USER and DB_PASSWORD"),
        ],
    )
    def test_incomplete_credentials_fail_loudly_instead_of_using_sqlite(
        self, env, missing
    ):
        """A missing secret must not silently start the app on a local file
        while the real database sits unused."""
        with pytest.raises(RuntimeError, match=missing):
            resolve_database_url(env, "/data")
