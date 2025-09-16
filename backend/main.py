import os
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Response, Cookie, status
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from pydantic import BaseModel
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

class SnippetIn(BaseModel):
    date_read: Optional[date] = None
    book_name: Optional[str] = None
    page_number: Optional[int] = None
    chapter: Optional[str] = None
    verse: Optional[str] = None
    text_snippet: Optional[str] = None
    thoughts: Optional[str] = None
    created_by: Optional[str] = None

class SnippetOut(SnippetIn):
    id: int
    created_utc: datetime


class UserOut(BaseModel):
    id: int
    username: str
    created_utc: datetime


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
        cur.execute("SELECT id, username, created_utc FROM users WHERE id = %s", (uid,))
        row = cur.fetchone()
    if not row:
        return None
    return UserOut(**dict(row))


def get_user_with_password(username: str):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            "SELECT id, username, password_hash, created_utc FROM users WHERE username = %s",
            (username,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_current_user(session_token: Optional[str] = Cookie(None)) -> UserOut:
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

    return UserOut(id=user_row["id"], username=user_row["username"], created_utc=user_row["created_utc"])


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
        cur.execute("""
            SELECT id, created_utc, date_read, book_name, page_number, chapter, verse, text_snippet, thoughts, created_by
            FROM snippets
            ORDER BY id DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
    return [SnippetOut(**dict(r)) for r in rows]

#test

@app.post("/api/snippets", status_code=201)
def create_snippet(payload: SnippetIn, current_user: UserOut = Depends(get_current_user)):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO snippets (date_read, book_name, page_number, chapter, verse, text_snippet, thoughts, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (payload.date_read, payload.book_name, payload.page_number, payload.chapter,
              payload.verse, payload.text_snippet, payload.thoughts, payload.created_by))
        new_id = cur.fetchone()[0]
        conn.commit()
    return {"id": new_id}

@app.get("/api/snippets/{sid}", response_model=SnippetOut)
def get_snippet(sid: int, current_user: UserOut = Depends(get_current_user)):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM snippets WHERE id=%s", (sid,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return SnippetOut(**dict(row))

# run: uvicorn main:app --host 127.0.0.1 --port 8000 --reload
