import asyncio
import contextlib
import hashlib
import logging
import math
import os
import re
import sys
import time
import json
import secrets
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Literal, NamedTuple, Optional, Sequence, Set, Tuple

from fastapi import (
    BackgroundTasks,
    Cookie,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from pydantic import BaseModel, ConfigDict, EmailStr, Field, conint, constr, model_validator
from urllib import error as urllib_error, parse as urllib_parse, request as urllib_request
from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.hash import bcrypt

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.append(str(_project_root))

try:
    from backend.app.schemas.notifications import NotificationCreate, NotificationType
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from app.schemas.notifications import (  # type: ignore[no-redef]
        NotificationCreate,
        NotificationType,
    )
try:
    from backend.app.email import (
        EmailConfig,
        EmailProvider,
        create_email_provider,
        load_email_config,
    )
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from app.email import (  # type: ignore[no-redef]
        EmailConfig,
        EmailProvider,
        create_email_provider,
        load_email_config,
    )

try:
    from backend.group_service import (
        fetch_group,
        fetch_group_member_ids,
        fetch_group_membership,
        is_private_group,
        is_site_admin,
        is_site_moderator,
    )
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from group_service import (  # type: ignore[no-redef]
        fetch_group,
        fetch_group_member_ids,
        fetch_group_membership,
        is_private_group,
        is_site_admin,
        is_site_moderator,
    )

try:
    from backend.analytics import router as analytics_router
    from backend.analytics_config import ANALYTICS_ENABLED
    from backend.analytics_queue import AnalyticsQueue, create_analytics_pool
    from backend.middleware_perf import PerformanceAnalyticsMiddleware
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from analytics import router as analytics_router  # type: ignore[no-redef]
    from analytics_config import ANALYTICS_ENABLED  # type: ignore[no-redef]
    from analytics_queue import AnalyticsQueue, create_analytics_pool  # type: ignore[no-redef]
    from middleware_perf import PerformanceAnalyticsMiddleware  # type: ignore[no-redef]


load_dotenv()

def _parse_connect_timeout(raw_value: str) -> int:
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise ValueError("DB_CONNECT_TIMEOUT must be a number") from exc
    if timeout < 0:
        raise ValueError("DB_CONNECT_TIMEOUT must be non-negative")
    return int(math.ceil(timeout))

DB_CFG = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "snippets_db"),
    user=os.getenv("DB_USER", "snip_user"),
    password=os.getenv("DB_PASSWORD", "snip_pass"),
    connect_timeout=_parse_connect_timeout(os.getenv("DB_CONNECT_TIMEOUT", "5")),
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXP_MINUTES = int(os.getenv("JWT_EXP_MINUTES", str(60 * 24 * 7)))  # default: 7 days
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}

logger = logging.getLogger("trending_refresh")
books_logger = logging.getLogger("book_suggestions")

ONBOARDING_TOKEN_TTL_MINUTES = int(os.getenv("ONBOARDING_TOKEN_TTL_MINUTES", str(48 * 60)))
PASSWORD_RESET_TOKEN_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_TTL_MINUTES", "60"))
AUTH_TOKEN_BYTES = int(os.getenv("AUTH_TOKEN_BYTES", "32"))
EMAIL_CONFIG: EmailConfig = load_email_config()
EMAIL_SENDER = EMAIL_CONFIG.from_email

_email_provider: EmailProvider = create_email_provider(EMAIL_CONFIG)


ONBOARDING_TOKEN_TTL = timedelta(minutes=ONBOARDING_TOKEN_TTL_MINUTES)
PASSWORD_RESET_TOKEN_TTL = timedelta(minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES)

TRENDING_REFRESH_WARN_SECONDS = float(os.getenv("TRENDING_REFRESH_WARN_SECONDS", "5.0"))
TRENDING_REFRESH_MAX_ERROR_LENGTH = int(os.getenv("TRENDING_REFRESH_MAX_ERROR_LENGTH", "1024"))
SNIPPET_VISIBILITY_VALUES = {"public", "private"}

_refresh_metrics_lock = Lock()
_refresh_metrics: Dict[str, Any] = {
    "in_progress": False,
    "last_scheduled_at": None,
    "last_started_at": None,
    "last_completed_at": None,
    "last_success_at": None,
    "last_failure_at": None,
    "last_duration_seconds": None,
    "consecutive_failures": 0,
    "last_error": None,
    "warning_threshold_seconds": TRENDING_REFRESH_WARN_SECONDS,
}

TOKEN_TYPE_ONBOARDING = "onboarding"
TOKEN_TYPE_PASSWORD_RESET = "password_reset"


class TokenValidationResult(NamedTuple):
    email: Optional[str]
    expires_at: datetime

def get_email_provider() -> EmailProvider:
    return _email_provider


def set_email_provider(provider: EmailProvider) -> None:
    global _email_provider
    _email_provider = provider

def _truncate_error_message(message: str) -> str:
    if len(message) > TRENDING_REFRESH_MAX_ERROR_LENGTH:
        return message[: TRENDING_REFRESH_MAX_ERROR_LENGTH - 3] + "..."
    return message


def _mark_refresh_start() -> None:
    started_at = datetime.utcnow()
    with _refresh_metrics_lock:
        _refresh_metrics["last_started_at"] = started_at
        _refresh_metrics["in_progress"] = True


def _mark_refresh_success(duration: float) -> None:
    completed_at = datetime.utcnow()
    with _refresh_metrics_lock:
        _refresh_metrics["last_completed_at"] = completed_at
        _refresh_metrics["last_success_at"] = completed_at
        _refresh_metrics["last_duration_seconds"] = duration
        _refresh_metrics["last_error"] = None
        _refresh_metrics["consecutive_failures"] = 0
        _refresh_metrics["in_progress"] = False
    if duration > TRENDING_REFRESH_WARN_SECONDS:
        logger.warning(
            "Trending refresh completed in %.2f seconds (threshold %.2f)",
            duration,
            TRENDING_REFRESH_WARN_SECONDS,
        )
    else:
        logger.debug("Trending refresh completed in %.2f seconds", duration)


def _mark_refresh_failure(duration: float, error: Exception) -> None:
    completed_at = datetime.utcnow()
    error_text = _truncate_error_message(f"{type(error).__name__}: {error}")
    with _refresh_metrics_lock:
        failures = int(_refresh_metrics.get("consecutive_failures", 0)) + 1
        _refresh_metrics["last_completed_at"] = completed_at
        _refresh_metrics["last_failure_at"] = completed_at
        _refresh_metrics["last_duration_seconds"] = duration
        _refresh_metrics["last_error"] = error_text
        _refresh_metrics["consecutive_failures"] = failures
        _refresh_metrics["in_progress"] = False
    logger.exception(
        "Trending refresh failed after %.2f seconds (failure #%d): %s",
        duration,
        failures,
        error_text,
    )


def schedule_trending_refresh(background_tasks: BackgroundTasks) -> None:
    with _refresh_metrics_lock:
        _refresh_metrics["last_scheduled_at"] = datetime.utcnow()
        already_in_progress = bool(_refresh_metrics.get("in_progress"))
    if already_in_progress:
        logger.debug(
            "Trending refresh already running; scheduling another run to follow the current one",
        )
    background_tasks.add_task(refresh_trending_view)


def get_trending_refresh_metrics() -> Dict[str, Any]:
    with _refresh_metrics_lock:
        return dict(_refresh_metrics)

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _delete_expired_tokens(cursor: Any, *, now: datetime) -> int:
    cursor.execute(
        "DELETE FROM user_tokens WHERE expires_at <= %s",
        (now,),
    )
    return cursor.rowcount


