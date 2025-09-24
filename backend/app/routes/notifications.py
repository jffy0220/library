"""API routes for notification interactions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..schemas.notifications import (
    NotificationListResponse,
    NotificationMarkReadRequest,
    NotificationMarkReadResponse,
    NotificationUnreadCount,
)

try:  # pragma: no cover - import fallback for tests executed as scripts
    from backend.main import get_current_user
except ModuleNotFoundError as exc:  # pragma: no cover - fallback for local execution
    if exc.name != "backend":
        raise
    from ...main import get_current_user  # type: ignore[no-redef]

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    *,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(
        default=_DEFAULT_PAGE_SIZE,
        ge=1,
        le=_MAX_PAGE_SIZE,
    ),
    current_user=Depends(get_current_user),
) -> NotificationListResponse:
    """Return paginated notifications for the authenticated user."""
    from ..services import notifications as notifications_service

    return notifications_service.list_notifications(
        current_user.id,
        limit=limit,
        cursor=cursor,
    )


@router.get("/unread_count", response_model=NotificationUnreadCount)
def get_unread_count(*, current_user=Depends(get_current_user)) -> NotificationUnreadCount:
    """Return the unread notification count for the current user."""
    from ..services import notifications as notifications_service

    count = notifications_service.unread_count(current_user.id)
    return NotificationUnreadCount(count=count)


@router.post("/mark_read", response_model=NotificationMarkReadResponse)
def mark_notifications_read(
    payload: NotificationMarkReadRequest,
    *,
    current_user=Depends(get_current_user),
) -> NotificationMarkReadResponse:
    """Mark the provided notifications as read for the current user."""
    from ..services import notifications as notifications_service

    updated_ids = notifications_service.mark_read(
        payload.ids,
        user_id=current_user.id,
    )
    unread_count = notifications_service.unread_count(current_user.id)
    return NotificationMarkReadResponse(
        updated_ids=updated_ids,
        unread_count=unread_count,
    )