"""Utilities for engagement features such as streaks and weekly summaries."""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]


DEFAULT_TIMEZONE = "UTC"
REDISCOVER_MIN_AGE_DAYS = 45
WEEKLY_WINDOW_DAYS = 7
RECENT_TAG_LOOKBACK_DAYS = 30
MAX_TOP_TAGS = 5
MAX_REDISCOVER_ITEMS = 3


_get_conn_factory: Optional[Callable[[], PgConnection]] = None


def _ensure_conn_factory() -> None:
    global _get_conn_factory
    if _get_conn_factory is not None:
        return
    module = None
    try:  # pragma: no cover - defer to canonical import path
        module = importlib.import_module("backend.main")
    except ModuleNotFoundError as exc:
        if exc.name != "backend":
            raise
        try:
            module = importlib.import_module("main")
        except ModuleNotFoundError:
            module = None
    if module is None or not hasattr(module, "get_conn"):
        raise RuntimeError("Unable to locate database connection factory")
    _get_conn_factory = getattr(module, "get_conn")


@dataclass
class StreakBadges:
    name: str
    icon: str
    threshold: int
    description: str = ""


BADGE_THRESHOLDS: Sequence[StreakBadges] = (
    StreakBadges(name="Getting started", icon="✨", threshold=1, description="Logged your first snippet"),
    StreakBadges(name="Building momentum", icon="🔥", threshold=3, description="Three days in a row"),
    StreakBadges(name="Weekly habit", icon="📅", threshold=7, description="A full week of captures"),
    StreakBadges(name="Consistent curator", icon="🏅", threshold=14, description="Two weeks strong"),
    StreakBadges(name="Monthly master", icon="🏆", threshold=30, description="Thirty day streak"),
)


def _normalize_timezone(value: Optional[str]) -> str:
    if not value:
        return DEFAULT_TIMEZONE
    candidate = value.strip()
    if not candidate:
        return DEFAULT_TIMEZONE
    try:
        ZoneInfo(candidate)
    except Exception:  # pragma: no cover - defensive fallback for invalid tz
        return DEFAULT_TIMEZONE
    return candidate


def upsert_timezone(conn: PgConnection, user_id: int, timezone_name: Optional[str]) -> str:
    """Persist the supplied timezone for the user and return the stored value."""

    tz = _normalize_timezone(timezone_name)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_profiles (user_id, timezone)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET timezone = EXCLUDED.timezone,
                updated_at = NOW()
            """,
            (user_id, tz),
        )
    return tz


def resolve_timezone(conn: PgConnection, user_id: int, fallback: Optional[str] = None) -> str:
    """Return the stored timezone or a normalized fallback if none exists."""

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT timezone FROM user_profiles WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    if row and row.get("timezone"):
        return _normalize_timezone(row["timezone"])
    return _normalize_timezone(fallback)


def _fetch_activity_days(conn: PgConnection, user_id: int, timezone_name: str) -> List[date]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT (created_utc AT TIME ZONE %s)::date AS local_day
            FROM snippets
            WHERE created_by_user_id = %s
            ORDER BY local_day ASC
            """,
            (timezone_name, user_id),
        )
        rows = cur.fetchall()
    return [row["local_day"] for row in rows if row.get("local_day")]


def _compute_longest_streak(days: Sequence[date]) -> int:
    if not days:
        return 0
    longest = 1
    current = 1
    previous = days[0]
    for current_day in days[1:]:
        if (current_day - previous).days == 1:
            current += 1
        else:
            current = 1
        if current > longest:
            longest = current
        previous = current_day
    return longest


def _compute_current_streak(days: Sequence[date], today: date) -> Tuple[int, bool, Optional[date]]:
    if not days:
        return 0, False, None
    day_set = set(days)
    active_today = today in day_set
    if active_today:
        streak = 1
        cursor = today - timedelta(days=1)
    elif (today - timedelta(days=1)) in day_set:
        streak = 1
        cursor = today - timedelta(days=2)
    else:
        return 0, False, max(day_set)

    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)

    return streak, active_today, max(day_set)