def prune_expired_user_tokens(now: Optional[datetime] = None) -> int:
    current_time = now or datetime.utcnow()
    with contextlib.closing(get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                return _delete_expired_tokens(cur, now=current_time)


def _issue_user_token(
    user_id: int,
    email: Optional[str],
    ttl: timedelta,
    token_type: str,
) -> Tuple[str, datetime]:
    issued_at = datetime.utcnow()
    expires_at = issued_at + ttl
    token = secrets.token_urlsafe(AUTH_TOKEN_BYTES)
    token_hash = _hash_token(token)

    with contextlib.closing(get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                _delete_expired_tokens(cur, now=issued_at)
                cur.execute(
                    "DELETE FROM user_tokens WHERE user_id = %s AND token_type = %s",
                    (user_id, token_type),
                )
                cur.execute(
                    (
                        "INSERT INTO user_tokens (user_id, token_type, token_hash, email, expires_at) "
                        "VALUES (%s, %s, %s, %s, %s)"
                    ),
                    (user_id, token_type, token_hash, email, expires_at),
                )

    return token, expires_at


def issue_onboarding_token(user_id: int, email: str) -> Tuple[str, datetime]:
    return _issue_user_token(user_id, email, ONBOARDING_TOKEN_TTL, TOKEN_TYPE_ONBOARDING)


def issue_password_reset_token(user_id: int, email: Optional[str]) -> Tuple[str, datetime]:
    return _issue_user_token(user_id, email, PASSWORD_RESET_TOKEN_TTL, TOKEN_TYPE_PASSWORD_RESET)


def _validate_user_token(
    user_id: int,
    token: str,
    token_type: str,
    *,
    consume: bool = False,
) -> Optional[TokenValidationResult]:
    token_hash = _hash_token(token)
    now = datetime.utcnow()

    with contextlib.closing(get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                _delete_expired_tokens(cur, now=now)
                cur.execute(
                    (
                        "SELECT email, expires_at, token_hash "
                        "FROM user_tokens WHERE user_id = %s AND token_type = %s"
                    ),
                    (user_id, token_type),
                )
                row = cur.fetchone()
                if not row:
                    return None
                email, expires_at, stored_hash = row
                if stored_hash != token_hash:
                    return None
                if expires_at <= now:
                    cur.execute(
                        "DELETE FROM user_tokens WHERE user_id = %s AND token_type = %s",
                        (user_id, token_type),
                    )
                    return None
                if consume:
                    cur.execute(
                        (
                            "DELETE FROM user_tokens "
                            "WHERE user_id = %s AND token_type = %s AND token_hash = %s"
                        ),
                        (user_id, token_type, token_hash),
                    )
                return TokenValidationResult(email=email, expires_at=expires_at)


def validate_onboarding_token(
    user_id: int, token: str, *, consume: bool = False
) -> Optional[TokenValidationResult]:
    return _validate_user_token(
        user_id,
        token,
        TOKEN_TYPE_ONBOARDING,
        consume=consume,
    )


def validate_password_reset_token(
    user_id: int, token: str, *, consume: bool = False
) -> Optional[TokenValidationResult]:
    return _validate_user_token(
        user_id,
        token,
        TOKEN_TYPE_PASSWORD_RESET,
        consume=consume,
    )


def send_onboarding_email(email: str, username: str, token: str, expires_at: datetime) -> None:
    provider = get_email_provider()
    log_context = {
        **provider.describe(),
        "email_sender": EMAIL_SENDER,
        "email_recipient": email,
        "email_username": username,
        "email_expires_at": expires_at.isoformat(),
        "email_token": token,
        "email_type": "onboarding",
    }
    logger.info(
        "Dispatching onboarding email",
        extra={**log_context, "email_event": "onboarding.dispatch.start"},
    )
    subject = "Welcome to the Library"
    text_body = (
        f"Hello {username},\n\n"
        "Thanks for signing up for the Library app. "
        "Use the verification token below to finish creating your account:\n\n"
        f"{token}\n\n"
        f"The token expires at {expires_at.isoformat()}.\n"
    )
    html_body = (
        "<!DOCTYPE html><html><body style=\"font-family: Arial, sans-serif; line-height: 1.5; color: #0f172a;\">"
        f"<p>Hello {username},</p>"
        "<p>Thanks for signing up for the Library app. Use the verification token below to finish creating your account.</p>"
        f"<p style=\"font-size: 1.25em; font-weight: bold; letter-spacing: 0.05em;\">{token}</p>"
        f"<p>The token expires at {expires_at.isoformat()}.</p>"
        "</body></html>"
    )
    try:
        provider.send_email(email, subject, html_body, text_body)
    except Exception:
        logger.exception(
            "Failed to send onboarding email",
            extra={**log_context, "email_event": "onboarding.dispatch.error"},
        )
        raise
    logger.info(
        "Onboarding email dispatched",
        extra={**log_context, "email_event": "onboarding.dispatch.success"},
    )


def send_password_reset_email(
    email: str, username: str, token: str, expires_at: datetime
) -> None:
    provider = get_email_provider()
    log_context = {
        **provider.describe(),
        "email_sender": EMAIL_SENDER,
        "email_recipient": email,
        "email_username": username,
        "email_expires_at": expires_at.isoformat(),
        "email_token": token,
        "email_type": "password_reset",
    }
    logger.info(
        "Dispatching password reset email",
        extra={**log_context, "email_event": "password_reset.dispatch.start"},
    )
    subject = "Reset your Library password"
    text_body = (
        f"Hello {username},\n\n"
        "A password reset was requested for your Library account. "
        "Use the token below to proceed:\n\n"
        f"{token}\n\n"
        f"This token expires at {expires_at.isoformat()}.\n"
        "If you did not request a reset you can ignore this message.\n"
    )
    html_body = (
        "<!DOCTYPE html><html><body style=\"font-family: Arial, sans-serif; line-height: 1.5; color: #0f172a;\">"
        f"<p>Hello {username},</p>"
        "<p>A password reset was requested for your Library account. Use the token below to proceed.</p>"
        f"<p style=\"font-size: 1.25em; font-weight: bold; letter-spacing: 0.05em;\">{token}</p>"
        f"<p>This token expires at {expires_at.isoformat()}.</p>"
        "<p>If you did not request a reset you can ignore this message.</p>"
        "</body></html>"
    )
    try:
        provider.send_email(email, subject, html_body, text_body)
    except Exception:
        logger.exception(
            "Failed to send password reset email",
            extra={**log_context, "email_event": "password_reset.dispatch.error"},
        )
        raise
    logger.info(
        "Password reset email dispatched",
        extra={**log_context, "email_event": "password_reset.dispatch.success"},
    )

def get_conn():
    return psycopg2.connect(**DB_CFG)

def ensure_book_catalog_entry(
    conn: psycopg2.extensions.connection,
    title: Optional[str],
    author: Optional[str],
    *,
    isbn: Optional[str] = None,
    google_volume_id: Optional[str] = None,
) -> None:
    normalized_title = (title or "").strip()
    if not normalized_title:
        return
    normalized_author = (author or "").strip()
    author_for_lookup = normalized_author.lower() if normalized_author else ""
    title_for_lookup = normalized_title.lower()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM book_catalog
            WHERE LOWER(TRIM(title)) = %s
              AND COALESCE(LOWER(TRIM(author)), '') = %s
            """,
            (title_for_lookup, author_for_lookup),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE book_catalog
                SET updated_utc = NOW(),
                    isbn = COALESCE(%s, isbn),
                    google_volume_id = COALESCE(%s, google_volume_id)
                WHERE id = %s
                """,
                (isbn, google_volume_id, row[0]),
            )
        else:
            cur.execute(
                """
                INSERT INTO book_catalog (title, author, isbn, google_volume_id)
                VALUES (%s, %s, %s, %s)
                """,
                (normalized_title, normalized_author or None, isbn, google_volume_id),
            )

def _queue_analytics_event(event: Dict[str, Any]) -> None:
    queue = getattr(app.state, "analytics_queue", None)
    if queue:
        queue.put_nowait(event)


def _build_server_event(
    name: str,
    *,
    request: Optional[Request],
    user_id: Optional[int],
    props: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base_context: Dict[str, Any] = {"source": "api"}
    if context:
        base_context.update(context)
    return {
        "event": name,
        "ts": datetime.utcnow(),
        "user_id": str(user_id) if user_id is not None else None,
        "anonymous_id": "server",
        "session_id": "server",
        "route": request.url.path if request else None,
        "props": props or {},
        "context": base_context,
        "duration_ms": duration_ms,
    }

class SnippetBase(BaseModel):
    date_read: Optional[date] = None
    book_name: Optional[str] = None
    book_author: Optional[str] = None
    page_number: Optional[int] = None
    chapter: Optional[str] = None
    verse: Optional[str] = None
    text_snippet: Optional[str] = None
    thoughts: Optional[str] = None
    tags: Optional[List[str]] = None
    visibility: Optional[str] = Field(default="public")

class TagOut(BaseModel):
    id: int
    name: str
    slug: str


class TagSummary(TagOut):
    usage_count: int

class BookSummary(BaseModel):
    name: str
    usage_count: int

class BookSuggestion(BaseModel):
    title: str
    author: Optional[str] = None
    source: Literal["catalog", "google"] = "catalog"
    isbn: Optional[str] = None
    google_volume_id: Optional[str] = Field(default=None, alias="googleVolumeId")

    model_config = ConfigDict(populate_by_name=True)

class SnippetCreate(SnippetBase):
    group_id: Optional[int] = None

class SnippetUpdate(BaseModel):
    date_read: Optional[date] = None
    book_name: Optional[str] = None
    book_author: Optional[str] = None
    page_number: Optional[int] = None
    chapter: Optional[str] = None
    verse: Optional[str] = None
    text_snippet: Optional[str] = None
    thoughts: Optional[str] = None
    tags: Optional[List[str]] = None
    visibility: Optional[str] = None

class SnippetOut(SnippetBase):
    id: int
    created_utc: datetime
    created_by_user_id: Optional[int]
    created_by_username: Optional[str]
    group_id: Optional[int] = None
    tags: List[TagOut] = Field(default_factory=list)
    visibility: str = Field(default="public")


class SnippetWithStats(SnippetOut):
    recent_comment_count: int = 0
    tag_count: int = 0
    lexeme_count: int = 0

class SnippetListResponse(BaseModel):
    items: List[SnippetOut]
    total: int
    next_page: Optional[int] = Field(default=None, alias="nextPage")

    class Config:
        allow_population_by_field_name = True

class SearchHighlight(BaseModel):
    text: Optional[str] = None
    thoughts: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class SnippetSearchResult(SnippetOut):
    search_rank: Optional[float] = Field(default=None, alias="searchRank")
    highlights: SearchHighlight = Field(default_factory=SearchHighlight)

    model_config = ConfigDict(populate_by_name=True)


class SnippetSearchResponse(BaseModel):
    items: List[SnippetSearchResult]
    total: int
    next_page: Optional[int] = Field(default=None, alias="nextPage")

    model_config = ConfigDict(populate_by_name=True)


class SavedSearchBase(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=120)
    query: Dict[str, Any]


class SavedSearchOut(SavedSearchBase):
    id: int
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True)


class SavedSearchCreate(SavedSearchBase):
    pass


class SavedSearchUpdate(BaseModel):
    name: Optional[constr(strip_whitespace=True, min_length=1, max_length=120)] = None
    query: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_any(cls, values: "SavedSearchUpdate") -> "SavedSearchUpdate":
        if values.name is None and values.query is None:
            raise ValueError("At least one field must be provided")
        return values

    model_config = ConfigDict(populate_by_name=True)


def _load_saved_search_query(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, dict):
            return loaded
    return {}

TAG_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_tag(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    slug = TAG_SLUG_RE.sub("-", value.strip().lower())
    slug = slug.strip("-")
    return slug or None


def normalize_tag_inputs(raw_tags: Optional[List[str]]) -> List[Tuple[str, str]]:
    normalized: List[Tuple[str, str]] = []
    seen: set[str] = set()
    if not raw_tags:
        return normalized
    for raw in raw_tags:
        if raw is None:
            continue
        name = raw.strip()
        if not name:
            continue
        slug = slugify_tag(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        normalized.append((name, slug))
    return normalized

def normalize_snippet_visibility(value: Optional[str]) -> str:
    normalized = (value or "public").strip().lower()
    if normalized not in SNIPPET_VISIBILITY_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid visibility setting")
    return normalized


def upsert_tags(conn, raw_tags: Optional[List[str]]) -> List[TagOut]:
    normalized = normalize_tag_inputs(raw_tags)
    if not normalized:
        return []
    tags: List[TagOut] = []
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        for name, slug in normalized:
            cur.execute(
                """
                INSERT INTO tags (name, slug)
                VALUES (%s, %s)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING id, name, slug
                """,
                (name, slug),
            )
            row = cur.fetchone()
            if row:
                tags.append(TagOut(**dict(row)))
    return tags


def fetch_tags_for_snippets(conn, snippet_ids: List[int]) -> Dict[int, List[TagOut]]:
    if not snippet_ids:
        return {}
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT st.snippet_id, t.id, t.name, t.slug
            FROM snippet_tags st
            JOIN tags t ON t.id = st.tag_id
            WHERE st.snippet_id = ANY(%s)
            ORDER BY LOWER(t.name)
            """,
            (snippet_ids,),
        )
        mapping: Dict[int, List[TagOut]] = defaultdict(list)
        for row in cur.fetchall():
            mapping[row["snippet_id"]].append(
                TagOut(id=row["id"], name=row["name"], slug=row["slug"])
            )
    return mapping


def _hydrate_saved_search(row: Any) -> SavedSearchOut:
    query_data = _load_saved_search_query(row["query"]) if "query" in row else {}
    return SavedSearchOut(
        id=row["id"],
        name=row["name"],
        query=query_data,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def fetch_saved_search(conn, saved_search_id: int, user_id: int) -> Optional[SavedSearchOut]:
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, query, created_at, updated_at
            FROM saved_searches
            WHERE id = %s AND user_id = %s
            """,
            (saved_search_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    return _hydrate_saved_search(row)


def list_saved_searches_for_user(conn, user_id: int) -> List[SavedSearchOut]:
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, query, created_at, updated_at
            FROM saved_searches
            WHERE user_id = %s
            ORDER BY updated_at DESC, id DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    return [_hydrate_saved_search(row) for row in rows]

def link_tags_to_snippet(conn, snippet_id: int, tags: List[TagOut]) -> None:
    if not tags:
        return
    values = [(snippet_id, tag.id) for tag in tags]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO snippet_tags (snippet_id, tag_id)
            VALUES %s
            ON CONFLICT (snippet_id, tag_id) DO NOTHING
            """,
            values,
        )


def refresh_trending_view() -> None:
    _mark_refresh_start()
    start_time = time.monotonic()
    conn = None
    try:
        conn = psycopg2.connect(**DB_CFG)
    except psycopg2.Error:
        return
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW trending_snippet_activity")
    except Exception as exc:
        _mark_refresh_failure(time.monotonic() - start_time, exc)
        return
    finally:
        if conn is not None:
            conn.close()

class CommentCreate(BaseModel):
    content: str
    reply_to_comment_id: Optional[int] = Field(default=None, alias="replyToCommentId")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="before")
    def _normalize_reply_comment_id(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "replyToCommentId" not in values and "reply_to_comment_id" not in values:
                for legacy_key in (
                    "parentCommentId",
                    "parent_comment_id",
                    "replyCommentId",
                    "reply_comment_id",
                ):
                    if legacy_key in values:
                        normalized = dict(values)
                        normalized["replyToCommentId"] = normalized[legacy_key]
                        return normalized
        return values

class CommentUpdate(BaseModel):
    content: Optional[str] = None

class CommentVote(BaseModel):
    vote: conint(ge=-1, le=1)

class CommentOut(BaseModel):
    id: int
    snippet_id: int
    user_id: int
    username: str
    content: str
    created_utc: datetime
    upvotes: int
    downvotes: int
    user_vote: int
    group_id: Optional[int] = None

_MENTION_PATTERN = re.compile(r"(?<!\w)@([A-Za-z0-9_]{1,80})")


def _extract_mentions(text: str) -> Set[str]:
    mentions: Dict[str, str] = {}
    for match in _MENTION_PATTERN.finditer(text):
        username = match.group(1)
        key = username.lower()
        if key not in mentions:
            mentions[key] = username
    return set(mentions.values())


def _fetch_user_ids_by_usernames(usernames: Set[str]) -> Dict[str, int]:
    if not usernames:
        return {}
    normalized = sorted({name.lower() for name in usernames if name})
    if not normalized:
        return {}
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, username FROM users WHERE LOWER(username) = ANY(%s)",
            (normalized,),
        )
        rows = cur.fetchall()
    return {row[1].lower(): row[0] for row in rows}


def _build_comment_notifications(
    actor_id: int,
    snippet_owner_id: Optional[int],
    snippet_id: int,
    comment_id: int,
    parent_comment_user_id: Optional[int],
    mention_user_ids: Iterable[int],
    allowed_mention_user_ids: Optional[Iterable[int]] = None,
) -> List[NotificationCreate]:
    events: List[NotificationCreate] = []
    if snippet_owner_id and snippet_owner_id != actor_id:
        events.append(
            NotificationCreate(
                userId=snippet_owner_id,
                actorUserId=actor_id,
                snippetId=snippet_id,
                commentId=comment_id,
                type=NotificationType.REPLY_TO_SNIPPET,
            )
        )
    if parent_comment_user_id and parent_comment_user_id != actor_id:
        events.append(
            NotificationCreate(
                userId=parent_comment_user_id,
                actorUserId=actor_id,
                snippetId=snippet_id,
                commentId=comment_id,
                type=NotificationType.REPLY_TO_COMMENT,
            )
        )
    allowed_set = set(allowed_mention_user_ids) if allowed_mention_user_ids is not None else None
    for mention_user_id in sorted({uid for uid in mention_user_ids if uid != actor_id}):
        if allowed_set is not None and mention_user_id not in allowed_set:
            continue
        events.append(
            NotificationCreate(
                userId=mention_user_id,
                actorUserId=actor_id,
                snippetId=snippet_id,
                commentId=comment_id,
                type=NotificationType.MENTION,
            )
        )
    return events


def _schedule_notification_tasks(
    background_tasks: BackgroundTasks, events: Sequence[NotificationCreate]
) -> None:
    if not events:
        return
    from backend.app.services.notifications import create_notification

    for event in events:
        background_tasks.add_task(create_notification, event)

class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_utc: datetime

class RegisterRequest(BaseModel):
    username: constr(strip_whitespace=True, min_length=3, max_length=80)
    email: EmailStr
    password: constr(min_length=8, max_length=256)


class RegisterResponse(BaseModel):
    message: str
    expires_at: datetime


class PasswordResetRequest(BaseModel):
    identifier: constr(strip_whitespace=True, min_length=3, max_length=255)


class PasswordResetResponse(BaseModel):
    message: str
    expires_at: datetime

class ReportCreate(BaseModel):
    reason: Optional[str] = None


class ReportResolve(BaseModel):
    resolution_note: Optional[str] = None


class ReportOut(BaseModel):
    id: int
    content_type: str
    content_id: int
    reporter_id: int
    reporter_username: Optional[str]
    reason: Optional[str]
    status: str
    created_utc: datetime
    resolved_utc: Optional[datetime]
    resolved_by_user_id: Optional[int]
    resolved_by_username: Optional[str]
    resolution_note: Optional[str]
    snippet: Optional[SnippetOut] = None
    comment: Optional[CommentOut] = None


class LoginRequest(BaseModel):
    username: str
    password: str


def create_access_token(*, subject: str, expires_delta: Optional[timedelta] = None) -> str:
    payload = {"sub": subject}
    if expires_delta is None:
        expires_delta = timedelta(minutes=JWT_EXP_MINUTES)
    expire = datetime.utcnow() + expires_delta
    payload["exp"] = expire
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_user_by_id(uid: int) -> Optional[UserOut]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT id, username, role, created_utc FROM users WHERE id = %s", (uid,))
        row = cur.fetchone()
    if not row:
        return None
    return UserOut(**dict(row))


def get_user_by_username(username: str):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
             "SELECT id, username, email, role, created_utc FROM users WHERE LOWER(username) = LOWER(%s)",
            (username,),
        )
        row = cur.fetchone()
    return dict(row) if row else None

def get_user_by_email(email: str):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            "SELECT id, username, email, role, created_utc FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_user_with_password(identifier: str):
    lookup = identifier.strip()
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        row = None
        if "@" in lookup:
            cur.execute(
                "SELECT id, username, password_hash, role, created_utc FROM users WHERE LOWER(email) = LOWER(%s)",
                (lookup,),
            )
            row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT id, username, password_hash, role, created_utc FROM users WHERE LOWER(username) = LOWER(%s)",
                (lookup,),
            )
            row = cur.fetchone()
    return dict(row) if row else None

def resolve_user_from_session_token(session_token: str) -> Optional[UserOut]:
    try:
        payload = jwt.decode(session_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            return None
        user_id = int(subject)
    except (JWTError, ValueError):
        return None

    return get_user_by_id(user_id)


def get_current_user(session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME)) -> UserOut:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = resolve_user_from_session_token(session_token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def get_optional_current_user(
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> Optional[UserOut]:
    if not session_token:
        return None

    try:
        user = resolve_user_from_session_token(session_token)
    except Exception:
        logger.exception("Unexpected error while resolving optional session token")
        return None
    return user


def is_moderator(user: UserOut) -> bool:
    return is_site_moderator(user)


def is_admin(user: UserOut) -> bool:
    return is_site_admin(user)


def fetch_snippet(snippet_id: int) -> Optional[SnippetOut]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT s.id, s.created_utc, s.date_read, s.book_name, s.book_author, s.page_number, s.chapter, s.verse,
                       s.text_snippet, s.thoughts, s.created_by_user_id, s.group_id, s.visibility,
                       u.username AS created_by_username
                FROM snippets s
                LEFT JOIN users u ON u.id = s.created_by_user_id
                WHERE s.id = %s
                """,
                (snippet_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        snippet = SnippetOut(**dict(row))
        tag_map = fetch_tags_for_snippets(conn, [snippet.id])
        snippet.tags = tag_map.get(snippet.id, [])
    return snippet

def ensure_snippet_visibility(snippet: SnippetOut, viewer: Optional[UserOut], conn: Optional[Any] = None) -> None:
    viewer_id = getattr(viewer, "id", None)
    if snippet.visibility != "public" and snippet.created_by_user_id != viewer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This snippet is private")

    group_id = snippet.group_id
    if group_id is None:
        return

    if viewer and (snippet.created_by_user_id == viewer.id or is_moderator(viewer)):
        return

    if viewer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Membership required to view this group snippet",
        )

    should_close = False
    connection = conn
    if connection is None:
        connection = get_conn()
        should_close = True
    try:
        membership = fetch_group_membership(connection, group_id, viewer_id)
    finally:
        if should_close:
            connection.close()

    if membership:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Membership required to view this group snippet",
    )

def fetch_comment(comment_id: int, user_id: int) -> Optional[CommentOut]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc, c.group_id,
                   COALESCE(SUM(CASE WHEN v.vote = 1 THEN 1 ELSE 0 END), 0) AS upvotes,
                   COALESCE(SUM(CASE WHEN v.vote = -1 THEN 1 ELSE 0 END), 0) AS downvotes,
                   COALESCE((
                       SELECT vote FROM comment_votes WHERE comment_id = c.id AND user_id = %s
                   ), 0) AS user_vote
            FROM comments c
            JOIN users u ON u.id = c.user_id
            LEFT JOIN comment_votes v ON v.comment_id = c.id
            WHERE c.id = %s
            GROUP BY c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc, c.group_id
            """,
            (user_id, comment_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    return CommentOut(**dict(row))


def list_comments_for_snippet(snippet_id: int, user_id: Optional[int]) -> List[CommentOut]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc, c.group_id,
                   COALESCE(SUM(CASE WHEN v.vote = 1 THEN 1 ELSE 0 END), 0) AS upvotes,
                   COALESCE(SUM(CASE WHEN v.vote = -1 THEN 1 ELSE 0 END), 0) AS downvotes,
                   CASE
                       WHEN %s IS NULL THEN 0
                       ELSE COALESCE((
                           SELECT vote FROM comment_votes WHERE comment_id = c.id AND user_id = %s
                       ), 0)
                   END AS user_vote
            FROM comments c
            JOIN users u ON u.id = c.user_id
            LEFT JOIN comment_votes v ON v.comment_id = c.id
            WHERE c.snippet_id = %s
            GROUP BY c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc, c.group_id
            ORDER BY c.created_utc DESC
            """,
            (user_id, user_id, snippet_id),
        )
        rows = cur.fetchall()
    return [CommentOut(**dict(r)) for r in rows]

def build_report_from_row(row, viewer: UserOut) -> ReportOut:
    data = dict(row)
    snippet = None
    comment = None
    if data["content_type"] == "snippet":
        snippet = fetch_snippet(data["content_id"])
    elif data["content_type"] == "comment":
        comment = fetch_comment(data["content_id"], viewer.id)
    data["snippet"] = snippet
    data["comment"] = comment
    return ReportOut(**data)


def fetch_report(report_id: int, viewer: UserOut) -> Optional[ReportOut]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT r.id, r.content_type, r.content_id, r.reporter_id, ru.username AS reporter_username,
                   r.reason, r.status, r.created_utc, r.resolved_utc, r.resolved_by_user_id,
                   rb.username AS resolved_by_username, r.resolution_note
            FROM content_flags r
            LEFT JOIN users ru ON ru.id = r.reporter_id
            LEFT JOIN users rb ON rb.id = r.resolved_by_user_id
            WHERE r.id = %s
            """,
            (report_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return build_report_from_row(row, viewer)


def create_report_for_content(content_type: str, content_id: int, reporter: UserOut, reason: Optional[str]) -> ReportOut:
    reason_text = (reason or "").strip()
    reason_value = reason_text or None

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM content_flags
            WHERE content_type = %s AND content_id = %s AND reporter_id = %s AND status = 'open'
            """,
            (content_type, content_id, reporter.id),
        )
        if cur.fetchone():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already reported this item")

        cur.execute(
            """
            INSERT INTO content_flags (content_type, content_id, reporter_id, reason)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (content_type, content_id, reporter.id, reason_value),
        )
        report_id = cur.fetchone()[0]
        conn.commit()

    report = fetch_report(report_id, reporter)
    if report is None:
        raise HTTPException(status_code=500, detail="Unable to load report")
    return report

from backend.app.routes.billing import router as billing_router
from backend.app.routes.direct_messages import router as direct_messages_router
from backend.app.routes.engagement import router as engagement_router
from backend.app.routes.notifications import router as notifications_router
from backend.app.routes.user_preferences import (
    router as notification_preferences_router,
)
from backend.digests import (
    get_digest_metrics,
    shutdown_digest_scheduler,
    start_digest_scheduler,
)

app = FastAPI(title="Book Snippets API")

start_digest_scheduler()

app.add_middleware(PerformanceAnalyticsMiddleware)

# Vite proxy origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(billing_router)
app.include_router(direct_messages_router)
app.include_router(engagement_router)
app.include_router(notifications_router)
app.include_router(notification_preferences_router)
app.include_router(analytics_router)


@app.on_event("startup")
async def setup_analytics() -> None:
    loop = asyncio.get_running_loop()
    pool = await create_analytics_pool()
    queue = AnalyticsQueue(pool=pool, loop=loop, enabled=ANALYTICS_ENABLED)
    app.state.analytics_pool = pool
    app.state.analytics_queue = queue
    app.state.analytics_task = None
    if queue.enabled:
        app.state.analytics_task = asyncio.create_task(queue.run())


@app.on_event("shutdown")
async def teardown_analytics() -> None:
    task = getattr(app.state, "analytics_task", None)
    queue = getattr(app.state, "analytics_queue", None)
    pool = getattr(app.state, "analytics_pool", None)

    if queue:
        queue.close()

    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    if queue:
        await queue.flush()

    if pool:
        await pool.close()

@app.post("/api/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, background_tasks: BackgroundTasks):
    username = payload.username.strip()
    email = payload.email.strip().lower()
    password = payload.password

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT username, email
            FROM users
            WHERE LOWER(username) = LOWER(%s)
               OR (email IS NOT NULL AND LOWER(email) = LOWER(%s))
            LIMIT 1
            """,
            (username, email),
        )
        existing = cur.fetchone()
        if existing:
            existing_data = dict(existing)
            detail = "Username already registered"
            existing_email = existing_data.get("email")
            if existing_email and existing_email.lower() == email:
                detail = "Email already registered"
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

        password_hash = bcrypt.hash(password)
        try:
            cur.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, username, email, role, created_utc
                """,
                (username, email, password_hash),
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered",
            )
        row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to create user")

    token, expires_at = issue_onboarding_token(row["id"], email)
    background_tasks.add_task(
        send_onboarding_email,
        email,
        row["username"],
        token,
        expires_at,
    )

    signup_event = _build_server_event(
        "user_signed_up",
        request=request,
        user_id=row["id"],
        props={"has_email": bool(email)},
    )
    _queue_analytics_event(signup_event)

    return RegisterResponse(
        message="Registration successful. Check your email for verification instructions.",
        expires_at=expires_at,
    )


@app.post("/api/auth/password-reset", response_model=PasswordResetResponse)
def request_password_reset(payload: PasswordResetRequest, background_tasks: BackgroundTasks):
    identifier = payload.identifier.strip()
    normalized_email: Optional[str] = None
    user_row = None

    if "@" in identifier:
        normalized_email = identifier.lower()
        user_row = get_user_by_email(normalized_email)
    else:
        user_row = get_user_by_username(identifier)
        if user_row and user_row.get("email"):
            normalized_email = user_row["email"].lower()

    expires_at = datetime.utcnow() + PASSWORD_RESET_TOKEN_TTL

    if user_row and normalized_email:
        token, expires_at = issue_password_reset_token(user_row["id"], normalized_email)
        background_tasks.add_task(
            send_password_reset_email,
            normalized_email,
            user_row["username"],
            token,
            expires_at,
        )
    elif user_row:
        logger.warning(
            "Password reset requested for username %s but no email is associated",
            user_row["username"],
        )

    return PasswordResetResponse(
        message="If an account matches the information provided, a reset email has been sent.",
        expires_at=expires_at,
    )

@app.post("/api/auth/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, request: Request):
    identifier = payload.username.strip()
    user_row = get_user_with_password(identifier)
    if not user_row or not bcrypt.verify(payload.password, user_row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_access_token(subject=str(user_row["id"]))
    max_age = int(timedelta(minutes=JWT_EXP_MINUTES).total_seconds())
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        max_age=max_age,
        path="/",
    )

    login_event = _build_server_event(
        "user_logged_in",
        request=request,
        user_id=user_row["id"],
    )
    _queue_analytics_event(login_event)

    return UserOut(
        id=user_row["id"],
        username=user_row["username"],
        role=user_row["role"],
        created_utc=user_row["created_utc"],
    )


@app.post("/api/auth/logout")
def logout(response: Response, request: Request):
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
    )
    user_id = None
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
        except JWTError:
            user_id = None
    logout_event = _build_server_event(
        "user_logged_out",
        request=request,
        user_id=user_id,
    )
    _queue_analytics_event(logout_event)
    return {"ok": True}


@app.get("/api/auth/me", response_model=UserOut)
def read_current_user(current_user: UserOut = Depends(get_current_user)):
    return current_user

@app.get("/api/healthz")
def healthz():
    return {"ok": True}

@app.get("/api/metrics/trending-refresh")
def read_trending_refresh_metrics() -> Dict[str, Any]:
    return get_trending_refresh_metrics()

@app.get("/api/metrics/email-digests")
def read_email_digest_metrics() -> Dict[str, Any]:
    return get_digest_metrics()


@app.on_event("shutdown")
def _shutdown_digest_scheduler() -> None:
    shutdown_digest_scheduler()

@app.get("/api/snippets", response_model=SnippetListResponse)
def list_snippets(
    q: Optional[str] = Query(None, description="Full-text search query"),
    tags_csv: Optional[str] = Query(None, alias="tags", description="Comma separated list of tags"),
    tags_multi: Optional[List[str]] = Query(None, alias="tag", description="Repeatable tag filters"),
    sort: str = Query("recent", description="Sort order: recent, trending, or relevance"),
    limit: int = Query(50, ge=1, le=200),
    page: int = Query(1, ge=1, description="1-based page number for pagination"),
    current_user: Optional[UserOut] = Depends(get_optional_current_user),
):
    sort_key = sort.lower().strip()
    allowed_sorts = {"recent", "trending", "relevance"}
    if sort_key not in allowed_sorts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sort option")

    search_term = (q or "").strip()
    if not search_term:
        search_term = None

    raw_tags: List[str] = []
    if tags_csv:
        raw_tags.extend(part for part in tags_csv.split(",") if part.strip())
    if tags_multi:
        raw_tags.extend(tags_multi)
    normalized_tags = normalize_tag_inputs(raw_tags)
    tag_slugs = [slug for _, slug in normalized_tags]

    ts_vector = "to_tsvector('english', coalesce(s.text_snippet,'') || ' ' || coalesce(s.thoughts,''))"
    viewer_id = current_user.id if current_user else None
    viewer_is_moderator = bool(current_user and is_moderator(current_user))

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            select_fields = [
                "s.id",
                "s.created_utc",
                "s.date_read",
                "s.book_name",
                "s.book_author",
                "s.page_number",
                "s.chapter",
                "s.verse",
                "s.text_snippet",
                "s.thoughts",
                "s.created_by_user_id",
                "s.group_id",
                "s.visibility",
                "u.username AS created_by_username",
            ]
            joins = ["LEFT JOIN users u ON u.id = s.created_by_user_id"]
            where_clauses: List[str] = []
            params: List[object] = []

            if search_term:
                select_fields.append(
                    f"ts_rank_cd({ts_vector}, plainto_tsquery('english', %s)) AS search_rank"
                )
                params.append(search_term)
                where_clauses.append(
                    f"{ts_vector} @@ plainto_tsquery('english', %s)"
                )
                params.append(search_term)

            if tag_slugs:
                where_clauses.append(
                    "s.id IN ("
                    "SELECT st.snippet_id FROM snippet_tags st "
                    "JOIN tags t ON t.id = st.tag_id "
                    "GROUP BY st.snippet_id "
                    "HAVING COUNT(DISTINCT CASE WHEN t.slug = ANY(%s) THEN t.slug END) = %s"
                    ")"
                )
                params.append(tag_slugs)
                params.append(len(tag_slugs))

            if viewer_id is None:
                where_clauses.append("s.visibility = 'public'")
            else:
                where_clauses.append("(s.visibility = 'public' OR s.created_by_user_id = %s)")
                params.append(viewer_id)

            if viewer_is_moderator:
                pass
            elif viewer_id is None:
                where_clauses.append("s.group_id IS NULL")
            else:
                where_clauses.append(
                    "(s.group_id IS NULL OR s.created_by_user_id = %s OR EXISTS ("
                    "SELECT 1 FROM group_memberships gm WHERE gm.group_id = s.group_id AND gm.user_id = %s"
                    "))"
                )
                params.extend([viewer_id, viewer_id])

            order_clause = "s.created_utc DESC"
            if sort_key == "trending":
                select_fields.extend(
                    [
                        "COALESCE(tsa.recent_comment_count, 0) AS recent_comment_count",
                        "COALESCE(tsa.tag_count, 0) AS tag_count",
                        "COALESCE(tsa.lexeme_count, 0) AS lexeme_count",
                    ]
                )
                joins.append("LEFT JOIN trending_snippet_activity tsa ON tsa.snippet_id = s.id")
                order_clause = (
                    "COALESCE(tsa.recent_comment_count, 0) DESC, "
                    "COALESCE(tsa.tag_count, 0) DESC, "
                    "COALESCE(tsa.lexeme_count, 0) DESC, "
                    "s.created_utc DESC"
                )
            elif search_term:
                order_clause = "search_rank DESC, s.created_utc DESC"

            where_sql = ""
            if where_clauses:
                where_sql = " WHERE " + " AND ".join(where_clauses)

            filter_params = list(params)
            count_query = (
                "SELECT COUNT(DISTINCT s.id) FROM snippets s "
                + " ".join(joins)
                + where_sql
            )
            cur.execute(count_query, filter_params)
            count_row = cur.fetchone()
            total = int(count_row[0]) if count_row else 0

            offset = max((page - 1) * limit, 0)

            query = (
                "SELECT "
                + ", ".join(select_fields)
                + " FROM snippets s "
                + " ".join(joins)
                + where_sql
                + f" ORDER BY {order_clause} LIMIT %s OFFSET %s"
            )
            query_params = filter_params + [limit, offset]
            cur.execute(query, query_params)
            rows = cur.fetchall()

        snippets = [SnippetOut(**dict(row)) for row in rows]
        tag_map = fetch_tags_for_snippets(conn, [snippet.id for snippet in snippets])
        for snippet in snippets:
            snippet.tags = tag_map.get(snippet.id, [])
        next_page = None
        if offset + len(snippets) < total:
                next_page = page + 1

    return SnippetListResponse(items=snippets, total=total, next_page=next_page)


@app.get("/api/search/snippets", response_model=SnippetSearchResponse)
def search_snippets(
    request: Request,
    q: Optional[str] = Query(None, description="Full-text search query"),
    tags_csv: Optional[str] = Query(
        None, alias="tags", description="Comma separated list of tags"
    ),
    tags_multi: Optional[List[str]] = Query(
        None, alias="tag", description="Repeatable tag filters"
    ),
    book: Optional[str] = Query(None, description="Filter by book title"),
    created_from: Optional[datetime] = Query(
        None, alias="createdFrom", description="Filter by created date (inclusive)"
    ),
    created_to: Optional[datetime] = Query(
        None, alias="createdTo", description="Filter by created date (inclusive)"
    ),
    limit: int = Query(10, ge=1, le=50),
    page: int = Query(1, ge=1),
    current_user: Optional[UserOut] = Depends(get_optional_current_user),
):
    started = time.perf_counter()
    search_term = (q or "").strip()
    raw_tags: List[str] = []
    if tags_csv:
        raw_tags.extend(part for part in tags_csv.split(",") if part.strip())
    if tags_multi:
        raw_tags.extend(tags_multi)
    normalized_tags = normalize_tag_inputs(raw_tags)
    tag_slugs = [slug for _, slug in normalized_tags]

    ts_vector = "to_tsvector('english', coalesce(s.text_snippet,'') || ' ' || coalesce(s.thoughts,''))"
    viewer_id = current_user.id if current_user else None
    viewer_is_moderator = bool(current_user and is_moderator(current_user))

    select_fields = [
        "s.id",
        "s.created_utc",
        "s.date_read",
        "s.book_name",
        "s.book_author",
        "s.page_number",
        "s.chapter",
        "s.verse",
        "s.text_snippet",
        "s.thoughts",
        "s.created_by_user_id",
        "s.group_id",
        "s.visibility",
        "u.username AS created_by_username",
    ]
    select_params: List[object] = []
    where_clauses: List[str] = []
    where_params: List[object] = []
    joins = ["LEFT JOIN users u ON u.id = s.created_by_user_id"]

    if search_term:
        headline_options = (
            "StartSel=<mark>, StopSel=</mark>, MaxFragments=3, MaxWords=32, "
            "MinWords=12, ShortWord=0, FragmentDelimiter=\" … \""
        )
        thought_headline_options = (
            "StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=28, "
            "MinWords=10, ShortWord=0, FragmentDelimiter=\" … \""
        )
        select_fields.append(
            f"ts_rank_cd({ts_vector}, websearch_to_tsquery('english', %s)) AS search_rank"
        )
        select_fields.append(
            f"ts_headline('english', coalesce(s.text_snippet,''), websearch_to_tsquery('english', %s), '{headline_options}') AS text_highlight"
        )
        select_fields.append(
            f"ts_headline('english', coalesce(s.thoughts,''), websearch_to_tsquery('english', %s), '{thought_headline_options}') AS thoughts_highlight"
        )
        select_params.extend([search_term, search_term, search_term])
        where_clauses.append(
            f"{ts_vector} @@ websearch_to_tsquery('english', %s)"
        )
        where_params.append(search_term)
    else:
        select_fields.extend(
            [
                "NULL::float AS search_rank",
                "NULL::text AS text_highlight",
                "NULL::text AS thoughts_highlight",
            ]
        )

    if tag_slugs:
        where_clauses.append(
            "s.id IN ("
            "SELECT st.snippet_id FROM snippet_tags st "
            "JOIN tags t ON t.id = st.tag_id "
            "GROUP BY st.snippet_id "
            "HAVING COUNT(DISTINCT CASE WHEN t.slug = ANY(%s) THEN t.slug END) = %s"
            ")"
        )
        where_params.append(tag_slugs)
        where_params.append(len(tag_slugs))

    book_filter = (book or "").strip()
    if book_filter:
        where_clauses.append("s.book_name ILIKE %s")
        where_params.append(f"%{book_filter}%")

    if created_from:
        where_clauses.append("s.created_utc >= %s")
        where_params.append(created_from)

    if created_to:
        where_clauses.append("s.created_utc <= %s")
        where_params.append(created_to)

    if viewer_id is None:
        where_clauses.append("s.visibility = 'public'")
    else:
        where_clauses.append("(s.visibility = 'public' OR s.created_by_user_id = %s)")
        where_params.append(viewer_id)

    if viewer_is_moderator:
        pass
    elif viewer_id is None:
        where_clauses.append("s.group_id IS NULL")
    else:
        where_clauses.append(
            "(s.group_id IS NULL OR s.created_by_user_id = %s OR EXISTS ("
            "SELECT 1 FROM group_memberships gm WHERE gm.group_id = s.group_id AND gm.user_id = %s"
            "))"
        )
        where_params.extend([viewer_id, viewer_id])

    where_sql = ""
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)

    filter_params = list(where_params)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            count_query = (
                "SELECT COUNT(DISTINCT s.id) FROM snippets s "
                + " ".join(joins)
                + where_sql
            )
            cur.execute(count_query, filter_params)
            total_row = cur.fetchone()
            total = int(total_row[0]) if total_row else 0

            offset = max((page - 1) * limit, 0)

            order_clause = "search_rank DESC, s.created_utc DESC" if search_term else "s.created_utc DESC"
            query = (
                "SELECT "
                + ", ".join(select_fields)
                + " FROM snippets s "
                + " ".join(joins)
                + where_sql
                + f" ORDER BY {order_clause} LIMIT %s OFFSET %s"
            )
            query_params = select_params + filter_params + [limit, offset]
            cur.execute(query, query_params)
            rows = cur.fetchall()

        snippet_ids = [row["id"] for row in rows]
        tag_map = fetch_tags_for_snippets(conn, snippet_ids)

    results: List[SnippetSearchResult] = []
    for row in rows:
        snippet_payload = {
            "id": row["id"],
            "created_utc": row["created_utc"],
            "date_read": row["date_read"],
            "book_name": row["book_name"],
            "book_author": row.get("book_author"),
            "page_number": row["page_number"],
            "chapter": row["chapter"],
            "verse": row["verse"],
            "text_snippet": row["text_snippet"],
            "thoughts": row["thoughts"],
            "created_by_user_id": row["created_by_user_id"],
            "created_by_username": row["created_by_username"],
            "group_id": row["group_id"],
            "visibility": row["visibility"],
            "tags": tag_map.get(row["id"], []),
        }
        text_highlight = row.get("text_highlight")
        if not text_highlight and snippet_payload.get("text_snippet"):
            snippet_text = snippet_payload.get("text_snippet") or ""
            preview = snippet_text[:280]
            if len(snippet_text) > 280:
                preview = preview.rstrip() + "…"
            text_highlight = preview
        thoughts_highlight = row.get("thoughts_highlight")
        if not thoughts_highlight and snippet_payload.get("thoughts"):
            thoughts_text = snippet_payload.get("thoughts") or ""
            preview = thoughts_text[:240]
            if len(thoughts_text) > 240:
                preview = preview.rstrip() + "…"
            thoughts_highlight = preview
        result = SnippetSearchResult(
            **snippet_payload,
            search_rank=row.get("search_rank"),
            highlights=SearchHighlight(
                text=text_highlight,
                thoughts=thoughts_highlight,
            ),
        )
        results.append(result)

    next_page = None
    if (page - 1) * limit + len(results) < total:
        next_page = page + 1

    response = SnippetSearchResponse(items=results, total=total, next_page=next_page)

    duration_ms = int((time.perf_counter() - started) * 1000)
    has_filters = bool(search_term or tag_slugs or book_filter or created_from or created_to)
    if has_filters:
        filters_payload = {
            "tags": tag_slugs,
            "book": book_filter or None,
            "date_range": {
                "from": created_from.isoformat() if created_from else None,
                "to": created_to.isoformat() if created_to else None,
            },
        }
        props = {
            "q_len": len(search_term),
            "filters": filters_payload,
            "results_count": len(results),
        }
        event = _build_server_event(
            "search_performed",
            request=request,
            user_id=viewer_id,
            props=props,
            duration_ms=duration_ms,
        )
        _queue_analytics_event(event)
        if len(results) == 0:
            zero_props = {
                "q": search_term,
                "filters": filters_payload,
            }
            zero_event = _build_server_event(
                "search_zero_results",
                request=request,
                user_id=viewer_id,
                props=zero_props,
            )
            _queue_analytics_event(zero_event)

    return response

@app.get("/api/snippets/trending", response_model=List[SnippetWithStats])
def list_trending_snippets(limit: int = Query(6, ge=1, le=50)):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT s.id, s.created_utc, s.date_read, s.book_name, s.book_author, s.page_number, s.chapter, s.verse,
                       s.text_snippet, s.thoughts, s.created_by_user_id, s.group_id, s.visibility,
                       u.username AS created_by_username,
                       COALESCE(tsa.recent_comment_count, 0) AS recent_comment_count,
                       COALESCE(tsa.tag_count, 0) AS tag_count,
                       COALESCE(tsa.lexeme_count, 0) AS lexeme_count
                FROM trending_snippet_activity tsa
                JOIN snippets s ON s.id = tsa.snippet_id
                LEFT JOIN users u ON u.id = s.created_by_user_id
                WHERE s.visibility = 'public' AND s.group_id IS NULL
                ORDER BY tsa.recent_comment_count DESC, tsa.tag_count DESC, tsa.lexeme_count DESC, s.created_utc DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

        snippets = [SnippetWithStats(**dict(row)) for row in rows]
        tag_map = fetch_tags_for_snippets(conn, [snippet.id for snippet in snippets])
        for snippet in snippets:
            snippet.tags = tag_map.get(snippet.id, [])
    return snippets

@app.get("/api/search/saved/{saved_id}", response_model=SavedSearchOut)
def read_saved_search_endpoint(
    saved_id: int,
    current_user: UserOut = Depends(get_current_user),
):
    with get_conn() as conn:
        saved = fetch_saved_search(conn, saved_id, current_user.id)
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")
    return saved


@app.get("/api/search/saved", response_model=List[SavedSearchOut])
def list_saved_searches_endpoint(
    current_user: UserOut = Depends(get_current_user),
):
    with get_conn() as conn:
        return list_saved_searches_for_user(conn, current_user.id)


@app.post(
    "/api/search/saved",
    response_model=SavedSearchOut,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_search_endpoint(
    payload: SavedSearchCreate,
    current_user: UserOut = Depends(get_current_user),
):
    query_payload = payload.query or {}
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                INSERT INTO saved_searches (user_id, name, query)
                VALUES (%s, %s, %s)
                RETURNING id, name, query, created_at, updated_at
                """,
                (current_user.id, payload.name, json.dumps(query_payload)),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create saved search",
        )
    return _hydrate_saved_search(row)


@app.put("/api/search/saved/{saved_id}", response_model=SavedSearchOut)
def update_saved_search_endpoint(
    saved_id: int,
    payload: SavedSearchUpdate,
    current_user: UserOut = Depends(get_current_user),
):
    with get_conn() as conn:
        existing = fetch_saved_search(conn, saved_id, current_user.id)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")

        next_name = payload.name if payload.name is not None else existing.name
        next_query = payload.query if payload.query is not None else existing.query

        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                UPDATE saved_searches
                SET name = %s, query = %s, updated_at = NOW()
                WHERE id = %s AND user_id = %s
                RETURNING id, name, query, created_at, updated_at
                """,
                (next_name, json.dumps(next_query), saved_id, current_user.id),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")
    return _hydrate_saved_search(row)


@app.delete("/api/search/saved/{saved_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_search_endpoint(
    saved_id: int,
    current_user: UserOut = Depends(get_current_user),
):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM saved_searches WHERE id = %s AND user_id = %s",
                (saved_id, current_user.id),
            )
            deleted = cur.rowcount
        conn.commit()

    if deleted == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/api/books/catalog/search", response_model=List[BookSuggestion])
def search_book_catalog(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(12, ge=1, le=100),
):
    search = q.strip()
    if not search:
        return []
    like_pattern = f"%{search.lower()}%"

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT title, author, isbn, google_volume_id
            FROM book_catalog
            WHERE LOWER(TRIM(title)) LIKE %s
               OR LOWER(TRIM(COALESCE(author, ''))) LIKE %s
            ORDER BY LOWER(TRIM(title))
            LIMIT %s
            """,
            (like_pattern, like_pattern, limit),
        )
        rows = cur.fetchall()

    suggestions: List[BookSuggestion] = []
    for row in rows:
        title = (row["title"] or "").strip()
        if not title:
            continue
        author = (row["author"] or "").strip() or None
        suggestions.append(
            BookSuggestion(
                title=title,
                author=author,
                source="catalog",
                isbn=row.get("isbn"),
                google_volume_id=row.get("google_volume_id"),
            )
        )

    return suggestions


