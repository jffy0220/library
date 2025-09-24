from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, List, Mapping, Optional, Sequence, Tuple

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

try:
    from backend.main import get_conn
except ModuleNotFoundError as exc:  # pragma: no cover - fallback for local execution
    if exc.name != "backend":
        raise
    from main import get_conn  # type: ignore[no-redef]

from ..schemas.notifications import (
    EmailDigestOption,
    Notification,
    NotificationCreate,
    NotificationListResponse,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    NotificationType,
)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

_PREFERENCE_COLUMNS = (
    "reply_to_snippet",
    "reply_to_comment",
    "mention",
    "vote_on_your_snippet",
    "moderation_update",
    "system",
    "email_digest",
)


@contextmanager
def _ensure_connection(conn: Optional[PgConnection]):
    if conn is not None:
        yield conn
        return
    with get_conn() as owned_conn:
        yield owned_conn


def _encode_cursor(created_at: datetime, notification_id: int) -> str:
    payload = {"created_at": created_at.isoformat(), "id": notification_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> Tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw)
        created_at = datetime.fromisoformat(payload["created_at"])
        notification_id = int(payload["id"])
    except Exception as exc:  # pragma: no cover - defensive, validated by tests
        raise ValueError("Invalid cursor") from exc
    return created_at, notification_id


def _coerce_notification(row: Mapping[str, Any]) -> Notification:
    data = {
        "id": row["id"],
        "userId": row["user_id"],
        "type": row["type"],
        "actorUserId": row.get("actor_user_id"),
        "snippetId": row.get("snippet_id"),
        "commentId": row.get("comment_id"),
        "title": row.get("title"),
        "body": row.get("body"),
        "isRead": row.get("is_read", False),
        "createdAt": row["created_at"],
    }
    return Notification.model_validate(data)


def _prepare_preferences_payload(user_id: int, update: Mapping[str, Any]) -> Mapping[str, Any]:
    defaults = NotificationPreferences.default(user_id).model_dump(by_alias=False)
    payload = {key: defaults[key] for key in ("user_id", *_PREFERENCE_COLUMNS)}
    payload.update({k: v for k, v in update.items() if v is not None})
    return payload


