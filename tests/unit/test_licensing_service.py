import base64
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.config import settings
from app.services import licensing_service
from app.services.licensing_service import (
    activate_paid_license,
    request_feature_trial,
    deactivate_paid_license,
    get_effective_plan_value,
    get_entitlement_summary,
    get_or_create_licensing_state,
    import_offline_entitlement,
    refresh_entitlement,
    utc_now,
)


def _build_document(
    private_key: Ed25519PrivateKey,
    *,
    instance_id: str,
    entitlement_id: str = "ent_01",
    plan: str = "pro",
    is_trial: bool = True,
    status: str = "active",
    starts_offset_days: int = -1,
    expires_offset_days: int = 30,
    refresh_offset_days: int = 7,
    feature_overrides: list | None = None,
) -> dict:
    now = utc_now()
    payload = {
        "entitlement_id": entitlement_id,
        "instance_id": instance_id,
        "customer_id": "cust_01",
        "license_id": "lic_01",
        "plan": plan,
        "status": status,
        "is_trial": is_trial,
        "feature_overrides": feature_overrides or [],
        "max_users": 5,
        "issued_at": now.isoformat(),
        "starts_at": (now + timedelta(days=starts_offset_days)).isoformat(),
        "expires_at": (now + timedelta(days=expires_offset_days)).isoformat(),
        "refresh_after": (now + timedelta(days=refresh_offset_days)).isoformat(),
        "metadata": {"edition": "official", "channel": "trial" if is_trial else "paid"},
        "signature_version": "v1",
    }
    signature = base64.b64encode(
        private_key.sign(licensing_service._canonical_payload(payload))
    ).decode("utf-8")
    return {"payload": payload, "signature": signature, "key_id": "key_2026_01"}