@app.get("/api/books/google", response_model=List[BookSuggestion])
def search_google_books(
    q: str = Query(..., min_length=5, max_length=200),
    limit: int = Query(12, ge=1, le=40),
):
    search = q.strip()
    if len(search) < 5:
        return []

    params = {"q": search, "maxResults": min(limit, 40)}
    query_string = urllib_parse.urlencode(params)
    url = f"{GOOGLE_BOOKS_API_URL}?{query_string}"
    try:
        with urllib_request.urlopen(url, timeout=5.0) as response:
            body = response.read()
        payload = json.loads(body.decode("utf-8"))
    except (urllib_error.URLError, urllib_error.HTTPError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        books_logger.warning(
            "Google Books lookup failed",
            extra={"book_query": search, "error": str(exc)},
        )
        return []

    items = payload.get("items") or []
    suggestions: List[BookSuggestion] = []
    for item in items:
        volume_info = item.get("volumeInfo") or {}
        title = (volume_info.get("title") or "").strip()
        if not title:
            continue
        authors = [author.strip() for author in volume_info.get("authors") or [] if author and author.strip()]
        author_value = ", ".join(authors) if authors else None
        isbn_value: Optional[str] = None
        for identifier in volume_info.get("industryIdentifiers") or []:
            id_type = (identifier.get("type") or "").upper()
            if id_type == "ISBN_13" and identifier.get("identifier"):
                isbn_value = identifier.get("identifier")
                break
        suggestions.append(
            BookSuggestion(
                title=title,
                author=author_value,
                source="google",
                isbn=isbn_value,
                google_volume_id=item.get("id"),
            )
        )

    return suggestions

@app.get("/api/books", response_model=List[BookSummary])
def list_books(
    q: Optional[str] = Query(default=None, min_length=0, max_length=200),
    limit: int = Query(100, ge=1, le=500),
):
    search = (q or "").strip()
    search_clause = ""
    params: List[object] = []
    if search:
        search_clause = " AND LOWER(TRIM(book_name)) LIKE %s"
        params.append(f"%{search.lower()}%")
    params.append(limit)

    query = f"""
        WITH source AS (
            SELECT TRIM(book_name) AS name
            FROM snippets
            WHERE book_name IS NOT NULL
              AND TRIM(book_name) <> ''
              {search_clause}
        )
        SELECT name, COUNT(*) AS usage_count
        FROM source
        GROUP BY name
        ORDER BY usage_count DESC, LOWER(name)
        LIMIT %s
    """

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [BookSummary(name=row["name"], usage_count=row["usage_count"]) for row in rows]


@app.get("/api/tags", response_model=List[TagSummary])
def list_tags(limit: int = Query(100, ge=1, le=500)):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT t.id, t.name, t.slug, COUNT(DISTINCT st.snippet_id) AS usage_count
            FROM tags t
            LEFT JOIN snippet_tags st ON st.tag_id = t.id
            GROUP BY t.id, t.name, t.slug
            ORDER BY LOWER(t.name)
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [TagSummary(**dict(row)) for row in rows]


@app.get("/api/tags/popular", response_model=List[TagSummary])
def list_popular_tags(
    limit: int = Query(12, ge=1, le=200),
    days: int = Query(7, ge=1, le=365),
):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT t.id, t.name, t.slug, COUNT(DISTINCT st.snippet_id) AS usage_count
            FROM tags t
            JOIN snippet_tags st ON st.tag_id = t.id
            JOIN snippets s ON s.id = st.snippet_id
            WHERE s.created_utc >= NOW() - (%s * INTERVAL '1 day')
            GROUP BY t.id, t.name, t.slug
            ORDER BY usage_count DESC, LOWER(t.name)
            LIMIT %s
            """,
            (days, limit),
        )
        rows = cur.fetchall()
    return [TagSummary(**dict(row)) for row in rows]


@app.post("/api/snippets", status_code=201)
def create_snippet(
    payload: SnippetCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: UserOut = Depends(get_current_user),
):
    visibility = normalize_snippet_visibility(payload.visibility)
    group_id = payload.group_id

    with get_conn() as conn:
        if group_id is not None:
            target_group = fetch_group(conn, group_id=group_id)
            if target_group is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Group not found")
            membership = fetch_group_membership(conn, group_id, current_user.id)
            if not membership and not is_moderator(current_user):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Membership required to post in this group",
                )
            if visibility != "public":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Private snippets cannot be shared with a group",
                )

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snippets (date_read, book_name, book_author, page_number, chapter, verse, text_snippet, thoughts, group_id, visibility, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    payload.date_read,
                    payload.book_name,
                    payload.book_author,
                    payload.page_number,
                    payload.chapter,
                    payload.verse,
                    payload.text_snippet,
                    payload.thoughts,
                    group_id,
                    visibility,
                    current_user.id,
                ),
            )
            new_id = cur.fetchone()[0]

        ensure_book_catalog_entry(conn, payload.book_name, payload.book_author)
        tags = upsert_tags(conn, payload.tags)
        if tags:
            link_tags_to_snippet(conn, new_id, tags)
        conn.commit()

    schedule_trending_refresh(background_tasks)
    props = {
        "length": len((payload.text_snippet or "").strip()),
        "has_thoughts": bool((payload.thoughts or "").strip()),
        "book_id": payload.book_name,
        "tags_count": len(payload.tags or []),
        "source": "api",
    }
    event = _build_server_event(
        "snippet_created",
        request=request,
        user_id=current_user.id,
        props=props,
    )
    _queue_analytics_event(event)
    return {"id": new_id}

@app.patch("/api/snippets/{sid}", response_model=SnippetOut)
def update_snippet(
    sid: int,
    payload: SnippetUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: UserOut = Depends(get_current_user),
):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    if snippet.created_by_user_id != current_user.id and not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this snippet")

    updates = payload.dict(exclude_unset=True)
    tag_updates = updates.pop("tags", None)
    if "visibility" in updates:
        new_visibility = normalize_snippet_visibility(updates["visibility"])
        if snippet.group_id is not None and new_visibility != "public":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Private snippets cannot be assigned to a group",
            )
        updates["visibility"] = new_visibility
    if not updates and tag_updates is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")

    set_clauses = []
    values: List[object] = []
    for field, value in updates.items():
        set_clauses.append(f"{field} = %s")
        values.append(value)

    with get_conn() as conn:
        if set_clauses:
            update_values = [*values, sid]
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE snippets SET {', '.join(set_clauses)} WHERE id = %s",
                    update_values,
                )
        
        if "book_name" in updates or "book_author" in updates:
            ensure_book_catalog_entry(
                conn,
                updates.get("book_name", snippet.book_name),
                updates.get("book_author", snippet.book_author),
            )

        if tag_updates is not None:
            new_tags = upsert_tags(conn, tag_updates)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM snippet_tags WHERE snippet_id = %s", (sid,))
            if new_tags:
                link_tags_to_snippet(conn, sid, new_tags)

        conn.commit()

    schedule_trending_refresh(background_tasks)

    updated = fetch_snippet(sid)
    if updated is None:
        raise HTTPException(status_code=500, detail="Unable to load snippet")
    
    changed_fields: List[str] = []
    if (snippet.date_read or None) != (updated.date_read or None):
        changed_fields.append("date_read")
    if (snippet.book_name or "").strip() != (updated.book_name or "").strip():
        changed_fields.append("book_name")
    if (snippet.book_author or "").strip() != (updated.book_author or "").strip():
        changed_fields.append("book_author")
    if (snippet.page_number or None) != (updated.page_number or None):
        changed_fields.append("page_number")
    if (snippet.chapter or "").strip() != (updated.chapter or "").strip():
        changed_fields.append("chapter")
    if (snippet.verse or "").strip() != (updated.verse or "").strip():
        changed_fields.append("verse")
    if (snippet.text_snippet or "").strip() != (updated.text_snippet or "").strip():
        changed_fields.append("text_snippet")
    if (snippet.thoughts or "").strip() != (updated.thoughts or "").strip():
        changed_fields.append("thoughts")
    if snippet.visibility != updated.visibility:
        changed_fields.append("visibility")
    if (snippet.group_id or None) != (updated.group_id or None):
        changed_fields.append("group_id")
    original_tags = sorted(tag.name for tag in snippet.tags)
    updated_tags = sorted(tag.name for tag in updated.tags)
    if original_tags != updated_tags:
        changed_fields.append("tags")

    props = {
        "changed_fields": sorted(set(changed_fields)),
        "source": "api",
    }
    event = _build_server_event(
        "snippet_edited",
        request=request,
        user_id=current_user.id,
        props=props,
    )
    _queue_analytics_event(event)
    return updated


@app.delete("/api/snippets/{sid}", response_model=SnippetOut)
def delete_snippet(
    sid: int,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: UserOut = Depends(get_current_user),
):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    if snippet.created_by_user_id != current_user.id and not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this snippet")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM snippets WHERE id = %s", (sid,))
        conn.commit()

    schedule_trending_refresh(background_tasks)
    event = _build_server_event(
        "snippet_deleted",
        request=request,
        user_id=current_user.id,
        props={"snippet_id": snippet.id, "source": "api"},
    )
    _queue_analytics_event(event)
    return snippet

@app.get("/api/snippets/{sid}", response_model=SnippetOut)
def get_snippet(sid: int, current_user: Optional[UserOut] = Depends(get_optional_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    ensure_snippet_visibility(snippet, current_user)
    return snippet

# run: uvicorn main:app --host 127.0.0.1 --port 8000 --reload

@app.get("/api/snippets/{sid}/comments", response_model=List[CommentOut])
def get_snippet_comments(
    sid: int, current_user: Optional[UserOut] = Depends(get_optional_current_user)
):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    ensure_snippet_visibility(snippet, current_user)
    user_id = current_user.id if current_user else None
    return list_comments_for_snippet(sid, user_id)


@app.post("/api/snippets/{sid}/comments", response_model=CommentOut, status_code=201)
def create_snippet_comment(
    sid: int,
    payload: CommentCreate,
    background_tasks: BackgroundTasks,
    current_user: UserOut = Depends(get_current_user),
):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content is required")

    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    ensure_snippet_visibility(snippet, current_user)

    parent_comment = None
    if payload.reply_to_comment_id is not None:
        parent_comment = fetch_comment(payload.reply_to_comment_id, current_user.id)
        if parent_comment is None or parent_comment.snippet_id != snippet.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent comment")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO comments (snippet_id, user_id, content)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (sid, current_user.id, content),
            )
            comment_id = cur.fetchone()[0]
            conn.commit()

    schedule_trending_refresh(background_tasks)

    comment = fetch_comment(comment_id, current_user.id)
    if comment is None:
        raise HTTPException(status_code=500, detail="Unable to load comment")
    
    mention_usernames = _extract_mentions(content)
    mentioned_user_map = _fetch_user_ids_by_usernames(mention_usernames)
    mention_user_ids = set(mentioned_user_map.values())

    allowed_mention_user_ids: Optional[Set[int]] = None
    if snippet.group_id is not None and mention_user_ids:
        with get_conn() as conn:
            allowed_mention_user_ids = fetch_group_member_ids(conn, snippet.group_id)
    
    notification_events = _build_comment_notifications(
        current_user.id,
        snippet.created_by_user_id,
        comment.snippet_id,
        comment.id,
        parent_comment.user_id if parent_comment else None,
        mention_user_ids,
        allowed_mention_user_ids,
    )
    _schedule_notification_tasks(background_tasks, notification_events)
    
    return comment

@app.patch("/api/comments/{comment_id}", response_model=CommentOut)
def update_comment(comment_id: int, payload: CommentUpdate, current_user: UserOut = Depends(get_current_user)):
    existing = fetch_comment(comment_id, current_user.id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    snippet = fetch_snippet(existing.snippet_id)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    ensure_snippet_visibility(snippet, current_user)
    if existing.user_id != current_user.id and not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this comment")

    content = (payload.content or "").strip() if payload.content is not None else None
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content is required")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE comments SET content = %s WHERE id = %s", (content, comment_id))
        conn.commit()

    updated = fetch_comment(comment_id, current_user.id)
    if updated is None:
        raise HTTPException(status_code=500, detail="Unable to load comment")
    return updated


@app.delete("/api/comments/{comment_id}", response_model=CommentOut)
def delete_comment(comment_id: int, current_user: UserOut = Depends(get_current_user)):
    existing = fetch_comment(comment_id, current_user.id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    snippet = fetch_snippet(existing.snippet_id)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    ensure_snippet_visibility(snippet, current_user)
    if existing.user_id != current_user.id and not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this comment")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
        conn.commit()

    return existing

@app.post("/api/comments/{comment_id}/vote", response_model=CommentOut)
def set_comment_vote(comment_id: int, payload: CommentVote, current_user: UserOut = Depends(get_current_user)):
    vote_value = int(payload.vote)
    if vote_value not in (-1, 0, 1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid vote value")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM comments WHERE id = %s", (comment_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        if vote_value == 0:
            cur.execute(
                "DELETE FROM comment_votes WHERE comment_id = %s AND user_id = %s",
                (comment_id, current_user.id),
            )
        else:
            cur.execute(
                """
                INSERT INTO comment_votes (comment_id, user_id, vote)
                VALUES (%s, %s, %s)
                ON CONFLICT (comment_id, user_id) DO UPDATE SET vote = EXCLUDED.vote
                """,
                (comment_id, current_user.id, vote_value),
            )
        conn.commit()

    comment = fetch_comment(comment_id, current_user.id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    snippet = fetch_snippet(comment.snippet_id)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    ensure_snippet_visibility(snippet, current_user)
    return comment

@app.post("/api/snippets/{sid}/report", response_model=ReportOut)
def report_snippet(sid: int, payload: ReportCreate, current_user: UserOut = Depends(get_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    ensure_snippet_visibility(snippet, current_user)
    return create_report_for_content("snippet", sid, current_user, payload.reason)


@app.post("/api/comments/{comment_id}/report", response_model=ReportOut)
def report_comment(comment_id: int, payload: ReportCreate, current_user: UserOut = Depends(get_current_user)):
    comment = fetch_comment(comment_id, current_user.id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    snippet = fetch_snippet(comment.snippet_id)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    ensure_snippet_visibility(snippet, current_user)
    return create_report_for_content("comment", comment_id, current_user, payload.reason)


@app.get("/api/moderation/reports", response_model=List[ReportOut])
def list_reports(current_user: UserOut = Depends(get_current_user)):
    if not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT r.id, r.content_type, r.content_id, r.reporter_id, ru.username AS reporter_username,
                   r.reason, r.status, r.created_utc, r.resolved_utc, r.resolved_by_user_id,
                   rb.username AS resolved_by_username, r.resolution_note
            FROM content_flags r
            LEFT JOIN users ru ON ru.id = r.reporter_id
            LEFT JOIN users rb ON rb.id = r.resolved_by_user_id
            ORDER BY (r.status = 'open') DESC, r.created_utc DESC
            """
        )
        rows = cur.fetchall()

    return [build_report_from_row(row, current_user) for row in rows]


