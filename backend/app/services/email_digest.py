"""Utilities for compiling and dispatching email notification digests."""
from __future__ import annotations

import html
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from textwrap import shorten
from types import SimpleNamespace
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

import importlib

import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

from ..schemas.notifications import EmailDigestOption, NotificationType

EMAIL_CONFIG = SimpleNamespace(app_base_url="")
_get_conn: Optional[Callable[[], PgConnection]] = None
_get_email_provider: Optional[Callable[[], object]] = None


def _ensure_dependencies() -> None:
    global EMAIL_CONFIG, _get_conn, _get_email_provider
    if _get_conn is not None and _get_email_provider is not None:
        return

    main_module = None
    try:  # pragma: no cover - prefer canonical import path
        main_module = importlib.import_module("backend.main")
    except ModuleNotFoundError as exc:
        if exc.name and not exc.name.startswith("backend"):
            raise
        try:
            main_module = importlib.import_module("main")
        except ModuleNotFoundError:
            main_module = None

    if main_module is None:
        raise RuntimeError("Unable to locate backend configuration module")

    if hasattr(main_module, "EMAIL_CONFIG") and not getattr(EMAIL_CONFIG, "app_base_url", None):
        EMAIL_CONFIG = getattr(main_module, "EMAIL_CONFIG")
    if _get_conn is None and hasattr(main_module, "get_conn"):
        _get_conn = getattr(main_module, "get_conn")
    if _get_email_provider is None and hasattr(main_module, "get_email_provider"):
        _get_email_provider = getattr(main_module, "get_email_provider")
    if _get_conn is None or _get_email_provider is None:
        raise RuntimeError("Backend dependencies are not configured")

from ...email.renderer import render_email_digest

logger = logging.getLogger(__name__)


@dataclass
class DigestDispatchSummary:
    """Aggregated results for a digest delivery run."""

    digests_sent: int = 0
    notifications_delivered: int = 0
    failures: int = 0


_TYPE_HEADLINES: Dict[NotificationType, str] = {
    NotificationType.REPLY_TO_SNIPPET: "New reply to your snippet",
    NotificationType.REPLY_TO_COMMENT: "New reply to your comment",
    NotificationType.MENTION: "You were mentioned",
    NotificationType.VOTE_ON_YOUR_SNIPPET: "Your snippet received a vote",
    NotificationType.MODERATION_UPDATE: "Moderation update",
    NotificationType.SYSTEM: "System notification",
}


@contextmanager
def _connection_scope(conn: Optional[PgConnection]):
    if conn is not None:
        yield conn
        return
    _ensure_dependencies()
    assert _get_conn is not None  # for type checkers
    with _get_conn() as owned_conn:
        yield owned_conn


def _window_start(frequency: EmailDigestOption, now: datetime) -> datetime:
    if frequency == EmailDigestOption.DAILY:
        return now - timedelta(days=1)
    return now - timedelta(days=7)


def _normalize_base_url() -> str:
    base = getattr(EMAIL_CONFIG, "app_base_url", "").strip()
    if not base:
        return ""
    return base.rstrip("/") + "/"


def _format_item_detail(body: Optional[str]) -> str:
    if not body:
        return ""
    normalized = " ".join(body.split())
    return shorten(normalized, width=300, placeholder="…")


def _build_item_link(row: Mapping[str, object], base_url: str) -> str:
    snippet_id = row.get("snippet_id")
    comment_id = row.get("comment_id")
    if not base_url:
        return ""
    if snippet_id:
        snippet_path = f"snippet/{int(snippet_id)}"
        if comment_id:
            return f"{base_url}{snippet_path}#comment-{int(comment_id)}"
        return f"{base_url}{snippet_path}"
    return f"{base_url}notifications"


def _build_digest_items(
    rows: Iterable[Mapping[str, object]], base_url: str
) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    for row in rows:
        notification_type = NotificationType(row["type"])  # type: ignore[arg-type]
        headline = row.get("title") or _TYPE_HEADLINES.get(notification_type, "Notification update")
        detail = _format_item_detail(row.get("body"))
        created_at = row["created_at"]
        if isinstance(created_at, datetime):
            timestamp = created_at
        else:  # pragma: no cover - defensive conversion
            timestamp = datetime.fromisoformat(str(created_at))
        link = _build_item_link(row, base_url)
        items.append(
            {
                "id": int(row["id"]),
                "headline": str(headline),
                "detail": detail,
                "url": link,
                "created_at": timestamp,
            }
        )
    return items