def _select_badges(current_streak: int) -> Tuple[Optional[StreakBadges], Optional[StreakBadges]]:
    current_badge: Optional[StreakBadges] = None
    next_badge: Optional[StreakBadges] = None
    for badge in BADGE_THRESHOLDS:
        if current_streak >= badge.threshold:
            current_badge = badge
        elif next_badge is None:
            next_badge = badge
            break
    if current_badge and next_badge is None:
        next_badge = None
    return current_badge, next_badge


def calculate_streak(
    conn: PgConnection,
    user_id: int,
    timezone_name: str,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    """Return streak statistics for the provided user."""

    tz = _normalize_timezone(timezone_name)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    local_today = current_time.astimezone(ZoneInfo(tz)).date()

    days = _fetch_activity_days(conn, user_id, tz)
    longest = _compute_longest_streak(days)
    current_streak, active_today, last_day = _compute_current_streak(days, local_today)
    current_badge, next_badge = _select_badges(current_streak)

    summary: Dict[str, object] = {
        "current": current_streak,
        "longest": longest,
        "active_today": active_today,
        "last_active_date": last_day,
        "timezone": tz,
    }
    if current_badge:
        summary["current_badge"] = current_badge
    if next_badge:
        summary["next_badge"] = next_badge
    return summary


def _render_snippet_excerpt(row: Mapping[str, object]) -> str:
    text = (row.get("text_snippet") or "").strip()
    if not text:
        text = (row.get("thoughts") or "").strip()
    if not text:
        return ""
    words = text.split()
    if len(words) <= 50:
        return " ".join(words)
    return " ".join(words[:50]) + "…"


def _normalize_query_payload(raw: Mapping[str, object]) -> str:
    return json.dumps(raw, sort_keys=True)


def _ensure_saved_search(
    conn: PgConnection,
    *,
    user_id: int,
    name: str,
    query: Mapping[str, object],
) -> int:
    serialized = _normalize_query_payload(query)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, query
            FROM saved_searches
            WHERE user_id = %s AND name = %s
            LIMIT 1
            """,
            (user_id, name),
        )
        row = cur.fetchone()
        if row:
            stored = row.get("query") or {}
            stored_serialized = (
                _normalize_query_payload(stored)
                if isinstance(stored, Mapping)
                else json.dumps(stored, sort_keys=True)
            )
            if stored_serialized != serialized:
                cur.execute(
                    """
                    UPDATE saved_searches
                    SET query = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (serialized, row["id"]),
                )
                updated = cur.fetchone()
                return int(updated["id"] if updated else row["id"])
            return int(row["id"])

        cur.execute(
            """
            INSERT INTO saved_searches (user_id, name, query)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (user_id, name, serialized),
        )
        created = cur.fetchone()
    if not created:
        raise RuntimeError("Failed to upsert saved search")
    return int(created["id"])


def _fetch_recent_tags(
    conn: PgConnection,
    *,
    user_id: int,
    window_start: datetime,
) -> List[Tuple[str, str, int]]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT t.name, t.slug, COUNT(*) AS usage_count
            FROM snippet_tags st
            JOIN snippets s ON s.id = st.snippet_id
            JOIN tags t ON t.id = st.tag_id
            WHERE s.created_by_user_id = %s
              AND s.created_utc >= %s
            GROUP BY t.id, t.name, t.slug
            ORDER BY usage_count DESC, LOWER(t.name)
            LIMIT %s
            """,
            (user_id, window_start, MAX_TOP_TAGS),
        )
        rows = cur.fetchall()
    return [(row["name"], row["slug"], int(row["usage_count"])) for row in rows]


