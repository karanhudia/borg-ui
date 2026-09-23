from unittest.mock import AsyncMock, Mock, patch

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api import settings as settings_api
from app.database.models import (
    LicensingState,
    Operation,
    Repository,
    SystemSettings,
    User,
)


def _set_plan(test_db, plan: str) -> None:
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-settings-plan")
        test_db.add(state)
    state.plan = plan
    state.status = "active"
    state.is_trial = False
    test_db.commit()


@pytest.mark.unit
class TestSystemSettingsContracts:
    def test_get_effective_timeout_prefers_saved_value_over_env(self):
        value, source = settings_api.get_effective_timeout(600, 120, 300)

        assert value == 600
        assert source == "saved"

    def test_get_effective_timeout_uses_env_when_db_matches_default(self):
        value, source = settings_api.get_effective_timeout(300, 450, 300)

        assert value == 450
        assert source == "env"

    def test_get_effective_timeout_falls_back_to_default(self):
        value, source = settings_api.get_effective_timeout(None, 300, 300)

        assert value == 300
        assert source is None

    def test_get_system_settings_creates_defaults_and_reports_timeout_sources(
        self, test_client: TestClient, admin_headers, test_db, monkeypatch
    ):
        monkeypatch.setenv("TZ", "America/Chicago")
        response = test_client.get("/api/settings/system", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        settings = body["settings"]
        assert settings["max_concurrent_backups"] == 2
        assert settings["max_concurrent_scheduled_backups"] == 2
        assert settings["max_concurrent_scheduled_checks"] == 4
        assert settings["log_retention_days"] == 30
        assert settings["timeout_sources"]["backup_timeout"] in (None, "env")
        assert settings["app_version"] == settings_api.get_runtime_app_version()
        assert settings["backup_monitoring_enabled"] is False
        assert settings["backup_monitoring_stale_after_days"] == 3
        assert settings["backup_monitoring_interval_hours"] == 24
        assert settings["backup_monitoring_alert_cooldown_hours"] == 24
        assert settings["backup_monitoring_include_observe_repos"] is True
        assert settings["backup_monitoring_last_checked_at"] is None
        assert settings["backup_monitoring_last_alert_sent_at"] is None
        assert settings["backup_reports_enabled"] is False
        assert settings["backup_reports_frequency"] == "weekly"
        assert settings["backup_reports_cron_expression"] == "0 8 * * 1"
        assert settings["backup_reports_timezone"] == "America/Chicago"
        assert settings["backup_reports_hour_utc"] == 8
        assert settings["backup_reports_weekday"] == 0
        assert settings["backup_reports_monthday"] == 1
        assert settings["backup_reports_include_summary"] is True
        assert settings["backup_reports_include_stale_repositories"] is True
        assert settings["backup_reports_include_recent_activity"] is True
        assert settings["backup_reports_last_sent_at"] is None
        assert settings["lock_breaking_enabled"] is True
        assert test_db.query(SystemSettings).count() == 1

    def test_get_system_settings_does_not_read_the_log_directory(
        self, test_client: TestClient, admin_headers
    ):
        """The shell requests this route on every page; the log storage
        figures (a stat of every log file) come from /system/logs/storage."""
        # patched on the class, so any binding of the instance (module-level
        # or local) hits it; a call would fail the request, not just the
        # assertion below
        with patch(
            "app.services.log_manager.LogManager.calculate_log_storage",
            side_effect=RuntimeError("boom"),
        ) as calculate:
            response = test_client.get("/api/settings/system", headers=admin_headers)

        assert response.status_code == 200
        payload = response.json()
        assert "log_storage" not in payload
        assert "log_storage" not in payload["settings"]
        calculate.assert_not_called()

    def test_get_system_settings_starts_no_process(
        self, test_client: TestClient, admin_headers
    ):
        """No `borg --version` per call (#1092): the shell requests this route
        on every page, and the sidebar reads the Borg version from
        /api/system/info, which caches it."""
        with patch("subprocess.run", side_effect=RuntimeError("boom")) as run:
            response = test_client.get("/api/settings/system", headers=admin_headers)

        assert response.status_code == 200
        assert "borg_version" not in response.json()["settings"]
        run.assert_not_called()

    def test_update_system_settings_rejects_invalid_log_save_policy(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"log_save_policy": "invalid-policy"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidLogSavePolicy"
        )

    def test_update_system_settings_persists_lock_breaking_enabled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"lock_breaking_enabled": False},
            headers=admin_headers,
        )

        assert response.status_code == 200
        settings = test_db.query(SystemSettings).first()
        assert settings.lock_breaking_enabled is False

        readback = test_client.get("/api/settings/system", headers=admin_headers)
        assert readback.status_code == 200
        assert readback.json()["settings"]["lock_breaking_enabled"] is False

    def test_update_system_settings_persists_auto_prune_preview(
        self, test_client: TestClient, admin_headers, test_db
    ):
        before = test_client.get("/api/settings/system", headers=admin_headers)
        assert before.json()["settings"]["auto_prune_preview"] is True

        response = test_client.put(
            "/api/settings/system",
            json={"auto_prune_preview": False},
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert test_db.query(SystemSettings).first().auto_prune_preview is False
        readback = test_client.get("/api/settings/system", headers=admin_headers)
        assert readback.json()["settings"]["auto_prune_preview"] is False

    def test_update_system_settings_rejects_too_small_log_limit(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"log_max_total_size_mb": 5},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.logSizeTooSmall"
        )

    def test_update_system_settings_rejects_negative_scheduler_limit(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"max_concurrent_scheduled_checks": -1},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidConcurrencyLimit"
        )

    def test_update_system_settings_persists_backup_monitoring_and_reports(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        with (
            patch("app.services.mqtt_service.mqtt_service.configure"),
            patch(
                "app.services.mqtt_service.build_mqtt_runtime_config",
                return_value={"enabled": False},
            ),
        ):
            response = test_client.put(
                "/api/settings/system",
                json={
                    "backup_monitoring_enabled": True,
                    "backup_monitoring_stale_after_days": 5,
                    "backup_monitoring_interval_hours": 6,
                    "backup_monitoring_alert_cooldown_hours": 12,
                    "backup_monitoring_include_observe_repos": False,
                    "backup_reports_enabled": True,
                    "backup_reports_frequency": "daily",
                    "backup_reports_cron_expression": "30 18 * * *",
                    "backup_reports_timezone": "Asia/Kolkata",
                    "backup_reports_hour_utc": 7,
                    "backup_reports_weekday": 2,
                    "backup_reports_monthday": 15,
                    "backup_reports_include_summary": False,
                    "backup_reports_include_stale_repositories": True,
                    "backup_reports_include_recent_activity": False,
                },
                headers=admin_headers,
            )

        assert response.status_code == 200
        settings = test_db.query(SystemSettings).first()
        assert settings.backup_monitoring_enabled is True
        assert settings.backup_monitoring_stale_after_days == 5
        assert settings.backup_monitoring_interval_hours == 6
        assert settings.backup_monitoring_alert_cooldown_hours == 12
        assert settings.backup_monitoring_include_observe_repos is False
        assert settings.backup_reports_enabled is True
        assert settings.backup_reports_frequency == "daily"
        assert settings.backup_reports_cron_expression == "30 18 * * *"
        assert settings.backup_reports_timezone == "Asia/Kolkata"
        assert settings.backup_reports_hour_utc == 7
        assert settings.backup_reports_weekday == 2
        assert settings.backup_reports_monthday == 15
        assert settings.backup_reports_include_summary is False
        assert settings.backup_reports_include_stale_repositories is True
        assert settings.backup_reports_include_recent_activity is False

        readback = test_client.get("/api/settings/system", headers=admin_headers)
        payload = readback.json()["settings"]
        assert payload["backup_monitoring_enabled"] is True
        assert payload["backup_reports_frequency"] == "daily"
        assert payload["backup_reports_cron_expression"] == "30 18 * * *"
        assert payload["backup_reports_timezone"] == "Asia/Kolkata"
        assert payload["backup_reports_include_recent_activity"] is False

    def test_update_system_settings_rejects_community_backup_monitoring_enable(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "community")

        response = test_client.put(
            "/api/settings/system",
            json={"backup_monitoring_enabled": True},
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"] == {
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": "alerting_monitoring",
            "required": "pro",
            "current": "community",
        }

    def test_update_system_settings_rejects_community_backup_reports_enable(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "community")

        response = test_client.put(
            "/api/settings/system",
            json={"backup_reports_enabled": True},
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"] == {
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": "backup_reports",
            "required": "pro",
            "current": "community",
        }

    def test_update_system_settings_rejects_invalid_backup_monitoring_values(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"backup_monitoring_stale_after_days": 0},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidBackupMonitoringSetting"
        )

    def test_update_system_settings_rejects_invalid_report_frequency(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"backup_reports_frequency": "hourly"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidBackupReportFrequency"
        )

    def test_update_system_settings_rejects_invalid_report_cron(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"backup_reports_cron_expression": "not a cron"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.invalidBackupReportSchedule"
        )

    def test_update_system_settings_rejects_invalid_report_timezone(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/system",
            json={"backup_reports_timezone": "Mars/Olympus"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.schedule.invalidTimezone"
        )

    def test_run_backup_monitoring_endpoint_returns_service_result(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        with patch(
            "app.api.settings.backup_monitoring_service.run_backup_monitoring",
            new=AsyncMock(return_value={"stale_count": 2, "alert_sent": True}),
        ) as mock_run:
            response = test_client.post(
                "/api/settings/backup-monitoring/run", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json() == {"stale_count": 2, "alert_sent": True}
        mock_run.assert_awaited_once()

    def test_run_backup_monitoring_endpoint_requires_pro(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "community")

        response = test_client.post(
            "/api/settings/backup-monitoring/run", headers=admin_headers
        )

        assert response.status_code == 403
        assert response.json()["detail"] == {
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": "alerting_monitoring",
            "required": "pro",
            "current": "community",
        }

    def test_send_backup_report_endpoint_returns_service_result(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        with patch(
            "app.api.settings.backup_monitoring_service.send_backup_report_now",
            new=AsyncMock(return_value={"sent": True, "repository_count": 3}),
        ) as mock_send:
            response = test_client.post(
                "/api/settings/backup-reports/send", headers=admin_headers
            )

        assert response.status_code == 200
        assert response.json() == {"sent": True, "repository_count": 3}
        mock_send.assert_awaited_once()

    def test_send_backup_report_endpoint_requires_pro(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "community")

        response = test_client.post(
            "/api/settings/backup-reports/send", headers=admin_headers
        )

        assert response.status_code == 403
        assert response.json()["detail"] == {
            "key": "backend.errors.plan.featureNotAvailable",
            "feature": "backup_reports",
            "required": "pro",
            "current": "community",
        }

    def test_update_system_settings_returns_warning_when_new_log_limit_is_below_current_usage(
        self, test_client: TestClient, admin_headers
    ):
        fake_log_manager = Mock()
        fake_log_manager.calculate_log_storage.return_value = {"total_size_mb": 250}

        with (
            patch("app.services.log_manager.log_manager", fake_log_manager),
            patch("app.api.settings._off_loop", wraps=asyncio.to_thread) as off_loop,
            patch("app.services.mqtt_service.mqtt_service.configure"),
            patch(
                "app.services.mqtt_service.build_mqtt_runtime_config",
                return_value={"enabled": False},
            ),
        ):
            response = test_client.put(
                "/api/settings/system",
                json={"log_max_total_size_mb": 100, "mqtt_password": ""},
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        # the scan went through the off-loop hop
        off_loop.assert_any_call(fake_log_manager.calculate_log_storage)
        assert body["success"] is True
        assert len(body["warnings"]) == 1
        assert "exceeds new limit" in body["warnings"][0]


@pytest.mark.unit
class TestSettingsUserContracts:
    def test_create_user_rejects_duplicate_email(
        self, test_client: TestClient, admin_headers, test_db
    ):
        test_db.add(SystemSettings())
        state = test_db.query(LicensingState).first()
        if state is None:
            state = LicensingState(instance_id="test-instance-settings-users")
            test_db.add(state)
        state.plan = "pro"
        state.status = "active"
        state.is_trial = False
        existing = User(
            username="existing",
            email="taken@example.com",
            role="viewer",
            password_hash="hash",
        )
        test_db.add(existing)
        test_db.commit()

        response = test_client.post(
            "/api/settings/users",
            json={
                "username": "new-user",
                "password": "SecurePass123!",
                "email": "taken@example.com",
                "role": "viewer",
            },
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.emailAlreadyExists"
        )

    def test_update_user_role_normalizes_repository_scope(
        self, test_client: TestClient, admin_headers, test_db
    ):
        user = User(
            username="scoped-user",
            email="scoped@example.com",
            role="viewer",
            all_repositories_role="operator",
            password_hash="hash",
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)

        response = test_client.put(
            f"/api/settings/users/{user.id}",
            json={"role": "viewer"},
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(user)
        assert user.role == "viewer"
        assert user.all_repositories_role == "viewer"

    def test_delete_user_rejects_deleting_self(
        self, test_client: TestClient, admin_headers, admin_user, test_db
    ):
        test_db.add(
            User(
                username="other-admin",
                email="other-admin@example.com",
                role="admin",
                password_hash="hash",
            )
        )
        test_db.commit()

        response = test_client.delete(
            f"/api/settings/users/{admin_user.id}", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.cannotDeleteOwnAccount"
        )

    def test_change_password_rejects_wrong_current_password(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/settings/change-password",
            json={"current_password": "wrong-password", "new_password": "NewPass123!"},
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.auth.currentPasswordIncorrect"
        )

    def test_get_profile_includes_deployment_metadata(
        self, test_client: TestClient, admin_headers, test_db
    ):
        settings = SystemSettings(
            deployment_type="enterprise", enterprise_name="Acme Inc"
        )
        test_db.add(settings)
        test_db.commit()

        response = test_client.get("/api/settings/profile", headers=admin_headers)

        assert response.status_code == 200
        profile = response.json()["profile"]
        assert profile["deployment_type"] == "enterprise"
        assert profile["enterprise_name"] == "Acme Inc"

    def test_get_preferences_returns_user_analytics_flags(
        self, test_client: TestClient, admin_headers, admin_user
    ):
        admin_user.analytics_enabled = False
        admin_user.analytics_consent_given = True

        response = test_client.get("/api/settings/preferences", headers=admin_headers)

        assert response.status_code == 200
        assert response.json() == {
            "success": True,
            "preferences": {
                "analytics_enabled": False,
                "analytics_consent_given": True,
            },
        }

    def test_update_preferences_persists_analytics_flags(
        self, test_client: TestClient, admin_headers, admin_user, test_db
    ):
        response = test_client.put(
            "/api/settings/preferences",
            json={"analytics_enabled": False, "analytics_consent_given": True},
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(admin_user)
        assert admin_user.analytics_enabled is False
        assert admin_user.analytics_consent_given is True
        assert (
            response.json()["message"] == "backend.success.settings.preferencesUpdated"
        )


@pytest.mark.unit
class TestCacheSettingsContracts:
    def test_clear_cache_rejects_missing_repository(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.post(
            "/api/settings/cache/clear?repository_id=99999", headers=admin_headers
        )

        assert response.status_code == 404
        assert (
            response.json()["detail"]["key"] == "backend.errors.repo.repositoryNotFound"
        )

    def test_clear_cache_for_repository_returns_cleared_count(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repository = Repository(
            name="Repo", path="/repos/main", encryption="none", repository_type="local"
        )
        test_db.add(repository)
        test_db.commit()
        test_db.refresh(repository)

        with patch(
            "app.api.settings.archive_cache.clear_repository",
            new=AsyncMock(return_value=3),
        ) as mock_clear:
            response = test_client.post(
                f"/api/settings/cache/clear?repository_id={repository.id}",
                headers=admin_headers,
            )

        assert response.status_code == 200
        assert response.json()["cleared_count"] == 3
        mock_clear.assert_awaited_once_with(repository.id)

    def test_update_cache_settings_requires_at_least_one_value(
        self, test_client: TestClient, admin_headers
    ):
        response = test_client.put(
            "/api/settings/cache/settings", headers=admin_headers
        )

        assert response.status_code == 400
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.settings.atLeastOneSettingRequired"
        )

    def test_update_cache_settings_reconfigures_backend(
        self, test_client: TestClient, admin_headers, test_db
    ):
        with patch(
            "app.api.settings.archive_cache.reconfigure",
            return_value={"success": True, "backend": "in-memory"},
        ) as mock_reconfigure:
            response = test_client.put(
                "/api/settings/cache/settings?cache_ttl_minutes=90&cache_max_size_mb=256&redis_url=disabled",
                headers=admin_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "backend.success.settings.cacheSettingsUpdated"
        assert body["backend"] == "in-memory"
        assert body["cache_ttl_minutes"] == 90
        assert body["cache_max_size_mb"] == 256
        mock_reconfigure.assert_called_once_with(
            redis_url="disabled", cache_max_size_mb=256
        )
        settings = test_db.query(SystemSettings).first()
        assert settings.cache_ttl_minutes == 90
        assert settings.cache_max_size_mb == 256
        assert settings.redis_url == "disabled"

    def test_update_cache_settings_reads_json_body_and_redacts_log(
        self, test_client: TestClient, admin_headers, test_db, caplog
    ):
        url = "redis://:hunter2@cache.internal:6379/0"
        caplog.set_level("INFO")
        with patch(
            "app.api.settings.archive_cache.reconfigure",
            return_value={"success": True, "backend": "redis"},
        ) as mock_reconfigure:
            response = test_client.put(
                "/api/settings/cache/settings",
                json={"cache_max_size_mb": 256, "redis_url": url},
                headers=admin_headers,
            )

        assert response.status_code == 200
        mock_reconfigure.assert_called_once_with(redis_url=url, cache_max_size_mb=256)
        assert test_db.query(SystemSettings).first().redis_url == url
        assert "Cache settings updated" in caplog.text
        assert "hunter2" not in caplog.text

    def test_get_log_storage_stats_reports_usage_percent(
        self, test_client: TestClient, admin_headers, test_db
    ):
        test_db.add(SystemSettings(log_max_total_size_mb=200))
        test_db.commit()

        fake_log_manager = Mock()
        fake_log_manager.calculate_log_storage.return_value = {
            "total_size_bytes": 50 * 1024 * 1024,
            "total_size_mb": 50,
            "file_count": 4,
            "oldest_log_date": None,
            "newest_log_date": None,
            "files_by_type": {"backup": 2, "restore": 2},
        }

        with (
            patch("app.services.log_manager.log_manager", fake_log_manager),
            patch("app.api.settings._off_loop", wraps=asyncio.to_thread) as off_loop,
        ):
            response = test_client.get(
                "/api/settings/system/logs/storage", headers=admin_headers
            )

        assert response.status_code == 200
        # the scan of the log directory went through the off-loop hop
        off_loop.assert_any_call(fake_log_manager.calculate_log_storage)
        log_storage = response.json()["storage"]
        assert log_storage["usage_percent"] == 25
        assert log_storage["file_count"] == 4
        assert log_storage["files_by_type"] == {"backup": 2, "restore": 2}


class TestBackgroundStatsRefresh:
    @pytest.mark.asyncio
    async def test_one_failed_enqueue_does_not_stop_the_rest(self, test_db):
        """`enqueue_chain` commits, so a failure leaves the session unusable
        until it is rolled back. Without that, the next repository's query
        raises and every repository after the first is silently skipped."""
        repos = []
        for name in ("first", "second"):
            repo = Repository(
                name=f"Stats {name}",
                path=f"/repos/stats-{name}",
                encryption="none",
                compression="lz4",
                repository_type="local",
            )
            test_db.add(repo)
            repos.append(repo)
        test_db.commit()
        ids = [repo.id for repo in repos]
        enqueued: list[int] = []

        def enqueue_chain(db, kinds, *, repository_id, trigger):
            if repository_id == ids[0]:
                # A doomed transaction, which is what a failed commit inside
                # `enqueue_chain` leaves behind (`kind` is NOT NULL).
                db.add(Operation(category="maintenance", run_id="doomed"))
                db.flush()
            enqueued.append(repository_id)

        with (
            patch("app.database.database.SessionLocal", return_value=test_db),
            patch(
                "app.services.operations.enqueue.enqueue_chain",
                side_effect=enqueue_chain,
            ),
            patch.object(test_db, "close"),
        ):
            await settings_api._run_stats_refresh_background(ids, "tester")

        assert enqueued == [ids[1]]

    @pytest.mark.asyncio
    async def test_the_refresh_timestamp_is_left_to_the_stats_executor(self, test_db):
        """The frontend reads `last_stats_refresh` as the signal that the
        statistics themselves are new, so enqueueing must not write it."""
        repo = Repository(
            name="Stats timestamp",
            path="/repos/stats-timestamp",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        settings_row = test_db.query(SystemSettings).first()
        if settings_row is None:
            settings_row = SystemSettings()
            test_db.add(settings_row)
        settings_row.last_stats_refresh = None
        test_db.commit()

        with (
            patch("app.database.database.SessionLocal", return_value=test_db),
            patch("app.services.operations.enqueue.enqueue_chain"),
            patch.object(test_db, "close"),
        ):
            await settings_api._run_stats_refresh_background([repo.id], "tester")

        test_db.refresh(settings_row)
        assert settings_row.last_stats_refresh is None
