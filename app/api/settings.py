from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import secrets
import structlog

from app.database.database import get_db
from app.database.models import User, Repository, SystemSettings
from app.core.authorization import authorize_request
from app.core.security import (
    encrypt_secret,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.core.features import get_current_plan, USER_LIMITS
from app.core.permissions import (
    GLOBAL_ROLE_RANK,
    REPOSITORY_ROLE_RANK,
    default_repository_role_for_global_role,
    normalize_repository_role_for_global_role,
)
from app.core.borg import BorgInterface
from app.config import get_runtime_app_version, settings as app_settings
from app.services.cache_service import archive_cache
from app.utils.datetime_utils import serialize_datetime

logger = structlog.get_logger()
router = APIRouter(tags=["settings"], dependencies=[Depends(authorize_request)])

# Initialize Borg interface
borg = BorgInterface()

# Default timeout values (built-in)
DEFAULT_TIMEOUTS = {
    "mount_timeout": 120,
    "info_timeout": 600,
    "list_timeout": 600,
    "init_timeout": 300,
    "backup_timeout": 3600,
    "source_size_timeout": 3600,
}


def get_effective_timeout(db_value, env_value, default_value):
    """
    Get the effective timeout value and its source.
    Priority: DB (if different from default) > Env > Default

    Returns: (value, source) where source is:
    - "saved" if using DB value that differs from default
    - "env" if using env var that differs from default
    - None if value equals default
    """
    # If DB value equals default, treat as not set (allow env to override)
    if db_value == default_value:
        db_value = None

    # Determine effective value and source
    if db_value is not None:
        # DB has a non-default value
        return (db_value, "saved")
    elif env_value != default_value:
        # Env var differs from default
        return (env_value, "env")
    else:
        # Use default
        return (default_value, None)


# Pydantic models for request/response
from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "viewer"
    full_name: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class PasswordReset(BaseModel):
    new_password: str


class UserPreferencesUpdate(BaseModel):
    analytics_enabled: Optional[bool] = None
    analytics_consent_given: Optional[bool] = None


class SystemSettingsUpdate(BaseModel):
    # Operation timeouts (in seconds)
    backup_timeout: Optional[int] = None
    mount_timeout: Optional[int] = None
    info_timeout: Optional[int] = None
    list_timeout: Optional[int] = None
    init_timeout: Optional[int] = None
    source_size_timeout: Optional[int] = None

    max_concurrent_backups: Optional[int] = None
    max_concurrent_scheduled_backups: Optional[int] = None
    max_concurrent_scheduled_checks: Optional[int] = None
    log_retention_days: Optional[int] = None
    log_save_policy: Optional[str] = None
    log_max_total_size_mb: Optional[int] = None
    log_cleanup_on_startup: Optional[bool] = None
    email_notifications: Optional[bool] = None
    webhook_url: Optional[str] = None
    auto_cleanup: Optional[bool] = None
    cleanup_retention_days: Optional[int] = None
    use_new_wizard: Optional[bool] = None
    bypass_lock_on_info: Optional[bool] = (
        None  # Use --bypass-lock for all borg info commands (beta)
    )
    bypass_lock_on_list: Optional[bool] = (
        None  # Use --bypass-lock for all borg list commands (beta)
    )
    show_restore_tab: Optional[bool] = (
        None  # Show legacy Restore tab in navigation (beta)
    )
    borg2_fast_browse_beta_enabled: Optional[bool] = None
    stats_refresh_interval_minutes: Optional[int] = (
        None  # How often to refresh repository stats (0 = disabled)
    )

    # MQTT settings
    mqtt_enabled: Optional[bool] = None
    mqtt_broker_url: Optional[str] = None
    mqtt_broker_port: Optional[int] = None
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_client_id: Optional[str] = None
    mqtt_qos: Optional[int] = None
    mqtt_retain: Optional[bool] = None
    mqtt_tls_enabled: Optional[bool] = None
    mqtt_tls_ca_cert: Optional[str] = None
    mqtt_tls_client_cert: Optional[str] = None
    mqtt_tls_client_key: Optional[str] = None
    mqtt_beta_enabled: Optional[bool] = None

    # Metrics settings
    metrics_enabled: Optional[bool] = None
    metrics_require_auth: Optional[bool] = None
    metrics_token: Optional[str] = None
    rotate_metrics_token: Optional[bool] = None

    # Deployment profile
    deployment_type: Optional[str] = None
    enterprise_name: Optional[str] = None

    # Built-in OIDC / SSO settings
    oidc_enabled: Optional[bool] = None
    oidc_disable_local_auth: Optional[bool] = None
    oidc_provider_name: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    clear_oidc_client_secret: Optional[bool] = None
    oidc_scopes: Optional[str] = None
    oidc_redirect_uri_override: Optional[str] = None
    oidc_end_session_endpoint_override: Optional[str] = None
    oidc_claim_username: Optional[str] = None
    oidc_claim_email: Optional[str] = None
    oidc_claim_full_name: Optional[str] = None
    oidc_group_claim: Optional[str] = None
    oidc_role_claim: Optional[str] = None
    oidc_admin_groups: Optional[str] = None
    oidc_all_repositories_role_claim: Optional[str] = None
    oidc_new_user_mode: Optional[str] = None
    oidc_new_user_template_username: Optional[str] = None
    oidc_default_role: Optional[str] = None
    oidc_default_all_repositories_role: Optional[str] = None


@router.get("/system")
async def get_system_settings(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get system settings"""
    try:
        # Get settings from database or use defaults
        settings = db.query(SystemSettings).first()
        if not settings:
            # Create default settings - but NOT timeout values
            # Timeout values stay NULL so env vars can be used as fallback
            settings = SystemSettings(
                max_concurrent_backups=2,
                max_concurrent_scheduled_backups=2,
                max_concurrent_scheduled_checks=4,
                log_retention_days=30,
                email_notifications=False,
                webhook_url="",
                auto_cleanup=True,
                cleanup_retention_days=90,
                use_new_wizard=False,  # Beta features disabled by default
                show_restore_tab=False,  # Legacy Restore tab hidden by default
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)

        # Get log storage statistics
        from app.services.log_manager import log_manager

        try:
            log_storage = log_manager.calculate_log_storage()
            usage_percent = 0
            if settings.log_max_total_size_mb and settings.log_max_total_size_mb > 0:
                usage_percent = min(
                    100,
                    int(
                        (log_storage["total_size_mb"] / settings.log_max_total_size_mb)
                        * 100
                    ),
                )

            log_storage_info = {
                "total_size_mb": log_storage["total_size_mb"],
                "file_count": log_storage["file_count"],
                "oldest_log_date": log_storage["oldest_log_date"].isoformat()
                if log_storage["oldest_log_date"]
                else None,
                "newest_log_date": log_storage["newest_log_date"].isoformat()
                if log_storage["newest_log_date"]
                else None,
                "usage_percent": usage_percent,
                "files_by_type": log_storage["files_by_type"],
            }
        except Exception as e:
            logger.warning("Failed to calculate log storage", error=str(e))
            log_storage_info = {
                "total_size_mb": 0,
                "file_count": 0,
                "oldest_log_date": None,
                "newest_log_date": None,
                "usage_percent": 0,
                "files_by_type": {},
            }

        # Calculate effective timeout values and their sources
        mount_timeout, mount_source = get_effective_timeout(
            settings.mount_timeout,
            app_settings.borg_mount_timeout,
            DEFAULT_TIMEOUTS["mount_timeout"],
        )
        info_timeout, info_source = get_effective_timeout(
            settings.info_timeout,
            app_settings.borg_info_timeout,
            DEFAULT_TIMEOUTS["info_timeout"],
        )
        list_timeout, list_source = get_effective_timeout(
            settings.list_timeout,
            app_settings.borg_list_timeout,
            DEFAULT_TIMEOUTS["list_timeout"],
        )
        init_timeout, init_source = get_effective_timeout(
            settings.init_timeout,
            app_settings.borg_init_timeout,
            DEFAULT_TIMEOUTS["init_timeout"],
        )
        backup_timeout, backup_source = get_effective_timeout(
            settings.backup_timeout,
            app_settings.backup_timeout,
            DEFAULT_TIMEOUTS["backup_timeout"],
        )
        source_size_timeout, source_size_source = get_effective_timeout(
            settings.source_size_timeout,
            app_settings.source_size_timeout,
            DEFAULT_TIMEOUTS["source_size_timeout"],
        )

        return {
            "success": True,
            "settings": {
                # Operation timeouts (effective values)
                "backup_timeout": backup_timeout,
                "mount_timeout": mount_timeout,
                "info_timeout": info_timeout,
                "list_timeout": list_timeout,
                "init_timeout": init_timeout,
                "source_size_timeout": source_size_timeout,
                # Timeout sources: "saved" (from DB), "env" (from env var), or null (default)
                "timeout_sources": {
                    "backup_timeout": backup_source,
                    "mount_timeout": mount_source,
                    "info_timeout": info_source,
                    "list_timeout": list_source,
                    "init_timeout": init_source,
                    "source_size_timeout": source_size_source,
                },
                # Other settings
                "max_concurrent_backups": settings.max_concurrent_backups,
                "max_concurrent_scheduled_backups": settings.max_concurrent_scheduled_backups
                if settings.max_concurrent_scheduled_backups is not None
                else 2,
                "max_concurrent_scheduled_checks": settings.max_concurrent_scheduled_checks
                if settings.max_concurrent_scheduled_checks is not None
                else 4,
                "log_retention_days": settings.log_retention_days,
                "log_save_policy": settings.log_save_policy,
                "log_max_total_size_mb": settings.log_max_total_size_mb,
                "log_cleanup_on_startup": settings.log_cleanup_on_startup,
                "email_notifications": settings.email_notifications,
                "webhook_url": settings.webhook_url,
                "auto_cleanup": settings.auto_cleanup,
                "cleanup_retention_days": settings.cleanup_retention_days,
                "use_new_wizard": settings.use_new_wizard,
                "bypass_lock_on_info": settings.bypass_lock_on_info,
                "bypass_lock_on_list": settings.bypass_lock_on_list,
                "show_restore_tab": settings.show_restore_tab,
                "borg2_fast_browse_beta_enabled": settings.borg2_fast_browse_beta_enabled,
                "stats_refresh_interval_minutes": settings.stats_refresh_interval_minutes
                if settings.stats_refresh_interval_minutes is not None
                else 60,
                "last_stats_refresh": serialize_datetime(settings.last_stats_refresh),
                "borg_version": borg.get_version(),
                "app_version": get_runtime_app_version(),
                # MQTT settings
                "mqtt_enabled": settings.mqtt_enabled,
                "mqtt_broker_url": settings.mqtt_broker_url,
                "mqtt_broker_port": settings.mqtt_broker_port,
                "mqtt_username": settings.mqtt_username,
                "mqtt_client_id": settings.mqtt_client_id,
                "mqtt_qos": settings.mqtt_qos,
                "mqtt_retain": settings.mqtt_retain,
                "mqtt_tls_enabled": settings.mqtt_tls_enabled,
                "mqtt_tls_ca_cert": settings.mqtt_tls_ca_cert,
                "mqtt_tls_client_cert": settings.mqtt_tls_client_cert,
                "mqtt_tls_client_key": settings.mqtt_tls_client_key,
                "mqtt_beta_enabled": settings.mqtt_beta_enabled,
                "mqtt_password_set": bool(
                    settings.mqtt_password
                ),  # Indicate if password is set (without exposing it)
                "metrics_enabled": settings.metrics_enabled
                if settings.metrics_enabled is not None
                else False,
                "metrics_require_auth": settings.metrics_require_auth
                if settings.metrics_require_auth is not None
                else False,
                "metrics_token_set": bool(settings.metrics_token),
                "oidc_enabled": settings.oidc_enabled,
                "oidc_disable_local_auth": settings.oidc_disable_local_auth,
                "oidc_provider_name": settings.oidc_provider_name or "Single sign-on",
                "oidc_discovery_url": settings.oidc_discovery_url,
                "oidc_client_id": settings.oidc_client_id,
                "oidc_client_secret_set": bool(settings.oidc_client_secret_encrypted),
                "oidc_scopes": settings.oidc_scopes or "openid profile email",
                "oidc_redirect_uri_override": settings.oidc_redirect_uri_override,
                "oidc_end_session_endpoint_override": settings.oidc_end_session_endpoint_override,
                "oidc_claim_username": settings.oidc_claim_username
                or "preferred_username",
                "oidc_claim_email": settings.oidc_claim_email or "email",
                "oidc_claim_full_name": settings.oidc_claim_full_name or "name",
                "oidc_group_claim": settings.oidc_group_claim,
                "oidc_role_claim": settings.oidc_role_claim,
                "oidc_admin_groups": settings.oidc_admin_groups,
                "oidc_all_repositories_role_claim": settings.oidc_all_repositories_role_claim,
                "oidc_new_user_mode": settings.oidc_new_user_mode or "viewer",
                "oidc_new_user_template_username": settings.oidc_new_user_template_username,
                "oidc_default_role": settings.oidc_default_role or "viewer",
                "oidc_default_all_repositories_role": settings.oidc_default_all_repositories_role
                or "viewer",
            },
            "log_storage": log_storage_info,
        }
    except Exception as e:
        logger.error("Failed to get system settings", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedRetrieveSystemSettings",
                "params": {"error": str(e)},
            },
        )


@router.put("/system")
async def update_system_settings(
    settings_update: SystemSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update system settings (admin only)"""
    try:
        # Validate log management settings
        warnings = []

        if settings_update.log_save_policy is not None:
            valid_policies = ["failed_only", "failed_and_warnings", "all_jobs"]
            if settings_update.log_save_policy not in valid_policies:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.settings.invalidLogSavePolicy",
                        "params": {"policies": ", ".join(valid_policies)},
                    },
                )

        if settings_update.log_max_total_size_mb is not None:
            if settings_update.log_max_total_size_mb < 10:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.settings.logSizeTooSmall"},
                )

            # Check if new limit is below current usage
            from app.services.log_manager import log_manager

            try:
                log_storage = log_manager.calculate_log_storage()
                if log_storage["total_size_mb"] > settings_update.log_max_total_size_mb:
                    warnings.append(
                        f"Warning: Current log storage ({log_storage['total_size_mb']} MB) exceeds new limit "
                        f"({settings_update.log_max_total_size_mb} MB). Consider running log cleanup."
                    )
            except Exception as e:
                logger.warning(
                    "Failed to check log storage for validation", error=str(e)
                )

        concurrency_fields = {
            "max_concurrent_backups": settings_update.max_concurrent_backups,
            "max_concurrent_scheduled_backups": settings_update.max_concurrent_scheduled_backups,
            "max_concurrent_scheduled_checks": settings_update.max_concurrent_scheduled_checks,
        }
        for field_name, value in concurrency_fields.items():
            if value is not None and value < 0:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "key": "backend.errors.settings.invalidConcurrencyLimit",
                        "params": {"field": field_name},
                    },
                )

        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)

        # Update settings
        # Operation timeouts - save NULL if value equals default OR env value (so env/default can be used)
        # This ensures "from env" shows correctly when value matches env var
        if settings_update.mount_timeout is not None:
            if settings_update.mount_timeout in (
                DEFAULT_TIMEOUTS["mount_timeout"],
                app_settings.borg_mount_timeout,
            ):
                settings.mount_timeout = None
            else:
                settings.mount_timeout = settings_update.mount_timeout
        if settings_update.info_timeout is not None:
            if settings_update.info_timeout in (
                DEFAULT_TIMEOUTS["info_timeout"],
                app_settings.borg_info_timeout,
            ):
                settings.info_timeout = None
            else:
                settings.info_timeout = settings_update.info_timeout
        if settings_update.list_timeout is not None:
            if settings_update.list_timeout in (
                DEFAULT_TIMEOUTS["list_timeout"],
                app_settings.borg_list_timeout,
            ):
                settings.list_timeout = None
            else:
                settings.list_timeout = settings_update.list_timeout
        if settings_update.init_timeout is not None:
            if settings_update.init_timeout in (
                DEFAULT_TIMEOUTS["init_timeout"],
                app_settings.borg_init_timeout,
            ):
                settings.init_timeout = None
            else:
                settings.init_timeout = settings_update.init_timeout
        if settings_update.backup_timeout is not None:
            if settings_update.backup_timeout in (
                DEFAULT_TIMEOUTS["backup_timeout"],
                app_settings.backup_timeout,
            ):
                settings.backup_timeout = None
            else:
                settings.backup_timeout = settings_update.backup_timeout
        if settings_update.source_size_timeout is not None:
            if settings_update.source_size_timeout in (
                DEFAULT_TIMEOUTS["source_size_timeout"],
                app_settings.source_size_timeout,
            ):
                settings.source_size_timeout = None
            else:
                settings.source_size_timeout = settings_update.source_size_timeout
        # Other settings
        if settings_update.max_concurrent_backups is not None:
            settings.max_concurrent_backups = settings_update.max_concurrent_backups
        if settings_update.max_concurrent_scheduled_backups is not None:
            settings.max_concurrent_scheduled_backups = (
                settings_update.max_concurrent_scheduled_backups
            )
        if settings_update.max_concurrent_scheduled_checks is not None:
            settings.max_concurrent_scheduled_checks = (
                settings_update.max_concurrent_scheduled_checks
            )
        if settings_update.log_retention_days is not None:
            settings.log_retention_days = settings_update.log_retention_days
        if settings_update.log_save_policy is not None:
            settings.log_save_policy = settings_update.log_save_policy
        if settings_update.log_max_total_size_mb is not None:
            settings.log_max_total_size_mb = settings_update.log_max_total_size_mb
        if settings_update.log_cleanup_on_startup is not None:
            settings.log_cleanup_on_startup = settings_update.log_cleanup_on_startup
        if settings_update.email_notifications is not None:
            settings.email_notifications = settings_update.email_notifications
        if settings_update.webhook_url is not None:
            settings.webhook_url = settings_update.webhook_url
        if settings_update.auto_cleanup is not None:
            settings.auto_cleanup = settings_update.auto_cleanup
        if settings_update.cleanup_retention_days is not None:
            settings.cleanup_retention_days = settings_update.cleanup_retention_days
        if settings_update.use_new_wizard is not None:
            settings.use_new_wizard = settings_update.use_new_wizard
        if settings_update.bypass_lock_on_info is not None:
            settings.bypass_lock_on_info = settings_update.bypass_lock_on_info
        if settings_update.bypass_lock_on_list is not None:
            settings.bypass_lock_on_list = settings_update.bypass_lock_on_list
        if settings_update.show_restore_tab is not None:
            settings.show_restore_tab = settings_update.show_restore_tab
        if settings_update.borg2_fast_browse_beta_enabled is not None:
            settings.borg2_fast_browse_beta_enabled = (
                settings_update.borg2_fast_browse_beta_enabled
            )
        if settings_update.stats_refresh_interval_minutes is not None:
            settings.stats_refresh_interval_minutes = (
                settings_update.stats_refresh_interval_minutes
            )

        # MQTT settings
        if settings_update.mqtt_beta_enabled is not None:
            settings.mqtt_beta_enabled = settings_update.mqtt_beta_enabled
        if settings_update.mqtt_enabled is not None:
            settings.mqtt_enabled = settings_update.mqtt_enabled
        if settings_update.mqtt_broker_url is not None:
            settings.mqtt_broker_url = settings_update.mqtt_broker_url
        if settings_update.mqtt_broker_port is not None:
            settings.mqtt_broker_port = settings_update.mqtt_broker_port
        if settings_update.mqtt_username is not None:
            settings.mqtt_username = settings_update.mqtt_username
        if settings_update.mqtt_password is not None:
            if settings_update.mqtt_password == "":
                settings.mqtt_password = None
            else:
                settings.mqtt_password = settings_update.mqtt_password
        if settings_update.mqtt_client_id is not None:
            settings.mqtt_client_id = settings_update.mqtt_client_id
        if settings_update.mqtt_qos is not None:
            settings.mqtt_qos = settings_update.mqtt_qos
        if settings_update.mqtt_retain is not None:
            settings.mqtt_retain = settings_update.mqtt_retain
        if settings_update.mqtt_tls_enabled is not None:
            settings.mqtt_tls_enabled = settings_update.mqtt_tls_enabled
        if settings_update.mqtt_tls_ca_cert is not None:
            settings.mqtt_tls_ca_cert = settings_update.mqtt_tls_ca_cert
        if settings_update.mqtt_tls_client_cert is not None:
            settings.mqtt_tls_client_cert = settings_update.mqtt_tls_client_cert
        if settings_update.mqtt_tls_client_key is not None:
            settings.mqtt_tls_client_key = settings_update.mqtt_tls_client_key

        generated_metrics_token = None

        # Metrics settings
        if settings_update.metrics_enabled is not None:
            settings.metrics_enabled = settings_update.metrics_enabled
        if settings_update.metrics_require_auth is not None:
            settings.metrics_require_auth = settings_update.metrics_require_auth
        if settings_update.metrics_token is not None:
            if settings_update.metrics_token == "":
                settings.metrics_token = None
            else:
                settings.metrics_token = settings_update.metrics_token
                generated_metrics_token = settings.metrics_token
        if settings_update.rotate_metrics_token:
            settings.metrics_token = secrets.token_urlsafe(32)
            generated_metrics_token = settings.metrics_token
        elif settings.metrics_require_auth and not settings.metrics_token:
            settings.metrics_token = secrets.token_urlsafe(32)
            generated_metrics_token = settings.metrics_token

        # Keep persisted metrics state internally consistent when the endpoint is disabled.
        if settings.metrics_enabled is False:
            settings.metrics_require_auth = False

        if settings_update.deployment_type is not None:
            if settings_update.deployment_type not in ("individual", "enterprise"):
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.settings.invalidDeploymentType"},
                )
            settings.deployment_type = settings_update.deployment_type

        if settings_update.enterprise_name is not None:
            settings.enterprise_name = settings_update.enterprise_name.strip() or None

        valid_oidc_new_user_modes = {"deny", "viewer", "pending", "template"}
        if (
            settings_update.oidc_new_user_mode is not None
            and settings_update.oidc_new_user_mode not in valid_oidc_new_user_modes
        ):
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.settings.invalidOidcNewUserMode",
                    "params": {"modes": ", ".join(sorted(valid_oidc_new_user_modes))},
                },
            )

        if (
            settings_update.oidc_default_role is not None
            and settings_update.oidc_default_role not in GLOBAL_ROLE_RANK
        ):
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.settings.invalidOidcDefaultRole"},
            )

        if (
            settings_update.oidc_default_all_repositories_role is not None
            and settings_update.oidc_default_all_repositories_role
            not in REPOSITORY_ROLE_RANK
        ):
            raise HTTPException(
                status_code=400,
                detail={
                    "key": "backend.errors.settings.invalidOidcDefaultRepositoryRole"
                },
            )

        if settings_update.oidc_enabled is not None:
            settings.oidc_enabled = settings_update.oidc_enabled
        if settings_update.oidc_disable_local_auth is not None:
            settings.oidc_disable_local_auth = settings_update.oidc_disable_local_auth
        if settings_update.oidc_provider_name is not None:
            settings.oidc_provider_name = (
                settings_update.oidc_provider_name.strip() or "Single sign-on"
            )
        if settings_update.oidc_discovery_url is not None:
            settings.oidc_discovery_url = (
                settings_update.oidc_discovery_url.strip() or None
            )
        if settings_update.oidc_client_id is not None:
            settings.oidc_client_id = settings_update.oidc_client_id.strip() or None
        if settings_update.clear_oidc_client_secret:
            settings.oidc_client_secret_encrypted = None
        elif settings_update.oidc_client_secret is not None:
            if settings_update.oidc_client_secret == "":
                settings.oidc_client_secret_encrypted = None
            else:
                settings.oidc_client_secret_encrypted = encrypt_secret(
                    settings_update.oidc_client_secret
                )
        if settings_update.oidc_scopes is not None:
            settings.oidc_scopes = (
                settings_update.oidc_scopes.strip() or "openid profile email"
            )
        if settings_update.oidc_redirect_uri_override is not None:
            settings.oidc_redirect_uri_override = (
                settings_update.oidc_redirect_uri_override.strip() or None
            )
        if settings_update.oidc_end_session_endpoint_override is not None:
            settings.oidc_end_session_endpoint_override = (
                settings_update.oidc_end_session_endpoint_override.strip() or None
            )
        if settings_update.oidc_claim_username is not None:
            settings.oidc_claim_username = (
                settings_update.oidc_claim_username.strip() or "preferred_username"
            )
        if settings_update.oidc_claim_email is not None:
            settings.oidc_claim_email = (
                settings_update.oidc_claim_email.strip() or "email"
            )
        if settings_update.oidc_claim_full_name is not None:
            settings.oidc_claim_full_name = (
                settings_update.oidc_claim_full_name.strip() or "name"
            )
        if settings_update.oidc_group_claim is not None:
            settings.oidc_group_claim = settings_update.oidc_group_claim.strip() or None
        if settings_update.oidc_role_claim is not None:
            settings.oidc_role_claim = settings_update.oidc_role_claim.strip() or None
        if settings_update.oidc_admin_groups is not None:
            settings.oidc_admin_groups = (
                settings_update.oidc_admin_groups.strip() or None
            )
        if settings_update.oidc_all_repositories_role_claim is not None:
            settings.oidc_all_repositories_role_claim = (
                settings_update.oidc_all_repositories_role_claim.strip() or None
            )
        if settings_update.oidc_new_user_mode is not None:
            settings.oidc_new_user_mode = settings_update.oidc_new_user_mode
        if settings_update.oidc_new_user_template_username is not None:
            settings.oidc_new_user_template_username = (
                settings_update.oidc_new_user_template_username.strip() or None
            )
        if settings_update.oidc_default_role is not None:
            settings.oidc_default_role = settings_update.oidc_default_role
        if settings_update.oidc_default_all_repositories_role is not None:
            settings.oidc_default_all_repositories_role = (
                normalize_repository_role_for_global_role(
                    settings.oidc_default_role or "viewer",
                    settings_update.oidc_default_all_repositories_role,
                )
            )

        if (
            settings.oidc_new_user_mode == "template"
            and not settings.oidc_new_user_template_username
        ):
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.settings.oidcTemplateUserRequired"},
            )

        if settings.oidc_disable_local_auth and not settings.oidc_enabled:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.settings.oidcLocalAuthRequiresOidc"},
            )

        if settings.oidc_enabled and (
            not settings.oidc_discovery_url
            or not settings.oidc_client_id
            or not settings.oidc_client_secret_encrypted
        ):
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.settings.oidcConfigurationIncomplete"},
            )

        settings.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(settings)

        # Reconfigure MQTT runtime immediately so in-memory enabled state tracks
        # changes to both mqtt_enabled and mqtt_beta_enabled without restart.
        try:
            from app.services.mqtt_service import (
                mqtt_service,
                build_mqtt_runtime_config,
            )

            mqtt_config = build_mqtt_runtime_config(settings)
            mqtt_service.configure(mqtt_config)

            if mqtt_config["enabled"]:
                mqtt_service.sync_state_with_db(db, reason="settings_update")
        except Exception as mqtt_error:
            logger.warning(
                "Failed to apply MQTT runtime reconfiguration", error=str(mqtt_error)
            )

        logger.info("System settings updated", user=current_user.username)

        response = {
            "success": True,
            "message": "backend.success.settings.systemSettingsUpdated",
        }
        if generated_metrics_token:
            response["generated_metrics_token"] = generated_metrics_token
        if warnings:
            response["warnings"] = warnings

        return response
    except HTTPException:
        # Re-raise HTTP exceptions (like validation errors) as-is
        raise
    except Exception as e:
        logger.error("Failed to update system settings", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedUpdateSystemSettings",
                "params": {"error": str(e)},
            },
        )


