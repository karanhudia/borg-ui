from sqlalchemy.orm import Session

from app.database.models import AuthEvent, OidcLoginState, RepositoryWipeJob


def detach_user_delete_references(db: Session, user_id: int) -> None:
    """Clear nullable user references that should survive user deletion."""
    db.query(AuthEvent).filter(AuthEvent.actor_user_id == user_id).update(
        {AuthEvent.actor_user_id: None}, synchronize_session=False
    )
    db.query(OidcLoginState).filter(OidcLoginState.user_id == user_id).update(
        {OidcLoginState.user_id: None}, synchronize_session=False
    )
    # Wipe history keeps its rows; these columns have no ON DELETE, so the
    # foreign key refuses the delete (dashboard e4561d13bbb29ff1).
    for column in (
        RepositoryWipeJob.requested_by_user_id,
        RepositoryWipeJob.confirmed_by_user_id,
    ):
        db.query(RepositoryWipeJob).filter(column == user_id).update(
            {column: None}, synchronize_session=False
        )
