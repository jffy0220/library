from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable, List, Optional, Tuple

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

try:  # pragma: no cover - helper for local imports
    from backend.main import get_conn
except ModuleNotFoundError as exc:  # pragma: no cover - fallback for local execution
    if exc.name != "backend":
        raise
    from main import get_conn  # type: ignore[no-redef]

from ..schemas.direct_messages import (
    DirectMessage,
    DirectMessageList,
    DirectMessageMarkReadResponse,
    DirectMessageParticipant,
    DirectMessagePreview,
    DirectMessageSendResponse,
    DirectMessageThread,
    DirectMessageThreadList,
)


@contextmanager
def _managed_connection(conn: Optional[PgConnection] = None):
    if conn is not None:
        yield conn, False
        return

    connection = get_conn()
    try:
        yield connection, True
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _build_participant_key(user_a: int, user_b: int) -> str:
    first, second = sorted((user_a, user_b))
    return f"{first}-{second}"


def _ensure_username(cursor, username: str) -> Tuple[int, str]:
    normalized = (username or "").strip()
    if not normalized:
        raise ValueError("Username is required")

    cursor.execute(
        """
        SELECT id, username
        FROM users
        WHERE LOWER(username) = LOWER(%s)
        LIMIT 1
        """,
        (normalized,),
    )
    row = cursor.fetchone()
    if not row:
        raise LookupError("User not found")
    return int(row[0]), row[1]


def _ensure_participant(
    cursor: psycopg2.extensions.cursor,
    thread_id: int,
    user_id: int,
) -> None:
    cursor.execute(
        """
        SELECT 1
        FROM dm_participants
        WHERE thread_id = %s AND user_id = %s
        LIMIT 1
        """,
        (thread_id, user_id),
    )
    if cursor.fetchone() is None:
        raise PermissionError("You do not have access to this thread")


