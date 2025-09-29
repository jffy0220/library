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
from . import engagement as engagement_service
from .engagement import DEFAULT_TIMEZONE

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

from ...mail.renderer import render_email_digest, render_weekly_digest

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

def _group_rows_by_user(rows: Iterable[Mapping[str, object]]) -> Dict[int, Dict[str, object]]:
    grouped: Dict[int, Dict[str, object]] = {}
    for row in rows:
        user_id = int(row["user_id"])
        entry = grouped.setdefault(
            user_id,
            {
                "rows": [],
                "email": row.get("email"),
                "username": row.get("username"),
            },
        )
        entry["rows"].append(row)
        if not entry.get("email") and row.get("email"):
            entry["email"] = row.get("email")
        if not entry.get("username") and row.get("username"):
            entry["username"] = row.get("username")
    return grouped

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

def _render_top_tags_text(entries: Sequence[Mapping[str, object]]) -> str:
    if not entries:
        return "No tagged snippets this week."
    lines = []
    for entry in entries:
        line = f"- #{entry.get('name', '')}: {entry.get('count', 0)} mention(s)"
        url = entry.get("url")
        if url:
            line += f" → {url}"
        lines.append(line)
    return "\n".join(lines)


def _render_top_tags_html(entries: Sequence[Mapping[str, object]]) -> str:
    if not entries:
        return "<p>You did not add any tagged snippets this week.</p>"
    parts = ["<ul style=\"margin: 0; padding-left: 1.25em;\">"]
    for entry in entries:
        name = html.escape(str(entry.get("name", "")))
        count = int(entry.get("count", 0))
        url = str(entry.get("url") or "")
        parts.append("<li style=\"margin-bottom: 0.5em;\">")
        parts.append(f"<strong>#{name}</strong> — {count} snippet{'s' if count != 1 else ''}")
        if url:
            safe_url = html.escape(url, quote=True)
            parts.append(
                f" <a href=\"{safe_url}\" style=\"color: #2563eb;\">Open saved search</a>"
            )
        parts.append("</li>")
    parts.append("</ul>")
    return "".join(parts)


def _render_rediscover_text(
    items: Sequence[Mapping[str, object]], base_url: str
) -> str:
    if not items:
        return "Nothing to rediscover this week — keep exploring!"
    lines: List[str] = []
    for item in items:
        created = item.get("created_utc")
        created_label = ""
        if isinstance(created, datetime):
            created_label = created.date().isoformat()
        title = item.get("title") or "Untitled"
        snippet_id = item.get("id")
        url = f"{base_url}snippet/{snippet_id}" if base_url and snippet_id else ""
        line = f"- {title} ({created_label})"
        if url:
            line += f" → {url}"
        excerpt = item.get("excerpt")
        if excerpt:
            line += f"\n  {excerpt}"
        lines.append(line)
    return "\n".join(lines)


