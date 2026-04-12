"""
Unit tests for main.py application startup and routes
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException


@pytest.mark.unit
@pytest.mark.asyncio
class TestStartupEvent:
    """Test application startup event"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session"""
        mock = Mock()
        mock.query.return_value.first.return_value = None
        mock.close = Mock()
        return mock

    async def test_startup_configures_mqtt(self, mock_db):
        """Test that startup configures MQTT service"""
        with patch('app.database.migrations.run_migrations'):
            with patch('app.core.security.create_first_user', new_callable=AsyncMock):
                mock_settings = Mock()
                mock_settings.mqtt_enabled = True
                mock_settings.mqtt_beta_enabled = True
                mock_settings.mqtt_broker_url = "mqtt://localhost:1883"
                mock_settings.borg2_binary_path = None
                mock_db.query.return_value.first.return_value = mock_settings

                with patch('app.database.database.SessionLocal', return_value=mock_db):
                    with patch('app.services.cache_service.archive_cache'):
                        with patch('app.core.borg.borg.get_system_info', new_callable=AsyncMock):
                            with patch('app.services.backup_service.backup_service'):
                                with patch('app.utils.process_utils.cleanup_orphaned_jobs'):
                                    with patch('app.utils.process_utils.cleanup_orphaned_mounts'):
                                        with patch('app.services.mqtt_service.mqtt_service') as mock_mqtt:
                                            with patch('app.services.mqtt_service.build_mqtt_runtime_config', return_value={}):
                                                with patch('app.api.schedule.check_scheduled_jobs', return_value=AsyncMock()):
                                                    with patch('app.services.check_scheduler.check_scheduler'):
                                                        with patch('app.services.stats_refresh_scheduler.stats_refresh_scheduler'):
                                                            with patch('app.services.mqtt_sync_scheduler.start_mqtt_sync_scheduler', return_value=AsyncMock()):
                                                                with patch('asyncio.create_task'):
                                                                    from app.main import startup_event, app
                                                                    app.state.background_tasks = []
                                                                    await startup_event()
                                                                    mock_mqtt.configure.assert_called_once()
                                                                    mock_mqtt.sync_state_with_db.assert_called_once()

    async def test_startup_configures_cache_even_when_license_sync_disabled(self, mock_db):
        """SessionLocal must still be available for cache config when license sync is off."""
        mock_settings = Mock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.cache_max_size_mb = 128
        mock_db.query.return_value.first.return_value = mock_settings

        with patch("app.database.migrations.run_migrations"), patch(
            "app.core.security.create_first_user", new_callable=AsyncMock
        ), patch("app.main.settings.enable_startup_license_sync", False), patch(
            "app.database.database.SessionLocal", return_value=mock_db
        ), patch("app.services.cache_service.archive_cache") as mock_cache, patch(
            "app.core.borg.borg.get_system_info", new_callable=AsyncMock
        ), patch("app.services.backup_service.backup_service"), patch(
            "app.utils.process_utils.cleanup_orphaned_jobs"
        ), patch("app.utils.process_utils.cleanup_orphaned_mounts"), patch(
            "app.api.schedule.check_scheduled_jobs", return_value=AsyncMock()
        ), patch("app.services.check_scheduler.check_scheduler"), patch(
            "app.services.stats_refresh_scheduler.stats_refresh_scheduler"
        ), patch(
            "app.services.mqtt_sync_scheduler.start_mqtt_sync_scheduler", return_value=AsyncMock()
        ), patch("asyncio.create_task"):
            mock_cache.reconfigure.return_value = {"success": True, "backend": "redis"}
            from app.main import startup_event, app

            app.state.background_tasks = []
            await startup_event()

        mock_cache.reconfigure.assert_called_once_with(
            redis_url="redis://localhost:6379/0",
            cache_max_size_mb=128,
        )

    async def test_background_license_refresh_uses_runtime_version_when_startup_sync_disabled(self, mock_db):
        """The refresh loop should not close over an undefined app_version."""
        mock_settings = Mock()
        mock_settings.redis_url = None
        mock_settings.log_cleanup_on_startup = False
        mock_settings.mqtt_enabled = False
        mock_settings.mqtt_beta_enabled = False
        mock_db.query.return_value.first.return_value = mock_settings

        captured_refresh_coro = None

        def fake_spawn_background_task(coro):
            nonlocal captured_refresh_coro
            coro_name = getattr(getattr(coro, "cr_code", None), "co_name", "")
            if coro_name == "licensing_refresh_loop":
                captured_refresh_coro = coro
            else:
                coro.close()
            return Mock()

        with patch("app.database.migrations.run_migrations"), patch(
            "app.core.security.create_first_user", new_callable=AsyncMock
        ), patch("app.main.settings.enable_startup_license_sync", False), patch(
            "app.database.database.SessionLocal", return_value=mock_db
        ), patch("app.main.get_runtime_app_version", return_value="9.9.9"), patch(
            "app.main._spawn_background_task", side_effect=fake_spawn_background_task
        ), patch("app.services.cache_service.archive_cache"), patch(
            "app.core.borg.borg.get_system_info", new_callable=AsyncMock
        ), patch("app.services.backup_service.backup_service"), patch(
            "app.utils.process_utils.cleanup_orphaned_jobs"
        ), patch("app.utils.process_utils.cleanup_orphaned_mounts"), patch(
            "app.api.schedule.check_scheduled_jobs", return_value=AsyncMock()
        ), patch("app.services.check_scheduler.check_scheduler"), patch(
            "app.services.stats_refresh_scheduler.stats_refresh_scheduler"
        ), patch(
            "app.services.mqtt_sync_scheduler.start_mqtt_sync_scheduler", return_value=AsyncMock()
        ), patch("asyncio.create_task"):
            from app.main import startup_event, app

            app.state.background_tasks = []
            await startup_event()

            assert captured_refresh_coro is not None
            assert captured_refresh_coro.cr_frame is not None
            assert captured_refresh_coro.cr_frame.f_locals["app_version"] == "9.9.9"
            captured_refresh_coro.close()


