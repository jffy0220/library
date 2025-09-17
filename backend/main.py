import os
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Response, Cookie, status
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from pydantic import BaseModel, conint
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

class SnippetOut(SnippetBase):
    id: int
    created_utc: datetime
    created_by_user_id: Optional[int]
    created_by_username: Optional[str]

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


def get_current_user(session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME)) -> UserOut:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(session_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            raise ValueError("Missing subject")
        user_id = int(subject)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user

def is_moderator(user: UserOut) -> bool:
    return user.role in {"moderator", "admin"}


def fetch_snippet(snippet_id: int) -> Optional[SnippetOut]:
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
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
    return SnippetOut(**dict(row))

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


def list_comments_for_snippet(snippet_id: int, user_id: int) -> List[CommentOut]:
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
            WHERE c.snippet_id = %s
            GROUP BY c.id, c.snippet_id, c.user_id, u.username, c.content, c.created_utc
            ORDER BY c.created_utc DESC
            """,
            (user_id, snippet_id),
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
def list_snippets():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """
            SELECT s.id, s.created_utc, s.date_read, s.book_name, s.page_number, s.chapter, s.verse,
                   s.text_snippet, s.thoughts, s.created_by_user_id, u.username AS created_by_username
            FROM snippets s
            LEFT JOIN users u ON u.id = s.created_by_user_id
            ORDER BY s.id DESC
            LIMIT 100
            """
        )
        rows = cur.fetchall()
    return [SnippetOut(**dict(r)) for r in rows]

#test

@app.post("/api/snippets", status_code=201)
def create_snippet(payload: SnippetCreate, current_user: UserOut = Depends(get_current_user)):
    with get_conn() as conn, conn.cursor() as cur:
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
        conn.commit()
    return {"id": new_id}

@app.patch("/api/snippets/{sid}", response_model=SnippetOut)
def update_snippet(sid: int, payload: SnippetUpdate, current_user: UserOut = Depends(get_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    if snippet.created_by_user_id != current_user.id and not is_moderator(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this snippet")

    updates = payload.dict(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided")

    set_clauses = []
    values: List[object] = []
    for field, value in updates.items():
        set_clauses.append(f"{field} = %s")
        values.append(value)
    values.append(sid)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE snippets SET {', '.join(set_clauses)} WHERE id = %s", values)
        conn.commit()

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

    return snippet

@app.get("/api/snippets/{sid}", response_model=SnippetOut)
def get_snippet(sid: int, current_user: UserOut = Depends(get_current_user)):
    snippet = fetch_snippet(sid)
    if snippet is None:
        raise HTTPException(status_code=404, detail="Not found")
    return snippet

# run: uvicorn main:app --host 127.0.0.1 --port 8000 --reload

@app.get("/api/snippets/{sid}/comments", response_model=List[CommentOut])
def get_snippet_comments(sid: int, current_user: UserOut = Depends(get_current_user)):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM snippets WHERE id = %s", (sid,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="Snippet not found")
    return list_comments_for_snippet(sid, current_user.id)


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