from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import LicensingState

logger = structlog.get_logger()
PLAN_RANK = {"community": 0, "pro": 1, "enterprise": 2}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _to_utc(value)
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    return _to_utc(datetime.fromisoformat(normalized))


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _get_public_key() -> str | None:
    return settings.activation_public_key


def _get_auth_headers() -> dict[str, str]:
    secret = settings.activation_shared_secret
    if not secret:
        return {}
    return {"Authorization": f"Bearer {secret}"}


def _validate_signature(payload: dict[str, Any], signature: str) -> bool:
    public_key_value = _get_public_key()
    if not public_key_value:
        logger.info("Skipping entitlement signature validation; no activation public key configured")
        return True

    try:
        public_key_raw = base64.b64decode(public_key_value)
        signature_raw = base64.b64decode(signature)
        public_key = _load_public_key(public_key_raw)
        public_key.verify(signature_raw, _canonical_payload(payload))
        return True
    except Exception as exc:
        logger.warning("Failed entitlement signature validation", error=str(exc))
        return False


def _load_public_key(public_key_raw: bytes) -> Ed25519PublicKey:
    try:
        return Ed25519PublicKey.from_public_bytes(public_key_raw)
    except ValueError:
        public_key = load_der_public_key(public_key_raw)
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("Activation public key is not an Ed25519 public key")
        return public_key


def get_or_create_licensing_state(db: Session) -> LicensingState:
    state = db.query(LicensingState).first()
    if state:
        if not state.instance_id:
            state.instance_id = str(uuid.uuid4())
            db.commit()
            db.refresh(state)
        return state

    state = LicensingState(instance_id=str(uuid.uuid4()))
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def get_effective_plan_value(db: Session) -> str:
    state = get_or_create_licensing_state(db)
    refresh_status_if_expired(state)
    db.commit()
    return state.plan if state.status == "active" else "community"


def refresh_status_if_expired(state: LicensingState) -> None:
    now = utc_now()
    starts_at = _to_utc(state.starts_at)
    expires_at = _to_utc(state.expires_at)

    if state.status != "active":
        return

    if starts_at and now < starts_at:
        state.status = "none"
        state.plan = "community"
        return

    if expires_at and now >= expires_at:
        state.status = "expired"
        state.plan = "community"


def get_entitlement_summary(db: Session) -> dict[str, Any]:
    state = get_or_create_licensing_state(db)
    refresh_status_if_expired(state)
    db.commit()

    payload = state.payload_json or {}
    refresh_after = _parse_dt(payload.get("refresh_after"))
    is_full_access = bool(state.is_trial and state.status == "active")

    return {
        "status": state.status,
        "access_level": _access_level(state),
        "is_full_access": is_full_access,
        "full_access_consumed": state.trial_consumed,
        "expires_at": state.expires_at.isoformat() if state.expires_at else None,
        "starts_at": state.starts_at.isoformat() if state.starts_at else None,
        "refresh_after": refresh_after.isoformat() if refresh_after else None,
        "instance_id": state.instance_id,
        "entitlement_id": state.entitlement_id,
        "key_id": state.key_id,
        "license_id": state.license_id,
        "customer_id": state.customer_id,
        "ui_state": _ui_state(state),
        "last_refresh_at": state.last_refresh_at.isoformat() if state.last_refresh_at else None,
        "last_refresh_error": state.last_refresh_error,
    }


def get_feature_access(db: Session) -> dict[str, bool]:
    from app.core.features import FEATURES

    state = get_or_create_licensing_state(db)
    refresh_status_if_expired(state)
    current_plan = state.plan if state.status == "active" else "community"
    effective = {
        feature: PLAN_RANK[current_plan] >= PLAN_RANK[required.value]
        for feature, required in FEATURES.items()
    }

    payload = state.payload_json or {}
    for override in payload.get("feature_overrides", []) or []:
        feature = override.get("feature")
        enabled = override.get("enabled")
        if feature in effective and isinstance(enabled, bool):
            effective[feature] = enabled

    return effective


def _clear_entitlement(
    db: Session,
    state: LicensingState,
    *,
    status: str,
    refresh_error: str | None = None,
) -> None:
    state.plan = "community"
    state.status = status
    state.is_trial = False
    state.entitlement_id = None
    state.key_id = None
    state.customer_id = None
    state.license_id = None
    state.max_users = None
    state.issued_at = None
    state.starts_at = None
    state.expires_at = None
    state.payload_json = None
    state.signature = None
    state.last_refresh_at = utc_now()
    state.last_refresh_error = refresh_error
    db.commit()