@pytest.fixture
def activation_keys(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setattr(
        settings, "activation_public_key", base64.b64encode(public_key).decode("utf-8")
    )
    monkeypatch.setattr(
        settings, "activation_service_url", "https://activation.example.test"
    )
    return private_key


@pytest.fixture
def activation_keys_der(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    monkeypatch.setattr(
        settings, "activation_public_key", base64.b64encode(public_key).decode("utf-8")
    )
    monkeypatch.setattr(
        settings, "activation_service_url", "https://activation.example.test"
    )
    return private_key


@pytest.mark.unit
def test_import_offline_entitlement_sets_active_trial(db_session, activation_keys):
    state = get_or_create_licensing_state(db_session)
    document = _build_document(activation_keys, instance_id=state.instance_id)

    result = import_offline_entitlement(db_session, document)

    summary = get_entitlement_summary(db_session)
    assert result["result"] == "imported"
    assert get_effective_plan_value(db_session) == "pro"
    assert summary["status"] == "active"
    assert summary["access_level"] == "full_access"
    assert summary["is_full_access"] is True
    assert summary["instance_id"] == state.instance_id
    assert summary["expires_at"].endswith("+00:00")
    assert summary["starts_at"].endswith("+00:00")
    assert summary["refresh_after"].endswith("+00:00")
    assert summary["last_refresh_at"].endswith("+00:00")


@pytest.mark.unit
def test_import_offline_entitlement_accepts_der_public_keys(
    db_session, activation_keys_der
):
    state = get_or_create_licensing_state(db_session)
    document = _build_document(activation_keys_der, instance_id=state.instance_id)

    result = import_offline_entitlement(db_session, document)

    summary = get_entitlement_summary(db_session)
    assert result["result"] == "imported"
    assert summary["status"] == "active"
    assert summary["access_level"] == "full_access"
    assert summary["is_full_access"] is True


@pytest.mark.unit
def test_expired_entitlement_downgrades_to_community(db_session, activation_keys):
    state = get_or_create_licensing_state(db_session)
    document = _build_document(
        activation_keys,
        instance_id=state.instance_id,
        expires_offset_days=-1,
    )

    import_offline_entitlement(db_session, document)

    summary = get_entitlement_summary(db_session)
    assert get_effective_plan_value(db_session) == "community"
    assert summary["status"] == "expired"
    assert summary["is_full_access"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_entitlement_updates_state(db_session, activation_keys):
    state = get_or_create_licensing_state(db_session)
    initial = _build_document(
        activation_keys, instance_id=state.instance_id, entitlement_id="ent_old"
    )
    import_offline_entitlement(db_session, initial)
    updated = _build_document(
        activation_keys,
        instance_id=state.instance_id,
        entitlement_id="ent_new",
        plan="enterprise",
        is_trial=False,
    )

    with patch(
        "app.services.licensing_service._post_activation",
        new=AsyncMock(return_value={"result": "updated", "entitlement": updated}),
    ):
        result = await refresh_entitlement(db_session, app_version="1.70.0")

    summary = get_entitlement_summary(db_session)
    assert result["result"] == "updated"
    assert get_effective_plan_value(db_session) == "enterprise"
    assert summary["entitlement_id"] == "ent_new"
    assert summary["access_level"] == "enterprise"
    assert summary["is_full_access"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_failure_keeps_active_entitlement_until_expiry(
    db_session, activation_keys
):
    state = get_or_create_licensing_state(db_session)
    document = _build_document(
        activation_keys,
        instance_id=state.instance_id,
        entitlement_id="ent_keep_active",
        plan="enterprise",
        is_trial=False,
        refresh_offset_days=-1,
        expires_offset_days=30,
    )
    import_offline_entitlement(db_session, document)

    with patch(
        "app.services.licensing_service._post_activation",
        new=AsyncMock(side_effect=RuntimeError("activation service offline")),
    ):
        with pytest.raises(RuntimeError, match="activation service offline"):
            await refresh_entitlement(db_session, app_version="1.70.0")

    summary = get_entitlement_summary(db_session)
    assert get_effective_plan_value(db_session) == "enterprise"
    assert summary["status"] == "active"
    assert summary["access_level"] == "enterprise"
    assert summary["last_refresh_error"] == "activation service offline"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refresh_downgrade_revokes_local_entitlement(db_session, activation_keys):
    state = get_or_create_licensing_state(db_session)
    document = _build_document(
        activation_keys,
        instance_id=state.instance_id,
        entitlement_id="ent_to_revoke",
        plan="pro",
        is_trial=False,
    )
    import_offline_entitlement(db_session, document)

    with patch(
        "app.services.licensing_service._post_activation",
        new=AsyncMock(return_value={"result": "downgraded"}),
    ):
        result = await refresh_entitlement(db_session, app_version="1.70.0")

    summary = get_entitlement_summary(db_session)
    assert result["result"] == "downgraded"
    assert get_effective_plan_value(db_session) == "community"
    assert summary["status"] == "expired"
    assert summary["access_level"] == "community"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_and_deactivate_paid_license(db_session, activation_keys):
    state = get_or_create_licensing_state(db_session)
    activated = _build_document(
        activation_keys,
        instance_id=state.instance_id,
        entitlement_id="ent_paid",
        is_trial=False,
        plan="pro",
    )

    with patch(
        "app.services.licensing_service._post_activation",
        new=AsyncMock(
            side_effect=[
                {"result": "activated", "entitlement": activated},
                {"result": "deactivated"},
            ]
        ),
    ):
        activation_result = await activate_paid_license(
            db_session,
            license_key="BORG-XXXX-XXXX-XXXX",
            app_version="1.70.0",
        )
        assert activation_result["result"] == "activated"
        assert get_effective_plan_value(db_session) == "pro"

        deactivation_result = await deactivate_paid_license(
            db_session,
        )

    summary = get_entitlement_summary(db_session)
    assert deactivation_result["result"] == "deactivated"
    assert get_effective_plan_value(db_session) == "community"
    assert summary["status"] == "none"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deactivate_paid_license_requires_stored_license_id(db_session):
    get_or_create_licensing_state(db_session)

    with pytest.raises(
        RuntimeError, match="No active paid license is stored for this instance"
    ):
        await deactivate_paid_license(db_session)


@pytest.mark.unit
def test_pro_activation_enqueues_nothing(db_session, activation_keys):
    """Going Pro used to enqueue a catch-up index for every repository. The
    index is built on every plan now, so there is nothing to catch up (spec
    2026-09-21-community-teasers-and-feature-trials, section 2)."""
    from app.database.models import Operation, Repository

    db_session.add(
        Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    )
    db_session.commit()
    state = get_or_create_licensing_state(db_session)
    document = _build_document(
        activation_keys, instance_id=state.instance_id, plan="pro", is_trial=False
    )
    import_offline_entitlement(db_session, document)
    assert db_session.query(Operation).count() == 0


@pytest.mark.unit
def test_feature_override_grants_while_the_entitlement_is_active(
    db_session, activation_keys
):
    state = get_or_create_licensing_state(db_session)
    import_offline_entitlement(
        db_session,
        _build_document(
            activation_keys,
            instance_id=state.instance_id,
            plan="community",
            is_trial=False,
            feature_overrides=[{"feature": "archive_history", "enabled": True}],
        ),
    )

    assert licensing_service.get_feature_access(db_session)["archive_history"] is True


@pytest.mark.unit
def test_feature_override_stops_granting_once_expired(db_session, activation_keys):
    state = get_or_create_licensing_state(db_session)
    import_offline_entitlement(
        db_session,
        _build_document(
            activation_keys,
            instance_id=state.instance_id,
            plan="community",
            is_trial=False,
            starts_offset_days=-30,
            expires_offset_days=-1,
            feature_overrides=[{"feature": "archive_history", "enabled": True}],
        ),
    )

    access = licensing_service.get_feature_access(db_session)
    assert access["archive_history"] is False
    assert get_effective_plan_value(db_session) == "community"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feature_trial_grants_the_feature_on_a_community_plan(
    db_session, activation_keys
):
    """The activation service answers with a Community entitlement carrying
    one override, and the feature reads as available until it expires."""
    state = get_or_create_licensing_state(db_session)
    document = _build_document(
        activation_keys,
        instance_id=state.instance_id,
        plan="community",
        is_trial=False,
        expires_offset_days=14,
        feature_overrides=[{"feature": "archive_history", "enabled": True}],
    )
    with patch.object(
        licensing_service,
        "_post_activation",
        AsyncMock(return_value={"result": "activated", "entitlement": document}),
    ) as post:
        result = await request_feature_trial(
            db_session, feature="archive_history", app_version="2.3.0"
        )

    assert post.await_args.args[0] == "/v1/trials/activate"
    assert post.await_args.args[1]["requested_feature"] == "archive_history"
    assert result["result"] == "activated"
    assert licensing_service.get_feature_access(db_session)["archive_history"] is True
    assert get_effective_plan_value(db_session) == "community"
    summary = get_entitlement_summary(db_session)
    assert [f["feature"] for f in summary["trial_features"]] == ["archive_history"]
    assert summary["expired_trial_features"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_denied_feature_trial_leaves_the_plan_alone(db_session):
    state = get_or_create_licensing_state(db_session)
    with patch.object(
        licensing_service,
        "_post_activation",
        AsyncMock(return_value={"result": "denied", "reason": "trial_already_used"}),
    ):
        result = await request_feature_trial(
            db_session, feature="archive_history", app_version="2.3.0"
        )

    assert result["result"] == "denied" and result["reason"] == "trial_already_used"
    assert licensing_service.get_feature_access(db_session)["archive_history"] is False
    assert state.status != "active"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_feature_trial_for_an_unknown_feature_is_refused(db_session):
    with pytest.raises(RuntimeError, match="Unknown feature"):
        await request_feature_trial(db_session, feature="nope", app_version="2.3.0")


@pytest.mark.unit
def test_a_lapsed_feature_trial_is_reported_as_expired(db_session, activation_keys):
    state = get_or_create_licensing_state(db_session)
    import_offline_entitlement(
        db_session,
        _build_document(
            activation_keys,
            instance_id=state.instance_id,
            plan="community",
            is_trial=False,
            starts_offset_days=-30,
            expires_offset_days=-1,
            feature_overrides=[{"feature": "archive_history", "enabled": True}],
        ),
    )
    summary = get_entitlement_summary(db_session)
    assert summary["trial_features"] == []
    assert summary["expired_trial_features"] == ["archive_history"]
