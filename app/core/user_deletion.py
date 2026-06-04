from sqlalchemy.orm import Session

from app.database.models import AuthEvent, OidcLoginState


def detach_user_delete_references(db: Session, user_id: int) -> None:
    """Clear nullable user references that should survive user deletion."""
    db.query(AuthEvent).filter(AuthEvent.actor_user_id == user_id).update(
        {AuthEvent.actor_user_id: None}, synchronize_session=False
    )
    db.query(OidcLoginState).filter(OidcLoginState.user_id == user_id).update(
        {OidcLoginState.user_id: None}, synchronize_session=False
    )
