import base64
from datetime import datetime, timedelta, timezone

from backend.app.schemas.notifications import (
    EmailDigestOption,
    NotificationCreate,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    NotificationType,
)
from backend.app.services import notifications


class FakeCursor:
    def __init__(self, *, fetchone_result=None, fetchall_result=None):
        self.fetchone_result = fetchone_result
        self.fetchall_result = list(fetchall_result or [])
        self.execute_calls = []
        self.closed = False

    def execute(self, query, params=None):
        self.execute_calls.append((" ".join(query.split()), params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return list(self.fetchall_result)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False


class FakeConnection:
    def __init__(self, *cursors):
        self._cursors = list(cursors)
        self.cursor_calls = []

    def cursor(self, *args, **kwargs):
        self.cursor_calls.append((args, kwargs))
        if not self._cursors:
            raise AssertionError("No cursors configured")
        return self._cursors.pop(0)


def test_encode_decode_cursor_round_trip():
    created_at = datetime(2024, 5, 1, 12, 30, tzinfo=timezone.utc)
    encoded = notifications._encode_cursor(created_at, 42)
    assert isinstance(encoded, str)

    decoded_created_at, decoded_id = notifications._decode_cursor(encoded)
    assert decoded_id == 42
    assert decoded_created_at == created_at

    # Spot check encoding format for stability.
    raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
    assert b"\"id\":42" in raw


def test_create_notification_inserts_row():
    row = {
        "id": 1,
        "user_id": 7,
        "type": NotificationType.MENTION.value,
        "actor_user_id": 2,
        "snippet_id": 11,
        "comment_id": None,
        "title": "New mention",
        "body": "You were mentioned",
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
    }
    cursor = FakeCursor(fetchone_result=row)
    conn = FakeConnection(cursor)

    event = NotificationCreate(
        userId=row["user_id"],
        type=NotificationType.MENTION,
        actorUserId=row["actor_user_id"],
        snippetId=row["snippet_id"],
        title=row["title"],
        body=row["body"],
    )

    created = notifications.create_notification(event, conn=conn)

    assert created.id == row["id"]
    assert created.user_id == row["user_id"]
    assert created.type == NotificationType.MENTION
    assert cursor.execute_calls


def test_list_notifications_paginates_results():
    now = datetime.now(timezone.utc)
    older = now - timedelta(minutes=1)
    oldest = now - timedelta(minutes=2)
    rows = [
        {
            "id": 3,
            "user_id": 9,
            "type": NotificationType.SYSTEM.value,
            "actor_user_id": None,
            "snippet_id": None,
            "comment_id": None,
            "title": "System alert",
            "body": "System message",
            "is_read": False,
            "created_at": now,
        },
        {
            "id": 2,
            "user_id": 9,
            "type": NotificationType.MENTION.value,
            "actor_user_id": 4,
            "snippet_id": 8,
            "comment_id": None,
            "title": None,
            "body": "Mentioned",
            "is_read": True,
            "created_at": older,
        },
        {
            "id": 1,
            "user_id": 9,
            "type": NotificationType.REPLY_TO_SNIPPET.value,
            "actor_user_id": 5,
            "snippet_id": 8,
            "comment_id": 12,
            "title": None,
            "body": "Reply",
            "is_read": False,
            "created_at": oldest,
        },
    ]
    cursor = FakeCursor(fetchall_result=rows)
    conn = FakeConnection(cursor)

    response = notifications.list_notifications(9, limit=2, conn=conn)

    assert len(response.items) == 2
    assert response.next_cursor is not None
    assert response.items[0].id == rows[0]["id"]


def test_unread_count_returns_integer():
    cursor = FakeCursor(fetchone_result=(5,))
    conn = FakeConnection(cursor)

    count = notifications.unread_count(4, conn=conn)
    assert count == 5


def test_mark_read_filters_ids_and_returns_updated():
    cursor = FakeCursor(fetchall_result=[(3,), (2,)])
    conn = FakeConnection(cursor)

    updated = notifications.mark_read([2, 2, 3], user_id=7, conn=conn)
    assert sorted(updated) == [2, 3]
    # Ensure duplicates were removed from parameters.
    (_, params), = cursor.execute_calls
    assert params[1] == [2, 3]


def test_get_preferences_returns_defaults_when_missing():
    cursor = FakeCursor(fetchone_result=None)
    conn = FakeConnection(cursor)

    prefs = notifications.get_preferences(user_id=5, conn=conn)
    assert isinstance(prefs, NotificationPreferences)
    assert prefs.user_id == 5
    assert prefs.email_digest == EmailDigestOption.WEEKLY


def test_upsert_preferences_applies_updates():
    updated_row = {
        "user_id": 10,
        "reply_to_snippet": False,
        "reply_to_comment": True,
        "mention": False,
        "vote_on_your_snippet": True,
        "moderation_update": True,
        "system": True,
        "email_digest": EmailDigestOption.DAILY.value,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    cursor = FakeCursor(fetchone_result=updated_row)
    conn = FakeConnection(cursor)

    prefs = notifications.upsert_preferences(
        10,
        NotificationPreferencesUpdate(mention=False, emailDigest=EmailDigestOption.DAILY),
        conn=conn,
    )

    assert prefs.user_id == 10
    assert not prefs.mention
    assert prefs.email_digest == EmailDigestOption.DAILY

    (_, params), = cursor.execute_calls
    assert params["user_id"] == 10
    assert params["mention"] is False
    assert params["email_digest"] == EmailDigestOption.DAILY