async def _run_stats_refresh_background(repo_ids: list, username: str):
    """Background task to refresh stats for all repositories"""
    from app.core.borg_router import BorgRouter
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        success_count = 0
        error_count = 0

        for repo_id in repo_ids:
            repo = db.query(Repository).filter(Repository.id == repo_id).first()
            if not repo:
                continue
            try:
                result = await BorgRouter(repo).update_stats(db)
                if result:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(
                    "Error refreshing stats for repository",
                    repo_id=repo.id,
                    repo_name=repo.name,
                    error=str(e),
                )
                error_count += 1

        # Update last_stats_refresh timestamp
        settings = db.query(SystemSettings).first()
        if settings:
            settings.last_stats_refresh = datetime.utcnow()
            db.commit()

        logger.info(
            "Background stats refresh completed",
            user=username,
            success=success_count,
            errors=error_count,
        )
    except Exception as e:
        logger.error("Background stats refresh failed", error=str(e))
    finally:
        db.close()


@router.post("/refresh-stats")
async def refresh_all_stats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Manually trigger a refresh of all repository statistics.
    Runs in the background and returns immediately.
    Check last_stats_refresh timestamp to know when it completed.
    """
    try:
        import asyncio

        logger.info("Manual stats refresh triggered", user=current_user.username)

        # Get all repository IDs
        repos = db.query(Repository).all()
        repo_ids = [r.id for r in repos]

        if not repo_ids:
            return {
                "success": True,
                "message": "backend.success.settings.noRepositoriesToRefresh",
                "repository_count": 0,
            }

        # Start background task
        asyncio.create_task(
            _run_stats_refresh_background(repo_ids, current_user.username)
        )

        return {
            "success": True,
            "message": {
                "key": "backend.success.settings.statsRefreshStarted",
                "params": {"count": len(repo_ids)},
            },
            "repository_count": len(repo_ids),
        }
    except Exception as e:
        logger.error("Failed to start stats refresh", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedStartStatsRefresh",
                "params": {"error": str(e)},
            },
        )


@router.get("/users")
async def get_users(db: Session = Depends(get_db)):
    """Get all users (admin only)"""
    try:
        users = db.query(User).all()
        return {
            "success": True,
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "email": user.email,
                    "is_active": user.is_active,
                    "role": user.role,
                    "all_repositories_role": user.all_repositories_role,
                    "auth_source": getattr(user, "auth_source", "local"),
                    "oidc_subject": getattr(user, "oidc_subject", None),
                    "created_at": user.created_at,
                    "last_login": user.last_login,
                }
                for user in users
            ],
        }
    except Exception as e:
        logger.error("Failed to get users", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedRetrieveUsers",
                "params": {"error": str(e)},
            },
        )


@router.post("/users")
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only)"""
    try:
        # Check user limit by plan
        current_plan = get_current_plan(db)
        user_count = db.query(User).count()
        limit = USER_LIMITS[current_plan]
        if limit is not None and user_count >= limit:
            raise HTTPException(
                status_code=403,
                detail={
                    "key": "backend.errors.plan.userLimitReached",
                    "current": current_plan.value,
                    "limit": limit,
                },
            )

        # Check if username already exists
        existing_user = (
            db.query(User).filter(User.username == user_data.username).first()
        )
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.settings.usernameAlreadyExists"},
            )

        # Check if email already exists
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.settings.emailAlreadyExists"},
            )

        # Create new user
        hashed_password = get_password_hash(user_data.password)
        new_user = User(
            username=user_data.username,
            full_name=user_data.full_name,
            email=user_data.email,
            password_hash=hashed_password,
            role=user_data.role,
            all_repositories_role=default_repository_role_for_global_role(
                user_data.role
            ),
            is_active=True,
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info(
            "User created",
            username=user_data.username,
            created_by=current_user.username,
        )

        return {
            "success": True,
            "message": "backend.success.settings.userCreated",
            "user": {
                "id": new_user.id,
                "username": new_user.username,
                "full_name": new_user.full_name,
                "email": new_user.email,
                "is_active": new_user.is_active,
                "role": new_user.role,
                "all_repositories_role": new_user.all_repositories_role,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create user", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedCreateUser",
                "params": {"error": str(e)},
            },
        )


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user (admin only)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=404, detail={"key": "backend.errors.settings.userNotFound"}
            )

        # Update user fields
        if user_data.username is not None:
            # Check if username already exists
            existing_user = (
                db.query(User)
                .filter(User.username == user_data.username, User.id != user_id)
                .first()
            )
            if existing_user:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.settings.usernameAlreadyExists"},
                )
            user.username = user_data.username

        if user_data.full_name is not None:
            user.full_name = user_data.full_name.strip() or None

        if user_data.email is not None:
            # Check if email already exists
            existing_email = (
                db.query(User)
                .filter(User.email == user_data.email, User.id != user_id)
                .first()
            )
            if existing_email:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.settings.emailAlreadyExists"},
                )
            user.email = user_data.email

        if user_data.is_active is not None:
            user.is_active = user_data.is_active

        if user_data.role is not None:
            user.role = user_data.role
            user.all_repositories_role = normalize_repository_role_for_global_role(
                user.role,
                user.all_repositories_role,
            )

        user.updated_at = datetime.utcnow()
        db.commit()

        logger.info("User updated", user_id=user_id, updated_by=current_user.username)

        return {"success": True, "message": "backend.success.settings.userUpdated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update user", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedUpdateUser",
                "params": {"error": str(e)},
            },
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete user (admin only)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=404, detail={"key": "backend.errors.settings.userNotFound"}
            )

        # Prevent deleting the last admin user
        if user.is_admin:
            admin_count = db.query(User).filter(User.role == "admin").count()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.settings.cannotDeleteLastAdmin"},
                )

        # Prevent deleting yourself
        if user.id == current_user.id:
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.settings.cannotDeleteOwnAccount"},
            )

        db.delete(user)
        db.commit()

        logger.info("User deleted", user_id=user_id, deleted_by=current_user.username)

        return {"success": True, "message": "backend.success.settings.userDeleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete user", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedDeleteUser",
                "params": {"error": str(e)},
            },
        )


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    password_data: PasswordReset,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset user password (admin only)"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=404, detail={"key": "backend.errors.settings.userNotFound"}
            )

        hashed_password = get_password_hash(password_data.new_password)
        user.password_hash = hashed_password
        user.updated_at = datetime.utcnow()
        db.commit()

        logger.info(
            "User password reset", user_id=user_id, reset_by=current_user.username
        )

        return {"success": True, "message": "backend.success.settings.passwordReset"}
    except HTTPException:
        raise  # Re-raise HTTP exceptions to preserve status codes
    except Exception as e:
        logger.error("Failed to reset user password", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedResetPassword",
                "params": {"error": str(e)},
            },
        )


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change current user's password"""
    try:
        # Verify current password
        if not verify_password(
            password_data.current_password, current_user.password_hash
        ):
            raise HTTPException(
                status_code=400,
                detail={"key": "backend.errors.auth.currentPasswordIncorrect"},
            )

        # Update password
        hashed_password = get_password_hash(password_data.new_password)
        current_user.password_hash = hashed_password
        current_user.must_change_password = (
            False  # Clear the flag after password change
        )
        current_user.updated_at = datetime.utcnow()
        db.commit()

        logger.info("Password changed", username=current_user.username)

        return {"success": True, "message": "backend.success.settings.passwordChanged"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to change password", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedChangePassword",
                "params": {"error": str(e)},
            },
        )


