import hashlib

from sqlalchemy.orm import Session

from app.services.licensing_service import get_or_create_licensing_state


def analytics_keys(db: Session, user_id: int) -> dict[str, str | None]:
    """Pseudonymous keys for usage analytics.

    Analytics only ever carries these hashes. The license platform's nightly
    analytics sync computes sha256(instance_id) the same way to join installs.
    """
    instance_id = get_or_create_licensing_state(db).instance_id
    # Optional telemetry must not prevent preferences from loading or hash a
    # missing identity into a shared key. Leave identity repair to licensing.
    if not instance_id or not instance_id.strip():
        return {"analytics_instance_key": None, "analytics_user_key": None}
    return {
        "analytics_instance_key": hashlib.sha256(instance_id.encode()).hexdigest(),
        "analytics_user_key": hashlib.sha256(
            f"{instance_id}:{user_id}".encode()
        ).hexdigest(),
    }