def _render_items_text(items: Sequence[Mapping[str, object]]) -> str:
    lines: List[str] = []
    for item in items:
        created_at = item["created_at"]
        if isinstance(created_at, datetime):
            created_display = created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:  # pragma: no cover - defensive branch
            created_display = str(created_at)
        headline = item.get("headline", "Notification")
        detail = item.get("detail") or ""
        url = item.get("url") or ""
        lines.append(f"- {headline} ({created_display})")
        if detail:
            lines.append(f"  {detail}")
        if url:
            lines.append(f"  {url}")
    return "\n".join(lines)


def _render_items_html(items: Sequence[Mapping[str, object]]) -> str:
    parts = ["<ul style=\"margin: 1em 0; padding-left: 1.25em;\">"]
    for item in items:
        created_at = item["created_at"]
        if isinstance(created_at, datetime):
            created_display = created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        else:  # pragma: no cover - defensive branch
            created_display = str(created_at)
        headline = html.escape(str(item.get("headline", "Notification")))
        detail = html.escape(str(item.get("detail", ""))) if item.get("detail") else ""
        url = str(item.get("url") or "")
        parts.append("<li style=\"margin-bottom: 1em;\">")
        parts.append(f"<strong>{headline}</strong><br />")
        parts.append(f"<span style=\"color: #64748b; font-size: 0.9em;\">{created_display}</span><br />")
        if detail:
            parts.append(f"<div style=\"margin: 0.5em 0;\">{detail}</div>")
        if url:
            safe_url = html.escape(url, quote=True)
            parts.append(
                f"<a href=\"{safe_url}\" style=\"color: #2563eb;\">View activity</a>"
            )
        parts.append("</li>")
    parts.append("</ul>")
    return "".join(parts)


def _fetch_candidate_rows(
    connection: PgConnection,
    frequency: EmailDigestOption,
    window_start: datetime,
) -> List[Mapping[str, object]]:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                n.id,
                n.user_id,
                n.type::text AS type,
                n.title,
                n.body,
                n.snippet_id,
                n.comment_id,
                n.created_at,
                u.email,
                u.username
            FROM notifications n
            JOIN notification_prefs p ON p.user_id = n.user_id
            JOIN users u ON u.id = n.user_id
            WHERE p.email_digest = %s
              AND n.is_read = FALSE
              AND n.emailed_at IS NULL
              AND n.created_at >= %s
            ORDER BY n.user_id ASC, n.created_at ASC, n.id ASC
            """,
            (frequency.value, window_start),
        )
        rows = cur.fetchall()
    return list(rows)


def send_email_digests(
    frequency: EmailDigestOption,
    *,
    now: Optional[datetime] = None,
    conn: Optional[PgConnection] = None,
) -> DigestDispatchSummary:
    if frequency not in (EmailDigestOption.DAILY, EmailDigestOption.WEEKLY):
        return DigestDispatchSummary()

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    _ensure_dependencies()

    window_start = _window_start(frequency, current_time)
    summary = DigestDispatchSummary()
    base_url = _normalize_base_url()
    assert _get_email_provider is not None  # for type checkers
    provider = _get_email_provider()

    with _connection_scope(conn) as connection:
        rows = _fetch_candidate_rows(connection, frequency, window_start)
        if not rows:
            return summary

        grouped: Dict[int, Dict[str, object]] = {}
        for row in rows:
            user_id = int(row["user_id"])
            entry = grouped.setdefault(
                user_id,
                {
                    "email": row.get("email"),
                    "username": row.get("username"),
                    "rows": [],
                },
            )
            entry["rows"].append(row)

        delivered_notification_ids: List[int] = []

        for user_id, payload in grouped.items():
            email = (payload.get("email") or "").strip()
            if not email:
                logger.debug(
                    "Skipping digest for user without email",
                    extra={"user_id": user_id, "frequency": frequency.value},
                )
                continue

            items = _build_digest_items(payload["rows"], base_url)
            if not items:
                continue

            context = {
                "recipient_name": payload.get("username") or "there",
                "frequency_label": frequency.value,
                "frequency_title": frequency.value.capitalize(),
                "item_count": len(items),
                "items_text": _render_items_text(items),
                "items_html": _render_items_html(items),
                "notifications_url": f"{base_url}notifications" if base_url else "",
            }

            try:
                subject, text_body, html_body = render_email_digest(context)
                provider.send_email(email, subject, html_body, text_body)
            except Exception:
                summary.failures += 1
                logger.exception(
                    "Failed to send email digest",
                    extra={"user_id": user_id, "frequency": frequency.value},
                )
                continue

            delivered_notification_ids.extend(item["id"] for item in items)
            summary.digests_sent += 1
            summary.notifications_delivered += len(items)

        if delivered_notification_ids:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE notifications
                    SET emailed_at = %s
                    WHERE id = ANY(%s)
                    """,
                    (current_time, delivered_notification_ids),
                )

    return summary


__all__ = ["send_email_digests", "DigestDispatchSummary"]