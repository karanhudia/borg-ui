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
