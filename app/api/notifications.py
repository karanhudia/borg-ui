"""
Notification settings API endpoints.

Provides CRUD operations for notification configurations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from app.database.database import get_db
from app.database.models import NotificationSettings
from app.services.notification_service import notification_service
from app.api.auth import get_current_user, User
from app.utils.datetime_utils import serialize_datetime

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# Pydantic models
class NotificationSettingsCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="User-friendly name")
    service_url: str = Field(..., description="Apprise service URL (e.g., slack://token/)")
    enabled: bool = Field(default=True)
    title_prefix: Optional[str] = Field(default=None, max_length=100, description="Optional prefix for notification titles (e.g., '[Production]')")
    notify_on_backup_start: bool = Field(default=False)
    notify_on_backup_success: bool = Field(default=False)
    notify_on_backup_failure: bool = Field(default=True)
    notify_on_restore_success: bool = Field(default=False)
    notify_on_restore_failure: bool = Field(default=True)
    notify_on_schedule_failure: bool = Field(default=True)


class NotificationSettingsUpdate(BaseModel):
    name: Optional[str] = None
    service_url: Optional[str] = None
    enabled: Optional[bool] = None
    title_prefix: Optional[str] = None
    notify_on_backup_start: Optional[bool] = None
    notify_on_backup_success: Optional[bool] = None
    notify_on_backup_failure: Optional[bool] = None
    notify_on_restore_success: Optional[bool] = None
    notify_on_restore_failure: Optional[bool] = None
    notify_on_schedule_failure: Optional[bool] = None


class NotificationSettingsResponse(BaseModel):
    id: int
    name: str
    service_url: str
    enabled: bool
    title_prefix: Optional[str]
    notify_on_backup_start: bool
    notify_on_backup_success: bool
    notify_on_backup_failure: bool
    notify_on_restore_success: bool
    notify_on_restore_failure: bool
    notify_on_schedule_failure: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: serialize_datetime(v)
        }


class TestNotificationRequest(BaseModel):
    service_url: str = Field(..., description="Apprise service URL to test")


# Endpoints
@router.get("", response_model=List[NotificationSettingsResponse])
async def list_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all notification settings."""
    settings = db.query(NotificationSettings).all()
    return settings


@router.get("/{setting_id}", response_model=NotificationSettingsResponse)
async def get_notification_setting(
    setting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get notification setting by ID."""
    setting = db.query(NotificationSettings).filter(
        NotificationSettings.id == setting_id
    ).first()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification setting not found"
        )

    return setting


@router.post("", response_model=NotificationSettingsResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_setting(
    setting_data: NotificationSettingsCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new notification setting."""
    # Create setting
    setting = NotificationSettings(**setting_data.model_dump())
    db.add(setting)
    db.commit()
    db.refresh(setting)

    return setting


@router.put("/{setting_id}", response_model=NotificationSettingsResponse)
async def update_notification_setting(
    setting_id: int,
    setting_data: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update notification setting."""
    setting = db.query(NotificationSettings).filter(
        NotificationSettings.id == setting_id
    ).first()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification setting not found"
        )

    # Update fields
    update_data = setting_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(setting, key, value)

    db.commit()
    db.refresh(setting)

    return setting


@router.delete("/{setting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification_setting(
    setting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete notification setting."""
    setting = db.query(NotificationSettings).filter(
        NotificationSettings.id == setting_id
    ).first()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification setting not found"
        )

    db.delete(setting)
    db.commit()


@router.post("/test")
async def test_notification(
    request: TestNotificationRequest,
    current_user: User = Depends(get_current_user)
):
    """Test a notification service URL."""
    result = await notification_service.test_notification(request.service_url)
    return result