def _fetch_thread_row(
    cursor: psycopg2.extensions.cursor,
    thread_id: int,
    user_id: int,
) -> Optional[dict]:
    cursor.execute(
        """
        SELECT
            t.id AS thread_id,
            t.created_at,
            t.last_message_at,
            other_user.id AS other_user_id,
            other_user.username AS other_username,
            last_message.id AS last_message_id,
            last_message.body AS last_message_body,
            last_message.sender_id AS last_message_sender_id,
            last_message.created_at AS last_message_created_at,
            last_sender.username AS last_message_sender_username,
            COALESCE(unread.unread_count, 0) AS unread_count
        FROM dm_participants me
        JOIN dm_threads t ON t.id = me.thread_id
        JOIN dm_participants other_participant
            ON other_participant.thread_id = t.id AND other_participant.user_id <> me.user_id
        JOIN users other_user ON other_user.id = other_participant.user_id
        LEFT JOIN LATERAL (
            SELECT m.id, m.body, m.sender_id, m.created_at
            FROM dm_messages m
            WHERE m.thread_id = t.id
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT 1
        ) AS last_message ON TRUE
        LEFT JOIN users last_sender ON last_sender.id = last_message.sender_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS unread_count
            FROM dm_messages m
            WHERE m.thread_id = t.id
              AND m.sender_id <> me.user_id
              AND (me.last_read_message_id IS NULL OR m.id > me.last_read_message_id)
        ) AS unread ON TRUE
        WHERE me.user_id = %s AND me.thread_id = %s
        LIMIT 1
        """,
        (user_id, thread_id),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    column_names = [desc[0] for desc in cursor.description]
    return dict(zip(column_names, row))


def _build_thread_from_row(row: dict) -> DirectMessageThread:
    participant = DirectMessageParticipant(
        userId=int(row["other_user_id"]),
        username=row.get("other_username") or "",
    )
    last_message = None
    if row.get("last_message_id"):
        last_message = DirectMessagePreview(
            id=int(row["last_message_id"]),
            threadId=int(row["thread_id"]),
            senderId=int(row.get("last_message_sender_id") or 0),
            senderUsername=row.get("last_message_sender_username") or "",
            body=row.get("last_message_body") or "",
            createdAt=row.get("last_message_created_at"),
        )
    last_message_at = row.get("last_message_created_at") or row.get("last_message_at")
    return DirectMessageThread(
        id=int(row["thread_id"]),
        createdAt=row.get("created_at"),
        lastMessageAt=last_message_at,
        participant=participant,
        lastMessage=last_message,
        unreadCount=int(row.get("unread_count") or 0),
    )


def _list_threads_rows(cursor, user_id: int) -> Iterable[dict]:
    cursor.execute(
        """
        SELECT
            t.id AS thread_id,
            t.created_at,
            t.last_message_at,
            other_user.id AS other_user_id,
            other_user.username AS other_username,
            last_message.id AS last_message_id,
            last_message.body AS last_message_body,
            last_message.sender_id AS last_message_sender_id,
            last_message.created_at AS last_message_created_at,
            last_sender.username AS last_message_sender_username,
            COALESCE(unread.unread_count, 0) AS unread_count
        FROM dm_participants me
        JOIN dm_threads t ON t.id = me.thread_id
        JOIN dm_participants other_participant
            ON other_participant.thread_id = t.id AND other_participant.user_id <> me.user_id
        JOIN users other_user ON other_user.id = other_participant.user_id
        LEFT JOIN LATERAL (
            SELECT m.id, m.body, m.sender_id, m.created_at
            FROM dm_messages m
            WHERE m.thread_id = t.id
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT 1
        ) AS last_message ON TRUE
        LEFT JOIN users last_sender ON last_sender.id = last_message.sender_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS unread_count
            FROM dm_messages m
            WHERE m.thread_id = t.id
              AND m.sender_id <> me.user_id
              AND (me.last_read_message_id IS NULL OR m.id > me.last_read_message_id)
        ) AS unread ON TRUE
        WHERE me.user_id = %s
        ORDER BY COALESCE(last_message.created_at, t.created_at) DESC, t.id DESC
        """,
        (user_id,),
    )
    column_names = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        yield dict(zip(column_names, row))


def list_threads(user_id: int, *, conn: Optional[PgConnection] = None) -> DirectMessageThreadList:
    with _managed_connection(conn) as (connection, _owns):
        with connection.cursor() as cur:
            rows = list(_list_threads_rows(cur, user_id))
    threads = [_build_thread_from_row(row) for row in rows]
    return DirectMessageThreadList(threads=threads)


def start_thread(
    *,
    initiator_id: int,
    target_username: str,
    conn: Optional[PgConnection] = None,
) -> DirectMessageThread:
    with _managed_connection(conn) as (connection, owns):
        with connection.cursor() as cur:
            target_id, _ = _ensure_username(cur, target_username)
            if target_id == initiator_id:
                raise ValueError("You cannot start a conversation with yourself")

            participant_key = _build_participant_key(initiator_id, target_id)
            cur.execute(
                "SELECT id FROM dm_threads WHERE participant_key = %s",
                (participant_key,),
            )
            existing = cur.fetchone()
            if existing:
                thread_id = int(existing[0])
            else:
                cur.execute(
                    """
                    INSERT INTO dm_threads (participant_key)
                    VALUES (%s)
                    RETURNING id
                    """,
                    (participant_key,),
                )
                thread_id = int(cur.fetchone()[0])
                cur.executemany(
                    """
                    INSERT INTO dm_participants (thread_id, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT (thread_id, user_id) DO NOTHING
                    """,
                    (
                        (thread_id, initiator_id),
                        (thread_id, target_id),
                    ),
                )
            cur.execute(
                """
                UPDATE dm_participants
                SET joined_at = COALESCE(joined_at, NOW())
                WHERE thread_id = %s AND user_id IN (%s, %s)
                """,
                (thread_id, initiator_id, target_id),
            )
        if owns:
            connection.commit()
        with connection.cursor() as cur:
            row = _fetch_thread_row(cur, thread_id, initiator_id)
            if row is None:
                raise LookupError("Thread not found")
    return _build_thread_from_row(row)


def get_thread(
    thread_id: int,
    *,
    user_id: int,
    conn: Optional[PgConnection] = None,
) -> DirectMessageThread:
    with _managed_connection(conn) as (connection, _owns):
        with connection.cursor() as cur:
            row = _fetch_thread_row(cur, thread_id, user_id)
            if row is None:
                raise LookupError("Thread not found")
    return _build_thread_from_row(row)


def list_messages(
    thread_id: int,
    *,
    user_id: int,
    limit: int = 30,
    cursor: Optional[int] = None,
    conn: Optional[PgConnection] = None,
) -> DirectMessageList:
    limit = max(1, min(limit, 100))
    with _managed_connection(conn) as (connection, _owns):
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _ensure_participant(cur, thread_id, user_id)
            params: List[object] = [thread_id]
            query = [
                "SELECT m.id, m.thread_id, m.sender_id, u.username AS sender_username, m.body, m.created_at",
                "FROM dm_messages m",
                "JOIN users u ON u.id = m.sender_id",
                "WHERE m.thread_id = %s",
            ]
            if cursor is not None:
                query.append("AND m.id < %s")
                params.append(cursor)
            query.append("ORDER BY m.id DESC LIMIT %s")
            params.append(limit + 1)
            cur.execute("\n".join(query), params)
            rows = cur.fetchall()

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    rows_sorted = sorted(rows, key=lambda row: row["id"])
    messages = [
        DirectMessage(
            id=int(row["id"]),
            threadId=int(row["thread_id"]),
            senderId=int(row["sender_id"]),
            senderUsername=row.get("sender_username") or "",
            body=row.get("body") or "",
            createdAt=row["created_at"],
        )
        for row in rows_sorted
    ]
    next_cursor = None
    if has_more and rows_sorted:
        next_cursor = str(rows_sorted[0]["id"])
    return DirectMessageList(messages=messages, nextCursor=next_cursor, hasMore=has_more)


def _latest_message_id(cur, thread_id: int) -> Optional[int]:
    cur.execute(
        """
        SELECT id
        FROM dm_messages
        WHERE thread_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (thread_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _unread_count(cur, thread_id: int, user_id: int) -> int:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM dm_messages m
        JOIN dm_participants p ON p.thread_id = m.thread_id AND p.user_id = %s
        WHERE m.thread_id = %s
          AND m.sender_id <> %s
          AND (p.last_read_message_id IS NULL OR m.id > p.last_read_message_id)
        """,
        (user_id, thread_id, user_id),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def mark_thread_read(
    thread_id: int,
    *,
    user_id: int,
    conn: Optional[PgConnection] = None,
) -> DirectMessageMarkReadResponse:
    with _managed_connection(conn) as (connection, owns):
        with connection.cursor() as cur:
            _ensure_participant(cur, thread_id, user_id)
            latest_id = _latest_message_id(cur, thread_id)
            cur.execute(
                """
                UPDATE dm_participants
                SET last_read_message_id = %s,
                    last_read_at = NOW()
                WHERE thread_id = %s AND user_id = %s
                """,
                (latest_id, thread_id, user_id),
            )
            unread = _unread_count(cur, thread_id, user_id)
        if owns:
            connection.commit()
    return DirectMessageMarkReadResponse(unreadCount=unread)


def send_message(
    thread_id: int,
    *,
    user_id: int,
    sender_username: str,
    body: str,
    conn: Optional[PgConnection] = None,
) -> DirectMessageSendResponse:
    message_body = (body or "").strip()
    if not message_body:
        raise ValueError("Message body cannot be empty")
    if len(message_body) > 280:
        raise ValueError("Message body must be 280 characters or fewer")

    with _managed_connection(conn) as (connection, owns):
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            _ensure_participant(cur, thread_id, user_id)
            cur.execute(
                """
                INSERT INTO dm_messages (thread_id, sender_id, body)
                VALUES (%s, %s, %s)
                RETURNING id, created_at
                """,
                (thread_id, user_id, message_body),
            )
            inserted = cur.fetchone()
            message_id = int(inserted["id"])
            created_at = inserted["created_at"]

            cur.execute(
                "UPDATE dm_threads SET last_message_at = %s WHERE id = %s",
                (created_at, thread_id),
            )
            cur.execute(
                """
                UPDATE dm_participants
                SET last_read_message_id = %s,
                    last_read_at = %s
                WHERE thread_id = %s AND user_id = %s
                """,
                (message_id, created_at, thread_id, user_id),
            )
        if owns:
            connection.commit()
        with connection.cursor() as cur:
            row = _fetch_thread_row(cur, thread_id, user_id)
            if row is None:
                raise LookupError("Thread not found")
    message = DirectMessage(
        id=message_id,
        threadId=thread_id,
        senderId=user_id,
        senderUsername=sender_username,
        body=message_body,
        createdAt=created_at,
    )
    thread = _build_thread_from_row(row)
    return DirectMessageSendResponse(message=message, thread=thread)