def create_notification(
    event: NotificationCreate | Mapping[str, Any],
    *,
    conn: Optional[PgConnection] = None,
) -> Notification:
    if not isinstance(event, NotificationCreate):
        event = NotificationCreate.model_validate(event)

    with _ensure_connection(conn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO notifications (
                    user_id,
                    type,
                    actor_user_id,
                    snippet_id,
                    comment_id,
                    title,
                    body
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id,
                          user_id,
                          type::text AS type,
                          actor_user_id,
                          snippet_id,
                          comment_id,
                          title,
                          body,
                          is_read,
                          created_at
                """,
                (
                    event.user_id,
                    event.type.value,
                    event.actor_user_id,
                    event.snippet_id,
                    event.comment_id,
                    event.title,
                    event.body,
                ),
            )
            row = cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to insert notification")
    return _coerce_notification(row)


def list_notifications(
    user_id: int,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: Optional[str] = None,
    conn: Optional[PgConnection] = None,
) -> NotificationListResponse:
    page_size = max(1, min(int(limit), MAX_PAGE_SIZE))

    params: List[Any] = [user_id]
    cursor_clause = ""
    if cursor:
        created_at, notification_id = _decode_cursor(cursor)
        cursor_clause = (
            " AND (n.created_at < %s OR (n.created_at = %s AND n.id < %s))"
        )
        params.extend([created_at, created_at, notification_id])

    params.append(page_size + 1)

    query = f"""
        SELECT
            n.id,
            n.user_id,
            n.type::text AS type,
            n.actor_user_id,
            n.snippet_id,
            n.comment_id,
            n.title,
            n.body,
            n.is_read,
            n.created_at
        FROM notifications n
        WHERE n.user_id = %s{cursor_clause}
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT %s
    """

    with _ensure_connection(conn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    next_cursor = None
    if len(rows) > page_size:
        last_row = rows.pop()
        next_cursor = _encode_cursor(last_row["created_at"], last_row["id"])

    notifications = [_coerce_notification(row) for row in rows]
    return NotificationListResponse(items=notifications, nextCursor=next_cursor)


def unread_count(
    user_id: int,
    *,
    conn: Optional[PgConnection] = None,
) -> int:
    with _ensure_connection(conn) as connection:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = FALSE",
                (user_id,),
            )
            row = cur.fetchone()
    return int(row[0]) if row else 0


def mark_read(
    notification_ids: Sequence[int],
    user_id: int,
    *,
    conn: Optional[PgConnection] = None,
) -> List[int]:
    ids = list(dict.fromkeys(int(notification_id) for notification_id in notification_ids))
    if not ids:
        return []

    with _ensure_connection(conn) as connection:
        with connection.cursor() as cur:
            cur.execute(
                """
                UPDATE notifications
                SET is_read = TRUE
                WHERE user_id = %s AND id = ANY(%s)
                RETURNING id
                """,
                (user_id, ids),
            )
            rows = cur.fetchall()
    return [row[0] for row in rows]


def get_preferences(
    user_id: int,
    *,
    conn: Optional[PgConnection] = None,
) -> NotificationPreferences:
    with _ensure_connection(conn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    user_id,
                    reply_to_snippet,
                    reply_to_comment,
                    mention,
                    vote_on_your_snippet,
                    moderation_update,
                    system,
                    email_digest,
                    created_at,
                    updated_at
                FROM notification_prefs
                WHERE user_id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
    if not row:
        return NotificationPreferences.default(user_id)
    payload = {
        "userId": row["user_id"],
        "replyToSnippet": row["reply_to_snippet"],
        "replyToComment": row["reply_to_comment"],
        "mention": row["mention"],
        "voteOnYourSnippet": row["vote_on_your_snippet"],
        "moderationUpdate": row["moderation_update"],
        "system": row["system"],
        "emailDigest": row["email_digest"],
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }
    return NotificationPreferences.model_validate(payload)


def upsert_preferences(
    user_id: int,
    preferences: NotificationPreferencesUpdate | Mapping[str, Any],
    *,
    conn: Optional[PgConnection] = None,
) -> NotificationPreferences:
    if not isinstance(preferences, NotificationPreferencesUpdate):
        preferences = NotificationPreferencesUpdate.model_validate(preferences)
    update_payload = preferences.model_dump(by_alias=False, exclude_unset=True)
    normalized = _prepare_preferences_payload(user_id, update_payload)

    columns = [
        "user_id",
        *(_PREFERENCE_COLUMNS),
    ]
    insert_placeholders = ", ".join(["%(" + column + ")s" for column in columns])

    update_assignments = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in _PREFERENCE_COLUMNS
    )

    query = f"""
        INSERT INTO notification_prefs ({', '.join(columns)}, created_at, updated_at)
        VALUES ({insert_placeholders}, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE
        SET {update_assignments}, updated_at = NOW()
        RETURNING
            user_id,
            reply_to_snippet,
            reply_to_comment,
            mention,
            vote_on_your_snippet,
            moderation_update,
            system,
            email_digest,
            created_at,
            updated_at
    """

    with _ensure_connection(conn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, normalized)
            row = cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert notification preferences")
    payload = {
        "userId": row["user_id"],
        "replyToSnippet": row["reply_to_snippet"],
        "replyToComment": row["reply_to_comment"],
        "mention": row["mention"],
        "voteOnYourSnippet": row["vote_on_your_snippet"],
        "moderationUpdate": row["moderation_update"],
        "system": row["system"],
        "emailDigest": row["email_digest"],
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }
    return NotificationPreferences.model_validate(payload)


__all__ = [
    "create_notification",
    "list_notifications",
    "unread_count",
    "mark_read",
    "get_preferences",
    "upsert_preferences",
    "NotificationType",
    "NotificationPreferences",
    "NotificationPreferencesUpdate",
    "EmailDigestOption",
]