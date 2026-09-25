import hashlib

from sqlalchemy.orm import Session

from app.services.licensing_service import get_or_create_licensing_state


def analytics_keys(db: Session, user_id: int) -> dict[str, str]:
    """Pseudonymous keys for usage analytics.

    Analytics only ever carries these hashes. The license platform's nightly
    analytics sync computes sha256(instance_id) the same way to join installs.
    """
    instance_id = get_or_create_licensing_state(db).instance_id
    return {
        "analytics_instance_key": hashlib.sha256(instance_id.encode()).hexdigest(),
        "analytics_user_key": hashlib.sha256(
            f"{instance_id}:{user_id}".encode()
        ).hexdigest(),
    }
