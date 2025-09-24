from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List

from backend.app.routes import notifications as notifications_routes
from backend.app.services import notifications as notifications_service
from backend.app.schemas.notifications import (
    Notification,
    NotificationListResponse,
    NotificationMarkReadRequest,
    NotificationMarkReadResponse,
    NotificationType,
)


def test_list_notifications_returns_paginated_results(monkeypatch):
    user = SimpleNamespace(id=101)
    captured: Dict[str, object] = {}

    notification = Notification(
        id=1,
        userId=user.id,
        type=NotificationType.SYSTEM,
        createdAt=datetime.now(timezone.utc),
        isRead=False,
    )

    def fake_list_notifications(
        user_id: int,
        *,
        limit: int,
        cursor: str | None,
        conn=None,
    ) -> NotificationListResponse:
        captured["user_id"] = user_id
        captured["limit"] = limit
        captured["cursor"] = cursor
        return NotificationListResponse(items=[notification], nextCursor="next-cursor")

    monkeypatch.setattr(
        notifications_service,
        "list_notifications",
        fake_list_notifications,
    )

    response = notifications_routes.list_notifications(
        cursor="abc",
        limit=5,
        current_user=user,
    )

    assert isinstance(response, NotificationListResponse)
    assert response.items[0].id == notification.id
    assert response.next_cursor == "next-cursor"
    assert captured == {"user_id": user.id, "limit": 5, "cursor": "abc"}


def test_get_unread_count_returns_value(monkeypatch):
    user = SimpleNamespace(id=202)

    def fake_unread_count(user_id: int, *, conn=None) -> int:
        assert user_id == user.id
        return 7

    monkeypatch.setattr(
        notifications_service,
        "unread_count",
        fake_unread_count,
    )

    response = notifications_routes.get_unread_count(current_user=user)

    assert response.count == 7


def test_mark_read_returns_updated_ids_and_unread_count(monkeypatch):
    user = SimpleNamespace(id=303)
    captured: Dict[str, object] = {}

    def fake_mark_read(
        notification_ids: List[int],
        *,
        user_id: int,
        conn=None,
    ) -> List[int]:
        captured["mark_read_ids"] = list(notification_ids)
        captured["user_id"] = user_id
        return [2, 3]

    def fake_unread_count(user_id: int, *, conn=None) -> int:
        assert user_id == user.id
        return 4

    monkeypatch.setattr(
        notifications_service,
        "mark_read",
        fake_mark_read,
    )
    monkeypatch.setattr(
        notifications_service,
        "unread_count",
        fake_unread_count,
    )

    request = NotificationMarkReadRequest(ids=[3, 2])

    response = notifications_routes.mark_notifications_read(
        request,
        current_user=user,
    )

    assert isinstance(response, NotificationMarkReadResponse)
    assert response.updated_ids == [2, 3]
    assert response.unread_count == 4
    assert captured == {"mark_read_ids": [3, 2], "user_id": user.id}
