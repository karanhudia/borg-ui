"""Get-or-create the spec 6.2 extension row for an operation.

Wipe, rclone sync, restore, and backup have one. The row is flushed, not
committed, so a caller composing several writes keeps one transaction.
"""

from sqlalchemy.orm import Session

from app.database.models import (
    Operation,
    OperationBackupDetails,
    OperationRcloneDetails,
    OperationRestoreDetails,
    OperationWipeDetails,
)


def _get_or_create(db: Session, model, operation: Operation):
    row = db.get(model, operation.id)
    if row is None:
        row = model(operation_id=operation.id)
        db.add(row)
        db.flush()
    return row


def wipe_details(db: Session, operation: Operation) -> OperationWipeDetails:
    return _get_or_create(db, OperationWipeDetails, operation)


def rclone_details(db: Session, operation: Operation) -> OperationRcloneDetails:
    return _get_or_create(db, OperationRcloneDetails, operation)


def restore_details(db: Session, operation: Operation) -> OperationRestoreDetails:
    return _get_or_create(db, OperationRestoreDetails, operation)


def backup_details(db: Session, operation: Operation) -> OperationBackupDetails:
    return _get_or_create(db, OperationBackupDetails, operation)