def _normalize_service_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text or f"HTTP {response.status_code}"

    error = payload.get("error")
    if isinstance(error, dict):
        return error.get("message") or error.get("code") or f"HTTP {response.status_code}"
    return response.text or f"HTTP {response.status_code}"


def _validate_entitlement_document(state: LicensingState, payload: Any, signature: Any) -> str | None:
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return "Activation service returned malformed entitlement"

    if payload.get("instance_id") != state.instance_id:
        return "Entitlement instance_id does not match this Borg UI instance."

    if not _validate_signature(payload, signature):
        return "Entitlement signature validation failed"

    return None


def _apply_entitlement(
    db: Session,
    state: LicensingState,
    payload: dict[str, Any],
    signature: str,
    key_id: str | None = None,
    refresh_error: str | None = None,
) -> None:
    state.entitlement_id = payload.get("entitlement_id")
    state.key_id = key_id
    state.customer_id = payload.get("customer_id")
    state.license_id = payload.get("license_id")
    state.plan = payload.get("plan") or "community"
    state.status = payload.get("status") or "active"
    state.is_trial = bool(payload.get("is_trial"))
    state.trial_consumed = bool(state.trial_consumed or payload.get("is_trial"))
    state.max_users = payload.get("max_users")
    state.issued_at = _parse_dt(payload.get("issued_at"))
    state.starts_at = _parse_dt(payload.get("starts_at"))
    state.expires_at = _parse_dt(payload.get("expires_at"))
    state.last_refresh_at = utc_now()
    state.last_refresh_error = refresh_error
    state.payload_json = payload
    state.signature = signature
    refresh_status_if_expired(state)
    db.commit()