@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's profile"""
    settings = db.query(SystemSettings).first()
    deployment_type = settings.deployment_type if settings else "individual"
    enterprise_name = settings.enterprise_name if settings else None

    return {
        "success": True,
        "profile": {
            "id": current_user.id,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "is_active": current_user.is_active,
            "is_admin": current_user.is_admin,
            "role": current_user.role,
            "must_change_password": current_user.must_change_password,
            "created_at": current_user.created_at,
            "last_login": current_user.last_login,
            "deployment_type": deployment_type,
            "enterprise_name": enterprise_name,
        },
    }


@router.put("/profile")
async def update_profile(
    profile_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user's profile"""
    try:
        # Update user fields
        if profile_data.username is not None:
            # Check if username already exists
            existing_user = (
                db.query(User)
                .filter(
                    User.username == profile_data.username, User.id != current_user.id
                )
                .first()
            )
            if existing_user:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.settings.usernameAlreadyExists"},
                )
            current_user.username = profile_data.username

        if profile_data.full_name is not None:
            current_user.full_name = profile_data.full_name.strip() or None

        if profile_data.email is not None:
            # Check if email already exists
            existing_email = (
                db.query(User)
                .filter(User.email == profile_data.email, User.id != current_user.id)
                .first()
            )
            if existing_email:
                raise HTTPException(
                    status_code=400,
                    detail={"key": "backend.errors.settings.emailAlreadyExists"},
                )
            current_user.email = profile_data.email

        current_user.updated_at = datetime.utcnow()
        db.commit()

        logger.info("Profile updated", username=current_user.username)

        return {"success": True, "message": "backend.success.settings.profileUpdated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update profile", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedUpdateProfile",
                "params": {"error": str(e)},
            },
        )


