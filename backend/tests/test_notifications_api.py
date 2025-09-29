from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional

from backend.app.routes import notifications as notifications_routes
from backend.app.routes import user_preferences as preferences_routes
from backend.app.services import notifications as notifications_service
from backend.app.schemas.notifications import (
    Notification,
    NotificationListResponse,
    NotificationMarkReadRequest,
    NotificationMarkReadResponse,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    EmailDigestOption,
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
        cursor: Optional[str],
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

def test_get_notification_preferences_returns_user_settings(monkeypatch):
    user = SimpleNamespace(id=404)
    expected = NotificationPreferences.default(user.id)

    def fake_get_preferences(user_id: int, *, conn=None):
        assert user_id == user.id
        return expected

    monkeypatch.setattr(
        notifications_service,
        "get_preferences",
        fake_get_preferences,
    )

    response = preferences_routes.get_notification_preferences(current_user=user)

    assert response == expected


def test_update_notification_preferences_upserts_and_returns(monkeypatch):
    user = SimpleNamespace(id=505)
    payload = NotificationPreferencesUpdate(
        replyToSnippet=False,
        mention=False,
        emailDigest=EmailDigestOption.DAILY,
    )
    expected = NotificationPreferences(
        userId=user.id,
        replyToSnippet=False,
        mention=False,
        emailDigest=EmailDigestOption.DAILY,
    )
    captured: Dict[str, object] = {}

    def fake_upsert_preferences(user_id: int, preferences, *, conn=None):
        captured["user_id"] = user_id
        captured["preferences"] = preferences
        return expected

    monkeypatch.setattr(
        notifications_service,
        "upsert_preferences",
        fake_upsert_preferences,
    )

    response = preferences_routes.update_notification_preferences(
        payload,
        current_user=user,
    )

    assert response == expected
    assert captured["user_id"] == user.id
    assert isinstance(captured["preferences"], NotificationPreferencesUpdate)
    assert captured["preferences"].reply_to_snippet is False
    assert captured["preferences"].mention is False
    assert captured["preferences"].email_digest is EmailDigestOption.DAILY