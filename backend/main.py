import os
import re
from collections import defaultdict
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple

from fastapi import FastAPI, HTTPException, Depends, Response, Cookie, status, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from pydantic import BaseModel, conint, Field
from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.hash import bcrypt

load_dotenv()

DB_CFG = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "snippets_db"),
    user=os.getenv("DB_USER", "snip_user"),
    password=os.getenv("DB_PASSWORD", "snip_pass"),
)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXP_MINUTES = int(os.getenv("JWT_EXP_MINUTES", str(60 * 24 * 7)))  # default: 7 days
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}

def get_conn():
    return psycopg2.connect(**DB_CFG)

class SnippetBase(BaseModel):
    date_read: Optional[date] = None
    book_name: Optional[str] = None
    page_number: Optional[int] = None
    chapter: Optional[str] = None
    verse: Optional[str] = None
    text_snippet: Optional[str] = None
    thoughts: Optional[str] = None
    tags: Optional[List[str]] = None

class TagOut(BaseModel):
    id: int
    name: str
    slug: str


class TagSummary(TagOut):
    usage_count: int

class SnippetCreate(SnippetBase):
    pass

class SnippetUpdate(BaseModel):
    date_read: Optional[date] = None
    book_name: Optional[str] = None
    page_number: Optional[int] = None
    chapter: Optional[str] = None
    verse: Optional[str] = None
    text_snippet: Optional[str] = None
    thoughts: Optional[str] = None
    tags: Optional[List[str]] = None

class SnippetOut(SnippetBase):
    id: int
    created_utc: datetime
    created_by_user_id: Optional[int]
    created_by_username: Optional[str]
    tags: List[TagOut] = Field(default_factory=list)


class SnippetWithStats(SnippetOut):
    recent_comment_count: int = 0
    tag_count: int = 0
    lexeme_count: int = 0

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
    try:
        conn = psycopg2.connect(**DB_CFG)
    except psycopg2.Error:
        return
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW trending_snippet_activity")
    except psycopg2.Error:
        pass
    finally:
        conn.close()

class CommentCreate(BaseModel):
    content: str

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


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_utc: datetime

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


def get_user_with_password(username: str):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
             "SELECT id, username, password_hash, role, created_utc FROM users WHERE username = %s",
            (username,),
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

    user = resolve_user_from_session_token(session_token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def is_moderator(user: UserOut) -> bool:
    return user.role in {"moderator", "admin"}


def fetch_snippet(snippet_id: int) -> Optional[SnippetOut]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT s.id, s.created_utc, s.date_read, s.book_name, s.page_number, s.chapter, s.verse,
                       s.text_snippet, s.thoughts, s.created_by_user_id, u.username AS created_by_username
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

def fetch_comment(comment_id: int, user_id: int) -> Optional[CommentOut]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc,
                   COALESCE(SUM(CASE WHEN v.vote = 1 THEN 1 ELSE 0 END), 0) AS upvotes,
                   COALESCE(SUM(CASE WHEN v.vote = -1 THEN 1 ELSE 0 END), 0) AS downvotes,
                   COALESCE((
                       SELECT vote FROM comment_votes WHERE comment_id = c.id AND user_id = %s
                   ), 0) AS user_vote
            FROM comments c
            JOIN users u ON u.id = c.user_id
            LEFT JOIN comment_votes v ON v.comment_id = c.id
            WHERE c.id = %s
            GROUP BY c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc
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
            SELECT c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc,
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
            GROUP BY c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc
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

app = FastAPI(title="Book Snippets API")

# Vite proxy origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/auth/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response):
    user_row = get_user_with_password(payload.username)
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

    return UserOut(
        id=user_row["id"],
        username=user_row["username"],
        role=user_row["role"],
        created_utc=user_row["created_utc"],
    )


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
    )
    return {"ok": True}


@app.get("/api/auth/me", response_model=UserOut)
def read_current_user(current_user: UserOut = Depends(get_current_user)):
    return current_user

@app.get("/api/healthz")
def healthz():
    return {"ok": True}