@router.get("/preferences")
async def get_preferences(current_user: User = Depends(get_current_user)):
    """Get current user's preferences"""
    return {
        "success": True,
        "preferences": {
            "analytics_enabled": current_user.analytics_enabled
            if hasattr(current_user, "analytics_enabled")
            else True,
            "analytics_consent_given": current_user.analytics_consent_given
            if hasattr(current_user, "analytics_consent_given")
            else False,
        },
    }


@router.put("/preferences")
async def update_preferences(
    preferences: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user's preferences"""
    try:
        if preferences.analytics_enabled is not None:
            current_user.analytics_enabled = preferences.analytics_enabled
        if preferences.analytics_consent_given is not None:
            current_user.analytics_consent_given = preferences.analytics_consent_given

        current_user.updated_at = datetime.utcnow()
        db.commit()

        logger.info(
            "User preferences updated",
            username=current_user.username,
            analytics_enabled=preferences.analytics_enabled,
            analytics_consent_given=preferences.analytics_consent_given,
        )

        return {
            "success": True,
            "message": "backend.success.settings.preferencesUpdated",
        }
    except Exception as e:
        logger.error("Failed to update preferences", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedUpdatePreferences",
                "params": {"error": str(e)},
            },
        )


@router.post("/system/cleanup")
async def cleanup_system(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Run system cleanup (admin only)"""
    try:
        # Get system settings
        settings = db.query(SystemSettings).first()
        if not settings:
            # Create default settings if they don't exist
            settings = SystemSettings(
                backup_timeout=3600,
                max_concurrent_backups=2,
                log_retention_days=30,
                email_notifications=False,
                webhook_url="",
                auto_cleanup=True,
                cleanup_retention_days=90,
            )
            db.add(settings)
            db.commit()
            db.refresh(settings)

        # Perform cleanup tasks (placeholder implementation)
        cleanup_results = {
            "logs_cleaned": 0,
            "old_backups_removed": 0,
            "temp_files_cleaned": 0,
        }

        # TODO: Implement actual cleanup logic
        # - Clean old logs based on log_retention_days
        # - Remove old backup archives based on cleanup_retention_days
        # - Clean temporary files

        logger.info(
            "System cleanup completed",
            user=current_user.username,
            results=cleanup_results,
        )

        return {
            "success": True,
            "message": "backend.success.settings.systemCleanupCompleted",
            "results": cleanup_results,
        }
    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error occurred"
        logger.error("Failed to run system cleanup", error=error_msg)
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedRunSystemCleanup",
                "params": {"error": error_msg},
            },
        )


@router.get("/system/logs/storage")
async def get_log_storage_stats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Get detailed log storage statistics.

    Returns comprehensive information about log files including:
    - Total size and file count
    - Breakdown by job type
    - Oldest and newest log dates
    - Usage percentage against configured limit
    """
    try:
        from app.services.log_manager import log_manager

        # Get system settings for limit
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)
            db.commit()

        # Calculate log storage
        log_storage = log_manager.calculate_log_storage()

        # Calculate usage percentage
        usage_percent = 0
        if settings.log_max_total_size_mb and settings.log_max_total_size_mb > 0:
            usage_percent = min(
                100,
                int(
                    (log_storage["total_size_mb"] / settings.log_max_total_size_mb)
                    * 100
                ),
            )

        return {
            "success": True,
            "storage": {
                "total_size_bytes": log_storage["total_size_bytes"],
                "total_size_mb": log_storage["total_size_mb"],
                "file_count": log_storage["file_count"],
                "oldest_log_date": log_storage["oldest_log_date"].isoformat()
                if log_storage["oldest_log_date"]
                else None,
                "newest_log_date": log_storage["newest_log_date"].isoformat()
                if log_storage["newest_log_date"]
                else None,
                "files_by_type": log_storage["files_by_type"],
                "usage_percent": usage_percent,
                "limit_mb": settings.log_max_total_size_mb,
                "retention_days": settings.log_retention_days,
            },
        }
    except Exception as e:
        logger.error("Failed to get log storage stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedGetLogStorageStats",
                "params": {"error": str(e)},
            },
        )


