from __future__ import annotations

import base64
import json
import html
import logging
import time
from contextlib import contextmanager
from datetime import datetime
from textwrap import shorten
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urljoin

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

try:
    from backend.main import EMAIL_CONFIG, get_conn, get_email_provider
except ModuleNotFoundError as exc:  # pragma: no cover - fallback for local execution
    if exc.name != "backend":
        raise
    from main import EMAIL_CONFIG, get_conn, get_email_provider  # type: ignore[no-redef]

from ..schemas.notifications import (
    EmailDigestOption,
    Notification,
    NotificationCreate,
    NotificationListResponse,
    NotificationPreferences,
    NotificationPreferencesUpdate,
    NotificationType,
)

from ..email import render_reply_notification

logger = logging.getLogger(__name__)

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

def _format_snippet_title(row: Mapping[str, Any]) -> Optional[str]:
    title = (row.get("book_name") or "").strip()
    return title or None


def _build_snippet_excerpt(row: Mapping[str, Any]) -> Optional[str]:
    candidate = (row.get("text_snippet") or "").strip()
    if not candidate:
        candidate = (row.get("thoughts") or "").strip()
    if not candidate:
        return None
    normalized = " ".join(candidate.split())
    return shorten(normalized, width=400, placeholder="…")


def _compose_comment_context(
    connection: PgConnection,
    notification: Notification,
) -> Optional[Dict[str, Any]]:
    if not notification.comment_id or not notification.snippet_id:
        return None

    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                c.content AS comment_content,
                c.created_utc AS comment_created_at,
                c.snippet_id,
                u.username AS actor_username,
                s.book_name,
                s.text_snippet,
                s.thoughts
            FROM comments c
            JOIN snippets s ON s.id = c.snippet_id
            LEFT JOIN users u ON u.id = c.user_id
            WHERE c.id = %s
            LIMIT 1
            """,
            (notification.comment_id,),
        )
        comment_row = cur.fetchone()

    if not comment_row:
        return None

    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT email, username FROM users WHERE id = %s",
            (notification.user_id,),
        )
        recipient_row = cur.fetchone()

    if not recipient_row or not recipient_row.get("email"):
        return None

    base_url = EMAIL_CONFIG.app_base_url.rstrip("/") + "/"
    snippet_path = f"snippet/{notification.snippet_id}"
    snippet_url = urljoin(base_url, snippet_path)
    comment_url = f"{snippet_url}#comment-{notification.comment_id}"

    actor_name = comment_row.get("actor_username") or "Someone"
    recipient_name = recipient_row.get("username") or "there"
    comment_content = (comment_row.get("comment_content") or "").strip()
    comment_content_html = html.escape(comment_content).replace("\n", "<br />")

    snippet_title = _format_snippet_title(comment_row)
    snippet_excerpt = _build_snippet_excerpt(comment_row)
    if snippet_excerpt:
        snippet_excerpt_text = f"Snippet excerpt:\n{snippet_excerpt}\n\n"
        snippet_excerpt_html = (
            "<hr style=\"border: none; border-top: 1px solid #e2e8f0; margin: 1.5em 0;\" />"
            "<p style=\"margin-bottom: 0.5em; font-weight: bold;\">Snippet excerpt</p>"
            f"<p>{html.escape(snippet_excerpt).replace('\n', '<br />')}</p>"
        )
    else:
        snippet_excerpt_text = ""
        snippet_excerpt_html = ""

    return {
        "recipient_email": recipient_row["email"],
        "recipient_name": recipient_name,
        "actor_name": actor_name,
        "comment_content": comment_content,
        "comment_content_html": comment_content_html,
        "snippet_title_suffix": f" about {snippet_title}" if snippet_title else "",
        "snippet_title_suffix_html": (
            f" about <strong>{html.escape(snippet_title)}</strong>" if snippet_title else ""
        ),
        "snippet_excerpt_text_block": snippet_excerpt_text,
        "snippet_excerpt_html_block": snippet_excerpt_html,
        "snippet_url": snippet_url,
        "comment_url": comment_url,
    }


def _send_reply_notification_email(
    notification: Notification, context: Dict[str, Any]
) -> None:
    provider = get_email_provider()
    subject, text_body, html_body = render_reply_notification(notification.type, context)
    attempts = max(1, EMAIL_CONFIG.max_attempts)
    backoff = max(0.0, EMAIL_CONFIG.backoff_seconds)
    recipient = context["recipient_email"]

    for attempt in range(1, attempts + 1):
        try:
            provider.send_email(recipient, subject, html_body, text_body)
        except Exception:
            logger.exception(
                "Failed to send reply notification email",
                extra={
                    "notification_id": notification.id,
                    "email_recipient": recipient,
                    "email_attempt": attempt,
                    "email_attempts": attempts,
                },
            )
            if attempt >= attempts:
                break
            if backoff > 0:
                time.sleep(backoff * attempt)
            continue

        logger.info(
            "Reply notification email dispatched",
            extra={
                "notification_id": notification.id,
                "email_recipient": recipient,
                "email_provider": provider.describe(),
            },
        )
        break


def _maybe_send_reply_email(
    notification: Notification,
    connection: PgConnection,
) -> None:
    preference_field = _EMAIL_PREFERENCE_MAP.get(notification.type)
    if not preference_field:
        return

    try:
        preferences = get_preferences(notification.user_id, conn=connection)
    except Exception:
        logger.exception(
            "Failed to load notification preferences for email delivery",
            extra={"notification_id": notification.id},
        )
        return

    if not getattr(preferences, preference_field):
        return

    context = _compose_comment_context(connection, notification)
    if not context:
        return

    _send_reply_notification_email(notification, context)



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
    notification = _coerce_notification(row)

    with _ensure_connection(conn) as connection:
        try:
            _maybe_send_reply_email(notification, connection)
        except Exception:
            logger.exception(
                "Unexpected error while sending reply email",
                extra={"notification_id": notification.id},
            )

    return notification


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
_EMAIL_PREFERENCE_MAP: Dict[NotificationType, str] = {
    NotificationType.REPLY_TO_SNIPPET: "reply_to_snippet",
    NotificationType.REPLY_TO_COMMENT: "reply_to_comment",
}