def _fetch_rediscover_snippets(
    conn: PgConnection,
    *,
    user_id: int,
    before: datetime,
    tag_slugs: Sequence[str],
    limit: int = MAX_REDISCOVER_ITEMS,
) -> List[Dict[str, object]]:
    if not tag_slugs:
        return []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (s.id) s.id, s.book_name, s.text_snippet, s.thoughts, s.created_utc
            FROM snippets s
            JOIN snippet_tags st ON st.snippet_id = s.id
            JOIN tags t ON t.id = st.tag_id
            WHERE s.created_by_user_id = %s
              AND s.created_utc < %s
              AND t.slug = ANY(%s)
            ORDER BY s.id, s.created_utc DESC
            LIMIT %s
            """,
            (user_id, before, list(tag_slugs), limit),
        )
        rows = cur.fetchall()
    rediscover: List[Dict[str, object]] = []
    for row in rows:
        rediscover.append(
            {
                "id": int(row["id"]),
                "created_utc": row["created_utc"],
                "title": row.get("book_name") or "Untitled",
                "excerpt": _render_snippet_excerpt(row),
            }
        )
    return rediscover


def weekly_activity_summary(
    conn: PgConnection,
    user_id: int,
    timezone_name: str,
    *,
    now: Optional[datetime] = None,
    base_url: str = "",
) -> Dict[str, object]:
    tz = _normalize_timezone(timezone_name)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    tzinfo = ZoneInfo(tz)
    local_now = current_time.astimezone(tzinfo)
    period_end = local_now.date()
    period_start = period_end - timedelta(days=WEEKLY_WINDOW_DAYS - 1)

    utc_window_start = datetime.combine(period_start, datetime.min.time(), tzinfo).astimezone(timezone.utc)
    recent_tag_window = current_time - timedelta(days=RECENT_TAG_LOOKBACK_DAYS)
    rediscover_before = current_time - timedelta(days=REDISCOVER_MIN_AGE_DAYS)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM snippets
            WHERE created_by_user_id = %s
              AND created_utc >= %s
            """,
            (user_id, utc_window_start),
        )
        row = cur.fetchone()
        recent_count = int(row["total"]) if row else 0

    top_tags = _fetch_recent_tags(conn, user_id=user_id, window_start=recent_tag_window)
    rediscover_items = _fetch_rediscover_snippets(
        conn,
        user_id=user_id,
        before=rediscover_before,
        tag_slugs=[slug for _, slug, _ in top_tags],
    )

    top_tag_entries: List[Dict[str, object]] = []
    for name, slug, usage in top_tags:
        saved_search_id = _ensure_saved_search(
            conn,
            user_id=user_id,
            name=f"Tag: #{name}",
            query={"tags": [name]},
        )
        url = f"{base_url}?savedSearch={saved_search_id}" if base_url else ""
        top_tag_entries.append(
            {
                "name": name,
                "slug": slug,
                "count": usage,
                "saved_search_id": saved_search_id,
                "url": url,
            }
        )

    summary: Dict[str, object] = {
        "timezone": tz,
        "period_start": period_start,
        "period_end": period_end,
        "recent_count": recent_count,
        "top_tags": top_tag_entries,
        "rediscover": rediscover_items,
    }

    return summary


def engagement_status(
    user_id: int,
    *,
    timezone_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, object]:
    _ensure_conn_factory()
    assert _get_conn_factory is not None
    with _get_conn_factory() as conn:
        stored_tz = resolve_timezone(conn, user_id, fallback=timezone_name)
        if timezone_name and _normalize_timezone(timezone_name) != stored_tz:
            stored_tz = upsert_timezone(conn, user_id, timezone_name)
        streak = calculate_streak(conn, user_id, stored_tz, now=now)
    current_badge = streak.get("current_badge")
    next_badge = streak.get("next_badge")
    response: Dict[str, object] = {
        "streak": {
            "current": streak["current"],
            "longest": streak["longest"],
            "activeToday": streak["active_today"],
            "lastActiveDate": streak.get("last_active_date"),
            "timezone": streak["timezone"],
            "currentBadge": (
                {
                    "name": current_badge.name,
                    "icon": current_badge.icon,
                    "threshold": current_badge.threshold,
                    "description": current_badge.description,
                }
                if current_badge
                else None
            ),
            "nextBadge": (
                {
                    "name": next_badge.name,
                    "icon": next_badge.icon,
                    "threshold": next_badge.threshold,
                    "description": next_badge.description,
                }
                if next_badge
                else None
            ),
        }
    }
    response["showCapturePrompt"] = not bool(streak["active_today"])
    response["timezone"] = streak["timezone"]
    return response


__all__ = [
    "engagement_status",
    "calculate_streak",
    "weekly_activity_summary",
    "resolve_timezone",
    "upsert_timezone",
]