@router.post("/system/logs/cleanup")
async def manual_log_cleanup(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Manually trigger log cleanup based on current settings.

    This endpoint:
    - Requires admin access
    - Reads log_retention_days and log_max_total_size_mb from settings
    - Protects logs for running jobs
    - Performs age-based cleanup first, then size-based cleanup
    - Returns detailed cleanup statistics
    """
    try:
        from app.services.log_manager import log_manager

        # Get system settings
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)
            db.commit()

        max_age_days = settings.log_retention_days or 30
        max_total_size_mb = settings.log_max_total_size_mb or 500

        logger.info(
            "Manual log cleanup triggered",
            user=current_user.username,
            max_age_days=max_age_days,
            max_total_size_mb=max_total_size_mb,
        )

        # Run cleanup
        result = log_manager.cleanup_logs_combined(
            db=db,
            max_age_days=max_age_days,
            max_total_size_mb=max_total_size_mb,
            dry_run=False,
        )

        # Get updated storage stats
        log_storage = log_manager.calculate_log_storage()

        logger.info(
            "Manual log cleanup completed",
            user=current_user.username,
            deleted_count=result["total_deleted_count"],
            size_freed_mb=result["total_deleted_size_mb"],
        )

        if result["total_deleted_count"] > 0:
            message = {
                "key": "backend.success.settings.logCleanupCompleted",
                "params": {
                    "count": result["total_deleted_count"],
                    "sizeMb": result["total_deleted_size_mb"],
                },
            }
        else:
            message = {
                "key": "backend.success.settings.logCleanupNoop",
                "params": {
                    "retentionDays": max_age_days,
                    "sizeLimitMb": max_total_size_mb,
                },
            }

        return {
            "success": result["success"],
            "message": message,
            "cleanup_results": {
                "age_cleanup": {
                    "deleted_count": result["age_cleanup"]["deleted_count"],
                    "deleted_size_mb": result["age_cleanup"]["deleted_size_mb"],
                    "skipped_count": result["age_cleanup"]["skipped_count"],
                },
                "size_cleanup": {
                    "deleted_count": result["size_cleanup"]["deleted_count"],
                    "deleted_size_mb": result["size_cleanup"]["deleted_size_mb"],
                    "skipped_count": result["size_cleanup"]["skipped_count"],
                    "final_size_mb": result["size_cleanup"]["final_size_mb"],
                },
                "total_deleted_count": result["total_deleted_count"],
                "total_deleted_size_mb": result["total_deleted_size_mb"],
                "errors": result["total_errors"],
            },
            "current_storage": {
                "total_size_mb": log_storage["total_size_mb"],
                "file_count": log_storage["file_count"],
            },
        }
    except Exception as e:
        logger.error(
            "Failed to run manual log cleanup", user=current_user.username, error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedRunLogCleanup",
                "params": {"error": str(e)},
            },
        )


# ============================================================================
# Cache Management Endpoints
# ============================================================================


@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Get cache statistics and configuration.

    Returns:
    - Backend type (redis/in-memory)
    - Cache statistics (hits, misses, hit rate, size, entry count)
    - Current settings (TTL, max size)
    - Availability status

    Accessible to all authenticated users.
    """
    try:
        # Get cache stats from service
        stats = await archive_cache.get_stats()

        # Get database settings
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)
            db.commit()

        # Combine with database settings
        stats["cache_ttl_minutes"] = settings.cache_ttl_minutes
        stats["cache_max_size_mb"] = settings.cache_max_size_mb
        stats["redis_url"] = settings.redis_url
        stats["browse_max_items"] = settings.browse_max_items
        stats["browse_max_memory_mb"] = settings.browse_max_memory_mb

        return stats

    except Exception as e:
        logger.error("Failed to get cache stats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedGetCacheStats",
                "params": {"error": str(e)},
            },
        )