@app.post("/api/moderation/reports/{report_id}/resolve", response_model=ReportOut)
def resolve_report(report_id: int, payload: ReportResolve, current_user: UserOut = Depends(get_current_user)):
    if not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    resolution_note = (payload.resolution_note or "").strip() if payload.resolution_note is not None else None

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM content_flags WHERE id = %s FOR UPDATE", (report_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Report not found")
        if row[0] == "resolved":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Report already resolved")

        cur.execute(
            """
            UPDATE content_flags
            SET status = 'resolved',
                resolved_utc = NOW(),
                resolved_by_user_id = %s,
                resolution_note = %s
            WHERE id = %s
            """,
            (current_user.id, resolution_note or None, report_id),
        )
        conn.commit()

    report = fetch_report(report_id, current_user)
    if report is None:
        raise HTTPException(status_code=500, detail="Unable to load report")
    return report

try:
    from backend import app_context
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    import app_context  # type: ignore[no-redef]

app_context.configure(
    get_conn=get_conn,
    get_current_user=get_current_user,
    get_optional_current_user=get_optional_current_user,
    user_model=UserOut,
    snippet_model=SnippetOut,
    snippet_list_response_model=SnippetListResponse,
    comment_model=CommentOut,
    fetch_tags_for_snippets=fetch_tags_for_snippets,
)

try:
    from backend import groups as group_routes
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    import groups as group_routes  # type: ignore[no-redef]

app.include_router(group_routes.router)
GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"