@app.get("/api/snippets", response_model=List[SnippetOut])
def list_snippets(
    q: Optional[str] = Query(None, description="Full-text search query"),
    tags_csv: Optional[str] = Query(None, alias="tags", description="Comma separated list of tags"),
    tags_multi: Optional[List[str]] = Query(None, alias="tag", description="Repeatable tag filters"),
    sort: str = Query("recent", description="Sort order: recent, trending, or relevance"),
    limit: int = Query(50, ge=1, le=200),
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

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            select_fields = [
                "s.id",
                "s.created_utc",
                "s.date_read",
                "s.book_name",
                "s.page_number",
                "s.chapter",
                "s.verse",
                "s.text_snippet",
                "s.thoughts",
                "s.created_by_user_id",
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

            query = (
                "SELECT "
                + ", ".join(select_fields)
                + " FROM snippets s "
                + " ".join(joins)
                + where_sql
                + f" ORDER BY {order_clause} LIMIT %s"
            )
            params.append(limit)
            cur.execute(query, params)
            rows = cur.fetchall()

        snippets = [SnippetOut(**dict(row)) for row in rows]
        tag_map = fetch_tags_for_snippets(conn, [snippet.id for snippet in snippets])
        for snippet in snippets:
            snippet.tags = tag_map.get(snippet.id, [])
    return snippets


@app.get("/api/snippets/trending", response_model=List[SnippetWithStats])
def list_trending_snippets(limit: int = Query(6, ge=1, le=50)):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                """
                SELECT s.id, s.created_utc, s.date_read, s.book_name, s.page_number, s.chapter, s.verse,
                       s.text_snippet, s.thoughts, s.created_by_user_id, u.username AS created_by_username,
                       COALESCE(tsa.recent_comment_count, 0) AS recent_comment_count,
                       COALESCE(tsa.tag_count, 0) AS tag_count,
                       COALESCE(tsa.lexeme_count, 0) AS lexeme_count
                FROM trending_snippet_activity tsa
                JOIN snippets s ON s.id = tsa.snippet_id
                LEFT JOIN users u ON u.id = s.created_by_user_id
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
def create_snippet(payload: SnippetCreate, current_user: UserOut = Depends(get_current_user)):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO snippets (date_read, book_name, page_number, chapter, verse, text_snippet, thoughts, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    payload.date_read,
                    payload.book_name,
                    payload.page_number,
                    payload.chapter,
                    payload.verse,
                    payload.text_snippet,
                    payload.thoughts,
                    current_user.id,
                ),
            )
            new_id = cur.fetchone()[0]

        tags = upsert_tags(conn, payload.tags)
        if tags:
            link_tags_to_snippet(conn, new_id, tags)
        conn.commit()

    refresh_trending_view()
    return {"id": new_id}

@app.patch("/api/snippets/{sid}", response_model=SnippetOut)
def update_snippet(sid: int, payload: SnippetUpdate, current_user: UserOut = Depends(get_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    if snippet.created_by_user_id != current_user.id and not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this snippet")

    updates = payload.dict(exclude_unset=True)
    tag_updates = updates.pop("tags", None)
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

        if tag_updates is not None:
            new_tags = upsert_tags(conn, tag_updates)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM snippet_tags WHERE snippet_id = %s", (sid,))
            if new_tags:
                link_tags_to_snippet(conn, sid, new_tags)

        conn.commit()

    refresh_trending_view()

    updated = fetch_snippet(sid)
    if updated is None:
        raise HTTPException(status_code=500, detail="Unable to load snippet")
    return updated


@app.delete("/api/snippets/{sid}", response_model=SnippetOut)
def delete_snippet(sid: int, current_user: UserOut = Depends(get_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    if snippet.created_by_user_id != current_user.id and not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this snippet")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM snippets WHERE id = %s", (sid,))
        conn.commit()

    refresh_trending_view()
    return snippet

@app.get("/api/snippets/{sid}", response_model=SnippetOut)
def get_snippet(sid: int, _current_user: Optional[UserOut] = Depends(get_optional_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    return snippet

# run: uvicorn main:app --host 127.0.0.1 --port 8000 --reload

@app.get("/api/snippets/{sid}/comments", response_model=List[CommentOut])
def get_snippet_comments(
    sid: int, current_user: Optional[UserOut] = Depends(get_optional_current_user)
):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM snippets WHERE id = %s", (sid,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Snippet not found")
    user_id = current_user.id if current_user else None
    return list_comments_for_snippet(sid, user_id)


@app.post("/api/snippets/{sid}/comments", response_model=CommentOut, status_code=201)
def create_snippet_comment(sid: int, payload: CommentCreate, current_user: UserOut = Depends(get_current_user)):
    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Content is required")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM snippets WHERE id = %s", (sid,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Snippet not found")
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

    refresh_trending_view()

    comment = fetch_comment(comment_id, current_user.id)
    if comment is None:
        raise HTTPException(status_code=500, detail="Unable to load comment")
    return comment

@app.patch("/api/comments/{comment_id}", response_model=CommentOut)
def update_comment(comment_id: int, payload: CommentUpdate, current_user: UserOut = Depends(get_current_user)):
    existing = fetch_comment(comment_id, current_user.id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Comment not found")
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
    return comment

@app.post("/api/snippets/{sid}/report", response_model=ReportOut)
def report_snippet(sid: int, payload: ReportCreate, current_user: UserOut = Depends(get_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Snippet not found")
    return create_report_for_content("snippet", sid, current_user, payload.reason)


@app.post("/api/comments/{comment_id}/report", response_model=ReportOut)
def report_comment(comment_id: int, payload: ReportCreate, current_user: UserOut = Depends(get_current_user)):
    comment = fetch_comment(comment_id, current_user.id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
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