@router.post("/cache/clear")
async def clear_cache(
    repository_id: Optional[int] = Query(
        None, description="Repository ID to clear cache for (or None for all)"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Clear archive cache.

    - If repository_id provided: Clear cache for that repository only
    - If repository_id is None: Clear all cache entries

    Requires admin access.

    Returns:
    - Number of cache entries cleared
    """
    try:
        if repository_id is not None:
            # Validate repository exists
            repository = (
                db.query(Repository).filter(Repository.id == repository_id).first()
            )
            if not repository:
                raise HTTPException(
                    status_code=404,
                    detail={"key": "backend.errors.repo.repositoryNotFound"},
                )

            # Clear cache for specific repository
            cleared_count = await archive_cache.clear_repository(repository_id)
            logger.info(
                "Cache cleared for repository",
                user=current_user.username,
                repository_id=repository_id,
                cleared_count=cleared_count,
            )

            return {
                "cleared_count": cleared_count,
                "repository_id": repository_id,
                "message": "backend.success.settings.cacheCleared",
            }
        else:
            # Clear all cache
            cleared_count = await archive_cache.clear_all()
            logger.info(
                "Cache cleared (all repositories)",
                user=current_user.username,
                cleared_count=cleared_count,
            )

            return {
                "cleared_count": cleared_count,
                "repository_id": None,
                "message": "backend.success.settings.allCacheCleared",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to clear cache",
            user=current_user.username,
            repository_id=repository_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedClearCache",
                "params": {"error": str(e)},
            },
        )


@router.put("/cache/settings")
async def update_cache_settings(
    cache_ttl_minutes: Optional[int] = Query(
        None, ge=1, le=10080, description="Cache TTL in minutes (1-10080)"
    ),
    cache_max_size_mb: Optional[int] = Query(
        None, ge=100, le=10240, description="Max cache size in MB (100-10240)"
    ),
    redis_url: Optional[str] = Query(
        None, description="External Redis URL (e.g., redis://host:6379/0)"
    ),
    browse_max_items: Optional[int] = Query(
        None,
        ge=100_000,
        le=50_000_000,
        description="Max items to load when browsing archives (100k-50M)",
    ),
    browse_max_memory_mb: Optional[int] = Query(
        None,
        ge=100,
        le=16384,
        description="Max memory for archive browsing in MB (100MB-16GB)",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update cache settings.

    Parameters:
    - cache_ttl_minutes: Cache time-to-live in minutes (1 minute to 7 days)
    - cache_max_size_mb: Maximum cache size in megabytes (100MB to 10GB)
    - redis_url: External Redis URL (optional). Use empty string to clear and use local Redis.
    - browse_max_items: Maximum number of files to load when browsing archives (100k to 50M)
    - browse_max_memory_mb: Maximum memory allowed for archive browsing (100MB to 16GB)

    Note: TTL changes only affect new cache entries. Existing entries keep their original TTL.
    Note: Browse limits prevent OOM when viewing archives with millions of files.

    Requires admin access.

    Returns:
    - Updated settings
    - Redis connection result if redis_url was changed
    """
    if (
        cache_ttl_minutes is None
        and cache_max_size_mb is None
        and redis_url is None
        and browse_max_items is None
        and browse_max_memory_mb is None
    ):
        raise HTTPException(
            status_code=400,
            detail={"key": "backend.errors.settings.atLeastOneSettingRequired"},
        )

    try:
        # Get or create system settings
        settings = db.query(SystemSettings).first()
        if not settings:
            settings = SystemSettings()
            db.add(settings)

        # Track changes for logging
        changes = {}
        reconfigure_result = None

        # Update Redis URL if provided
        if redis_url is not None:
            old_url = settings.redis_url
            settings.redis_url = redis_url if redis_url.strip() else None
            changes["redis_url"] = {"old": old_url, "new": settings.redis_url}

            # Reconfigure cache service with new Redis URL
            try:
                reconfigure_result = archive_cache.reconfigure(
                    redis_url=settings.redis_url,
                    cache_max_size_mb=cache_max_size_mb or settings.cache_max_size_mb,
                )

                if not reconfigure_result["success"]:
                    logger.warning(
                        "Redis reconfiguration failed, using fallback",
                        redis_url=settings.redis_url,
                        backend=reconfigure_result["backend"],
                    )
            except Exception as reconfig_error:
                logger.error(
                    "Failed to reconfigure cache service",
                    redis_url=settings.redis_url,
                    error=str(reconfig_error),
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "key": "backend.errors.settings.failedConnectRedis",
                        "params": {"error": str(reconfig_error)},
                    },
                )

        # Update TTL
        if cache_ttl_minutes is not None:
            old_ttl = settings.cache_ttl_minutes
            settings.cache_ttl_minutes = cache_ttl_minutes
            changes["cache_ttl_minutes"] = {"old": old_ttl, "new": cache_ttl_minutes}

            # Update config for new cache entries
            app_settings.cache_ttl_seconds = cache_ttl_minutes * 60

        # Update max size
        if cache_max_size_mb is not None:
            old_size = settings.cache_max_size_mb
            settings.cache_max_size_mb = cache_max_size_mb
            changes["cache_max_size_mb"] = {"old": old_size, "new": cache_max_size_mb}

            # Update config for cache service
            app_settings.cache_max_size_mb = cache_max_size_mb

            # If we didn't already reconfigure for redis_url, reconfigure for size
            if redis_url is None and reconfigure_result is None:
                try:
                    reconfigure_result = archive_cache.reconfigure(
                        cache_max_size_mb=cache_max_size_mb
                    )
                except Exception as reconfig_error:
                    logger.warning(
                        "Failed to reconfigure cache size", error=str(reconfig_error)
                    )

        # Update browse limits
        if browse_max_items is not None:
            old_items = settings.browse_max_items
            settings.browse_max_items = browse_max_items
            changes["browse_max_items"] = {"old": old_items, "new": browse_max_items}

        if browse_max_memory_mb is not None:
            old_memory = settings.browse_max_memory_mb
            settings.browse_max_memory_mb = browse_max_memory_mb
            changes["browse_max_memory_mb"] = {
                "old": old_memory,
                "new": browse_max_memory_mb,
            }

        db.commit()

        logger.info(
            "Cache settings updated", user=current_user.username, changes=changes
        )

        response = {
            "cache_ttl_minutes": settings.cache_ttl_minutes,
            "cache_max_size_mb": settings.cache_max_size_mb,
            "redis_url": settings.redis_url,
            "browse_max_items": settings.browse_max_items,
            "browse_max_memory_mb": settings.browse_max_memory_mb,
            "message": "backend.success.settings.cacheSettingsUpdated",
        }

        # Add reconfiguration result if available
        if reconfigure_result:
            response["backend"] = reconfigure_result["backend"]
            response["connection_info"] = reconfigure_result.get("connection_info")

        return response

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(
            "Failed to update cache settings", user=current_user.username, error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail={
                "key": "backend.errors.settings.failedUpdateCacheSettings",
                "params": {"error": str(e)},
            },
        )
