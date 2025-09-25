"""Routes for managing user-specific notification preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..schemas.notifications import (
    NotificationPreferences,
    NotificationPreferencesUpdate,
)

from .notifications import _get_current_user

router = APIRouter(prefix="/api/users/me", tags=["notification-preferences"])


@router.get("/notification_prefs", response_model=NotificationPreferences)
def get_notification_preferences(
    *,
    current_user=Depends(_get_current_user),
) -> NotificationPreferences:
    """Return the notification preferences for the authenticated user."""
    from ..services import notifications as notifications_service

    return notifications_service.get_preferences(current_user.id)


@router.put("/notification_prefs", response_model=NotificationPreferences)
def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    *,
    current_user=Depends(_get_current_user),
) -> NotificationPreferences:
    """Create or update the notification preferences for the authenticated user."""
    from ..services import notifications as notifications_service

    return notifications_service.upsert_preferences(current_user.id, payload)


__all__ = [
    "router",
    "get_notification_preferences",
    "update_notification_preferences",
]