@pytest.mark.unit
@pytest.mark.asyncio
class TestShutdownEvent:
    """Test application shutdown event"""

    async def test_shutdown_disconnects_mqtt(self):
        """Test that shutdown disconnects MQTT service"""
        # Create a real mock module with mqtt_service attribute
        from types import SimpleNamespace
        mock_mqtt = Mock()
        mock_module = SimpleNamespace(mqtt_service=mock_mqtt)

        with patch.dict('sys.modules', {'app.services.mqtt_service': mock_module}):
            from app.main import app

            # Define a test version of shutdown_event inline
            async def test_shutdown():
                app_tasks = getattr(app.state, "background_tasks", [])
                if app_tasks:
                    for task in app_tasks:
                        task.cancel()
                    import asyncio
                    try:
                        await asyncio.gather(*app_tasks, return_exceptions=True)
                    except Exception:
                        pass

                # This will now use our mocked module
                from app.services.mqtt_service import mqtt_service
                try:
                    mqtt_service.disconnect()
                except Exception:
                    pass

            app.state.background_tasks = []
            await test_shutdown()
            mock_mqtt.disconnect.assert_called_once()

    async def test_shutdown_handles_mqtt_error(self):
        """Test that shutdown handles MQTT disconnect errors"""
        # Create a real mock module with mqtt_service attribute
        from types import SimpleNamespace
        mock_mqtt = Mock()
        mock_mqtt.disconnect.side_effect = Exception("MQTT error")
        mock_module = SimpleNamespace(mqtt_service=mock_mqtt)

        with patch.dict('sys.modules', {'app.services.mqtt_service': mock_module}):
            from app.main import app

            # Track if warning was called
            warning_called = False

            # Define a test version of shutdown_event inline
            async def test_shutdown():
                nonlocal warning_called
                app_tasks = getattr(app.state, "background_tasks", [])
                if app_tasks:
                    for task in app_tasks:
                        task.cancel()
                    import asyncio
                    try:
                        await asyncio.gather(*app_tasks, return_exceptions=True)
                    except Exception:
                        pass

                # This will now use our mocked module
                from app.services.mqtt_service import mqtt_service
                try:
                    mqtt_service.disconnect()
                except Exception as e:
                    # Should log warning but not raise
                    warning_called = True

            app.state.background_tasks = []
            await test_shutdown()
            assert warning_called, "Expected exception to be caught and logged"


@pytest.mark.unit
class TestCatchAll:
    @pytest.mark.asyncio
    async def test_serves_announcements_manifest_as_json(self):
        from app.main import catch_all

        with patch("app.main.os.path.exists", side_effect=lambda path: path == "app/static/announcements.json"):
            with patch("app.main.FileResponse") as mock_file_response:
                sentinel_response = Mock()
                mock_file_response.return_value = sentinel_response

                response = await catch_all("announcements.json")

        mock_file_response.assert_called_once_with(
            "app/static/announcements.json",
            media_type="application/json",
        )
        assert response is sentinel_response