async def _post_activation(endpoint_path: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    if not settings.activation_service_url:
        raise RuntimeError("Activation service URL is not configured.")

    endpoint = settings.activation_service_url.rstrip("/") + endpoint_path
    async with httpx.AsyncClient(timeout=settings.activation_timeout_seconds) as client:
        response = await client.post(endpoint, json=request_payload, headers=_get_auth_headers())
        if response.status_code >= 400:
            raise RuntimeError(_normalize_service_error(response))
        return response.json()


def _should_refresh(state: LicensingState) -> bool:
    if not settings.activation_service_url:
        return False

    payload = state.payload_json or {}
    refresh_after = _parse_dt(payload.get("refresh_after"))
    now = utc_now()

    if refresh_after and now >= refresh_after:
        return True

    if state.last_refresh_at is None:
        return state.status == "active"

    return (now - _to_utc(state.last_refresh_at)).total_seconds() >= (
        settings.activation_refresh_interval_hours * 60 * 60
    )


def _access_level(state: LicensingState) -> str:
    if state.status == "active" and state.is_trial:
        return "full_access"
    if state.status == "active":
        return state.plan or "community"
    return "community"


def _ui_state(state: LicensingState) -> str:
    if state.status == "active" and state.is_trial:
        return "full_access_active"
    if state.status == "active":
        return "paid_active"
    if state.trial_consumed:
        return "full_access_expired"
    return "community"


async def sync_licensing_state(db: Session, *, app_version: str) -> None:
    state = get_or_create_licensing_state(db)
    refresh_status_if_expired(state)

    if state.status == "active":
        if _should_refresh(state):
            await refresh_entitlement(db, app_version=app_version)
        else:
            db.commit()
        return

    await attempt_auto_full_access_activation(db, app_version)


async def attempt_auto_full_access_activation(db: Session, app_version: str) -> None:
    state = get_or_create_licensing_state(db)
    refresh_status_if_expired(state)

    if state.trial_consumed:
        if _should_refresh(state):
            await refresh_entitlement(db, app_version=app_version)
        else:
            db.commit()
        return

    if not settings.activation_service_url:
        logger.debug("Activation service URL not configured; staying on community plan")
        db.commit()
        return

    request_payload = {
        "instance_id": state.instance_id,
        "app": "borg-ui",
        "app_version": app_version,
        "hostname": os.getenv("HOSTNAME"),
        "fingerprint": None,
        "requested_plan": "enterprise",
    }

    try:
        data = await _post_activation("/v1/trials/activate", request_payload)
    except Exception as exc:
        state.last_refresh_at = utc_now()
        state.last_refresh_error = str(exc)
        db.commit()
        logger.warning("Automatic full access activation failed", error=str(exc))
        return

    result = data.get("result")
    if result == "denied":
        state.trial_consumed = data.get("reason") == "trial_already_used"
        state.last_refresh_at = utc_now()
        state.last_refresh_error = None
        db.commit()
        return

    entitlement = data.get("entitlement") or {}
    payload = entitlement.get("payload")
    signature = entitlement.get("signature")
    key_id = entitlement.get("key_id")
    error = _validate_entitlement_document(state, payload, signature)
    if error:
        state.last_refresh_at = utc_now()
        state.last_refresh_error = error
        db.commit()
        logger.warning("Automatic full access activation returned invalid entitlement", error=error)
        return

    _apply_entitlement(db, state, payload, signature, key_id=key_id)


async def refresh_entitlement(db: Session, *, app_version: str) -> dict[str, Any]:
    state = get_or_create_licensing_state(db)
    refresh_status_if_expired(state)

    try:
        data = await _post_activation(
            "/v1/entitlements/refresh",
            {
                "instance_id": state.instance_id,
                "current_entitlement_id": state.entitlement_id,
                "app_version": app_version,
            },
        )
    except Exception as exc:
        state.last_refresh_at = utc_now()
        state.last_refresh_error = str(exc)
        db.commit()
        raise

    result = data.get("result")
    if result == "unchanged":
        state.last_refresh_at = utc_now()
        state.last_refresh_error = None
        db.commit()
        return {"result": "unchanged", "entitlement": get_entitlement_summary(db)}

    if result == "downgraded":
        _clear_entitlement(db, state, status="expired")
        return {"result": "downgraded", "entitlement": get_entitlement_summary(db)}

    entitlement = data.get("entitlement") or {}
    payload = entitlement.get("payload")
    signature = entitlement.get("signature")
    key_id = entitlement.get("key_id")
    error = _validate_entitlement_document(state, payload, signature)
    if error:
        state.last_refresh_at = utc_now()
        state.last_refresh_error = error
        db.commit()
        raise RuntimeError(error)

    _apply_entitlement(db, state, payload, signature, key_id=key_id)
    return {"result": result or "updated", "entitlement": get_entitlement_summary(db)}


async def activate_paid_license(db: Session, *, license_key: str, app_version: str) -> dict[str, Any]:
    state = get_or_create_licensing_state(db)
    data = await _post_activation(
        "/v1/licenses/activate",
        {
            "instance_id": state.instance_id,
            "license_key": license_key,
            "app_version": app_version,
        },
    )

    entitlement = data.get("entitlement") or {}
    payload = entitlement.get("payload")
    signature = entitlement.get("signature")
    key_id = entitlement.get("key_id")
    error = _validate_entitlement_document(state, payload, signature)
    if error:
        state.last_refresh_at = utc_now()
        state.last_refresh_error = error
        db.commit()
        raise RuntimeError(error)

    _apply_entitlement(db, state, payload, signature, key_id=key_id)
    return {"result": data.get("result") or "activated", "entitlement": get_entitlement_summary(db)}


async def deactivate_paid_license(db: Session) -> dict[str, Any]:
    state = get_or_create_licensing_state(db)
    if not state.license_id:
        raise RuntimeError("No active paid license is stored for this instance")

    data = await _post_activation(
        "/v1/licenses/deactivate",
        {
            "instance_id": state.instance_id,
            "license_id": state.license_id,
        },
    )
    _clear_entitlement(db, state, status="none")
    return {"result": data.get("result") or "deactivated", "entitlement": get_entitlement_summary(db)}


def import_offline_entitlement(db: Session, document: dict[str, Any]) -> dict[str, Any]:
    state = get_or_create_licensing_state(db)
    payload = document.get("payload")
    signature = document.get("signature")
    key_id = document.get("key_id")
    error = _validate_entitlement_document(state, payload, signature)
    if error:
        raise RuntimeError(error)

    _apply_entitlement(db, state, payload, signature, key_id=key_id)
    return {"result": "imported", "entitlement": get_entitlement_summary(db)}
