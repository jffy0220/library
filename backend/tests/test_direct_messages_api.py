+165
-0

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import HTTPException

from backend.app.routes import direct_messages as dm_routes
from backend.app.schemas.direct_messages import (
    DirectMessage,
    DirectMessageList,
    DirectMessageMarkReadResponse,
    DirectMessageParticipant,
    DirectMessageSendRequest,
    DirectMessageSendResponse,
    DirectMessageStartRequest,
    DirectMessageStartResponse,
    DirectMessageThread,
    DirectMessageThreadList,
)
from backend.app.services import direct_messages as dm_service


def _sample_thread(thread_id: int = 1) -> DirectMessageThread:
    participant = DirectMessageParticipant(userId=2, username="bob")
    return DirectMessageThread(
        id=thread_id,
        createdAt=datetime.now(timezone.utc),
        lastMessageAt=None,
        participant=participant,
        lastMessage=None,
        unreadCount=0,
    )


def test_start_conversation_returns_thread(monkeypatch):
    user = SimpleNamespace(id=10, username="alice")
    thread = _sample_thread(99)
    captured = {}

    def fake_start_thread(*, initiator_id: int, target_username: str, conn=None):
        captured["initiator_id"] = initiator_id
        captured["target_username"] = target_username
        return thread

    monkeypatch.setattr(dm_service, "start_thread", fake_start_thread)

    payload = DirectMessageStartRequest(username="bob")
    response = dm_routes.start_conversation(payload, current_user=user)

    assert isinstance(response, DirectMessageStartResponse)
    assert response.thread == thread
    assert response.thread_id == thread.id
    assert captured == {"initiator_id": user.id, "target_username": "bob"}


def test_list_threads_returns_service_response(monkeypatch):
    user = SimpleNamespace(id=22)
    thread_list = DirectMessageThreadList(threads=[_sample_thread(3)])

    def fake_list_threads(user_id: int, *, conn=None):
        assert user_id == user.id
        return thread_list

    monkeypatch.setattr(dm_service, "list_threads", fake_list_threads)

    response = dm_routes.list_threads(current_user=user)

    assert response is thread_list


def test_list_thread_messages_passes_cursor(monkeypatch):
    user = SimpleNamespace(id=33)
    expected = DirectMessageList(messages=[], nextCursor=None, hasMore=False)
    captured = {}

    def fake_list_messages(
        thread_id: int,
        *,
        user_id: int,
        limit: int,
        cursor: Optional[int],
        conn=None,
    ):
        captured["thread_id"] = thread_id
        captured["user_id"] = user_id
        captured["limit"] = limit
        captured["cursor"] = cursor
        return expected

    monkeypatch.setattr(dm_service, "list_messages", fake_list_messages)

    response = dm_routes.list_thread_messages(
        55,
        cursor="15",
        limit=5,
        current_user=user,
    )

    assert response is expected
    assert captured == {"thread_id": 55, "user_id": user.id, "limit": 5, "cursor": 15}


@pytest.mark.parametrize("cursor_value", ["abc", "10.5"])
def test_list_thread_messages_invalid_cursor(cursor_value):
    user = SimpleNamespace(id=44)
    with pytest.raises(HTTPException) as exc:
        dm_routes.list_thread_messages(1, cursor=cursor_value, current_user=user)
    assert exc.value.status_code == 400


def test_send_thread_message_returns_response(monkeypatch):
    user = SimpleNamespace(id=77, username="alice")
    message = DirectMessage(
        id=5,
        threadId=8,
        senderId=user.id,
        senderUsername=user.username,
        body="Hi",
        createdAt=datetime.now(timezone.utc),
    )
    thread = _sample_thread(8)
    expected = DirectMessageSendResponse(message=message, thread=thread)
    captured = {}

    def fake_send_message(
        thread_id: int,
        *,
        user_id: int,
        sender_username: str,
        body: str,
        conn=None,
    ):
        captured.update(
            {
                "thread_id": thread_id,
                "user_id": user_id,
                "sender_username": sender_username,
                "body": body,
            }
        )
        return expected

    monkeypatch.setattr(dm_service, "send_message", fake_send_message)

    payload = DirectMessageSendRequest(body="Hello there")
    response = dm_routes.send_thread_message(8, payload, current_user=user)

    assert response is expected
    assert captured == {
        "thread_id": 8,
        "user_id": user.id,
        "sender_username": user.username,
        "body": "Hello there",
    }


def test_mark_thread_read_returns_response(monkeypatch):
    user = SimpleNamespace(id=88)
    expected = DirectMessageMarkReadResponse(unreadCount=0)
    captured = {}

    def fake_mark_thread_read(thread_id: int, *, user_id: int, conn=None):
        captured["thread_id"] = thread_id
        captured["user_id"] = user_id
        return expected

    monkeypatch.setattr(dm_service, "mark_thread_read", fake_mark_thread_read)

    response = dm_routes.mark_thread_read(12, current_user=user)

    assert response is expected
    assert captured == {"thread_id": 12, "user_id": user.id}