def _render_rediscover_html(
    items: Sequence[Mapping[str, object]], base_url: str
) -> str:
    if not items:
        return "<p>We did not find older snippets to revisit this week.</p>"
    parts = ["<ul style=\"margin: 0; padding-left: 1.25em;\">"]
    for item in items:
        title = html.escape(str(item.get("title", "Untitled")))
        created = item.get("created_utc")
        if isinstance(created, datetime):
            created_label = created.date().isoformat()
        else:
            created_label = html.escape(str(created)) if created else ""
        excerpt = html.escape(str(item.get("excerpt", "")))
        snippet_id = item.get("id")
        url = f"{base_url}snippet/{snippet_id}" if base_url and snippet_id else ""
        parts.append("<li style=\"margin-bottom: 1em;\">")
        parts.append(f"<strong>{title}</strong>")
        if created_label:
            parts.append(f"<br /><span style=\"color: #64748b;\">{created_label}</span>")
        if excerpt:
            parts.append(f"<div style=\"margin-top: 0.5em;\">{excerpt}</div>")
        if url:
            safe_url = html.escape(url, quote=True)
            parts.append(
                f"<a href=\"{safe_url}\" style=\"color: #2563eb;\">Open snippet</a>"
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

def _fetch_weekly_subscribers(connection: PgConnection) -> List[Mapping[str, object]]:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT u.id, u.email, u.username, COALESCE(up.timezone, %s) AS timezone
            FROM users u
            LEFT JOIN notification_prefs p ON p.user_id = u.id
            LEFT JOIN user_profiles up ON up.user_id = u.id
            WHERE (p.email_digest = %s OR p.email_digest IS NULL)
              AND u.email IS NOT NULL
            """,
            (DEFAULT_TIMEZONE, EmailDigestOption.WEEKLY.value),
        )
        rows = cur.fetchall()
    return list(rows)


def _prepare_daily_recipients(
    notification_rows: Sequence[Mapping[str, object]],
    *,
    base_url: str,
) -> List[Dict[str, object]]:
    grouped = _group_rows_by_user(notification_rows)
    recipients: List[Dict[str, object]] = []
    for user_id, payload in grouped.items():
        email = (payload.get("email") or "").strip()
        if not email:
            continue
        items = _build_digest_items(payload["rows"], base_url)
        if not items:
            continue
        context = {
            "recipient_name": payload.get("username") or "there",
            "frequency_label": EmailDigestOption.DAILY.value,
            "frequency_title": "Daily",
            "item_count": len(items),
            "items_text": _render_items_text(items),
            "items_html": _render_items_html(items),
            "notifications_url": f"{base_url}notifications" if base_url else "",
        }
        recipients.append(
            {
                "user_id": user_id,
                "email": email,
                "context": context,
                "notification_ids": [item["id"] for item in items],
                "notification_count": len(items),
                "template": "daily",
            }
        )
    return recipients


def _prepare_weekly_recipients(
    connection: PgConnection,
    notification_rows: Sequence[Mapping[str, object]],
    *,
    base_url: str,
    now: datetime,
) -> List[Dict[str, object]]:
    grouped = _group_rows_by_user(notification_rows)
    subscribers = _fetch_weekly_subscribers(connection)
    for subscriber in subscribers:
        user_id = int(subscriber["id"])
        entry = grouped.setdefault(user_id, {"rows": []})
        entry.setdefault("rows", [])
        entry["email"] = subscriber.get("email")
        entry["username"] = subscriber.get("username")
        entry["timezone"] = subscriber.get("timezone")

    recipients: List[Dict[str, object]] = []
    for user_id, payload in grouped.items():
        email = (payload.get("email") or "").strip()
        if not email:
            continue
        timezone_name = payload.get("timezone") or DEFAULT_TIMEZONE
        items = _build_digest_items(payload.get("rows", []), base_url)
        notification_ids = [item["id"] for item in items]
        weekly_summary = engagement_service.weekly_activity_summary(
            connection,
            user_id,
            timezone_name,
            now=now,
            base_url=base_url,
        )

        period_start = weekly_summary.get("period_start")
        period_end = weekly_summary.get("period_end")
        timezone_label = weekly_summary.get("timezone") or timezone_name
        period_start_label = period_start.isoformat() if hasattr(period_start, "isoformat") else str(period_start)
        period_end_label = period_end.isoformat() if hasattr(period_end, "isoformat") else str(period_end)
        period_range = f"{period_start_label} – {period_end_label} ({timezone_label})"

        top_tags = weekly_summary.get("top_tags", [])
        rediscover_items = weekly_summary.get("rediscover", [])
        recent_count = int(weekly_summary.get("recent_count", 0))
        recent_line = (
            "You captured 1 new snippet."
            if recent_count == 1
            else f"You captured {recent_count} new snippets."
        )

        context = {
            "recipient_name": payload.get("username") or "there",
            "weekly_period": period_range,
            "weekly_recent_line": recent_line,
            "weekly_recent_count": recent_count,
            "weekly_top_tags_text": _render_top_tags_text(top_tags),
            "weekly_top_tags_html": _render_top_tags_html(top_tags),
            "weekly_rediscover_text": _render_rediscover_text(rediscover_items, base_url),
            "weekly_rediscover_html": _render_rediscover_html(rediscover_items, base_url),
            "notifications_text": _render_items_text(items) if items else "",
            "notifications_html": _render_items_html(items) if items else "",
            "notifications_url": f"{base_url}notifications" if base_url else "",
        }

        recipients.append(
            {
                "user_id": user_id,
                "email": email,
                "context": context,
                "notification_ids": notification_ids,
                "notification_count": len(items),
                "template": "weekly",
            }
        )

    return recipients

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
        notification_rows = _fetch_candidate_rows(connection, frequency, window_start)
        if frequency == EmailDigestOption.DAILY:
            recipients = _prepare_daily_recipients(notification_rows, base_url=base_url)
        else:
            recipients = _prepare_weekly_recipients(
                connection,
                notification_rows,
                base_url=base_url,
                now=current_time,
            )

        if not recipients:
            return summary

        delivered_notification_ids: List[int] = []

        for recipient in recipients:
            email = recipient["email"]
            context = recipient["context"]
            template = recipient.get("template")

            try:
                if template == "weekly":
                    subject, text_body, html_body = render_weekly_digest(context)
                else:
                    subject, text_body, html_body = render_email_digest(context)
                provider.send_email(email, subject, html_body, text_body)
            except Exception:
                summary.failures += 1
                logger.exception(
                    "Failed to send email digest",
                    extra={"user_id": recipient["user_id"], "frequency": frequency.value},
                )
                continue

            delivered_notification_ids.extend(recipient.get("notification_ids", []))
            summary.digests_sent += 1
            summary.notifications_delivered += int(recipient.get("notification_count", 0))

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